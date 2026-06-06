from __future__ import annotations

from copy import deepcopy

from scripts.validation.check_qdrant_file_dense_comparison import evaluate_report


def _result_row(rank: int, canonical_id: str) -> dict:
    return {
        "rank": rank,
        "canonical_id": canonical_id,
        "dense_index": rank - 1,
        "score": 1.0 - rank / 100.0,
    }


def _qdrant_row(rank: int, canonical_id: str) -> dict:
    return {
        **_result_row(rank, canonical_id),
        "point_id": rank - 1,
        "build_id": "build-1",
        "payload": {
            "canonical_id": canonical_id,
            "dense_index": rank - 1,
            "build_id": "build-1",
        },
    }


def _profile_result(*, exact: bool = True) -> dict:
    rows = [_qdrant_row(1, "a"), _qdrant_row(2, "b")]
    return {
        "profile": {"name": "exact" if exact else "ef_256", "exact": exact},
        "latency_ms": 1.0,
        "returned_count": 2,
        "comparison": {
            "top_k": 2,
            "overlap_ratio": 1.0,
            "exact_same_order": True,
        },
        "mapping_audit": {"failure_count": 0},
        "determinism": None,
        "classification": {
            "classification": "exact_match",
            "severity": "ok",
        },
        "results": rows,
    }


def _valid_report() -> dict:
    return {
        "schema_version": "qdrant_file_dense_comparison_v2",
        "summary": {
            "build_id": "build-1",
            "collection_name": "collection",
            "external_top_k": 2,
            "enabled_queries_count": 1,
            "query_count": 1,
            "error_count": 0,
            "selected_profile_name": "ef_256",
            "exact_profile_name": "exact",
            "selected_profile_full_match": True,
            "exact_profile_full_match": True,
            "blocking_classification_count": 0,
        },
        "quality_policy": {
            "max_error_count": 0,
            "require_selected_profile_full_match": True,
            "require_exact_profile_full_match": True,
            "min_mean_overlap_at_k": 1.0,
            "min_query_overlap_at_k": 1.0,
        },
        "selected_profile_summary": {
            "query_count": 1,
            "mean_overlap_at_k": 1.0,
            "min_overlap_at_k": 1.0,
        },
        "exact_profile_summary": {
            "query_count": 1,
            "mean_overlap_at_k": 1.0,
            "min_overlap_at_k": 1.0,
        },
        "latency_summary": {
            "file_reference": {"count": 1},
            "selected_profile": {"count": 1},
            "exact_profile": {"count": 1},
        },
        "blocking_classifications": [],
        "errors": [],
        "query_results": [
            {
                "query_id": "q1",
                "query_vector": {
                    "dimension": 2,
                    "dtype": "float32",
                    "norm": 1.0,
                    "all_finite": True,
                    "sha256": "a" * 64,
                },
                "file_reference": {
                    "results": [_result_row(1, "a"), _result_row(2, "b")]
                },
                "selected_profile": _profile_result(exact=False),
                "exact_profile": _profile_result(exact=True),
            }
        ],
    }


def test_valid_v2_report_passes_strict_validation() -> None:
    result = evaluate_report(_valid_report(), strict=True)
    assert result["ok"] is True
    assert result["required_failed_checks"] == []


def test_exact_profile_mismatch_is_blocking() -> None:
    report = _valid_report()
    report["summary"]["exact_profile_full_match"] = False
    report["exact_profile_summary"]["mean_overlap_at_k"] = 0.5
    report["exact_profile_summary"]["min_overlap_at_k"] = 0.5
    report["query_results"][0]["exact_profile"]["comparison"][
        "exact_same_order"
    ] = False

    result = evaluate_report(report, strict=True)
    assert result["ok"] is False
    assert "exact_profile_full_match" in result["required_failed_checks"]


def test_selected_profile_regression_fails_when_full_match_is_required() -> None:
    report = _valid_report()
    report["summary"]["selected_profile_full_match"] = False
    report["selected_profile_summary"]["mean_overlap_at_k"] = 0.95
    report["selected_profile_summary"]["min_overlap_at_k"] = 0.95
    selected = report["query_results"][0]["selected_profile"]
    selected["comparison"]["exact_same_order"] = False
    selected["comparison"]["overlap_ratio"] = 0.95
    selected["determinism"] = {
        "recorded_runs": 5,
        "stable_order": True,
    }
    selected["classification"] = {
        "classification": "approximate_search_recall_difference",
        "severity": "warning",
    }

    result = evaluate_report(report, strict=True)
    assert result["ok"] is False
    assert "selected_profile_full_match" in result["required_failed_checks"]


def test_selected_warning_can_pass_when_policy_allows_ann_difference() -> None:
    report = _valid_report()
    report["quality_policy"]["require_selected_profile_full_match"] = False
    report["summary"]["selected_profile_full_match"] = False
    selected = report["query_results"][0]["selected_profile"]
    selected["comparison"]["exact_same_order"] = False
    selected["comparison"]["overlap_ratio"] = 1.0
    selected["determinism"] = {
        "recorded_runs": 5,
        "stable_order": True,
    }
    selected["classification"] = {
        "classification": "approximate_search_recall_difference",
        "severity": "warning",
    }

    result = evaluate_report(report, strict=True)
    assert result["ok"] is True


def test_mapping_failure_fails_validation() -> None:
    report = _valid_report()
    report["query_results"][0]["selected_profile"]["mapping_audit"] = {
        "failure_count": 1
    }

    result = evaluate_report(report, strict=True)
    assert result["ok"] is False
    assert any("mapping_failure_count" in problem for problem in result["problems"])


def test_unstable_mismatch_fails_validation() -> None:
    report = _valid_report()
    report["quality_policy"]["require_selected_profile_full_match"] = False
    selected = report["query_results"][0]["selected_profile"]
    selected["comparison"]["exact_same_order"] = False
    selected["comparison"]["overlap_ratio"] = 1.0
    selected["determinism"] = {
        "recorded_runs": 5,
        "stable_order": False,
    }

    result = evaluate_report(report, strict=True)
    assert result["ok"] is False
    assert any("unstable_order" in problem for problem in result["problems"])


def test_duplicate_result_ids_fail_validation() -> None:
    report = _valid_report()
    selected = report["query_results"][0]["selected_profile"]
    selected["results"][1]["canonical_id"] = "a"

    result = evaluate_report(report, strict=True)
    assert result["ok"] is False
    assert any("duplicate_canonical_id" in problem for problem in result["problems"])
