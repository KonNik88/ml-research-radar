from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from radar_core.ranking.profiles import RankingProfileError
from radar_core.retrieval.dense_backend import (
    DenseBackendCompatibilityError,
    DenseBackendRequestError,
    DenseBackendResultError,
    DenseBackendUnavailableError,
)
from services.api.citation_graph_service import (
    DEFAULT_CITATION_GRAPH_CAVEATS,
    build_citation_graph_status,
)
from services.api.citation_graph_store import CitationGraphStore
from services.api.discovery_service import (
    PaperComparisonPaperNotFoundError,
    get_discovery_service,
)
from services.api.logging import get_logger
from services.api.runtime import get_runtime
from services.api.schemas import (
    ApiInfoResponse,
    ArtifactListResponse,
    CitationGraphStatusResponse,
    CitationGraphTraversalResponse,
    DiscoveryPaperDetailResponse,
    DiscoveryPaperComparisonRequest,
    DiscoveryPaperComparisonResponse,
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
from services.api.workspace.errors import WorkspaceError
from services.api.workspace.router import router as workspace_router

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
app.include_router(workspace_router)


@app.exception_handler(WorkspaceError)
async def handle_workspace_error(
    _: Request,
    exc: WorkspaceError,
):
    log_method = logger.error if exc.status_code >= 500 else logger.warning
    log_method(
        "Workspace request failed: error_code=%s message=%s",
        exc.error_code,
        exc.message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
        ).model_dump(),
    )


@app.exception_handler(DenseBackendRequestError)
async def handle_dense_backend_request_error(
    _: Request,
    exc: DenseBackendRequestError,
):
    logger.warning(
        "Dense backend request error: %s",
        exc,
    )
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(
            error_code="dense_backend_bad_request",
            message=str(exc),
            details=None,
        ).model_dump(),
    )


@app.exception_handler(DenseBackendUnavailableError)
async def handle_dense_backend_unavailable_error(
    _: Request,
    exc: DenseBackendUnavailableError,
):
    logger.error(
        "Dense backend unavailable: %s",
        exc,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(
            error_code="dense_backend_unavailable",
            message=str(exc),
            details=None,
        ).model_dump(),
    )


@app.exception_handler(DenseBackendCompatibilityError)
async def handle_dense_backend_compatibility_error(
    _: Request,
    exc: DenseBackendCompatibilityError,
):
    logger.error(
        "Dense backend compatibility error: %s",
        exc,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(
            error_code="dense_backend_incompatible",
            message=str(exc),
            details=None,
        ).model_dump(),
    )


@app.exception_handler(DenseBackendResultError)
async def handle_dense_backend_result_error(
    _: Request,
    exc: DenseBackendResultError,
):
    logger.error(
        "Dense backend result error: %s",
        exc,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(
            error_code="dense_backend_invalid_result",
            message=str(exc),
            details=None,
        ).model_dump(),
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
            details={"errors": jsonable_encoder(exc.errors())},
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
        "lexical_artifacts_loaded": snapshot["loaded_components"].get(
            "lexical_artifacts", False
        ),
        "dense_artifacts_loaded": snapshot["loaded_components"].get(
            "dense_artifacts", False
        ),
        "embedding_model_loaded": snapshot["loaded_components"].get(
            "embedding_model", False
        ),
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
def runtime_snapshot(
    refresh_qdrant: bool = Query(
        False,
        description=(
            "Force a fresh live Qdrant diagnostics probe instead of "
            "using the bounded runtime cache."
        ),
    ),
) -> RuntimeSnapshotResponse:
    runtime = get_runtime()
    return RuntimeSnapshotResponse(
        **runtime.runtime_snapshot(
            include_qdrant=True,
            refresh_qdrant=refresh_qdrant,
        )
    )


@app.get("/citation-graph/status", response_model=CitationGraphStatusResponse)
def citation_graph_status() -> CitationGraphStatusResponse:
    return build_citation_graph_status(settings=settings)


def _graph_error_response(
    *,
    status_code: int,
    error_code: str,
    message: str,
    details: dict | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error_code=error_code,
            message=message,
            details=details,
        ).model_dump(),
    )


