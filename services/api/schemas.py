from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    build_id: str
    corpus_doc_count: int
    embedding_model_name: str | None = None
    corpus_path: str


class ApiInfoResponse(BaseModel):
    api_title: str
    api_version: str
    build_id: str
    corpus_doc_count: int
    embedding_model_name: str | None = None
    artifacts_root: str
    loaded_components: dict[str, bool]


class ReloadResponse(BaseModel):
    status: str
    build_id: str
    corpus_doc_count: int
    embedding_model_name: str | None = None
    model_reused: bool
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

    # richer filters for the expanded corpus
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
    backend_mode: str | None = None
    build_id: str | None = None
    corpus_doc_count: int = 0
    embedding_model_name: str | None = None
    artifacts_root: str
    loaded_components: dict[str, bool]
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