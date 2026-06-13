from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest
from types import SimpleNamespace

from scripts.evaluation.qdrant_hybrid_evaluation import (
    build_scenario_matrix,
    classify_hybrid_difference,
    compare_ranked_ids,
    dense_candidates_to_score_rows,
    determinism_summary,
    metric_deltas,
    public_candidate_k,
    query_vector_fingerprint,
    resolve_scoring_params,
    strict_hydrate_score_rows,
    validate_hybrid_evaluation_config,
    validate_public_scoring_contract,
)
from services.api.search_service import (
    _candidate_pool_size,
)


def valid_config() -> dict:
    return {
        "schema_version": (
            "qdrant_hybrid_evaluation_config_v1"
        ),
        "qdrant": {
            "host": "localhost",
            "port": 6333,
            "grpc_port": 6334,
            "prefer_grpc": True,
            "collection_name": "collection",
            "timeout_sec": 120,
            "check_compatibility": True,
            "profile": {
                "name": "ef_256",
                "exact": False,
                "hnsw_ef": 256,
            },
        },
        "retrieval": {
            "manifest_path": "manifest.json",
            "golden_queries_path": "golden.jsonl",
            "scoring_config_path": "scoring.yaml",
        },
        "evaluation": {
            "max_queries": None,
            "top_k_values": [10, 20],
            "rank_modes": [False, True],
            "offset": 0,
            "sort_by": "relevance",
            "candidate_pool": {
                "policy": "public",
            },
            "hybrid": {
                "normalization": "minmax",
                "lexical_weight": 0.55,
                "dense_weight": 0.45,
            },
            "determinism": {
                "repeated_runs": 2,
                "mismatch_repeated_runs": 5,
            },
        },
        "quality": {
            "max_error_count": 0,
            "min_mean_final_overlap_at_k": 0.99,
            "min_query_final_overlap_at_k": 0.95,
            "require_same_build_id": True,
            "require_same_query_vector": True,
            "require_same_lexical_inputs": True,
            "require_same_candidate_budget": True,
            "require_same_hybrid_config": True,
            "require_no_fallback": True,
            "require_all_differences_classified": True,
            "require_no_blocking_classifications": True,
            "require_deterministic_results": True,
        },
        "safety": {
            "evaluation_only": True,
            "production_default_changed": False,
            "public_qdrant_promoted": False,
            "fallback_used": False,
            "canonical_data_changed": False,
            "retrieval_build_changed": False,
            "qdrant_collection_mutated": False,
        },
        "output": {
            "output_dir": (
                "artifacts/reports/evaluation"
            ),
        },
    }


def exact_comparison() -> dict:
    return {
        "overlap_ratio": 1.0,
        "exact_same_order": True,
        "same_set": True,
    }


def test_valid_config_passes() -> None:
    validate_hybrid_evaluation_config(
        valid_config()
    )


def test_config_rejects_wrong_schema() -> None:
    config = valid_config()
    config["schema_version"] = "wrong"

    with pytest.raises(
        ValueError,
        match="schema_version",
    ):
        validate_hybrid_evaluation_config(config)


def test_config_requires_grpc() -> None:
    config = valid_config()
    config["qdrant"]["prefer_grpc"] = False

    with pytest.raises(
        ValueError,
        match="prefer_grpc",
    ):
        validate_hybrid_evaluation_config(config)


def test_config_rejects_duplicate_top_k() -> None:
    config = valid_config()
    config["evaluation"]["top_k_values"] = [
        10,
        10,
    ]

    with pytest.raises(
        ValueError,
        match="duplicates",
    ):
        validate_hybrid_evaluation_config(config)


def test_config_rejects_invalid_safety_marker() -> None:
    config = deepcopy(valid_config())
    config["safety"][
        "public_qdrant_promoted"
    ] = True

    with pytest.raises(
        ValueError,
        match="public_qdrant_promoted",
    ):
        validate_hybrid_evaluation_config(config)


@pytest.mark.parametrize(
    (
        "top_k",
        "offset",
        "corpus_size",
        "expected",
    ),
    [
        (5, 0, 1_000, 50),
        (10, 0, 1_000, 50),
        (20, 0, 1_000, 100),
        (10, 80, 1_000, 90),
        (20, 0, 75, 75),
        (10, 0, 30, 30),
    ],
)
def test_public_candidate_k_matches_api_policy(
    top_k: int,
    offset: int,
    corpus_size: int,
    expected: int,
) -> None:
    helper_result = public_candidate_k(
        top_k=top_k,
        offset=offset,
        corpus_size=corpus_size,
    )

    api_result = _candidate_pool_size(
        requested_top_k=top_k,
        offset=offset,
        corpus_size=corpus_size,
    )

    assert helper_result == expected
    assert api_result == expected
    assert helper_result == api_result


