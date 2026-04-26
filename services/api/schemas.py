from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    backend_mode: str
    ready: bool
    build_id: str
    corpus_doc_count: int
    embedding_model_name: str | None = None
    checks: dict[str, bool] = Field(default_factory=dict)


class ApiInfoResponse(BaseModel):
    api_title: str
    api_version: str
    backend_mode: str
    build_id: str
    corpus_doc_count: int
    embedding_model_name: str | None = None
    artifacts_root: str
    loaded_components: dict[str, bool]


class ReloadResponse(BaseModel):
    status: str
    backend_mode: str
    message: str
    build_id: str
    corpus_doc_count: int
    embedding_model_name: str | None = None
    model_reused: bool = False
    last_reload_at: str | None = None


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: dict[str, Any] | None = None


class SearchFilters(BaseModel):
    year_from: int | None = None
    year_to: int | None = None
    category: str | None = None
    source: str | None = None
    publication_type: str | None = None
    venue: str | None = None
    open_access: bool | None = None
    has_code_link: bool | None = None


class SearchMeta(BaseModel):
    build_id: str
    result_count: int
    rank_applied: bool
    timing_ms: dict[str, float] = Field(default_factory=dict)
    debug_enabled: bool = False
    applied_filters: SearchFilters | None = None
    retrieved_candidates_before_filters: int | None = None
    retrieved_candidates_after_filters: int | None = None
    offset: int = 0
    returned_count: int = 0
    sort_by: str | None = None


class SearchResultDocument(BaseModel):
    canonical_id: str
    title: str
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)

    year: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    openalex_id: str | None = None

    primary_category: str | None = None
    categories: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    venue: str | None = None
    journal: str | None = None
    conference: str | None = None
    publisher: str | None = None
    publication_type: str | None = None
    language: str | None = None

    landing_page_url: str | None = None
    pdf_url: str | None = None
    repo_url: str | None = None

    open_access: bool | None = None
    has_code_link: bool = False
    code_links: list[str] = Field(default_factory=list)

    cited_by_count: int | None = None
    references_count: int | None = None

    source_count: int = 0
    unique_source_count: int = 0

    metadata_completeness_score: float | None = None
    is_preprint: bool | None = None
    is_review: bool = False
    is_survey: bool = False
    is_withdrawn: bool = False


class RetrievalScores(BaseModel):
    score: float | None = None
    lexical_score: float | None = None
    dense_score: float | None = None
    hybrid_score: float | None = None


class RankingScores(BaseModel):
    final_score: float
    retrieval_score: float
    recency_score: float
    source_support_score: float
    metadata_quality_score: float


class SearchResultItem(BaseModel):
    document: SearchResultDocument
    retrieval: RetrievalScores
    ranking: RankingScores | None = None


class SearchResponse(BaseModel):
    query: str
    mode: Literal["lexical", "dense", "hybrid"]
    top_k: int
    rank_applied: bool
    build_id: str
    meta: SearchMeta | None = None
    results: list[SearchResultItem]


class RuntimeSnapshotResponse(BaseModel):
    ready: bool
    backend_mode: str
    build_id: str | None = None
    corpus_doc_count: int = 0
    embedding_model_name: str | None = None
    artifacts_root: str
    loaded_components: dict[str, bool] = Field(default_factory=dict)
    db_connected: bool = False
    last_load_error: str | None = None
    last_loaded_at: str | None = None
    last_reload_at: str | None = None
    model_reused: bool = False
    current_model_name: str | None = None


class DocumentListResponse(BaseModel):
    total: int
    offset: int
    limit: int
    sort_by: str
    results: list[SearchResultDocument]


class ArtifactEntityResponse(BaseModel):
    artifact_id: str
    artifact_type: str
    provider: str

    external_id: str | None = None
    normalized_url: str
    canonical_url: str

    name: str | None = None
    owner: str | None = None
    title: str | None = None
    description: str | None = None
    license: str | None = None

    stars: int | None = None
    forks: int | None = None
    downloads: int | None = None
    likes: int | None = None

    topics: list[Any] = Field(default_factory=list)
    tags: list[Any] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    first_seen_at: str | None = None
    last_seen_at: str | None = None
    fetched_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    linked_papers_count: int | None = None
    relation_types: list[str] = Field(default_factory=list)


class PaperArtifactLinkResponse(BaseModel):
    link_id: str
    canonical_id: str
    artifact_id: str
    relation_type: str
    confidence: float = 0.0

    evidence_source: str | None = None
    evidence_url: str | None = None
    source_field: str | None = None
    source_doc_id: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    artifact: ArtifactEntityResponse


class ArtifactListResponse(BaseModel):
    total: int
    offset: int
    limit: int
    sort_by: str
    results: list[ArtifactEntityResponse]


class DocumentArtifactsResponse(BaseModel):
    canonical_id: str
    total: int
    results: list[PaperArtifactLinkResponse]