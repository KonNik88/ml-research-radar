from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from radar_core.config import load_scoring_config
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
    QdrantSearchMeta,
    QdrantSearchResponse,
    QdrantSearchResultItem,
)
from services.api.settings import get_settings
from radar_core.retrieval.qdrant_store import QdrantRetrievalStore


logger = get_logger(__name__)

SearchMode = Literal["lexical", "dense", "hybrid"]
SearchSortBy = Literal["relevance", "year_desc", "year_asc"]
DEFAULT_QDRANT_HOST = "localhost"
DEFAULT_QDRANT_PORT = 6333
DEFAULT_QDRANT_COLLECTION_NAME = "ml_radar_dense_benchmark_v1"
DEFAULT_QDRANT_TIMEOUT_SEC = 120

@dataclass
class SearchFilterParams:
    year_from: int | None = None
    year_to: int | None = None
    category: str | None = None
    source: str | None = None
    publication_type: str | None = None
    venue: str | None = None
    open_access: bool | None = None
    has_code_link: bool | None = None
    offset: int = 0
    sort_by: SearchSortBy = "relevance"


def _load_search_scoring_params() -> dict[str, float]:
    cfg = load_scoring_config()

    hybrid_cfg = cfg.get("retrieval", {}).get("hybrid", {})
    ranking_weights = cfg.get("ranking", {}).get("weights", {})

    return {
        "hybrid_lexical_weight": float(hybrid_cfg.get("lexical_weight", 0.55)),
        "hybrid_dense_weight": float(hybrid_cfg.get("dense_weight", 0.45)),
        "ranking_retrieval_weight": float(ranking_weights.get("retrieval", 0.60)),
        "ranking_recency_weight": float(ranking_weights.get("recency", 0.20)),
        "ranking_source_support_weight": float(ranking_weights.get("source_support", 0.10)),
        "ranking_metadata_quality_weight": float(ranking_weights.get("metadata_quality", 0.10)),
    }


def _minmax_normalize(score_map: dict[str, float]) -> dict[str, float]:
    if not score_map:
        return {}

    values = list(score_map.values())
    min_v = min(values)
    max_v = max(values)

    if abs(max_v - min_v) < 1e-12:
        return {k: 1.0 for k in score_map}

    return {k: (v - min_v) / (max_v - min_v) for k, v in score_map.items()}


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(values: Any) -> list[str]:
    if not values:
        return []
    out: list[str] = []
    for value in values:
        text = _string_or_none(value)
        if text:
            out.append(text)
    return out


def _doc_to_schema(doc: CanonicalDocument) -> SearchResultDocument:
    return SearchResultDocument(
        canonical_id=doc.canonical_id,
        title=doc.title,
        abstract=doc.abstract,
        authors=list(doc.authors or []),
        year=doc.year,
        doi=doc.doi,
        arxiv_id=getattr(doc, "arxiv_id", None),
        openalex_id=getattr(doc, "openalex_id", None),
        primary_category=doc.primary_category,
        categories=list(doc.categories or []),
        concepts=list(getattr(doc, "concepts", []) or []),
        keywords=list(getattr(doc, "keywords", []) or []),
        tags=list(doc.tags or []),
        venue=getattr(doc, "venue", None),
        journal=getattr(doc, "journal", None),
        conference=getattr(doc, "conference", None),
        publisher=getattr(doc, "publisher", None),
        publication_type=getattr(doc, "publication_type", None),
        language=getattr(doc, "language", None),
        landing_page_url=_string_or_none(getattr(doc, "landing_page_url", None)),
        pdf_url=_string_or_none(getattr(doc, "pdf_url", None)),
        repo_url=_string_or_none(getattr(doc, "repo_url", None)),
        open_access=getattr(doc, "open_access", None),
        has_code_link=bool(getattr(doc, "has_code_link", False)),
        code_links=_string_list(getattr(doc, "code_links", []) or []),
        cited_by_count=getattr(doc, "cited_by_count", None),
        references_count=getattr(doc, "references_count", None),
        source_count=int(doc.source_count or 0),
        unique_source_count=int(getattr(doc, "unique_source_count", 0) or 0),
        metadata_completeness_score=getattr(doc, "metadata_completeness_score", None),
        is_preprint=getattr(doc, "is_preprint", None),
        is_review=bool(getattr(doc, "is_review", False)),
        is_survey=bool(getattr(doc, "is_survey", False)),
        is_withdrawn=bool(getattr(doc, "is_withdrawn", False)),
    )

