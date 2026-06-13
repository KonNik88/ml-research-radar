from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

import scripts.evaluation.run_qdrant_hybrid_evaluation as runner


def exact_comparison() -> dict:
    return {
        "overlap_count": 2,
        "overlap_ratio": 1.0,
        "same_set": True,
        "exact_same_order": True,
        "reference_only": [],
        "candidate_only": [],
        "rank_changes": [],
        "rank_change_count": 0,
    }


def exact_scenario_result(
    *,
    scenario_id: str = "top10__candidate50__unranked",
) -> dict:
    return {
        "scenario_id": scenario_id,
        "top_k": 10,
        "candidate_k": 50,
        "rank": False,
        "file": {
            "dense_ids": ["a", "b"],
            "final_ids": ["a", "b"],
            "timing_ms": {
                "dense_wall_ms": 1.0,
                "backend_search_ms": 0.8,
                "merge_ms": 0.1,
                "hydrate_ms": 0.1,
                "rank_ms": 0.0,
            },
        },
        "qdrant": {
            "dense_ids": ["a", "b"],
            "final_ids": ["a", "b"],
            "timing_ms": {
                "dense_wall_ms": 0.8,
                "backend_search_ms": 0.6,
                "merge_ms": 0.1,
                "hydrate_ms": 0.1,
                "rank_ms": 0.0,
            },
        },
        "comparison": {
            "dense": exact_comparison(),
            "final": exact_comparison(),
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
        },
    }


def test_select_enabled_cases_preserves_order() -> None:
    rows = [
        {
            "query_id": "q1",
            "query": "first",
            "enabled": True,
        },
        {
            "query_id": "disabled",
            "query": "disabled",
            "enabled": False,
        },
        {
            "query_id": "q2",
            "query": "second",
        },
    ]

    selected = runner.select_enabled_cases(
        rows,
        max_queries=None,
    )

    assert [
        row["query_id"]
        for row in selected
    ] == ["q1", "q2"]


def test_select_enabled_cases_applies_limit() -> None:
    rows = [
        {
            "query_id": "q1",
            "query": "first",
        },
        {
            "query_id": "q2",
            "query": "second",
        },
    ]

    selected = runner.select_enabled_cases(
        rows,
        max_queries=1,
    )

    assert len(selected) == 1
    assert selected[0]["query_id"] == "q1"


def test_select_enabled_cases_rejects_empty_query(
) -> None:
    with pytest.raises(
        ValueError,
        match="empty query text",
    ):
        runner.select_enabled_cases(
            [
                {
                    "query_id": "q1",
                    "query": "",
                    "enabled": True,
                }
            ],
            max_queries=None,
        )


def test_apply_repeat_evidence_exact() -> None:
    runs = [
        exact_scenario_result(),
        exact_scenario_result(),
    ]

    result = runner.apply_repeat_evidence(
        runs
    )

    assert result["repeat_count"] == 2
    assert result["determinism"]["stable"] is True
    assert result["comparison"][
        "classification"
    ] == "exact_match"
    assert result["comparison"]["blocking"] is False


def test_apply_repeat_evidence_detects_instability(
) -> None:
    first = exact_scenario_result()
    second = exact_scenario_result()

    second["qdrant"]["final_ids"] = ["b", "a"]

    result = runner.apply_repeat_evidence(
        [first, second]
    )

    assert result["determinism"]["stable"] is False
    assert result["comparison"][
        "classification"
    ] == "non_deterministic_result"
    assert result["comparison"]["blocking"] is True


def test_run_scenario_uses_normal_repeat_count(
    monkeypatch,
) -> None:
    calls = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        return deepcopy(
            exact_scenario_result()
        )

    monkeypatch.setattr(
        runner,
        "run_paired_hybrid_scenario",
        fake_run,
    )

    result = runner.run_scenario_with_repeats(
        case={"query_id": "q1"},
        query_vector=None,
        lexical_candidates=[],
        file_backend=object(),
        qdrant_backend=object(),
        documents_by_id={},
        scenario={
            "scenario_id": (
                "top10__candidate50__unranked"
            )
        },
        scoring_params={},
        repeated_runs=2,
        mismatch_repeated_runs=5,
    )

    assert len(calls) == 2
    assert result["repeat_count"] == 2


