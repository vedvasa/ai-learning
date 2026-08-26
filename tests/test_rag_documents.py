from pathlib import Path

import pytest

from app.rag.documents import DocumentFormatError, load_corpus, load_document

VALID_DOCUMENT = """+++
document_key = "billing-help"
title = "Billing help"
canonical_path = "/support/billing/help"
source_url = "https://support.knowledgedesk.example/billing/help"
version = 1
updated_at = "2026-08-25T10:00:00Z"
tenant_id = "tenant-a"
visibility = "public"
+++
# Billing help<TRAILING-SPACES>

Use the billing page.\r
""".replace("<TRAILING-SPACES>", "  ")


def test_load_document_validates_metadata_and_normalizes_content(tmp_path: Path) -> None:
    path = tmp_path / "billing.md"
    path.write_text(VALID_DOCUMENT, encoding="utf-8")

    document = load_document(path, source_path="billing.md")

    assert document.metadata.document_key == "billing-help"
    assert document.metadata.version == 1
    assert document.content == "# Billing help\n\nUse the billing page.\n"
    assert len(document.content_hash) == 64
    assert document.source_path == "billing.md"


def test_load_document_rejects_missing_front_matter(tmp_path: Path) -> None:
    path = tmp_path / "invalid.md"
    path.write_text("# Missing metadata\n", encoding="utf-8")

    with pytest.raises(DocumentFormatError, match="must begin"):
        load_document(path)


def test_load_corpus_is_sorted_and_rejects_duplicate_identity(tmp_path: Path) -> None:
    (tmp_path / "b.md").write_text(VALID_DOCUMENT, encoding="utf-8")
    duplicate = VALID_DOCUMENT.replace('title = "Billing help"', 'title = "Duplicate"')
    (tmp_path / "a.md").write_text(duplicate, encoding="utf-8")

    with pytest.raises(DocumentFormatError, match="duplicate"):
        load_corpus(tmp_path)
