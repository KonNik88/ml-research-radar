from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query

from services.api.runtime import get_runtime
from services.api.schemas import HealthResponse, SearchResponse
from services.api.search_service import run_search


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = get_runtime()
    runtime.load()
    yield


app = FastAPI(
    title="ML Research Radar API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    runtime = get_runtime()
    if not runtime.is_ready():
        raise HTTPException(status_code=503, detail="Runtime is not ready")

    manifest = runtime.manifest
    if manifest is None:
        raise HTTPException(status_code=503, detail="Manifest is not loaded")

    return HealthResponse(
        status="ok",
        build_id=manifest.build_id,
        corpus_doc_count=manifest.corpus_doc_count,
        embedding_model_name=manifest.embedding_model_name,
        corpus_path=manifest.corpus_path,
    )


@app.get("/search", response_model=SearchResponse)
def search(
    query: str = Query(..., min_length=1, description="Search query"),
    mode: Literal["lexical", "dense", "hybrid"] = Query("hybrid"),
    top_k: int = Query(10, ge=1, le=100),
    rank: bool = Query(False),
) -> SearchResponse:
    runtime = get_runtime()
    if not runtime.is_ready():
        raise HTTPException(status_code=503, detail="Runtime is not ready")

    try:
        return run_search(
            runtime=runtime,
            query=query,
            mode=mode,
            top_k=top_k,
            rank=rank,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Search failed: {exc}") from exc