def _citation_graph_unavailable_response() -> JSONResponse | None:
    status = build_citation_graph_status(settings=settings)

    if status.availability.get("available") is True and status.error_code is None:
        return None

    error_code = status.error_code or "graph_artifacts_invalid"
    message = status.message or "Citation/reference graph is not available."

    return _graph_error_response(
        status_code=503,
        error_code=error_code,
        message=message,
        details={
            "compatibility": status.compatibility,
            "availability": status.availability,
        },
    )


def _citation_graph_caveats(*extra: str) -> list[str]:
    caveats = list(DEFAULT_CITATION_GRAPH_CAVEATS)
    for item in extra:
        if item not in caveats:
            caveats.append(item)
    return caveats


@lru_cache(maxsize=2)
def _load_citation_graph_store_cached(graph_root: str) -> CitationGraphStore:
    return CitationGraphStore.load(graph_root)


def _load_citation_graph_store() -> CitationGraphStore:
    return _load_citation_graph_store_cached(str(settings.citation_graph_root))


def _paper_comparison_citation_graph_context(
    canonical_ids: list[str],
) -> tuple[dict[str, dict], dict, list[str]]:
    status = build_citation_graph_status(settings=settings)
    availability = status.availability or {}
    caveats = list(status.caveats or [])

    if (
        availability.get("available") is not True
        or status.error_code is not None
    ):
        capability = {
            "available": False,
            "runtime_enabled": availability.get("runtime_enabled"),
            "reason": status.error_code or "citation_graph_unavailable",
            "message": status.message,
            "caveats": caveats,
            "graph": status.graph.model_dump(),
        }
        return (
            {},
            capability,
            [
                "citation_graph_unavailable; canonical and feature-level "
                "citation signals remain available"
            ],
        )

    try:
        store = _load_citation_graph_store()
        evidence = store.paper_comparison_evidence(canonical_ids)
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        capability = {
            "available": False,
            "runtime_enabled": availability.get("runtime_enabled"),
            "reason": f"{type(exc).__name__}: {exc}",
            "message": "Citation graph comparison evidence could not be loaded.",
            "caveats": caveats,
            "graph": status.graph.model_dump(),
        }
        return (
            {},
            capability,
            [
                "citation_graph_unavailable; canonical and feature-level "
                "citation signals remain available"
            ],
        )

    capability = {
        "available": True,
        "runtime_enabled": availability.get("runtime_enabled"),
        "reason": None,
        "message": None,
        "caveats": _citation_graph_caveats(
            "comparison_uses_selected_paper_relationships_only",
        ),
        "graph": store.graph_summary(),
    }
    return evidence, capability, []


@app.get(
    "/citation-graph/papers/{canonical_id}/references",
    response_model=CitationGraphTraversalResponse,
)
def citation_graph_paper_references(
    canonical_id: str,
    limit: int | None = Query(None, ge=1),
    offset: int = Query(0, ge=0),
) -> CitationGraphTraversalResponse | JSONResponse:
    resolved_limit = (
        limit if limit is not None else settings.citation_graph_default_limit
    )

    if resolved_limit > settings.citation_graph_max_limit:
        return _graph_error_response(
            status_code=400,
            error_code="graph_result_limit_exceeded",
            message=(
                f"limit={resolved_limit} exceeds "
                f"citation_graph_max_limit={settings.citation_graph_max_limit}"
            ),
            details={
                "limit": resolved_limit,
                "max_limit": settings.citation_graph_max_limit,
            },
        )

    unavailable_response = _citation_graph_unavailable_response()
    if unavailable_response is not None:
        return unavailable_response

    try:
        store = _load_citation_graph_store()
        result = store.outgoing_references(
            canonical_id,
            limit=resolved_limit,
            offset=offset,
        )
    except FileNotFoundError as exc:
        return _graph_error_response(
            status_code=503,
            error_code="graph_artifacts_not_found",
            message=str(exc),
            details=None,
        )
    except (OSError, ValueError) as exc:
        return _graph_error_response(
            status_code=503,
            error_code="graph_artifacts_invalid",
            message=str(exc),
            details=None,
        )

    if not result.found:
        return _graph_error_response(
            status_code=404,
            error_code="canonical_id_not_found",
            message=f"Citation graph paper not found: {canonical_id}",
            details={"canonical_id": canonical_id},
        )

    return CitationGraphTraversalResponse(
        graph=store.graph_summary(),
        query=result.query,
        items=result.items,
        page=result.page.to_dict(),
        caveats=_citation_graph_caveats(
            "unresolved_references_preserved_as_external_reference_nodes",
        ),
    )