def test_run_scenario_expands_mismatch_repeats(
    monkeypatch,
) -> None:
    calls = []

    mismatch = exact_scenario_result()
    mismatch["comparison"][
        "classification"
    ] = "same_set_different_order"
    mismatch["comparison"]["final"][
        "exact_same_order"
    ] = False

    def fake_run(**kwargs):
        calls.append(kwargs)
        return deepcopy(mismatch)

    monkeypatch.setattr(
        runner,
        "run_paired_hybrid_scenario",
        fake_run,
    )

    result = runner.run_scenario_with_repeats(
        case={"query_id": "q1"},
        query_vector=None,
        lexical_candidates=[],
        file_backend=object(),
        qdrant_backend=object(),
        documents_by_id={},
        scenario={
            "scenario_id": (
                "top10__candidate50__unranked"
            )
        },
        scoring_params={},
        repeated_runs=2,
        mismatch_repeated_runs=5,
    )

    assert len(calls) == 5
    assert result["repeat_count"] == 5


def test_summarize_results_exact() -> None:
    scenario = exact_scenario_result()
    scenario["determinism"] = {
        "stable": True,
    }
    scenario["error"] = None

    summary = runner.summarize_results(
        query_results=[
            {
                "query_id": "q1",
                "scenarios": [scenario],
            }
        ],
        errors=[],
        expected_scenario_count=1,
        quality_config={
            "max_error_count": 0,
            "min_mean_final_overlap_at_k": 0.99,
            "min_query_final_overlap_at_k": 0.95,
            "require_no_blocking_classifications": True,
            "require_deterministic_results": True,
        },
    )

    assert summary["complete"] is True
    assert summary[
        "successful_scenario_count"
    ] == 1
    assert summary["error_count"] == 0
    assert summary["dense_overlap"] == {
        "mean": 1.0,
        "min": 1.0,
    }
    assert summary["final_overlap"] == {
        "mean": 1.0,
        "min": 1.0,
    }
    assert summary[
        "classification_counts"
    ] == {
        "exact_match": 1,
    }
    assert summary["quality_ok"] is True


def test_summarize_results_rejects_blocking_result(
) -> None:
    scenario = exact_scenario_result()
    scenario["comparison"][
        "classification"
    ] = "hydration_defect"
    scenario["comparison"]["blocking"] = True
    scenario["determinism"] = {
        "stable": True,
    }
    scenario["error"] = None

    summary = runner.summarize_results(
        query_results=[
            {
                "query_id": "q1",
                "scenarios": [scenario],
            }
        ],
        errors=[],
        expected_scenario_count=1,
        quality_config={
            "max_error_count": 0,
            "min_mean_final_overlap_at_k": 0.99,
            "min_query_final_overlap_at_k": 0.95,
            "require_no_blocking_classifications": True,
            "require_deterministic_results": True,
        },
    )

    assert summary[
        "blocking_classification_count"
    ] == 1
    assert summary["quality_ok"] is False


def test_save_report_writes_latest_and_history(
    tmp_path: Path,
) -> None:
    report = {
        "safety": {
            "evaluation_only": True,
            "production_default_changed": False,
            "public_qdrant_promoted": False,
            "fallback_used": False,
        },
        "runtime": {
            "build_id": "build-1",
            "corpus_doc_count": 10,
            "embedding_model_name": "model",
        },
        "qdrant": {
            "collection_name": "collection",
            "transport": "grpc",
            "profile": {
                "name": "ef_256",
            },
        },
        "summary": {
            "enabled_query_count": 1,
            "selected_query_count": 1,
            "scenario_count_per_query": 4,
            "expected_scenario_count": 4,
            "successful_scenario_count": 4,
            "error_count": 0,
            "dense_overlap": {
                "mean": 1.0,
                "min": 1.0,
            },
            "final_overlap": {
                "mean": 1.0,
                "min": 1.0,
            },
            "exact_dense_order_count": 4,
            "exact_final_order_count": 4,
            "blocking_classification_count": 0,
            "determinism_failure_count": 0,
            "classification_counts": {
                "exact_match": 4,
            },
        },
        "verdict": {
            "ok": True,
            "error_count": 0,
            "blocking_classification_count": 0,
        },
    }

    paths = runner.save_report(
        report=report,
        output_dir=tmp_path,
        run_ts="20260613T000000Z",
    )

    for path in paths.values():
        assert Path(path).exists()

    assert report["report_paths"] == paths