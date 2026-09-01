from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from ai_learning import golden_retrieval
from ai_learning.golden_retrieval import GoldenDatasetError, load_worksheet
from app.schemas.golden_retrieval import (
    GoldenDatasetPurpose,
    LabelOrigin,
    RetrievalCategory,
)

REPOSITORY_ROOT = Path(__file__).parents[1]
WORKSHEET_PATH = (
    REPOSITORY_ROOT
    / "datasets"
    / "rag-evaluation"
    / "week4_human_labels.json"
)
CORPUS_PATH = REPOSITORY_ROOT / "datasets" / "knowledge-base"
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "golden_retrieval"
SYNTHETIC_WORKSHEET_PATH = FIXTURE_ROOT / "synthetic_completed_worksheet.json"
SYNTHETIC_CORPUS_PATH = FIXTURE_ROOT / "corpus"
PRIVATE_CONTENT_HASH = (
    "5791eddc415c98a41db1cccf4ea3f70ade5a4ac250c34ee83a979dfb072912cb"
)


def _synthetic_worksheet() -> dict:
    return json.loads(SYNTHETIC_WORKSHEET_PATH.read_text(encoding="utf-8"))


def _write_worksheet(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "worksheet.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _load_synthetic(path: Path, *, require_complete: bool = False):
    return load_worksheet(
        path,
        corpus_directory=SYNTHETIC_CORPUS_PATH,
        require_complete=require_complete,
        allow_contract_test=True,
    )


def _golden_worksheet_from_synthetic() -> dict:
    payload = _synthetic_worksheet()
    payload["purpose"] = "golden"
    payload["dataset_name"] = "Golden schema-only test payload"
    for slot in payload["slots"]:
        provenance = slot["label"]["label_provenance"]
        provenance.update(
            {
                "origin": "human",
                "annotator_role": "project_owner",
                "human_reviewed": True,
            }
        )
    return payload


def test_committed_week4_worksheet_has_ten_blank_human_slots() -> None:
    first = load_worksheet(WORKSHEET_PATH, corpus_directory=CORPUS_PATH)
    second = load_worksheet(WORKSHEET_PATH, corpus_directory=CORPUS_PATH)

    assert first.worksheet.purpose is GoldenDatasetPurpose.GOLDEN
    assert len(first.worksheet.slots) == 10
    assert first.completed_labels == 0
    assert first.blank_labels == 10
    assert first.dataset is None
    assert first.dataset_sha256 is None
    assert first.worksheet_sha256 == second.worksheet_sha256
    assert all(slot.label is None for slot in first.worksheet.slots)


def test_blank_worksheet_fails_completed_dataset_gate() -> None:
    with pytest.raises(GoldenDatasetError, match="10 blank label slots"):
        load_worksheet(
            WORKSHEET_PATH,
            corpus_directory=CORPUS_PATH,
            require_complete=True,
        )


def test_explicit_synthetic_fixture_validates_completed_contract() -> None:
    loaded = _load_synthetic(
        SYNTHETIC_WORKSHEET_PATH,
        require_complete=True,
    )

    assert loaded.dataset is not None
    assert loaded.dataset.purpose is GoldenDatasetPurpose.CONTRACT_TEST
    assert loaded.completed_labels == 10
    assert loaded.blank_labels == 0
    assert loaded.dataset_sha256 is not None
    assert len(loaded.dataset_sha256) == 64
    assert {case.category for case in loaded.dataset.cases} == set(
        RetrievalCategory
    )
    assert all(
        case.label_provenance.origin is LabelOrigin.SYNTHETIC_TEST
        for case in loaded.dataset.cases
    )


def test_synthetic_fixture_cannot_be_loaded_as_golden_data() -> None:
    with pytest.raises(GoldenDatasetError, match="cannot be accepted"):
        load_worksheet(
            SYNTHETIC_WORKSHEET_PATH,
            corpus_directory=SYNTHETIC_CORPUS_PATH,
        )


def test_canonical_hash_ignores_json_formatting_and_field_order(
    tmp_path: Path,
) -> None:
    payload = _synthetic_worksheet()
    reordered = dict(reversed(tuple(payload.items())))
    path = tmp_path / "reordered.json"
    path.write_text(json.dumps(reordered, separators=(",", ":")), encoding="utf-8")

    original = _load_synthetic(
        SYNTHETIC_WORKSHEET_PATH,
        require_complete=True,
    )
    rewritten = _load_synthetic(
        path,
        require_complete=True,
    )

    assert rewritten.worksheet_sha256 == original.worksheet_sha256
    assert rewritten.dataset_sha256 == original.dataset_sha256


def test_missing_corpus_document_is_rejected(tmp_path: Path) -> None:
    payload = _synthetic_worksheet()
    payload["slots"][0]["label"]["expected_relevant_documents"][0][
        "document_key"
    ] = "synthetic-missing"

    with pytest.raises(GoldenDatasetError, match="absent from the corpus"):
        _load_synthetic(
            _write_worksheet(tmp_path, payload),
        )


def test_cross_tenant_document_reference_is_rejected(tmp_path: Path) -> None:
    payload = _synthetic_worksheet()
    first_label = payload["slots"][0]["label"]
    first_label["context"]["tenant_id"] = "other-tenant"
    first_label["expected_relevant_documents"][0]["tenant_id"] = "other-tenant"

    with pytest.raises(GoldenDatasetError, match="crosses the case tenant"):
        _load_synthetic(
            _write_worksheet(tmp_path, payload),
        )


def test_document_outside_user_visibility_is_rejected(tmp_path: Path) -> None:
    payload = _synthetic_worksheet()
    reference = payload["slots"][0]["label"]["expected_relevant_documents"][0]
    reference.update(
        {
            "document_key": "synthetic-private",
            "document_version": 1,
            "content_sha256": PRIVATE_CONTENT_HASH,
        }
    )

    with pytest.raises(GoldenDatasetError, match="outside the user's visibility"):
        _load_synthetic(
            _write_worksheet(tmp_path, payload),
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("document_version", 99, "version changed"),
        ("content_sha256", "0" * 64, "content hash changed"),
    ],
)
def test_stale_document_reference_is_rejected(
    tmp_path: Path,
    field: str,
    value: int | str,
    message: str,
) -> None:
    payload = _synthetic_worksheet()
    payload["slots"][0]["label"]["expected_relevant_documents"][0][field] = value

    with pytest.raises(GoldenDatasetError, match=message):
        _load_synthetic(
            _write_worksheet(tmp_path, payload),
        )


