from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import shutil

import pytest
from pydantic import ValidationError

from ai_learning import retrieval_drafts
from ai_learning.golden_retrieval import (
    DEFAULT_CORPUS,
    DEFAULT_WORKSHEET,
    HUMAN_CHECKPOINT_SHA256,
    GoldenDatasetError,
    load_worksheet,
)
from app.schemas.golden_retrieval import GoldenRetrievalCase
from app.schemas.retrieval_drafts import RetrievalDraftBatch

DRAFT_DIRECTORY = Path("datasets/rag-evaluation/week4_drafts")


@pytest.fixture
def draft_directory(tmp_path):
    directory = tmp_path / "drafts"
    shutil.copytree(DRAFT_DIRECTORY, directory)
    return directory


def _mutate(directory, batch, operation):
    path = directory / f"batch-{batch}.json"
    payload = json.loads(path.read_text())
    operation(payload)
    path.write_text(json.dumps(payload))


def test_committed_drafts_preserve_checkpoint_and_match_approved_mix():
    batches = retrieval_drafts.load_draft_batches()
    checkpoint = load_worksheet(
        DEFAULT_WORKSHEET, corpus_directory=DEFAULT_CORPUS, require_complete=True,
    )
    assert checkpoint.dataset_sha256 == HUMAN_CHECKPOINT_SHA256
    assert checkpoint.completed_labels == 10
    assert [slot.slot_number for batch in batches for slot in batch.slots] == list(range(11, 41))
    labels = [slot.label for batch in batches for slot in batch.slots]
    assert all(label.label_provenance.origin == "model_assisted" for label in labels)
    assert not any(label.label_provenance.human_reviewed for label in labels)
    combined = [*checkpoint.dataset.cases, *labels]
    assert Counter(case.category.value for case in combined) == {
        "direct_fact": 12, "multi_document": 8, "ambiguous": 5,
        "unanswerable": 5, "adversarial": 5, "privacy_boundary": 5,
    }
    assert sum(not case.should_abstain for case in combined) == 24
    assert len({
        ref.document_key for case in combined
        for ref in case.expected_relevant_documents
    }) == 21


def test_draft_files_and_labels_are_rejected_as_golden_data():
    for batch in retrieval_drafts.load_draft_batches():
        with pytest.raises(GoldenDatasetError):
            load_worksheet(
                DRAFT_DIRECTORY / f"batch-{batch.batch_number}.json",
                corpus_directory=DEFAULT_CORPUS, require_complete=True,
            )
        for slot in batch.slots:
            with pytest.raises(ValidationError):
                GoldenRetrievalCase.model_validate(slot.label.model_dump(mode="json"))


def test_reviewed_reference_set_preserves_checkpoint_and_only_approved_six():
    checkpoint = load_worksheet(
        DEFAULT_WORKSHEET, corpus_directory=DEFAULT_CORPUS, require_complete=True,
    )
    reviewed = load_worksheet(
        Path("datasets/rag-evaluation/week4_reviewed_labels.json"),
        corpus_directory=DEFAULT_CORPUS, require_complete=True,
    )
    assert checkpoint.dataset_sha256 == HUMAN_CHECKPOINT_SHA256
    assert reviewed.dataset.cases[:10] == checkpoint.dataset.cases
    selected = [
        slot.label for batch in retrieval_drafts.load_draft_batches()
        for slot in batch.slots if slot.slot_number in {15, 19, 26, 27, 30, 40}
    ]
    accepted = reviewed.dataset.cases[10:]
    assert len(accepted) == len(selected) == 6
    for label, original in zip(accepted, selected, strict=True):
        assert label.model_dump(exclude={"label_provenance"}) == original.model_dump(
            exclude={"label_provenance"},
        )
        assert label.label_provenance.origin == "model_assisted"
        assert label.label_provenance.annotator_role == "project_owner"
        assert label.label_provenance.human_reviewed is True
        assert str(label.label_provenance.labeled_on) == "2026-09-29"
    assert sum(not case.should_abstain for case in reviewed.dataset.cases) == 7


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(purpose="golden"),
    lambda p: p.update(status="approved"),
    lambda p: p["slots"][0]["label"]["label_provenance"].update(human_reviewed=True),
    lambda p: p["slots"][0]["label"]["label_provenance"].update(human_reviewed="false"),
    lambda p: p["slots"][0]["label"]["label_provenance"].update(origin="human"),
    lambda p: p["slots"][0]["label"]["label_provenance"].update(annotator_name="A person"),
    lambda p: p["slots"][0].update(slot_number=1),
    lambda p: p["slots"].pop(),
    lambda p: p["slots"][0]["label"].update(should_abstain=True),
])
def test_draft_schema_rejects_review_claims_and_malformed_content(mutation):
    payload = json.loads((DRAFT_DIRECTORY / "batch-1.json").read_text())
    mutation(payload)
    with pytest.raises(ValidationError):
        RetrievalDraftBatch.model_validate(payload)


