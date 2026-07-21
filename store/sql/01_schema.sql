CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS canonical_documents (
    canonical_id TEXT PRIMARY KEY,
    reconciliation_key TEXT NOT NULL UNIQUE,

    document_type TEXT,
    title TEXT NOT NULL,
    abstract TEXT,

    year INTEGER,
    published_at TIMESTAMPTZ,
    publication_date TIMESTAMPTZ,
    updated_record_at TIMESTAMPTZ,

    doi TEXT,
    arxiv_id TEXT,
    openalex_id TEXT,
    pmid TEXT,
    pmcid TEXT,
    semantic_scholar_id TEXT,
    dblp_id TEXT,
    mag_id TEXT,

    journal_ref TEXT,
    comment TEXT,
    venue TEXT,
    journal TEXT,
    conference TEXT,
    publisher TEXT,
    publication_type TEXT,
    language TEXT,

    landing_page_url TEXT,
    pdf_url TEXT,
    repo_url TEXT,
    license TEXT,

    open_access BOOLEAN,
    is_open_access BOOLEAN,
    is_preprint BOOLEAN,
    is_review BOOLEAN,
    is_survey BOOLEAN,
    is_withdrawn BOOLEAN,

    citation_graph_available BOOLEAN,
    has_code_link BOOLEAN,
    has_dataset_link BOOLEAN,
    has_model_link BOOLEAN,
    has_pdf BOOLEAN,

    cited_by_count INTEGER,
    references_count INTEGER,

    source_count INTEGER,
    unique_source_count INTEGER,
    metadata_completeness_score DOUBLE PRECISION,

    authors JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
    external_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
    categories JSONB NOT NULL DEFAULT '[]'::jsonb,
    concepts JSONB NOT NULL DEFAULT '[]'::jsonb,
    keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    referenced_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    referenced_dois JSONB NOT NULL DEFAULT '[]'::jsonb,
    referenced_arxiv_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    code_links JSONB NOT NULL DEFAULT '[]'::jsonb,
    dataset_links JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_links JSONB NOT NULL DEFAULT '[]'::jsonb,
    doc_ids JSONB NOT NULL DEFAULT '[]'::jsonb,

    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS source_documents (
    source_observation_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,

    source TEXT NOT NULL,
    source_id TEXT,
    source_record_id TEXT,
    source_record_url TEXT,
    source_api_url TEXT,
    canonical_url TEXT,

    content_hash TEXT,
    document_type TEXT,

    doi TEXT,
    arxiv_id TEXT,
    openalex_id TEXT,
    pmid TEXT,
    pmcid TEXT,
    semantic_scholar_id TEXT,
    dblp_id TEXT,
    mag_id TEXT,

    title TEXT,
    abstract TEXT,

    year INTEGER,
    published_at TIMESTAMPTZ,
    publication_date TIMESTAMPTZ,
    updated_source_at TIMESTAMPTZ,

    landing_page_url TEXT,
    pdf_url TEXT,
    repo_url TEXT,
    license TEXT,

    open_access BOOLEAN,
    primary_category TEXT,
    comment TEXT,
    journal_ref TEXT,
    venue TEXT,
    journal TEXT,
    conference TEXT,
    publisher TEXT,
    publication_type TEXT,
    language TEXT,

    cited_by_count INTEGER,
    references_count INTEGER,

    citation_graph_available BOOLEAN,
    has_code_link BOOLEAN,
    has_dataset_link BOOLEAN,
    has_model_link BOOLEAN,
    has_pdf BOOLEAN,

    is_withdrawn BOOLEAN,
    is_open_access BOOLEAN,
    is_preprint BOOLEAN,
    is_review BOOLEAN,
    is_survey BOOLEAN,

    raw_artifact_path TEXT,
    raw_source_name TEXT,
    ingested_at TIMESTAMPTZ,
    metadata_completeness_score DOUBLE PRECISION,
    pipeline_version TEXT,

    authors JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
    external_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
    categories JSONB NOT NULL DEFAULT '[]'::jsonb,
    concepts JSONB NOT NULL DEFAULT '[]'::jsonb,
    keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    referenced_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    referenced_dois JSONB NOT NULL DEFAULT '[]'::jsonb,
    referenced_arxiv_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    code_links JSONB NOT NULL DEFAULT '[]'::jsonb,
    dataset_links JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_links JSONB NOT NULL DEFAULT '[]'::jsonb,
    stages JSONB NOT NULL DEFAULT '[]'::jsonb,

    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS canonical_source_links (
    id BIGSERIAL PRIMARY KEY,

    canonical_id TEXT NOT NULL REFERENCES canonical_documents(canonical_id) ON DELETE CASCADE,
    source_observation_id TEXT NOT NULL
        REFERENCES source_documents(source_observation_id) ON DELETE RESTRICT,
    doc_id TEXT NULL,

    source TEXT NOT NULL,
    source_id TEXT,
    source_record_id TEXT,
    source_record_url TEXT,
    canonical_url TEXT,
    fetched_at TIMESTAMPTZ,
    source_updated_at TIMESTAMPTZ,
    source_api_url TEXT,
    raw_source_name TEXT,
    run_ts TIMESTAMPTZ,

    UNIQUE (canonical_id, source_observation_id)
);

CREATE TABLE IF NOT EXISTS document_references (
    id BIGSERIAL PRIMARY KEY,
    canonical_id TEXT NOT NULL REFERENCES canonical_documents(canonical_id) ON DELETE CASCADE,
    reference_type TEXT NOT NULL,
    reference_value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS export_runs (
    id BIGSERIAL PRIMARY KEY,
    run_type TEXT NOT NULL,
    source_path TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);