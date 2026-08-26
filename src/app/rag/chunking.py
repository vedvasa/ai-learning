from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

import tiktoken

from app.rag.documents import SourceDocument

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class TokenEncoder(Protocol):
    def encode(self, text: str) -> list[int]: ...

    def decode(self, tokens: list[int]) -> str: ...


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    chunk_index: int
    heading_path: tuple[str, ...]
    content: str
    token_count: int
    content_hash: str
    metadata: dict[str, str]


@dataclass(frozen=True, slots=True)
class _Section:
    heading_path: tuple[str, ...]
    heading_line: str | None
    body: str


class MarkdownChunker:
    """Create deterministic chunks at Markdown heading and paragraph boundaries."""

    def __init__(
        self,
        *,
        max_tokens: int = 500,
        model: str = "text-embedding-3-small",
        encoder: TokenEncoder | None = None,
    ) -> None:
        if max_tokens < 32:
            raise ValueError("max_tokens must be at least 32")
        self.max_tokens = max_tokens
        self._encoder = encoder or tiktoken.encoding_for_model(model)

    def chunk(self, document: SourceDocument) -> list[DocumentChunk]:
        pieces: list[tuple[tuple[str, ...], str]] = []
        for section in self._sections(document.content):
            pieces.extend(self._split_section(section))

        if not pieces:
            raise ValueError("document produced no searchable chunks")

        metadata = document.metadata
        common_metadata = {
            "document_key": metadata.document_key,
            "canonical_path": metadata.canonical_path,
            "source_path": document.source_path,
            "updated_at": metadata.updated_at.isoformat(),
            "visibility": metadata.visibility,
        }
        return [
            DocumentChunk(
                chunk_index=index,
                heading_path=heading_path,
                content=content,
                token_count=len(self._encoder.encode(content)),
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                metadata=dict(common_metadata),
            )
            for index, (heading_path, content) in enumerate(pieces)
        ]

    @staticmethod
    def _sections(content: str) -> list[_Section]:
        sections: list[_Section] = []
        headings: list[str] = []
        current_heading: str | None = None
        body_lines: list[str] = []

        def flush() -> None:
            body = "\n".join(body_lines).strip()
            if body or current_heading:
                sections.append(
                    _Section(tuple(headings), current_heading, body)
                )

        for line in content.splitlines():
            match = HEADING.match(line)
            if match is None:
                body_lines.append(line)
                continue

            flush()
            level = len(match.group(1))
            heading = match.group(2).strip()
            headings = headings[: level - 1]
            headings.append(heading)
            current_heading = line.strip()
            body_lines = []

        flush()
        return sections

    def _split_section(self, section: _Section) -> list[tuple[tuple[str, ...], str]]:
        prefix = section.heading_line or ""
        paragraphs = [
            paragraph.strip()
            for paragraph in re.split(r"\n\s*\n", section.body)
            if paragraph.strip()
        ]
        if not paragraphs:
            if prefix and len(self._encoder.encode(prefix)) <= self.max_tokens:
                return [(section.heading_path, prefix)]
            return []

        chunks: list[str] = []
        current = prefix
        for paragraph in paragraphs:
            candidate = self._join(current, paragraph)
            if len(self._encoder.encode(candidate)) <= self.max_tokens:
                current = candidate
                continue

            if current and current != prefix:
                chunks.append(current)
                current = prefix

            paragraph_tokens = self._encoder.encode(paragraph)
            while paragraph_tokens:
                window_size = self._largest_window(prefix, paragraph_tokens)
                if window_size == 0:
                    raise ValueError("heading consumes the entire chunk token budget")
                window = self._encoder.decode(
                    paragraph_tokens[:window_size]
                ).strip()
                candidate = self._join(prefix, window)
                paragraph_tokens = paragraph_tokens[window_size:]
                if paragraph_tokens:
                    chunks.append(candidate)
                else:
                    current = candidate

        if current and current != prefix:
            chunks.append(current)
        return [(section.heading_path, chunk) for chunk in chunks]

    @staticmethod
    def _join(left: str, right: str) -> str:
        if not left:
            return right.strip()
        if not right:
            return left.strip()
        return f"{left.strip()}\n\n{right.strip()}"

    def _largest_window(self, prefix: str, tokens: list[int]) -> int:
        low = 1
        high = len(tokens)
        best = 0
        while low <= high:
            midpoint = (low + high) // 2
            text = self._encoder.decode(tokens[:midpoint]).strip()
            candidate = self._join(prefix, text)
            if len(self._encoder.encode(candidate)) <= self.max_tokens:
                best = midpoint
                low = midpoint + 1
            else:
                high = midpoint - 1
        return best
