from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from app.schemas.retrieval import MAX_QUESTION_CHARACTERS

INITIAL_HUMAN_LABEL_COUNT = 10


class StrictGoldenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GoldenDatasetPurpose(StrEnum):
    GOLDEN = "golden"
    CONTRACT_TEST = "contract_test"


class RetrievalCategory(StrEnum):
    DIRECT_FACT = "direct_fact"
    MULTI_DOCUMENT = "multi_document"
    AMBIGUOUS = "ambiguous"
    UNANSWERABLE = "unanswerable"
    ADVERSARIAL = "adversarial"
    PRIVACY_BOUNDARY = "privacy_boundary"


class RetrievalDifficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class PrincipalType(StrEnum):
    ANONYMOUS = "anonymous"
    MEMBER = "member"
    ADMINISTRATOR = "administrator"


class DocumentVisibility(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"


class LabelOrigin(StrEnum):
    HUMAN = "human"
    MODEL_ASSISTED = "model_assisted"
    SYNTHETIC_TEST = "synthetic_test"


class AnnotatorRole(StrEnum):
    PROJECT_OWNER = "project_owner"
    INDEPENDENT_REVIEWER = "independent_reviewer"
    TEST_FIXTURE = "test_fixture"


class GoldenUserContext(StrictGoldenModel):
    tenant_id: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
    )
    principal_id: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^fictional-[a-z0-9][a-z0-9-]*$",
    )
    principal_type: PrincipalType
    allowed_visibilities: tuple[DocumentVisibility, ...] = Field(
        min_length=1,
        max_length=3,
    )

    @model_validator(mode="after")
    def validate_visibility_scope(self) -> Self:
        if len(self.allowed_visibilities) != len(set(self.allowed_visibilities)):
            raise ValueError("allowed visibilities must be unique")
        if (
            self.principal_type is PrincipalType.ANONYMOUS
            and self.allowed_visibilities != (DocumentVisibility.PUBLIC,)
        ):
            raise ValueError("anonymous users may access only public documents")
        return self


class StableDocumentReference(StrictGoldenModel):
    tenant_id: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
    )
    document_key: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
    )
    document_version: int = Field(gt=0)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class GoldenLabelProvenance(StrictGoldenModel):
    origin: LabelOrigin
    annotator_role: AnnotatorRole
    labeled_on: date
    human_reviewed: StrictBool

    @model_validator(mode="after")
    def validate_non_personal_provenance(self) -> Self:
        if self.origin is LabelOrigin.SYNTHETIC_TEST:
            if self.annotator_role is not AnnotatorRole.TEST_FIXTURE:
                raise ValueError(
                    "synthetic test labels must use the test_fixture role"
                )
            if self.human_reviewed:
                raise ValueError(
                    "synthetic test labels cannot claim human review"
                )
            return self
        if self.annotator_role is AnnotatorRole.TEST_FIXTURE:
            raise ValueError("golden labels cannot use the test_fixture role")
        if not self.human_reviewed:
            raise ValueError("reference labels must be human reviewed")
        return self