@app.get(
    "/citation-graph/papers/{canonical_id}/citations",
    response_model=CitationGraphTraversalResponse,
)
def citation_graph_paper_citations(
    canonical_id: str,
    limit: int | None = Query(None, ge=1),
    offset: int = Query(0, ge=0),
) -> CitationGraphTraversalResponse | JSONResponse:
    resolved_limit = (
        limit if limit is not None else settings.citation_graph_default_limit
    )

    if resolved_limit > settings.citation_graph_max_limit:
        return _graph_error_response(
            status_code=400,
            error_code="graph_result_limit_exceeded",
            message=(
                f"limit={resolved_limit} exceeds "
                f"citation_graph_max_limit={settings.citation_graph_max_limit}"
            ),
            details={
                "limit": resolved_limit,
                "max_limit": settings.citation_graph_max_limit,
            },
        )

    unavailable_response = _citation_graph_unavailable_response()
    if unavailable_response is not None:
        return unavailable_response

    try:
        store = _load_citation_graph_store()
        result = store.incoming_citations(
            canonical_id,
            limit=resolved_limit,
            offset=offset,
        )
    except FileNotFoundError as exc:
        return _graph_error_response(
            status_code=503,
            error_code="graph_artifacts_not_found",
            message=str(exc),
            details=None,
        )
    except (OSError, ValueError) as exc:
        return _graph_error_response(
            status_code=503,
            error_code="graph_artifacts_invalid",
            message=str(exc),
            details=None,
        )

    if not result.found:
        return _graph_error_response(
            status_code=404,
            error_code="canonical_id_not_found",
            message=f"Citation graph paper not found: {canonical_id}",
            details={"canonical_id": canonical_id},
        )

    return CitationGraphTraversalResponse(
        graph=store.graph_summary(),
        query=result.query,
        items=result.items,
        page=result.page.to_dict(),
        caveats=_citation_graph_caveats(
            "resolved_internal_references_only",
        ),
    )


@app.get(
    "/citation-graph/external-references/{reference_id:path}/papers",
    response_model=CitationGraphTraversalResponse,
)
def citation_graph_external_reference_papers(
    reference_id: str,
    limit: int | None = Query(None, ge=1),
    offset: int = Query(0, ge=0),
) -> CitationGraphTraversalResponse | JSONResponse:
    resolved_limit = (
        limit if limit is not None else settings.citation_graph_default_limit
    )

    if resolved_limit > settings.citation_graph_max_limit:
        return _graph_error_response(
            status_code=400,
            error_code="graph_result_limit_exceeded",
            message=(
                f"limit={resolved_limit} exceeds "
                f"citation_graph_max_limit={settings.citation_graph_max_limit}"
            ),
            details={
                "limit": resolved_limit,
                "max_limit": settings.citation_graph_max_limit,
            },
        )

    unavailable_response = _citation_graph_unavailable_response()
    if unavailable_response is not None:
        return unavailable_response

    try:
        store = _load_citation_graph_store()
        result = store.external_reference_papers(
            reference_id,
            limit=resolved_limit,
            offset=offset,
        )
    except FileNotFoundError as exc:
        return _graph_error_response(
            status_code=503,
            error_code="graph_artifacts_not_found",
            message=str(exc),
            details=None,
        )
    except (OSError, ValueError) as exc:
        return _graph_error_response(
            status_code=503,
            error_code="graph_artifacts_invalid",
            message=str(exc),
            details=None,
        )

    if not result.found:
        return _graph_error_response(
            status_code=404,
            error_code="external_reference_not_found",
            message=f"Citation graph external reference not found: {reference_id}",
            details={"external_reference_id": reference_id},
        )

    return CitationGraphTraversalResponse(
        graph=store.graph_summary(),
        query=result.query,
        items=result.items,
        page=result.page.to_dict(),
        caveats=_citation_graph_caveats(
            "external_reference_is_unresolved",
            "not_publication_grade_reference_entity",
        ),
    )


