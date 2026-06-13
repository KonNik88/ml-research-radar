"""Pure helpers for hybrid lexical/dense score composition.

This module owns only backend-neutral score composition:

- lexical and dense score-map construction;
- independent min-max normalization;
- weighted hybrid-score calculation;
- current score-based ordering.

It intentionally does not:

- encode queries;
- execute lexical or dense retrieval;
- access runtime state or environment variables;
- hydrate canonical documents;
- apply filters, ranking, pagination, or API serialization.

The implementation preserves the current public and controlled-experiment
hybrid semantics. In particular, equal-score ordering is not hardened here;
changing tie-breaking would be a separate behavior change.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def minmax_normalize_scores(
    score_map: Mapping[str, float],
) -> dict[str, float]:
    """Normalize scores to [0, 1] using the existing project semantics.

    Empty mappings remain empty. When all values are equal, every candidate
    receives 1.0, matching the previous API and controlled-runner behavior.
    """

    if not score_map:
        return {}

    values = list(score_map.values())
    min_value = min(values)
    max_value = max(values)

    if abs(max_value - min_value) < 1e-12:
        return {
            canonical_id: 1.0
            for canonical_id in score_map
        }

    return {
        canonical_id: (
            float(score) - float(min_value)
        )
        / (
            float(max_value) - float(min_value)
        )
        for canonical_id, score in score_map.items()
    }


def merge_hybrid_candidate_scores(
    *,
    lexical_candidates: Sequence[Mapping[str, Any]],
    dense_candidates: Sequence[Mapping[str, Any]],
    lexical_weight: float,
    dense_weight: float,
) -> list[dict[str, Any]]:
    """Merge backend-neutral lexical and dense candidate scores.

    Candidate inputs must expose:

    - ``canonical_id``;
    - ``score``.

    The returned rows intentionally contain score information only.
    Canonical-document hydration remains a caller responsibility so public
    runtime and strict evaluation can retain different failure policies.
    """

    lexical_score_map = {
        str(candidate["canonical_id"]): float(
            candidate.get("score", 0.0)
        )
        for candidate in lexical_candidates
    }
    dense_score_map = {
        str(candidate["canonical_id"]): float(
            candidate.get("score", 0.0)
        )
        for candidate in dense_candidates
    }

    lexical_normalized = minmax_normalize_scores(
        lexical_score_map
    )
    dense_normalized = minmax_normalize_scores(
        dense_score_map
    )

    # Preserve the current implementation semantics. In particular, this
    # deliberately does not introduce a new deterministic secondary
    # tie-breaker. Tie hardening, if needed, belongs to a separate slice.
    all_ids = set(lexical_normalized) | set(
        dense_normalized
    )

    combined: list[dict[str, Any]] = []

    for canonical_id in all_ids:
        lexical_score = lexical_score_map.get(
            canonical_id,
            0.0,
        )
        dense_score = dense_score_map.get(
            canonical_id,
            0.0,
        )

        hybrid_score = (
            float(lexical_weight)
            * lexical_normalized.get(
                canonical_id,
                0.0,
            )
            + float(dense_weight)
            * dense_normalized.get(
                canonical_id,
                0.0,
            )
        )

        combined.append(
            {
                "canonical_id": canonical_id,
                "hybrid_score": float(hybrid_score),
                "lexical_score": float(lexical_score),
                "dense_score": float(dense_score),
            }
        )

    combined.sort(
        key=lambda candidate: candidate[
            "hybrid_score"
        ],
        reverse=True,
    )

    return combined