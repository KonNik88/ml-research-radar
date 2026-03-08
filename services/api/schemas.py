from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    build_id: str
    corpus_doc_count: int
    embedding_model_name: str
    corpus_path: str


class SearchResultDocument(BaseModel):
    canonical_id: str
    title: str
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    primary_category: str | None = None
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    source_count: int = 0


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
    results: list[SearchResultItem]