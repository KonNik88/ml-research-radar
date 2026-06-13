from __future__ import annotations

from copy import deepcopy

from scripts.validation.check_qdrant_hybrid_evaluation import (
    evaluate_report,
)


def config(
    *,
    expected_queries: int = 2,
) -> dict:
    return {
        "qdrant": {
            "collection_name": "collection",
            "prefer_grpc": True,
            "profile": {
                "name": "ef_256",
                "exact": False,
                "hnsw_ef": 256,
            },
        },
        "evaluation": {
            "max_queries": None,
        },
        "quality": {
            "expected_enabled_query_count": (
                expected_queries
            ),
            "require_full_query_set": True,
            "min_mean_final_overlap_at_k": 0.99,
            "min_query_final_overlap_at_k": 0.95,
        },
    }


def sha(character: str) -> str:
    return character * 64


def determinism() -> dict:
    summary = {
        "run_count": 2,
        "stable": True,
        "reference_digest": sha("a"),
        "unique_digest_count": 1,
        "run_digests": [
            sha("a"),
            sha("a"),
        ],
        "mismatch_run_numbers": [],
    }

    return {
        "stable": True,
        "file_dense": deepcopy(summary),
        "qdrant_dense": deepcopy(summary),
        "file_final": deepcopy(summary),
        "qdrant_final": deepcopy(summary),
    }


def branch(
    *,
    name: str,
    build_id: str,
) -> dict:
    return {
        "backend": {
            "name": name,
            "implementation": f"Fake{name}",
            "build_id": build_id,
            "ready": True,
        },
        "dense_ids": ["a", "b"],
        "final_ids": ["a", "b"],
        "metrics": {
            "hit": 1.0,
            "precision": 0.5,
            "recall": 1.0,
            "mrr": 1.0,
            "ndcg": 1.0,
        },
        "timing_ms": {
            "dense_wall_ms": 1.0,
            "backend_search_ms": 0.8,
            "merge_ms": 0.1,
            "hydrate_ms": 0.1,
            "rank_ms": 0.0,
        },
    }


def comparison() -> dict:
    item = {
        "overlap_count": 2,
        "overlap_ratio": 1.0,
        "same_set": True,
        "exact_same_order": True,
        "reference_digest": sha("b"),
        "candidate_digest": sha("b"),
        "rank_changes": [],
        "rank_change_count": 0,
    }

    return {
        "dense": deepcopy(item),
        "final": deepcopy(item),
        "metric_deltas": {
            "hit": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "mrr": 0.0,
            "ndcg": 0.0,
        },
        "classification": "exact_match",
        "severity": "diagnostic",
        "blocking": False,
        "reason": "Exact match.",
    }


def scenario(
    *,
    scenario_id: str,
    top_k: int,
    candidate_k: int,
    rank: bool,
) -> dict:
    return {
        "scenario_id": scenario_id,
        "top_k": top_k,
        "candidate_k": candidate_k,
        "rank": rank,
        "shared": {
            "query_vector": {
                "dimension": 2,
                "dtype": "float32",
                "norm": 1.0,
                "all_finite": True,
                "sha256": sha("c"),
            },
            "lexical": {
                "count": candidate_k,
                "ids_digest": sha("d"),
                "ids_and_scores_sha256": (
                    sha("e")
                ),
            },
            "lexical_weight": 0.55,
            "dense_weight": 0.45,
            "normalization": "minmax",
        },
        "file": branch(
            name="file",
            build_id="build-1",
        ),
        "qdrant": branch(
            name="qdrant",
            build_id="build-1",
        ),
        "comparison": comparison(),
        "determinism": determinism(),
        "repeat_count": 2,
        "error": None,
    }


