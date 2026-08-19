from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import pytest

from ai_learning import triage_batch
from ai_learning.triage_batch import DatasetError, load_dataset
from app.core.config import Settings
from app.providers.base import TriageResult
from app.schemas.triage import TicketTriage

FIXTURE_DIRECTORY = (
    Path(__file__).parents[1] / "datasets" / "ticket-triage"
)


class FakeCliProvider:
    name = "openai"
    model = "gpt-test"

    async def triage(self, ticket) -> TriageResult:
        return TriageResult(
            triage=TicketTriage(
                category="billing",
                priority="medium",
                summary="Aggregate reports must omit this generated summary.",
                sentiment="neutral",
                requested_action="Use a fictional workflow.",
                requires_human_review=True,
                confidence=0.9,
                rationale="Synthetic fixture evidence supports this label.",
            ),
            provider="openai",
            model=self.model,
            latency_ms=10,
            input_tokens=10,
            output_tokens=5,
            finish_reason="completed",
            provider_request_id=None,
        )


class FakeRegistry:
    def __init__(self, provider: FakeCliProvider) -> None:
        self.provider = provider

    def get(self, provider_name: str, model: str) -> FakeCliProvider:
        assert provider_name == self.provider.name
        assert model == self.provider.model
        return self.provider


def test_committed_dataset_has_30_unique_synthetic_cases() -> None:
    first = load_dataset(FIXTURE_DIRECTORY)
    second = load_dataset(FIXTURE_DIRECTORY)

    assert len(first.cases) == 30
    assert len({case.ticket.ticket_id for case in first.cases}) == 30
    assert first.cases[0].ticket.ticket_id == "TKT-001"
    assert first.cases[-1].ticket.ticket_id == "TKT-030"
    assert first.sha256 == second.sha256
    assert {case.expected.category.value for case in first.cases} == {
        "account_access",
        "billing",
        "cancellation",
        "feature_request",
        "other",
        "security",
        "technical_issue",
    }
    assert sum(
        case.expected.requires_human_review for case in first.cases
    ) == 11


def test_dataset_error_does_not_echo_invalid_ticket_text(tmp_path: Path) -> None:
    secret_text = "private ticket text must not be printed"
    fixture_path = tmp_path / "invalid.json"
    fixture_path.write_text(
        json.dumps(
            [
                {
                    "ticket": {
                        "ticket_id": "BAD-1",
                        "subject": secret_text,
                        "body": " ",
                        "channel": "email",
                    },
                    "expected": {
                        "category": "billing",
                        "priority": "medium",
                        "requires_human_review": True,
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DatasetError) as caught:
        load_dataset(fixture_path)

    assert "invalid.json case 1 is invalid" in str(caught.value)
    assert secret_text not in str(caught.value)


def test_dataset_rejects_duplicate_ticket_ids_across_files(
    tmp_path: Path,
) -> None:
    case = load_dataset(
        FIXTURE_DIRECTORY / "starter_tickets.json"
    ).cases[0].model_dump(mode="json")
    (tmp_path / "one.json").write_text(json.dumps([case]), encoding="utf-8")
    (tmp_path / "two.json").write_text(json.dumps([case]), encoding="utf-8")

    with pytest.raises(DatasetError, match="Duplicate ticket ID: TKT-001"):
        load_dataset(tmp_path)


def test_dataset_rejects_more_than_100_cases(tmp_path: Path) -> None:
    template = load_dataset(
        FIXTURE_DIRECTORY / "starter_tickets.json"
    ).cases[0].model_dump(mode="json")
    cases = []
    for index in range(101):
        case = json.loads(json.dumps(template))
        case["ticket"]["ticket_id"] = f"LIMIT-{index:03d}"
        cases.append(case)
    fixture_path = tmp_path / "too-many.json"
    fixture_path.write_text(json.dumps(cases), encoding="utf-8")

    with pytest.raises(
        DatasetError,
        match="Dataset cannot contain more than 100 cases",
    ):
        load_dataset(fixture_path)


def test_cli_refuses_provider_calls_without_explicit_acknowledgement(
    capsys,
) -> None:
    args = triage_batch.build_parser().parse_args(
        ["--input", str(FIXTURE_DIRECTORY)]
    )

    exit_code = asyncio.run(triage_batch.run_cli(args))

    assert exit_code == 2
    assert "Validated 30 synthetic cases" in capsys.readouterr().err


def test_cli_validate_only_succeeds_without_constructing_provider(capsys) -> None:
    args = triage_batch.build_parser().parse_args(
        [
            "--input",
            str(FIXTURE_DIRECTORY),
            "--validate-only",
        ]
    )

    exit_code = asyncio.run(triage_batch.run_cli(args))

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Validated 30 synthetic cases" in output
    assert "Dataset SHA-256" in output


def test_cli_requires_both_pricing_inputs(capsys) -> None:
    args = triage_batch.build_parser().parse_args(
        [
            "--input",
            str(FIXTURE_DIRECTORY),
            "--allow-paid-calls",
            "--input-price-per-million-usd",
            "1",
        ]
    )

    exit_code = asyncio.run(triage_batch.run_cli(args))

    assert exit_code == 2
    assert "Provide both input and output prices" in capsys.readouterr().err


def test_cli_writes_aggregate_only_report_with_injected_provider(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    output_path = tmp_path / "reports" / "evaluation.json"
    settings = Settings(
        _env_file=None,
        app_env="test",
        llm_provider="openai",
        openai_api_key="test-key",
        openai_model="gpt-test",
        llm_retry_base_delay_seconds=0,
    )
    provider = FakeCliProvider()
    monkeypatch.setattr(triage_batch, "Settings", lambda: settings)
    monkeypatch.setattr(
        triage_batch,
        "build_provider_registry",
        lambda _settings: FakeRegistry(provider),
    )
    args = triage_batch.build_parser().parse_args(
        [
            "--input",
            str(FIXTURE_DIRECTORY / "starter_tickets.json"),
            "--output",
            str(output_path),
            "--provider",
            "openai",
            "--model",
            "gpt-test",
            "--max-cases",
            "1",
            "--allow-paid-calls",
        ]
    )

    exit_code = asyncio.run(triage_batch.run_cli(args))

    assert exit_code == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["available_cases"] == 6
    assert report["metrics"]["total_cases"] == 1
    assert report["metrics"]["schema_valid_response_rate"] == 1
    serialized = output_path.read_text(encoding="utf-8")
    assert "ticket_id" not in serialized
    assert "Charged twice" not in serialized
    assert "Aggregate reports must omit" not in serialized
    assert "Evaluated 1 cases" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("--max-cases", "0"),
        ("--max-cases", "101"),
        ("--concurrency", "0"),
        ("--concurrency", "11"),
        ("--input-price-per-million-usd", "-1"),
        ("--input-price-per-million-usd", "nan"),
    ],
)
def test_cli_rejects_unsafe_numeric_bounds(
    argument: str,
    value: str,
) -> None:
    parser = triage_batch.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([argument, value])