@app.get(
    "/citation-graph/source-families",
    response_model=CitationGraphTraversalResponse,
)
def citation_graph_source_families(
    limit: int | None = Query(None, ge=1),
    offset: int = Query(0, ge=0),
) -> CitationGraphTraversalResponse | JSONResponse:
    resolved_limit = (
        limit if limit is not None else settings.citation_graph_default_limit
    )

    if resolved_limit > settings.citation_graph_max_limit:
        return _graph_error_response(
            status_code=400,
            error_code="graph_result_limit_exceeded",
            message=(
                f"limit={resolved_limit} exceeds "
                f"citation_graph_max_limit={settings.citation_graph_max_limit}"
            ),
            details={
                "limit": resolved_limit,
                "max_limit": settings.citation_graph_max_limit,
            },
        )

    unavailable_response = _citation_graph_unavailable_response()
    if unavailable_response is not None:
        return unavailable_response

    try:
        store = _load_citation_graph_store()
        result = store.source_family_diagnostics(
            limit=resolved_limit,
            offset=offset,
        )
    except FileNotFoundError as exc:
        return _graph_error_response(
            status_code=503,
            error_code="graph_artifacts_not_found",
            message=str(exc),
            details=None,
        )
    except (OSError, ValueError) as exc:
        return _graph_error_response(
            status_code=503,
            error_code="graph_artifacts_invalid",
            message=str(exc),
            details=None,
        )

    query = dict(result.query)
    query["limit"] = resolved_limit
    query["offset"] = offset

    return CitationGraphTraversalResponse(
        graph=store.graph_summary(),
        query=query,
        items=result.items,
        page=result.page.to_dict(),
        caveats=_citation_graph_caveats(
            "source_family_reference_evidence_only",
            "not_source_coverage_metric",
        ),
    )


@app.get(
    "/citation-graph/top-referenced-papers",
    response_model=CitationGraphTraversalResponse,
)
def citation_graph_top_referenced_papers(
    limit: int | None = Query(None, ge=1),
    offset: int = Query(0, ge=0),
) -> CitationGraphTraversalResponse | JSONResponse:
    resolved_limit = (
        limit if limit is not None else settings.citation_graph_default_limit
    )

    if resolved_limit > settings.citation_graph_max_limit:
        return _graph_error_response(
            status_code=400,
            error_code="graph_result_limit_exceeded",
            message=(
                f"limit={resolved_limit} exceeds "
                f"citation_graph_max_limit={settings.citation_graph_max_limit}"
            ),
            details={
                "limit": resolved_limit,
                "max_limit": settings.citation_graph_max_limit,
            },
        )

    unavailable_response = _citation_graph_unavailable_response()
    if unavailable_response is not None:
        return unavailable_response

    try:
        store = _load_citation_graph_store()
        result = store.top_referenced_papers(
            limit=resolved_limit,
            offset=offset,
        )
    except FileNotFoundError as exc:
        return _graph_error_response(
            status_code=503,
            error_code="graph_artifacts_not_found",
            message=str(exc),
            details=None,
        )
    except (OSError, ValueError) as exc:
        return _graph_error_response(
            status_code=503,
            error_code="graph_artifacts_invalid",
            message=str(exc),
            details=None,
        )

    query = dict(result.query)
    query["limit"] = resolved_limit
    query["offset"] = offset

    return CitationGraphTraversalResponse(
        graph=store.graph_summary(),
        query=query,
        items=result.items,
        page=result.page.to_dict(),
        caveats=_citation_graph_caveats(
            "resolved_internal_reference_count_only",
            "not_global_citation_metric",
            "not_publication_grade_ranking",
        ),
    )


