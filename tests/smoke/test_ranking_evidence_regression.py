from __future__ import annotations

from pathlib import Path

from scripts.validation.check_ranking_evidence_regression import (
    build_ranking_evidence_regression_report,
)


def _metric(value: float) -> dict[str, float]:
    return {
        "hit": value,
        "precision": value,
        "recall": value,
        "mrr": value,
        "ndcg": value,
    }


def _candidate(canonical_id: str, rank: int, final_score: float | None) -> dict:
    return {
        "canonical_id": canonical_id,
        "title": canonical_id,
        "relevant": canonical_id == "a",
        "relevance_grade": 3.0 if canonical_id == "a" else 0.0,
        "rank_before": rank,
        "rank_after": rank,
        "rank_delta": 0,
        "retrieval_score_raw": 1.0 - rank * 0.1,
        "retrieval_score_normalized": 1.0 - (rank - 1) * 0.5,
        "recency_score": 0.5,
        "source_support_score": 0.5,
        "metadata_quality_score": 0.5,
        "final_score": final_score,
        "year": 2024,
        "source_count": 2,
    }


def _run(profile_name: str, apply_ranking: bool) -> dict:
    ids = ["a", "b"]
    metric = {"10": _metric(1.0)}
    return {
        "query_id": "q1",
        "query": "ranking",
        "group": "test",
        "candidate_k": 2,
        "profile_name": profile_name,
        "apply_ranking": apply_ranking,
        "weights": {
            "retrieval": 1.0,
            "recency": 0.0,
            "source_support": 0.0,
            "metadata_quality": 0.0,
        }
        if apply_ranking
        else None,
        "results_count": 2,
        "candidate_count": 2,
        "result_ids_before": ids,
        "result_ids_after": ids,
        "metrics_before": metric,
        "metrics_after": metric,
        "metric_deltas": {"10": _metric(0.0)},
        "effect_classification": "ranking_no_effect"
        if apply_ranking
        else None,
        "classification_details": {},
        "moved_candidate_count": 0,
        "relevant_moved_up_count": 0,
        "relevant_moved_down_count": 0,
        "relevant_added_to_top_k": [],
        "relevant_removed_from_top_k": [],
        "candidate_evidence": [
            _candidate("a", 1, 1.0 if apply_ranking else None),
            _candidate("b", 2, 0.0 if apply_ranking else None),
        ],
        "determinism": {
            "repeats": 2,
            "order_equal": True,
            "scores_equal_within_tolerance": True,
            "ok": True,
        },
        "timings": {},
        "error": None,
    }


