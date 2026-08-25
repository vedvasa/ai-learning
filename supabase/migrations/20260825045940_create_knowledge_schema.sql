create schema if not exists knowledge;

revoke all on schema knowledge from public;
revoke all on schema knowledge from anon;
revoke all on schema knowledge from authenticated;

create extension if not exists vector with schema extensions;

create table knowledge.documents (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null check (btrim(tenant_id) <> ''),
    document_key text not null check (btrim(document_key) <> ''),
    title text not null check (btrim(title) <> ''),
    canonical_path text not null check (canonical_path ~ '^/'),
    source_url text,
    visibility text not null default 'internal'
        check (visibility in ('public', 'internal', 'restricted')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (tenant_id, document_key),
    unique (tenant_id, canonical_path),
    unique (id, tenant_id),
    check (source_url is null or source_url ~ '^https?://')
);

create table knowledge.document_versions (
    id uuid primary key default gen_random_uuid(),
    document_id uuid not null,
    tenant_id text not null,
    version integer not null check (version > 0),
    content text not null check (btrim(content) <> ''),
    content_hash text not null check (content_hash ~ '^[0-9a-f]{64}$'),
    is_active boolean not null default false,
    created_at timestamptz not null default now(),
    foreign key (document_id, tenant_id)
        references knowledge.documents (id, tenant_id) on delete cascade,
    unique (document_id, version),
    unique (document_id, content_hash),
    unique (id, tenant_id)
);

create unique index document_versions_one_active_per_document
    on knowledge.document_versions (document_id)
    where is_active;

create table knowledge.chunks (
    id uuid primary key default gen_random_uuid(),
    document_version_id uuid not null,
    tenant_id text not null,
    chunk_index integer not null check (chunk_index >= 0),
    heading_path text[] not null default '{}',
    content text not null check (btrim(content) <> ''),
    token_count integer not null check (token_count > 0),
    content_hash text not null check (content_hash ~ '^[0-9a-f]{64}$'),
    metadata jsonb not null default '{}'::jsonb
        check (jsonb_typeof(metadata) = 'object'),
    embedding extensions.vector(1536),
    embedding_model text,
    embedding_dimension integer,
    created_at timestamptz not null default now(),
    foreign key (document_version_id, tenant_id)
        references knowledge.document_versions (id, tenant_id) on delete cascade,
    unique (document_version_id, chunk_index),
    check (
        (
            embedding is null
            and embedding_model is null
            and embedding_dimension is null
        )
        or
        (
            embedding is not null
            and embedding_model = 'text-embedding-3-small'
            and embedding_dimension = 1536
        )
    )
);

create index chunks_tenant_id_idx on knowledge.chunks (tenant_id);
create index chunks_document_version_id_idx
    on knowledge.chunks (document_version_id);
create index chunks_embedding_cache_lookup_idx
    on knowledge.chunks (content_hash, embedding_model, embedding_dimension)
    where embedding is not null;

create table knowledge.ingestion_jobs (
    id uuid primary key default gen_random_uuid(),
    document_id uuid,
    tenant_id text not null check (btrim(tenant_id) <> ''),
    status text not null default 'pending'
        check (status in ('pending', 'running', 'succeeded', 'failed', 'skipped')),
    source_path text not null check (btrim(source_path) <> ''),
    source_content_hash text
        check (source_content_hash is null or source_content_hash ~ '^[0-9a-f]{64}$'),
    chunks_written integer not null default 0 check (chunks_written >= 0),
    error_kind text,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz not null default now(),
    foreign key (document_id, tenant_id)
        references knowledge.documents (id, tenant_id)
        on delete set null (document_id),
    check (finished_at is null or started_at is not null),
    check (finished_at is null or finished_at >= started_at)
);

create index ingestion_jobs_tenant_created_idx
    on knowledge.ingestion_jobs (tenant_id, created_at desc);

create table knowledge.conversations (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null check (btrim(tenant_id) <> ''),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (id, tenant_id)
);

create table knowledge.messages (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid not null,
    tenant_id text not null,
    sequence_number integer not null check (sequence_number >= 0),
    role text not null check (role in ('user', 'assistant')),
    content text not null check (btrim(content) <> ''),
    citations jsonb not null default '[]'::jsonb
        check (jsonb_typeof(citations) = 'array'),
    abstained boolean,
    created_at timestamptz not null default now(),
    foreign key (conversation_id, tenant_id)
        references knowledge.conversations (id, tenant_id) on delete cascade,
    unique (conversation_id, sequence_number),
    unique (id, tenant_id),
    check (
        (role = 'user' and abstained is null and citations = '[]'::jsonb)
        or role = 'assistant'
    )
);

create index messages_conversation_sequence_idx
    on knowledge.messages (conversation_id, sequence_number);

create table knowledge.model_calls (
    id uuid primary key default gen_random_uuid(),
    request_id uuid not null,
    tenant_id text not null check (btrim(tenant_id) <> ''),
    conversation_id uuid,
    message_id uuid,
    operation text not null check (btrim(operation) <> ''),
    provider text not null check (provider in ('openai', 'anthropic')),
    model text not null check (btrim(model) <> ''),
    outcome text not null check (outcome in ('succeeded', 'failed', 'cancelled')),
    latency_ms numeric(12, 2) not null check (latency_ms >= 0),
    input_tokens integer check (input_tokens is null or input_tokens >= 0),
    output_tokens integer check (output_tokens is null or output_tokens >= 0),
    error_kind text,
    created_at timestamptz not null default now(),
    foreign key (conversation_id, tenant_id)
        references knowledge.conversations (id, tenant_id)
        on delete set null (conversation_id),
    foreign key (message_id, tenant_id)
        references knowledge.messages (id, tenant_id)
        on delete set null (message_id),
    unique (request_id, operation)
);

create index model_calls_tenant_created_idx
    on knowledge.model_calls (tenant_id, created_at desc);

comment on schema knowledge is
    'Private backend schema for KnowledgeDesk documents, retrieval, and model telemetry.';
comment on column knowledge.chunks.embedding is
    '1536-dimensional text-embedding-3-small vector; model changes require a migration.';
comment on table knowledge.model_calls is
    'Operational metadata only. Prompts, retrieved context, and model output do not belong here.';
