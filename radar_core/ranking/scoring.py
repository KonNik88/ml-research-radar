from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from radar_core.retrieval.hybrid import HybridSearchResult


@dataclass
class RankedResult:
    canonical_id: str
    final_score: float
    retrieval_score: float
    recency_score: float
    source_support_score: float
    title: str
    year: int | None
    doi: str | None
    source_count: int
    document: object


class SimpleResearchRanker:
    def __init__(
        self,
        retrieval_weight: float = 0.75,
        recency_weight: float = 0.15,
        source_support_weight: float = 0.10,
    ):
        self.retrieval_weight = retrieval_weight
        self.recency_weight = recency_weight
        self.source_support_weight = source_support_weight

    def rank(self, results: list[HybridSearchResult], top_k: int = 10) -> list[RankedResult]:
        ranked: list[RankedResult] = []
        for result in results:
            recency_score = _compute_recency_score(result.year)
            source_support_score = min(result.source_count / 3.0, 1.0)
            final_score = (
                self.retrieval_weight * result.hybrid_score
                + self.recency_weight * recency_score
                + self.source_support_weight * source_support_score
            )
            ranked.append(
                RankedResult(
                    canonical_id=result.canonical_id,
                    final_score=final_score,
                    retrieval_score=result.hybrid_score,
                    recency_score=recency_score,
                    source_support_score=source_support_score,
                    title=result.title,
                    year=result.year,
                    doi=result.doi,
                    source_count=result.source_count,
                    document=result.document,
                )
            )

        ranked.sort(key=lambda x: x.final_score, reverse=True)
        return ranked[:top_k]


def _compute_recency_score(year: int | None) -> float:
    if year is None:
        return 0.0
    current_year = datetime.now(timezone.utc).year
    delta = max(current_year - year, 0)
    return max(0.0, 1.0 - delta / 10.0)
