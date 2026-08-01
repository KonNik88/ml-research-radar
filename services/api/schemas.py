from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


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

class QdrantRuntimeDiagnostics(BaseModel):
    configured: bool = True
    ok: bool = False

    host: str
    port: int
    grpc_port: int
    prefer_grpc: bool
    transport: Literal["rest", "grpc"]
    collection_name: str
    timeout_sec: float
    check_compatibility: bool

    collection_exists: bool = False
    points_count: int | None = None
    expected_corpus_doc_count: int | None = None
    points_match_corpus: bool | None = None

    vector_size: int | None = None
    distance: str | None = None
    status: str | None = None
    optimizer_status: str | None = None
    error: str | None = None

    probe_cached: bool = False
    probe_checked_at: str | None = None
    probe_cache_age_sec: float | None = None
    probe_ttl_sec: float = 0.0

    profile_name: str
    exact: bool = False
    hnsw_ef: int | None = None
    build_id: str | None = None

    backend_created: bool = False
    compatibility_checked: bool = False
    compatibility_ok: bool | None = None

    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0

    last_status: Literal["never", "ok", "error"] = "never"
    last_request_at: str | None = None
    last_success_at: str | None = None
    last_failure_at: str | None = None

    last_failure_category: str | None = None
    last_failure_stage: str | None = None
    last_failure_message: str | None = None

    last_result_count: int | None = None
    last_timing_ms: dict[str, float] = Field(default_factory=dict)

    requested_vector_backend: str | None = None
    effective_vector_backend: str | None = None
    fallback_applied: bool = False

class RuntimeSnapshotResponse(BaseModel):
    ready: bool
    backend_mode: str
    build_id: str | None = None
    corpus_doc_count: int = 0
    embedding_model_name: str | None = None
    artifacts_root: str
    loaded_components: dict[str, bool] = Field(default_factory=dict)
    db_connected: bool = False
    qdrant: QdrantRuntimeDiagnostics | None = None
    last_load_error: str | None = None
    last_loaded_at: str | None = None
    last_reload_at: str | None = None
    model_reused: bool = False
    current_model_name: str | None = None
    service_status: dict[str, Any] = Field(default_factory=dict)


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

class ArtifactDetailResponse(BaseModel):
    artifact_id: str
    found: bool
    artifact: ArtifactEntityResponse


class ArtifactLinkedPaperRow(BaseModel):
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

    paper: SearchResultDocument


class ArtifactLinkedPapersResponse(BaseModel):
    artifact_id: str
    total: int
    offset: int
    limit: int
    sort_by: str
    results: list[ArtifactLinkedPaperRow]

class DiscoveryProfile(BaseModel):
    name: str
    description: str
    sort_by: str
    top_k: int
    descending: bool = True
    filters: dict[str, Any] = Field(default_factory=dict)


class DiscoveryProfilesResponse(BaseModel):
    schema_version: str
    default_profile: str | None = None
    profile_count: int
    profiles: list[DiscoveryProfile]


class DiscoveryRankingResponse(BaseModel):
    mode: str
    profile: dict[str, Any]
    sort_by: str
    descending: bool
    top_k: int
    input_rows_count: int
    filtered_rows_count: int
    returned_rows_count: int
    filters: dict[str, Any] = Field(default_factory=dict)
    features_path: str | None = None
    results: list[dict[str, Any]] = Field(default_factory=list)


class DiscoveryPaperDetailResponse(BaseModel):
    canonical_id: str
    found: bool
    detail: dict[str, Any]
    inputs: dict[str, Any] = Field(default_factory=dict)


class DiscoverySimilarPapersResponse(BaseModel):
    mode: str
    target_canonical_id: str
    target_found: bool
    target: dict[str, Any]
    rank_by: str
    top_k: int
    min_similarity: float | None = None
    input_rows_count: int
    returned_rows_count: int
    dense_artifacts: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)
    results: list[dict[str, Any]] = Field(default_factory=list)