def valid_report(
    *,
    query_count: int = 2,
) -> dict:
    matrix = [
        {
            "scenario_id": (
                "top2__candidate2__unranked"
            ),
            "top_k": 2,
            "candidate_k": 2,
            "rank": False,
        },
        {
            "scenario_id": (
                "top2__candidate2__ranked"
            ),
            "top_k": 2,
            "candidate_k": 2,
            "rank": True,
        },
    ]

    query_results = []

    for index in range(query_count):
        query_results.append(
            {
                "query_id": f"q{index}",
                "query": "query",
                "scenarios": [
                    scenario(
                        scenario_id=(
                            "top2__candidate2__"
                            "unranked"
                        ),
                        top_k=2,
                        candidate_k=2,
                        rank=False,
                    ),
                    scenario(
                        scenario_id=(
                            "top2__candidate2__"
                            "ranked"
                        ),
                        top_k=2,
                        candidate_k=2,
                        rank=True,
                    ),
                ],
                "error": None,
            }
        )

    expected = query_count * len(matrix)

    return {
        "schema_version": (
            "qdrant_hybrid_evaluation_v1"
        ),
        "report_name": (
            "qdrant_hybrid_evaluation"
        ),
        "generated_at_utc": (
            "2026-06-13T00:00:00+00:00"
        ),
        "config": {},
        "safety": {
            "evaluation_only": True,
            "production_default_changed": False,
            "public_qdrant_promoted": False,
            "fallback_used": False,
            "canonical_data_changed": False,
            "retrieval_build_changed": False,
            "qdrant_collection_mutated": False,
        },
        "runtime": {
            "backend_mode": "file",
            "ready": True,
            "build_id": "build-1",
            "corpus_doc_count": 10,
            "embedding_model_name": "model",
            "embedding_shape": [10, 2],
        },
        "qdrant": {
            "collection_name": "collection",
            "transport": "grpc",
            "profile": {
                "name": "ef_256",
                "exact": False,
                "hnsw_ef": 256,
            },
        },
        "scenario_matrix": matrix,
        "summary": {
            "enabled_query_count": query_count,
            "selected_query_count": query_count,
            "scenario_count_per_query": (
                len(matrix)
            ),
            "expected_scenario_count": expected,
            "successful_scenario_count": expected,
            "error_count": 0,
            "complete": True,
            "quality_ok": True,
            "dense_overlap": {
                "mean": 1.0,
                "min": 1.0,
            },
            "final_overlap": {
                "mean": 1.0,
                "min": 1.0,
            },
            "blocking_classification_count": 0,
            "blocking_classifications": [],
            "determinism_failure_count": 0,
            "determinism_failures": [],
            "classification_counts": {
                "exact_match": expected,
            },
        },
        "query_results": query_results,
        "errors": [],
        "verdict": {
            "ok": True,
            "error_count": 0,
            "blocking_classification_count": 0,
            "determinism_failure_count": 0,
        },
    }


def test_valid_full_report_passes_strict() -> None:
    result = evaluate_report(
        valid_report(),
        config=config(),
        strict=True,
    )

    assert result["ok"] is True
    assert result[
        "required_failed_checks"
    ] == []


def test_smoke_report_passes_non_strict() -> None:
    result = evaluate_report(
        valid_report(query_count=1),
        config=config(expected_queries=2),
        strict=False,
    )

    assert result["ok"] is True


def test_smoke_report_fails_full_strict_gate(
) -> None:
    result = evaluate_report(
        valid_report(query_count=1),
        config=config(expected_queries=2),
        strict=True,
    )

    assert result["ok"] is False
    assert (
        "enabled_query_count_expected"
        in result["required_failed_checks"]
    )


def test_fallback_marker_fails() -> None:
    report = valid_report()
    report["safety"]["fallback_used"] = True

    result = evaluate_report(
        report,
        config=config(),
        strict=True,
    )

    assert result["ok"] is False
    assert (
        "safety_no_fallback"
        in result["required_failed_checks"]
    )


def test_missing_scenario_fails() -> None:
    report = valid_report()
    report["query_results"][0][
        "scenarios"
    ].pop()

    result = evaluate_report(
        report,
        config=config(),
        strict=True,
    )

    assert result["ok"] is False
    assert (
        "scenario_coverage_valid"
        in result["required_failed_checks"]
    )


def test_query_vector_mismatch_fails() -> None:
    report = valid_report()

    report["query_results"][0][
        "scenarios"
    ][1]["shared"]["query_vector"][
        "sha256"
    ] = sha("f")

    result = evaluate_report(
        report,
        config=config(),
        strict=True,
    )

    assert result["ok"] is False
    assert (
        "shared_evidence_valid"
        in result["required_failed_checks"]
    )


def test_blocking_classification_fails_strict(
) -> None:
    report = valid_report()

    scenario_row = report[
        "query_results"
    ][0]["scenarios"][0]

    scenario_row["comparison"][
        "classification"
    ] = "hydration_defect"
    scenario_row["comparison"][
        "blocking"
    ] = True

    report["summary"][
        "blocking_classification_count"
    ] = 1
    report["summary"][
        "blocking_classifications"
    ] = [
        {
            "query_id": "q0",
            "scenario_id": (
                scenario_row["scenario_id"]
            ),
        }
    ]
    report["summary"]["quality_ok"] = False
    report["verdict"]["ok"] = False

    result = evaluate_report(
        report,
        config=config(),
        strict=True,
    )

    assert result["ok"] is False
    assert (
        "no_blocking_classifications"
        in result["required_failed_checks"]
    )


def test_non_finite_timing_fails() -> None:
    report = valid_report()

    report["query_results"][0][
        "scenarios"
    ][0]["qdrant"]["timing_ms"][
        "dense_wall_ms"
    ] = float("nan")

    result = evaluate_report(
        report,
        config=config(),
        strict=True,
    )

    assert result["ok"] is False
    assert (
        "timings_valid"
        in result["required_failed_checks"]
    )
    assert (
        "all_numbers_finite"
        in result["required_failed_checks"]
    )