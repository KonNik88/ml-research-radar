"""Pure helpers for controlled file-vs-Qdrant hybrid evaluation.

The module contains no runtime construction and performs no network calls.

It owns only:

- evaluation-config validation;
- public candidate-pool resolution;
- query-vector fingerprints;
- ranked-ID comparison;
- metric deltas;
- determinism diagnostics;
- high-level difference classification.

Dense retrieval, query encoding, lexical retrieval, hybrid merging,
canonical hydration, and ranking remain caller responsibilities.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from scripts.evaluation.qdrant_serving_performance import (
    compare_id_lists,
    result_ids_digest,
)


CONFIG_SCHEMA_VERSION = (
    "qdrant_hybrid_evaluation_config_v1"
)
REPORT_SCHEMA_VERSION = "qdrant_hybrid_evaluation_v1"


BLOCKING_CLASSIFICATIONS = frozenset(
    {
        "mapping_defect",
        "build_mismatch",
        "hydration_defect",
        "duplicate_candidate_defect",
        "non_finite_score",
        "non_deterministic_result",
        "fallback_detected",
        "unclassified_difference",
    }
)


def _require_mapping(
    value: Any,
    *,
    name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _require_non_empty_string(
    value: Any,
    *,
    name: str,
) -> str:
    parsed = str(value or "").strip()

    if not parsed:
        raise ValueError(f"{name} must be non-empty")

    return parsed


def _require_positive_int(
    value: Any,
    *,
    name: str,
) -> int:
    if isinstance(value, bool) or not isinstance(
        value,
        int,
    ):
        raise ValueError(f"{name} must be an integer")

    if value <= 0:
        raise ValueError(f"{name} must be positive")

    return int(value)


def _require_non_negative_int(
    value: Any,
    *,
    name: str,
) -> int:
    if isinstance(value, bool) or not isinstance(
        value,
        int,
    ):
        raise ValueError(f"{name} must be an integer")

    if value < 0:
        raise ValueError(
            f"{name} must be non-negative"
        )

    return int(value)


def _require_finite_number(
    value: Any,
    *,
    name: str,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(
            value,
            (int, float, np.integer, np.floating),
        )
    ):
        raise ValueError(f"{name} must be numeric")

    parsed = float(value)

    if not math.isfinite(parsed):
        raise ValueError(f"{name} must be finite")

    return parsed


def _validate_unique_positive_ints(
    values: Any,
    *,
    name: str,
) -> list[int]:
    if not isinstance(values, list) or not values:
        raise ValueError(
            f"{name} must be a non-empty list"
        )

    parsed = [
        _require_positive_int(
            value,
            name=f"{name}[{index}]",
        )
        for index, value in enumerate(values)
    ]

    if len(parsed) != len(set(parsed)):
        raise ValueError(
            f"{name} must not contain duplicates"
        )

    return parsed


def validate_hybrid_evaluation_config(
    config: Mapping[str, Any],
) -> None:
    """Validate the stable configuration contract."""

    if not isinstance(config, Mapping):
        raise ValueError("config must be a mapping")

    schema_version = config.get("schema_version")

    if schema_version != CONFIG_SCHEMA_VERSION:
        raise ValueError(
            "schema_version must be "
            f"{CONFIG_SCHEMA_VERSION!r}, "
            f"got {schema_version!r}"
        )

    qdrant = _require_mapping(
        config.get("qdrant"),
        name="qdrant",
    )

    _require_non_empty_string(
        qdrant.get("host"),
        name="qdrant.host",
    )
    _require_positive_int(
        qdrant.get("port"),
        name="qdrant.port",
    )
    _require_positive_int(
        qdrant.get("grpc_port"),
        name="qdrant.grpc_port",
    )

    if qdrant.get("prefer_grpc") is not True:
        raise ValueError(
            "qdrant.prefer_grpc must be true"
        )

    _require_non_empty_string(
        qdrant.get("collection_name"),
        name="qdrant.collection_name",
    )
    _require_positive_int(
        qdrant.get("timeout_sec"),
        name="qdrant.timeout_sec",
    )

    if not isinstance(
        qdrant.get("check_compatibility"),
        bool,
    ):
        raise ValueError(
            "qdrant.check_compatibility "
            "must be boolean"
        )

    profile = _require_mapping(
        qdrant.get("profile"),
        name="qdrant.profile",
    )

    _require_non_empty_string(
        profile.get("name"),
        name="qdrant.profile.name",
    )

    if profile.get("exact") is not False:
        raise ValueError(
            "qdrant.profile.exact must be false "
            "for the selected ANN profile"
        )

    _require_positive_int(
        profile.get("hnsw_ef"),
        name="qdrant.profile.hnsw_ef",
    )

    retrieval = _require_mapping(
        config.get("retrieval"),
        name="retrieval",
    )

    for field in (
        "manifest_path",
        "golden_queries_path",
        "scoring_config_path",
    ):
        _require_non_empty_string(
            retrieval.get(field),
            name=f"retrieval.{field}",
        )

    evaluation = _require_mapping(
        config.get("evaluation"),
        name="evaluation",
    )

    max_queries = evaluation.get("max_queries")
    if max_queries is not None:
        _require_positive_int(
            max_queries,
            name="evaluation.max_queries",
        )

    _validate_unique_positive_ints(
        evaluation.get("top_k_values"),
        name="evaluation.top_k_values",
    )

    rank_modes = evaluation.get("rank_modes")
    if (
        not isinstance(rank_modes, list)
        or not rank_modes
        or any(
            not isinstance(value, bool)
            for value in rank_modes
        )
    ):
        raise ValueError(
            "evaluation.rank_modes must be "
            "a non-empty boolean list"
        )

    if len(rank_modes) != len(set(rank_modes)):
        raise ValueError(
            "evaluation.rank_modes must not "
            "contain duplicates"
        )

    _require_non_negative_int(
        evaluation.get("offset"),
        name="evaluation.offset",
    )

    if evaluation.get("sort_by") != "relevance":
        raise ValueError(
            "evaluation.sort_by must be "
            "'relevance'"
        )

    candidate_pool = _require_mapping(
        evaluation.get("candidate_pool"),
        name="evaluation.candidate_pool",
    )

    if candidate_pool.get("policy") != "public":
        raise ValueError(
            "evaluation.candidate_pool.policy "
            "must be 'public'"
        )

    hybrid = _require_mapping(
        evaluation.get("hybrid"),
        name="evaluation.hybrid",
    )

    if hybrid.get("normalization") != "minmax":
        raise ValueError(
            "evaluation.hybrid.normalization "
            "must be 'minmax'"
        )

    lexical_weight = _require_finite_number(
        hybrid.get("lexical_weight"),
        name="evaluation.hybrid.lexical_weight",
    )
    dense_weight = _require_finite_number(
        hybrid.get("dense_weight"),
        name="evaluation.hybrid.dense_weight",
    )

    if lexical_weight < 0 or dense_weight < 0:
        raise ValueError(
            "hybrid weights must be non-negative"
        )

    if lexical_weight + dense_weight <= 0:
        raise ValueError(
            "hybrid weight sum must be positive"
        )

    determinism = _require_mapping(
        evaluation.get("determinism"),
        name="evaluation.determinism",
    )

    repeated_runs = _require_positive_int(
        determinism.get("repeated_runs"),
        name=(
            "evaluation.determinism."
            "repeated_runs"
        ),
    )
    mismatch_repeated_runs = _require_positive_int(
        determinism.get(
            "mismatch_repeated_runs"
        ),
        name=(
            "evaluation.determinism."
            "mismatch_repeated_runs"
        ),
    )

    if mismatch_repeated_runs < repeated_runs:
        raise ValueError(
            "mismatch_repeated_runs must be "
            "greater than or equal to repeated_runs"
        )

    quality = _require_mapping(
        config.get("quality"),
        name="quality",
    )

    _require_non_negative_int(
        quality.get("max_error_count"),
        name="quality.max_error_count",
    )

    for field in (
        "min_mean_final_overlap_at_k",
        "min_query_final_overlap_at_k",
    ):
        threshold = _require_finite_number(
            quality.get(field),
            name=f"quality.{field}",
        )

        if not 0.0 <= threshold <= 1.0:
            raise ValueError(
                f"quality.{field} must be "
                "between 0 and 1"
            )

    for field in (
        "require_same_build_id",
        "require_same_query_vector",
        "require_same_lexical_inputs",
        "require_same_candidate_budget",
        "require_same_hybrid_config",
        "require_no_fallback",
        "require_all_differences_classified",
        "require_no_blocking_classifications",
        "require_deterministic_results",
    ):
        if not isinstance(quality.get(field), bool):
            raise ValueError(
                f"quality.{field} must be boolean"
            )

    safety = _require_mapping(
        config.get("safety"),
        name="safety",
    )

    expected_safety = {
        "evaluation_only": True,
        "production_default_changed": False,
        "public_qdrant_promoted": False,
        "fallback_used": False,
        "canonical_data_changed": False,
        "retrieval_build_changed": False,
        "qdrant_collection_mutated": False,
    }

    for field, expected in expected_safety.items():
        if safety.get(field) is not expected:
            raise ValueError(
                f"safety.{field} must be "
                f"{expected!r}"
            )

    output = _require_mapping(
        config.get("output"),
        name="output",
    )
    _require_non_empty_string(
        output.get("output_dir"),
        name="output.output_dir",
    )


def public_candidate_k(
    *,
    top_k: int,
    offset: int = 0,
    corpus_size: int | None = None,
) -> int:
    """Resolve the current public candidate-pool policy."""

    parsed_top_k = _require_positive_int(
        top_k,
        name="top_k",
    )
    parsed_offset = _require_non_negative_int(
        offset,
        name="offset",
    )

    candidate_k = max(
        parsed_top_k + parsed_offset,
        parsed_top_k * 5,
        50,
    )

    if corpus_size is None:
        return candidate_k

    parsed_corpus_size = _require_positive_int(
        corpus_size,
        name="corpus_size",
    )

    return min(candidate_k, parsed_corpus_size)


def query_vector_fingerprint(
    query_vector: Any,
) -> dict[str, Any]:
    """Build a stable fingerprint for a prepared query vector."""

    vector = np.asarray(
        query_vector,
        dtype=np.float32,
    )

    if vector.ndim != 1:
        raise ValueError(
            "query_vector must be one-dimensional"
        )

    if vector.size == 0:
        raise ValueError(
            "query_vector must not be empty"
        )

    if not np.all(np.isfinite(vector)):
        raise ValueError(
            "query_vector contains non-finite values"
        )

    contiguous = np.ascontiguousarray(vector)

    return {
        "dimension": int(contiguous.shape[0]),
        "dtype": str(contiguous.dtype),
        "norm": float(np.linalg.norm(contiguous)),
        "all_finite": True,
        "sha256": hashlib.sha256(
            contiguous.tobytes()
        ).hexdigest(),
    }


def compare_ranked_ids(
    reference_ids: Sequence[str],
    candidate_ids: Sequence[str],
    *,
    top_k: int,
) -> dict[str, Any]:
    """Compare two ranked result lists with rank diagnostics."""

    parsed_top_k = _require_positive_int(
        top_k,
        name="top_k",
    )

    reference = [
        str(value)
        for value in reference_ids[:parsed_top_k]
    ]
    candidate = [
        str(value)
        for value in candidate_ids[:parsed_top_k]
    ]

    comparison = compare_id_lists(
        reference,
        candidate,
        top_k=parsed_top_k,
    )

    reference_ranks = {
        canonical_id: index
        for index, canonical_id in enumerate(
            reference,
            start=1,
        )
    }
    candidate_ranks = {
        canonical_id: index
        for index, canonical_id in enumerate(
            candidate,
            start=1,
        )
    }

    shared_ids = [
        canonical_id
        for canonical_id in reference
        if canonical_id in candidate_ranks
    ]

    rank_changes = [
        {
            "canonical_id": canonical_id,
            "reference_rank": reference_ranks[
                canonical_id
            ],
            "candidate_rank": candidate_ranks[
                canonical_id
            ],
            "rank_delta": (
                candidate_ranks[canonical_id]
                - reference_ranks[canonical_id]
            ),
        }
        for canonical_id in shared_ids
    ]

    return {
        **comparison,
        "reference_digest": result_ids_digest(
            reference
        ),
        "candidate_digest": result_ids_digest(
            candidate
        ),
        "rank_changes": rank_changes,
        "rank_change_count": sum(
            row["rank_delta"] != 0
            for row in rank_changes
        ),
    }


def metric_deltas(
    reference_metrics: Mapping[str, Any],
    candidate_metrics: Mapping[str, Any],
    *,
    metric_names: Sequence[str],
) -> dict[str, float]:
    """Calculate candidate-minus-reference metric deltas."""

    deltas: dict[str, float] = {}

    for metric_name in metric_names:
        if metric_name not in reference_metrics:
            raise ValueError(
                "Missing reference metric: "
                f"{metric_name}"
            )

        if metric_name not in candidate_metrics:
            raise ValueError(
                "Missing candidate metric: "
                f"{metric_name}"
            )

        reference_value = _require_finite_number(
            reference_metrics[metric_name],
            name=(
                f"reference_metrics.{metric_name}"
            ),
        )
        candidate_value = _require_finite_number(
            candidate_metrics[metric_name],
            name=(
                f"candidate_metrics.{metric_name}"
            ),
        )

        deltas[metric_name] = (
            candidate_value - reference_value
        )

    return deltas


def determinism_summary(
    ranked_id_runs: Sequence[Sequence[str]],
) -> dict[str, Any]:
    """Summarize repeat stability for ranked ID lists."""

    if not ranked_id_runs:
        raise ValueError(
            "ranked_id_runs must not be empty"
        )

    normalized_runs = [
        [str(value) for value in run]
        for run in ranked_id_runs
    ]
    digests = [
        result_ids_digest(run)
        for run in normalized_runs
    ]

    reference = normalized_runs[0]
    mismatch_run_numbers = [
        index
        for index, run in enumerate(
            normalized_runs,
            start=1,
        )
        if run != reference
    ]

    return {
        "run_count": len(normalized_runs),
        "stable": not mismatch_run_numbers,
        "reference_digest": digests[0],
        "unique_digest_count": len(
            set(digests)
        ),
        "run_digests": digests,
        "mismatch_run_numbers": (
            mismatch_run_numbers
        ),
    }


def classify_hybrid_difference(
    *,
    dense_comparison: Mapping[str, Any],
    final_comparison: Mapping[str, Any],
    deterministic: bool,
    mapping_failure_count: int = 0,
    hydration_failure_count: int = 0,
    fallback_used: bool = False,
) -> dict[str, Any]:
    """Classify a paired file/Qdrant hybrid difference."""

    if fallback_used:
        classification = "fallback_detected"
        reason = "A fallback path was used."
    elif mapping_failure_count > 0:
        classification = "mapping_defect"
        reason = "Dense candidate mapping failed."
    elif hydration_failure_count > 0:
        classification = "hydration_defect"
        reason = "Canonical hydration failed."
    elif not deterministic:
        classification = (
            "non_deterministic_result"
        )
        reason = (
            "Repeated runs produced different "
            "ranked IDs."
        )
    elif (
        bool(dense_comparison.get(
            "exact_same_order"
        ))
        and bool(final_comparison.get(
            "exact_same_order"
        ))
    ):
        classification = "exact_match"
        reason = (
            "Dense candidates and final hybrid "
            "results match exactly."
        )
    elif bool(final_comparison.get(
        "exact_same_order"
    )):
        classification = (
            "dense_candidate_difference_"
            "no_final_effect"
        )
        reason = (
            "Dense candidates differ, but final "
            "hybrid results are identical."
        )
    elif bool(final_comparison.get("same_set")):
        classification = (
            "same_set_different_order"
        )
        reason = (
            "Final hybrid result set matches, "
            "but ordering differs."
        )
    elif float(
        dense_comparison.get(
            "overlap_ratio",
            0.0,
        )
    ) < 1.0:
        classification = (
            "approximate_search_recall_difference"
        )
        reason = (
            "Approximate dense retrieval changed "
            "the final hybrid result set."
        )
    else:
        classification = (
            "hybrid_merge_order_difference"
        )
        reason = (
            "Dense set overlap is complete, but "
            "hybrid composition differs."
        )

    return {
        "classification": classification,
        "severity": (
            "blocking"
            if classification
            in BLOCKING_CLASSIFICATIONS
            else "diagnostic"
        ),
        "blocking": (
            classification
            in BLOCKING_CLASSIFICATIONS
        ),
        "reason": reason,
    }

def build_scenario_matrix(
    config: Mapping[str, Any],
    *,
    corpus_size: int,
) -> list[dict[str, Any]]:
    """Build the complete paired evaluation scenario matrix."""

    validate_hybrid_evaluation_config(config)

    parsed_corpus_size = _require_positive_int(
        corpus_size,
        name="corpus_size",
    )

    evaluation = _require_mapping(
        config.get("evaluation"),
        name="evaluation",
    )

    top_k_values = _validate_unique_positive_ints(
        evaluation.get("top_k_values"),
        name="evaluation.top_k_values",
    )
    rank_modes = list(
        evaluation.get("rank_modes") or []
    )
    offset = _require_non_negative_int(
        evaluation.get("offset"),
        name="evaluation.offset",
    )

    hybrid = _require_mapping(
        evaluation.get("hybrid"),
        name="evaluation.hybrid",
    )

    lexical_weight = _require_finite_number(
        hybrid.get("lexical_weight"),
        name="evaluation.hybrid.lexical_weight",
    )
    dense_weight = _require_finite_number(
        hybrid.get("dense_weight"),
        name="evaluation.hybrid.dense_weight",
    )

    scenarios: list[dict[str, Any]] = []

    for top_k in top_k_values:
        candidate_k = public_candidate_k(
            top_k=top_k,
            offset=offset,
            corpus_size=parsed_corpus_size,
        )

        for rank in rank_modes:
            rank_label = (
                "ranked"
                if bool(rank)
                else "unranked"
            )

            scenarios.append(
                {
                    "scenario_id": (
                        f"top{top_k}"
                        f"__candidate{candidate_k}"
                        f"__{rank_label}"
                    ),
                    "top_k": int(top_k),
                    "candidate_k": int(candidate_k),
                    "rank": bool(rank),
                    "offset": int(offset),
                    "sort_by": "relevance",
                    "normalization": str(
                        hybrid["normalization"]
                    ),
                    "lexical_weight": float(
                        lexical_weight
                    ),
                    "dense_weight": float(
                        dense_weight
                    ),
                }
            )

    return scenarios


def dense_candidates_to_score_rows(
    candidates: Sequence[Any],
) -> list[dict[str, Any]]:
    """Adapt typed dense candidates to hybrid score rows."""

    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):
        canonical_id = str(
            getattr(
                candidate,
                "canonical_id",
                "",
            )
            or ""
        ).strip()

        if not canonical_id:
            raise ValueError(
                "Dense candidate canonical_id "
                f"is empty at position {index}"
            )

        if canonical_id in seen_ids:
            raise ValueError(
                "Duplicate dense candidate "
                f"canonical_id: {canonical_id}"
            )

        seen_ids.add(canonical_id)

        score = _require_finite_number(
            getattr(candidate, "score", None),
            name=(
                "dense candidate score "
                f"at position {index}"
            ),
        )

        rank = _require_positive_int(
            getattr(candidate, "rank", None),
            name=(
                "dense candidate rank "
                f"at position {index}"
            ),
        )

        if rank != index:
            raise ValueError(
                "Dense candidate ranks must be "
                "continuous and one-based: "
                f"position={index}, rank={rank}"
            )

        dense_index = getattr(
            candidate,
            "dense_index",
            None,
        )
        if dense_index is not None:
            dense_index = _require_non_negative_int(
                dense_index,
                name=(
                    "dense candidate dense_index "
                    f"at position {index}"
                ),
            )

        rows.append(
            {
                "canonical_id": canonical_id,
                "score": float(score),
                "rank": int(rank),
                "dense_index": dense_index,
                "backend_point_id": getattr(
                    candidate,
                    "backend_point_id",
                    None,
                ),
                "backend_metadata": dict(
                    getattr(
                        candidate,
                        "backend_metadata",
                        {},
                    )
                    or {}
                ),
            }
        )

    return rows


def strict_hydrate_score_rows(
    score_rows: Sequence[Mapping[str, Any]],
    *,
    documents_by_id: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Hydrate every score row or fail explicitly.

    The paired evaluation must not silently discard candidates from either
    backend because that would make file/Qdrant comparison asymmetric.
    """

    hydrated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for position, score_row in enumerate(
        score_rows,
        start=1,
    ):
        canonical_id = str(
            score_row.get("canonical_id") or ""
        ).strip()

        if not canonical_id:
            raise ValueError(
                "Hybrid score row canonical_id "
                f"is empty at position {position}"
            )

        if canonical_id in seen_ids:
            raise ValueError(
                "Duplicate hybrid score row "
                f"canonical_id: {canonical_id}"
            )
        seen_ids.add(canonical_id)

        document = documents_by_id.get(
            canonical_id
        )

        if document is None:
            raise ValueError(
                "Canonical hydration failed for "
                f"canonical_id={canonical_id!r}"
            )

        hydrated.append(
            {
                **dict(score_row),
                "canonical_id": canonical_id,
                "title": document.title,
                "year": document.year,
                "doi": document.doi,
                "source_count": int(
                    document.source_count or 0
                ),
                "document": document,
            }
        )

    return hydrated