def test_query_vector_fingerprint_is_stable() -> None:
    vector = np.asarray(
        [0.1, 0.2, 0.3],
        dtype=np.float32,
    )

    first = query_vector_fingerprint(vector)
    second = query_vector_fingerprint(
        vector.copy()
    )

    assert first == second
    assert first["dimension"] == 3
    assert first["dtype"] == "float32"
    assert first["all_finite"] is True
    assert len(first["sha256"]) == 64


def test_query_vector_fingerprint_changes() -> None:
    first = query_vector_fingerprint(
        np.asarray([0.1, 0.2], dtype=np.float32)
    )
    second = query_vector_fingerprint(
        np.asarray([0.1, 0.3], dtype=np.float32)
    )

    assert first["sha256"] != second["sha256"]


def test_compare_ranked_ids_exact() -> None:
    result = compare_ranked_ids(
        ["a", "b"],
        ["a", "b"],
        top_k=2,
    )

    assert result["overlap_ratio"] == 1.0
    assert result["same_set"] is True
    assert result["exact_same_order"] is True
    assert result["rank_change_count"] == 0
    assert (
        result["reference_digest"]
        == result["candidate_digest"]
    )


def test_compare_ranked_ids_records_rank_changes() -> None:
    result = compare_ranked_ids(
        ["a", "b", "c"],
        ["b", "a", "d"],
        top_k=3,
    )

    assert result["overlap_count"] == 2
    assert result["same_set"] is False
    assert result["exact_same_order"] is False
    assert result["rank_change_count"] == 2

    assert result["rank_changes"] == [
        {
            "canonical_id": "a",
            "reference_rank": 1,
            "candidate_rank": 2,
            "rank_delta": 1,
        },
        {
            "canonical_id": "b",
            "reference_rank": 2,
            "candidate_rank": 1,
            "rank_delta": -1,
        },
    ]


def test_metric_deltas_are_candidate_minus_reference(
) -> None:
    result = metric_deltas(
        {
            "recall": 0.5,
            "mrr": 0.75,
            "ndcg": 0.6,
        },
        {
            "recall": 0.6,
            "mrr": 0.5,
            "ndcg": 0.6,
        },
        metric_names=[
            "recall",
            "mrr",
            "ndcg",
        ],
    )

    assert result == pytest.approx(
        {
            "recall": 0.1,
            "mrr": -0.25,
            "ndcg": 0.0,
        }
    )


def test_determinism_summary_detects_stability(
) -> None:
    result = determinism_summary(
        [
            ["a", "b"],
            ["a", "b"],
        ]
    )

    assert result["stable"] is True
    assert result["unique_digest_count"] == 1
    assert result["mismatch_run_numbers"] == []


def test_determinism_summary_detects_difference(
) -> None:
    result = determinism_summary(
        [
            ["a", "b"],
            ["b", "a"],
            ["a", "b"],
        ]
    )

    assert result["stable"] is False
    assert result["unique_digest_count"] == 2
    assert result["mismatch_run_numbers"] == [2]


def test_classification_exact_match() -> None:
    result = classify_hybrid_difference(
        dense_comparison=exact_comparison(),
        final_comparison=exact_comparison(),
        deterministic=True,
    )

    assert result["classification"] == "exact_match"
    assert result["blocking"] is False


def test_classification_dense_difference_without_final_effect(
) -> None:
    result = classify_hybrid_difference(
        dense_comparison={
            "overlap_ratio": 0.98,
            "exact_same_order": False,
            "same_set": False,
        },
        final_comparison=exact_comparison(),
        deterministic=True,
    )

    assert result["classification"] == (
        "dense_candidate_difference_"
        "no_final_effect"
    )
    assert result["blocking"] is False


def test_classification_hydration_failure_is_blocking(
) -> None:
    result = classify_hybrid_difference(
        dense_comparison=exact_comparison(),
        final_comparison=exact_comparison(),
        deterministic=True,
        hydration_failure_count=1,
    )

    assert result["classification"] == (
        "hydration_defect"
    )
    assert result["blocking"] is True
    assert result["severity"] == "blocking"

def scoring_config() -> dict:
    return {
        "retrieval": {
            "hybrid": {
                "normalization": "minmax",
                "lexical_weight": 0.55,
                "dense_weight": 0.45,
            },
        },
        "ranking": {
            "weights": {
                "retrieval": 0.60,
                "recency": 0.20,
                "source_support": 0.10,
                "metadata_quality": 0.10,
            },
        },
    }


