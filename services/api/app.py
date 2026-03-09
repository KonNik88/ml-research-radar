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
    ErrorResponse,
    HealthResponse,
    ReloadResponse,
    RuntimeSnapshotResponse,
    SearchResponse,
)
from services.api.search_service import run_search
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
    if not runtime.is_ready():
        raise RuntimeError("Runtime is not ready")

    manifest = runtime.manifest
    if manifest is None:
        raise RuntimeError("Manifest is not loaded")

    return HealthResponse(
        status="ok",
        build_id=manifest.build_id,
        corpus_doc_count=manifest.corpus_doc_count,
        embedding_model_name=manifest.embedding_model_name,
        corpus_path=manifest.corpus_path,
    )


@app.get("/info", response_model=ApiInfoResponse)
def info() -> ApiInfoResponse:
    runtime = get_runtime()
    snapshot = runtime.runtime_snapshot()

    if runtime.manifest is None:
        raise RuntimeError("Manifest is not loaded")

    return ApiInfoResponse(
        api_title=settings.api_title,
        api_version=settings.api_version,
        build_id=runtime.manifest.build_id,
        corpus_doc_count=snapshot["corpus_doc_count"],
        embedding_model_name=runtime.manifest.embedding_model_name,
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

    if runtime.manifest is None:
        raise RuntimeError("Manifest is not loaded after reload")

    return ReloadResponse(
        status="reloaded",
        build_id=runtime.manifest.build_id,
        corpus_doc_count=len(runtime.documents),
        embedding_model_name=runtime.manifest.embedding_model_name,
    )


@app.get("/search", response_model=SearchResponse)
def search(
    query: str = Query(..., min_length=1, description="Search query"),
    mode: Literal["lexical", "dense", "hybrid"] = Query("hybrid"),
    top_k: int | None = Query(None, ge=1),
    rank: bool = Query(False),
) -> SearchResponse:
    runtime = get_runtime()
    if not runtime.is_ready():
        raise RuntimeError("Runtime is not ready")

    resolved_top_k = top_k if top_k is not None else settings.default_top_k
    if resolved_top_k > settings.max_top_k:
        raise ValueError(
            f"top_k={resolved_top_k} exceeds max_top_k={settings.max_top_k}"
        )

    return run_search(
        runtime=runtime,
        query=query,
        mode=mode,
        top_k=resolved_top_k,
        rank=rank,
    )