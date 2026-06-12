from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.validation.check_qdrant_serving_performance import (
    INPUT_SCHEMA_VERSION,
    evaluate_report,
)


DIGEST = "a" * 64
IDS = [f"id-{index}" for index in range(10)]


def _latency(count: int) -> dict:
    return {
        "count": count,
        "mean_ms": 10.0,
        "std_ms": 1.0,
        "min_ms": 8.0,
        "p50_ms": 10.0,
        "p95_ms": 12.0,
        "max_ms": 13.0,
    }


def _resources() -> dict:
    return {
        "process": {
            "supported": True,
            "sample_count": 2,
            "rss_bytes_peak": 1000,
        },
        "system": {
            "supported": True,
            "sample_count": 2,
            "memory_percent_peak": 50.0,
        },
        "docker": {
            "before": {"supported": True},
            "after": {"supported": True},
        },
        "gpu": {
            "before": {"supported": True},
            "after": {"supported": True},
        },
        "sampling_policy": {
            "process_and_system": "periodic",
            "docker_and_gpu": "before_after_only",
            "interval_sec": 0.25,
        },
    }


def _record(kind: str, query_id: str) -> dict:
    timing_key = (
        "wall_latency_ms"
        if kind == "backend"
        else "client_latency_ms"
    )
    return {
        "query_id": query_id,
        "top_k": 10,
        timing_key: 10.0,
        "result_count": 10,
        "result_ids_count": 10,
        "result_ids_digest": DIGEST,
    }


def _scenario(kind: str, count: int) -> dict:
    timing_key = (
        "latency"
        if kind == "backend"
        else "client_latency"
    )
    return {
        "request_count": count,
        "success_count": count,
        "error_count": 0,
        "wall_time_ms": 100.0,
        "throughput_rps": 10.0,
        timing_key: _latency(count),
        "resources": _resources(),
        "records": [
            _record(kind, f"q-{index}")
            for index in range(count)
        ],
        "errors": [],
    }


def _comparison(query_id: str) -> dict:
    return {
        "query_id": query_id,
        "top_k": 10,
        "comparison_available": True,
        "reference_ids": IDS,
        "candidate_ids": IDS,
        "reference_ids_digest": DIGEST,
        "candidate_ids_digest": DIGEST,
        "reference_count": 10,
        "candidate_count": 10,
        "overlap_count": 10,
        "overlap_ratio": 1.0,
        "exact_same_order": True,
        "same_set": True,
        "duplicate_reference_ids": [],
        "duplicate_candidate_ids": [],
        "reference_only": [],
        "candidate_only": [],
    }


def _quality_section(count: int) -> dict:
    return {
        "comparison_count": count,
        "missing_comparison_count": 0,
        "mean_overlap_at_k": 1.0,
        "min_overlap_at_k": 1.0,
        "exact_same_order_count": count,
        "exact_same_order_all": True,
        "comparisons": [
            _comparison(f"q-{index}")
            for index in range(count)
        ],
        "file_determinism": {
            "group_count": count,
            "failure_count": 0,
            "stable": True,
            "failures": [],
        },
        "qdrant_determinism": {
            "group_count": count,
            "failure_count": 0,
            "stable": True,
            "failures": [],
        },
    }


def _fresh_target(target: str) -> dict:
    return {
        "target": target,
        "startup_ms": 100.0,
        "first_request": {
            "status_code": 200,
            "top_k": 10,
            "client_latency_ms": 20.0,
            "derived_timing_ms": {
                "server_known_stage_sum_ms": 15.0,
                "server_unattributed_ms": 1.0,
                "client_overhead_ms": 4.0,
            },
            "result_count": 10,
            "canonical_ids": IDS,
        },
        "resources": _resources(),
        "log_path": "log.txt",
    }


def _fresh_quality() -> dict:
    return {
        "top_k": 10,
        "reference_count": 10,
        "candidate_count": 10,
        "overlap_count": 10,
        "overlap_ratio": 1.0,
        "exact_same_order": True,
        "same_set": True,
        "duplicate_reference_ids": [],
        "duplicate_candidate_ids": [],
        "reference_only": [],
        "candidate_only": [],
    }


