from __future__ import annotations

import hashlib
import json
from math import ceil
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

from app.rag.chunking import MarkdownChunker
from app.rag.repository import PsycopgKnowledgeRepository
from app.schemas.golden_retrieval import StableDocumentReference
from app.schemas.retrieval_evaluation import (
    EmbeddingCaptureUsage, RankedChunkReference, RecordedRetrievalCase, RecordedRetrievalRun,
)
from app.schemas.vector_capture import CapturedChunk, CapturedQuery, VectorCapture
from app.services.retrieval_evaluation import (
    RetrievalEvaluationError, _canonical_hash, corpus_sha256,
)


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prepare_vector_inputs(dataset, corpus, configuration):
    chunker = MarkdownChunker(
        max_tokens=configuration.chunk_max_tokens, model=configuration.embedding_model,
    )
    chunks = []
    for document in corpus:
        reference = StableDocumentReference(
            tenant_id=document.metadata.tenant_id,
            document_key=document.metadata.document_key,
            document_version=document.metadata.version, content_sha256=document.content_hash,
        )
        chunks.extend(
            (RankedChunkReference(document=reference, chunk_index=chunk.chunk_index), chunk)
            for chunk in chunker.chunk(document)
        )
    return chunks


def capture_plan(dataset, chunks, configuration):
    # Match the application's tokenizer without constructing a provider client.
    import tiktoken
    encoder = tiktoken.encoding_for_model(configuration.embedding_model)
    tokens = sum(chunk.token_count for _, chunk in chunks)
    tokens += sum(len(encoder.encode(case.question)) for case in dataset.cases)
    return {
        "documents": len({(ref.document.tenant_id, ref.document.document_key) for ref, _ in chunks}),
        "chunks": len(chunks), "queries": len(dataset.cases),
        "estimated_input_tokens": tokens,
        "maximum_api_requests": ceil((len(chunks) + len(dataset.cases)) / 64),
    }


def capture_vectors(dataset, corpus, configuration, *, client, source_revision):
    if (client.model, client.dimensions) != (configuration.embedding_model, configuration.embedding_dimensions):
        raise RetrievalEvaluationError("Embedding client does not match the capture configuration.")
    chunks = prepare_vector_inputs(dataset, corpus, configuration)
    texts = [chunk.content for _, chunk in chunks] + [case.question for case in dataset.cases]
    embedded = client.embed_many(texts)
    if len(embedded.vectors) != len(texts):
        raise RetrievalEvaluationError("Embedding response did not cover every input.")
    tokens = [call.input_tokens for call in embedded.calls]
    return VectorCapture(
        evidence_kind="recorded_openai_embeddings", source_revision=source_revision,
        dataset_sha256=_canonical_hash(dataset.model_dump(mode="json")),
        corpus_sha256=corpus_sha256(corpus), configuration=configuration,
        chunks=tuple(
            CapturedChunk(reference=ref, input_sha256=chunk.content_hash, vector=vector)
            for (ref, chunk), vector in zip(chunks, embedded.vectors[:len(chunks)], strict=True)
        ),
        queries=tuple(
            CapturedQuery(case_id=case.case_id, input_sha256=text_sha256(case.question), vector=vector)
            for case, vector in zip(dataset.cases, embedded.vectors[len(chunks):], strict=True)
        ),
        embedding_calls=len(embedded.calls),
        embedding_input_tokens=sum(tokens) if tokens and all(value is not None for value in tokens) else None,
        embedding_latency_ms=sum(call.latency_ms for call in embedded.calls),
    )


def validate_capture(capture, dataset, corpus):
    if (capture.dataset_sha256 != _canonical_hash(dataset.model_dump(mode="json"))
            or capture.corpus_sha256 != corpus_sha256(corpus)):
        raise RetrievalEvaluationError("Captured vectors do not match dataset/corpus hashes.")
    chunks = prepare_vector_inputs(dataset, corpus, capture.configuration)
    expected = [(ref, chunk.content_hash) for ref, chunk in chunks]
    actual = [(chunk.reference, chunk.input_sha256) for chunk in capture.chunks]
    if expected != actual:
        raise RetrievalEvaluationError("Captured chunks do not match the current chunker.")
    if {query.case_id: query.input_sha256 for query in capture.queries} != {
        case.case_id: text_sha256(case.question) for case in dataset.cases
    }:
        raise RetrievalEvaluationError("Captured queries do not match the working set.")
    return chunks


