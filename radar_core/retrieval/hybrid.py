from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.retrieval.embeddings import DenseRetriever
from radar_core.retrieval.lexical import BM25Index, build_bm25_index


@dataclass
class HybridSearchResult:
    canonical_id: str
    hybrid_score: float
    lexical_score: float
    dense_score: float
    title: str
    year: int | None
    doi: str | None
    source_count: int
    document: CanonicalDocument


class HybridRetriever:
    def __init__(
        self,
        lexical_weight: float = 0.55,
        dense_weight: float = 0.45,
        dense_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ):
        self.lexical_weight = lexical_weight
        self.dense_weight = dense_weight
        self.lexical_index: BM25Index | None = None
        self.dense_retriever = DenseRetriever(model_name=dense_model_name)
        self.documents: list[CanonicalDocument] = []

    def build(self, documents: Sequence[CanonicalDocument]) -> None:
        self.documents = list(documents)
        self.lexical_index = build_bm25_index(self.documents)
        self.dense_retriever.build(self.documents)

    def search(self, query: str, top_k: int = 10, candidate_k: int = 50) -> list[HybridSearchResult]:
        if not self.documents or self.lexical_index is None:
            return []

        lexical_results = self.lexical_index.search(query, top_k=candidate_k)
        dense_results = self.dense_retriever.search(query, top_k=candidate_k)

        lexical_scores = {r.canonical_id: r.score for r in lexical_results}
        dense_scores = {r.canonical_id: r.score for r in dense_results}

        lexical_norm = _minmax_normalize(lexical_scores)
        dense_norm = _minmax_normalize(dense_scores)

        by_id = {doc.canonical_id: doc for doc in self.documents}
        merged_ids = set(lexical_scores) | set(dense_scores)

        combined: list[HybridSearchResult] = []
        for canonical_id in merged_ids:
            doc = by_id[canonical_id]
            l_score = lexical_norm.get(canonical_id, 0.0)
            d_score = dense_norm.get(canonical_id, 0.0)
            hybrid_score = self.lexical_weight * l_score + self.dense_weight * d_score
            combined.append(
                HybridSearchResult(
                    canonical_id=canonical_id,
                    hybrid_score=hybrid_score,
                    lexical_score=lexical_scores.get(canonical_id, 0.0),
                    dense_score=dense_scores.get(canonical_id, 0.0),
                    title=doc.title,
                    year=doc.year,
                    doi=doc.doi,
                    source_count=doc.source_count,
                    document=doc,
                )
            )

        combined.sort(key=lambda x: x.hybrid_score, reverse=True)
        return combined[:top_k]


def _minmax_normalize(score_map: dict[str, float]) -> dict[str, float]:
    if not score_map:
        return {}

    values = list(score_map.values())
    v_min = min(values)
    v_max = max(values)

    if abs(v_max - v_min) < 1e-12:
        return {k: 1.0 for k in score_map}

    return {k: (v - v_min) / (v_max - v_min) for k, v in score_map.items()}
