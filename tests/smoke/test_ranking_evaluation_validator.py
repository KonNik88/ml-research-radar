from __future__ import annotations

from pathlib import Path

from scripts.validation.check_ranking_evaluation import (
    build_checks,
    required_check_names,
)


def _metric_row(value: float) -> dict[str, float]:
    return {
        "hit": value,
        "precision": value,
        "recall": value,
        "mrr": value,
        "ndcg": value,
    }


def _candidate(
    canonical_id: str,
    rank: int,
    *,
    final_score: float | None,
) -> dict:
    return {
        "canonical_id": canonical_id,
        "title": canonical_id,
        "relevant": canonical_id == "a",
        "relevance_grade": 3.0 if canonical_id == "a" else 0.0,
        "rank_before": rank,
        "rank_after": rank,
        "rank_delta": 0,
        "retrieval_score_raw": 1.0 - (rank - 1) * 0.1,
        "retrieval_score_normalized": 1.0 - (rank - 1) * 0.5,
        "recency_score": 0.5,
        "source_support_score": 0.5,
        "metadata_quality_score": 0.5,
        "final_score": final_score,
        "year": 2024,
        "source_count": 2,
    }


def _run(
    *,
    candidate_k: int,
    profile_name: str,
    apply_ranking: bool,
) -> dict:
    ids = ["a", "b"]
    metric = {"1": _metric_row(1.0), "2": _metric_row(1.0)}
    evidence = [
        _candidate(
            "a",
            1,
            final_score=1.0 if apply_ranking else None,
        ),
        _candidate(
            "b",
            2,
            final_score=0.0 if apply_ranking else None,
        ),
    ]
    return {
        "query_id": "q1",
        "query": "ranking",
        "group": "test",
        "candidate_k": candidate_k,
        "profile_name": profile_name,
        "apply_ranking": apply_ranking,
        "weights": (
            {
                "retrieval": 1.0,
                "recency": 0.0,
                "source_support": 0.0,
                "metadata_quality": 0.0,
            }
            if apply_ranking
            else None
        ),
        "results_count": 2,
        "candidate_count": 2,
        "result_ids_before": ids,
        "result_ids_after": ids,
        "metrics_before": metric,
        "metrics_after": metric,
        "metric_deltas": {
            "1": _metric_row(0.0),
            "2": _metric_row(0.0),
        },
        "effect_classification": (
            "ranking_no_effect"
            if apply_ranking
            else None
        ),
        "classification_details": {},
        "moved_candidate_count": 0,
        "relevant_moved_up_count": 0,
        "relevant_moved_down_count": 0,
        "relevant_added_to_top_k": [],
        "relevant_removed_from_top_k": [],
        "candidate_evidence": evidence,
        "determinism": {
            "repeats": 2,
            "order_equal": True,
            "scores_equal_within_tolerance": True,
            "ok": True,
        },
        "timings": {
            "hybrid_merge_ms": 1.0,
            "ranking_evaluation_ms": 1.0,
        },
        "error": None,
    }


def _config() -> dict:
    return {
        "schema_version": "ranking_evaluation_v1",
        "metadata": {
            "public_behavior_change": False,
        },
        "defaults": {
            "backend_mode": "file",
            "candidate_k_values": [2, 3],
            "metric_k_values": [1, 2],
            "primary_k": 2,
            "numeric_tolerance": 1.0e-12,
        },
        "profiles": [
            {
                "name": "unranked",
                "apply_ranking": False,
            },
            {
                "name": "retrieval_only",
                "apply_ranking": True,
                "weights": {
                    "retrieval": 1.0,
                    "recency": 0.0,
                    "source_support": 0.0,
                    "metadata_quality": 0.0,
                },
            },
        ],
        "classifications": {
            "primary": [
                "ranking_no_effect",
            ]
        },
        "analysis": {
            "quality_composite_weights": {
                "recall": 0.40,
                "ndcg": 0.40,
                "mrr": 0.20,
            }
        },
        "thresholds": {
            "min_enabled_cases": 1,
            "expected_profiles_count": 2,
            "expected_candidate_depths_count": 2,
        },
        "decision_policy": {
            "change_public_default_during_evaluation": False,
            "permitted_outcomes": [
                "reject_heuristic_reranking",
            ],
        },
    }


