from __future__ import annotations

from scripts.evaluation.summarize_ranking_evaluation import (
    aggregate_sensitivity,
    build_analysis,
    build_profile_comparison,
    compact_query_run,
)


def _metric(value: float) -> dict[str, float]:
    return {
        "hit": value,
        "precision": value,
        "recall": value,
        "mrr": value,
        "ndcg": value,
    }


def _candidate(
    canonical_id: str,
    *,
    rank_before: int,
    rank_after: int,
    relevant: bool,
) -> dict:
    return {
        "canonical_id": canonical_id,
        "title": canonical_id,
        "relevant": relevant,
        "relevance_grade": 3.0 if relevant else 0.0,
        "rank_before": rank_before,
        "rank_after": rank_after,
        "rank_delta": rank_before - rank_after,
        "retrieval_score_raw": 1.0,
        "retrieval_score_normalized": 0.8,
        "recency_score": 0.4,
        "source_support_score": 0.3,
        "metadata_quality_score": 0.9,
        "final_score": 0.7,
        "year": 2024,
        "source_count": 2,
    }


def _run(
    *,
    profile_name: str,
    candidate_k: int,
    delta: float,
    removed: bool = False,
) -> dict:
    evidence = [
        _candidate(
            "relevant",
            rank_before=1,
            rank_after=2 if removed else 1,
            relevant=True,
        ),
        _candidate(
            "other",
            rank_before=2,
            rank_after=1 if removed else 2,
            relevant=False,
        ),
    ]
    return {
        "query_id": "q1",
        "query": "ranking",
        "group": "test",
        "candidate_k": candidate_k,
        "profile_name": profile_name,
        "effect_classification": (
            "ranking_removed_relevant_from_top_k"
            if removed
            else "ranking_no_effect"
        ),
        "metric_deltas": {
            "10": {
                "hit": delta,
                "precision": delta,
                "recall": delta,
                "mrr": delta,
                "ndcg": delta,
            }
        },
        "moved_candidate_count": 2 if removed else 0,
        "relevant_moved_up_count": 0,
        "relevant_moved_down_count": 1 if removed else 0,
        "relevant_added_to_top_k": [],
        "relevant_removed_from_top_k": (
            ["relevant"] if removed else []
        ),
        "candidate_evidence": evidence,
        "result_ids_before": ["relevant", "other"],
        "result_ids_after": (
            ["other", "relevant"] if removed else ["relevant", "other"]
        ),
        "error": None,
    }


def _report() -> dict:
    runs = [
        _run(
            profile_name="current",
            candidate_k=50,
            delta=-0.2,
            removed=True,
        ),
        _run(
            profile_name="current",
            candidate_k=100,
            delta=0.0,
        ),
        _run(
            profile_name="retrieval_plus_metadata_quality",
            candidate_k=50,
            delta=0.0,
        ),
    ]
    return {
        "schema_version": "ranking_evaluation_v1",
        "generated_at_utc": "2026-06-17T00:00:00+00:00",
        "run_ts": "20260617T000000Z",
        "runtime": {
            "backend_mode": "file",
            "build_id": "test-build",
            "corpus_doc_count": 2,
            "ready": True,
        },
        "summary": {
            "runs_count": 3,
        },
        "decision": {
            "recommended_outcome": "reject_heuristic_reranking",
            "best_ranked_profile": "retrieval_plus_metadata_quality",
        },
        "profile_summary": [
            {
                "profile_name": "unranked",
                "quality_composite": 0.80,
                "recall_at_10": 0.80,
                "ndcg_at_10": 0.80,
                "mrr_at_10": 0.80,
                "mean_moved_candidate_count": 0.0,
                "relevant_added_to_top_k_count": 0,
                "relevant_removed_from_top_k_count": 0,
                "classification_counts": {},
            },
            {
                "profile_name": "current",
                "quality_composite": 0.60,
                "recall_at_10": 0.60,
                "ndcg_at_10": 0.60,
                "mrr_at_10": 0.60,
                "mean_moved_candidate_count": 1.0,
                "relevant_added_to_top_k_count": 0,
                "relevant_removed_from_top_k_count": 1,
                "classification_counts": {
                    "ranking_removed_relevant_from_top_k": 1,
                    "ranking_no_effect": 1,
                },
            },
            {
                "profile_name": "retrieval_plus_metadata_quality",
                "quality_composite": 0.79,
                "recall_at_10": 0.79,
                "ndcg_at_10": 0.79,
                "mrr_at_10": 0.79,
                "mean_moved_candidate_count": 0.0,
                "relevant_added_to_top_k_count": 0,
                "relevant_removed_from_top_k_count": 0,
                "classification_counts": {
                    "ranking_no_effect": 1,
                },
            },
        ],
        "runs": runs,
        "candidate_pool_sensitivity": [
            {
                "query_id": "q1",
                "profile_name": "current",
                "smaller_candidate_k": 50,
                "larger_candidate_k": 100,
                "top_k_set_equal": False,
                "top_k_order_equal": False,
                "top_k_overlap_ratio": 0.8,
                "component_changes": {
                    "recency_score": {
                        "mean_abs_change": 0.2,
                        "max_abs_change": 0.5,
                        "changed_count": 2,
                    }
                },
            }
        ],
    }


def test_profile_comparison_uses_unranked_as_baseline() -> None:
    rows = build_profile_comparison(_report())
    by_name = {row["profile_name"]: row for row in rows}

    assert by_name["current"]["quality_delta_vs_unranked"] == -0.2
    assert (
        by_name["retrieval_plus_metadata_quality"][
            "quality_delta_vs_unranked"
        ]
        == -0.01
    )


def test_compact_query_run_preserves_removed_relevant_details() -> None:
    row = compact_query_run(
        _report()["runs"][0],
        primary_k=10,
    )

    assert row["harm_score"] > 0.0
    assert len(row["removed_relevant"]) == 1
    assert row["removed_relevant"][0]["canonical_id"] == "relevant"
    assert row["removed_relevant"][0]["rank_before"] == 1
    assert row["removed_relevant"][0]["rank_after"] == 2


def test_aggregate_sensitivity_summarizes_profile_stability() -> None:
    rows = aggregate_sensitivity(_report())

    assert len(rows) == 1
    assert rows[0]["profile_name"] == "current"
    assert rows[0]["top_k_set_equal_rate"] == 0.0
    assert rows[0]["mean_top_k_overlap_ratio"] == 0.8
    assert (
        rows[0]["component_summary"]["recency_score"][
            "mean_of_mean_abs_change"
        ]
        == 0.2
    )


def test_build_analysis_records_rejection_without_public_change() -> None:
    analysis = build_analysis(
        _report(),
        primary_k=10,
        top_n=5,
    )

    assert analysis["schema_version"] == "ranking_evaluation_analysis_v1"
    assert (
        analysis["accepted_interpretation"]["recommended_outcome"]
        == "reject_heuristic_reranking"
    )
    assert analysis["accepted_interpretation"]["public_default_change"] is False
    assert (
        len(analysis["query_cases"]["current"]["worst_cases"])
        == 1
    )
