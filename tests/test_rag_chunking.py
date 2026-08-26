from datetime import UTC, datetime

from app.rag.chunking import MarkdownChunker
from app.rag.documents import DocumentMetadata, SourceDocument, content_hash


class CharacterEncoder:
    def encode(self, text: str) -> list[int]:
        return [ord(character) for character in text]

    def decode(self, tokens: list[int]) -> str:
        return "".join(chr(token) for token in tokens)


def make_document(content: str) -> SourceDocument:
    return SourceDocument(
        metadata=DocumentMetadata(
            document_key="sync-help",
            title="Sync help",
            canonical_path="/support/sync",
            source_url="https://support.knowledgedesk.example/sync",
            version=1,
            updated_at=datetime(2026, 8, 25, tzinfo=UTC),
            tenant_id="tenant-a",
            visibility="public",
        ),
        content=content,
        content_hash=content_hash(content),
        source_path="sync.md",
    )


def test_chunker_preserves_heading_paths_and_source_identity() -> None:
    document = make_document(
        "# Sync help\n\nOverview.\n\n## Mobile\n\nRefresh both devices.\n"
    )
    chunker = MarkdownChunker(max_tokens=100, encoder=CharacterEncoder())

    chunks = chunker.chunk(document)

    assert [chunk.heading_path for chunk in chunks] == [
        ("Sync help",),
        ("Sync help", "Mobile"),
    ]
    assert chunks[1].content.startswith("## Mobile")
    assert chunks[1].metadata["document_key"] == "sync-help"
    assert chunks[1].metadata["source_path"] == "sync.md"


def test_chunker_splits_oversized_paragraph_without_exceeding_limit() -> None:
    document = make_document("# Long\n\n" + "word " * 40)
    chunker = MarkdownChunker(max_tokens=32, encoder=CharacterEncoder())

    chunks = chunker.chunk(document)

    assert len(chunks) > 1
    assert all(chunk.token_count <= 32 for chunk in chunks)
    assert all(chunk.heading_path == ("Long",) for chunk in chunks)


def test_chunking_is_deterministic() -> None:
    document = make_document("# Sync help\n\nRefresh both devices.\n")
    chunker = MarkdownChunker(max_tokens=100, encoder=CharacterEncoder())

    first = chunker.chunk(document)
    second = chunker.chunk(document)

    assert first == second