@app.get(
    "/citation-graph/top-external-references",
    response_model=CitationGraphTraversalResponse,
)
def citation_graph_top_external_references(
    limit: int | None = Query(None, ge=1),
    offset: int = Query(0, ge=0),
) -> CitationGraphTraversalResponse | JSONResponse:
    resolved_limit = (
        limit if limit is not None else settings.citation_graph_default_limit
    )

    if resolved_limit > settings.citation_graph_max_limit:
        return _graph_error_response(
            status_code=400,
            error_code="graph_result_limit_exceeded",
            message=(
                f"limit={resolved_limit} exceeds "
                f"citation_graph_max_limit={settings.citation_graph_max_limit}"
            ),
            details={
                "limit": resolved_limit,
                "max_limit": settings.citation_graph_max_limit,
            },
        )

    unavailable_response = _citation_graph_unavailable_response()
    if unavailable_response is not None:
        return unavailable_response

    try:
        store = _load_citation_graph_store()
        result = store.top_external_references(
            limit=resolved_limit,
            offset=offset,
        )
    except FileNotFoundError as exc:
        return _graph_error_response(
            status_code=503,
            error_code="graph_artifacts_not_found",
            message=str(exc),
            details=None,
        )
    except (OSError, ValueError) as exc:
        return _graph_error_response(
            status_code=503,
            error_code="graph_artifacts_invalid",
            message=str(exc),
            details=None,
        )

    query = dict(result.query)
    query["limit"] = resolved_limit
    query["offset"] = offset

    return CitationGraphTraversalResponse(
        graph=store.graph_summary(),
        query=query,
        items=result.items,
        page=result.page.to_dict(),
        caveats=_citation_graph_caveats(
            "external_reference_is_unresolved",
            "not_publication_grade_reference_entity",
            "not_global_citation_metric",
            "not_publication_grade_ranking",
        ),
    )


@app.post("/reload", response_model=ReloadResponse)
def reload_runtime() -> ReloadResponse:
    if not settings.enable_reload_endpoint:
        raise HTTPException(status_code=404, detail="Reload endpoint is disabled")

    runtime = get_runtime()
    _load_citation_graph_store_cached.cache_clear()
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
    category: str | None = Query(
        None, description="Category, concept, keyword or tag filter"
    ),
    source: str | None = Query(None, description="Source filter, e.g. arxiv/openalex"),
    publication_type: str | None = Query(
        None, description="Publication type filter, e.g. article/preprint"
    ),
    venue: str | None = Query(
        None, description="Venue/journal/conference/publisher filter"
    ),
    open_access: bool | None = Query(None, description="Open access filter"),
    has_code_link: bool | None = Query(
        None, description="Filter by presence of legacy canonical code link"
    ),
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
    query: str | None = Query(
        None, description="Simple text query over title/abstract/venue/publisher"
    ),
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
    provider: str | None = Query(
        None, description="Artifact provider, e.g. github/figshare/zenodo"
    ),
    artifact_type: str | None = Query(
        None, description="Artifact type, e.g. github_repository"
    ),
    relation_type: str | None = Query(
        None,
        description="Trusted paper-artifact relation, e.g. code/dataset/model/demo",
    ),
    owner: str | None = Query(
        None, description="Artifact owner/namespace when available"
    ),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    has_paper_links: bool | None = Query(
        None, description="Filter artifacts by trusted paper links presence"
    ),
    min_stars: int | None = Query(
        None,
        ge=0,
        description="Minimum GitHub stars. Rows with NULL stars do not match.",
    ),
    max_stars: int | None = Query(
        None,
        ge=0,
        description="Maximum GitHub stars. Rows with NULL stars do not match.",
    ),
    language: str | None = Query(
        None, description="GitHub repository language, case-insensitive, e.g. Python"
    ),
    license: str | None = Query(
        None, description="Artifact/GitHub license, case-insensitive, e.g. mit/gpl-3.0"
    ),
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
    ]
    | None = Query(None, description="GitHub enrichment status filter"),
    has_github_metadata: bool | None = Query(
        None,
        description="Filter by presence of metadata.github. Use with provider=github for diagnostics.",
    ),
    pushed_after: datetime | None = Query(
        None,
        description="Filter GitHub repositories by metadata.github.pushed_at >= this timestamp.",
    ),
    pushed_before: datetime | None = Query(
        None,
        description="Filter GitHub repositories by metadata.github.pushed_at <= this timestamp.",
    ),
    updated_after: datetime | None = Query(
        None,
        description="Filter GitHub repositories by materialized GitHub updated_at >= this timestamp.",
    ),
    updated_before: datetime | None = Query(
        None,
        description="Filter GitHub repositories by materialized GitHub updated_at <= this timestamp.",
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
        "pushed_desc",
        "updated_desc",
    ] = Query("linked_papers_desc"),
) -> ArtifactListResponse:
    runtime = get_runtime()
    if not runtime.is_ready():
        raise RuntimeError("Runtime is not ready")

    if runtime.db_store is None:
        raise RuntimeError("DB backend is not enabled")

    if min_stars is not None and max_stars is not None and min_stars > max_stars:
        raise ValueError("min_stars must be less than or equal to max_stars")

    if (
        pushed_after is not None
        and pushed_before is not None
        and pushed_after > pushed_before
    ):
        raise ValueError("pushed_after must be less than or equal to pushed_before")

    if (
        updated_after is not None
        and updated_before is not None
        and updated_after > updated_before
    ):
        raise ValueError("updated_after must be less than or equal to updated_before")

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
        pushed_after=pushed_after,
        pushed_before=pushed_before,
        updated_after=updated_after,
        updated_before=updated_before,
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
        pushed_after=pushed_after,
        pushed_before=pushed_before,
        updated_after=updated_after,
        updated_before=updated_before,
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
        raise HTTPException(
            status_code=404, detail=f"Artifact not found: {artifact_id}"
        )

    return ArtifactDetailResponse(
        artifact_id=artifact_id,
        found=True,
        artifact=artifact,
    )