def db_row_to_schema(doc: dict[str, Any]) -> SearchResultDocument:
    return SearchResultDocument(
        canonical_id=doc["canonical_id"],
        title=doc["title"],
        abstract=doc.get("abstract"),
        authors=list(doc.get("authors") or []),
        year=doc.get("year"),
        doi=doc.get("doi"),
        arxiv_id=doc.get("arxiv_id"),
        openalex_id=doc.get("openalex_id"),
        primary_category=doc.get("primary_category"),
        categories=list(doc.get("categories") or []),
        concepts=list(doc.get("concepts") or []),
        keywords=list(doc.get("keywords") or []),
        tags=list(doc.get("tags") or []),
        venue=doc.get("venue"),
        journal=doc.get("journal"),
        conference=doc.get("conference"),
        publisher=doc.get("publisher"),
        publication_type=doc.get("publication_type"),
        language=doc.get("language"),
        landing_page_url=_string_or_none(doc.get("landing_page_url")),
        pdf_url=_string_or_none(doc.get("pdf_url")),
        repo_url=_string_or_none(doc.get("repo_url")),
        open_access=doc.get("open_access"),
        has_code_link=bool(doc.get("has_code_link", False)),
        code_links=_string_list(doc.get("code_links") or []),
        cited_by_count=doc.get("cited_by_count"),
        references_count=doc.get("references_count"),
        source_count=int(doc.get("source_count") or 0),
        unique_source_count=int(doc.get("unique_source_count") or 0),
        metadata_completeness_score=doc.get("metadata_completeness_score"),
        is_preprint=doc.get("is_preprint"),
        is_review=bool(doc.get("is_review", False)),
        is_survey=bool(doc.get("is_survey", False)),
        is_withdrawn=bool(doc.get("is_withdrawn", False)),
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

def _encode_query_embedding(runtime: ApiRuntime, query: str) -> np.ndarray:
    if runtime.embedding_model is None:
        raise RuntimeError("Embedding model is not loaded")

    query_embedding = runtime.embedding_model.encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )[0].astype(np.float32)

    return query_embedding

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
    concepts = [c.lower() for c in (getattr(doc, "concepts", []) or [])]
    keywords = [k.lower() for k in (getattr(doc, "keywords", []) or [])]

    return (
        category_norm == primary
        or category_norm in categories
        or category_norm in tags
        or category_norm in concepts
        or category_norm in keywords
    )


def _matches_source(doc: CanonicalDocument, source: str | None) -> bool:
    if not source:
        return True

    source_norm = source.strip().lower()
    if not source_norm:
        return True

    sources = [(src.source or "").lower() for src in (doc.sources or [])]
    return source_norm in sources


def _matches_publication_type(doc: CanonicalDocument, publication_type: str | None) -> bool:
    if not publication_type:
        return True

    query_value = publication_type.strip().lower()
    if not query_value:
        return True

    doc_value = (getattr(doc, "publication_type", None) or "").strip().lower()
    return doc_value == query_value


def _matches_venue(doc: CanonicalDocument, venue: str | None) -> bool:
    if not venue:
        return True

    query_value = venue.strip().lower()
    if not query_value:
        return True

    candidates = [
        (getattr(doc, "venue", None) or "").strip().lower(),
        (getattr(doc, "journal", None) or "").strip().lower(),
        (getattr(doc, "conference", None) or "").strip().lower(),
        (getattr(doc, "publisher", None) or "").strip().lower(),
    ]
    return query_value in [c for c in candidates if c]


def _matches_open_access(doc: CanonicalDocument, open_access: bool | None) -> bool:
    if open_access is None:
        return True
    return getattr(doc, "open_access", None) is open_access


