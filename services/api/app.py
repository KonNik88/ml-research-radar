from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from radar_core.ranking.profiles import RankingProfileError
from services.api.discovery_service import get_discovery_service
from services.api.logging import get_logger
from services.api.runtime import get_runtime
from services.api.schemas import (
    ApiInfoResponse,
    ArtifactListResponse,
    DiscoveryPaperDetailResponse,
    DiscoveryPaperTopicClusterResponse,
    DiscoveryProfilesResponse,
    DiscoveryRankingResponse,
    DiscoverySimilarPapersResponse,
    DiscoveryTopicClusterDetailResponse,
    DiscoveryTopicClusterMapResponse,
    DiscoveryTopicClustersResponse,
    DocumentArtifactsResponse,
    DocumentListResponse,
    ErrorResponse,
    HealthResponse,
    ReloadResponse,
    RuntimeSnapshotResponse,
    SearchResponse,
    ArtifactDetailResponse,
    ArtifactLinkedPapersResponse,
    QdrantSearchResponse,
)
from services.api.search_service import (
    db_row_to_schema,
    run_qdrant_experimental_search,
    run_search,
)
from services.api.settings import get_settings

DiscoveryRankingSortBy = Literal[
    "radar_score",
    "implementation_readiness_score",
    "source_confidence_score",
    "citation_signal_score",
    "recency_score",
    "year",
    "github_stars_max",
    "github_stars_sum",
    "github_forks_max",
    "github_forks_sum",
    "trusted_artifact_links_count",
    "trusted_code_links_count",
    "trusted_dataset_links_count",
    "trusted_model_links_count",
    "trusted_demo_links_count",
    "hf_downloads_max",
    "hf_likes_max",
]

DiscoveryClusterSortBy = Literal[
    "size_desc",
    "cluster_id_asc",
    "mean_radar_desc",
    "artifact_ready_desc",
]

DiscoveryClusterPaperSortBy = Literal[
    "rank",
    "similarity_desc",
    "radar_score",
    "implementation_readiness_score",
    "citation_signal_score",
    "year_desc",
]

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = get_runtime()
    runtime.load()
    yield


settings = get_settings()

app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    lifespan=lifespan,
)


@app.exception_handler(ValueError)
async def handle_value_error(_: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(
            error_code="bad_request",
            message=str(exc),
            details=None,
        ).model_dump(),
    )


@app.exception_handler(FileNotFoundError)
async def handle_file_not_found(_: Request, exc: FileNotFoundError):
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error_code="file_not_found",
            message=str(exc),
            details=None,
        ).model_dump(),
    )


@app.exception_handler(RuntimeError)
async def handle_runtime_error(_: Request, exc: RuntimeError):
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(
            error_code="runtime_not_ready",
            message=str(exc),
            details=None,
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error_code="validation_error",
            message="Request validation failed",
            details={"errors": exc.errors()},
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def handle_generic_error(_: Request, exc: Exception):
    logger.exception("Unhandled API error")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error_code="internal_error",
            message="Internal server error",
            details={"type": type(exc).__name__},
        ).model_dump(),
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    runtime = get_runtime()
    snapshot = runtime.runtime_snapshot()

    if not snapshot["ready"]:
        raise RuntimeError("Runtime is not ready")

    checks = {
        "manifest_loaded": snapshot["loaded_components"].get("manifest", False),
        "documents_loaded": snapshot["loaded_components"].get("documents", False),
        "lexical_artifacts_loaded": snapshot["loaded_components"].get("lexical_artifacts", False),
        "dense_artifacts_loaded": snapshot["loaded_components"].get("dense_artifacts", False),
        "embedding_model_loaded": snapshot["loaded_components"].get("embedding_model", False),
        "db_store_loaded": snapshot["loaded_components"].get("db_store", False),
        "db_connected": snapshot.get("db_connected", False),
    }

    return HealthResponse(
        status="ok",
        backend_mode=snapshot["backend_mode"],
        ready=snapshot["ready"],
        build_id=snapshot["build_id"] or "unknown",
        corpus_doc_count=snapshot["corpus_doc_count"],
        embedding_model_name=snapshot["embedding_model_name"],
        checks=checks,
    )