class GoldenRetrievalCase(StrictGoldenModel):
    case_id: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
    )
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARACTERS)
    context: GoldenUserContext
    expected_relevant_documents: tuple[StableDocumentReference, ...] = Field(
        default=(),
        max_length=8,
    )
    key_answer_facts: tuple[str, ...] = Field(default=(), max_length=12)
    should_abstain: StrictBool
    category: RetrievalCategory
    difficulty: RetrievalDifficulty
    adversarial_notes: str | None = Field(
        default=None,
        min_length=1,
        max_length=1_000,
    )
    label_provenance: GoldenLabelProvenance

    @field_validator("question")
    @classmethod
    def question_must_contain_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must contain non-whitespace text")
        return value.strip()

    @field_validator("key_answer_facts")
    @classmethod
    def normalize_answer_facts(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("key answer facts must not be blank")
        if len({value.casefold() for value in normalized}) != len(normalized):
            raise ValueError("key answer facts must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_reference_label(self) -> Self:
        identities = [
            (reference.tenant_id, reference.document_key)
            for reference in self.expected_relevant_documents
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("expected document references must be unique")
        if any(
            reference.tenant_id != self.context.tenant_id
            for reference in self.expected_relevant_documents
        ):
            raise ValueError(
                "expected document references must match the case tenant"
            )

        if self.should_abstain:
            if self.expected_relevant_documents or self.key_answer_facts:
                raise ValueError(
                    "abstention cases cannot name relevant documents or answer facts"
                )
        elif not self.expected_relevant_documents or not self.key_answer_facts:
            raise ValueError(
                "answerable cases require relevant documents and key answer facts"
            )

        if self.category is RetrievalCategory.DIRECT_FACT:
            if self.should_abstain or len(self.expected_relevant_documents) != 1:
                raise ValueError(
                    "direct_fact cases must answer from exactly one document"
                )
        elif self.category is RetrievalCategory.MULTI_DOCUMENT:
            if self.should_abstain or len(self.expected_relevant_documents) < 2:
                raise ValueError(
                    "multi_document cases must answer from at least two documents"
                )
        elif self.category in {
            RetrievalCategory.AMBIGUOUS,
            RetrievalCategory.UNANSWERABLE,
        } and not self.should_abstain:
            raise ValueError(
                "ambiguous and unanswerable cases must expect abstention"
            )

        if self.category in {
            RetrievalCategory.ADVERSARIAL,
            RetrievalCategory.PRIVACY_BOUNDARY,
        } and self.adversarial_notes is None:
            raise ValueError(
                "adversarial and privacy-boundary cases require adversarial notes"
            )
        return self


class GoldenRetrievalDataset(StrictGoldenModel):
    schema_version: Literal["1.0"] = "1.0"
    purpose: GoldenDatasetPurpose
    dataset_name: str = Field(min_length=1, max_length=160)
    dataset_version: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )
    cases: tuple[GoldenRetrievalCase, ...] = Field(min_length=10, max_length=200)

    @model_validator(mode="after")
    def validate_dataset(self) -> Self:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case IDs must be unique")
        questions = [case.question.casefold() for case in self.cases]
        if len(questions) != len(set(questions)):
            raise ValueError("questions must be unique")

        missing_categories = set(RetrievalCategory) - {
            case.category for case in self.cases
        }
        if missing_categories:
            missing = ", ".join(
                sorted(category.value for category in missing_categories)
            )
            raise ValueError(f"dataset is missing required categories: {missing}")

        if self.purpose is GoldenDatasetPurpose.GOLDEN:
            if any(
                case.label_provenance.origin is LabelOrigin.SYNTHETIC_TEST
                for case in self.cases
            ):
                raise ValueError("golden datasets cannot contain synthetic test labels")
            if any(
                case.label_provenance.origin is not LabelOrigin.HUMAN
                for case in self.cases[:INITIAL_HUMAN_LABEL_COUNT]
            ):
                raise ValueError("the first ten golden labels must be human authored")
        elif any(
            case.label_provenance.origin is not LabelOrigin.SYNTHETIC_TEST
            for case in self.cases
        ):
            raise ValueError("contract-test datasets must use synthetic test labels")
        return self


class GoldenLabelSlot(StrictGoldenModel):
    slot_number: int = Field(ge=1, le=200)
    label: GoldenRetrievalCase | None = None


class GoldenRetrievalWorksheet(StrictGoldenModel):
    schema_version: Literal["1.0"] = "1.0"
    purpose: GoldenDatasetPurpose
    dataset_name: str = Field(min_length=1, max_length=160)
    dataset_version: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )
    slots: tuple[GoldenLabelSlot, ...] = Field(min_length=10, max_length=200)

    @model_validator(mode="after")
    def validate_slots(self) -> Self:
        slot_numbers = [slot.slot_number for slot in self.slots]
        if slot_numbers != list(range(1, len(self.slots) + 1)):
            raise ValueError("worksheet slots must be contiguous and start at one")

        completed = [slot.label for slot in self.slots if slot.label is not None]
        case_ids = [case.case_id for case in completed]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("completed worksheet case IDs must be unique")
        questions = [case.question.casefold() for case in completed]
        if len(questions) != len(set(questions)):
            raise ValueError("completed worksheet questions must be unique")
        if self.purpose is GoldenDatasetPurpose.GOLDEN:
            if any(
                slot.label is not None
                and slot.slot_number <= INITIAL_HUMAN_LABEL_COUNT
                and slot.label.label_provenance.origin is not LabelOrigin.HUMAN
                for slot in self.slots
            ):
                raise ValueError(
                    "the first ten worksheet labels must be human authored"
                )
            if any(
                case.label_provenance.origin is LabelOrigin.SYNTHETIC_TEST
                for case in completed
            ):
                raise ValueError(
                    "golden worksheets cannot contain synthetic test labels"
                )
        elif any(
            case.label_provenance.origin is not LabelOrigin.SYNTHETIC_TEST
            for case in completed
        ):
            raise ValueError(
                "contract-test worksheets must use synthetic test labels"
            )
        return self
