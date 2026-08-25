begin;

create extension if not exists pgtap with schema extensions;
set local search_path = extensions, public;

select plan(27);

select has_schema('knowledge', 'knowledge schema exists');
select ok(
    exists (select 1 from pg_extension where extname = 'vector'),
    'pgvector is enabled'
);

select has_table('knowledge', 'documents', 'documents table exists');
select has_table('knowledge', 'document_versions', 'document_versions table exists');
select has_table('knowledge', 'chunks', 'chunks table exists');
select has_table('knowledge', 'ingestion_jobs', 'ingestion_jobs table exists');
select has_table('knowledge', 'conversations', 'conversations table exists');
select has_table('knowledge', 'messages', 'messages table exists');
select has_table('knowledge', 'model_calls', 'model_calls table exists');

select is(
    (
        select format_type(attribute.atttypid, attribute.atttypmod)
        from pg_attribute as attribute
        join pg_class as relation on relation.oid = attribute.attrelid
        join pg_namespace as namespace on namespace.oid = relation.relnamespace
        where namespace.nspname = 'knowledge'
          and relation.relname = 'chunks'
          and attribute.attname = 'embedding'
    ),
    'vector(1536)',
    'chunk embeddings have an explicit 1536-dimension type'
);
select has_column('knowledge', 'chunks', 'embedding_model', 'embedding model is recorded');
select has_column(
    'knowledge',
    'chunks',
    'embedding_dimension',
    'embedding dimension is recorded'
);
select has_column('knowledge', 'chunks', 'metadata', 'chunk metadata is recorded');
select has_index(
    'knowledge',
    'document_versions',
    'document_versions_one_active_per_document',
    'only one active version is allowed per document'
);
select has_index(
    'knowledge',
    'chunks',
    'chunks_tenant_id_idx',
    'tenant filtering has a supporting index'
);
select has_index(
    'knowledge',
    'chunks',
    'chunks_embedding_cache_lookup_idx',
    'content hashes support model-aware embedding cache lookup'
);

select is(
    has_schema_privilege('public', 'knowledge', 'usage'),
    false,
    'PUBLIC cannot use the private schema'
);
select is(
    has_schema_privilege('anon', 'knowledge', 'usage'),
    false,
    'anon cannot use the private schema'
);
select is(
    has_schema_privilege('authenticated', 'knowledge', 'usage'),
    false,
    'authenticated cannot use the private schema'
);

insert into knowledge.documents (
    id,
    tenant_id,
    document_key,
    title,
    canonical_path
)
values (
    '10000000-0000-0000-0000-000000000001',
    'tenant-a',
    'billing-refunds',
    'Billing refunds',
    '/support/billing/refunds'
);

select throws_ok(
    $$
        insert into knowledge.document_versions (
            document_id,
            tenant_id,
            version,
            content,
            content_hash
        )
        values (
            '10000000-0000-0000-0000-000000000001',
            'tenant-b',
            1,
            'Wrong tenant',
            repeat('a', 64)
        )
    $$,
    '23503',
    null,
    'cross-tenant document versions are rejected'
);

select throws_ok(
    $$
        insert into knowledge.document_versions (
            document_id,
            tenant_id,
            version,
            content,
            content_hash
        )
        values (
            '10000000-0000-0000-0000-000000000001',
            'tenant-a',
            1,
            'Bad hash',
            'not-a-sha256'
        )
    $$,
    '23514',
    null,
    'invalid content hashes are rejected'
);

insert into knowledge.document_versions (
    id,
    document_id,
    tenant_id,
    version,
    content,
    content_hash,
    is_active
)
values (
    '20000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    'tenant-a',
    1,
    'Refund policy content',
    repeat('b', 64),
    true
);

select throws_ok(
    $$
        insert into knowledge.document_versions (
            document_id,
            tenant_id,
            version,
            content,
            content_hash,
            is_active
        )
        values (
            '10000000-0000-0000-0000-000000000001',
            'tenant-a',
            2,
            'Another active version',
            repeat('c', 64),
            true
        )
    $$,
    '23505',
    null,
    'a document cannot have two active versions'
);

select lives_ok(
    $$
        insert into knowledge.chunks (
            document_version_id,
            tenant_id,
            chunk_index,
            content,
            token_count,
            content_hash
        )
        values (
            '20000000-0000-0000-0000-000000000001',
            'tenant-a',
            0,
            'Refunds are available within thirty days.',
            8,
            repeat('d', 64)
        )
    $$,
    'a chunk may be stored before its embedding is generated'
);

select throws_ok(
    $$
        insert into knowledge.chunks (
            document_version_id,
            tenant_id,
            chunk_index,
            content,
            token_count,
            content_hash,
            embedding,
            embedding_model,
            embedding_dimension
        )
        values (
            '20000000-0000-0000-0000-000000000001',
            'tenant-a',
            1,
            'A chunk with incompatible embedding metadata.',
            7,
            repeat('e', 64),
            array_fill(0::real, array[1536])::extensions.vector,
            'different-embedding-model',
            1536
        )
    $$,
    '23514',
    null,
    'incompatible embedding models are rejected'
);

select hasnt_column(
    'knowledge',
    'model_calls',
    'prompt',
    'model-call telemetry cannot store prompts'
);
select hasnt_column(
    'knowledge',
    'model_calls',
    'output',
    'model-call telemetry cannot store model output'
);
select is(
    (
        select count(*)::integer
        from pg_indexes
        where schemaname = 'knowledge'
          and tablename = 'chunks'
          and indexdef ~* 'using (hnsw|ivfflat)'
    ),
    0,
    'Week 3 starts with exact vector search rather than an unmeasured ANN index'
);

select * from finish();
rollback;
