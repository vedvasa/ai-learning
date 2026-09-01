from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, ValidationError

from app.rag.documents import DocumentFormatError, SourceDocument, load_corpus
from app.schemas.golden_retrieval import (
    GoldenDatasetPurpose,
    GoldenRetrievalCase,
    GoldenRetrievalDataset,
    GoldenRetrievalWorksheet,
)

DEFAULT_WORKSHEET = Path("datasets/rag-evaluation/week4_human_labels.json")
DEFAULT_CORPUS = Path("datasets/knowledge-base")


class GoldenDatasetError(ValueError):
    """Safe validation error that does not repeat labeled content."""


@dataclass(frozen=True, slots=True)
class LoadedGoldenWorksheet:
    worksheet: GoldenRetrievalWorksheet
    worksheet_sha256: str
    completed_labels: int
    blank_labels: int
    dataset: GoldenRetrievalDataset | None
    dataset_sha256: str | None


def canonical_sha256(model: BaseModel) -> str:
    canonical_json = json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical_json).hexdigest()


def load_worksheet(
    path: Path,
    *,
    corpus_directory: Path,
    require_complete: bool = False,
    allow_contract_test: bool = False,
) -> LoadedGoldenWorksheet:
    try:
        raw_worksheet = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GoldenDatasetError(
            f"Could not read valid JSON from {path.name}."
        ) from error
    try:
        worksheet = GoldenRetrievalWorksheet.model_validate(raw_worksheet)
    except ValidationError as error:
        raise GoldenDatasetError(
            f"{path.name} does not satisfy the Week 4 worksheet schema."
        ) from error
    if (
        worksheet.purpose is GoldenDatasetPurpose.CONTRACT_TEST
        and not allow_contract_test
    ):
        raise GoldenDatasetError(
            "Contract-test fixtures cannot be accepted as golden data."
        )

    try:
        corpus = load_corpus(corpus_directory)
    except DocumentFormatError as error:
        raise GoldenDatasetError("The knowledge corpus is invalid.") from error

    completed_cases = tuple(
        slot.label for slot in worksheet.slots if slot.label is not None
    )
    _validate_document_references(completed_cases, corpus=corpus)

    blank_labels = len(worksheet.slots) - len(completed_cases)
    if require_complete and blank_labels:
        raise GoldenDatasetError(
            f"The worksheet still has {blank_labels} blank label slots."
        )

    dataset = None
    dataset_sha256 = None
    if not blank_labels:
        try:
            dataset = GoldenRetrievalDataset(
                schema_version=worksheet.schema_version,
                purpose=worksheet.purpose,
                dataset_name=worksheet.dataset_name,
                dataset_version=worksheet.dataset_version,
                cases=completed_cases,
            )
        except ValidationError as error:
            raise GoldenDatasetError(
                "Completed labels do not satisfy the Week 4 dataset schema."
            ) from error
        dataset_sha256 = canonical_sha256(dataset)

    return LoadedGoldenWorksheet(
        worksheet=worksheet,
        worksheet_sha256=canonical_sha256(worksheet),
        completed_labels=len(completed_cases),
        blank_labels=blank_labels,
        dataset=dataset,
        dataset_sha256=dataset_sha256,
    )


def corpus_reference_manifest(corpus_directory: Path) -> list[dict[str, object]]:
    try:
        corpus = load_corpus(corpus_directory)
    except DocumentFormatError as error:
        raise GoldenDatasetError("The knowledge corpus is invalid.") from error
    return [
        {
            "reference": {
                "tenant_id": document.metadata.tenant_id,
                "document_key": document.metadata.document_key,
                "document_version": document.metadata.version,
                "content_sha256": document.content_hash,
            },
            "visibility": document.metadata.visibility,
        }
        for document in sorted(
            corpus,
            key=lambda item: (
                item.metadata.tenant_id,
                item.metadata.document_key,
            ),
        )
    ]


def _validate_document_references(
    cases: Sequence[GoldenRetrievalCase],
    *,
    corpus: Sequence[SourceDocument],
) -> None:
    corpus_by_identity = {
        (document.metadata.tenant_id, document.metadata.document_key): document
        for document in corpus
    }
    corpus_keys = {document.metadata.document_key for document in corpus}

    for case in cases:
        allowed_visibilities = {
            visibility.value for visibility in case.context.allowed_visibilities
        }
        for reference in case.expected_relevant_documents:
            identity = (reference.tenant_id, reference.document_key)
            document = corpus_by_identity.get(identity)
            if document is None:
                if reference.document_key in corpus_keys:
                    raise GoldenDatasetError(
                        "A document reference crosses the case tenant boundary."
                    )
                raise GoldenDatasetError(
                    "A document reference is absent from the corpus."
                )
            if document.metadata.version != reference.document_version:
                raise GoldenDatasetError(
                    "A document reference is stale because its version changed."
                )
            if document.content_hash != reference.content_sha256:
                raise GoldenDatasetError(
                    "A document reference is stale because its content hash changed."
                )
            if document.metadata.visibility not in allowed_visibilities:
                raise GoldenDatasetError(
                    "A referenced document is outside the user's visibility scope."
                )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the provider-free Week 4 golden retrieval labeling worksheet."
        )
    )
    parser.add_argument("--worksheet", type=Path, default=DEFAULT_WORKSHEET)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument(
        "--require-complete",
        action="store_true",
        help=(
            "Reject blank slots and validate category coverage plus the canonical "
            "completed-dataset hash."
        ),
    )
    operation.add_argument(
        "--print-corpus-manifest",
        action="store_true",
        help=(
            "Print copyable version/hash document references and visibility "
            "without document content."
        ),
    )
    return parser


def run_cli(args: argparse.Namespace) -> int:
    if args.print_corpus_manifest:
        try:
            manifest = corpus_reference_manifest(args.corpus)
        except GoldenDatasetError as error:
            print(f"Golden dataset error: {error}", file=sys.stderr)
            return 2
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    try:
        loaded = load_worksheet(
            args.worksheet,
            corpus_directory=args.corpus,
            require_complete=args.require_complete,
        )
    except GoldenDatasetError as error:
        print(f"Golden dataset error: {error}", file=sys.stderr)
        return 2

    total_labels = len(loaded.worksheet.slots)
    if loaded.dataset is None:
        print(
            f"Validated Week 4 labeling worksheet: {loaded.completed_labels}/"
            f"{total_labels} labels completed; {loaded.blank_labels} blank. "
            f"Worksheet SHA-256: {loaded.worksheet_sha256}"
        )
        return 0

    print(
        f"Validated completed Week 4 dataset with {total_labels} labels. "
        f"Dataset SHA-256: {loaded.dataset_sha256}"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    exit_code = run_cli(build_parser().parse_args(argv))
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