def _valid_report() -> dict:
    query_count = 2
    backend_rounds = 2
    api_rounds = 1
    backend_count = query_count * backend_rounds
    api_count = query_count * api_rounds

    quality_sections = {
        "backend_sequential": _quality_section(query_count),
        "backend_concurrent_1": _quality_section(query_count),
        "backend_concurrent_2": _quality_section(query_count),
        "api_fresh": _quality_section(1),
        "api_sequential": _quality_section(query_count),
        "api_concurrent_1": _quality_section(query_count),
        "api_concurrent_2": _quality_section(query_count),
    }

    return {
        "schema_version": INPUT_SCHEMA_VERSION,
        "generated_at_utc": "2026-06-11T00:00:00+00:00",
        "preset": "smoke",
        "benchmark_only": True,
        "production_default_changed": False,
        "public_qdrant_promoted": False,
        "fallback_used": False,
        "report_policy": {
            "repeated_measurement_ids": "sha256_digest_only",
            "quality_comparison_ids": "retained_once_per_scenario",
            "resource_raw_samples": "summary_only",
            "docker_raw_payload": "omitted",
        },
        "config": {
            "retrieval": {
                "expected_distance": "Cosine",
            },
            "qdrant": {
                "port": 6333,
                "grpc_port": 6334,
                "prefer_grpc": True,
            },
            "presets": {
                "smoke": {
                    "max_queries": 2,
                    "top_k_values": [10],
                    "encoding": {
                        "warmup_rounds": 1,
                        "measured_rounds": 2,
                    },
                    "backend": {
                        "warmup_rounds": 1,
                        "measured_rounds": backend_rounds,
                        "concurrency_levels": [1, 2],
                    },
                    "api": {
                        "warmup_rounds": 1,
                        "measured_rounds": api_rounds,
                        "concurrency_levels": [1, 2],
                    },
                    "fresh_process": {
                        "enabled": True,
                    },
                }
            },
        },
        "resolved_preset": {
            "max_queries": 2,
            "top_k_values": [10],
            "encoding": {
                "warmup_rounds": 1,
                "measured_rounds": 2,
            },
            "backend": {
                "warmup_rounds": 1,
                "measured_rounds": backend_rounds,
                "concurrency_levels": [1, 2],
            },
            "api": {
                "warmup_rounds": 1,
                "measured_rounds": api_rounds,
                "concurrency_levels": [1, 2],
            },
            "fresh_process": {
                "enabled": True,
            },
        },
        "summary": {
            "build_id": "build",
            "corpus_doc_count": 100,
            "embedding_shape": [100, 384],
            "query_count": query_count,
            "top_k_values": [10],
            "collection_name": "collection",
            "qdrant_transport": "grpc",
            "qdrant_rest_port": 6333,
            "qdrant_grpc_port": 6334,
            "profile_name": "ef_256",
            "error_count": 0,
            "quality_ok": True,
        },
        "collection": {
            "collection_name": "collection",
            "status": "green",
            "optimizer_status": "ok",
            "points_count": 100,
            "vector_size": 384,
            "distance": "Cosine",
            "transport": "grpc",
            "rest_port": 6333,
            "grpc_port": 6334,
            "prefer_grpc": True,
        },
        "query_set": {
            "selected_query_count": query_count,
            "query_ids": ["q-0", "q-1"],
            "queries": [{}, {}],
        },
        "encoding": {
            "model_load_ms": 100.0,
            "first_encode_ms": 20.0,
            "latency": _latency(query_count * 2),
            "samples": [
                {
                    "latency_ms": 10.0,
                    "dimension": 384,
                    "norm": 1.0,
                    "all_finite": True,
                }
                for _ in range(query_count * 2)
            ],
        },
        "backend_only": {
            "skipped": False,
            "construction": {
                "file_ms": 1.0,
                "qdrant_ms": 1.0,
            },
            "first_request": {
                "file": {
                    "result_count": 10,
                    "canonical_ids": IDS,
                },
                "qdrant": {
                    "result_count": 10,
                    "canonical_ids": IDS,
                },
                "comparison": {
                    "overlap_ratio": 1.0,
                    "exact_same_order": True,
                },
                "errors": [],
            },
            "sequential": {
                "file": _scenario("backend", backend_count),
                "qdrant": _scenario("backend", backend_count),
                "quality": _quality_section(query_count),
            },
            "concurrent": {
                "file": [
                    {
                        **{
                            key: value
                            for key, value in _scenario(
                                "backend", backend_count
                            ).items()
                            if key != "request_count"
                        },
                        "task_count": backend_count,
                        "concurrency": 1,
                    },
                    {
                        **{
                            key: value
                            for key, value in _scenario(
                                "backend", backend_count
                            ).items()
                            if key != "request_count"
                        },
                        "task_count": backend_count,
                        "concurrency": 2,
                    },
                ],
                "qdrant": [
                    {
                        **{
                            key: value
                            for key, value in _scenario(
                                "backend", backend_count
                            ).items()
                            if key != "request_count"
                        },
                        "task_count": backend_count,
                        "concurrency": 1,
                    },
                    {
                        **{
                            key: value
                            for key, value in _scenario(
                                "backend", backend_count
                            ).items()
                            if key != "request_count"
                        },
                        "task_count": backend_count,
                        "concurrency": 2,
                    },
                ],
                "quality_by_concurrency": {},
            },
        },
        "api_serving": {
            "skipped": False,
            "fresh_process": {
                "enabled": True,
                "file_dense": _fresh_target("file_dense"),
                "qdrant": _fresh_target("qdrant"),
                "quality": _fresh_quality(),
            },
            "warm_process": {
                "startup_ms": 100.0,
                "process_pid": 123,
                "log_path": "warm.log",
                "warmup_rounds": 1,
            },
            "warm_sequential": {
                "file_dense": _scenario("api", api_count),
                "qdrant": _scenario("api", api_count),
                "quality": _quality_section(query_count),
            },
            "warm_concurrent": {
                "file_dense": [
                    {
                        **{
                            key: value
                            for key, value in _scenario(
                                "api", api_count
                            ).items()
                            if key != "request_count"
                        },
                        "task_count": api_count,
                        "concurrency": 1,
                    },
                    {
                        **{
                            key: value
                            for key, value in _scenario(
                                "api", api_count
                            ).items()
                            if key != "request_count"
                        },
                        "task_count": api_count,
                        "concurrency": 2,
                    },
                ],
                "qdrant": [
                    {
                        **{
                            key: value
                            for key, value in _scenario(
                                "api", api_count
                            ).items()
                            if key != "request_count"
                        },
                        "task_count": api_count,
                        "concurrency": 1,
                    },
                    {
                        **{
                            key: value
                            for key, value in _scenario(
                                "api", api_count
                            ).items()
                            if key != "request_count"
                        },
                        "task_count": api_count,
                        "concurrency": 2,
                    },
                ],
                "quality_by_concurrency": {},
            },
        },
        "quality": {
            "policy": {},
            "sections": quality_sections,
        },
        "errors": [],
        "verdict": {
            "ok": True,
            "failed_checks": [],
            "error_count": 0,
            "comparison_count": 13,
            "missing_comparison_count": 0,
            "mean_overlap_at_k": 1.0,
            "min_overlap_at_k": 1.0,
            "result_count_mismatch_count": 0,
            "duplicate_id_failure_count": 0,
            "determinism_failure_count": 0,
        },
    }