def resolve_scoring_params(
    scoring_config: Mapping[str, Any],
) -> dict[str, float | str]:
    """Resolve the public hybrid and ranking configuration."""

    retrieval = _require_mapping(
        scoring_config.get("retrieval"),
        name="scoring.retrieval",
    )
    hybrid = _require_mapping(
        retrieval.get("hybrid"),
        name="scoring.retrieval.hybrid",
    )

    ranking = _require_mapping(
        scoring_config.get("ranking"),
        name="scoring.ranking",
    )
    weights = _require_mapping(
        ranking.get("weights"),
        name="scoring.ranking.weights",
    )

    normalization = _require_non_empty_string(
        hybrid.get("normalization"),
        name=(
            "scoring.retrieval.hybrid."
            "normalization"
        ),
    )

    return {
        "normalization": normalization,
        "hybrid_lexical_weight": (
            _require_finite_number(
                hybrid.get("lexical_weight"),
                name=(
                    "scoring.retrieval.hybrid."
                    "lexical_weight"
                ),
            )
        ),
        "hybrid_dense_weight": (
            _require_finite_number(
                hybrid.get("dense_weight"),
                name=(
                    "scoring.retrieval.hybrid."
                    "dense_weight"
                ),
            )
        ),
        "ranking_retrieval_weight": (
            _require_finite_number(
                weights.get("retrieval"),
                name=(
                    "scoring.ranking.weights."
                    "retrieval"
                ),
            )
        ),
        "ranking_recency_weight": (
            _require_finite_number(
                weights.get("recency"),
                name=(
                    "scoring.ranking.weights."
                    "recency"
                ),
            )
        ),
        "ranking_source_support_weight": (
            _require_finite_number(
                weights.get("source_support"),
                name=(
                    "scoring.ranking.weights."
                    "source_support"
                ),
            )
        ),
        "ranking_metadata_quality_weight": (
            _require_finite_number(
                weights.get("metadata_quality"),
                name=(
                    "scoring.ranking.weights."
                    "metadata_quality"
                ),
            )
        ),
    }