@pytest.mark.parametrize("field", ["case_id", "question"])
def test_drafts_cannot_duplicate_the_human_checkpoint(draft_directory, field):
    original = json.loads(DEFAULT_WORKSHEET.read_text())["slots"][0]["label"][field]
    _mutate(draft_directory, 1, lambda p: p["slots"][0]["label"].update({field: original}))
    with pytest.raises(GoldenDatasetError, match="duplicate"):
        retrieval_drafts.load_draft_batches(draft_directory)


def test_duplicate_across_batches_is_rejected(draft_directory):
    case_id = json.loads((draft_directory / "batch-1.json").read_text())["slots"][0]["label"]["case_id"]
    _mutate(draft_directory, 2, lambda p: p["slots"][0]["label"].update(case_id=case_id))
    with pytest.raises(GoldenDatasetError, match="duplicate"):
        retrieval_drafts.load_draft_batches(draft_directory)


def test_checkpoint_pin_and_category_mix_are_enforced(draft_directory):
    _mutate(draft_directory, 1, lambda p: p.update(human_checkpoint_sha256="0" * 64))
    with pytest.raises(GoldenDatasetError, match="checkpoint"):
        retrieval_drafts.load_draft_batches(draft_directory)
    _mutate(draft_directory, 1, lambda p: p.update(human_checkpoint_sha256=HUMAN_CHECKPOINT_SHA256))
    _mutate(draft_directory, 1, lambda p: p["slots"][0]["label"].update(
        category="adversarial", adversarial_notes="Synthetic schema mutation",
    ))
    with pytest.raises(GoldenDatasetError, match="category|categories"):
        retrieval_drafts.load_draft_batches(draft_directory)


@pytest.mark.parametrize("kind", ["target", "review"])
def test_stale_references_are_rejected(draft_directory, kind):
    def change(payload):
        slot = payload["slots"][0]
        refs = slot["label"]["expected_relevant_documents"] if kind == "target" else slot["review_references"]
        refs[0]["content_sha256"] = "0" * 64
    _mutate(draft_directory, 1, change)
    with pytest.raises(GoldenDatasetError, match="stale"):
        retrieval_drafts.load_draft_batches(draft_directory)


def test_internal_review_reference_is_not_an_allowed_public_retrieval_target(draft_directory):
    def change(payload):
        slot = payload["slots"][-1]
        slot["label"].update(
            should_abstain=False,
            expected_relevant_documents=[slot["review_references"][0]],
            key_answer_facts=["Synthetic test fact"],
        )
    _mutate(draft_directory, 1, change)
    with pytest.raises(GoldenDatasetError, match="visibility scope"):
        retrieval_drafts.load_draft_batches(draft_directory)


def test_review_sources_must_cover_all_expected_documents(draft_directory):
    _mutate(draft_directory, 1, lambda p: p["slots"][0].update(review_references=[]))
    with pytest.raises(GoldenDatasetError, match="include all expected"):
        retrieval_drafts.load_draft_batches(draft_directory)


def test_review_sheets_match_current_draft_content(draft_directory, capsys):
    parser = retrieval_drafts.build_parser()
    options = ["--draft-directory", str(draft_directory), "--check-review-sheets"]
    assert retrieval_drafts.run_cli(parser.parse_args(options)) == 0
    _mutate(draft_directory, 1, lambda p: p["slots"][0].update(review_notes="Revised draft rationale"))
    assert retrieval_drafts.run_cli(parser.parse_args(options)) == 2
    assert "out of date" in capsys.readouterr().err
    assert retrieval_drafts.run_cli(parser.parse_args([
        "--draft-directory", str(draft_directory), "--write-review-sheets",
    ])) == 0
    assert retrieval_drafts.run_cli(parser.parse_args(options)) == 0


def test_draft_validation_never_constructs_settings_or_external_clients(monkeypatch):
    import openai
    import psycopg
    from app.core.config import Settings
    def forbidden(*args, **kwargs):
        pytest.fail("Draft validation must remain provider/database/settings free")
    monkeypatch.setattr(Settings, "__init__", forbidden)
    monkeypatch.setattr(openai.OpenAI, "__init__", forbidden)
    monkeypatch.setattr(psycopg, "connect", forbidden)
    assert retrieval_drafts.run_cli(retrieval_drafts.build_parser().parse_args([])) == 0


def test_malformed_draft_is_not_echoed(draft_directory, capsys):
    (draft_directory / "batch-1.json").write_text('{"private": "DO-NOT-ECHO"}')
    assert retrieval_drafts.run_cli(retrieval_drafts.build_parser().parse_args([
        "--draft-directory", str(draft_directory),
    ])) == 2
    output = capsys.readouterr()
    assert "DO-NOT-ECHO" not in output.err + output.out
