"""Pure helpers for the Qdrant serving-performance benchmark.

This module intentionally has no import-time side effects:

- it does not load the embedding model;
- it does not connect to Qdrant;
- it does not start Uvicorn;
- it does not write reports automatically.

The orchestration CLI lives in
``scripts.evaluation.run_qdrant_serving_performance``.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TypeVar

import numpy as np
import psutil
import yaml


CONFIG_SCHEMA_VERSION = "qdrant_serving_performance_config_v1"

T = TypeVar("T")


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def exception_chain(
    exc: BaseException,
    *,
    max_depth: int = 8,
) -> list[dict[str, Any]]:
    """Return a compact, cycle-safe exception cause/context chain."""

    if (
        not isinstance(max_depth, int)
        or isinstance(max_depth, bool)
        or max_depth <= 0
    ):
        raise ValueError("max_depth must be a positive integer")

    chain: list[dict[str, Any]] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    relation = "raised"

    while current is not None and len(chain) < max_depth:
        identity = id(current)
        if identity in seen:
            chain.append(
                {
                    "relation": relation,
                    "type": type(current).__name__,
                    "module": type(current).__module__,
                    "message": str(current),
                    "cycle_detected": True,
                }
            )
            break

        seen.add(identity)
        chain.append(
            {
                "relation": relation,
                "type": type(current).__name__,
                "module": type(current).__module__,
                "message": str(current),
                "cycle_detected": False,
            }
        )

        if current.__cause__ is not None:
            current = current.__cause__
            relation = "cause"
        elif (
            current.__context__ is not None
            and not current.__suppress_context__
        ):
            current = current.__context__
            relation = "context"
        else:
            current = None

    return chain


def exception_details(
    exc: BaseException,
) -> dict[str, Any]:
    """Serialize an exception without losing its root cause chain."""

    return {
        "error": f"{type(exc).__name__}: {exc}",
        "error_type": type(exc).__name__,
        "error_module": type(exc).__module__,
        "error_message": str(exc),
        "error_chain": exception_chain(exc),
    }


def normalize_path(path: str | Path | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"YAML config not found: {path}")

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML mapping in {path}")
    return payload


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")

    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue

            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSONL at {path}:{line_no}: {exc}"
                ) from exc

            if not isinstance(row, dict):
                raise ValueError(
                    f"Expected JSON object at {path}:{line_no}"
                )

            rows.append(row)

    return rows


def load_ids(path: Path) -> list[str]:
    payload = load_json(path)

    if isinstance(payload, list):
        return [str(value) for value in payload]

    if isinstance(payload, dict):
        for key in ("ids", "canonical_ids", "document_ids"):
            values = payload.get(key)
            if isinstance(values, list):
                return [str(value) for value in values]

    raise ValueError(f"Unsupported dense IDs JSON shape: {path}")


def enabled_queries(path: Path) -> list[dict[str, Any]]:
    return [
        row
        for row in read_jsonl(path)
        if row.get("enabled") is True
    ]


def resolve_query_text(row: Mapping[str, Any]) -> str:
    for key in ("query", "query_text", "text"):
        value = str(row.get(key) or "").strip()
        if value:
            return value

    raise ValueError(
        "Golden query row has no query text: "
        f"query_id={row.get('query_id')!r}"
    )


def select_queries(
    rows: Sequence[Mapping[str, Any]],
    *,
    max_queries: int | None,
) -> list[dict[str, Any]]:
    if max_queries is not None:
        if (
            not isinstance(max_queries, int)
            or isinstance(max_queries, bool)
            or max_queries <= 0
        ):
            raise ValueError(
                "max_queries must be null or a positive integer"
            )

    selected = rows if max_queries is None else rows[:max_queries]
    return [dict(row) for row in selected]


def _require_mapping(
    value: Any,
    *,
    name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _require_positive_int(
    value: Any,
    *,
    name: str,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
    ):
        raise ValueError(
            f"{name} must be a positive integer, got {value!r}"
        )
    return value


def _require_non_negative_int(
    value: Any,
    *,
    name: str,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise ValueError(
            f"{name} must be a non-negative integer, got {value!r}"
        )
    return value


def _validate_positive_unique_ints(
    values: Any,
    *,
    name: str,
) -> list[int]:
    if not isinstance(values, list) or not values:
        raise ValueError(f"{name} must be a non-empty list")

    normalized = [
        _require_positive_int(value, name=f"{name}[]")
        for value in values
    ]

    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} contains duplicate values")

    return normalized


def validate_benchmark_config(
    config: Mapping[str, Any],
) -> None:
    if config.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise ValueError(
            "Unexpected benchmark config schema_version: "
            f"{config.get('schema_version')!r}"
        )

    qdrant = _require_mapping(config.get("qdrant"), name="qdrant")
    retrieval = _require_mapping(
        config.get("retrieval"),
        name="retrieval",
    )
    api = _require_mapping(config.get("api"), name="api")
    presets = _require_mapping(config.get("presets"), name="presets")
    resources = _require_mapping(
        config.get("resources"),
        name="resources",
    )
    quality = _require_mapping(config.get("quality"), name="quality")
    output = _require_mapping(config.get("output"), name="output")

    _require_positive_int(qdrant.get("port"), name="qdrant.port")

    grpc_port = _require_positive_int(
        qdrant.get("grpc_port"),
        name="qdrant.grpc_port",
    )

    if grpc_port > 65535:
        raise ValueError(
            "qdrant.grpc_port must be <= 65535"
        )

    if not isinstance(qdrant.get("prefer_grpc"), bool):
        raise ValueError(
            "qdrant.prefer_grpc must be boolean"
        )

    timeout_sec = qdrant.get("timeout_sec")
    if (
        not isinstance(timeout_sec, (int, float))
        or isinstance(timeout_sec, bool)
        or not math.isfinite(float(timeout_sec))
        or float(timeout_sec) <= 0
    ):
        raise ValueError("qdrant.timeout_sec must be positive")

    if not str(qdrant.get("collection_name") or "").strip():
        raise ValueError("qdrant.collection_name is required")

    profile = _require_mapping(
        qdrant.get("profile"),
        name="qdrant.profile",
    )
    if not str(profile.get("name") or "").strip():
        raise ValueError("qdrant.profile.name is required")

    exact = bool(profile.get("exact", False))
    hnsw_ef = profile.get("hnsw_ef")
    if exact and hnsw_ef is not None:
        raise ValueError(
            "qdrant.profile.hnsw_ef must be null for exact search"
        )
    if hnsw_ef is not None:
        _require_positive_int(
            hnsw_ef,
            name="qdrant.profile.hnsw_ef",
        )

    for key in ("manifest_path", "golden_queries_path"):
        if not str(retrieval.get(key) or "").strip():
            raise ValueError(f"retrieval.{key} is required")

    _require_positive_int(api.get("port"), name="api.port")

    for key in (
        "startup_timeout_sec",
        "startup_poll_interval_sec",
        "request_timeout_sec",
    ):
        value = api.get(key)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or float(value) <= 0
        ):
            raise ValueError(f"api.{key} must be positive")

    for target_name in ("file_dense", "qdrant"):
        target = _require_mapping(
            api.get(target_name),
            name=f"api.{target_name}",
        )
        if not str(target.get("path") or "").startswith("/"):
            raise ValueError(
                f"api.{target_name}.path must start with '/'"
            )
        _require_mapping(
            target.get("params") or {},
            name=f"api.{target_name}.params",
        )

    if not presets:
        raise ValueError("presets must not be empty")

    for preset_name, raw_preset in presets.items():
        preset = _require_mapping(
            raw_preset,
            name=f"presets.{preset_name}",
        )

        max_queries = preset.get("max_queries")
        if max_queries is not None:
            _require_positive_int(
                max_queries,
                name=f"presets.{preset_name}.max_queries",
            )

        _validate_positive_unique_ints(
            preset.get("top_k_values"),
            name=f"presets.{preset_name}.top_k_values",
        )

        for section_name in ("encoding", "backend", "api"):
            section = _require_mapping(
                preset.get(section_name),
                name=f"presets.{preset_name}.{section_name}",
            )
            _require_non_negative_int(
                section.get("warmup_rounds"),
                name=(
                    f"presets.{preset_name}."
                    f"{section_name}.warmup_rounds"
                ),
            )
            _require_positive_int(
                section.get("measured_rounds"),
                name=(
                    f"presets.{preset_name}."
                    f"{section_name}.measured_rounds"
                ),
            )

            if section_name in ("backend", "api"):
                _validate_positive_unique_ints(
                    section.get("concurrency_levels"),
                    name=(
                        f"presets.{preset_name}."
                        f"{section_name}.concurrency_levels"
                    ),
                )

        fresh_process = _require_mapping(
            preset.get("fresh_process"),
            name=f"presets.{preset_name}.fresh_process",
        )
        if not isinstance(fresh_process.get("enabled"), bool):
            raise ValueError(
                f"presets.{preset_name}.fresh_process.enabled "
                "must be boolean"
            )

    interval = resources.get("sample_interval_sec")
    if (
        not isinstance(interval, (int, float))
        or isinstance(interval, bool)
        or not math.isfinite(float(interval))
        or float(interval) <= 0
    ):
        raise ValueError(
            "resources.sample_interval_sec must be positive"
        )

    for key in (
        "collect_process_memory",
        "collect_system_memory",
        "collect_docker_stats",
        "collect_gpu_stats",
    ):
        if not isinstance(resources.get(key), bool):
            raise ValueError(f"resources.{key} must be boolean")

    max_error_count = quality.get("max_error_count")
    _require_non_negative_int(
        max_error_count,
        name="quality.max_error_count",
    )

    for key in (
        "min_mean_overlap_at_k",
        "min_query_overlap_at_k",
    ):
        value = quality.get(key)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or not 0.0 <= float(value) <= 1.0
        ):
            raise ValueError(f"quality.{key} must be in [0, 1]")

    for key in (
        "require_exact_same_order",
        "require_result_count_match",
    ):
        if not isinstance(quality.get(key), bool):
            raise ValueError(f"quality.{key} must be boolean")

    if not str(output.get("output_dir") or "").strip():
        raise ValueError("output.output_dir is required")


def resolve_preset(
    config: Mapping[str, Any],
    preset_name: str,
) -> dict[str, Any]:
    validate_benchmark_config(config)

    presets = config["presets"]
    if preset_name not in presets:
        raise ValueError(
            f"Unknown benchmark preset: {preset_name!r}"
        )

    return deepcopy(dict(presets[preset_name]))


def is_finite_non_negative(value: Any) -> bool:
    return (
        isinstance(value, (int, float, np.integer, np.floating))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0.0
    )


def summarize_samples(
    values_ms: Sequence[float],
) -> dict[str, float | int | None]:
    values = [float(value) for value in values_ms]

    invalid = [
        value
        for value in values
        if not math.isfinite(value) or value < 0.0
    ]
    if invalid:
        raise ValueError(
            "Latency samples must be finite and non-negative: "
            f"{invalid[:5]}"
        )

    if not values:
        return {
            "count": 0,
            "mean_ms": None,
            "std_ms": None,
            "min_ms": None,
            "p50_ms": None,
            "p95_ms": None,
            "max_ms": None,
        }

    array = np.asarray(values, dtype=np.float64)

    return {
        "count": int(array.size),
        "mean_ms": float(np.mean(array)),
        "std_ms": float(np.std(array)),
        "min_ms": float(np.min(array)),
        "p50_ms": float(np.percentile(array, 50)),
        "p95_ms": float(np.percentile(array, 95)),
        "max_ms": float(np.max(array)),
    }


def backend_candidate_ids(result: Any) -> list[str]:
    candidates = getattr(result, "candidates", None)
    if candidates is None:
        raise ValueError("Backend result has no candidates")

    values: list[str] = []
    for index, candidate in enumerate(candidates, start=1):
        canonical_id = str(
            getattr(candidate, "canonical_id", "") or ""
        ).strip()
        if not canonical_id:
            raise ValueError(
                f"Backend candidate {index} has no canonical_id"
            )
        values.append(canonical_id)

    return values


def api_result_ids(payload: Mapping[str, Any]) -> list[str]:
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("API payload.results must be a list")

    values: list[str] = []

    for index, item in enumerate(results, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(
                f"API result {index} must be an object"
            )

        document = item.get("document")
        if not isinstance(document, Mapping):
            raise ValueError(
                f"API result {index}.document must be an object"
            )

        canonical_id = str(
            document.get("canonical_id") or ""
        ).strip()
        if not canonical_id:
            raise ValueError(
                f"API result {index} has no canonical_id"
            )

        values.append(canonical_id)

    return values


def api_timing_ms(
    payload: Mapping[str, Any],
) -> dict[str, float]:
    meta = payload.get("meta")
    if not isinstance(meta, Mapping):
        return {}

    raw = meta.get("timing_ms")
    if not isinstance(raw, Mapping):
        return {}

    timings: dict[str, float] = {}
    for key, value in raw.items():
        if not is_finite_non_negative(value):
            raise ValueError(
                f"Invalid API timing {key}={value!r}"
            )
        timings[str(key)] = float(value)

    return timings



def derive_api_timings(
    *,
    client_latency_ms: float,
    server_timing_ms: Mapping[str, float],
) -> dict[str, float | None]:
    """Derive non-overlapping diagnostic timing fields.

    ``server_known_stage_sum_ms`` sums all server stages except ``total_ms``.
    ``server_unattributed_ms`` is the non-negative remainder inside the server
    total. ``client_overhead_ms`` is the non-negative remainder between the
    client-observed latency and server total.
    """

    if not is_finite_non_negative(client_latency_ms):
        raise ValueError(
            "client_latency_ms must be finite and non-negative"
        )

    normalized: dict[str, float] = {}
    for key, value in server_timing_ms.items():
        if not is_finite_non_negative(value):
            raise ValueError(
                f"Invalid server timing {key}={value!r}"
            )
        normalized[str(key)] = float(value)

    total_ms = normalized.get("total_ms")
    known_stage_sum_ms = sum(
        value
        for key, value in normalized.items()
        if key != "total_ms"
    )

    if total_ms is None:
        return {
            "server_known_stage_sum_ms": (
                known_stage_sum_ms if normalized else None
            ),
            "server_unattributed_ms": None,
            "client_overhead_ms": None,
        }

    return {
        "server_known_stage_sum_ms": known_stage_sum_ms,
        "server_unattributed_ms": max(
            0.0,
            total_ms - known_stage_sum_ms,
        ),
        "client_overhead_ms": max(
            0.0,
            float(client_latency_ms) - total_ms,
        ),
    }


def result_ids_digest(values: Sequence[str]) -> str:
    """Return an order-sensitive SHA-256 digest for ranked result IDs."""

    normalized = [str(value) for value in values]
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def compact_result_record(
    row: Mapping[str, Any],
) -> dict[str, Any]:
    """Remove repeated ranked IDs while retaining count and stable digest."""

    compact = dict(row)
    raw_ids = compact.pop("canonical_ids", None)

    if raw_ids is None:
        return compact

    if not isinstance(raw_ids, Sequence) or isinstance(
        raw_ids,
        (str, bytes),
    ):
        raise ValueError("canonical_ids must be a sequence")

    ids = [str(value) for value in raw_ids]
    compact["result_ids_count"] = len(ids)
    compact["result_ids_digest"] = result_ids_digest(ids)
    return compact


def summarize_quality_sections(
    *,
    comparison_sections: Mapping[str, Mapping[str, Any]],
    quality_cfg: Mapping[str, Any],
    error_count: int,
) -> dict[str, Any]:
    """Aggregate quality checks across backend and serving scenarios."""

    overlaps: list[float] = []
    exact_flags: list[bool] = []
    result_count_flags: list[bool] = []
    duplicate_flags: list[bool] = []
    missing_count = 0
    determinism_failures = 0

    for section in comparison_sections.values():
        missing_count += int(
            section.get("missing_comparison_count", 0)
        )
        determinism_failures += int(
            section.get("file_determinism", {}).get(
                "failure_count",
                0,
            )
        )
        determinism_failures += int(
            section.get("qdrant_determinism", {}).get(
                "failure_count",
                0,
            )
        )

        for row in section.get("comparisons", []):
            if row.get("comparison_available") is not True:
                continue

            overlap = row.get("overlap_ratio")
            if is_finite_non_negative(overlap):
                overlaps.append(float(overlap))

            exact_flags.append(
                bool(row.get("exact_same_order"))
            )

            top_k = row.get("top_k")
            reference_count = row.get("reference_count")
            candidate_count = row.get("candidate_count")
            result_count_flags.append(
                isinstance(top_k, int)
                and not isinstance(top_k, bool)
                and reference_count == top_k
                and candidate_count == top_k
            )

            duplicate_flags.append(
                not row.get("duplicate_reference_ids")
                and not row.get("duplicate_candidate_ids")
            )

    mean_overlap = (
        float(np.mean(overlaps)) if overlaps else None
    )
    min_overlap = min(overlaps) if overlaps else None

    result_count_mismatch_count = sum(
        not value for value in result_count_flags
    )
    duplicate_id_failure_count = sum(
        not value for value in duplicate_flags
    )

    checks = {
        "error_count_within_limit": (
            int(error_count)
            <= int(quality_cfg["max_error_count"])
        ),
        "comparisons_complete": missing_count == 0,
        "mean_overlap_pass": (
            mean_overlap is not None
            and mean_overlap
            >= float(
                quality_cfg["min_mean_overlap_at_k"]
            )
        ),
        "min_overlap_pass": (
            min_overlap is not None
            and min_overlap
            >= float(
                quality_cfg["min_query_overlap_at_k"]
            )
        ),
        "exact_order_pass": (
            all(exact_flags)
            if bool(
                quality_cfg["require_exact_same_order"]
            )
            else True
        ),
        "result_count_match_pass": (
            all(result_count_flags)
            if bool(
                quality_cfg["require_result_count_match"]
            )
            else True
        ),
        "duplicate_ids_pass": all(duplicate_flags),
        "determinism_pass": determinism_failures == 0,
    }

    failed = [
        name for name, value in checks.items() if not value
    ]

    return {
        "ok": len(failed) == 0,
        "checks": checks,
        "failed_checks": failed,
        "error_count": int(error_count),
        "comparison_count": len(overlaps),
        "missing_comparison_count": missing_count,
        "mean_overlap_at_k": mean_overlap,
        "min_overlap_at_k": min_overlap,
        "exact_same_order_count": sum(exact_flags),
        "result_count_mismatch_count": (
            result_count_mismatch_count
        ),
        "duplicate_id_failure_count": (
            duplicate_id_failure_count
        ),
        "determinism_failure_count": determinism_failures,
    }


def _duplicate_values(values: Sequence[str]) -> list[str]:
    counts = Counter(values)
    return sorted(
        value
        for value, count in counts.items()
        if count > 1
    )


def compare_id_lists(
    reference_ids: Sequence[str],
    candidate_ids: Sequence[str],
    *,
    top_k: int,
) -> dict[str, Any]:
    top_k = _require_positive_int(top_k, name="top_k")

    reference = [str(value) for value in reference_ids[:top_k]]
    candidate = [str(value) for value in candidate_ids[:top_k]]

    reference_set = set(reference)
    candidate_set = set(candidate)

    overlap_count = len(reference_set & candidate_set)

    return {
        "top_k": top_k,
        "reference_count": len(reference),
        "candidate_count": len(candidate),
        "overlap_count": overlap_count,
        "overlap_ratio": (
            overlap_count / top_k
            if top_k > 0
            else 0.0
        ),
        "exact_same_order": reference == candidate,
        "same_set": reference_set == candidate_set,
        "duplicate_reference_ids": _duplicate_values(reference),
        "duplicate_candidate_ids": _duplicate_values(candidate),
        "reference_only": [
            value
            for value in reference
            if value not in candidate_set
        ],
        "candidate_only": [
            value
            for value in candidate
            if value not in reference_set
        ],
    }


def process_memory_snapshot(pid: int) -> dict[str, Any]:
    try:
        process = psutil.Process(int(pid))
        memory = process.memory_info()

        return {
            "supported": True,
            "pid": int(pid),
            "rss_bytes": int(memory.rss),
            "vms_bytes": int(memory.vms),
            "memory_percent": float(process.memory_percent()),
            "num_threads": int(process.num_threads()),
        }
    except (psutil.Error, OSError, ValueError) as exc:
        return {
            "supported": False,
            "pid": int(pid),
            "reason": f"{type(exc).__name__}: {exc}",
        }


def system_memory_snapshot() -> dict[str, Any]:
    try:
        memory = psutil.virtual_memory()
        return {
            "supported": True,
            "total_bytes": int(memory.total),
            "available_bytes": int(memory.available),
            "used_bytes": int(memory.used),
            "percent": float(memory.percent),
        }
    except Exception as exc:
        return {
            "supported": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }


_SIZE_UNITS = {
    "b": 1,
    "kb": 1000,
    "kib": 1024,
    "mb": 1000**2,
    "mib": 1024**2,
    "gb": 1000**3,
    "gib": 1024**3,
    "tb": 1000**4,
    "tib": 1024**4,
}


def parse_size_to_bytes(value: str) -> int:
    text = str(value).strip().lower().replace(" ", "")
    if not text:
        raise ValueError("Size value is empty")

    number_text = ""
    unit_text = ""

    for char in text:
        if char.isdigit() or char in ".+-":
            if unit_text:
                raise ValueError(
                    f"Invalid size value: {value!r}"
                )
            number_text += char
        else:
            unit_text += char

    if not number_text or unit_text not in _SIZE_UNITS:
        raise ValueError(f"Unsupported size value: {value!r}")

    number = float(number_text)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"Invalid size value: {value!r}")

    return int(number * _SIZE_UNITS[unit_text])


def _parse_percent(value: Any) -> float | None:
    if value is None:
        return None

    text = str(value).strip().rstrip("%")
    try:
        parsed = float(text)
    except ValueError:
        return None

    return parsed if math.isfinite(parsed) else None


def docker_container_snapshot(
    container_name: str,
) -> dict[str, Any]:
    docker = shutil.which("docker")
    if docker is None:
        return {
            "supported": False,
            "reason": "docker_cli_not_available",
        }

    try:
        completed = subprocess.run(
            [
                docker,
                "stats",
                "--no-stream",
                "--format",
                "{{json .}}",
                str(container_name),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "supported": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }

    if completed.returncode != 0:
        return {
            "supported": False,
            "reason": (
                completed.stderr.strip()
                or f"docker_stats_exit_{completed.returncode}"
            ),
        }

    line = next(
        (
            item.strip()
            for item in completed.stdout.splitlines()
            if item.strip()
        ),
        "",
    )
    if not line:
        return {
            "supported": False,
            "reason": "docker_stats_empty_output",
        }

    try:
        raw = json.loads(line)
    except json.JSONDecodeError as exc:
        return {
            "supported": False,
            "reason": f"invalid_docker_stats_json: {exc}",
            "raw_output": line,
        }

    memory_usage = str(raw.get("MemUsage") or "")
    used_memory_text = memory_usage.split("/", maxsplit=1)[0].strip()

    used_memory_bytes: int | None = None
    if used_memory_text:
        try:
            used_memory_bytes = parse_size_to_bytes(
                used_memory_text
            )
        except ValueError:
            used_memory_bytes = None

    return {
        "supported": True,
        "container_name": str(
            raw.get("Name")
            or raw.get("Container")
            or container_name
        ),
        "container_id": raw.get("ID"),
        "cpu_percent": _parse_percent(raw.get("CPUPerc")),
        "memory_percent": _parse_percent(raw.get("MemPerc")),
        "memory_usage": memory_usage or None,
        "memory_used_bytes": used_memory_bytes,
        "pids": (
            int(raw["PIDs"])
            if str(raw.get("PIDs") or "").isdigit()
            else None
        ),
    }


def gpu_snapshot() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return {
            "supported": False,
            "reason": "nvidia_smi_not_available",
        }

    try:
        completed = subprocess.run(
            [
                executable,
                "--query-gpu="
                "index,name,memory.used,memory.total,"
                "utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "supported": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }

    if completed.returncode != 0:
        return {
            "supported": False,
            "reason": (
                completed.stderr.strip()
                or f"nvidia_smi_exit_{completed.returncode}"
            ),
        }

    gpus: list[dict[str, Any]] = []

    for line in completed.stdout.splitlines():
        text = line.strip()
        if not text:
            continue

        parts = [part.strip() for part in text.split(",")]
        if len(parts) != 5:
            return {
                "supported": False,
                "reason": "unexpected_nvidia_smi_output",
                "raw_output": completed.stdout,
            }

        try:
            gpus.append(
                {
                    "index": int(parts[0]),
                    "name": parts[1],
                    "memory_used_mib": float(parts[2]),
                    "memory_total_mib": float(parts[3]),
                    "utilization_gpu_percent": float(parts[4]),
                }
            )
        except ValueError as exc:
            return {
                "supported": False,
                "reason": f"invalid_nvidia_smi_value: {exc}",
                "raw_output": completed.stdout,
            }

    return {
        "supported": True,
        "gpus": gpus,
    }


def run_threaded_calls(
    callables: Sequence[Callable[[], T]],
    *,
    max_workers: int,
    task_contexts: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    max_workers = _require_positive_int(
        max_workers,
        name="max_workers",
    )

    tasks = list(callables)

    if task_contexts is None:
        contexts = [{} for _ in tasks]
    else:
        contexts = [dict(context) for context in task_contexts]
        if len(contexts) != len(tasks):
            raise ValueError(
                "task_contexts length must match callables length"
            )

    if not tasks:
        return {
            "concurrency": max_workers,
            "task_count": 0,
            "success_count": 0,
            "error_count": 0,
            "wall_time_ms": 0.0,
            "throughput_rps": 0.0,
            "latency": summarize_samples([]),
            "records": [],
        }

    records: list[dict[str, Any] | None] = [
        None for _ in tasks
    ]

    def invoke(
        index: int,
        callback: Callable[[], T],
        context: Mapping[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        started = time.perf_counter()
        try:
            value = callback()
            latency_ms = (
                time.perf_counter() - started
            ) * 1000
            return index, {
                "task_index": index,
                "task_context": dict(context),
                "ok": True,
                "latency_ms": latency_ms,
                "value": value,
                "error": None,
                "error_type": None,
                "error_module": None,
                "error_message": None,
                "error_chain": [],
            }
        except Exception as exc:
            latency_ms = (
                time.perf_counter() - started
            ) * 1000
            return index, {
                "task_index": index,
                "task_context": dict(context),
                "ok": False,
                "latency_ms": latency_ms,
                "value": None,
                **exception_details(exc),
            }

    wall_started = time.perf_counter()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                invoke,
                index,
                callback,
                contexts[index],
            )
            for index, callback in enumerate(tasks)
        ]

        for future in as_completed(futures):
            index, record = future.result()
            records[index] = record

    wall_time_ms = (
        time.perf_counter() - wall_started
    ) * 1000

    completed_records = [
        record
        for record in records
        if record is not None
    ]
    success_records = [
        record
        for record in completed_records
        if record["ok"] is True
    ]
    error_records = [
        record
        for record in completed_records
        if record["ok"] is False
    ]

    throughput_rps = (
        len(completed_records) / (wall_time_ms / 1000)
        if wall_time_ms > 0
        else 0.0
    )

    return {
        "concurrency": max_workers,
        "task_count": len(completed_records),
        "success_count": len(success_records),
        "error_count": len(error_records),
        "wall_time_ms": wall_time_ms,
        "throughput_rps": throughput_rps,
        "latency": summarize_samples(
            [
                float(record["latency_ms"])
                for record in completed_records
            ]
        ),
        "records": completed_records,
    }

