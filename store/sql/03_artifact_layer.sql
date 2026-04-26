CREATE TABLE IF NOT EXISTS artifact_entities (
    artifact_id TEXT PRIMARY KEY,
    artifact_type TEXT NOT NULL,
    provider TEXT NOT NULL,
    external_id TEXT,
    normalized_url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    name TEXT,
    owner TEXT,
    title TEXT,
    description TEXT,
    license TEXT,
    stars INTEGER,
    forks INTEGER,
    downloads BIGINT,
    likes INTEGER,
    topics JSONB NOT NULL DEFAULT '[]'::jsonb,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    fetched_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,

    CONSTRAINT artifact_entities_provider_external_id_unique
        UNIQUE (provider, external_id),

    CONSTRAINT artifact_entities_normalized_url_unique
        UNIQUE (normalized_url)
);

CREATE TABLE IF NOT EXISTS artifact_observations (
    observation_id TEXT PRIMARY KEY,
    artifact_id TEXT REFERENCES artifact_entities(artifact_id) ON DELETE SET NULL,
    artifact_type TEXT NOT NULL,
    provider TEXT NOT NULL,
    raw_url TEXT NOT NULL,
    normalized_url TEXT NOT NULL,
    source_layer TEXT NOT NULL,
    source_name TEXT,
    source_doc_id TEXT,
    canonical_id TEXT,
    source_field TEXT,
    evidence_text TEXT,
    relation_type TEXT,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS paper_artifact_links (
    link_id TEXT PRIMARY KEY,
    canonical_id TEXT NOT NULL REFERENCES canonical_documents(canonical_id) ON DELETE CASCADE,
    artifact_id TEXT NOT NULL REFERENCES artifact_entities(artifact_id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    evidence_source TEXT,
    evidence_url TEXT,
    source_field TEXT,
    source_doc_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT paper_artifact_links_unique
        UNIQUE (canonical_id, artifact_id, relation_type, evidence_source, source_field)
);

CREATE INDEX IF NOT EXISTS idx_artifact_entities_type
    ON artifact_entities (artifact_type);

CREATE INDEX IF NOT EXISTS idx_artifact_entities_provider
    ON artifact_entities (provider);

CREATE INDEX IF NOT EXISTS idx_artifact_entities_owner
    ON artifact_entities (owner);

CREATE INDEX IF NOT EXISTS idx_artifact_entities_topics_gin
    ON artifact_entities USING gin (topics);

CREATE INDEX IF NOT EXISTS idx_artifact_entities_tags_gin
    ON artifact_entities USING gin (tags);

CREATE INDEX IF NOT EXISTS idx_artifact_observations_canonical_id
    ON artifact_observations (canonical_id);

CREATE INDEX IF NOT EXISTS idx_artifact_observations_source_doc_id
    ON artifact_observations (source_doc_id);

CREATE INDEX IF NOT EXISTS idx_artifact_observations_provider
    ON artifact_observations (provider);

CREATE INDEX IF NOT EXISTS idx_artifact_observations_type
    ON artifact_observations (artifact_type);

CREATE INDEX IF NOT EXISTS idx_paper_artifact_links_canonical_id
    ON paper_artifact_links (canonical_id);

CREATE INDEX IF NOT EXISTS idx_paper_artifact_links_artifact_id
    ON paper_artifact_links (artifact_id);

CREATE INDEX IF NOT EXISTS idx_paper_artifact_links_relation_type
    ON paper_artifact_links (relation_type);