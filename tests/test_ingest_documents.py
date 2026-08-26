import json
from pathlib import Path

from ai_learning.ingest_documents import _is_local_database, run


def test_committed_corpus_dry_run_has_expected_size(capsys) -> None:
    exit_code = run(["--dry-run"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "dry_run"
    assert output["documents"] == 21
    assert output["chunks"] >= 42
    assert all(len(item["content_hash"]) == 64 for item in output["results"])


def test_live_ingestion_requires_explicit_spend_confirmation(capsys) -> None:
    exit_code = run(["--max-documents", "1"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert output == {
        "status": "blocked",
        "error": "--confirm-spend is required for live ingestion",
    }


def test_missing_corpus_returns_safe_error(tmp_path: Path, capsys) -> None:
    exit_code = run(["--dry-run", "--directory", str(tmp_path / "missing")])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert output["status"] == "failed"
    assert "does not exist" in output["error"]


def test_local_database_detection_does_not_expose_or_accept_remote_hosts() -> None:
    assert _is_local_database(
        "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    )
    assert not _is_local_database("host=db.example.com dbname=postgres")
    assert not _is_local_database("not a connection string")