def _profile_summary(profile_name: str) -> dict:
    return {
        "profile_name": profile_name,
        "runs_count": 2,
        "classification_counts": (
            {"ranking_no_effect": 2}
            if profile_name == "retrieval_only"
            else {}
        ),
        "relevant_removed_from_top_k_count": 0,
        "relevant_added_to_top_k_count": 0,
        "mean_moved_candidate_count": 0.0,
        "hit_at_1": 1.0,
        "precision_at_1": 1.0,
        "recall_at_1": 1.0,
        "mrr_at_1": 1.0,
        "ndcg_at_1": 1.0,
        "hit_at_2": 1.0,
        "precision_at_2": 1.0,
        "recall_at_2": 1.0,
        "mrr_at_2": 1.0,
        "ndcg_at_2": 1.0,
        "quality_composite": 1.0,
    }


def _report() -> dict:
    runs = [
        _run(
            candidate_k=candidate_k,
            profile_name=profile_name,
            apply_ranking=profile_name == "retrieval_only",
        )
        for candidate_k in (2, 3)
        for profile_name in ("unranked", "retrieval_only")
    ]

    sensitivity = [
        {
            "query_id": "q1",
            "query": "ranking",
            "profile_name": profile_name,
            "smaller_candidate_k": 2,
            "larger_candidate_k": 3,
            "shared_candidate_count": 2,
            "component_changes": {
                "retrieval_score_normalized": {
                    "mean_abs_change": 0.0,
                    "max_abs_change": 0.0,
                    "changed_count": 0,
                }
            },
            "top_k_overlap_count": 2,
            "top_k_overlap_ratio": 1.0,
            "top_k_set_equal": True,
            "top_k_order_equal": True,
            "metric_deltas": {
                "1": _metric_row(0.0),
                "2": _metric_row(0.0),
            },
        }
        for profile_name in ("unranked", "retrieval_only")
    ]

    return {
        "schema_version": "ranking_evaluation_v1",
        "report_name": "ranking_evaluation",
        "runtime": {
            "backend_mode": "file",
            "ready": True,
            "build_id": "test-build",
            "corpus_doc_count": 2,
        },
        "summary": {
            "total_cases_count": 1,
            "enabled_cases_count": 1,
            "profiles_count": 2,
            "candidate_depths_count": 2,
            "expected_runs_count": 4,
            "runs_count": 4,
            "error_count": 0,
            "ranked_comparisons_count": 2,
            "classification_counts": {
                "ranking_no_effect": 2,
            },
            "determinism_failure_count": 0,
            "candidate_pool_sensitivity_rows_count": 2,
        },
        "query_cache_meta": [
            {
                "query_id": "q1",
                "query": "ranking",
                "max_candidate_k": 3,
            }
        ],
        "profiles": _config()["profiles"],
        "runs": runs,
        "profile_depth_summary": [
            {
                "profile_name": profile_name,
                "candidate_k": candidate_k,
            }
            for profile_name in ("unranked", "retrieval_only")
            for candidate_k in (2, 3)
        ],
        "profile_summary": [
            _profile_summary("unranked"),
            _profile_summary("retrieval_only"),
        ],
        "candidate_pool_sensitivity": sensitivity,
        "decision": {
            "status": "preliminary_evidence_only",
            "automatic_public_change_allowed": False,
            "recommended_outcome": "reject_heuristic_reranking",
            "reason": "Synthetic test outcome.",
            "unranked_quality_composite": 1.0,
            "current_quality_composite": 1.0,
            "current_relevant_removed_from_top_k_count": 0,
            "best_ranked_profile": "retrieval_only",
            "best_ranked_quality_composite": 1.0,
            "requires_manual_review": True,
            "requires_strict_validator": True,
        },
    }


def test_valid_synthetic_report_passes_all_strict_checks() -> None:
    checks, diagnostics, _ = build_checks(
        config=_config(),
        report=_report(),
        report_path=Path("synthetic.json"),
    )

    # The synthetic path does not physically exist; all semantic checks
    # should still pass.
    semantic_required = [
        name
        for name in required_check_names(strict=True)
        if name != "report_path_exists"
    ]

    assert diagnostics == {}
    assert all(checks[name] for name in semantic_required)


def test_retrieval_only_order_change_fails_invariant() -> None:
    report = _report()
    for run in report["runs"]:
        if (
            run["profile_name"] == "retrieval_only"
            and run["candidate_k"] == 2
        ):
            run["result_ids_after"] = ["b", "a"]
            break

    checks, diagnostics, _ = build_checks(
        config=_config(),
        report=report,
        report_path=Path("synthetic.json"),
    )

    assert checks["retrieval_only_matches_unranked"] is False
    assert "retrieval_only_invariant" in diagnostics


def test_non_permitted_decision_fails() -> None:
    report = _report()
    report["decision"]["recommended_outcome"] = "unknown_outcome"

    checks, _, _ = build_checks(
        config=_config(),
        report=report,
        report_path=Path("synthetic.json"),
    )

    assert checks["decision_outcome_permitted"] is False