def test_completed_dataset_requires_every_category(tmp_path: Path) -> None:
    payload = _synthetic_worksheet()
    ambiguous_label = payload["slots"][2]["label"]
    ambiguous_label["category"] = "unanswerable"

    with pytest.raises(
        GoldenDatasetError,
        match="Completed labels do not satisfy",
    ):
        _load_synthetic(
            _write_worksheet(tmp_path, payload),
            require_complete=True,
        )


def test_first_ten_golden_labels_cannot_be_model_assisted(tmp_path: Path) -> None:
    payload = _golden_worksheet_from_synthetic()
    payload["slots"][0]["label"]["label_provenance"]["origin"] = (
        "model_assisted"
    )

    with pytest.raises(GoldenDatasetError, match="worksheet schema"):
        load_worksheet(
            _write_worksheet(tmp_path, payload),
            corpus_directory=SYNTHETIC_CORPUS_PATH,
        )


def test_personal_provenance_field_is_rejected(tmp_path: Path) -> None:
    payload = _golden_worksheet_from_synthetic()
    provenance = payload["slots"][0]["label"]["label_provenance"]
    provenance["annotator_name"] = "A Person"

    with pytest.raises(GoldenDatasetError, match="worksheet schema"):
        load_worksheet(
            _write_worksheet(tmp_path, payload),
            corpus_directory=SYNTHETIC_CORPUS_PATH,
        )


def test_duplicate_questions_are_rejected(tmp_path: Path) -> None:
    payload = deepcopy(_golden_worksheet_from_synthetic())
    payload["slots"][1]["label"]["question"] = payload["slots"][0]["label"][
        "question"
    ].upper()

    with pytest.raises(GoldenDatasetError, match="worksheet schema"):
        load_worksheet(
            _write_worksheet(tmp_path, payload),
            corpus_directory=SYNTHETIC_CORPUS_PATH,
        )


def test_cli_validates_blank_template_without_external_clients(capsys) -> None:
    args = golden_retrieval.build_parser().parse_args(
        [
            "--worksheet",
            str(WORKSHEET_PATH),
            "--corpus",
            str(CORPUS_PATH),
        ]
    )

    assert golden_retrieval.run_cli(args) == 0
    output = capsys.readouterr().out
    assert "0/10 labels completed; 10 blank" in output
    assert "Worksheet SHA-256" in output


def test_cli_prints_reference_manifest_without_document_content(capsys) -> None:
    args = golden_retrieval.build_parser().parse_args(
        [
            "--corpus",
            str(SYNTHETIC_CORPUS_PATH),
            "--print-corpus-manifest",
        ]
    )

    assert golden_retrieval.run_cli(args) == 0
    manifest = json.loads(capsys.readouterr().out)
    assert len(manifest) == 3
    assert manifest[0]["reference"] == {
        "tenant_id": "synthetic-tenant",
        "document_key": "synthetic-alpha",
        "document_version": 1,
        "content_sha256": (
            "59f3e61e7daa41b72ae12bb44e42ce9502dbd6aba42305bf05ca4be0f03c194d"
        ),
    }
    assert manifest[0]["visibility"] == "public"
    assert "content" not in manifest[0]


def test_cli_requires_all_human_labels_when_requested(capsys) -> None:
    args = golden_retrieval.build_parser().parse_args(
        [
            "--worksheet",
            str(WORKSHEET_PATH),
            "--corpus",
            str(CORPUS_PATH),
            "--require-complete",
        ]
    )

    assert golden_retrieval.run_cli(args) == 2
    assert "10 blank label slots" in capsys.readouterr().err
