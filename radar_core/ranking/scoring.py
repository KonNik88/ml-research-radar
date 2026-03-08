from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RankedResult:
    canonical_id: str
    title: str
    year: int | None
    doi: str | None
    source_count: int
    retrieval_score: float
    recency_score: float
    source_support_score: float
    metadata_quality_score: float
    final_score: float
    document: Any
    raw: dict[str, Any]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def minmax_normalize(score_map: dict[str, float]) -> dict[str, float]:
    if not score_map:
        return {}

    values = list(score_map.values())
    min_v = min(values)
    max_v = max(values)

    if abs(max_v - min_v) < 1e-12:
        return {k: 1.0 for k in score_map}

    return {k: (v - min_v) / (max_v - min_v) for k, v in score_map.items()}


def compute_recency_score(
    year: int | None,
    min_year: int,
    max_year: int,
) -> float:
    if year is None:
        return 0.0

    if max_year <= min_year:
        return 1.0

    clipped = max(min(year, max_year), min_year)
    return (clipped - min_year) / (max_year - min_year)


def compute_source_support_score(source_count: int | None, max_source_count: int) -> float:
    if not source_count or source_count <= 0:
        return 0.0

    if max_source_count <= 1:
        return 1.0

    clipped = min(source_count, max_source_count)
    return (clipped - 1) / (max_source_count - 1)


def compute_metadata_quality_score(document: Any) -> float:
    checks = [
        bool(getattr(document, "title", None)),
        bool(getattr(document, "abstract", None)),
        bool(getattr(document, "authors", None)),
        bool(getattr(document, "year", None)),
        bool(getattr(document, "doi", None)),
        bool(getattr(document, "categories", None)),
        bool(getattr(document, "tags", None)),
        bool(getattr(document, "primary_category", None)),
    ]
    return sum(1 for flag in checks if flag) / len(checks)


def rank_results(
    candidates: list[dict[str, Any]],
    retrieval_score_field: str = "hybrid_score",
    retrieval_weight: float = 0.60,
    recency_weight: float = 0.20,
    source_support_weight: float = 0.10,
    metadata_quality_weight: float = 0.10,
) -> list[RankedResult]:
    if not candidates:
        return []

    years = [c.get("year") for c in candidates if c.get("year") is not None]
    min_year = min(years) if years else 2000
    max_year = max(years) if years else min_year

    source_counts = [int(c.get("source_count", 0) or 0) for c in candidates]
    max_source_count = max(source_counts) if source_counts else 1

    retrieval_raw = {
        c["canonical_id"]: _safe_float(c.get(retrieval_score_field, 0.0))
        for c in candidates
    }
    retrieval_norm = minmax_normalize(retrieval_raw)

    ranked: list[RankedResult] = []
    for c in candidates:
        canonical_id = c["canonical_id"]
        doc = c["document"]

        retrieval_score = retrieval_norm.get(canonical_id, 0.0)
        recency_score = compute_recency_score(c.get("year"), min_year=min_year, max_year=max_year)
        source_support_score = compute_source_support_score(
            c.get("source_count", 0),
            max_source_count=max_source_count,
        )
        metadata_quality_score = compute_metadata_quality_score(doc)

        final_score = (
            retrieval_weight * retrieval_score
            + recency_weight * recency_score
            + source_support_weight * source_support_score
            + metadata_quality_weight * metadata_quality_score
        )

        ranked.append(
            RankedResult(
                canonical_id=canonical_id,
                title=c.get("title"),
                year=c.get("year"),
                doi=c.get("doi"),
                source_count=int(c.get("source_count", 0) or 0),
                retrieval_score=float(retrieval_score),
                recency_score=float(recency_score),
                source_support_score=float(source_support_score),
                metadata_quality_score=float(metadata_quality_score),
                final_score=float(final_score),
                document=doc,
                raw=c,
            )
        )

    ranked.sort(key=lambda x: x.final_score, reverse=True)
    return ranked