from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError

from ai_learning.golden_retrieval import (
    DEFAULT_CORPUS,
    DEFAULT_WORKSHEET,
    GoldenDatasetError,
    load_worksheet,
)
from app.rag.documents import DocumentFormatError, load_corpus
from app.schemas.golden_retrieval import GoldenRetrievalDataset
from app.schemas.retrieval_evaluation import RecordedRetrievalRun
from app.services.retrieval_evaluation import (
    RetrievalEvaluationError,
    compare_retrieval_reports,
    corpus_sha256,
    evaluate_retrieval,
    render_retrieval_markdown,
)

HUMAN_CHECKPOINT_SHA256 = (
    "092042662d3d2b5e641d70a26f8f241a02344471dd05b60df14462a22b7b3418"
)


def validate_checkpoint(dataset: GoldenRetrievalDataset, *, corpus_directory: Path) -> None:
    checkpoint = load_worksheet(
        DEFAULT_WORKSHEET, corpus_directory=corpus_directory, require_complete=True,
    )
    if checkpoint.dataset_sha256 != HUMAN_CHECKPOINT_SHA256:
        raise RetrievalEvaluationError("The preserved human checkpoint has changed.")
    assert checkpoint.dataset is not None
    if dataset.cases[:10] != checkpoint.dataset.cases:
        raise RetrievalEvaluationError("The first ten labels must match the human checkpoint.")


def _read_results(path: Path) -> RecordedRetrievalRun:
    try:
        return RecordedRetrievalRun.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValidationError) as error:
        raise RetrievalEvaluationError("Could not load a valid retrieval results file.") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Week 4 labels or score saved rankings without providers or database access.",
    )
    parser.add_argument("--worksheet", type=Path, default=DEFAULT_WORKSHEET)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--minimum-cases", type=int, choices=range(10, 201), default=10, metavar="10..200")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--results", type=Path, help="Saved rankings; synthetic or recorded evidence is labeled explicitly.")
    parser.add_argument("--baseline-results", type=Path)
    parser.add_argument("--maximum-metric-drop", type=float, default=0)
    parser.add_argument("--output-directory", type=Path, default=Path("artifacts/retrieval-evaluation"))
    return parser


def run_cli(args: argparse.Namespace) -> int:
    try:
        loaded = load_worksheet(
            args.worksheet, corpus_directory=args.corpus, require_complete=True,
        )
        assert loaded.dataset is not None
        validate_checkpoint(loaded.dataset, corpus_directory=args.corpus)
        if loaded.completed_labels < args.minimum_cases:
            raise RetrievalEvaluationError("The dataset does not meet the requested minimum case count.")
        corpus = load_corpus(args.corpus)
        if args.validate_only:
            if args.baseline_results is not None or args.maximum_metric_drop != 0:
                raise RetrievalEvaluationError("Baseline options require --results.")
            print(
                f"Validated {loaded.completed_labels} Week 4 labels; human checkpoint preserved. "
                f"Dataset SHA-256: {loaded.dataset_sha256}; corpus SHA-256: {corpus_sha256(corpus)}"
            )
            return 0
        if args.baseline_results is None and args.maximum_metric_drop != 0:
            raise RetrievalEvaluationError("A metric-drop allowance requires --baseline-results.")
        report = evaluate_retrieval(loaded.dataset, corpus, _read_results(args.results))
        if args.baseline_results is not None:
            baseline = evaluate_retrieval(
                loaded.dataset, corpus, _read_results(args.baseline_results),
            )
            report = compare_retrieval_reports(
                report, baseline, maximum_metric_drop=args.maximum_metric_drop,
            )
        outputs = (
            args.output_directory / "report.json",
            args.output_directory / "report.md",
        )
        inputs = [args.worksheet, DEFAULT_WORKSHEET, args.results]
        if args.baseline_results is not None:
            inputs.append(args.baseline_results)
        if any(
            output.resolve() in {path.resolve() for path in inputs}
            or output.resolve().is_relative_to(args.corpus.resolve())
            for output in outputs
        ):
            raise RetrievalEvaluationError("Reports must not overwrite evaluation inputs.")
        _atomic_write(outputs[0], report.model_dump_json(indent=2) + "\n")
        _atomic_write(outputs[1], render_retrieval_markdown(report))
    except (GoldenDatasetError, DocumentFormatError, RetrievalEvaluationError) as error:
        # Corpus loader errors can include paths; keep all command failures content-free.
        message = "The corpus is invalid." if isinstance(error, DocumentFormatError) else str(error)
        print(f"Retrieval evaluation error: {message}", file=sys.stderr)
        return 2
    except OSError:
        print("Retrieval evaluation error: could not write reports.", file=sys.stderr)
        return 2
    print(
        f"Scored {report.metrics.total_cases} cases ({report.evidence_kind}; ranked-result replay). "
        f"Gate: {'PASS' if report.gate_passed else 'FAIL'}. No provider calls or database writes."
    )
    print(f"Reports: {args.output_directory / 'report.json'} and {args.output_directory / 'report.md'}")
    return 0 if report.gate_passed else 1


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> None:
    exit_code = run_cli(build_parser().parse_args(argv))
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