def execute_local_vectors(connection, capture, dataset, corpus, *, source_revision):
    """Use only session-local tables; caller rolls back the dedicated connection."""
    chunks = validate_capture(capture, dataset, corpus)
    config = capture.configuration
    for name in ("documents", "document_versions", "chunks"):
        # Closed names only; never accept an operator-supplied schema/table.
        connection.execute(
            f"create temporary table {name} (like knowledge.{name} including all) on commit drop"
        )
    references = {}
    versions = {}
    for document in corpus:
        meta = document.metadata
        identity = (meta.tenant_id, meta.document_key)
        document_id = uuid5(NAMESPACE_URL, f"week4:{meta.tenant_id}:{meta.document_key}")
        version_id = uuid5(document_id, document.content_hash)
        versions[identity] = version_id
        connection.execute(
            "insert into pg_temp.documents (id,tenant_id,document_key,title,canonical_path,source_url,visibility) "
            "values (%s,%s,%s,%s,%s,%s,%s)",
            (document_id, meta.tenant_id, meta.document_key, meta.title, meta.canonical_path,
             str(meta.source_url) if meta.source_url else None, meta.visibility),
        )
        connection.execute(
            "insert into pg_temp.document_versions "
            "(id,document_id,tenant_id,version,content,content_hash,is_active) values (%s,%s,%s,%s,%s,%s,true)",
            (version_id, document_id, meta.tenant_id, meta.version, document.content, document.content_hash),
        )
    for (reference, chunk), captured in zip(chunks, capture.chunks, strict=True):
        ref = reference.document
        version_id = versions[(ref.tenant_id, ref.document_key)]
        chunk_id = uuid5(version_id, f"{chunk.chunk_index}:{chunk.content_hash}")
        references[chunk_id] = reference
        connection.execute(
            "insert into pg_temp.chunks "
            "(id,document_version_id,tenant_id,chunk_index,heading_path,content,token_count,content_hash,metadata,"
            "embedding,embedding_model,embedding_dimension) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::extensions.vector,%s,%s)",
            (chunk_id, version_id, ref.tenant_id, chunk.chunk_index, list(chunk.heading_path),
             chunk.content, chunk.token_count, chunk.content_hash, json.dumps(chunk.metadata),
             PsycopgKnowledgeRepository._serialize_vector(captured.vector),
             config.embedding_model, config.embedding_dimensions),
        )
    for name in ("documents", "document_versions", "chunks"):
        connection.execute(f"analyze pg_temp.{name}")
    queries = {query.case_id: query for query in capture.queries}
    outcomes = []
    for case in dataset.cases:
        started = perf_counter()
        matches = PsycopgKnowledgeRepository.search_chunks_on_connection(
            connection, namespace="pg_temp", tenant_id=case.context.tenant_id,
            query_embedding=queries[case.case_id].vector,
            embedding_model=config.embedding_model, embedding_dimensions=config.embedding_dimensions,
            top_k=config.top_k, minimum_similarity=config.minimum_similarity,
            allowed_visibilities=case.context.allowed_visibilities,
        )
        outcomes.append(RecordedRetrievalCase(
            case_id=case.case_id, ranked_chunks=tuple(references[match.chunk_id] for match in matches),
            search_latency_ms=round((perf_counter() - started) * 1000, 3),
        ))
    return RecordedRetrievalRun(
        evidence_kind="synthetic_test" if capture.evidence_kind == "synthetic_test" else "recorded_exact_vector",
        source_revision=source_revision, search_execution="local_pgvector",
        vector_capture_sha256=_canonical_hash(capture.model_dump(mode="json")),
        capture_usage=EmbeddingCaptureUsage(
            calls=capture.embedding_calls, input_tokens=capture.embedding_input_tokens,
            latency_ms=capture.embedding_latency_ms,
        ),
        dataset_sha256=capture.dataset_sha256, corpus_sha256=capture.corpus_sha256,
        configuration=config, cases=tuple(outcomes),
    )
