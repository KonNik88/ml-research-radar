from __future__ import annotations

from scripts.evaluation.run_ranking_evaluation import (
    build_candidate_pool_sensitivity_pair,
    classify_ranking_effect,
    validate_profile,
)


def _metrics(*, recall: float, mrr: float, ndcg: float, hit: float = 1.0):
    return {
        "10": {
            "hit": hit,
            "precision": recall,
            "recall": recall,
            "mrr": mrr,
            "ndcg": ndcg,
        }
    }


def test_validate_profile_accepts_normalized_ranked_weights() -> None:
    validate_profile(
        {
            "name": "current",
            "apply_ranking": True,
            "weights": {
                "retrieval": 0.60,
                "recency": 0.20,
                "source_support": 0.10,
                "metadata_quality": 0.10,
            },
        },
        1e-12,
    )


def test_classify_removed_relevant_has_highest_priority() -> None:
    classification, details = classify_ranking_effect(
        before_ids=["relevant", "other"],
        after_ids=["other", "replacement"],
        grades_by_id={"relevant": 3.0},
        metrics_before=_metrics(recall=1.0, mrr=1.0, ndcg=1.0),
        metrics_after=_metrics(recall=0.0, mrr=0.0, ndcg=0.0, hit=0.0),
        primary_k=2,
        tolerance=1e-12,
    )

    assert classification == "ranking_removed_relevant_from_top_k"
    assert details["relevant_removed_from_top_k"] == ["relevant"]


def test_classify_added_relevant() -> None:
    classification, details = classify_ranking_effect(
        before_ids=["other", "replacement"],
        after_ids=["relevant", "other"],
        grades_by_id={"relevant": 3.0},
        metrics_before=_metrics(recall=0.0, mrr=0.0, ndcg=0.0, hit=0.0),
        metrics_after=_metrics(recall=1.0, mrr=1.0, ndcg=1.0),
        primary_k=2,
        tolerance=1e-12,
    )

    assert classification == "ranking_added_relevant_to_top_k"
    assert details["relevant_added_to_top_k"] == ["relevant"]


def test_classify_same_set_different_order_as_boundary_effect() -> None:
    classification, details = classify_ranking_effect(
        before_ids=["a", "b"],
        after_ids=["b", "a"],
        grades_by_id={"a": 3.0, "b": 3.0},
        metrics_before=_metrics(recall=1.0, mrr=1.0, ndcg=1.0),
        metrics_after=_metrics(recall=1.0, mrr=1.0, ndcg=1.0),
        primary_k=2,
        tolerance=1e-12,
    )

    assert classification == "tie_or_boundary_effect"
    assert details["same_top_k_set"] is True
    assert details["same_top_k_order"] is False


def test_candidate_pool_sensitivity_detects_component_changes() -> None:
    smaller = {
        "query_id": "q1",
        "query": "ranking",
        "profile_name": "current",
        "candidate_k": 50,
        "result_ids_after": ["a", "b"],
        "metrics_after": _metrics(recall=1.0, mrr=1.0, ndcg=1.0),
        "candidate_evidence": [
            {
                "canonical_id": "a",
                "retrieval_score_normalized": 1.0,
                "recency_score": 0.0,
                "source_support_score": 1.0,
                "metadata_quality_score": 0.5,
                "final_score": 0.75,
            },
            {
                "canonical_id": "b",
                "retrieval_score_normalized": 0.0,
                "recency_score": 1.0,
                "source_support_score": 0.0,
                "metadata_quality_score": 0.5,
                "final_score": 0.25,
            },
        ],
    }
    larger = {
        "query_id": "q1",
        "query": "ranking",
        "profile_name": "current",
        "candidate_k": 100,
        "result_ids_after": ["b", "a"],
        "metrics_after": _metrics(recall=1.0, mrr=1.0, ndcg=1.0),
        "candidate_evidence": [
            {
                "canonical_id": "a",
                "retrieval_score_normalized": 0.8,
                "recency_score": 0.3,
                "source_support_score": 0.5,
                "metadata_quality_score": 0.5,
                "final_score": 0.64,
            },
            {
                "canonical_id": "b",
                "retrieval_score_normalized": 0.2,
                "recency_score": 0.7,
                "source_support_score": 0.2,
                "metadata_quality_score": 0.5,
                "final_score": 0.36,
            },
        ],
    }

    result = build_candidate_pool_sensitivity_pair(
        smaller=smaller,
        larger=larger,
        primary_k=2,
    )

    assert result["shared_candidate_count"] == 2
    assert result["top_k_set_equal"] is True
    assert result["top_k_order_equal"] is False
    assert (
        result["component_changes"]["recency_score"]["changed_count"]
        == 2
    )