def validate_public_scoring_contract(
    evaluation_config: Mapping[str, Any],
    scoring_config: Mapping[str, Any],
) -> dict[str, float | str]:
    """Require evaluation hybrid settings to match public scoring config."""

    validate_hybrid_evaluation_config(
        evaluation_config
    )

    scoring_params = resolve_scoring_params(
        scoring_config
    )

    evaluation = _require_mapping(
        evaluation_config.get("evaluation"),
        name="evaluation",
    )
    hybrid = _require_mapping(
        evaluation.get("hybrid"),
        name="evaluation.hybrid",
    )

    expected_normalization = str(
        hybrid.get("normalization") or ""
    )
    actual_normalization = str(
        scoring_params["normalization"]
    )

    if expected_normalization != actual_normalization:
        raise ValueError(
            "Evaluation normalization does not "
            "match public scoring config: "
            f"evaluation={expected_normalization!r}, "
            f"public={actual_normalization!r}"
        )

    comparisons = (
        (
            "lexical_weight",
            float(hybrid["lexical_weight"]),
            float(
                scoring_params[
                    "hybrid_lexical_weight"
                ]
            ),
        ),
        (
            "dense_weight",
            float(hybrid["dense_weight"]),
            float(
                scoring_params[
                    "hybrid_dense_weight"
                ]
            ),
        ),
    )

    for name, evaluation_value, public_value in comparisons:
        if not math.isclose(
            evaluation_value,
            public_value,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "Evaluation hybrid setting does "
                "not match public scoring config: "
                f"{name} evaluation="
                f"{evaluation_value}, "
                f"public={public_value}"
            )

    return scoring_params
