from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from app.schemas.golden_retrieval import GoldenRetrievalDataset, StrictGoldenModel
from app.schemas.retrieval_drafts import DraftRetrievalCase


class RetrievalWorkingSet(StrictGoldenModel):
    """Exploratory inputs with explicit provenance; never a golden dataset."""

    schema_version: Literal["1.0"] = "1.0"
    purpose: Literal["retrieval_working_set"] = "retrieval_working_set"
    dataset_version: Literal["week4-working-v1"] = "week4-working-v1"
    reviewed: GoldenRetrievalDataset
    provisional: tuple[DraftRetrievalCase, ...] = Field(max_length=30)

    @property
    def cases(self):
        return (*self.reviewed.cases, *self.provisional)

    @model_validator(mode="after")
    def validate_composition(self) -> Self:
        if self.reviewed.purpose != "golden":
            raise ValueError("working sets require real reviewed reference labels")
        ids = [case.case_id for case in self.cases]
        questions = [case.question.casefold() for case in self.cases]
        if len(ids) != len(set(ids)) or len(questions) != len(set(questions)):
            raise ValueError("working-set cases must be unique across groups")
        if len(self.cases) != 40:
            raise ValueError("the Week 4 working set must contain exactly forty cases")
        return self
