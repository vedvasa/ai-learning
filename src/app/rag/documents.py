from __future__ import annotations

import hashlib
import re
import tomllib
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

FRONT_MATTER_DELIMITER = "+++"
MULTIPLE_BLANK_LINES = re.compile(r"\n{3,}")


class DocumentFormatError(ValueError):
    """Raised when a corpus document does not satisfy the source contract."""


class DocumentMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_key: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str = Field(min_length=1)
    canonical_path: str = Field(pattern=r"^/")
    source_url: HttpUrl | None = None
    version: int = Field(gt=0)
    updated_at: datetime
    tenant_id: str = Field(min_length=1)
    visibility: Literal["public", "internal", "restricted"]

    @field_validator("title", "tenant_id")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


@dataclass(frozen=True, slots=True)
class SourceDocument:
    metadata: DocumentMetadata
    content: str
    content_hash: str
    source_path: str


def normalize_markdown(content: str) -> str:
    normalized = unicodedata.normalize("NFC", content)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in normalized.splitlines())
    normalized = MULTIPLE_BLANK_LINES.sub("\n\n", normalized).strip()
    if not normalized:
        raise DocumentFormatError("document body must not be blank")
    return f"{normalized}\n"


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_document(path: Path, *, source_path: str | None = None) -> SourceDocument:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise DocumentFormatError(f"could not read {path.name}") from error

    lines = raw.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    if not lines or lines[0].strip() != FRONT_MATTER_DELIMITER:
        raise DocumentFormatError(f"{path.name} must begin with TOML front matter")

    try:
        closing_index = next(
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == FRONT_MATTER_DELIMITER
        )
    except StopIteration as error:
        raise DocumentFormatError(f"{path.name} has unclosed TOML front matter") from error

    front_matter = "\n".join(lines[1:closing_index])
    body = "\n".join(lines[closing_index + 1 :])

    try:
        metadata = DocumentMetadata.model_validate(tomllib.loads(front_matter))
    except (tomllib.TOMLDecodeError, ValueError) as error:
        raise DocumentFormatError(f"{path.name} has invalid front matter") from error

    normalized_content = normalize_markdown(body)
    return SourceDocument(
        metadata=metadata,
        content=normalized_content,
        content_hash=content_hash(normalized_content),
        source_path=source_path or path.as_posix(),
    )


def load_corpus(directory: Path, *, limit: int | None = None) -> list[SourceDocument]:
    if not directory.is_dir():
        raise DocumentFormatError(f"corpus directory does not exist: {directory}")

    paths = sorted(directory.glob("*.md"))
    if limit is not None:
        paths = paths[:limit]
    if not paths:
        raise DocumentFormatError(f"no Markdown documents found in {directory}")

    documents = [
        load_document(path, source_path=path.relative_to(directory).as_posix())
        for path in paths
    ]
    identities = [
        (document.metadata.tenant_id, document.metadata.document_key)
        for document in documents
    ]
    if len(identities) != len(set(identities)):
        raise DocumentFormatError("corpus contains duplicate tenant/document keys")
    return documents