def test_valid_strict_report_passes() -> None:
    result = evaluate_report(
        _valid_report(),
        strict=True,
    )

    assert result["verdict"]["ok"] is True
    assert result["verdict"]["required_failed_checks"] == []


def test_wrong_schema_fails() -> None:
    report = _valid_report()
    report["schema_version"] = "wrong"

    result = evaluate_report(report, strict=True)

    assert result["checks"]["input_schema_version_ok"] is False
    assert "input_schema_version_ok" in result["verdict"][
        "required_failed_checks"
    ]


def test_missing_concurrency_level_fails() -> None:
    report = _valid_report()
    report["api_serving"]["warm_concurrent"]["qdrant"].pop()

    result = evaluate_report(report, strict=True)

    assert result["checks"]["api_concurrent_valid"] is False


def test_negative_latency_fails() -> None:
    report = _valid_report()
    report["backend_only"]["sequential"]["file"][
        "records"
    ][0]["wall_latency_ms"] = -1.0

    result = evaluate_report(report, strict=True)

    assert result["checks"]["backend_sequential_valid"] is False


def test_quality_regression_fails() -> None:
    report = _valid_report()
    report["quality"]["sections"]["api_sequential"][
        "comparisons"
    ][0]["candidate_ids"] = ["wrong"] * 10

    result = evaluate_report(report, strict=True)

    assert result["checks"]["quality_sections_valid"] is False


