from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

import scripts.evaluation.qdrant_serving_performance as performance
from scripts.evaluation.qdrant_serving_performance import (
    api_result_ids,
    api_timing_ms,
    backend_candidate_ids,
    compact_result_record,
    compare_id_lists,
    derive_api_timings,
    docker_container_snapshot,
    exception_chain,
    gpu_snapshot,
    parse_size_to_bytes,
    resolve_preset,
    result_ids_digest,
    run_threaded_calls,
    summarize_quality_sections,
    summarize_samples,
    validate_benchmark_config,
)


def _valid_config() -> dict:
    return {
        "schema_version": (
            "qdrant_serving_performance_config_v1"
        ),
        "qdrant": {
            "host": "localhost",
            "port": 6333,
            "collection_name": "collection",
            "timeout_sec": 120,
            "check_compatibility": False,
            "profile": {
                "name": "ef_256",
                "exact": False,
                "hnsw_ef": 256,
            },
        },
        "retrieval": {
            "manifest_path": "manifest.json",
            "golden_queries_path": "golden.jsonl",
        },
        "api": {
            "host": "127.0.0.1",
            "port": 8011,
            "startup_timeout_sec": 240,
            "startup_poll_interval_sec": 0.25,
            "request_timeout_sec": 120,
            "file_dense": {
                "path": "/search",
                "params": {},
            },
            "qdrant": {
                "path": "/experimental/search/qdrant",
                "params": {},
            },
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
                    "measured_rounds": 2,
                    "concurrency_levels": [1, 2],
                },
                "api": {
                    "warmup_rounds": 1,
                    "measured_rounds": 1,
                    "concurrency_levels": [1, 2],
                },
                "fresh_process": {
                    "enabled": True,
                },
            }
        },
        "resources": {
            "collect_process_memory": True,
            "collect_system_memory": True,
            "collect_docker_stats": True,
            "collect_gpu_stats": True,
            "sample_interval_sec": 0.25,
        },
        "quality": {
            "max_error_count": 0,
            "min_mean_overlap_at_k": 1.0,
            "min_query_overlap_at_k": 1.0,
            "require_exact_same_order": True,
            "require_result_count_match": True,
        },
        "output": {
            "output_dir": "artifacts/reports/evaluation",
        },
    }


def test_summarize_samples_empty() -> None:
    assert summarize_samples([]) == {
        "count": 0,
        "mean_ms": None,
        "std_ms": None,
        "min_ms": None,
        "p50_ms": None,
        "p95_ms": None,
        "max_ms": None,
    }


def test_summarize_samples_calculates_distribution() -> None:
    summary = summarize_samples([1.0, 2.0, 3.0, 4.0])

    assert summary["count"] == 4
    assert summary["mean_ms"] == pytest.approx(2.5)
    assert summary["std_ms"] == pytest.approx(
        float(np.std([1.0, 2.0, 3.0, 4.0]))
    )
    assert summary["min_ms"] == 1.0
    assert summary["p50_ms"] == pytest.approx(2.5)
    assert summary["p95_ms"] == pytest.approx(3.85)
    assert summary["max_ms"] == 4.0


@pytest.mark.parametrize(
    "samples",
    [
        [1.0, -1.0],
        [1.0, float("nan")],
        [1.0, float("inf")],
    ],
)
def test_summarize_samples_rejects_invalid_values(
    samples,
) -> None:
    with pytest.raises(
        ValueError,
        match="finite and non-negative",
    ):
        summarize_samples(samples)


def test_backend_candidate_ids_extracts_order() -> None:
    result = SimpleNamespace(
        candidates=(
            SimpleNamespace(canonical_id="a"),
            SimpleNamespace(canonical_id="b"),
        )
    )

    assert backend_candidate_ids(result) == ["a", "b"]


def test_api_result_ids_and_timings_extract_expected_shape() -> None:
    payload = {
        "meta": {
            "timing_ms": {
                "encode_ms": 1.0,
                "total_ms": 3.0,
            }
        },
        "results": [
            {
                "document": {
                    "canonical_id": "a",
                }
            },
            {
                "document": {
                    "canonical_id": "b",
                }
            },
        ],
    }

    assert api_result_ids(payload) == ["a", "b"]
    assert api_timing_ms(payload) == {
        "encode_ms": 1.0,
        "total_ms": 3.0,
    }