def test_build_scenario_matrix() -> None:
    scenarios = build_scenario_matrix(
        valid_config(),
        corpus_size=60_954,
    )

    assert scenarios == [
        {
            "scenario_id": (
                "top10__candidate50__unranked"
            ),
            "top_k": 10,
            "candidate_k": 50,
            "rank": False,
            "offset": 0,
            "sort_by": "relevance",
            "normalization": "minmax",
            "lexical_weight": 0.55,
            "dense_weight": 0.45,
        },
        {
            "scenario_id": (
                "top10__candidate50__ranked"
            ),
            "top_k": 10,
            "candidate_k": 50,
            "rank": True,
            "offset": 0,
            "sort_by": "relevance",
            "normalization": "minmax",
            "lexical_weight": 0.55,
            "dense_weight": 0.45,
        },
        {
            "scenario_id": (
                "top20__candidate100__unranked"
            ),
            "top_k": 20,
            "candidate_k": 100,
            "rank": False,
            "offset": 0,
            "sort_by": "relevance",
            "normalization": "minmax",
            "lexical_weight": 0.55,
            "dense_weight": 0.45,
        },
        {
            "scenario_id": (
                "top20__candidate100__ranked"
            ),
            "top_k": 20,
            "candidate_k": 100,
            "rank": True,
            "offset": 0,
            "sort_by": "relevance",
            "normalization": "minmax",
            "lexical_weight": 0.55,
            "dense_weight": 0.45,
        },
    ]


def test_dense_candidates_to_score_rows() -> None:
    candidates = [
        SimpleNamespace(
            canonical_id="a",
            score=0.9,
            rank=1,
            dense_index=4,
            backend_point_id=4,
            backend_metadata={
                "payload": {
                    "canonical_id": "a",
                }
            },
        ),
        SimpleNamespace(
            canonical_id="b",
            score=0.8,
            rank=2,
            dense_index=7,
            backend_point_id=7,
            backend_metadata={},
        ),
    ]

    rows = dense_candidates_to_score_rows(
        candidates
    )

    assert rows == [
        {
            "canonical_id": "a",
            "score": 0.9,
            "rank": 1,
            "dense_index": 4,
            "backend_point_id": 4,
            "backend_metadata": {
                "payload": {
                    "canonical_id": "a",
                }
            },
        },
        {
            "canonical_id": "b",
            "score": 0.8,
            "rank": 2,
            "dense_index": 7,
            "backend_point_id": 7,
            "backend_metadata": {},
        },
    ]


def test_dense_candidates_reject_duplicate_ids(
) -> None:
    candidates = [
        SimpleNamespace(
            canonical_id="a",
            score=0.9,
            rank=1,
            dense_index=1,
            backend_point_id=1,
            backend_metadata={},
        ),
        SimpleNamespace(
            canonical_id="a",
            score=0.8,
            rank=2,
            dense_index=2,
            backend_point_id=2,
            backend_metadata={},
        ),
    ]

    with pytest.raises(
        ValueError,
        match="Duplicate dense candidate",
    ):
        dense_candidates_to_score_rows(candidates)


def test_dense_candidates_reject_rank_gap() -> None:
    candidates = [
        SimpleNamespace(
            canonical_id="a",
            score=0.9,
            rank=2,
            dense_index=1,
            backend_point_id=1,
            backend_metadata={},
        ),
    ]

    with pytest.raises(
        ValueError,
        match="continuous",
    ):
        dense_candidates_to_score_rows(candidates)


def test_strict_hydration() -> None:
    document = SimpleNamespace(
        canonical_id="a",
        title="Paper A",
        year=2025,
        doi="10.1/a",
        source_count=2,
    )

    rows = strict_hydrate_score_rows(
        [
            {
                "canonical_id": "a",
                "hybrid_score": 0.8,
                "lexical_score": 0.7,
                "dense_score": 0.9,
            }
        ],
        documents_by_id={
            "a": document,
        },
    )

    assert rows[0]["document"] is document
    assert rows[0]["title"] == "Paper A"
    assert rows[0]["year"] == 2025
    assert rows[0]["source_count"] == 2


def test_strict_hydration_rejects_missing_document(
) -> None:
    with pytest.raises(
        ValueError,
        match="Canonical hydration failed",
    ):
        strict_hydrate_score_rows(
            [
                {
                    "canonical_id": "missing",
                    "hybrid_score": 0.8,
                    "lexical_score": 0.7,
                    "dense_score": 0.9,
                }
            ],
            documents_by_id={},
        )


def test_resolve_scoring_params() -> None:
    params = resolve_scoring_params(
        scoring_config()
    )

    assert params == {
        "normalization": "minmax",
        "hybrid_lexical_weight": 0.55,
        "hybrid_dense_weight": 0.45,
        "ranking_retrieval_weight": 0.60,
        "ranking_recency_weight": 0.20,
        "ranking_source_support_weight": 0.10,
        "ranking_metadata_quality_weight": 0.10,
    }


def test_public_scoring_contract_passes() -> None:
    params = validate_public_scoring_contract(
        valid_config(),
        scoring_config(),
    )

    assert params[
        "hybrid_lexical_weight"
    ] == pytest.approx(0.55)


def test_public_scoring_contract_rejects_weight_drift(
) -> None:
    config = valid_config()
    config["evaluation"]["hybrid"][
        "lexical_weight"
    ] = 0.40

    with pytest.raises(
        ValueError,
        match="does not match public scoring",
    ):
        validate_public_scoring_contract(
            config,
            scoring_config(),
        )
