"""Pure helpers for Qdrant vs file-dense parity evaluation.

The functions in this module intentionally avoid API/runtime concerns. They
operate on prepared query vectors, dense artifacts, and normalized result rows.

Reference file-dense semantics are the current production kernel:

    scores = stored_embeddings @ normalized_float32_query
    order = np.argsort(scores)[::-1]

Stored embeddings are used as persisted. Callers must verify from dense metadata
that the matrix is already normalized; this module does not silently re-normalize
it and therefore cannot hide build-contract violations.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from radar_core.retrieval.dense_backend import (
    exact_file_dense_candidates,
)

ResultRow = dict[str, Any]


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float, np.integer, np.floating))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _positive_int(value: int, *, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {value!r}")
    return value


def canonical_ids(rows: Sequence[Mapping[str, Any]], top_k: int | None = None) -> list[str]:
    """Return non-empty canonical IDs in result order."""

    selected = rows if top_k is None else rows[:top_k]
    values: list[str] = []
    for row in selected:
        canonical_id = str(row.get("canonical_id") or "").strip()
        if canonical_id:
            values.append(canonical_id)
    return values


def query_vector_metadata(query_vector: np.ndarray) -> dict[str, Any]:
    """Build a compact fingerprint for a prepared query vector."""

    vector = np.asarray(query_vector, dtype=np.float32)
    if vector.ndim != 1:
        raise ValueError(f"query_vector must be one-dimensional, got shape={vector.shape}")

    return {
        "dimension": int(vector.shape[0]),
        "dtype": str(vector.dtype),
        "norm": float(np.linalg.norm(vector)),
        "all_finite": bool(np.isfinite(vector).all()),
        "sha256": hashlib.sha256(vector.tobytes()).hexdigest(),
    }


def exact_file_dense_search(
    *,
    embeddings: np.ndarray,
    ids: Sequence[str],
    query_vector: np.ndarray,
    limit: int,
) -> list[ResultRow]:
    """Run exact file-dense search with production ordering semantics.

    The authoritative exact candidate kernel lives in
    ``radar_core.retrieval.dense_backend``. This function remains as a
    compatibility adapter for parity reports and existing callers.

    The query is expected to be prepared and normalized by the caller. Stored
    embeddings are used as persisted.
    """

    limit = _positive_int(limit, name="limit")

    candidates = exact_file_dense_candidates(
        embeddings=embeddings,
        ids=ids,
        query_vector=query_vector,
        top_k=limit,
    )

    return [
        {
            "rank": candidate.rank,
            "canonical_id": candidate.canonical_id,
            "dense_index": candidate.dense_index,
            "score": candidate.score,
        }
        for candidate in candidates
    ]


def build_rank_map(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Map canonical ID to first one-based rank."""

    rank_map: dict[str, int] = {}
    for fallback_rank, row in enumerate(rows, start=1):
        canonical_id = str(row.get("canonical_id") or "").strip()
        if not canonical_id or canonical_id in rank_map:
            continue
        rank_value = row.get("rank")
        rank = int(rank_value) if isinstance(rank_value, int) else fallback_rank
        rank_map[canonical_id] = rank
    return rank_map


