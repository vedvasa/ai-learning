from __future__ import annotations

from datetime import date
from typing import Literal, Self

from pydantic import Field, StrictBool, model_validator

from app.schemas.golden_retrieval import (
    RetrievalCaseContent,
    StableDocumentReference,
    StrictGoldenModel,
)


class DraftLabelProvenance(StrictGoldenModel):
    origin: Literal["model_assisted"]
    drafted_on: date
    human_reviewed: StrictBool

    @model_validator(mode="after")
    def reject_review_claim(self) -> Self:
        if self.human_reviewed:
            raise ValueError("drafts cannot claim human review")
        return self


class DraftRetrievalCase(RetrievalCaseContent):
    label_provenance: DraftLabelProvenance


class DraftReviewSlot(StrictGoldenModel):
    slot_number: int = Field(ge=11, le=40, strict=True)
    label: DraftRetrievalCase
    review_notes: str = Field(min_length=1, max_length=1_500)
    review_references: tuple[StableDocumentReference, ...] = Field(max_length=8)


class RetrievalDraftBatch(StrictGoldenModel):
    schema_version: Literal["1.0"] = "1.0"
    purpose: Literal["retrieval_label_drafts"]
    status: Literal["awaiting_human_review"]
    batch_number: int = Field(ge=1, le=3, strict=True)
    human_checkpoint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    slots: tuple[DraftReviewSlot, ...] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def validate_slots(self) -> Self:
        first = self.batch_number * 10 + 1
        if [slot.slot_number for slot in self.slots] != list(range(first, first + 10)):
            raise ValueError("draft slots must match the batch's ten positions")
        ids = [slot.label.case_id for slot in self.slots]
        questions = [slot.label.question.casefold() for slot in self.slots]
        if len(ids) != len(set(ids)) or len(questions) != len(set(questions)):
            raise ValueError("draft case IDs and questions must be unique")
        return self