class DiscoveryPaperComparisonRequest(BaseModel):
    canonical_ids: list[str] = Field(min_length=2, max_length=5)

    @field_validator("canonical_ids")
    @classmethod
    def validate_canonical_ids(cls, values: list[str]) -> list[str]:
        normalized = [str(value).strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("canonical_ids must be non-empty")
        if any(len(value) > 256 for value in normalized):
            raise ValueError("canonical_ids must be at most 256 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("canonical_ids must be unique")
        return normalized


class DiscoveryPaperComparisonResponse(BaseModel):
    schema_version: Literal["paper_comparison_v0.1"]
    mode: Literal["paper_comparison"]
    canonical_ids: list[str]
    paper_count: int
    input_order_preserved: bool
    papers: list[dict[str, Any]] = Field(default_factory=list)
    pairwise: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class DiscoveryTopicClusterSummary(BaseModel):
    cluster_id: int
    size: int
    label_candidates: list[str] = Field(default_factory=list)

    artifact_ready_count: int = 0
    code_artifact_count: int = 0
    dataset_artifact_count: int = 0
    model_artifact_count: int = 0
    demo_artifact_count: int = 0
    github_found_paper_count: int = 0
    hf_found_paper_count: int = 0

    mean_radar_score: float | None = None
    mean_implementation_readiness_score: float | None = None
    mean_source_confidence_score: float | None = None
    mean_citation_signal_score: float | None = None

    top_title_terms: list[list[Any]] = Field(default_factory=list)
    top_title_trigrams: list[list[Any]] = Field(default_factory=list)
    top_abstract_bigrams: list[list[Any]] = Field(default_factory=list)
    top_abstract_trigrams: list[list[Any]] = Field(default_factory=list)
    top_categories: list[list[Any]] = Field(default_factory=list)
    top_concepts: list[list[Any]] = Field(default_factory=list)
    top_keywords: list[list[Any]] = Field(default_factory=list)
    top_source_families: list[list[Any]] = Field(default_factory=list)

    representative_papers: list[dict[str, Any]] = Field(default_factory=list)


class DiscoveryTopicClustersResponse(BaseModel):
    mode: str
    cluster_build_id: str
    retrieval_build_id: str
    cluster_config_hash: str | None = None

    algorithm: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    embedding_model: str | None = None
    embedding_shape: list[int] = Field(default_factory=list)

    cluster_count: int
    total: int
    offset: int
    limit: int
    returned_count: int
    sort_by: str

    inputs: dict[str, Any] = Field(default_factory=dict)
    results: list[DiscoveryTopicClusterSummary] = Field(default_factory=list)


class DiscoveryTopicClusterDetailResponse(BaseModel):
    mode: str
    cluster_id: int
    found: bool

    cluster_build_id: str | None = None
    retrieval_build_id: str | None = None
    cluster_config_hash: str | None = None

    summary: dict[str, Any] = Field(default_factory=dict)
    total_papers: int = 0
    returned_papers_count: int = 0
    top_k: int
    sort_by: str

    inputs: dict[str, Any] = Field(default_factory=dict)
    papers: list[dict[str, Any]] = Field(default_factory=list)

    filtered_papers_count: int = 0
    filters: dict[str, Any] = Field(default_factory=dict)


class DiscoveryPaperTopicClusterResponse(BaseModel):
    mode: str
    canonical_id: str
    found: bool

    cluster_build_id: str | None = None
    retrieval_build_id: str | None = None
    cluster_config_hash: str | None = None

    assignment: dict[str, Any] | None = None
    cluster: dict[str, Any] | None = None

    inputs: dict[str, Any] = Field(default_factory=dict)

class DiscoveryTopicClusterMapPoint(BaseModel):
    point_id: str | None = None
    point_type: str
    cluster_id: int

    x: float
    y: float

    canonical_id: str | None = None
    title: str | None = None
    year: int | None = None

    label_candidates: list[str] = Field(default_factory=list)

    size: int | None = None
    radar_score: float | None = None
    implementation_readiness_score: float | None = None
    artifact_ready_count: int | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


class DiscoveryTopicClusterMapResponse(BaseModel):
    mode: str

    projection_build_id: str
    cluster_build_id: str
    retrieval_build_id: str
    cluster_config_hash: str | None = None

    projection_algorithm: str | None = None
    point_count: int = 0
    centroid_count: int = 0
    representative_count: int = 0
    sampled_count: int = 0

    total_points_count: int = 0
    returned_points_count: int = 0
    include_papers: bool = False
    max_points: int

    inputs: dict[str, Any] = Field(default_factory=dict)
    points: list[DiscoveryTopicClusterMapPoint] = Field(default_factory=list)

class QdrantSearchMeta(BaseModel):
    build_id: str
    collection_name: str
    result_count: int
    timing_ms: dict[str, float] = Field(default_factory=dict)
    vector_backend: str = "qdrant"
    source_backend: str = "file_runtime"


class QdrantSearchResultItem(BaseModel):
    rank: int
    document: SearchResultDocument
    retrieval: RetrievalScores
    point_id: int | str | None = None
    dense_index: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class QdrantSearchResponse(BaseModel):
    query: str
    mode: Literal["dense_qdrant"] = "dense_qdrant"
    top_k: int
    build_id: str
    collection_name: str
    meta: QdrantSearchMeta
    results: list[QdrantSearchResultItem]


class CitationGraphStatusGraph(BaseModel):
    name: str = "citation_reference_graph"
    version: str = "v0.1"
    runtime_enabled: bool = False
    available: bool = False
    exposure_mode: str = "local_inspection"
    graph_root: str | None = None
    reports_root: str | None = None

    metadata_reference_fields_only: bool = True
    full_text_parsed: bool = False
    pdfs_parsed: bool = False
    bibliography_sections_parsed: bool = False

    manual_review_required: bool = True
    manual_review_complete: bool = False
    publication_ready: bool = False
    may_be_used_as_reconcile_input: bool = False
    not_a_complete_citation_index: bool = True


class CitationGraphStatusResponse(BaseModel):
    graph: CitationGraphStatusGraph
    query: dict[str, Any] = Field(default_factory=dict)
    items: list[Any] = Field(default_factory=list)
    page: dict[str, Any] = Field(default_factory=dict)
    caveats: list[str] = Field(default_factory=list)
    availability: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    reports: dict[str, Any] = Field(default_factory=dict)
    compatibility: dict[str, Any] = Field(default_factory=dict)
    counts: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    message: str | None = None


class CitationGraphTraversalResponse(BaseModel):
    graph: dict[str, Any] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    items: list[dict[str, Any]] = Field(default_factory=list)
    page: dict[str, Any] = Field(default_factory=dict)
    caveats: list[str] = Field(default_factory=list)
