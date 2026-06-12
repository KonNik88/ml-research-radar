"""Validate Qdrant serving-performance evidence.

The validator checks the report as operational evidence. It intentionally does
not require Qdrant to be faster than the file backend. Strict mode requires:

- complete backend-only and API-serving scenarios;
- exact quality parity under the configured policy;
- coherent request/sample counters;
- finite non-negative timing data;
- explicit resource capability state;
- compact repeated-measurement records;
- safety markers proving that the benchmark did not promote Qdrant or change
  production defaults.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "qdrant_serving_performance_quality_v1"
INPUT_SCHEMA_VERSION = "qdrant_serving_performance_v1"

DEFAULT_REPORT_PATH = Path(
    "artifacts/reports/evaluation/"
    "qdrant_serving_performance_latest.json"
)
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def dump_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def is_finite_non_negative(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0.0
    )


def is_positive_int(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value > 0
    )


def is_non_negative_int(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _summary_valid(
    summary: Mapping[str, Any],
    *,
    expected_count: int | None = None,
) -> bool:
    count = summary.get("count")
    if not is_non_negative_int(count):
        return False
    if expected_count is not None and count != expected_count:
        return False

    fields = (
        "mean_ms",
        "std_ms",
        "min_ms",
        "p50_ms",
        "p95_ms",
        "max_ms",
    )

    if count == 0:
        return all(summary.get(field) is None for field in fields)

    if not all(
        is_finite_non_negative(summary.get(field))
        for field in fields
    ):
        return False

    return (
        float(summary["min_ms"])
        <= float(summary["p50_ms"])
        <= float(summary["p95_ms"])
        <= float(summary["max_ms"])
    )


def _resource_section_valid(
    resources: Mapping[str, Any],
) -> bool:
    process = _mapping(resources.get("process"))
    system = _mapping(resources.get("system"))
    docker = _mapping(resources.get("docker"))
    gpu = _mapping(resources.get("gpu"))
    policy = _mapping(resources.get("sampling_policy"))

    process_explicit = isinstance(process.get("supported"), bool)
    system_explicit = isinstance(system.get("supported"), bool)

    if process.get("supported") is True:
        process_explicit = (
            process_explicit
            and is_positive_int(process.get("sample_count"))
            and is_finite_non_negative(
                process.get("rss_bytes_peak")
            )
        )

    if system.get("supported") is True:
        system_explicit = (
            system_explicit
            and is_positive_int(system.get("sample_count"))
            and is_finite_non_negative(
                system.get("memory_percent_peak")
            )
        )

    def capability_explicit(value: Any) -> bool:
        payload = _mapping(value)
        return isinstance(payload.get("supported"), bool)

    docker_explicit = (
        capability_explicit(docker.get("before"))
        and capability_explicit(docker.get("after"))
    )
    gpu_explicit = (
        capability_explicit(gpu.get("before"))
        and capability_explicit(gpu.get("after"))
    )

    return (
        process_explicit
        and system_explicit
        and docker_explicit
        and gpu_explicit
        and policy.get("process_and_system") == "periodic"
        and policy.get("docker_and_gpu") == "before_after_only"
        and is_finite_non_negative(policy.get("interval_sec"))
        and float(policy["interval_sec"]) > 0.0
    )


def _record_is_compact(
    record: Mapping[str, Any],
    *,
    timing_key: str,
) -> bool:
    return (
        "canonical_ids" not in record
        and is_positive_int(record.get("result_ids_count"))
        and is_sha256(record.get("result_ids_digest"))
        and is_positive_int(record.get("result_count"))
        and record.get("result_count")
        == record.get("result_ids_count")
        and is_finite_non_negative(record.get(timing_key))
    )


def _scenario_valid(
    scenario: Mapping[str, Any],
    *,
    expected_count: int,
    timing_summary_key: str,
    timing_record_key: str,
) -> tuple[bool, list[str]]:
    problems: list[str] = []
    records = _sequence(scenario.get("records"))
    errors = _sequence(scenario.get("errors"))

    observed_count = scenario.get("request_count")
    if observed_count is None:
        observed_count = scenario.get("task_count")

    checks = {
        "request_count": observed_count == expected_count,
        "success_count": scenario.get("success_count")
        == expected_count,
        "error_count": scenario.get("error_count") == 0,
        "records_count": len(records) == expected_count,
        "errors_empty": len(errors) == 0,
        "wall_time": is_finite_non_negative(
            scenario.get("wall_time_ms")
        ),
        "throughput": is_finite_non_negative(
            scenario.get("throughput_rps")
        ),
        "latency_summary": _summary_valid(
            _mapping(scenario.get(timing_summary_key)),
            expected_count=expected_count,
        ),
        "resources": _resource_section_valid(
            _mapping(scenario.get("resources"))
        ),
        "compact_records": all(
            isinstance(record, Mapping)
            and _record_is_compact(
                record,
                timing_key=timing_record_key,
            )
            for record in records
        ),
    }

    for name, ok in checks.items():
        if not ok:
            problems.append(name)

    return all(checks.values()), problems


def _quality_section_valid(
    section: Mapping[str, Any],
    *,
    expected_count: int,
    top_k_values: set[int],
) -> tuple[bool, list[str]]:
    problems: list[str] = []
    comparisons = _sequence(section.get("comparisons"))

    if section.get("comparison_count") != expected_count:
        problems.append("comparison_count")
    if section.get("missing_comparison_count") != 0:
        problems.append("missing_comparison_count")
    if section.get("mean_overlap_at_k") != 1.0:
        problems.append("mean_overlap_at_k")
    if section.get("min_overlap_at_k") != 1.0:
        problems.append("min_overlap_at_k")
    if section.get("exact_same_order_count") != expected_count:
        problems.append("exact_same_order_count")
    if section.get("exact_same_order_all") is not True:
        problems.append("exact_same_order_all")
    if len(comparisons) != expected_count:
        problems.append("comparisons_length")

    for index, row in enumerate(comparisons):
        if not isinstance(row, Mapping):
            problems.append(f"comparison_{index}:not_object")
            continue

        top_k = row.get("top_k")
        row_ok = (
            row.get("comparison_available") is True
            and top_k in top_k_values
            and row.get("reference_count") == top_k
            and row.get("candidate_count") == top_k
            and row.get("overlap_count") == top_k
            and row.get("overlap_ratio") == 1.0
            and row.get("exact_same_order") is True
            and row.get("same_set") is True
            and row.get("reference_ids")
            == row.get("candidate_ids")
            and len(_sequence(row.get("reference_ids"))) == top_k
            and is_sha256(row.get("reference_ids_digest"))
            and row.get("reference_ids_digest")
            == row.get("candidate_ids_digest")
            and _sequence(row.get("duplicate_reference_ids"))
            == []
            and _sequence(row.get("duplicate_candidate_ids"))
            == []
            and _sequence(row.get("reference_only")) == []
            and _sequence(row.get("candidate_only")) == []
        )
        if not row_ok:
            problems.append(f"comparison_{index}:invalid")

    for name in ("file_determinism", "qdrant_determinism"):
        payload = _mapping(section.get(name))
        stable = payload.get("stable")
        stable_ok = stable is True or stable is None
        if (
            not stable_ok
            or payload.get("failure_count") != 0
            or _sequence(payload.get("failures"))
        ):
            problems.append(name)

    return len(problems) == 0, problems


def _fresh_quality_valid(
    payload: Mapping[str, Any],
    *,
    expected_top_k: int,
) -> bool:
    return (
        payload.get("top_k") == expected_top_k
        and payload.get("reference_count") == expected_top_k
        and payload.get("candidate_count") == expected_top_k
        and payload.get("overlap_count") == expected_top_k
        and payload.get("overlap_ratio") == 1.0
        and payload.get("exact_same_order") is True
        and payload.get("same_set") is True
        and _sequence(payload.get("duplicate_reference_ids")) == []
        and _sequence(payload.get("duplicate_candidate_ids")) == []
        and _sequence(payload.get("reference_only")) == []
        and _sequence(payload.get("candidate_only")) == []
    )


def _fresh_target_valid(
    payload: Mapping[str, Any],
    *,
    expected_top_k: int,
) -> bool:
    first_request = _mapping(payload.get("first_request"))
    timings = _mapping(first_request.get("derived_timing_ms"))

    return (
        is_finite_non_negative(payload.get("startup_ms"))
        and first_request.get("status_code") == 200
        and first_request.get("top_k") == expected_top_k
        and first_request.get("result_count") == expected_top_k
        and len(_sequence(first_request.get("canonical_ids")))
        == expected_top_k
        and is_finite_non_negative(
            first_request.get("client_latency_ms")
        )
        and all(
            is_finite_non_negative(timings.get(name))
            for name in (
                "server_known_stage_sum_ms",
                "server_unattributed_ms",
                "client_overhead_ms",
            )
        )
        and _resource_section_valid(
            _mapping(payload.get("resources"))
        )
        and isinstance(payload.get("log_path"), str)
        and bool(payload.get("log_path"))
    )


def _resource_capabilities_explicit(
    *,
    backend: Mapping[str, Any],
    api: Mapping[str, Any],
) -> bool:
    """Validate resource evidence independently from scenario success."""

    resource_sections: list[Mapping[str, Any]] = []

    backend_sequential = _mapping(backend.get("sequential"))
    for name in ("file", "qdrant"):
        resource_sections.append(
            _mapping(
                _mapping(backend_sequential.get(name)).get(
                    "resources"
                )
            )
        )

    backend_concurrent = _mapping(backend.get("concurrent"))
    for name in ("file", "qdrant"):
        for row in _sequence(backend_concurrent.get(name)):
            resource_sections.append(
                _mapping(_mapping(row).get("resources"))
            )

    fresh = _mapping(api.get("fresh_process"))
    for name in ("file_dense", "qdrant"):
        resource_sections.append(
            _mapping(_mapping(fresh.get(name)).get("resources"))
        )

    api_sequential = _mapping(api.get("warm_sequential"))
    for name in ("file_dense", "qdrant"):
        resource_sections.append(
            _mapping(
                _mapping(api_sequential.get(name)).get(
                    "resources"
                )
            )
        )

    api_concurrent = _mapping(api.get("warm_concurrent"))
    for name in ("file_dense", "qdrant"):
        for row in _sequence(api_concurrent.get(name)):
            resource_sections.append(
                _mapping(_mapping(row).get("resources"))
            )

    return bool(resource_sections) and all(
        _resource_section_valid(resources)
        for resources in resource_sections
    )


def evaluate_report(
    source: Mapping[str, Any],
    *,
    strict: bool,
    report_exists: bool = True,
) -> dict[str, Any]:
    problems: list[str] = []

    summary = _mapping(source.get("summary"))
    config = _mapping(source.get("config"))
    resolved = _mapping(source.get("resolved_preset"))
    collection = _mapping(source.get("collection"))
    query_set = _mapping(source.get("query_set"))
    encoding = _mapping(source.get("encoding"))
    backend = _mapping(source.get("backend_only"))
    api = _mapping(source.get("api_serving"))
    quality = _mapping(source.get("quality"))
    verdict_src = _mapping(source.get("verdict"))
    report_policy = _mapping(source.get("report_policy"))

    preset_name = source.get("preset")
    preset_cfg = _mapping(
        _mapping(config.get("presets")).get(preset_name)
    )

    query_count = summary.get("query_count")
    top_k_values_raw = _sequence(summary.get("top_k_values"))
    top_k_values = {
        int(value)
        for value in top_k_values_raw
        if is_positive_int(value)
    }

    backend_cfg = _mapping(resolved.get("backend"))
    api_cfg = _mapping(resolved.get("api"))
    encoding_cfg = _mapping(resolved.get("encoding"))

    backend_rounds = backend_cfg.get("measured_rounds")
    api_rounds = api_cfg.get("measured_rounds")
    encoding_rounds = encoding_cfg.get("measured_rounds")
    backend_levels = _sequence(
        backend_cfg.get("concurrency_levels")
    )
    api_levels = _sequence(
        api_cfg.get("concurrency_levels")
    )

    base_counts_valid = (
        is_positive_int(query_count)
        and top_k_values
        and is_positive_int(backend_rounds)
        and is_positive_int(api_rounds)
        and is_positive_int(encoding_rounds)
    )

    backend_expected_count = (
        int(query_count)
        * len(top_k_values)
        * int(backend_rounds)
        if base_counts_valid
        else 0
    )
    api_expected_count = (
        int(query_count)
        * len(top_k_values)
        * int(api_rounds)
        if base_counts_valid
        else 0
    )
    encoding_expected_count = (
        int(query_count) * int(encoding_rounds)
        if base_counts_valid
        else 0
    )

    checks: dict[str, bool] = {
        "report_exists": bool(report_exists),
        "input_schema_version_ok": source.get("schema_version")
        == INPUT_SCHEMA_VERSION,
        "preset_valid": preset_name in {"smoke", "full"},
        "generated_at_present": bool(
            source.get("generated_at_utc")
        ),
        "build_id_present": bool(summary.get("build_id")),
        "collection_name_present": bool(
            summary.get("collection_name")
        ),
        "profile_name_present": bool(
            summary.get("profile_name")
        ),
        "query_count_positive": is_positive_int(query_count),
        "top_k_values_valid": (
            len(top_k_values) == len(top_k_values_raw)
            and bool(top_k_values)
        ),
        "resolved_preset_matches_config": (
            bool(preset_cfg) and dict(resolved) == dict(preset_cfg)
        ),
        "query_set_count_matches_summary": (
            query_set.get("selected_query_count") == query_count
            and len(_sequence(query_set.get("query_ids")))
            == query_count
            and len(_sequence(query_set.get("queries")))
            == query_count
        ),
        "safety_benchmark_only": source.get("benchmark_only")
        is True,
        "safety_production_default_unchanged": source.get(
            "production_default_changed"
        )
        is False,
        "safety_public_qdrant_not_promoted": source.get(
            "public_qdrant_promoted"
        )
        is False,
        "safety_no_fallback": source.get("fallback_used")
        is False,
        "report_policy_valid": (
            report_policy.get("repeated_measurement_ids")
            == "sha256_digest_only"
            and report_policy.get("quality_comparison_ids")
            == "retained_once_per_scenario"
            and report_policy.get("resource_raw_samples")
            == "summary_only"
            and report_policy.get("docker_raw_payload")
            == "omitted"
        ),
        "summary_error_count_zero": summary.get("error_count")
        == 0,
        "top_level_errors_empty": _sequence(
            source.get("errors")
        )
        == [],
        "source_verdict_ok": verdict_src.get("ok") is True,
        "source_verdict_no_failed_checks": _sequence(
            verdict_src.get("failed_checks")
        )
        == [],
        "source_quality_exact": (
            verdict_src.get("error_count") == 0
            and verdict_src.get("missing_comparison_count") == 0
            and verdict_src.get("mean_overlap_at_k") == 1.0
            and verdict_src.get("min_overlap_at_k") == 1.0
            and verdict_src.get("result_count_mismatch_count")
            == 0
            and verdict_src.get("duplicate_id_failure_count")
            == 0
            and verdict_src.get("determinism_failure_count")
            == 0
        ),
    }

    embedding_shape = _sequence(summary.get("embedding_shape"))
    checks["collection_compatible"] = (
        collection.get("collection_name")
        == summary.get("collection_name")
        and collection.get("status") == "green"
        and collection.get("optimizer_status") == "ok"
        and collection.get("points_count")
        == summary.get("corpus_doc_count")
        and len(embedding_shape) == 2
        and collection.get("vector_size") == embedding_shape[1]
        and collection.get("distance")
        == _mapping(config.get("retrieval")).get(
            "expected_distance"
        )
    )

    encoding_samples = _sequence(encoding.get("samples"))
    checks["encoding_valid"] = (
        is_finite_non_negative(encoding.get("model_load_ms"))
        and is_finite_non_negative(
            encoding.get("first_encode_ms")
        )
        and _summary_valid(
            _mapping(encoding.get("latency")),
            expected_count=encoding_expected_count,
        )
        and len(encoding_samples) == encoding_expected_count
        and all(
            isinstance(row, Mapping)
            and is_finite_non_negative(row.get("latency_ms"))
            and row.get("dimension") == embedding_shape[1]
            and row.get("all_finite") is True
            and is_finite_non_negative(row.get("norm"))
            and abs(float(row.get("norm")) - 1.0) <= 1e-4
            for row in encoding_samples
        )
    )

    checks["backend_not_skipped"] = backend.get("skipped") is False
    checks["api_not_skipped"] = api.get("skipped") is False

    construction = _mapping(backend.get("construction"))
    checks["backend_construction_valid"] = all(
        is_finite_non_negative(construction.get(name))
        for name in ("file_ms", "qdrant_ms")
    )

    first = _mapping(backend.get("first_request"))
    first_file = _mapping(first.get("file"))
    first_qdrant = _mapping(first.get("qdrant"))
    first_comparison = _mapping(first.get("comparison"))
    first_top_k = min(top_k_values) if top_k_values else 0
    checks["backend_first_request_valid"] = (
        first.get("errors") == []
        and first_file.get("result_count") == first_top_k
        and first_qdrant.get("result_count") == first_top_k
        and len(_sequence(first_file.get("canonical_ids")))
        == first_top_k
        and first_file.get("canonical_ids")
        == first_qdrant.get("canonical_ids")
        and first_comparison.get("overlap_ratio") == 1.0
        and first_comparison.get("exact_same_order") is True
    )

    backend_seq = _mapping(backend.get("sequential"))
    backend_seq_ok = True
    for name in ("file", "qdrant"):
        ok, subproblems = _scenario_valid(
            _mapping(backend_seq.get(name)),
            expected_count=backend_expected_count,
            timing_summary_key="latency",
            timing_record_key="wall_latency_ms",
        )
        backend_seq_ok = backend_seq_ok and ok
        problems.extend(
            f"backend_sequential/{name}:{problem}"
            for problem in subproblems
        )
    checks["backend_sequential_valid"] = backend_seq_ok

    backend_concurrent = _mapping(backend.get("concurrent"))
    backend_concurrent_ok = True
    for name in ("file", "qdrant"):
        rows = _sequence(backend_concurrent.get(name))
        actual_levels = [
            row.get("concurrency")
            for row in rows
            if isinstance(row, Mapping)
        ]
        if actual_levels != backend_levels:
            backend_concurrent_ok = False
            problems.append(
                f"backend_concurrent/{name}:levels"
            )
        for row in rows:
            ok, subproblems = _scenario_valid(
                _mapping(row),
                expected_count=backend_expected_count,
                timing_summary_key="latency",
                timing_record_key="wall_latency_ms",
            )
            backend_concurrent_ok = backend_concurrent_ok and ok
            problems.extend(
                f"backend_concurrent/{name}/"
                f"{_mapping(row).get('concurrency')}:{problem}"
                for problem in subproblems
            )
    checks["backend_concurrent_valid"] = backend_concurrent_ok

    fresh = _mapping(api.get("fresh_process"))
    checks["api_fresh_valid"] = (
        fresh.get("enabled") is True
        and _fresh_target_valid(
            _mapping(fresh.get("file_dense")),
            expected_top_k=first_top_k,
        )
        and _fresh_target_valid(
            _mapping(fresh.get("qdrant")),
            expected_top_k=first_top_k,
        )
        and _fresh_quality_valid(
            _mapping(fresh.get("quality")),
            expected_top_k=first_top_k,
        )
    )

    warm_process = _mapping(api.get("warm_process"))
    checks["api_warm_process_valid"] = (
        is_finite_non_negative(
            warm_process.get("startup_ms")
        )
        and is_positive_int(warm_process.get("process_pid"))
        and isinstance(warm_process.get("log_path"), str)
        and bool(warm_process.get("log_path"))
        and warm_process.get("warmup_rounds")
        == api_cfg.get("warmup_rounds")
    )

    api_seq = _mapping(api.get("warm_sequential"))
    api_seq_ok = True
    for name in ("file_dense", "qdrant"):
        ok, subproblems = _scenario_valid(
            _mapping(api_seq.get(name)),
            expected_count=api_expected_count,
            timing_summary_key="client_latency",
            timing_record_key="client_latency_ms",
        )
        api_seq_ok = api_seq_ok and ok
        problems.extend(
            f"api_sequential/{name}:{problem}"
            for problem in subproblems
        )
    checks["api_sequential_valid"] = api_seq_ok

    api_concurrent = _mapping(api.get("warm_concurrent"))
    api_concurrent_ok = True
    for name in ("file_dense", "qdrant"):
        rows = _sequence(api_concurrent.get(name))
        actual_levels = [
            row.get("concurrency")
            for row in rows
            if isinstance(row, Mapping)
        ]
        if actual_levels != api_levels:
            api_concurrent_ok = False
            problems.append(f"api_concurrent/{name}:levels")
        for row in rows:
            ok, subproblems = _scenario_valid(
                _mapping(row),
                expected_count=api_expected_count,
                timing_summary_key="client_latency",
                timing_record_key="client_latency_ms",
            )
            api_concurrent_ok = api_concurrent_ok and ok
            problems.extend(
                f"api_concurrent/{name}/"
                f"{_mapping(row).get('concurrency')}:{problem}"
                for problem in subproblems
            )
    checks["api_concurrent_valid"] = api_concurrent_ok

    expected_quality_sections = {
        "backend_sequential",
        "api_fresh",
        "api_sequential",
        *{
            f"backend_concurrent_{level}"
            for level in backend_levels
        },
        *{
            f"api_concurrent_{level}"
            for level in api_levels
        },
    }
    quality_sections = _mapping(quality.get("sections"))
    checks["quality_section_names_valid"] = (
        set(quality_sections.keys())
        == expected_quality_sections
    )

    quality_sections_ok = True
    for name, section in quality_sections.items():
        expected_count = (
            1
            if name == "api_fresh"
            else int(query_count) * len(top_k_values)
            if is_positive_int(query_count)
            else 0
        )
        ok, subproblems = _quality_section_valid(
            _mapping(section),
            expected_count=expected_count,
            top_k_values=top_k_values,
        )
        quality_sections_ok = quality_sections_ok and ok
        problems.extend(
            f"quality/{name}:{problem}"
            for problem in subproblems
        )
    checks["quality_sections_valid"] = quality_sections_ok

    checks["resource_capabilities_explicit"] = (
        _resource_capabilities_explicit(
            backend=backend,
            api=api,
        )
    )

    structural_required = [
        "report_exists",
        "input_schema_version_ok",
        "preset_valid",
        "generated_at_present",
        "build_id_present",
        "collection_name_present",
        "profile_name_present",
        "query_count_positive",
        "top_k_values_valid",
        "resolved_preset_matches_config",
        "query_set_count_matches_summary",
        "collection_compatible",
        "encoding_valid",
        "backend_not_skipped",
        "api_not_skipped",
        "backend_construction_valid",
        "summary_error_count_zero",
        "top_level_errors_empty",
    ]

    strict_required = [
        "safety_benchmark_only",
        "safety_production_default_unchanged",
        "safety_public_qdrant_not_promoted",
        "safety_no_fallback",
        "report_policy_valid",
        "source_verdict_ok",
        "source_verdict_no_failed_checks",
        "source_quality_exact",
        "backend_first_request_valid",
        "backend_sequential_valid",
        "backend_concurrent_valid",
        "api_fresh_valid",
        "api_warm_process_valid",
        "api_sequential_valid",
        "api_concurrent_valid",
        "quality_section_names_valid",
        "quality_sections_valid",
        "resource_capabilities_explicit",
    ]

    required_names = list(structural_required)
    if strict:
        required_names.extend(strict_required)

    required_failed = [
        name for name in required_names if not checks.get(name, False)
    ]

    verdict = {
        "ok": len(required_failed) == 0,
        "strict": bool(strict),
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_iso(),
        "summary": {
            "input_schema_version": source.get("schema_version"),
            "preset": preset_name,
            "build_id": summary.get("build_id"),
            "collection_name": summary.get("collection_name"),
            "profile_name": summary.get("profile_name"),
            "query_count": query_count,
            "top_k_values": top_k_values_raw,
            "backend_concurrency_levels": backend_levels,
            "api_concurrency_levels": api_levels,
            "source_error_count": summary.get("error_count"),
            "source_comparison_count": verdict_src.get(
                "comparison_count"
            ),
            "source_mean_overlap_at_k": verdict_src.get(
                "mean_overlap_at_k"
            ),
            "source_min_overlap_at_k": verdict_src.get(
                "min_overlap_at_k"
            ),
        },
        "checks": checks,
        "problems": sorted(set(problems)),
        "verdict": verdict,
    }


def build_markdown(report: Mapping[str, Any]) -> str:
    summary = _mapping(report.get("summary"))
    verdict = _mapping(report.get("verdict"))

    lines = [
        "# Qdrant Serving Performance Quality",
        "",
        f"- schema_version: `{report.get('schema_version')}`",
        (
            "- input_schema_version: "
            f"`{summary.get('input_schema_version')}`"
        ),
        f"- preset: `{summary.get('preset')}`",
        f"- strict: `{verdict.get('strict')}`",
        f"- ok: `{verdict.get('ok')}`",
        (
            "- required_failed_count: "
            f"`{verdict.get('required_failed_count')}`"
        ),
        (
            "- required_failed_checks: "
            f"`{verdict.get('required_failed_checks')}`"
        ),
        "",
        "## Summary",
        "",
        f"- build_id: `{summary.get('build_id')}`",
        (
            "- collection_name: "
            f"`{summary.get('collection_name')}`"
        ),
        f"- profile_name: `{summary.get('profile_name')}`",
        f"- query_count: `{summary.get('query_count')}`",
        f"- top_k_values: `{summary.get('top_k_values')}`",
        (
            "- backend_concurrency_levels: "
            f"`{summary.get('backend_concurrency_levels')}`"
        ),
        (
            "- api_concurrency_levels: "
            f"`{summary.get('api_concurrency_levels')}`"
        ),
        (
            "- source_error_count: "
            f"`{summary.get('source_error_count')}`"
        ),
        (
            "- source_comparison_count: "
            f"`{summary.get('source_comparison_count')}`"
        ),
        (
            "- source_mean_overlap_at_k: "
            f"`{summary.get('source_mean_overlap_at_k')}`"
        ),
        (
            "- source_min_overlap_at_k: "
            f"`{summary.get('source_min_overlap_at_k')}`"
        ),
        "",
        "## Checks",
        "",
    ]

    for name, value in _mapping(report.get("checks")).items():
        lines.append(
            f"- {'✅' if value else '❌'} `{name}` = `{value}`"
        )

    problems = _sequence(report.get("problems"))
    if problems:
        lines.extend(["", "## Problems", ""])
        lines.extend(f"- `{problem}`" for problem in problems)

    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_PATH,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    run_ts = utc_ts()
    report_exists = args.report_path.exists()
    source = (
        load_json(args.report_path)
        if report_exists
        else {}
    )

    quality_report = evaluate_report(
        source,
        strict=bool(args.strict),
        report_exists=report_exists,
    )
    quality_report["run_ts"] = run_ts
    quality_report["report_path"] = str(args.report_path)

    latest_json = (
        args.output_dir
        / "qdrant_serving_performance_quality_latest.json"
    )
    latest_md = (
        args.output_dir
        / "qdrant_serving_performance_quality_latest.md"
    )
    history_json = (
        args.output_dir
        / "history"
        / f"qdrant_serving_performance_quality_{run_ts}.json"
    )
    history_md = (
        args.output_dir
        / "history"
        / f"qdrant_serving_performance_quality_{run_ts}.md"
    )

    markdown = build_markdown(quality_report)
    dump_json(latest_json, quality_report)
    dump_text(latest_md, markdown)
    dump_json(history_json, quality_report)
    dump_text(history_md, markdown)

    summary = quality_report["summary"]
    verdict = quality_report["verdict"]

    print(f"[OK] report_path={args.report_path}")
    print(f"[OK] schema_version={SCHEMA_VERSION}")
    print(
        "[OK] input_schema_version="
        f"{summary.get('input_schema_version')}"
    )
    print(f"[OK] preset={summary.get('preset')}")
    print(f"[OK] strict={args.strict}")
    print(f"[OK] build_id={summary.get('build_id')}")
    print(
        "[OK] collection_name="
        f"{summary.get('collection_name')}"
    )
    print(
        "[OK] profile_name="
        f"{summary.get('profile_name')}"
    )
    print(f"[OK] query_count={summary.get('query_count')}")
    print(
        "[OK] source_error_count="
        f"{summary.get('source_error_count')}"
    )
    print(
        "[OK] source_comparison_count="
        f"{summary.get('source_comparison_count')}"
    )
    print(
        "[OK] required_failed_count="
        f"{verdict.get('required_failed_count')}"
    )
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")

    if args.strict and verdict["required_failed_checks"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
