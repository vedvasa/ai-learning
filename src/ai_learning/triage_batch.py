from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError

from app.core.config import Settings
from app.providers.base import ProviderLookupError
from app.providers.registry import build_provider_registry
from app.schemas.evaluation import TriageEvaluationCase
from app.services.evaluation import EvaluationPricing, evaluate_triage_cases
from app.services.retry import RetryPolicy

DEFAULT_INPUT = Path("datasets/ticket-triage")
DEFAULT_OUTPUT = Path("artifacts/triage-evaluation.json")
MAX_DATASET_CASES = 100


class DatasetError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LoadedDataset:
    cases: list[TriageEvaluationCase]
    source_name: str
    sha256: str


def load_dataset(path: Path) -> LoadedDataset:
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(path.glob("*.json"))
    else:
        raise DatasetError(f"Input path does not exist: {path}")

    if not files:
        raise DatasetError(f"No JSON fixture files found in: {path}")

    cases: list[TriageEvaluationCase] = []
    ticket_ids: set[str] = set()
    for fixture_path in files:
        try:
            raw_cases = json.loads(fixture_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise DatasetError(
                f"Could not read valid JSON from {fixture_path.name}."
            ) from error

        if not isinstance(raw_cases, list):
            raise DatasetError(
                f"{fixture_path.name} must contain a JSON array of cases."
            )

        for case_number, raw_case in enumerate(raw_cases, start=1):
            try:
                case = TriageEvaluationCase.model_validate(raw_case)
            except ValidationError as error:
                raise DatasetError(
                    f"{fixture_path.name} case {case_number} is invalid."
                ) from error
            if case.ticket.ticket_id in ticket_ids:
                raise DatasetError(
                    f"Duplicate ticket ID: {case.ticket.ticket_id}"
                )
            ticket_ids.add(case.ticket.ticket_id)
            cases.append(case)
            if len(cases) > MAX_DATASET_CASES:
                raise DatasetError(
                    f"Dataset cannot contain more than {MAX_DATASET_CASES} cases."
                )

    if not cases:
        raise DatasetError("The fixture dataset contains no cases.")

    cases.sort(key=lambda case: case.ticket.ticket_id)
    canonical_json = json.dumps(
        [case.model_dump(mode="json") for case in cases],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return LoadedDataset(
        cases=cases,
        source_name=path.name,
        sha256=hashlib.sha256(canonical_json).hexdigest(),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate synthetic ticket fixtures through one configured provider."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--provider", choices=("openai", "anthropic"))
    parser.add_argument("--model")
    parser.add_argument("--max-cases", type=_positive_int, default=6)
    parser.add_argument("--concurrency", type=_bounded_concurrency, default=1)
    parser.add_argument(
        "--input-price-per-million-usd",
        type=_nonnegative_float,
    )
    parser.add_argument(
        "--output-price-per-million-usd",
        type=_nonnegative_float,
    )
    execution_mode = parser.add_mutually_exclusive_group()
    execution_mode.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate fixtures and exit without constructing a provider client.",
    )
    execution_mode.add_argument(
        "--allow-paid-calls",
        action="store_true",
        help="Acknowledge that this command can create billable provider calls.",
    )
    return parser


async def run_cli(args: argparse.Namespace) -> int:
    try:
        dataset = load_dataset(args.input)
    except DatasetError as error:
        print(f"Dataset error: {error}", file=sys.stderr)
        return 2

    if args.validate_only:
        print(
            f"Validated {len(dataset.cases)} synthetic cases. Dataset SHA-256: "
            f"{dataset.sha256}"
        )
        return 0

    if not args.allow_paid_calls:
        print(
            f"Validated {len(dataset.cases)} synthetic cases; no provider calls "
            "were made. Choose --validate-only or --allow-paid-calls.",
            file=sys.stderr,
        )
        return 2

    if (args.input_price_per_million_usd is None) != (
        args.output_price_per_million_usd is None
    ):
        print(
            "Provide both input and output prices, or neither.",
            file=sys.stderr,
        )
        return 2

    if _output_overlaps_input(args.input, args.output):
        print(
            "Output must be outside the input fixture path.",
            file=sys.stderr,
        )
        return 2

    settings = Settings()
    provider_name = args.provider or settings.llm_provider
    model = args.model or (
        settings.openai_model
        if provider_name == "openai"
        else settings.anthropic_model
    )
    try:
        provider = build_provider_registry(settings).get(provider_name, model)
    except ProviderLookupError as error:
        print(f"Provider configuration error: {error.message}", file=sys.stderr)
        return 2

    cases = dataset.cases[: args.max_cases]
    pricing = (
        EvaluationPricing(
            input_per_million_usd=args.input_price_per_million_usd,
            output_per_million_usd=args.output_price_per_million_usd,
        )
        if args.input_price_per_million_usd is not None
        else None
    )
    logging.getLogger("app").setLevel(settings.log_level)
    report = await evaluate_triage_cases(
        cases,
        provider=provider,
        retry_policy=RetryPolicy.from_settings(settings),
        timeout_seconds=settings.llm_timeout_seconds,
        concurrency=args.concurrency,
        source_name=dataset.source_name,
        dataset_sha256=dataset.sha256,
        available_cases=len(dataset.cases),
        max_cases=args.max_cases,
        pricing=pricing,
    )

    _write_report(args.output, report.model_dump_json(indent=2) + "\n")
    metrics = report.metrics
    print(
        f"Evaluated {metrics.total_cases} cases with {provider.name}/"
        f"{provider.model}: {metrics.successful_cases} schema-valid, "
        f"{metrics.failed_cases} failed."
    )
    print(f"Aggregate report: {args.output}")
    return 1 if metrics.failed_cases else 0


def _write_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(path)


def _output_overlaps_input(input_path: Path, output_path: Path) -> bool:
    resolved_input = input_path.resolve()
    resolved_output = output_path.resolve()
    if resolved_input.is_file():
        return resolved_input == resolved_output
    return (
        resolved_input == resolved_output
        or resolved_input in resolved_output.parents
    )


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1 or parsed > 100:
        raise argparse.ArgumentTypeError("must be between 1 and 100")
    return parsed


def _bounded_concurrency(value: str) -> int:
    parsed = int(value)
    if parsed < 1 or parsed > 10:
        raise argparse.ArgumentTypeError("must be between 1 and 10")
    return parsed


def _nonnegative_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("must be finite and zero or greater")
    return parsed


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    exit_code = asyncio.run(run_cli(args))
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