def _config() -> dict:
    return {
        "metadata": {"public_behavior_change": False},
        "defaults": {
            "candidate_k_values": [2],
            "metric_k_values": [10],
            "primary_k": 10,
            "numeric_tolerance": 1e-12,
        },
        "profiles": [
            {"name": "unranked", "apply_ranking": False},
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
        "classifications": {"primary": ["ranking_no_effect"]},
        "analysis": {
            "quality_composite_weights": {
                "recall": 0.4,
                "ndcg": 0.4,
                "mrr": 0.2,
            }
        },
        "thresholds": {
            "min_enabled_cases": 1,
            "expected_profiles_count": 2,
            "expected_candidate_depths_count": 1,
        },
        "decision_policy": {
            "change_public_default_during_evaluation": False,
            "permitted_outcomes": ["reject_heuristic_reranking"],
        },
    }


def _profile_summary(profile_name: str) -> dict:
    return {
        "profile_name": profile_name,
        "runs_count": 1,
        "classification_counts": {"ranking_no_effect": 1}
        if profile_name == "retrieval_only"
        else {},
        "relevant_removed_from_top_k_count": 0,
        "relevant_added_to_top_k_count": 0,
        "mean_moved_candidate_count": 0.0,
        "hit_at_10": 1.0,
        "precision_at_10": 1.0,
        "recall_at_10": 1.0,
        "mrr_at_10": 1.0,
        "ndcg_at_10": 1.0,
        "quality_composite": 1.0,
    }


def _sensitivity_row(profile_name: str) -> dict:
    return {
        "query_id": "q1",
        "query": "ranking",
        "profile_name": profile_name,
        "smaller_candidate_k": 2,
        "larger_candidate_k": 2,
        "shared_candidate_count": 2,
        "component_changes": {
            "retrieval_score_normalized": {
                "mean_abs_change": 0.0,
                "max_abs_change": 0.0,
                "changed_count": 0,
            },
            "recency_score": {
                "mean_abs_change": 0.0,
                "max_abs_change": 0.0,
                "changed_count": 0,
            },
            "source_support_score": {
                "mean_abs_change": 0.0,
                "max_abs_change": 0.0,
                "changed_count": 0,
            },
            "metadata_quality_score": {
                "mean_abs_change": 0.0,
                "max_abs_change": 0.0,
                "changed_count": 0,
            },
            "final_score": {
                "mean_abs_change": 0.0,
                "max_abs_change": 0.0,
                "changed_count": 0,
            },
        },
        "top_k_overlap_count": 2,
        "top_k_overlap_ratio": 1.0,
        "top_k_set_equal": True,
        "top_k_order_equal": True,
        "metric_deltas": {"10": _metric(0.0)},
    }


def _evaluation_report(build_id: str = "build-a") -> dict:
    return {
        "schema_version": "ranking_evaluation_v1",
        "report_name": "ranking_evaluation",
        "runtime": {
            "ready": True,
            "backend_mode": "file",
            "build_id": build_id,
            "corpus_doc_count": 2,
            "embedding_model_name": "model-a",
        },
        "summary": {
            "total_cases_count": 1,
            "enabled_cases_count": 1,
            "profiles_count": 2,
            "candidate_depths_count": 1,
            "expected_runs_count": 2,
            "runs_count": 2,
            "error_count": 0,
            "ranked_comparisons_count": 1,
            "classification_counts": {"ranking_no_effect": 1},
            "determinism_failure_count": 0,
            "candidate_pool_sensitivity_rows_count": 2,
        },
        "query_cache_meta": [{"query_id": "q1", "query": "ranking"}],
        "profiles": _config()["profiles"],
        "runs": [
            _run("unranked", False),
            _run("retrieval_only", True),
        ],
        "profile_summary": [
            _profile_summary("unranked"),
            _profile_summary("retrieval_only"),
        ],
        "profile_depth_summary": [
            {"profile_name": "unranked", "candidate_k": 2},
            {"profile_name": "retrieval_only", "candidate_k": 2},
        ],
        # Non-strict integrity still requires the sensitivity block to be
        # present. The real accepted report has 306 rows; this synthetic
        # fixture only needs minimal placeholder rows.
        "candidate_pool_sensitivity": [
            _sensitivity_row("unranked"),
            _sensitivity_row("retrieval_only"),
        ],
        "decision": {
            "recommended_outcome": "reject_heuristic_reranking",
            "automatic_public_change_allowed": False,
            "requires_manual_review": True,
            "requires_strict_validator": True,
            "best_ranked_profile": "retrieval_only",
            "unranked_quality_composite": 1.0,
            "current_quality_composite": 1.0,
            "current_relevant_removed_from_top_k_count": 0,
            "best_ranked_quality_composite": 1.0,
        },
    }


def _manifest(build_id: str = "build-a") -> dict:
    return {
        "build_id": build_id,
        "corpus_doc_count": 2,
        "embedding_model_name": "model-a",
        "corpus_fingerprint": "fp",
    }


def test_regression_report_passes_non_strict_gate(tmp_path: Path) -> None:
    report_path = tmp_path / "ranking.json"
    manifest_path = tmp_path / "latest.json"
    report_path.write_text("{}", encoding="utf-8")
    manifest_path.write_text("{}", encoding="utf-8")

    report = build_ranking_evidence_regression_report(
        config=_config(),
        evaluation_report=_evaluation_report(),
        retrieval_manifest=_manifest(),
        config_path=tmp_path / "config.yaml",
        report_path=report_path,
        retrieval_manifest_path=manifest_path,
        strict=False,
    )

    assert report["ok"] is True
    assert report["required_failed_count"] == 0
    assert report["checks"]["regression"][
        "ranking_evaluation_integrity_passed"
    ] is True
    assert report["checks"]["regression"][
        "ranking_evaluation_freshness_passed"
    ] is True


def test_regression_report_fails_when_report_is_stale(tmp_path: Path) -> None:
    report_path = tmp_path / "ranking.json"
    manifest_path = tmp_path / "latest.json"
    report_path.write_text("{}", encoding="utf-8")
    manifest_path.write_text("{}", encoding="utf-8")

    report = build_ranking_evidence_regression_report(
        config=_config(),
        evaluation_report=_evaluation_report(build_id="old"),
        retrieval_manifest=_manifest(build_id="new"),
        config_path=tmp_path / "config.yaml",
        report_path=report_path,
        retrieval_manifest_path=manifest_path,
        strict=False,
    )

    assert report["ok"] is False
    assert any(
        item.endswith("build_id_matches_current_retrieval_manifest")
        for item in report["required_failed_checks"]
    )


def test_regression_report_fails_on_disallowed_decision(tmp_path: Path) -> None:
    report_path = tmp_path / "ranking.json"
    manifest_path = tmp_path / "latest.json"
    report_path.write_text("{}", encoding="utf-8")
    manifest_path.write_text("{}", encoding="utf-8")

    evaluation_report = _evaluation_report()
    evaluation_report["decision"]["recommended_outcome"] = "unknown"

    report = build_ranking_evidence_regression_report(
        config=_config(),
        evaluation_report=evaluation_report,
        retrieval_manifest=_manifest(),
        config_path=tmp_path / "config.yaml",
        report_path=report_path,
        retrieval_manifest_path=manifest_path,
        strict=False,
    )

    assert report["ok"] is False
    assert (
        "regression::recommended_outcome_is_permitted"
        in report["required_failed_checks"]
    )


def test_regression_report_fails_when_public_change_is_allowed(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "ranking.json"
    manifest_path = tmp_path / "latest.json"
    report_path.write_text("{}", encoding="utf-8")
    manifest_path.write_text("{}", encoding="utf-8")

    evaluation_report = _evaluation_report()
    evaluation_report["decision"]["automatic_public_change_allowed"] = True

    report = build_ranking_evidence_regression_report(
        config=_config(),
        evaluation_report=evaluation_report,
        retrieval_manifest=_manifest(),
        config_path=tmp_path / "config.yaml",
        report_path=report_path,
        retrieval_manifest_path=manifest_path,
        strict=False,
    )

    assert report["ok"] is False
    assert (
        "regression::public_behavior_change_disabled"
        in report["required_failed_checks"]
    )