def _matches_has_code_link(doc: CanonicalDocument, has_code_link: bool | None) -> bool:
    if has_code_link is None:
        return True
    return bool(getattr(doc, "has_code_link", False)) is has_code_link


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

        if not _matches_publication_type(doc, filters.publication_type):
            continue

        if not _matches_venue(doc, filters.venue):
            continue

        if not _matches_open_access(doc, filters.open_access):
            continue

        if not _matches_has_code_link(doc, filters.has_code_link):
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


def _run_file_search(
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
    publication_type: str | None = None,
    venue: str | None = None,
    open_access: bool | None = None,
    has_code_link: bool | None = None,
    offset: int = 0,
    sort_by: SearchSortBy = "relevance",
) -> SearchResponse:
    settings = get_settings()
    scoring_params = _load_search_scoring_params()

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
        publication_type=publication_type,
        venue=venue,
        open_access=open_access,
        has_code_link=has_code_link,
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
            "publication_type": publication_type,
            "venue": venue,
            "open_access": open_access,
            "has_code_link": has_code_link,
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
            lexical_weight=scoring_params["hybrid_lexical_weight"],
            dense_weight=scoring_params["hybrid_dense_weight"],
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

    retrieved_candidates_before_filters = len(raw_candidates)
    filtered_candidates = _apply_filters(raw_candidates, filters)
    retrieved_candidates_after_filters = len(filtered_candidates)

    if rank:
        t_rank = time.perf_counter()
        retrieval_score_field = "hybrid_score" if mode == "hybrid" else "score"
        ranked_results = rank_results(
            filtered_candidates,
            retrieval_score_field=retrieval_score_field,
            retrieval_weight=scoring_params["ranking_retrieval_weight"],
            recency_weight=scoring_params["ranking_recency_weight"],
            source_support_weight=scoring_params["ranking_source_support_weight"],
            metadata_quality_weight=scoring_params["ranking_metadata_quality_weight"],
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
        retrieved_candidates_after_filters,
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
                publication_type=publication_type,
                venue=venue,
                open_access=open_access,
                has_code_link=has_code_link,
            ),
            retrieved_candidates_before_filters=retrieved_candidates_before_filters,
            retrieved_candidates_after_filters=retrieved_candidates_after_filters,
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


def _db_candidate_to_item(candidate: dict[str, Any]) -> SearchResultItem:
    return SearchResultItem(
        document=db_row_to_schema(candidate["document"]),
        retrieval=RetrievalScores(score=float(candidate.get("score", 0.0))),
        ranking=None,
    )


def _db_ranked_candidate_to_item(candidate: dict[str, Any]) -> SearchResultItem:
    return SearchResultItem(
        document=db_row_to_schema(candidate["document"]),
        retrieval=RetrievalScores(score=float(candidate.get("score", 0.0))),
        ranking=RankingScores(
            final_score=float(candidate.get("final_score", 0.0)),
            retrieval_score=float(candidate.get("retrieval_score", 0.0)),
            recency_score=float(candidate.get("recency_score", 0.0)),
            source_support_score=float(candidate.get("source_support_score", 0.0)),
            metadata_quality_score=float(candidate.get("metadata_quality_score", 0.0)),
        ),
    )


def _normalize_year(year: Any) -> int | None:
    if year is None:
        return None
    try:
        return int(year)
    except (TypeError, ValueError):
        return None


def _rank_db_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    years = [_normalize_year(c["document"].get("year")) for c in candidates]
    valid_years = [y for y in years if y is not None]
    min_year = min(valid_years) if valid_years else None
    max_year = max(valid_years) if valid_years else None

    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        doc = candidate["document"]
        retrieval_score = float(candidate.get("score", 0.0))

        year = _normalize_year(doc.get("year"))
        if year is None or min_year is None or max_year is None or min_year == max_year:
            recency_score = 0.0
        else:
            recency_score = (year - min_year) / (max_year - min_year)

        source_support_raw = int(doc.get("source_count") or 0)
        source_support_score = min(source_support_raw / 4.0, 1.0)

        metadata_quality_score = float(doc.get("metadata_completeness_score") or 0.0)
        final_score = (
            0.75 * retrieval_score
            + 0.10 * recency_score
            + 0.10 * source_support_score
            + 0.05 * metadata_quality_score
        )

        enriched = dict(candidate)
        enriched.update({
            "retrieval_score": retrieval_score,
            "recency_score": recency_score,
            "source_support_score": source_support_score,
            "metadata_quality_score": metadata_quality_score,
            "final_score": final_score,
        })
        ranked.append(enriched)

    ranked.sort(key=lambda x: x["final_score"], reverse=True)
    return ranked


