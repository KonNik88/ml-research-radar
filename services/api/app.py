from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from services.api.logging import get_logger
from services.api.runtime import get_runtime
from services.api.schemas import (
    ApiInfoResponse,
    DocumentListResponse,
    ErrorResponse,
    HealthResponse,
    ReloadResponse,
    RuntimeSnapshotResponse,
    SearchResponse,
)
from services.api.search_service import db_row_to_schema, run_search
from services.api.settings import get_settings


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
    return RuntimeSnapshotResponse(**runtime.runtime_snapshot())


@app.post("/reload", response_model=ReloadResponse)
def reload_runtime() -> ReloadResponse:
    if not settings.enable_reload_endpoint:
        raise HTTPException(status_code=404, detail="Reload endpoint is disabled")

    runtime = get_runtime()
    runtime.reload()
    snapshot = runtime.runtime_snapshot()

    message = (
        "DB backend runtime reloaded successfully"
        if snapshot["backend_mode"] == "db"
        else "File backend runtime reloaded successfully"
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
    has_code_link: bool | None = Query(None, description="Filter by presence of code link"),
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
    has_code_link: bool | None = Query(None),
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
    )

    return DocumentListResponse(
        total=total,
        offset=offset,
        limit=limit,
        sort_by=sort_by,
        results=[db_row_to_schema(row) for row in rows],
    )