@app.get("/info", response_model=ApiInfoResponse)
def info() -> ApiInfoResponse:
    runtime = get_runtime()
    snapshot = runtime.runtime_snapshot()

    return ApiInfoResponse(
        api_title=settings.api_title,
        api_version=settings.api_version,
        backend_mode=snapshot["backend_mode"],
        build_id=snapshot["build_id"] or "unknown",
        corpus_doc_count=snapshot["corpus_doc_count"],
        embedding_model_name=snapshot["embedding_model_name"],
        artifacts_root=snapshot["artifacts_root"],
        loaded_components=snapshot["loaded_components"],
    )


@app.get("/runtime", response_model=RuntimeSnapshotResponse)
def runtime_snapshot() -> RuntimeSnapshotResponse:
    runtime = get_runtime()
    return RuntimeSnapshotResponse(**runtime.runtime_snapshot(include_qdrant=True))


@app.post("/reload", response_model=ReloadResponse)
def reload_runtime() -> ReloadResponse:
    if not settings.enable_reload_endpoint:
        raise HTTPException(status_code=404, detail="Reload endpoint is disabled")

    runtime = get_runtime()
    runtime.reload()

    discovery_service = get_discovery_service()
    discovery_service.reload()

    snapshot = runtime.runtime_snapshot()

    message = (
        "DB backend runtime and Discovery caches reloaded successfully"
        if snapshot["backend_mode"] == "db"
        else "File backend runtime and Discovery caches reloaded successfully"
    )

    return ReloadResponse(
        status="reloaded",
        backend_mode=snapshot["backend_mode"],
        message=message,
        build_id=snapshot["build_id"] or "unknown",
        corpus_doc_count=snapshot["corpus_doc_count"],
        embedding_model_name=snapshot["embedding_model_name"],
        model_reused=snapshot["model_reused"],
        last_reload_at=snapshot["last_reload_at"],
    )


@app.get("/search", response_model=SearchResponse)
def search(
    query: str = Query(..., min_length=1, description="Search query"),
    mode: Literal["lexical", "dense", "hybrid"] = Query("hybrid"),
    top_k: int | None = Query(None, ge=1),
    rank: bool = Query(False),
    year_from: int | None = Query(None, ge=1900, le=2100),
    year_to: int | None = Query(None, ge=1900, le=2100),
    category: str | None = Query(None, description="Category, concept, keyword or tag filter"),
    source: str | None = Query(None, description="Source filter, e.g. arxiv/openalex"),
    publication_type: str | None = Query(None, description="Publication type filter, e.g. article/preprint"),
    venue: str | None = Query(None, description="Venue/journal/conference/publisher filter"),
    open_access: bool | None = Query(None, description="Open access filter"),
    has_code_link: bool | None = Query(None, description="Filter by presence of legacy canonical code link"),
    offset: int = Query(0, ge=0),
    sort_by: Literal["relevance", "year_desc", "year_asc"] = Query("relevance"),
) -> SearchResponse:
    runtime = get_runtime()
    if not runtime.is_ready():
        raise RuntimeError("Runtime is not ready")

    resolved_top_k = top_k if top_k is not None else settings.default_top_k
    if resolved_top_k > settings.max_top_k:
        raise ValueError(
            f"top_k={resolved_top_k} exceeds max_top_k={settings.max_top_k}"
        )

    if year_from is not None and year_to is not None and year_from > year_to:
        raise ValueError("year_from must be less than or equal to year_to")

    return run_search(
        runtime=runtime,
        query=query,
        mode=mode,
        top_k=resolved_top_k,
        rank=rank,
        year_from=year_from,
        year_to=year_to,
        category=category,
        source=source,
        publication_type=publication_type,
        venue=venue,
        open_access=open_access,
        has_code_link=has_code_link,
        offset=offset,
        sort_by=sort_by,
    )

@app.get("/experimental/search/qdrant", response_model=QdrantSearchResponse)
def experimental_qdrant_search(
    query: str = Query(..., min_length=1, description="Search query"),
    top_k: int | None = Query(None, ge=1),
) -> QdrantSearchResponse:
    runtime = get_runtime()
    if not runtime.is_ready():
        raise RuntimeError("Runtime is not ready")

    if runtime.backend_mode != "file":
        raise RuntimeError("Experimental Qdrant search requires file backend runtime")

    resolved_top_k = top_k if top_k is not None else settings.default_top_k
    if resolved_top_k > settings.max_top_k:
        raise ValueError(
            f"top_k={resolved_top_k} exceeds max_top_k={settings.max_top_k}"
        )

    return run_qdrant_experimental_search(
        runtime=runtime,
        query=query,
        top_k=resolved_top_k,
    )

