from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.ranking.scoring import rank_results
from services.api.logging import get_logger
from services.api.runtime import ApiRuntime
from services.api.schemas import (
    RankingScores,
    RetrievalScores,
    SearchFilters,
    SearchMeta,
    SearchResponse,
    SearchResultDocument,
    SearchResultItem,
)
from services.api.settings import get_settings


logger = get_logger(__name__)

SearchMode = Literal["lexical", "dense", "hybrid"]
SearchSortBy = Literal["relevance", "year_desc", "year_asc"]


@dataclass
class SearchFilterParams:
    year_from: int | None = None
    year_to: int | None = None
    category: str | None = None
    source: str | None = None
    offset: int = 0
    sort_by: SearchSortBy = "relevance"


def _minmax_normalize(score_map: dict[str, float]) -> dict[str, float]:
    if not score_map:
        return {}

    values = list(score_map.values())
    min_v = min(values)
    max_v = max(values)

    if abs(max_v - min_v) < 1e-12:
        return {k: 1.0 for k in score_map}

    return {k: (v - min_v) / (max_v - min_v) for k, v in score_map.items()}


def _doc_to_schema(doc: CanonicalDocument) -> SearchResultDocument:
    return SearchResultDocument(
        canonical_id=doc.canonical_id,
        title=doc.title,
        abstract=doc.abstract,
        authors=list(doc.authors or []),
        year=doc.year,
        doi=doc.doi,
        primary_category=doc.primary_category,
        categories=list(doc.categories or []),
        tags=list(doc.tags or []),
        source_count=int(doc.source_count or 0),
    )


def _normalize_query(query: str) -> str:
    settings = get_settings()
    normalized = query.strip()

    if not normalized:
        raise ValueError("Query must not be empty after trimming whitespace")

    if len(normalized) > settings.max_query_length:
        raise ValueError(
            f"Query is too long: {len(normalized)} > {settings.max_query_length}"
        )

    return normalized


def _dense_search_with_model(
    *,
    query: str,
    documents: list[CanonicalDocument],
    embeddings: np.ndarray,
    ids: list[str],
    embedding_model,
    top_k: int,
) -> list[dict[str, Any]]:
    if not documents or embeddings.size == 0:
        return []

    query_embedding = embedding_model.encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )[0].astype(np.float32)

    scores = embeddings @ query_embedding
    order = np.argsort(scores)[::-1][:top_k]

    id_to_doc = {doc.canonical_id: doc for doc in documents}
    results: list[dict[str, Any]] = []

    for idx in order:
        canonical_id = ids[int(idx)]
        doc = id_to_doc.get(canonical_id)
        if doc is None:
            continue

        results.append(
            {
                "canonical_id": canonical_id,
                "score": float(scores[int(idx)]),
                "title": doc.title,
                "year": doc.year,
                "doi": doc.doi,
                "source_count": int(doc.source_count or 0),
                "document": doc,
            }
        )

    return results


def _hybrid_search_with_model(
    *,
    query: str,
    documents: list[CanonicalDocument],
    lexical_index,
    dense_embeddings: np.ndarray,
    dense_ids: list[str],
    embedding_model,
    top_k: int,
    lexical_weight: float = 0.55,
    dense_weight: float = 0.45,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    t_lexical = time.perf_counter()
    lexical_results = lexical_index.search(query=query, top_k=top_k)
    lexical_ms = (time.perf_counter() - t_lexical) * 1000

    t_dense = time.perf_counter()
    dense_results = _dense_search_with_model(
        query=query,
        documents=documents,
        embeddings=dense_embeddings,
        ids=dense_ids,
        embedding_model=embedding_model,
        top_k=top_k,
    )
    dense_ms = (time.perf_counter() - t_dense) * 1000

    t_merge = time.perf_counter()
    lexical_score_map = {r.canonical_id: float(r.score) for r in lexical_results}
    dense_score_map = {r["canonical_id"]: float(r["score"]) for r in dense_results}

    lexical_norm = _minmax_normalize(lexical_score_map)
    dense_norm = _minmax_normalize(dense_score_map)

    all_ids = set(lexical_norm) | set(dense_norm)
    id_to_doc = {doc.canonical_id: doc for doc in documents}

    combined: list[dict[str, Any]] = []
    for canonical_id in all_ids:
        doc = id_to_doc.get(canonical_id)
        if doc is None:
            continue

        lexical_score = lexical_score_map.get(canonical_id, 0.0)
        dense_score = dense_score_map.get(canonical_id, 0.0)

        hybrid_score = (
            lexical_weight * lexical_norm.get(canonical_id, 0.0)
            + dense_weight * dense_norm.get(canonical_id, 0.0)
        )

        combined.append(
            {
                "canonical_id": canonical_id,
                "hybrid_score": float(hybrid_score),
                "lexical_score": float(lexical_score),
                "dense_score": float(dense_score),
                "title": doc.title,
                "year": doc.year,
                "doi": doc.doi,
                "source_count": int(doc.source_count or 0),
                "document": doc,
            }
        )

    combined.sort(key=lambda x: x["hybrid_score"], reverse=True)
    hybrid_merge_ms = (time.perf_counter() - t_merge) * 1000

    return combined[:top_k], {
        "lexical_ms": round(lexical_ms, 3),
        "dense_ms": round(dense_ms, 3),
        "hybrid_merge_ms": round(hybrid_merge_ms, 3),
    }


def _from_dense_result(r: dict[str, Any]) -> SearchResultItem:
    return SearchResultItem(
        document=_doc_to_schema(r["document"]),
        retrieval=RetrievalScores(score=float(r["score"])),
        ranking=None,
    )


def _from_hybrid_result(r: dict[str, Any]) -> SearchResultItem:
    return SearchResultItem(
        document=_doc_to_schema(r["document"]),
        retrieval=RetrievalScores(
            lexical_score=float(r["lexical_score"]),
            dense_score=float(r["dense_score"]),
            hybrid_score=float(r["hybrid_score"]),
        ),
        ranking=None,
    )


def _from_ranked_result(r) -> SearchResultItem:
    raw = r.raw
    retrieval = RetrievalScores()

    if "hybrid_score" in raw:
        retrieval.hybrid_score = float(raw.get("hybrid_score", 0.0))
        retrieval.lexical_score = float(raw.get("lexical_score", 0.0))
        retrieval.dense_score = float(raw.get("dense_score", 0.0))
    else:
        retrieval.score = float(raw.get("score", 0.0))

    return SearchResultItem(
        document=_doc_to_schema(r.document),
        retrieval=retrieval,
        ranking=RankingScores(
            final_score=float(r.final_score),
            retrieval_score=float(r.retrieval_score),
            recency_score=float(r.recency_score),
            source_support_score=float(r.source_support_score),
            metadata_quality_score=float(r.metadata_quality_score),
        ),
    )


def _lexical_results_to_dicts(results: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "canonical_id": r.canonical_id,
            "score": float(r.score),
            "title": r.title,
            "year": r.year,
            "doi": r.doi,
            "source_count": int(r.source_count or 0),
            "document": r.document,
        }
        for r in results
    ]