def _sort_db_candidates(
    candidates: list[dict[str, Any]],
    sort_by: SearchSortBy,
    *,
    ranked: bool,
) -> list[dict[str, Any]]:
    if sort_by == "relevance":
        if ranked:
            return sorted(candidates, key=lambda x: x.get("final_score", 0.0), reverse=True)
        return sorted(candidates, key=lambda x: x.get("score", 0.0), reverse=True)

    if sort_by == "year_desc":
        return sorted(
            candidates,
            key=lambda x: (
                _normalize_year(x["document"].get("year")) is not None,
                _normalize_year(x["document"].get("year")) if _normalize_year(x["document"].get("year")) is not None else -9999,
            ),
            reverse=True,
        )

    if sort_by == "year_asc":
        return sorted(
            candidates,
            key=lambda x: (
                _normalize_year(x["document"].get("year")) is None,
                _normalize_year(x["document"].get("year")) if _normalize_year(x["document"].get("year")) is not None else 9999,
            ),
        )

    raise ValueError(f"Unsupported sort_by: {sort_by}")


def run_db_search(
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
    publication_type: str | None = None,
    venue: str | None = None,
    open_access: bool | None = None,
    has_code_link: bool | None = None,
    offset: int = 0,
    sort_by: SearchSortBy = "relevance",
) -> SearchResponse:
    settings = get_settings()
    query = _normalize_query(query)

    if mode != "lexical":
        raise ValueError(f"{mode} search is not supported for db backend v1")

    if runtime.db_store is None:
        raise RuntimeError("DB runtime is not initialized")

    filters = SearchFilterParams(
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

    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    candidate_k = max(top_k + offset, top_k * 5, 50)

    total_matches = runtime.db_store.count_search_documents(
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

    t_retrieve = time.perf_counter()
    raw_rows = runtime.db_store.search_search_documents(
        query_text=query,
        year_from=year_from,
        year_to=year_to,
        category=category,
        source=source,
        publication_type=publication_type,
        venue=venue,
        is_open_access=open_access,
        has_code_link=has_code_link,
        limit=candidate_k,
        offset=0,
    )
    timings["retrieve_ms"] = round((time.perf_counter() - t_retrieve) * 1000, 3)

    raw_candidates = [{"document": row, "score": float(row.get("score", 0.0))} for row in raw_rows]

    if rank:
        t_rank = time.perf_counter()
        ranked_candidates = _rank_db_candidates(raw_candidates)
        timings["rank_ms"] = round((time.perf_counter() - t_rank) * 1000, 3)
        sorted_candidates = _sort_db_candidates(ranked_candidates, sort_by, ranked=True)
        paged_candidates = sorted_candidates[offset: offset + top_k]
        items = [_db_ranked_candidate_to_item(c) for c in paged_candidates]
    else:
        sorted_candidates = _sort_db_candidates(raw_candidates, sort_by, ranked=False)
        paged_candidates = sorted_candidates[offset: offset + top_k]
        items = [_db_candidate_to_item(c) for c in paged_candidates]

    timings["total_ms"] = round((time.perf_counter() - t0) * 1000, 3)

    meta = None
    if settings.enable_debug_meta:
        meta = SearchMeta(
            build_id="db-runtime",
            result_count=len(items),
            rank_applied=rank,
            timing_ms=timings,
            debug_enabled=True,
            applied_filters=SearchFilters(
                year_from=filters.year_from,
                year_to=filters.year_to,
                category=filters.category,
                source=filters.source,
                publication_type=filters.publication_type,
                venue=filters.venue,
                open_access=filters.open_access,
                has_code_link=filters.has_code_link,
            ),
            retrieved_candidates_before_filters=total_matches,
            retrieved_candidates_after_filters=total_matches,
            offset=offset,
            returned_count=len(items),
            sort_by=sort_by,
        )

    return SearchResponse(
        query=query,
        mode="lexical",
        top_k=top_k,
        rank_applied=rank,
        build_id="db-runtime",
        meta=meta,
        results=items,
    )

def run_qdrant_experimental_search(
    *,
    runtime: ApiRuntime,
    query: str,
    top_k: int,
    collection_name: str = DEFAULT_QDRANT_COLLECTION_NAME,
    host: str = DEFAULT_QDRANT_HOST,
    port: int = DEFAULT_QDRANT_PORT,
    timeout_sec: int = DEFAULT_QDRANT_TIMEOUT_SEC,
) -> QdrantSearchResponse:
    if runtime.backend_mode != "file":
        raise RuntimeError("Experimental Qdrant search requires file backend runtime")

    query = _normalize_query(query)

    if runtime.manifest is None:
        raise RuntimeError("Retrieval manifest is not loaded")

    if not runtime.documents:
        raise RuntimeError("Canonical documents are not loaded")

    if runtime.embedding_model is None:
        raise RuntimeError("Embedding model is not loaded")

    t0 = time.perf_counter()
    timings: dict[str, float] = {}

    t_encode = time.perf_counter()
    query_embedding = _encode_query_embedding(runtime, query)
    timings["encode_ms"] = round((time.perf_counter() - t_encode) * 1000, 3)

    store = QdrantRetrievalStore(
        host=host,
        port=port,
        collection_name=collection_name,
        timeout_sec=timeout_sec,
        check_compatibility=False,
    )

    if not store.collection_exists():
        raise RuntimeError(f"Qdrant collection does not exist: {collection_name}")

    t_search = time.perf_counter()
    qdrant_results = store.search_vector(
        vector=query_embedding.tolist(),
        top_k=top_k,
    )
    timings["qdrant_search_ms"] = round((time.perf_counter() - t_search) * 1000, 3)

    t_hydrate = time.perf_counter()
    id_to_doc = {doc.canonical_id: doc for doc in runtime.documents}

    items: list[QdrantSearchResultItem] = []
    for rank, result in enumerate(qdrant_results, start=1):
        doc = id_to_doc.get(result.canonical_id)
        if doc is None:
            continue

        payload = dict(result.payload or {})
        dense_index = payload.get("dense_index")
        if dense_index is not None:
            try:
                dense_index = int(dense_index)
            except (TypeError, ValueError):
                dense_index = None

        items.append(
            QdrantSearchResultItem(
                rank=rank,
                document=_doc_to_schema(doc),
                retrieval=RetrievalScores(
                    score=float(result.score),
                    dense_score=float(result.score),
                ),
                point_id=result.point_id,
                dense_index=dense_index,
                payload=payload,
            )
        )

    timings["hydrate_ms"] = round((time.perf_counter() - t_hydrate) * 1000, 3)
    timings["total_ms"] = round((time.perf_counter() - t0) * 1000, 3)

    return QdrantSearchResponse(
        query=query,
        top_k=top_k,
        build_id=runtime.manifest.build_id,
        collection_name=collection_name,
        meta=QdrantSearchMeta(
            build_id=runtime.manifest.build_id,
            collection_name=collection_name,
            result_count=len(items),
            timing_ms=timings,
        ),
        results=items,
    )

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
    publication_type: str | None = None,
    venue: str | None = None,
    open_access: bool | None = None,
    has_code_link: bool | None = None,
    offset: int = 0,
    sort_by: SearchSortBy = "relevance",
) -> SearchResponse:
    if runtime.backend_mode == "db":
        return run_db_search(
            runtime=runtime,
            query=query,
            mode=mode,
            top_k=top_k,
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

    return _run_file_search(
        runtime=runtime,
        query=query,
        mode=mode,
        top_k=top_k,
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