def test_api_result_ids_rejects_malformed_result() -> None:
    with pytest.raises(
        ValueError,
        match="document must be an object",
    ):
        api_result_ids(
            {
                "results": [
                    {
                        "document": None,
                    }
                ]
            }
        )


def test_compare_id_lists_exact_match() -> None:
    result = compare_id_lists(
        ["a", "b"],
        ["a", "b"],
        top_k=2,
    )

    assert result["overlap_ratio"] == 1.0
    assert result["exact_same_order"] is True
    assert result["same_set"] is True
    assert result["reference_only"] == []
    assert result["candidate_only"] == []


def test_compare_id_lists_detects_mismatch_and_duplicates() -> None:
    result = compare_id_lists(
        ["a", "b", "b"],
        ["a", "c", "c"],
        top_k=3,
    )

    assert result["overlap_count"] == 1
    assert result["overlap_ratio"] == pytest.approx(1 / 3)
    assert result["exact_same_order"] is False
    assert result["same_set"] is False
    assert result["duplicate_reference_ids"] == ["b"]
    assert result["duplicate_candidate_ids"] == ["c"]
    assert result["reference_only"] == ["b", "b"]
    assert result["candidate_only"] == ["c", "c"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1B", 1),
        ("1KB", 1000),
        ("1KiB", 1024),
        ("1.5MiB", 1572864),
        ("2GB", 2000000000),
    ],
)
def test_parse_size_to_bytes(value: str, expected: int) -> None:
    assert parse_size_to_bytes(value) == expected


def test_docker_snapshot_reports_explicit_unsupported_state(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        performance.shutil,
        "which",
        lambda executable: None,
    )

    assert docker_container_snapshot("qdrant") == {
        "supported": False,
        "reason": "docker_cli_not_available",
    }


def test_gpu_snapshot_reports_explicit_unsupported_state(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        performance.shutil,
        "which",
        lambda executable: None,
    )

    assert gpu_snapshot() == {
        "supported": False,
        "reason": "nvidia_smi_not_available",
    }


def test_valid_config_and_preset_pass() -> None:
    config = _valid_config()

    validate_benchmark_config(config)
    preset = resolve_preset(config, "smoke")

    assert preset["max_queries"] == 2
    assert preset["backend"]["concurrency_levels"] == [1, 2]


def test_config_rejects_wrong_schema() -> None:
    config = _valid_config()
    config["schema_version"] = "wrong"

    with pytest.raises(
        ValueError,
        match="schema_version",
    ):
        validate_benchmark_config(config)


def test_config_rejects_duplicate_concurrency() -> None:
    config = _valid_config()
    config["presets"]["smoke"]["backend"][
        "concurrency_levels"
    ] = [1, 1]

    with pytest.raises(
        ValueError,
        match="duplicate",
    ):
        validate_benchmark_config(config)


def test_run_threaded_calls_records_success_and_failure() -> None:
    result = run_threaded_calls(
        [
            lambda: "ok",
            lambda: 1 / 0,
        ],
        max_workers=2,
        task_contexts=[
            {"query_id": "ok-query"},
            {
                "query_id": "failed-query",
                "round": 2,
                "top_k": 20,
            },
        ],
    )

    assert result["task_count"] == 2
    assert result["success_count"] == 1
    assert result["error_count"] == 1
    assert result["latency"]["count"] == 2
    assert result["throughput_rps"] >= 0.0

    success = result["records"][0]
    failure = result["records"][1]

    assert success["ok"] is True
    assert success["value"] == "ok"
    assert success["task_context"] == {
        "query_id": "ok-query"
    }
    assert success["error_chain"] == []

    assert failure["ok"] is False
    assert failure["task_context"] == {
        "query_id": "failed-query",
        "round": 2,
        "top_k": 20,
    }
    assert failure["error_type"] == "ZeroDivisionError"
    assert failure["error_module"] == "builtins"
    assert failure["error_message"] == "division by zero"
    assert failure["error_chain"][0]["type"] == (
        "ZeroDivisionError"
    )