@app.get("/artifacts/{artifact_id}/papers", response_model=ArtifactLinkedPapersResponse)
def get_artifact_papers(
    artifact_id: str,
    relation_type: str | None = Query(
        None, description="Trusted relation filter, e.g. code/dataset/model/demo"
    ),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort_by: Literal["confidence_desc", "year_desc", "title_asc"] = Query(
        "confidence_desc"
    ),
) -> ArtifactLinkedPapersResponse:
    runtime = get_runtime()
    if not runtime.is_ready():
        raise RuntimeError("Runtime is not ready")

    if runtime.db_store is None:
        raise RuntimeError("DB backend is not enabled")

    artifact = runtime.db_store.get_artifact_by_id(artifact_id)
    if artifact is None:
        raise HTTPException(
            status_code=404, detail=f"Artifact not found: {artifact_id}"
        )

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


@app.get(
    "/documents/{canonical_id}/artifacts", response_model=DocumentArtifactsResponse
)
def get_document_artifacts(
    canonical_id: str,
    relation_type: str | None = Query(
        None, description="Trusted relation filter, e.g. code/dataset/model/demo"
    ),
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
        raise HTTPException(
            status_code=404, detail=f"Document not found: {canonical_id}"
        )

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
    query_title: str | None = Query(
        None, min_length=1, max_length=settings.max_query_length
    ),
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


@app.get(
    "/discovery/clusters/{cluster_id}",
    response_model=DiscoveryTopicClusterDetailResponse,
)
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
        raise HTTPException(
            status_code=404, detail=f"Topic cluster not found: {cluster_id}"
        )

    return DiscoveryTopicClusterDetailResponse(**payload)


@app.post(
    "/discovery/papers/compare",
    response_model=DiscoveryPaperComparisonResponse,
)
def discovery_paper_comparison(
    request: DiscoveryPaperComparisonRequest,
) -> DiscoveryPaperComparisonResponse:
    (
        citation_graph_by_canonical_id,
        citation_graph_capability,
        warnings,
    ) = _paper_comparison_citation_graph_context(request.canonical_ids)

    service = get_discovery_service()
    try:
        payload = service.compare_papers(
            canonical_ids=request.canonical_ids,
            citation_graph_by_canonical_id=citation_graph_by_canonical_id,
            citation_graph_capability=citation_graph_capability,
            initial_warnings=warnings,
        )
    except PaperComparisonPaperNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "One or more papers were not found in the current "
                "canonical corpus.",
                "missing_canonical_ids": exc.missing_canonical_ids,
            },
        ) from exc

    return DiscoveryPaperComparisonResponse(**payload)


@app.get(
    "/discovery/papers/{canonical_id}", response_model=DiscoveryPaperDetailResponse
)
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