def _matches_category(doc: CanonicalDocument, category: str | None) -> bool:
    if not category:
        return True

    category_norm = category.strip().lower()
    if not category_norm:
        return True

    primary = (doc.primary_category or "").lower()
    categories = [c.lower() for c in (doc.categories or [])]
    tags = [t.lower() for t in (doc.tags or [])]

    return (
        category_norm == primary
        or category_norm in categories
        or category_norm in tags
    )


def _matches_source(doc: CanonicalDocument, source: str | None) -> bool:
    if not source:
        return True

    source_norm = source.strip().lower()
    if not source_norm:
        return True

    sources = [(src.source or "").lower() for src in (doc.sources or [])]
    return source_norm in sources


def _apply_filters(
    candidates: list[dict[str, Any]],
    filters: SearchFilterParams,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []

    for candidate in candidates:
        doc: CanonicalDocument = candidate["document"]

        if filters.year_from is not None:
            if doc.year is None or doc.year < filters.year_from:
                continue

        if filters.year_to is not None:
            if doc.year is None or doc.year > filters.year_to:
                continue

        if not _matches_category(doc, filters.category):
            continue

        if not _matches_source(doc, filters.source):
            continue

        filtered.append(candidate)

    return filtered


def _sort_unranked_candidates(
    candidates: list[dict[str, Any]],
    sort_by: SearchSortBy,
) -> list[dict[str, Any]]:
    if sort_by == "relevance":
        return candidates

    if sort_by == "year_desc":
        return sorted(
            candidates,
            key=lambda x: (
                x["document"].year is not None,
                x["document"].year if x["document"].year is not None else -9999,
            ),
            reverse=True,
        )

    if sort_by == "year_asc":
        return sorted(
            candidates,
            key=lambda x: (
                x["document"].year is None,
                x["document"].year if x["document"].year is not None else 9999,
            ),
        )

    raise ValueError(f"Unsupported sort_by: {sort_by}")


def _sort_ranked_results(
    ranked_results: list[Any],
    sort_by: SearchSortBy,
) -> list[Any]:
    if sort_by == "relevance":
        return ranked_results

    if sort_by == "year_desc":
        return sorted(
            ranked_results,
            key=lambda x: (
                x.document.year is not None,
                x.document.year if x.document.year is not None else -9999,
            ),
            reverse=True,
        )

    if sort_by == "year_asc":
        return sorted(
            ranked_results,
            key=lambda x: (
                x.document.year is None,
                x.document.year if x.document.year is not None else 9999,
            ),
        )

    raise ValueError(f"Unsupported sort_by: {sort_by}")


def _candidate_pool_size(
    *,
    requested_top_k: int,
    offset: int,
    corpus_size: int,
) -> int:
    candidate_k = max(requested_top_k + offset, requested_top_k * 5, 50)
    return min(candidate_k, max(corpus_size, 1))


def run_search(
    *,
    runtime: ApiRuntime,
    query: str,
    mode: SearchMode,
    top_k: int,
    rank: bool,
    year_from: int | None = None,
    year_to: int | None = None,
    category: str | None = None,
    source: str | None = None,
    offset: int = 0,
    sort_by: SearchSortBy = "relevance",
) -> SearchResponse:
    settings = get_settings()

    query = _normalize_query(query)

    documents = runtime.documents
    lexical_artifacts = runtime.lexical_artifacts
    dense_artifacts = runtime.dense_artifacts
    embedding_model = runtime.embedding_model
    manifest = runtime.manifest

    if (
        lexical_artifacts is None
        or dense_artifacts is None
        or embedding_model is None
        or manifest is None
    ):
        raise RuntimeError("API runtime is not initialized")

    filters = SearchFilterParams(
        year_from=year_from,
        year_to=year_to,
        category=category,
        source=source,
        offset=offset,
        sort_by=sort_by,
    )

    t0 = time.perf_counter()
    timings: dict[str, float] = {}

    logger.info(
        "Search request: mode=%s top_k=%s rank=%s offset=%s sort_by=%s query=%s filters=%s",
        mode,
        top_k,
        rank,
        offset,
        sort_by,
        query,
        {
            "year_from": year_from,
            "year_to": year_to,
            "category": category,
            "source": source,
        },
    )

    candidate_k = _candidate_pool_size(
        requested_top_k=top_k,
        offset=offset,
        corpus_size=len(documents),
    )

    if mode == "lexical":
        t_retrieve = time.perf_counter()
        lexical_results = lexical_artifacts.index.search(query=query, top_k=candidate_k)
        raw_candidates = _lexical_results_to_dicts(lexical_results)
        timings["retrieve_ms"] = round((time.perf_counter() - t_retrieve) * 1000, 3)

    elif mode == "dense":
        t_retrieve = time.perf_counter()
        raw_candidates = _dense_search_with_model(
            query=query,
            documents=documents,
            embeddings=dense_artifacts.embeddings,
            ids=dense_artifacts.ids,
            embedding_model=embedding_model,
            top_k=candidate_k,
        )
        timings["retrieve_ms"] = round((time.perf_counter() - t_retrieve) * 1000, 3)

    elif mode == "hybrid":
        raw_candidates, hybrid_timings = _hybrid_search_with_model(
            query=query,
            documents=documents,
            lexical_index=lexical_artifacts.index,
            dense_embeddings=dense_artifacts.embeddings,
            dense_ids=dense_artifacts.ids,
            embedding_model=embedding_model,
            top_k=candidate_k,
        )
        timings.update(hybrid_timings)
        timings["retrieve_ms"] = round(
            hybrid_timings["lexical_ms"]
            + hybrid_timings["dense_ms"]
            + hybrid_timings["hybrid_merge_ms"],
            3,
        )
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    total_candidates_before_filters = len(raw_candidates)
    filtered_candidates = _apply_filters(raw_candidates, filters)
    total_candidates_after_filters = len(filtered_candidates)

    if rank:
        t_rank = time.perf_counter()
        retrieval_score_field = "hybrid_score" if mode == "hybrid" else "score"
        ranked_results = rank_results(
            filtered_candidates,
            retrieval_score_field=retrieval_score_field,
            retrieval_weight=0.60,
            recency_weight=0.20,
            source_support_weight=0.10,
            metadata_quality_weight=0.10,
        )
        timings["rank_ms"] = round((time.perf_counter() - t_rank) * 1000, 3)

        ranked_results = _sort_ranked_results(ranked_results, sort_by)
        paged_ranked_results = ranked_results[offset : offset + top_k]
        items = [_from_ranked_result(r) for r in paged_ranked_results]
    else:
        filtered_candidates = _sort_unranked_candidates(filtered_candidates, sort_by)
        paged_candidates = filtered_candidates[offset : offset + top_k]

        if mode == "lexical":
            items = [_from_dense_result(r) for r in paged_candidates]
            for item, candidate in zip(items, paged_candidates):
                item.retrieval = RetrievalScores(score=float(candidate["score"]))
        elif mode == "dense":
            items = [_from_dense_result(r) for r in paged_candidates]
        else:
            items = [_from_hybrid_result(r) for r in paged_candidates]

    timings["total_ms"] = round((time.perf_counter() - t0) * 1000, 3)

    logger.info(
        "Search completed: mode=%s top_k=%s rank=%s offset=%s filtered=%s returned=%s total_ms=%s",
        mode,
        top_k,
        rank,
        offset,
        total_candidates_after_filters,
        len(items),
        timings["total_ms"],
    )

    meta = None
    if settings.enable_debug_meta:
        meta = SearchMeta(
            build_id=manifest.build_id,
            result_count=len(items),
            rank_applied=rank,
            timing_ms=timings,
            debug_enabled=True,
            applied_filters=SearchFilters(
                year_from=year_from,
                year_to=year_to,
                category=category,
                source=source,
            ),
            total_candidates_before_filters=total_candidates_before_filters,
            total_candidates_after_filters=total_candidates_after_filters,
            offset=offset,
            returned_count=len(items),
            sort_by=sort_by,
        )

    return SearchResponse(
        query=query,
        mode=mode,
        top_k=top_k,
        rank_applied=rank,
        build_id=manifest.build_id,
        meta=meta,
        results=items,
    )