def test_exception_chain_retains_explicit_root_cause() -> None:
    try:
        try:
            raise OSError("connection reset by peer")
        except OSError as exc:
            raise RuntimeError("backend unavailable") from exc
    except RuntimeError as exc:
        chain = exception_chain(exc)

    assert [
        (row["relation"], row["type"], row["message"])
        for row in chain
    ] == [
        (
            "raised",
            "RuntimeError",
            "backend unavailable",
        ),
        (
            "cause",
            "OSError",
            "connection reset by peer",
        ),
    ]


def test_run_threaded_calls_rejects_context_length_mismatch() -> None:
    with pytest.raises(
        ValueError,
        match="task_contexts length",
    ):
        run_threaded_calls(
            [lambda: "ok"],
            max_workers=1,
            task_contexts=[],
        )


def test_derive_api_timings_exposes_unattributed_and_client_overhead() -> None:
    derived = derive_api_timings(
        client_latency_ms=120.0,
        server_timing_ms={
            "encode_ms": 10.0,
            "qdrant_search_ms": 20.0,
            "hydrate_ms": 30.0,
            "total_ms": 100.0,
        },
    )

    assert derived == {
        "server_known_stage_sum_ms": 60.0,
        "server_unattributed_ms": 40.0,
        "client_overhead_ms": 20.0,
    }


def test_result_ids_digest_is_stable_and_order_sensitive() -> None:
    assert result_ids_digest(["a", "b"]) == result_ids_digest(
        ["a", "b"]
    )
    assert result_ids_digest(["a", "b"]) != result_ids_digest(
        ["b", "a"]
    )


def test_compact_result_record_replaces_ids_with_digest() -> None:
    compact = compact_result_record(
        {
            "query_id": "q1",
            "canonical_ids": ["a", "b"],
            "latency_ms": 1.0,
        }
    )

    assert "canonical_ids" not in compact
    assert compact["result_ids_count"] == 2
    assert compact["result_ids_digest"] == result_ids_digest(
        ["a", "b"]
    )


def _quality_section(
    *,
    reference_count: int = 2,
    candidate_count: int = 2,
    top_k: int = 2,
    duplicate_reference_ids: list[str] | None = None,
    duplicate_candidate_ids: list[str] | None = None,
) -> dict:
    return {
        "comparison_count": 1,
        "missing_comparison_count": 0,
        "comparisons": [
            {
                "comparison_available": True,
                "top_k": top_k,
                "reference_count": reference_count,
                "candidate_count": candidate_count,
                "overlap_ratio": 1.0,
                "exact_same_order": True,
                "duplicate_reference_ids": (
                    duplicate_reference_ids or []
                ),
                "duplicate_candidate_ids": (
                    duplicate_candidate_ids or []
                ),
            }
        ],
        "file_determinism": {"failure_count": 0},
        "qdrant_determinism": {"failure_count": 0},
    }


def _quality_config() -> dict:
    return {
        "max_error_count": 0,
        "min_mean_overlap_at_k": 1.0,
        "min_query_overlap_at_k": 1.0,
        "require_exact_same_order": True,
        "require_result_count_match": True,
    }


def test_quality_summary_requires_full_result_count() -> None:
    verdict = summarize_quality_sections(
        comparison_sections={
            "scenario": _quality_section(
                candidate_count=1,
            )
        },
        quality_cfg=_quality_config(),
        error_count=0,
    )

    assert verdict["ok"] is False
    assert verdict["checks"]["result_count_match_pass"] is False
    assert verdict["result_count_mismatch_count"] == 1


def test_quality_summary_rejects_duplicate_ids() -> None:
    verdict = summarize_quality_sections(
        comparison_sections={
            "scenario": _quality_section(
                duplicate_candidate_ids=["b"],
            )
        },
        quality_cfg=_quality_config(),
        error_count=0,
    )

    assert verdict["ok"] is False
    assert verdict["checks"]["duplicate_ids_pass"] is False
    assert verdict["duplicate_id_failure_count"] == 1


def test_quality_summary_passes_clean_comparison() -> None:
    verdict = summarize_quality_sections(
        comparison_sections={
            "scenario": _quality_section()
        },
        quality_cfg=_quality_config(),
        error_count=0,
    )

    assert verdict["ok"] is True
    assert verdict["failed_checks"] == []
