from __future__ import annotations

from pathlib import Path

from scripts.validation.check_retrieval_serving_checkpoint import (
    DEFAULT_API_SMOKE_TESTS,
    build_parser,
    build_report,
    build_steps,
    summarize_evidence,
)


def _step_names(argv: list[str]) -> list[str]:
    args = build_parser().parse_args(argv)
    return [step.name for step in build_steps(args)]


def test_default_steps_are_lightweight_and_required() -> None:
    args = build_parser().parse_args([])
    steps = build_steps(args)
    names = [step.name for step in steps]

    assert names == [
        "ranking_evidence_regression",
        "qdrant_hybrid_evidence",
    ]
    assert all(step.required for step in steps)

    assert all(
        "run_qdrant" not in " ".join(step.cmd)
        for step in steps
    )
    assert all(
        step.env == {"ML_RADAR_SEARCH_BACKEND": "file"}
        for step in steps
    )


def test_can_skip_qdrant_hybrid_for_partial_debugging() -> None:
    names = _step_names(["--skip-qdrant-hybrid-evidence"])

    assert names == ["ranking_evidence_regression"]


def test_serving_performance_can_be_optional_or_required() -> None:
    args = build_parser().parse_args([
        "--include-serving-performance-evidence",
    ])
    steps = build_steps(args)

    optional = {
        step.name: step.required
        for step in steps
    }

    assert optional["qdrant_serving_performance_evidence"] is False

    args = build_parser().parse_args([
        "--require-serving-performance-evidence",
    ])
    steps = build_steps(args)

    required = {
        step.name: step.required
        for step in steps
    }

    assert required["qdrant_serving_performance_evidence"] is True


def test_live_collection_check_is_opt_in() -> None:
    assert "qdrant_collection_live" not in _step_names([])

    args = build_parser().parse_args([
        "--include-qdrant-collection-live",
    ])
    steps = {
        step.name: step
        for step in build_steps(args)
    }

    assert steps["qdrant_collection_live"].required is False
    assert "check_qdrant_collection" in " ".join(
        steps["qdrant_collection_live"].cmd
    )

    args = build_parser().parse_args([
        "--require-qdrant-collection-live",
    ])
    steps = {
        step.name: step
        for step in build_steps(args)
    }

    assert steps["qdrant_collection_live"].required is True


def test_api_smoke_is_opt_in_and_uses_expected_tests() -> None:
    assert "api_runtime_smoke" not in _step_names([])

    args = build_parser().parse_args(["--include-api-smoke"])
    steps = {
        step.name: step
        for step in build_steps(args)
    }

    api_step = steps["api_runtime_smoke"]

    assert api_step.required is True
    assert api_step.env == {"ML_RADAR_SEARCH_BACKEND": "file"}
    assert "pytest" in api_step.cmd
    for path in DEFAULT_API_SMOKE_TESTS:
        assert path in api_step.cmd


def test_summarize_evidence_handles_ranking_regression_shape() -> None:
    payload = {
        "schema_version": "ranking_evidence_regression_v1",
        "ok": True,
        "required_failed_count": 0,
        "extracted_values": {
            "evaluation_build_id": "build-1",
            "evaluation_corpus_doc_count": 2,
            "recommended_outcome": "reject_heuristic_reranking",
        },
    }

    summary = summarize_evidence(payload)

    assert summary["evidence_loaded"] is True
    assert summary["schema_version"] == "ranking_evidence_regression_v1"
    assert summary["ok"] is True
    assert summary["required_failed_count"] == 0
    assert summary["build_id"] == "build-1"
    assert summary["corpus_doc_count"] == 2
    assert summary["recommended_outcome"] == "reject_heuristic_reranking"


def test_summarize_evidence_handles_validator_verdict_shape() -> None:
    payload = {
        "schema_version": "qdrant_hybrid_evaluation_quality_v1",
        "summary": {
            "build_id": "build-1",
            "collection_name": "collection",
            "profile_name": "ef_256",
        },
        "verdict": {
            "ok": True,
            "required_failed_count": 0,
            "required_failed_checks": [],
        },
    }

    summary = summarize_evidence(payload)

    assert summary["evidence_loaded"] is True
    assert summary["ok"] is True
    assert summary["required_failed_count"] == 0
    assert summary["build_id"] == "build-1"
    assert summary["collection_name"] == "collection"
    assert summary["profile_name"] == "ef_256"


def test_build_report_fails_on_required_step_failure(tmp_path: Path) -> None:
    args = build_parser().parse_args([
        "--output-dir",
        str(tmp_path),
    ])

    report = build_report(
        args,
        [
            {
                "name": "ranking_evidence_regression",
                "required": True,
                "returncode": 1,
                "evidence": {"evidence_loaded": False},
            }
        ],
    )

    assert report["ok"] is False
    assert report["required_failed_count"] == 1
    assert report["required_failed_steps"] == [
        "ranking_evidence_regression"
    ]


def test_build_report_allows_optional_step_failure(tmp_path: Path) -> None:
    args = build_parser().parse_args([
        "--output-dir",
        str(tmp_path),
        "--include-serving-performance-evidence",
    ])

    report = build_report(
        args,
        [
            {
                "name": "ranking_evidence_regression",
                "required": True,
                "returncode": 0,
                "evidence": {"evidence_loaded": True},
            },
            {
                "name": "qdrant_hybrid_evidence",
                "required": True,
                "returncode": 0,
                "evidence": {"evidence_loaded": True},
            },
            {
                "name": "qdrant_serving_performance_evidence",
                "required": False,
                "returncode": 1,
                "evidence": {"evidence_loaded": False},
            },
        ],
    )

    assert report["ok"] is True
    assert report["required_failed_count"] == 0
    assert report["optional_failed_steps"] == [
        "qdrant_serving_performance_evidence"
    ]