def test_result_count_mismatch_fails() -> None:
    report = _valid_report()
    report["quality"]["sections"]["backend_sequential"][
        "comparisons"
    ][0]["candidate_count"] = 9

    result = evaluate_report(report, strict=True)

    assert result["checks"]["quality_sections_valid"] is False


def test_duplicate_ids_fail() -> None:
    report = _valid_report()
    report["quality"]["sections"]["backend_sequential"][
        "comparisons"
    ][0]["duplicate_candidate_ids"] = ["id-1"]

    result = evaluate_report(report, strict=True)

    assert result["checks"]["quality_sections_valid"] is False


def test_missing_resource_capability_fails() -> None:
    report = _valid_report()
    report["api_serving"]["warm_sequential"]["qdrant"][
        "resources"
    ]["gpu"]["after"] = {}

    result = evaluate_report(report, strict=True)

    assert result["checks"]["api_sequential_valid"] is False
    assert result["checks"][
        "resource_capabilities_explicit"
    ] is False


def test_scenario_failure_does_not_masquerade_as_resource_failure() -> None:
    report = _valid_report()
    scenario = report["backend_only"]["concurrent"]["qdrant"][1]
    scenario["success_count"] -= 1
    scenario["error_count"] = 1
    scenario["records"].pop()
    scenario["errors"] = [
        {
            "backend": "qdrant",
            "concurrency": 2,
            "query_id": "q-1",
            "round": 1,
            "top_k": 10,
            "error": "simulated",
        }
    ]

    result = evaluate_report(report, strict=True)

    assert result["checks"]["backend_concurrent_valid"] is False
    assert result["checks"][
        "resource_capabilities_explicit"
    ] is True


@pytest.mark.parametrize(
    ("field", "value", "check"),
    [
        (
            "production_default_changed",
            True,
            "safety_production_default_unchanged",
        ),
        (
            "public_qdrant_promoted",
            True,
            "safety_public_qdrant_not_promoted",
        ),
        (
            "fallback_used",
            True,
            "safety_no_fallback",
        ),
    ],
)
def test_safety_marker_failure_is_blocking(
    field: str,
    value: bool,
    check: str,
) -> None:
    report = _valid_report()
    report[field] = value

    result = evaluate_report(report, strict=True)

    assert result["checks"][check] is False
    assert check in result["verdict"]["required_failed_checks"]


def test_non_strict_mode_allows_quality_failure() -> None:
    report = _valid_report()
    report["quality"]["sections"]["api_sequential"][
        "comparisons"
    ][0]["candidate_ids"] = ["wrong"] * 10

    result = evaluate_report(report, strict=False)

    assert result["verdict"]["ok"] is True
    assert result["checks"]["quality_sections_valid"] is False

def test_transport_mismatch_fails() -> None:
    report = _valid_report()
    report["summary"]["qdrant_transport"] = "rest"

    result = evaluate_report(report, strict=True)

    assert (
        result["checks"]["qdrant_transport_matches_config"]
        is False
    )
    assert (
        "qdrant_transport_matches_config"
        in result["verdict"]["required_failed_checks"]
    )
