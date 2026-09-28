from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys
from typing import Sequence

from pydantic import ValidationError

from ai_learning.golden_retrieval import (
    DEFAULT_CORPUS,
    DEFAULT_WORKSHEET,
    HUMAN_CHECKPOINT_SHA256,
    GoldenDatasetError,
    canonical_sha256,
    load_worksheet,
    validate_document_references,
)
from app.rag.documents import DocumentFormatError, load_corpus
from app.schemas.retrieval_drafts import RetrievalDraftBatch

DEFAULT_DRAFT_DIRECTORY = Path("datasets/rag-evaluation/week4_drafts")
TARGET_CATEGORY_COUNTS = {
    "direct_fact": 12,
    "multi_document": 8,
    "ambiguous": 5,
    "unanswerable": 5,
    "adversarial": 5,
    "privacy_boundary": 5,
}


def load_draft_batches(
    directory: Path = DEFAULT_DRAFT_DIRECTORY,
    *,
    corpus_directory: Path = DEFAULT_CORPUS,
) -> tuple[RetrievalDraftBatch, ...]:
    checkpoint = load_worksheet(
        DEFAULT_WORKSHEET, corpus_directory=corpus_directory, require_complete=True,
    )
    if checkpoint.dataset_sha256 != HUMAN_CHECKPOINT_SHA256:
        raise GoldenDatasetError("The preserved human checkpoint has changed.")
    assert checkpoint.dataset is not None
    try:
        batches = tuple(
            RetrievalDraftBatch.model_validate_json(
                (directory / f"batch-{number}.json").read_text(encoding="utf-8")
            )
            for number in range(1, 4)
        )
        corpus = load_corpus(corpus_directory)
    except (OSError, UnicodeError, ValidationError, DocumentFormatError) as error:
        raise GoldenDatasetError("Could not load valid draft batches and corpus.") from error
    if [batch.batch_number for batch in batches] != [1, 2, 3]:
        raise GoldenDatasetError("Draft files must contain batches one through three in order.")
    if any(batch.human_checkpoint_sha256 != HUMAN_CHECKPOINT_SHA256 for batch in batches):
        raise GoldenDatasetError("Draft batches do not match the preserved checkpoint.")
    slots = [slot for batch in batches for slot in batch.slots]
    drafts = [slot.label for slot in slots]
    combined = [*checkpoint.dataset.cases, *drafts]
    ids = [case.case_id for case in combined]
    questions = [case.question.casefold() for case in combined]
    if len(ids) != len(set(ids)) or len(questions) != len(set(questions)):
        raise GoldenDatasetError("Drafts duplicate another case ID or question.")
    if Counter(case.category.value for case in combined) != TARGET_CATEGORY_COUNTS:
        raise GoldenDatasetError("Draft categories do not match the agreed 40-case mix.")
    validate_document_references(drafts, corpus=corpus)
    documents = {
        (document.metadata.tenant_id, document.metadata.document_key): document
        for document in corpus
    }
    for slot in slots:
        identities = [
            (ref.tenant_id, ref.document_key) for ref in slot.review_references
        ]
        if len(identities) != len(set(identities)):
            raise GoldenDatasetError("Review references must be unique.")
        for reference in slot.review_references:
            document = documents.get((reference.tenant_id, reference.document_key))
            if document is None or (
                document.metadata.version != reference.document_version
                or document.content_hash != reference.content_sha256
            ):
                raise GoldenDatasetError("A review reference is missing or stale.")
        if not set(identities).issuperset({
            (ref.tenant_id, ref.document_key)
            for ref in slot.label.expected_relevant_documents
        }):
            raise GoldenDatasetError("Review references must include all expected documents.")
    return batches


def render_review_sheet(batch: RetrievalDraftBatch) -> str:
    rows = [
        f"# Week 4 draft review — batch {batch.batch_number}",
        "",
        "**Status: awaiting your review. These are model-assisted drafts, not golden labels.**",
        "",
        f"Draft batch SHA-256: `{canonical_sha256(batch)}`",
        "",
        "Review the question, source documents, required facts, access scope, and whether "
        "the answer should be withheld or clarified. Reply with corrections by slot number, "
        "or approve this batch after checking all ten cases. Approval must refer to this version.",
        "",
        "The linked documents are reviewer evidence. For abstention cases they are not "
        "retrieval targets; an empty expected-document list does not require search to return "
        "nothing. Instruction-following and answer abstention need later answer evaluation.",
    ]
    for slot in batch.slots:
        case = slot.label
        rows.extend([
            "",
            f"## {slot.slot_number}. {case.case_id}",
            "",
            f"**Question:** {case.question}",
            "",
            f"**Category:** {case.category.value} · **Difficulty:** {case.difficulty.value}",
            f"**Context:** `{case.context.tenant_id}` / `{case.context.principal_id}` / "
            f"{case.context.principal_type.value}; allowed visibility: "
            + ", ".join(value.value for value in case.context.allowed_visibilities) + ".",
            f"**Should abstain or clarify:** {'Yes' if case.should_abstain else 'No'}.",
            "",
            "**Expected relevant documents:** " + (
                ", ".join(f"`{ref.document_key}`" for ref in case.expected_relevant_documents)
                or "None."
            ),
            "",
            "**Required answer facts:**",
            "",
        ])
        rows.extend(
            [f"- {fact}" for fact in case.key_answer_facts]
            or ["- None; the accepted schema leaves facts empty for abstention cases."]
        )
        rows.extend([
            "",
            f"**Review rationale:** {slot.review_notes}",
            "",
            "**Documents to check:** " + (
                ", ".join(
                    f"[{ref.document_key}](../../knowledge-base/{ref.document_key}.md)"
                    for ref in slot.review_references
                ) or "Check the corpus for unsupported claims."
            ),
        ])
        if case.adversarial_notes:
            rows.extend(["", f"**Boundary/adversarial notes:** {case.adversarial_notes}"])
        rows.extend(["", "**Human review:** pending."])
    return "\n".join(rows) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the 30 unreviewed Week 4 draft labels offline.")
    parser.add_argument("--draft-directory", type=Path, default=DEFAULT_DRAFT_DIRECTORY)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write-review-sheets", action="store_true")
    mode.add_argument("--check-review-sheets", action="store_true")
    return parser


def run_cli(args: argparse.Namespace) -> int:
    try:
        batches = load_draft_batches(args.draft_directory, corpus_directory=args.corpus)
        for batch in batches:
            sheet = args.draft_directory / f"batch-{batch.batch_number}.md"
            rendered = render_review_sheet(batch)
            if args.write_review_sheets:
                sheet.write_text(rendered, encoding="utf-8")
            elif args.check_review_sheets and sheet.read_text(encoding="utf-8") != rendered:
                raise GoldenDatasetError("A review sheet is out of date; regenerate it from the drafts.")
    except GoldenDatasetError as error:
        print(f"Draft validation error: {error}", file=sys.stderr)
        return 2
    except (OSError, UnicodeError):
        print("Draft validation error: could not read or write review sheets.", file=sys.stderr)
        return 2
    print("Validated 30 unreviewed drafts in 3 batches; 10 accepted human labels unchanged. "
          "No drafts were approved or added to golden data.")
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    exit_code = run_cli(build_parser().parse_args(argv))
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