@app.get("/documents", response_model=DocumentListResponse)
def list_documents(
    query: str | None = Query(None, description="Simple text query over title/abstract/venue/publisher"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    year_from: int | None = Query(None, ge=1900, le=2100),
    year_to: int | None = Query(None, ge=1900, le=2100),
    category: str | None = Query(None),
    source: str | None = Query(None),
    publication_type: str | None = Query(None),
    venue: str | None = Query(None),
    open_access: bool | None = Query(None),
    has_code_link: bool | None = Query(
        None,
        description="Legacy canonical/source-layer code link flag. Does not use artifact layer.",
    ),
    has_trusted_artifact: bool | None = Query(
        None,
        description="Filter by any trusted paper-artifact link.",
    ),
    has_trusted_code_artifact: bool | None = Query(
        None,
        description="Filter by trusted code artifact link.",
    ),
    has_trusted_dataset_artifact: bool | None = Query(
        None,
        description="Filter by trusted dataset artifact link.",
    ),
    has_trusted_model_artifact: bool | None = Query(
        None,
        description="Filter by trusted model artifact link.",
    ),
    has_trusted_demo_artifact: bool | None = Query(
        None,
        description="Filter by trusted demo/video/project artifact link.",
    ),
    artifact_provider: str | None = Query(
        None,
        description="Filter documents by trusted artifact provider, e.g. github/figshare/zenodo.",
    ),
    artifact_type: str | None = Query(
        None,
        description="Filter documents by trusted artifact type, e.g. github_repository.",
    ),
    sort_by: Literal["year_desc", "year_asc", "title_asc"] = Query("year_desc"),
) -> DocumentListResponse:
    runtime = get_runtime()
    if not runtime.is_ready():
        raise RuntimeError("Runtime is not ready")

    if runtime.db_store is None:
        raise RuntimeError("DB backend is not enabled")

    if year_from is not None and year_to is not None and year_from > year_to:
        raise ValueError("year_from must be less than or equal to year_to")

    rows = runtime.db_store.search_documents(
        query_text=query,
        year_from=year_from,
        year_to=year_to,
        category=category,
        source=source,
        publication_type=publication_type,
        venue=venue,
        is_open_access=open_access,
        has_code_link=has_code_link,
        has_trusted_artifact=has_trusted_artifact,
        has_trusted_code_artifact=has_trusted_code_artifact,
        has_trusted_dataset_artifact=has_trusted_dataset_artifact,
        has_trusted_model_artifact=has_trusted_model_artifact,
        has_trusted_demo_artifact=has_trusted_demo_artifact,
        artifact_provider=artifact_provider,
        artifact_type=artifact_type,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
    )

    total = runtime.db_store.count_documents(
        query_text=query,
        year_from=year_from,
        year_to=year_to,
        category=category,
        source=source,
        publication_type=publication_type,
        venue=venue,
        is_open_access=open_access,
        has_code_link=has_code_link,
        has_trusted_artifact=has_trusted_artifact,
        has_trusted_code_artifact=has_trusted_code_artifact,
        has_trusted_dataset_artifact=has_trusted_dataset_artifact,
        has_trusted_model_artifact=has_trusted_model_artifact,
        has_trusted_demo_artifact=has_trusted_demo_artifact,
        artifact_provider=artifact_provider,
        artifact_type=artifact_type,
    )

    return DocumentListResponse(
        total=total,
        offset=offset,
        limit=limit,
        sort_by=sort_by,
        results=[db_row_to_schema(row) for row in rows],
    )


@app.get("/artifacts", response_model=ArtifactListResponse)
def list_artifacts(
    provider: str | None = Query(None, description="Artifact provider, e.g. github/figshare/zenodo"),
    artifact_type: str | None = Query(None, description="Artifact type, e.g. github_repository"),
    relation_type: str | None = Query(None, description="Trusted paper-artifact relation, e.g. code/dataset/model/demo"),
    owner: str | None = Query(None, description="Artifact owner/namespace when available"),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    has_paper_links: bool | None = Query(None, description="Filter artifacts by trusted paper links presence"),
    min_stars: int | None = Query(None, ge=0, description="Minimum GitHub stars. Rows with NULL stars do not match."),
    max_stars: int | None = Query(None, ge=0, description="Maximum GitHub stars. Rows with NULL stars do not match."),
    language: str | None = Query(None, description="GitHub repository language, case-insensitive, e.g. Python"),
    license: str | None = Query(None, description="Artifact/GitHub license, case-insensitive, e.g. mit/gpl-3.0"),
    archived: bool | None = Query(
        None,
        description="GitHub archived flag. Only rows with explicit metadata.github.archived match.",
    ),
    github_status: Literal[
        "found",
        "not_found",
        "forbidden",
        "rate_limited",
        "error",
        "skipped_invalid_external_id",
    ] | None = Query(None, description="GitHub enrichment status filter"),
    has_github_metadata: bool | None = Query(
        None,
        description="Filter by presence of metadata.github. Use with provider=github for diagnostics.",
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort_by: Literal[
        "linked_papers_desc",
        "provider_asc",
        "type_asc",
        "owner_asc",
        "last_seen_desc",
        "stars_desc",
        "forks_desc",
    ] = Query("linked_papers_desc"),
) -> ArtifactListResponse:
    runtime = get_runtime()
    if not runtime.is_ready():
        raise RuntimeError("Runtime is not ready")

    if runtime.db_store is None:
        raise RuntimeError("DB backend is not enabled")

    if min_stars is not None and max_stars is not None and min_stars > max_stars:
        raise ValueError("min_stars must be less than or equal to max_stars")

    rows = runtime.db_store.list_artifacts(
        provider=provider,
        artifact_type=artifact_type,
        relation_type=relation_type,
        owner=owner,
        min_confidence=min_confidence,
        has_paper_links=has_paper_links,
        min_stars=min_stars,
        max_stars=max_stars,
        language=language,
        license=license,
        archived=archived,
        github_status=github_status,
        has_github_metadata=has_github_metadata,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
    )

    total = runtime.db_store.count_artifacts(
        provider=provider,
        artifact_type=artifact_type,
        relation_type=relation_type,
        owner=owner,
        min_confidence=min_confidence,
        has_paper_links=has_paper_links,
        min_stars=min_stars,
        max_stars=max_stars,
        language=language,
        license=license,
        archived=archived,
        github_status=github_status,
        has_github_metadata=has_github_metadata,
    )

    return ArtifactListResponse(
        total=total,
        offset=offset,
        limit=limit,
        sort_by=sort_by,
        results=rows,
    )

@app.get("/artifacts/{artifact_id}", response_model=ArtifactDetailResponse)
def get_artifact_detail(
    artifact_id: str,
) -> ArtifactDetailResponse:
    runtime = get_runtime()
    if not runtime.is_ready():
        raise RuntimeError("Runtime is not ready")

    if runtime.db_store is None:
        raise RuntimeError("DB backend is not enabled")

    artifact = runtime.db_store.get_artifact_by_id(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_id}")

    return ArtifactDetailResponse(
        artifact_id=artifact_id,
        found=True,
        artifact=artifact,
    )

@app.get("/artifacts/{artifact_id}/papers", response_model=ArtifactLinkedPapersResponse)
def get_artifact_papers(
    artifact_id: str,
    relation_type: str | None = Query(None, description="Trusted relation filter, e.g. code/dataset/model/demo"),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort_by: Literal["confidence_desc", "year_desc", "title_asc"] = Query("confidence_desc"),
) -> ArtifactLinkedPapersResponse:
    runtime = get_runtime()
    if not runtime.is_ready():
        raise RuntimeError("Runtime is not ready")

    if runtime.db_store is None:
        raise RuntimeError("DB backend is not enabled")

    artifact = runtime.db_store.get_artifact_by_id(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_id}")

    rows = runtime.db_store.list_artifact_papers(
        artifact_id=artifact_id,
        relation_type=relation_type,
        min_confidence=min_confidence,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
    )

    total = runtime.db_store.count_artifact_papers(
        artifact_id=artifact_id,
        relation_type=relation_type,
        min_confidence=min_confidence,
    )

    return ArtifactLinkedPapersResponse(
        artifact_id=artifact_id,
        total=total,
        offset=offset,
        limit=limit,
        sort_by=sort_by,
        results=[
            {
                **row,
                "paper": db_row_to_schema(row["paper"]),
            }
            for row in rows
        ],
    )

@app.get("/documents/{canonical_id}/artifacts", response_model=DocumentArtifactsResponse)
def get_document_artifacts(
    canonical_id: str,
    relation_type: str | None = Query(None, description="Trusted relation filter, e.g. code/dataset/model/demo"),
    provider: str | None = Query(None, description="Artifact provider filter"),
    artifact_type: str | None = Query(None, description="Artifact type filter"),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> DocumentArtifactsResponse:
    runtime = get_runtime()
    if not runtime.is_ready():
        raise RuntimeError("Runtime is not ready")

    if runtime.db_store is None:
        raise RuntimeError("DB backend is not enabled")

    document = runtime.db_store.get_document_by_id(canonical_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {canonical_id}")

    rows = runtime.db_store.get_document_artifacts(
        canonical_id=canonical_id,
        relation_type=relation_type,
        provider=provider,
        artifact_type=artifact_type,
        min_confidence=min_confidence,
        limit=limit,
        offset=offset,
    )

    total = runtime.db_store.count_document_artifacts(
        canonical_id=canonical_id,
        relation_type=relation_type,
        provider=provider,
        artifact_type=artifact_type,
        min_confidence=min_confidence,
    )

    return DocumentArtifactsResponse(
        canonical_id=canonical_id,
        total=total,
        results=rows,
    )


@app.get("/discovery/profiles", response_model=DiscoveryProfilesResponse)
def discovery_profiles() -> DiscoveryProfilesResponse:
    service = get_discovery_service()
    return DiscoveryProfilesResponse(**service.list_profiles())


@app.get("/discovery/ranking/{profile_name}", response_model=DiscoveryRankingResponse)
def discovery_ranking(
    profile_name: str,
    top_k: int | None = Query(None, ge=1, le=settings.max_top_k),
    query_title: str | None = Query(None, min_length=1, max_length=settings.max_query_length),
    source_family: str | None = Query(None, min_length=1, max_length=100),
    min_year: int | None = Query(None, ge=1900, le=2100),
    max_year: int | None = Query(None, ge=1900, le=2100),
    has_code: bool | None = Query(None),
    has_dataset: bool | None = Query(None),
    has_model: bool | None = Query(None),
    has_demo: bool | None = Query(None),
    has_github: bool | None = Query(None),
    has_hf: bool | None = Query(None),
    has_acl: bool | None = Query(None),
    has_doi: bool | None = Query(None),
    sort_by: DiscoveryRankingSortBy | None = Query(None),
    descending: bool | None = Query(None),
) -> DiscoveryRankingResponse:
    if min_year is not None and max_year is not None and min_year > max_year:
        raise ValueError("min_year must be less than or equal to max_year")

    service = get_discovery_service()

    try:
        payload = service.get_ranking(
            profile_name=profile_name,
            top_k=top_k,
            query_title=query_title,
            source_family=source_family,
            min_year=min_year,
            max_year=max_year,
            has_code=has_code,
            has_dataset=has_dataset,
            has_model=has_model,
            has_demo=has_demo,
            has_github=has_github,
            has_hf=has_hf,
            has_acl=has_acl,
            has_doi=has_doi,
            sort_by=sort_by,
            descending=descending,
        )
    except RankingProfileError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return DiscoveryRankingResponse(**payload)


@app.get("/discovery/clusters", response_model=DiscoveryTopicClustersResponse)
def discovery_topic_clusters(
    limit: int = Query(20, ge=1, le=settings.max_top_k),
    offset: int = Query(0, ge=0),
    sort_by: DiscoveryClusterSortBy = Query("size_desc"),
    include_representatives: bool = Query(True),
    min_size: int | None = Query(None, ge=1),
) -> DiscoveryTopicClustersResponse:
    service = get_discovery_service()
    payload = service.get_topic_clusters(
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        include_representatives=include_representatives,
        min_size=min_size,
    )
    return DiscoveryTopicClustersResponse(**payload)

@app.get("/discovery/clusters/map", response_model=DiscoveryTopicClusterMapResponse)
def discovery_topic_cluster_map(
    include_papers: bool = Query(False),
    max_points: int = Query(5000, ge=1, le=10000),
) -> DiscoveryTopicClusterMapResponse:
    service = get_discovery_service()
    payload = service.get_topic_cluster_map(
        include_papers=include_papers,
        max_points=max_points,
    )
    return DiscoveryTopicClusterMapResponse(**payload)

@app.get("/discovery/clusters/{cluster_id}", response_model=DiscoveryTopicClusterDetailResponse)
def discovery_topic_cluster_detail(
    cluster_id: int,
    top_k: int = Query(20, ge=1, le=settings.max_top_k),
    sort_by: DiscoveryClusterPaperSortBy = Query("rank"),
    min_year: int | None = Query(None, ge=1900, le=2100),
    max_year: int | None = Query(None, ge=1900, le=2100),
    has_code: bool | None = Query(None),
    has_dataset: bool | None = Query(None),
    has_model: bool | None = Query(None),
    has_demo: bool | None = Query(None),
    has_github: bool | None = Query(None),
    has_hf: bool | None = Query(None),
    has_acl: bool | None = Query(None),
    has_doi: bool | None = Query(None),
    min_radar_score: float | None = Query(None, ge=0.0, le=1.0),
    min_implementation_readiness_score: float | None = Query(None, ge=0.0, le=1.0),
    min_citation_signal_score: float | None = Query(None, ge=0.0, le=1.0),
) -> DiscoveryTopicClusterDetailResponse:
    if min_year is not None and max_year is not None and min_year > max_year:
        raise ValueError("min_year must be less than or equal to max_year")
    service = get_discovery_service()
    payload = service.get_topic_cluster(
        cluster_id=cluster_id,
        top_k=top_k,
        sort_by=sort_by,
        min_year=min_year,
        max_year=max_year,
        has_code=has_code,
        has_dataset=has_dataset,
        has_model=has_model,
        has_demo=has_demo,
        has_github=has_github,
        has_hf=has_hf,
        has_acl=has_acl,
        has_doi=has_doi,
        min_radar_score=min_radar_score,
        min_implementation_readiness_score=min_implementation_readiness_score,
        min_citation_signal_score=min_citation_signal_score,
    )

    if not payload["found"]:
        raise HTTPException(status_code=404, detail=f"Topic cluster not found: {cluster_id}")

    return DiscoveryTopicClusterDetailResponse(**payload)


@app.get("/discovery/papers/{canonical_id}", response_model=DiscoveryPaperDetailResponse)
def discovery_paper_detail(
    canonical_id: str,
    view: Literal["full"] = Query("full"),
) -> DiscoveryPaperDetailResponse:
    service = get_discovery_service()
    payload = service.get_paper_detail(canonical_id=canonical_id, view=view)

    if not payload["found"]:
        raise HTTPException(
            status_code=404,
            detail=f"Paper not found: {canonical_id}",
        )

    return DiscoveryPaperDetailResponse(**payload)


@app.get(
    "/discovery/papers/{canonical_id}/similar",
    response_model=DiscoverySimilarPapersResponse,
)
def discovery_similar_papers(
    canonical_id: str,
    top_k: int = Query(20, ge=1),
    rank_by: Literal["semantic", "radar_adjusted"] = Query("semantic"),
    min_similarity: float | None = Query(None, ge=-1.0, le=1.0),
) -> DiscoverySimilarPapersResponse:
    if top_k > settings.max_top_k:
        raise ValueError(f"top_k={top_k} exceeds max_top_k={settings.max_top_k}")

    service = get_discovery_service()

    try:
        payload = service.get_similar_papers(
            canonical_id=canonical_id,
            top_k=top_k,
            rank_by=rank_by,
            min_similarity=min_similarity,
        )
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise

    return DiscoverySimilarPapersResponse(**payload)


@app.get(
    "/discovery/papers/{canonical_id}/cluster",
    response_model=DiscoveryPaperTopicClusterResponse,
)
def discovery_paper_topic_cluster(
    canonical_id: str,
) -> DiscoveryPaperTopicClusterResponse:
    service = get_discovery_service()
    payload = service.get_paper_topic_cluster(canonical_id=canonical_id)

    if not payload["found"]:
        raise HTTPException(
            status_code=404,
            detail=f"Topic cluster assignment not found for paper: {canonical_id}",
        )

    return DiscoveryPaperTopicClusterResponse(**payload)