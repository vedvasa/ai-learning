from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.rag.embeddings import EmbeddingError, OpenAIEmbeddingClient


def test_embedding_client_batches_and_restores_index_order() -> None:
    create = Mock(
        side_effect=[
            SimpleNamespace(
                data=[
                    SimpleNamespace(index=1, embedding=[0.3, 0.4]),
                    SimpleNamespace(index=0, embedding=[0.1, 0.2]),
                ],
                usage=SimpleNamespace(total_tokens=4),
            ),
            SimpleNamespace(
                data=[SimpleNamespace(index=0, embedding=[0.5, 0.6])],
                usage=SimpleNamespace(total_tokens=2),
            ),
        ]
    )
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    embeddings = OpenAIEmbeddingClient(
        api_key="test-key",
        model="embedding-test",
        dimensions=2,
        batch_size=2,
        client=client,
    )

    result = embeddings.embed_many(["first", "second", "third"])

    assert result.vectors == ((0.1, 0.2), (0.3, 0.4), (0.5, 0.6))
    assert [call.input_tokens for call in result.calls] == [4, 2]
    assert create.call_count == 2
    create.assert_any_call(
        model="embedding-test",
        input=["first", "second"],
        dimensions=2,
        encoding_format="float",
    )


def test_embedding_client_rejects_wrong_dimensions() -> None:
    response = SimpleNamespace(
        data=[SimpleNamespace(index=0, embedding=[0.1])],
        usage=None,
    )
    client = SimpleNamespace(
        embeddings=SimpleNamespace(create=Mock(return_value=response))
    )
    embeddings = OpenAIEmbeddingClient(
        api_key="test-key", dimensions=2, client=client
    )

    with pytest.raises(EmbeddingError, match="invalid_embedding_dimensions"):
        embeddings.embed_many(["text"])


def test_embedding_client_disables_sdk_retries() -> None:
    with patch("app.rag.embeddings.OpenAI") as openai_client:
        OpenAIEmbeddingClient(
            api_key="test-key",
            timeout_seconds=7,
        )

    openai_client.assert_called_once_with(
        api_key="test-key",
        timeout=7,
        max_retries=0,
    )