def _score_map(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for row in rows:
        canonical_id = str(row.get("canonical_id") or "").strip()
        score = row.get("score")
        if canonical_id and _is_finite_number(score) and canonical_id not in scores:
            scores[canonical_id] = float(score)
    return scores


def compare_ranked_results(
    *,
    reference_rows: Sequence[Mapping[str, Any]],
    candidate_rows: Sequence[Mapping[str, Any]],
    top_k: int,
) -> dict[str, Any]:
    """Compare ranked result lists at ``top_k`` while preserving order.

    ``reference_only`` and ``candidate_only`` are derived automatically; no
    query-specific IDs are accepted or required.
    """

    top_k = _positive_int(top_k, name="top_k")
    reference_ids = canonical_ids(reference_rows, top_k)
    candidate_ids = canonical_ids(candidate_rows, top_k)

    reference_set = set(reference_ids)
    candidate_set = set(candidate_ids)
    overlap_count = len(reference_set & candidate_set)

    reference_rank_map = build_rank_map(reference_rows)
    candidate_rank_map = build_rank_map(candidate_rows)
    reference_score_map = _score_map(reference_rows)
    candidate_score_map = _score_map(candidate_rows)

    reference_only = [cid for cid in reference_ids if cid not in candidate_set]
    candidate_only = [cid for cid in candidate_ids if cid not in reference_set]

    common_deltas: list[dict[str, Any]] = []
    for canonical_id in reference_ids:
        if canonical_id not in candidate_set:
            continue
        reference_rank = reference_rank_map.get(canonical_id)
        candidate_rank = candidate_rank_map.get(canonical_id)
        reference_score = reference_score_map.get(canonical_id)
        candidate_score = candidate_score_map.get(canonical_id)
        score_delta = (
            candidate_score - reference_score
            if reference_score is not None and candidate_score is not None
            else None
        )
        common_deltas.append(
            {
                "canonical_id": canonical_id,
                "reference_rank": reference_rank,
                "candidate_rank": candidate_rank,
                "rank_delta": (
                    candidate_rank - reference_rank
                    if reference_rank is not None and candidate_rank is not None
                    else None
                ),
                "reference_score": reference_score,
                "candidate_score": candidate_score,
                "score_delta": score_delta,
                "abs_score_delta": abs(score_delta) if score_delta is not None else None,
            }
        )

    return {
        "top_k": top_k,
        "reference_returned_count": len(reference_ids),
        "candidate_returned_count": len(candidate_ids),
        "overlap_count": overlap_count,
        "overlap_ratio": overlap_count / top_k,
        "exact_same_order": reference_ids == candidate_ids,
        "same_set": reference_set == candidate_set and len(reference_ids) == len(candidate_ids),
        "reference_only": reference_only,
        "candidate_only": candidate_only,
        "common_result_deltas": common_deltas,
    }


def build_mismatch_details(
    *,
    comparison: Mapping[str, Any],
    reference_rows: Sequence[Mapping[str, Any]],
    candidate_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Enrich set differences with ranks and scores from the internal window."""

    reference_rank_map = build_rank_map(reference_rows)
    candidate_rank_map = build_rank_map(candidate_rows)
    reference_score_map = _score_map(reference_rows)
    candidate_score_map = _score_map(candidate_rows)

    def describe(canonical_id: str) -> dict[str, Any]:
        return {
            "canonical_id": canonical_id,
            "reference_rank": reference_rank_map.get(canonical_id),
            "candidate_rank": candidate_rank_map.get(canonical_id),
            "reference_score": reference_score_map.get(canonical_id),
            "candidate_score": candidate_score_map.get(canonical_id),
        }

    reference_only = [describe(str(cid)) for cid in comparison.get("reference_only", [])]
    candidate_only = [describe(str(cid)) for cid in comparison.get("candidate_only", [])]

    pairwise_gaps: list[dict[str, Any]] = []
    for missed in reference_only:
        for replacement in candidate_only:
            missed_score = missed.get("reference_score")
            replacement_score = replacement.get("reference_score")
            pairwise_gaps.append(
                {
                    "missed_reference_id": missed["canonical_id"],
                    "missed_reference_rank": missed.get("reference_rank"),
                    "missed_reference_score": missed_score,
                    "replacement_id": replacement["canonical_id"],
                    "replacement_reference_rank": replacement.get("reference_rank"),
                    "replacement_reference_score": replacement_score,
                    "reference_score_gap": (
                        missed_score - replacement_score
                        if _is_finite_number(missed_score)
                        and _is_finite_number(replacement_score)
                        else None
                    ),
                }
            )

    best_missed_rank = min(
        (
            int(item["reference_rank"])
            for item in reference_only
            if isinstance(item.get("reference_rank"), int)
        ),
        default=None,
    )

    return {
        "reference_only": reference_only,
        "candidate_only": candidate_only,
        "pairwise_reference_score_gaps": pairwise_gaps,
        "best_missed_reference_rank": best_missed_rank,
    }


def audit_qdrant_mapping(
    *,
    rows: Sequence[Mapping[str, Any]],
    ids: Sequence[str],
    expected_build_id: str,
    require_point_id_equals_dense_index: bool = True,
) -> dict[str, Any]:
    """Audit raw Qdrant result payloads against the active dense ID mapping."""

    failures: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for fallback_rank, row in enumerate(rows, start=1):
        payload = row.get("payload")
        payload = payload if isinstance(payload, Mapping) else {}

        raw_canonical_id = payload.get("canonical_id")
        raw_dense_index = payload.get("dense_index")
        raw_build_id = payload.get("build_id")
        point_id = row.get("point_id")
        score = row.get("score")

        canonical_id = str(raw_canonical_id).strip() if raw_canonical_id is not None else ""
        reasons: list[str] = []

        if not canonical_id:
            reasons.append("missing_payload_canonical_id")
        elif canonical_id in seen_ids:
            reasons.append("duplicate_canonical_id")
        else:
            seen_ids.add(canonical_id)

        dense_index: int | None
        if isinstance(raw_dense_index, int) and not isinstance(raw_dense_index, bool):
            dense_index = raw_dense_index
        else:
            dense_index = None
            reasons.append("missing_or_invalid_payload_dense_index")

        if dense_index is not None:
            if not 0 <= dense_index < len(ids):
                reasons.append("dense_index_out_of_range")
            elif canonical_id and str(ids[dense_index]) != canonical_id:
                reasons.append("ids_dense_index_mismatch")

        normalized_row_id = str(row.get("canonical_id") or "").strip()
        if normalized_row_id and canonical_id and normalized_row_id != canonical_id:
            reasons.append("normalized_id_payload_id_mismatch")

        if require_point_id_equals_dense_index and dense_index is not None:
            try:
                normalized_point_id: Any = int(point_id)
            except (TypeError, ValueError):
                normalized_point_id = point_id
            if normalized_point_id != dense_index:
                reasons.append("point_id_dense_index_mismatch")

        if str(raw_build_id or "") != str(expected_build_id):
            reasons.append("build_id_mismatch")

        if not _is_finite_number(score):
            reasons.append("non_finite_or_invalid_score")

        if reasons:
            failures.append(
                {
                    "rank": row.get("rank", fallback_rank),
                    "point_id": point_id,
                    "canonical_id": canonical_id or None,
                    "dense_index": dense_index,
                    "build_id": raw_build_id,
                    "reasons": reasons,
                }
            )

    reason_counts = Counter(
        reason for failure in failures for reason in failure.get("reasons", [])
    )

    return {
        "checked_count": len(rows),
        "failure_count": len(failures),
        "reason_counts": dict(sorted(reason_counts.items())),
        "failures": failures,
    }


def check_repeat_determinism(
    *,
    repeated_runs: Sequence[Sequence[Mapping[str, Any]]],
    top_k: int,
) -> dict[str, Any]:
    """Check result-order and score determinism across recorded runs."""

    top_k = _positive_int(top_k, name="top_k")
    if not repeated_runs:
        return {
            "recorded_runs": 0,
            "top_k_checked": top_k,
            "stable_order": None,
            "stable_scores": None,
            "max_score_delta": None,
            "id_sequences": [],
        }

    id_sequences = [canonical_ids(run, top_k) for run in repeated_runs]
    stable_order = all(sequence == id_sequences[0] for sequence in id_sequences[1:])

    max_score_delta = 0.0
    stable_scores = True
    reference_scores = [row.get("score") for row in repeated_runs[0][:top_k]]

    for run in repeated_runs[1:]:
        scores = [row.get("score") for row in run[:top_k]]
        if len(scores) != len(reference_scores):
            stable_scores = False
            continue
        for left, right in zip(reference_scores, scores):
            if not _is_finite_number(left) or not _is_finite_number(right):
                stable_scores = False
                continue
            delta = abs(float(left) - float(right))
            max_score_delta = max(max_score_delta, delta)
            if delta != 0.0:
                stable_scores = False

    return {
        "recorded_runs": len(repeated_runs),
        "top_k_checked": top_k,
        "stable_order": stable_order,
        "stable_scores": stable_scores,
        "max_score_delta": max_score_delta,
        "id_sequences": id_sequences,
    }


def summarize_latencies(values_ms: Iterable[float]) -> dict[str, Any]:
    values = [float(value) for value in values_ms if _is_finite_number(value)]
    if not values:
        return {
            "count": 0,
            "mean_ms": None,
            "p50_ms": None,
            "p95_ms": None,
            "max_ms": None,
        }

    array = np.asarray(values, dtype=np.float64)
    return {
        "count": len(values),
        "mean_ms": float(np.mean(array)),
        "p50_ms": float(np.percentile(array, 50)),
        "p95_ms": float(np.percentile(array, 95)),
        "max_ms": float(np.max(array)),
    }


def classify_profile_difference(
    *,
    comparison: Mapping[str, Any],
    exact_comparison: Mapping[str, Any],
    mapping_audit: Mapping[str, Any],
    determinism: Mapping[str, Any] | None,
    is_exact_profile: bool,
) -> dict[str, Any]:
    """Classify profile parity without hiding blocking integrity defects."""

    mapping_failures = int(mapping_audit.get("failure_count") or 0)
    if mapping_failures > 0:
        return {
            "classification": "mapping_or_payload_defect",
            "severity": "blocking",
            "rationale": f"mapping audit reported {mapping_failures} failure(s)",
        }

    exact_matches = bool(exact_comparison.get("exact_same_order"))
    if not exact_matches:
        return {
            "classification": "exact_parity_failure",
            "severity": "blocking",
            "rationale": "exact Qdrant profile does not match the exact file reference",
        }

    if bool(comparison.get("exact_same_order")):
        return {
            "classification": "exact_match",
            "severity": "ok",
            "rationale": "profile matches the exact file reference at top_k",
        }

    if is_exact_profile:
        return {
            "classification": "exact_parity_failure",
            "severity": "blocking",
            "rationale": "exact profile differs from the exact file reference",
        }

    if determinism is not None and determinism.get("stable_order") is False:
        return {
            "classification": "non_deterministic_result",
            "severity": "blocking",
            "rationale": "recorded repeated runs returned different result order",
        }

    return {
        "classification": "approximate_search_recall_difference",
        "severity": "warning",
        "rationale": (
            "ANN profile differs from the exact file reference while exact Qdrant "
            "matches and mapping integrity is valid"
        ),
    }
