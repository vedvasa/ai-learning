from pathlib import Path

from ai_learning.golden_retrieval import (
    DEFAULT_CORPUS, DEFAULT_WORKSHEET, HUMAN_CHECKPOINT_SHA256,
    GoldenDatasetError, load_worksheet,
)
from ai_learning.retrieval_drafts import DEFAULT_DRAFT_DIRECTORY, load_draft_batches
from app.schemas.golden_retrieval import GoldenRetrievalDataset
from app.schemas.retrieval_working_set import RetrievalWorkingSet
from app.services.retrieval_evaluation import RetrievalEvaluationError

DEFAULT_REVIEWED_WORKSHEET = Path("datasets/rag-evaluation/week4_reviewed_labels.json")


def validate_checkpoint(dataset: GoldenRetrievalDataset, *, corpus_directory: Path) -> None:
    checkpoint = load_worksheet(
        DEFAULT_WORKSHEET, corpus_directory=corpus_directory, require_complete=True,
    )
    if checkpoint.dataset_sha256 != HUMAN_CHECKPOINT_SHA256:
        raise RetrievalEvaluationError("The preserved human checkpoint has changed.")
    assert checkpoint.dataset is not None
    if dataset.cases[:10] != checkpoint.dataset.cases:
        raise RetrievalEvaluationError("The first ten labels must match the human checkpoint.")


def load_evaluation_dataset(
    *, worksheet: Path, corpus_directory: Path = DEFAULT_CORPUS,
    include_provisional: bool = False,
    draft_directory: Path = DEFAULT_DRAFT_DIRECTORY,
) -> GoldenRetrievalDataset | RetrievalWorkingSet:
    loaded = load_worksheet(worksheet, corpus_directory=corpus_directory, require_complete=True)
    assert loaded.dataset is not None
    validate_checkpoint(loaded.dataset, corpus_directory=corpus_directory)
    if not include_provisional:
        return loaded.dataset
    batches = load_draft_batches(draft_directory, corpus_directory=corpus_directory)
    drafts = {slot.label.case_id: slot.label for batch in batches for slot in batch.slots}
    for case in loaded.dataset.cases[10:]:
        original = drafts.get(case.case_id)
        if original is None or case.model_dump(exclude={"label_provenance"}) != original.model_dump(
            exclude={"label_provenance"},
        ):
            raise GoldenDatasetError("A reviewed case does not match its pinned draft content.")
    reviewed_ids = {case.case_id for case in loaded.dataset.cases}
    return RetrievalWorkingSet(
        reviewed=loaded.dataset,
        provisional=tuple(case for key, case in drafts.items() if key not in reviewed_ids),
    )
