from __future__ import annotations

from typing import Literal

import numpy as np

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.ranking.scoring import rank_results
from services.api.runtime import ApiRuntime
from services.api.schemas import (
    RankingScores,
    RetrievalScores,
    SearchResponse,
    SearchResultDocument,
    SearchResultItem,
)


SearchMode = Literal["lexical", "dense", "hybrid"]


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


def _dense_search_with_model(
    *,
    query: str,
    documents: list[CanonicalDocument],
    embeddings: np.ndarray,
    ids: list[str],
    embedding_model,
    top_k: int,
) -> list[dict]:
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
    results: list[dict] = []

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
) -> list[dict]:
    lexical_results = lexical_index.search(query=query, top_k=top_k)
    dense_results = _dense_search_with_model(
        query=query,
        documents=documents,
        embeddings=dense_embeddings,
        ids=dense_ids,
        embedding_model=embedding_model,
        top_k=top_k,
    )

    lexical_score_map = {r.canonical_id: float(r.score) for r in lexical_results}
    dense_score_map = {r["canonical_id"]: float(r["score"]) for r in dense_results}

    lexical_norm = _minmax_normalize(lexical_score_map)
    dense_norm = _minmax_normalize(dense_score_map)

    all_ids = set(lexical_norm) | set(dense_norm)
    id_to_doc = {doc.canonical_id: doc for doc in documents}

    combined: list[dict] = []
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
    return combined[:top_k]


def _from_lexical_result(r) -> SearchResultItem:
    return SearchResultItem(
        document=_doc_to_schema(r.document),
        retrieval=RetrievalScores(score=float(r.score)),
        ranking=None,
    )


def _from_dense_result(r: dict) -> SearchResultItem:
    return SearchResultItem(
        document=_doc_to_schema(r["document"]),
        retrieval=RetrievalScores(score=float(r["score"])),
        ranking=None,
    )


def _from_hybrid_result(r: dict) -> SearchResultItem:
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


def run_search(
    *,
    runtime: ApiRuntime,
    query: str,
    mode: SearchMode,
    top_k: int,
    rank: bool,
) -> SearchResponse:
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

    if mode == "lexical":
        results = lexical_artifacts.index.search(query=query, top_k=top_k)

        if rank:
            ranked = rank_results(
                [
                    {
                        "canonical_id": r.canonical_id,
                        "score": float(r.score),
                        "title": r.title,
                        "year": r.year,
                        "doi": r.doi,
                        "source_count": r.source_count,
                        "document": r.document,
                    }
                    for r in results
                ],
                retrieval_score_field="score",
            )
            items = [_from_ranked_result(r) for r in ranked]
        else:
            items = [_from_lexical_result(r) for r in results]

        return SearchResponse(
            query=query,
            mode=mode,
            top_k=top_k,
            rank_applied=rank,
            build_id=manifest.build_id,
            results=items,
        )

    if mode == "dense":
        results = _dense_search_with_model(
            query=query,
            documents=documents,
            embeddings=dense_artifacts.embeddings,
            ids=dense_artifacts.ids,
            embedding_model=embedding_model,
            top_k=top_k,
        )

        if rank:
            ranked = rank_results(results, retrieval_score_field="score")
            items = [_from_ranked_result(r) for r in ranked]
        else:
            items = [_from_dense_result(r) for r in results]

        return SearchResponse(
            query=query,
            mode=mode,
            top_k=top_k,
            rank_applied=rank,
            build_id=manifest.build_id,
            results=items,
        )

    if mode == "hybrid":
        results = _hybrid_search_with_model(
            query=query,
            documents=documents,
            lexical_index=lexical_artifacts.index,
            dense_embeddings=dense_artifacts.embeddings,
            dense_ids=dense_artifacts.ids,
            embedding_model=embedding_model,
            top_k=top_k,
        )

        if rank:
            ranked = rank_results(
                results,
                retrieval_score_field="hybrid_score",
                retrieval_weight=0.60,
                recency_weight=0.20,
                source_support_weight=0.10,
                metadata_quality_weight=0.10,
            )
            items = [_from_ranked_result(r) for r in ranked]
        else:
            items = [_from_hybrid_result(r) for r in results]

        return SearchResponse(
            query=query,
            mode=mode,
            top_k=top_k,
            rank_applied=rank,
            build_id=manifest.build_id,
            results=items,
        )

    raise ValueError(f"Unsupported mode: {mode}")