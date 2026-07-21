CREATE INDEX IF NOT EXISTS idx_canonical_documents_doi
    ON canonical_documents (doi);

CREATE INDEX IF NOT EXISTS idx_canonical_documents_arxiv_id
    ON canonical_documents (arxiv_id);

CREATE INDEX IF NOT EXISTS idx_canonical_documents_openalex_id
    ON canonical_documents (openalex_id);

CREATE INDEX IF NOT EXISTS idx_canonical_documents_year
    ON canonical_documents (year);

CREATE INDEX IF NOT EXISTS idx_canonical_documents_publication_type
    ON canonical_documents (publication_type);

CREATE INDEX IF NOT EXISTS idx_canonical_documents_venue
    ON canonical_documents (venue);

CREATE INDEX IF NOT EXISTS idx_canonical_documents_publisher
    ON canonical_documents (publisher);

CREATE INDEX IF NOT EXISTS idx_canonical_documents_is_open_access
    ON canonical_documents (is_open_access);

CREATE INDEX IF NOT EXISTS idx_canonical_documents_is_preprint
    ON canonical_documents (is_preprint);

CREATE INDEX IF NOT EXISTS idx_canonical_documents_title_trgm
    ON canonical_documents USING gin (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_canonical_documents_external_ids_gin
    ON canonical_documents USING gin (external_ids);

CREATE INDEX IF NOT EXISTS idx_canonical_documents_categories_gin
    ON canonical_documents USING gin (categories);

CREATE INDEX IF NOT EXISTS idx_canonical_documents_tags_gin
    ON canonical_documents USING gin (tags);


CREATE INDEX IF NOT EXISTS idx_source_documents_source
    ON source_documents (source);

CREATE INDEX IF NOT EXISTS idx_source_documents_doc_id
    ON source_documents (doc_id);

CREATE INDEX IF NOT EXISTS idx_source_documents_source_record_id
    ON source_documents (source, source_record_id);

CREATE INDEX IF NOT EXISTS idx_source_documents_doi
    ON source_documents (doi);

CREATE INDEX IF NOT EXISTS idx_source_documents_arxiv_id
    ON source_documents (arxiv_id);

CREATE INDEX IF NOT EXISTS idx_source_documents_openalex_id
    ON source_documents (openalex_id);

CREATE INDEX IF NOT EXISTS idx_source_documents_content_hash
    ON source_documents (content_hash);

CREATE INDEX IF NOT EXISTS idx_source_documents_title_trgm
    ON source_documents USING gin (title gin_trgm_ops);


CREATE INDEX IF NOT EXISTS idx_canonical_source_links_canonical_id
    ON canonical_source_links (canonical_id);

CREATE INDEX IF NOT EXISTS idx_canonical_source_links_source_observation_id
    ON canonical_source_links (source_observation_id);

-- Legacy diagnostic lookup only; doc_id is no longer a foreign-key identity.
CREATE INDEX IF NOT EXISTS idx_canonical_source_links_doc_id
    ON canonical_source_links (doc_id);

CREATE INDEX IF NOT EXISTS idx_canonical_source_links_source
    ON canonical_source_links (source);


CREATE INDEX IF NOT EXISTS idx_document_references_canonical_id
    ON document_references (canonical_id);

CREATE INDEX IF NOT EXISTS idx_document_references_type_value
    ON document_references (reference_type, reference_value);

CREATE INDEX IF NOT EXISTS idx_source_documents_source_record_url
    ON source_documents (source, source_record_url)
    WHERE source_record_url IS NOT NULL;