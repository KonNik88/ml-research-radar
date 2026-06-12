"""Run the read-only Qdrant serving-performance benchmark.

The benchmark compares two levels:

1. backend-only:
   FileDenseBackend vs QdrantDenseBackend over pre-encoded query vectors;

2. end-to-end serving:
   public file-dense ``/search`` vs experimental
   ``/experimental/search/qdrant`` over fresh and warm Uvicorn processes.

The command is evaluation-only. It does not:

- create or recreate Qdrant collections;
- upload or mutate vectors;
- change public search defaults;
- promote Qdrant;
- enable fallback.

Run from the project root:

    python -m scripts.evaluation.run_qdrant_serving_performance --preset smoke
"""

from __future__ import annotations

import argparse
import json
from importlib.metadata import PackageNotFoundError, version
import math
import os
import platform
import socket
import subprocess
import sys
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

import httpx
import numpy as np
import psutil
from sentence_transformers import SentenceTransformer

from radar_core.retrieval.dense_backend import (
    DenseSearchRequest,
    FileDenseBackend,
    QdrantDenseBackend,
    QdrantSearchProfile,
)
from radar_core.retrieval.qdrant_store import QdrantRetrievalStore
from scripts.evaluation.qdrant_serving_performance import (
    api_result_ids,
    api_timing_ms,
    backend_candidate_ids,
    compact_result_record,
    compare_id_lists,
    derive_api_timings,
    docker_container_snapshot,
    dump_json,
    dump_text,
    enabled_queries,
    gpu_snapshot,
    load_ids,
    load_json,
    load_yaml,
    normalize_path,
    process_memory_snapshot,
    resolve_preset,
    resolve_query_text,
    result_ids_digest,
    run_threaded_calls,
    select_queries,
    summarize_quality_sections,
    summarize_samples,
    system_memory_snapshot,
    utc_iso,
    utc_ts,
    validate_benchmark_config,
)


SCHEMA_VERSION = "qdrant_serving_performance_v1"
DEFAULT_CONFIG_PATH = Path(
    "configs/qdrant_serving_performance_v1.yaml"
)
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/evaluation")


@dataclass(frozen=True)
class QueryWorkload:
    query_id: str
    query_text: str
    query_vector: np.ndarray


@dataclass
class ApiProcess:
    process: subprocess.Popen[Any]
    log_handle: Any
    log_path: Path
    base_url: str
    startup_ms: float


def _round_ms(value: float) -> float:
    return round(float(value), 3)


def _safe_float(value: Any) -> float | None:
    if (
        not isinstance(value, (int, float, np.integer, np.floating))
        or isinstance(value, bool)
    ):
        return None

    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _python_environment() -> dict[str, Any]:
    package_distributions = {
        "httpx": "httpx",
        "numpy": "numpy",
        "psutil": "psutil",
        "qdrant_client": "qdrant-client",
        "sentence_transformers": "sentence-transformers",
        "torch": "torch",
        "uvicorn": "uvicorn",
    }
    packages: dict[str, str | None] = {}

    for module_name, distribution_name in package_distributions.items():
        try:
            packages[module_name] = version(distribution_name)
        except PackageNotFoundError:
            packages[module_name] = None

    try:
        import torch

        cuda_available = bool(torch.cuda.is_available())
        cuda_device_name = (
            torch.cuda.get_device_name(0)
            if cuda_available
            else None
        )
        cuda_version = torch.version.cuda
    except Exception:
        cuda_available = False
        cuda_device_name = None
        cuda_version = None

    return {
        "python": sys.version,
        "executable": normalize_path(sys.executable),
        "platform": platform.platform(),
        "processor": platform.processor() or None,
        "machine": platform.machine() or None,
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "packages": packages,
        "cuda_available": cuda_available,
        "cuda_device_name": cuda_device_name,
        "cuda_version": cuda_version,
    }


def _collection_summary(
    store: QdrantRetrievalStore,
) -> dict[str, Any]:
    info = store.get_collection_info()

    return {
        "collection_name": store.collection_name,
        "transport": store.transport,
        "rest_port": store.port,
        "grpc_port": store.grpc_port,
        "prefer_grpc": store.prefer_grpc,
        "status": info.get("status"),
        "optimizer_status": info.get("optimizer_status"),
        "points_count": info.get("points_count"),
        "indexed_vectors_count": info.get("indexed_vectors_count"),
        "vector_size": info.get("vector_size"),
        "distance": info.get("distance"),
    }


class LightweightResourceSampler:
    """Sample cheap process/system metrics during a workload.

    Docker CLI and nvidia-smi are deliberately sampled only before and after
    the workload because invoking them repeatedly can materially perturb short
    latency measurements.
    """

    def __init__(
        self,
        *,
        pid: int,
        interval_sec: float,
        collect_process: bool,
        collect_system: bool,
        collect_docker: bool,
        collect_gpu: bool,
        qdrant_container_name: str,
    ) -> None:
        self.pid = int(pid)
        self.interval_sec = float(interval_sec)
        self.collect_process = bool(collect_process)
        self.collect_system = bool(collect_system)
        self.collect_docker = bool(collect_docker)
        self.collect_gpu = bool(collect_gpu)
        self.qdrant_container_name = str(qdrant_container_name)

        self.process_samples: list[dict[str, Any]] = []
        self.system_samples: list[dict[str, Any]] = []

        self.docker_before: dict[str, Any] | None = None
        self.docker_after: dict[str, Any] | None = None
        self.gpu_before: dict[str, Any] | None = None
        self.gpu_after: dict[str, Any] | None = None

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._stopped = False
        self._summary_cache: dict[str, Any] | None = None

    def _sample_cheap(self) -> None:
        if self.collect_process:
            self.process_samples.append(
                process_memory_snapshot(self.pid)
            )

        if self.collect_system:
            self.system_samples.append(
                system_memory_snapshot()
            )

    def _loop(self) -> None:
        while not self._stop_event.wait(self.interval_sec):
            self._sample_cheap()

    def start(self) -> None:
        if self.collect_docker:
            self.docker_before = docker_container_snapshot(
                self.qdrant_container_name
            )

        if self.collect_gpu:
            self.gpu_before = gpu_snapshot()

        self._sample_cheap()

        self._thread = threading.Thread(
            target=self._loop,
            name="qdrant-performance-resource-sampler",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> dict[str, Any]:
        if self._stopped and self._summary_cache is not None:
            return self._summary_cache

        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(
                timeout=max(1.0, self.interval_sec * 4)
            )

        self._sample_cheap()

        if self.collect_docker:
            self.docker_after = docker_container_snapshot(
                self.qdrant_container_name
            )

        if self.collect_gpu:
            self.gpu_after = gpu_snapshot()

        self._stopped = True
        self._summary_cache = self.summary()
        return self._summary_cache

    @staticmethod
    def _supported_values(
        rows: Sequence[Mapping[str, Any]],
        field: str,
    ) -> list[float]:
        values: list[float] = []

        for row in rows:
            if row.get("supported") is not True:
                continue
            parsed = _safe_float(row.get(field))
            if parsed is not None:
                values.append(parsed)

        return values

    def summary(self) -> dict[str, Any]:
        rss_values = self._supported_values(
            self.process_samples,
            "rss_bytes",
        )
        vms_values = self._supported_values(
            self.process_samples,
            "vms_bytes",
        )
        process_percent_values = self._supported_values(
            self.process_samples,
            "memory_percent",
        )
        system_percent_values = self._supported_values(
            self.system_samples,
            "percent",
        )
        available_values = self._supported_values(
            self.system_samples,
            "available_bytes",
        )

        return {
            "process": {
                "supported": bool(rss_values),
                "sample_count": len(self.process_samples),
                "rss_bytes_first": (
                    int(rss_values[0])
                    if rss_values
                    else None
                ),
                "rss_bytes_last": (
                    int(rss_values[-1])
                    if rss_values
                    else None
                ),
                "rss_bytes_peak": (
                    int(max(rss_values))
                    if rss_values
                    else None
                ),
                "vms_bytes_peak": (
                    int(max(vms_values))
                    if vms_values
                    else None
                ),
                "memory_percent_peak": (
                    max(process_percent_values)
                    if process_percent_values
                    else None
                ),
            },
            "system": {
                "supported": bool(system_percent_values),
                "sample_count": len(self.system_samples),
                "memory_percent_peak": (
                    max(system_percent_values)
                    if system_percent_values
                    else None
                ),
                "available_bytes_min": (
                    int(min(available_values))
                    if available_values
                    else None
                ),
            },
            "docker": {
                "before": self.docker_before,
                "after": self.docker_after,
            },
            "gpu": {
                "before": self.gpu_before,
                "after": self.gpu_after,
            },
            "sampling_policy": {
                "process_and_system": "periodic",
                "docker_and_gpu": "before_after_only",
                "interval_sec": self.interval_sec,
            },
        }


@contextmanager
def sampled_resources(
    *,
    pid: int,
    resources_cfg: Mapping[str, Any],
) -> Iterator[LightweightResourceSampler]:
    sampler = LightweightResourceSampler(
        pid=pid,
        interval_sec=float(
            resources_cfg.get("sample_interval_sec", 0.25)
        ),
        collect_process=bool(
            resources_cfg.get("collect_process_memory", True)
        ),
        collect_system=bool(
            resources_cfg.get("collect_system_memory", True)
        ),
        collect_docker=bool(
            resources_cfg.get("collect_docker_stats", True)
        ),
        collect_gpu=bool(
            resources_cfg.get("collect_gpu_stats", True)
        ),
        qdrant_container_name=str(
            resources_cfg.get(
                "qdrant_container_name",
                "ml_radar_qdrant",
            )
        ),
    )

    sampler.start()
    try:
        yield sampler
    finally:
        sampler.stop()


def _encode_query(
    model: SentenceTransformer,
    query_text: str,
) -> np.ndarray:
    vector = model.encode(
        [query_text],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )[0]

    array = np.asarray(vector, dtype=np.float32)

    if array.ndim != 1:
        raise ValueError(
            f"Encoded query must be 1D, got shape={array.shape}"
        )

    if not np.all(np.isfinite(array)):
        raise ValueError("Encoded query contains non-finite values")

    return array


def _build_query_workload(
    *,
    model: SentenceTransformer,
    query_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[QueryWorkload], dict[str, Any]]:
    workloads: list[QueryWorkload] = []
    samples: list[dict[str, Any]] = []

    for index, row in enumerate(query_rows, start=1):
        query_id = str(row.get("query_id") or f"query_{index}")
        query_text = resolve_query_text(row)

        started = time.perf_counter()
        vector = _encode_query(model, query_text)
        latency_ms = _round_ms(
            (time.perf_counter() - started) * 1000
        )

        workloads.append(
            QueryWorkload(
                query_id=query_id,
                query_text=query_text,
                query_vector=vector,
            )
        )
        samples.append(
            {
                "query_id": query_id,
                "latency_ms": latency_ms,
                "dimension": int(vector.shape[0]),
                "norm": float(np.linalg.norm(vector)),
                "all_finite": bool(
                    np.all(np.isfinite(vector))
                ),
            }
        )

    return workloads, {
        "workload_vectorization": {
            "latency": summarize_samples(
                [row["latency_ms"] for row in samples]
            ),
            "samples": samples,
        }
    }


def _run_encoding_benchmark(
    *,
    model: SentenceTransformer,
    query_rows: Sequence[Mapping[str, Any]],
    preset: Mapping[str, Any],
) -> dict[str, Any]:
    config = preset["encoding"]
    warmup_rounds = int(config["warmup_rounds"])
    measured_rounds = int(config["measured_rounds"])

    first_query_text = resolve_query_text(query_rows[0])

    started = time.perf_counter()
    first_vector = _encode_query(model, first_query_text)
    first_encode_ms = _round_ms(
        (time.perf_counter() - started) * 1000
    )

    for _ in range(warmup_rounds):
        for row in query_rows:
            _encode_query(model, resolve_query_text(row))

    samples: list[dict[str, Any]] = []

    for round_index in range(measured_rounds):
        for query_index, row in enumerate(query_rows, start=1):
            query_id = str(
                row.get("query_id")
                or f"query_{query_index}"
            )
            query_text = resolve_query_text(row)

            started = time.perf_counter()
            vector = _encode_query(model, query_text)
            latency_ms = _round_ms(
                (time.perf_counter() - started) * 1000
            )

            samples.append(
                {
                    "round": round_index + 1,
                    "query_id": query_id,
                    "latency_ms": latency_ms,
                    "dimension": int(vector.shape[0]),
                    "norm": float(np.linalg.norm(vector)),
                    "all_finite": bool(
                        np.all(np.isfinite(vector))
                    ),
                }
            )

    return {
        "first_encode_ms": first_encode_ms,
        "first_vector_dimension": int(first_vector.shape[0]),
        "first_vector_norm": float(
            np.linalg.norm(first_vector)
        ),
        "warmup_rounds": warmup_rounds,
        "measured_rounds": measured_rounds,
        "latency": summarize_samples(
            [row["latency_ms"] for row in samples]
        ),
        "samples": samples,
    }


def _backend_call(
    *,
    backend: Any,
    workload: QueryWorkload,
    top_k: int,
) -> dict[str, Any]:
    request = DenseSearchRequest(
        query_vector=workload.query_vector,
        top_k=int(top_k),
    )

    started = time.perf_counter()
    result = backend.search(request)
    wall_latency_ms = _round_ms(
        (time.perf_counter() - started) * 1000
    )

    reported_backend_search_ms = _safe_float(
        result.timing_ms.get("backend_search_ms")
    )

    return {
        "query_id": workload.query_id,
        "top_k": int(top_k),
        "wall_latency_ms": wall_latency_ms,
        "reported_backend_search_ms": (
            _round_ms(reported_backend_search_ms)
            if reported_backend_search_ms is not None
            else None
        ),
        "result_count": len(result.candidates),
        "canonical_ids": backend_candidate_ids(result),
        "backend_name": result.backend.backend_name,
        "backend_implementation": (
            result.backend.implementation
        ),
        "backend_ready": bool(result.backend.ready),
        "backend_build_id": result.backend.build_id,
    }


def _warm_backend(
    *,
    backend: Any,
    workloads: Sequence[QueryWorkload],
    top_k_values: Sequence[int],
    rounds: int,
) -> None:
    for _ in range(rounds):
        for top_k in top_k_values:
            for workload in workloads:
                _backend_call(
                    backend=backend,
                    workload=workload,
                    top_k=top_k,
                )


def _run_backend_sequential(
    *,
    backend_name: str,
    backend: Any,
    workloads: Sequence[QueryWorkload],
    top_k_values: Sequence[int],
    measured_rounds: int,
    resources_cfg: Mapping[str, Any],
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    with sampled_resources(
        pid=os.getpid(),
        resources_cfg=resources_cfg,
    ) as sampler:
        wall_started = time.perf_counter()

        for round_index in range(measured_rounds):
            for top_k in top_k_values:
                for workload in workloads:
                    try:
                        row = _backend_call(
                            backend=backend,
                            workload=workload,
                            top_k=top_k,
                        )
                        row["round"] = round_index + 1
                        records.append(row)
                    except Exception as exc:
                        errors.append(
                            {
                                "backend": backend_name,
                                "round": round_index + 1,
                                "query_id": workload.query_id,
                                "top_k": int(top_k),
                                "error": _error_text(exc),
                            }
                        )

        wall_time_ms = _round_ms(
            (time.perf_counter() - wall_started) * 1000
        )
        resource_summary = sampler.stop()

    latency_values = [
        row["wall_latency_ms"] for row in records
    ]
    throughput_rps = (
        len(records) / (wall_time_ms / 1000)
        if wall_time_ms > 0
        else 0.0
    )

    return {
        "backend": backend_name,
        "measured_rounds": measured_rounds,
        "request_count": (
            measured_rounds
            * len(top_k_values)
            * len(workloads)
        ),
        "success_count": len(records),
        "error_count": len(errors),
        "wall_time_ms": wall_time_ms,
        "throughput_rps": throughput_rps,
        "latency": summarize_samples(latency_values),
        "reported_backend_search_latency": (
            summarize_samples(
                [
                    row["reported_backend_search_ms"]
                    for row in records
                    if row["reported_backend_search_ms"]
                    is not None
                ]
            )
        ),
        "resources": resource_summary,
        "records": records,
        "errors": errors,
    }


def _run_backend_concurrent(
    *,
    backend_name: str,
    backend: Any,
    workloads: Sequence[QueryWorkload],
    top_k_values: Sequence[int],
    measured_rounds: int,
    concurrency_levels: Sequence[int],
    resources_cfg: Mapping[str, Any],
) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []

    for concurrency in concurrency_levels:
        callbacks: list[Callable[[], dict[str, Any]]] = []
        task_contexts: list[dict[str, Any]] = []

        for round_index in range(measured_rounds):
            for top_k in top_k_values:
                for workload in workloads:
                    def callback(
                        *,
                        current_round: int = round_index + 1,
                        current_top_k: int = int(top_k),
                        current_workload: QueryWorkload = workload,
                    ) -> dict[str, Any]:
                        row = _backend_call(
                            backend=backend,
                            workload=current_workload,
                            top_k=current_top_k,
                        )
                        row["round"] = current_round
                        return row

                    callbacks.append(callback)
                    task_contexts.append(
                        {
                            "backend": backend_name,
                            "concurrency": int(concurrency),
                            "round": round_index + 1,
                            "query_id": workload.query_id,
                            "top_k": int(top_k),
                        }
                    )

        with sampled_resources(
            pid=os.getpid(),
            resources_cfg=resources_cfg,
        ) as sampler:
            threaded = run_threaded_calls(
                callbacks,
                max_workers=int(concurrency),
                task_contexts=task_contexts,
            )
            resource_summary = sampler.stop()

        records = [
            dict(row["value"])
            for row in threaded["records"]
            if row["ok"] is True
            and isinstance(row.get("value"), Mapping)
        ]
        errors = [
            {
                **dict(row.get("task_context") or {}),
                "task_index": row.get("task_index"),
                "latency_ms": row["latency_ms"],
                "error": row["error"],
                "error_type": row.get("error_type"),
                "error_module": row.get("error_module"),
                "error_message": row.get("error_message"),
                "error_chain": row.get("error_chain") or [],
            }
            for row in threaded["records"]
            if row["ok"] is False
        ]

        scenarios.append(
            {
                "backend": backend_name,
                "concurrency": int(concurrency),
                "task_count": threaded["task_count"],
                "success_count": threaded["success_count"],
                "error_count": threaded["error_count"],
                "wall_time_ms": _round_ms(
                    threaded["wall_time_ms"]
                ),
                "throughput_rps": float(
                    threaded["throughput_rps"]
                ),
                "latency": summarize_samples(
                    [
                        row["wall_latency_ms"]
                        for row in records
                    ]
                ),
                "reported_backend_search_latency": (
                    summarize_samples(
                        [
                            row["reported_backend_search_ms"]
                            for row in records
                            if row[
                                "reported_backend_search_ms"
                            ]
                            is not None
                        ]
                    )
                ),
                "resources": resource_summary,
                "records": records,
                "errors": errors,
            }
        )

    return scenarios


def _first_success_by_query_top_k(
    records: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, int], Mapping[str, Any]]:
    selected: dict[tuple[str, int], Mapping[str, Any]] = {}

    for row in records:
        key = (
            str(row.get("query_id")),
            int(row.get("top_k")),
        )
        selected.setdefault(key, row)

    return selected


def _determinism_summary(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    groups: dict[
        tuple[str, int],
        list[list[str]],
    ] = defaultdict(list)

    for row in records:
        groups[
            (
                str(row.get("query_id")),
                int(row.get("top_k")),
            )
        ].append(
            [str(value) for value in row.get("canonical_ids", [])]
        )

    failures: list[dict[str, Any]] = []

    for (query_id, top_k), runs in sorted(groups.items()):
        if not runs:
            continue

        reference = runs[0]
        unstable = [
            index + 1
            for index, current in enumerate(runs)
            if current != reference
        ]

        if unstable:
            failures.append(
                {
                    "query_id": query_id,
                    "top_k": top_k,
                    "run_count": len(runs),
                    "unstable_run_numbers": unstable,
                }
            )

    return {
        "group_count": len(groups),
        "failure_count": len(failures),
        "stable": len(failures) == 0,
        "failures": failures,
    }


def _compare_backend_records(
    *,
    file_records: Sequence[Mapping[str, Any]],
    qdrant_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    file_by_key = _first_success_by_query_top_k(file_records)
    qdrant_by_key = _first_success_by_query_top_k(qdrant_records)

    keys = sorted(set(file_by_key) | set(qdrant_by_key))
    comparisons: list[dict[str, Any]] = []

    for query_id, top_k in keys:
        file_row = file_by_key.get((query_id, top_k))
        qdrant_row = qdrant_by_key.get((query_id, top_k))

        if file_row is None or qdrant_row is None:
            comparisons.append(
                {
                    "query_id": query_id,
                    "top_k": top_k,
                    "comparison_available": False,
                    "missing_file": file_row is None,
                    "missing_qdrant": qdrant_row is None,
                }
            )
            continue

        reference_ids = [
            str(value)
            for value in file_row.get("canonical_ids", [])
        ]
        candidate_ids = [
            str(value)
            for value in qdrant_row.get("canonical_ids", [])
        ]
        comparison = compare_id_lists(
            reference_ids,
            candidate_ids,
            top_k=top_k,
        )

        comparisons.append(
            {
                "query_id": query_id,
                "top_k": top_k,
                "comparison_available": True,
                "reference_ids": reference_ids[:top_k],
                "candidate_ids": candidate_ids[:top_k],
                "reference_ids_digest": result_ids_digest(
                    reference_ids[:top_k]
                ),
                "candidate_ids_digest": result_ids_digest(
                    candidate_ids[:top_k]
                ),
                **comparison,
            }
        )

    available = [
        row
        for row in comparisons
        if row.get("comparison_available") is True
    ]
    overlaps = [
        float(row["overlap_ratio"])
        for row in available
    ]
    exact_count = sum(
        bool(row["exact_same_order"])
        for row in available
    )

    return {
        "comparison_count": len(available),
        "missing_comparison_count": (
            len(comparisons) - len(available)
        ),
        "mean_overlap_at_k": (
            float(np.mean(overlaps))
            if overlaps
            else None
        ),
        "min_overlap_at_k": (
            min(overlaps)
            if overlaps
            else None
        ),
        "exact_same_order_count": exact_count,
        "exact_same_order_all": (
            bool(available)
            and exact_count == len(available)
        ),
        "comparisons": comparisons,
        "file_determinism": _determinism_summary(
            file_records
        ),
        "qdrant_determinism": _determinism_summary(
            qdrant_records
        ),
    }


def _port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection(
            (host, int(port)),
            timeout=0.5,
        ):
            return True
    except OSError:
        return False


def _api_environment(
    *,
    qdrant_cfg: Mapping[str, Any],
) -> dict[str, str]:
    profile_cfg = qdrant_cfg["profile"]

    env = os.environ.copy()
    env.update(
        {
            "ML_RADAR_SEARCH_BACKEND": "file",
            "ML_RADAR_ENABLE_DEBUG_META": "true",
            "ML_RADAR_QDRANT_HOST": str(
                qdrant_cfg["host"]
            ),
            "ML_RADAR_QDRANT_PORT": str(
                qdrant_cfg["port"]
            ),
            "ML_RADAR_QDRANT_COLLECTION_NAME": str(
                qdrant_cfg["collection_name"]
            ),
            "ML_RADAR_QDRANT_TIMEOUT_SEC": str(
                qdrant_cfg["timeout_sec"]
            ),
            "ML_RADAR_QDRANT_CHECK_COMPATIBILITY": (
                "true"
                if bool(
                    qdrant_cfg.get(
                        "check_compatibility",
                        False,
                    )
                )
                else "false"
            ),
            "ML_RADAR_QDRANT_SEARCH_PROFILE_NAME": str(
                profile_cfg["name"]
            ),
            "ML_RADAR_QDRANT_SEARCH_EXACT": (
                "true"
                if bool(profile_cfg.get("exact", False))
                else "false"
            ),
        }
    )

    hnsw_ef = profile_cfg.get("hnsw_ef")
    if hnsw_ef is None:
        env.pop(
            "ML_RADAR_QDRANT_SEARCH_HNSW_EF",
            None,
        )
    else:
        env["ML_RADAR_QDRANT_SEARCH_HNSW_EF"] = str(
            hnsw_ef
        )

    return env


def _wait_for_api(
    *,
    process: subprocess.Popen[Any],
    base_url: str,
    startup_timeout_sec: float,
    poll_interval_sec: float,
) -> float:
    started = time.perf_counter()
    last_error: str | None = None

    while True:
        if process.poll() is not None:
            raise RuntimeError(
                "Uvicorn exited before becoming ready: "
                f"returncode={process.returncode}"
            )

        try:
            response = httpx.get(
                f"{base_url}/health",
                timeout=5.0,
            )
            if response.status_code == 200:
                payload = response.json()
                if payload.get("ready") is True:
                    return _round_ms(
                        (time.perf_counter() - started) * 1000
                    )
                last_error = (
                    "health response ready is not true: "
                    f"{payload!r}"
                )
            else:
                last_error = (
                    f"health status={response.status_code}"
                )
        except Exception as exc:
            last_error = _error_text(exc)

        elapsed = time.perf_counter() - started
        if elapsed >= startup_timeout_sec:
            raise TimeoutError(
                "Timed out waiting for API startup: "
                f"base_url={base_url}, "
                f"last_error={last_error}"
            )

        time.sleep(poll_interval_sec)


def _stop_api_process(api_process: ApiProcess) -> None:
    process = api_process.process

    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)

    api_process.log_handle.close()


@contextmanager
def running_api_process(
    *,
    api_cfg: Mapping[str, Any],
    qdrant_cfg: Mapping[str, Any],
    output_dir: Path,
    run_ts: str,
    label: str,
) -> Iterator[ApiProcess]:
    host = str(api_cfg["host"])
    port = int(api_cfg["port"])
    base_url = f"http://{host}:{port}"

    if _port_is_open(host, port):
        raise RuntimeError(
            f"Benchmark API port is already in use: {base_url}"
        )

    uvicorn_cfg = api_cfg.get("uvicorn") or {}
    app_path = str(
        uvicorn_cfg.get("app", "services.api.app:app")
    )
    workers = int(uvicorn_cfg.get("workers", 1))
    log_level = str(
        uvicorn_cfg.get("log_level", "warning")
    )

    log_path = (
        output_dir
        / "logs"
        / f"qdrant_serving_performance_{run_ts}_{label}.log"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open(
        "w",
        encoding="utf-8",
        errors="replace",
    )

    command = [
        sys.executable,
        "-m",
        "uvicorn",
        app_path,
        "--host",
        host,
        "--port",
        str(port),
        "--workers",
        str(workers),
        "--log-level",
        log_level,
    ]

    process = subprocess.Popen(
        command,
        cwd=str(Path.cwd()),
        env=_api_environment(qdrant_cfg=qdrant_cfg),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        startup_ms = _wait_for_api(
            process=process,
            base_url=base_url,
            startup_timeout_sec=float(
                api_cfg["startup_timeout_sec"]
            ),
            poll_interval_sec=float(
                api_cfg["startup_poll_interval_sec"]
            ),
        )

        api_process = ApiProcess(
            process=process,
            log_handle=log_handle,
            log_path=log_path,
            base_url=base_url,
            startup_ms=startup_ms,
        )

        try:
            yield api_process
        finally:
            _stop_api_process(api_process)

    except Exception:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)

        log_handle.close()
        raise


def _api_request(
    *,
    client: httpx.Client,
    base_url: str,
    target_name: str,
    target_cfg: Mapping[str, Any],
    query_id: str,
    query_text: str,
    top_k: int,
) -> dict[str, Any]:
    params = dict(target_cfg.get("params") or {})
    params.update(
        {
            "query": query_text,
            "top_k": int(top_k),
        }
    )

    path = str(target_cfg["path"])

    started = time.perf_counter()
    response = client.get(
        f"{base_url}{path}",
        params=params,
    )
    client_latency_ms = _round_ms(
        (time.perf_counter() - started) * 1000
    )

    content_type = response.headers.get(
        "content-type",
        "",
    )
    payload: dict[str, Any] | None = None

    if content_type.startswith("application/json"):
        raw = response.json()
        if isinstance(raw, dict):
            payload = raw

    if response.status_code != 200:
        raise RuntimeError(
            f"{target_name} returned HTTP "
            f"{response.status_code}: {payload!r}"
        )

    if payload is None:
        raise RuntimeError(
            f"{target_name} returned non-object JSON"
        )

    ids = api_result_ids(payload)
    timings = api_timing_ms(payload)
    derived_timings = derive_api_timings(
        client_latency_ms=client_latency_ms,
        server_timing_ms=timings,
    )

    return {
        "target": target_name,
        "query_id": query_id,
        "top_k": int(top_k),
        "status_code": response.status_code,
        "client_latency_ms": client_latency_ms,
        "server_timing_ms": timings,
        "derived_timing_ms": {
            key: (
                _round_ms(value)
                if value is not None
                else None
            )
            for key, value in derived_timings.items()
        },
        "result_count": len(ids),
        "canonical_ids": ids,
        "mode": payload.get("mode"),
        "build_id": payload.get("build_id"),
    }


def _warm_api_target(
    *,
    client: httpx.Client,
    api_process: ApiProcess,
    target_name: str,
    target_cfg: Mapping[str, Any],
    query_rows: Sequence[Mapping[str, Any]],
    top_k_values: Sequence[int],
    warmup_rounds: int,
) -> None:
    for _ in range(warmup_rounds):
        for top_k in top_k_values:
            for index, row in enumerate(
                query_rows,
                start=1,
            ):
                _api_request(
                    client=client,
                    base_url=api_process.base_url,
                    target_name=target_name,
                    target_cfg=target_cfg,
                    query_id=str(
                        row.get("query_id")
                        or f"query_{index}"
                    ),
                    query_text=resolve_query_text(row),
                    top_k=int(top_k),
                )


def _run_api_sequential(
    *,
    client: httpx.Client,
    api_process: ApiProcess,
    target_name: str,
    target_cfg: Mapping[str, Any],
    query_rows: Sequence[Mapping[str, Any]],
    top_k_values: Sequence[int],
    measured_rounds: int,
    resources_cfg: Mapping[str, Any],
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    with sampled_resources(
        pid=api_process.process.pid,
        resources_cfg=resources_cfg,
    ) as sampler:
        wall_started = time.perf_counter()

        for round_index in range(measured_rounds):
            for top_k in top_k_values:
                for query_index, row in enumerate(
                    query_rows,
                    start=1,
                ):
                    query_id = str(
                        row.get("query_id")
                        or f"query_{query_index}"
                    )
                    query_text = resolve_query_text(row)

                    try:
                        result = _api_request(
                            client=client,
                            base_url=api_process.base_url,
                            target_name=target_name,
                            target_cfg=target_cfg,
                            query_id=query_id,
                            query_text=query_text,
                            top_k=int(top_k),
                        )
                        result["round"] = round_index + 1
                        records.append(result)
                    except Exception as exc:
                        errors.append(
                            {
                                "target": target_name,
                                "round": round_index + 1,
                                "query_id": query_id,
                                "top_k": int(top_k),
                                "error": _error_text(exc),
                            }
                        )

        wall_time_ms = _round_ms(
            (time.perf_counter() - wall_started) * 1000
        )
        resource_summary = sampler.stop()

    throughput_rps = (
        len(records) / (wall_time_ms / 1000)
        if wall_time_ms > 0
        else 0.0
    )

    stage_values: dict[str, list[float]] = defaultdict(list)
    derived_values: dict[str, list[float]] = defaultdict(list)
    for row in records:
        for key, value in row["server_timing_ms"].items():
            parsed = _safe_float(value)
            if parsed is not None:
                stage_values[key].append(parsed)
        for key, value in row.get(
            "derived_timing_ms", {}
        ).items():
            parsed = _safe_float(value)
            if parsed is not None:
                derived_values[key].append(parsed)

    return {
        "target": target_name,
        "measured_rounds": measured_rounds,
        "request_count": (
            measured_rounds
            * len(top_k_values)
            * len(query_rows)
        ),
        "success_count": len(records),
        "error_count": len(errors),
        "wall_time_ms": wall_time_ms,
        "throughput_rps": throughput_rps,
        "client_latency": summarize_samples(
            [row["client_latency_ms"] for row in records]
        ),
        "server_stage_latency": {
            key: summarize_samples(values)
            for key, values in sorted(stage_values.items())
        },
        "derived_timing_latency": {
            key: summarize_samples(values)
            for key, values in sorted(derived_values.items())
        },
        "resources": resource_summary,
        "records": records,
        "errors": errors,
    }


def _run_api_concurrent(
    *,
    client: httpx.Client,
    api_process: ApiProcess,
    target_name: str,
    target_cfg: Mapping[str, Any],
    query_rows: Sequence[Mapping[str, Any]],
    top_k_values: Sequence[int],
    measured_rounds: int,
    concurrency_levels: Sequence[int],
    resources_cfg: Mapping[str, Any],
) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []

    for concurrency in concurrency_levels:
        callbacks: list[Callable[[], dict[str, Any]]] = []
        task_contexts: list[dict[str, Any]] = []

        for round_index in range(measured_rounds):
            for top_k in top_k_values:
                for query_index, row in enumerate(
                    query_rows,
                    start=1,
                ):
                    query_id = str(
                        row.get("query_id")
                        or f"query_{query_index}"
                    )
                    query_text = resolve_query_text(row)

                    def callback(
                        *,
                        current_round: int = round_index + 1,
                        current_top_k: int = int(top_k),
                        current_query_id: str = query_id,
                        current_query_text: str = query_text,
                    ) -> dict[str, Any]:
                        result = _api_request(
                            client=client,
                            base_url=api_process.base_url,
                            target_name=target_name,
                            target_cfg=target_cfg,
                            query_id=current_query_id,
                            query_text=current_query_text,
                            top_k=current_top_k,
                        )
                        result["round"] = current_round
                        return result

                    callbacks.append(callback)
                    task_contexts.append(
                        {
                            "target": target_name,
                            "concurrency": int(concurrency),
                            "round": round_index + 1,
                            "query_id": query_id,
                            "top_k": int(top_k),
                        }
                    )

        with sampled_resources(
            pid=api_process.process.pid,
            resources_cfg=resources_cfg,
        ) as sampler:
            threaded = run_threaded_calls(
                callbacks,
                max_workers=int(concurrency),
                task_contexts=task_contexts,
            )
            resource_summary = sampler.stop()

        records = [
            dict(row["value"])
            for row in threaded["records"]
            if row["ok"] is True
            and isinstance(row.get("value"), Mapping)
        ]
        errors = [
            {
                **dict(row.get("task_context") or {}),
                "task_index": row.get("task_index"),
                "latency_ms": row["latency_ms"],
                "error": row["error"],
                "error_type": row.get("error_type"),
                "error_module": row.get("error_module"),
                "error_message": row.get("error_message"),
                "error_chain": row.get("error_chain") or [],
            }
            for row in threaded["records"]
            if row["ok"] is False
        ]

        stage_values: dict[str, list[float]] = defaultdict(list)
        derived_values: dict[str, list[float]] = defaultdict(list)
        for row in records:
            for key, value in row[
                "server_timing_ms"
            ].items():
                parsed = _safe_float(value)
                if parsed is not None:
                    stage_values[key].append(parsed)
            for key, value in row.get(
                "derived_timing_ms", {}
            ).items():
                parsed = _safe_float(value)
                if parsed is not None:
                    derived_values[key].append(parsed)

        scenarios.append(
            {
                "target": target_name,
                "concurrency": int(concurrency),
                "task_count": threaded["task_count"],
                "success_count": threaded["success_count"],
                "error_count": threaded["error_count"],
                "wall_time_ms": _round_ms(
                    threaded["wall_time_ms"]
                ),
                "throughput_rps": float(
                    threaded["throughput_rps"]
                ),
                "client_latency": summarize_samples(
                    [
                        row["client_latency_ms"]
                        for row in records
                    ]
                ),
                "server_stage_latency": {
                    key: summarize_samples(values)
                    for key, values in sorted(
                        stage_values.items()
                    )
                },
                "derived_timing_latency": {
                    key: summarize_samples(values)
                    for key, values in sorted(
                        derived_values.items()
                    )
                },
                "resources": resource_summary,
                "records": records,
                "errors": errors,
            }
        )

    return scenarios


def _run_fresh_process_target(
    *,
    api_cfg: Mapping[str, Any],
    qdrant_cfg: Mapping[str, Any],
    resources_cfg: Mapping[str, Any],
    output_dir: Path,
    run_ts: str,
    target_name: str,
    target_cfg: Mapping[str, Any],
    query_row: Mapping[str, Any],
    top_k: int,
) -> dict[str, Any]:
    with running_api_process(
        api_cfg=api_cfg,
        qdrant_cfg=qdrant_cfg,
        output_dir=output_dir,
        run_ts=run_ts,
        label=f"fresh_{target_name}",
    ) as api_process:
        timeout = float(api_cfg["request_timeout_sec"])

        with httpx.Client(timeout=timeout) as client:
            with sampled_resources(
                pid=api_process.process.pid,
                resources_cfg=resources_cfg,
            ) as sampler:
                result = _api_request(
                    client=client,
                    base_url=api_process.base_url,
                    target_name=target_name,
                    target_cfg=target_cfg,
                    query_id=str(
                        query_row.get("query_id")
                        or "fresh_query"
                    ),
                    query_text=resolve_query_text(query_row),
                    top_k=int(top_k),
                )
                resources = sampler.stop()

        return {
            "target": target_name,
            "startup_ms": api_process.startup_ms,
            "first_request": result,
            "resources": resources,
            "log_path": normalize_path(
                api_process.log_path
            ),
        }


def _compare_api_records(
    *,
    file_records: Sequence[Mapping[str, Any]],
    qdrant_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return _compare_backend_records(
        file_records=file_records,
        qdrant_records=qdrant_records,
    )


def _quality_verdict(
    *,
    comparison_sections: Mapping[str, Mapping[str, Any]],
    quality_cfg: Mapping[str, Any],
    error_count: int,
) -> dict[str, Any]:
    return summarize_quality_sections(
        comparison_sections=comparison_sections,
        quality_cfg=quality_cfg,
        error_count=error_count,
    )


def _compact_repeated_records(
    *,
    backend_section: Mapping[str, Any],
    api_section: Mapping[str, Any],
) -> None:
    if backend_section.get("skipped") is not True:
        sequential = backend_section.get("sequential", {})
        for backend_name in ("file", "qdrant"):
            scenario = sequential.get(backend_name, {})
            if isinstance(scenario, dict):
                scenario["records"] = [
                    compact_result_record(row)
                    for row in scenario.get("records", [])
                ]

        concurrent = backend_section.get("concurrent", {})
        for backend_name in ("file", "qdrant"):
            for scenario in concurrent.get(backend_name, []):
                scenario["records"] = [
                    compact_result_record(row)
                    for row in scenario.get("records", [])
                ]

    if api_section.get("skipped") is not True:
        sequential = api_section.get("warm_sequential", {})
        for target_name in ("file_dense", "qdrant"):
            scenario = sequential.get(target_name, {})
            if isinstance(scenario, dict):
                scenario["records"] = [
                    compact_result_record(row)
                    for row in scenario.get("records", [])
                ]

        concurrent = api_section.get("warm_concurrent", {})
        for target_name in ("file_dense", "qdrant"):
            for scenario in concurrent.get(target_name, []):
                scenario["records"] = [
                    compact_result_record(row)
                    for row in scenario.get("records", [])
                ]


def _fmt(value: Any, digits: int = 3) -> str:
    parsed = _safe_float(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:.{digits}f}"


def _build_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    verdict = report["verdict"]

    lines = [
        "# Qdrant Serving Performance v1",
        "",
        f"- schema_version: `{report['schema_version']}`",
        f"- generated_at_utc: `{report['generated_at_utc']}`",
        f"- preset: `{report['preset']}`",
        f"- build_id: `{summary.get('build_id')}`",
        f"- collection: `{summary.get('collection_name')}`",
        f"- query_count: `{summary.get('query_count')}`",
        f"- error_count: `{summary.get('error_count')}`",
        f"- verdict_ok: `{verdict.get('ok')}`",
        "",
        "## Safety markers",
        "",
        f"- benchmark_only: `{report['benchmark_only']}`",
        (
            "- production_default_changed: "
            f"`{report['production_default_changed']}`"
        ),
        (
            "- public_qdrant_promoted: "
            f"`{report['public_qdrant_promoted']}`"
        ),
        f"- fallback_used: `{report['fallback_used']}`",
        "",
        "## Quality",
        "",
        (
            "- comparison_count_across_scenarios: "
            f"`{verdict.get('comparison_count')}`"
        ),
        (
            "- mean_overlap_at_k: "
            f"`{_fmt(verdict.get('mean_overlap_at_k'))}`"
        ),
        (
            "- min_overlap_at_k: "
            f"`{_fmt(verdict.get('min_overlap_at_k'))}`"
        ),
        (
            "- exact_same_order_count_across_scenarios: "
            f"`{verdict.get('exact_same_order_count')}`"
        ),
        (
            "- result_count_mismatch_count: "
            f"`{verdict.get('result_count_mismatch_count')}`"
        ),
        (
            "- duplicate_id_failure_count: "
            f"`{verdict.get('duplicate_id_failure_count')}`"
        ),
        f"- failed_checks: `{verdict.get('failed_checks')}`",
        "",
        "## Encoding",
        "",
        (
            "- model_load_ms: "
            f"`{_fmt(report['encoding'].get('model_load_ms'))}`"
        ),
        (
            "- first_encode_ms: "
            f"`{_fmt(report['encoding'].get('first_encode_ms'))}`"
        ),
        (
            "- warm_p50_ms: "
            f"`{_fmt(report['encoding'].get('latency', {}).get('p50_ms'))}`"
        ),
        (
            "- warm_p95_ms: "
            f"`{_fmt(report['encoding'].get('latency', {}).get('p95_ms'))}`"
        ),
        "",
        "## Backend-only sequential",
        "",
        "| backend | requests | errors | p50 ms | p95 ms | max ms | throughput rps |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    backend_sequential = report.get(
        "backend_only", {}
    ).get("sequential", {})
    for backend_name in ("file", "qdrant"):
        row = backend_sequential.get(backend_name) or {}
        latency = row.get("latency") or {}
        lines.append(
            "| {backend} | {requests} | {errors} | {p50} | {p95} | {maximum} | {throughput} |".format(
                backend=backend_name,
                requests=row.get("success_count", "n/a"),
                errors=row.get("error_count", "n/a"),
                p50=_fmt(latency.get("p50_ms")),
                p95=_fmt(latency.get("p95_ms")),
                maximum=_fmt(latency.get("max_ms")),
                throughput=_fmt(row.get("throughput_rps")),
            )
        )

    lines.extend(
        [
            "",
            "## Backend-only concurrency",
            "",
            "| backend | concurrency | requests | errors | p50 ms | p95 ms | throughput rps |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    backend_concurrent = report.get(
        "backend_only", {}
    ).get("concurrent", {})
    for backend_name in ("file", "qdrant"):
        for row in backend_concurrent.get(backend_name, []):
            latency = row.get("latency") or {}
            lines.append(
                "| {backend} | {concurrency} | {requests} | {errors} | {p50} | {p95} | {throughput} |".format(
                    backend=backend_name,
                    concurrency=row.get("concurrency"),
                    requests=row.get("success_count"),
                    errors=row.get("error_count"),
                    p50=_fmt(latency.get("p50_ms")),
                    p95=_fmt(latency.get("p95_ms")),
                    throughput=_fmt(row.get("throughput_rps")),
                )
            )

    fresh = report.get("api_serving", {}).get(
        "fresh_process", {}
    )
    lines.extend(
        [
            "",
            "## Fresh-process API",
            "",
            "| target | startup ms | first request client ms | server total ms | server unattributed ms | client overhead ms |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for target_name in ("file_dense", "qdrant"):
        row = fresh.get(target_name) or {}
        first = row.get("first_request") or {}
        server = first.get("server_timing_ms") or {}
        derived = first.get("derived_timing_ms") or {}
        lines.append(
            "| {target} | {startup} | {client} | {server_total} | {unattributed} | {client_overhead} |".format(
                target=target_name,
                startup=_fmt(row.get("startup_ms")),
                client=_fmt(first.get("client_latency_ms")),
                server_total=_fmt(server.get("total_ms")),
                unattributed=_fmt(
                    derived.get("server_unattributed_ms")
                ),
                client_overhead=_fmt(
                    derived.get("client_overhead_ms")
                ),
            )
        )

    lines.extend(
        [
            "",
            "## API warm sequential",
            "",
            "| target | requests | errors | p50 ms | p95 ms | max ms | throughput rps |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    api_sequential = report.get(
        "api_serving", {}
    ).get("warm_sequential", {})
    for target_name in ("file_dense", "qdrant"):
        row = api_sequential.get(target_name) or {}
        latency = row.get("client_latency") or {}
        lines.append(
            "| {target} | {requests} | {errors} | {p50} | {p95} | {maximum} | {throughput} |".format(
                target=target_name,
                requests=row.get("success_count", "n/a"),
                errors=row.get("error_count", "n/a"),
                p50=_fmt(latency.get("p50_ms")),
                p95=_fmt(latency.get("p95_ms")),
                maximum=_fmt(latency.get("max_ms")),
                throughput=_fmt(row.get("throughput_rps")),
            )
        )

    lines.extend(
        [
            "",
            "## API concurrency",
            "",
            "| target | concurrency | requests | errors | p50 ms | p95 ms | throughput rps |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    api_concurrent = report.get(
        "api_serving", {}
    ).get("warm_concurrent", {})
    for target_name in ("file_dense", "qdrant"):
        for row in api_concurrent.get(target_name, []):
            latency = row.get("client_latency") or {}
            lines.append(
                "| {target} | {concurrency} | {requests} | {errors} | {p50} | {p95} | {throughput} |".format(
                    target=target_name,
                    concurrency=row.get("concurrency"),
                    requests=row.get("success_count"),
                    errors=row.get("error_count"),
                    p50=_fmt(latency.get("p50_ms")),
                    p95=_fmt(latency.get("p95_ms")),
                    throughput=_fmt(row.get("throughput_rps")),
                )
            )

    qdrant_seq = api_sequential.get("qdrant") or {}
    qdrant_stages = qdrant_seq.get("server_stage_latency") or {}
    if qdrant_stages:
        lines.extend(
            [
                "",
                "## Qdrant API warm sequential stage timings",
                "",
                "| stage | p50 ms | p95 ms | max ms |",
                "|---|---:|---:|---:|",
            ]
        )
        for stage_name, stage in qdrant_stages.items():
            lines.append(
                "| {stage_name} | {p50} | {p95} | {maximum} |".format(
                    stage_name=stage_name,
                    p50=_fmt(stage.get("p50_ms")),
                    p95=_fmt(stage.get("p95_ms")),
                    maximum=_fmt(stage.get("max_ms")),
                )
            )

    qdrant_derived = qdrant_seq.get(
        "derived_timing_latency"
    ) or {}
    if qdrant_derived:
        lines.extend(
            [
                "",
                "## Qdrant API warm sequential derived timings",
                "",
                "| field | p50 ms | p95 ms | max ms |",
                "|---|---:|---:|---:|",
            ]
        )
        for field_name, field in qdrant_derived.items():
            lines.append(
                "| {field_name} | {p50} | {p95} | {maximum} |".format(
                    field_name=field_name,
                    p50=_fmt(field.get("p50_ms")),
                    p95=_fmt(field.get("p95_ms")),
                    maximum=_fmt(field.get("max_ms")),
                )
            )

    lines.extend(
        [
            "",
            "## Resource summary",
            "",
            "Repeated scenario records retain result digests rather than full ranked ID lists. Full ranked IDs are retained once per quality comparison.",
            "",
        ]
    )

    errors = report.get("errors") or []
    if errors:
        lines.extend(["## Errors", ""])
        for row in errors[:30]:
            lines.append(f"- `{row}`")
        if len(errors) > 30:
            lines.append(
                f"- ... and `{len(errors) - 30}` more"
            )

    lines.append("")
    return "\n".join(lines)


def _save_report(
    *,
    report: Mapping[str, Any],
    output_dir: Path,
    run_ts: str,
) -> dict[str, str]:
    latest_json = (
        output_dir
        / "qdrant_serving_performance_latest.json"
    )
    latest_md = (
        output_dir
        / "qdrant_serving_performance_latest.md"
    )
    history_json = (
        output_dir
        / "history"
        / f"qdrant_serving_performance_{run_ts}.json"
    )
    history_md = (
        output_dir
        / "history"
        / f"qdrant_serving_performance_{run_ts}.md"
    )

    markdown = _build_markdown(report)

    dump_json(latest_json, report)
    dump_text(latest_md, markdown)
    dump_json(history_json, report)
    dump_text(history_md, markdown)

    return {
        "latest_json": normalize_path(latest_json) or "",
        "latest_md": normalize_path(latest_md) or "",
        "history_json": normalize_path(history_json) or "",
        "history_md": normalize_path(history_md) or "",
    }


def run_benchmark(
    *,
    config_path: Path,
    preset_name: str,
    output_dir_override: Path | None,
    skip_backend: bool,
    skip_api: bool,
) -> dict[str, Any]:
    run_ts = utc_ts()
    generated_at_utc = utc_iso()

    config = load_yaml(config_path)
    validate_benchmark_config(config)
    preset = resolve_preset(config, preset_name)

    qdrant_cfg = config["qdrant"]
    retrieval_cfg = config["retrieval"]
    api_cfg = config["api"]
    resources_cfg = config["resources"]
    quality_cfg = config["quality"]

    output_dir = (
        output_dir_override
        if output_dir_override is not None
        else Path(config["output"]["output_dir"])
    )

    manifest_path = Path(
        retrieval_cfg["manifest_path"]
    )
    golden_queries_path = Path(
        retrieval_cfg["golden_queries_path"]
    )

    manifest = load_json(manifest_path)
    if not isinstance(manifest, Mapping):
        raise ValueError(
            f"Expected manifest object: {manifest_path}"
        )

    embeddings_path = Path(
        manifest["dense_embeddings_path"]
    )
    ids_path = Path(manifest["dense_ids_path"])
    meta_path = Path(manifest["dense_meta_path"])

    dense_meta = load_json(meta_path)
    if not isinstance(dense_meta, Mapping):
        raise ValueError(
            f"Expected dense meta object: {meta_path}"
        )

    if (
        bool(
            retrieval_cfg.get(
                "require_normalized_embeddings",
                True,
            )
        )
        and dense_meta.get("normalized") is not True
    ):
        raise RuntimeError(
            "Serving benchmark requires normalized dense "
            "artifacts"
        )

    embeddings = np.load(
        embeddings_path,
        mmap_mode="r",
    )
    dense_ids = load_ids(ids_path)

    if embeddings.ndim != 2:
        raise ValueError(
            f"Dense embeddings must be 2D: {embeddings.shape}"
        )

    if len(dense_ids) != int(embeddings.shape[0]):
        raise ValueError(
            f"dense ids count {len(dense_ids)} != "
            f"embeddings rows {embeddings.shape[0]}"
        )

    raw_queries = enabled_queries(golden_queries_path)
    query_rows = select_queries(
        raw_queries,
        max_queries=preset.get("max_queries"),
    )

    if not query_rows:
        raise RuntimeError(
            "No enabled Golden Set queries selected"
        )

    model_name = str(
        manifest["embedding_model_name"]
    )

    model_load_started = time.perf_counter()
    model = SentenceTransformer(model_name)
    model_load_ms = _round_ms(
        (time.perf_counter() - model_load_started) * 1000
    )

    encoding = _run_encoding_benchmark(
        model=model,
        query_rows=query_rows,
        preset=preset,
    )
    encoding["model_load_ms"] = model_load_ms
    encoding["model_name"] = model_name
    encoding["device"] = str(
        getattr(model, "device", None)
    )

    workloads, workload_encoding = _build_query_workload(
        model=model,
        query_rows=query_rows,
    )
    encoding.update(workload_encoding)

    store = QdrantRetrievalStore(
        host=str(qdrant_cfg["host"]),
        port=int(qdrant_cfg["port"]),
        grpc_port=int(qdrant_cfg["grpc_port"]),
        prefer_grpc=bool(qdrant_cfg["prefer_grpc"]),
        collection_name=str(
            qdrant_cfg["collection_name"]
        ),
        timeout_sec=float(
            qdrant_cfg["timeout_sec"]
        ),
        check_compatibility=bool(
            qdrant_cfg.get(
                "check_compatibility",
                False,
            )
        ),
    )

    collection = _collection_summary(store)

    build_id = str(manifest["build_id"])
    corpus_doc_count = int(
        manifest["corpus_doc_count"]
    )
    vector_size = int(embeddings.shape[1])
    expected_distance = str(
        retrieval_cfg.get(
            "expected_distance",
            "Cosine",
        )
    )

    backend_section: dict[str, Any] = {
        "skipped": bool(skip_backend),
    }
    api_section: dict[str, Any] = {
        "skipped": bool(skip_api),
    }
    comparison_sections: dict[str, Mapping[str, Any]] = {}
    top_level_errors: list[dict[str, Any]] = []

    if not skip_backend:
        file_construct_started = time.perf_counter()
        file_backend = FileDenseBackend(
            embeddings=embeddings,
            ids=dense_ids,
            build_id=build_id,
            normalized=bool(
                dense_meta.get("normalized")
            ),
        )
        file_construction_ms = _round_ms(
            (time.perf_counter() - file_construct_started)
            * 1000
        )

        profile_cfg = qdrant_cfg["profile"]

        qdrant_construct_started = time.perf_counter()
        qdrant_backend = QdrantDenseBackend(
            store=store,
            profile=QdrantSearchProfile(
                name=str(profile_cfg["name"]),
                exact=bool(
                    profile_cfg.get("exact", False)
                ),
                hnsw_ef=profile_cfg.get("hnsw_ef"),
            ),
            expected_build_id=build_id,
            expected_corpus_count=corpus_doc_count,
            expected_vector_size=vector_size,
            expected_distance=expected_distance,
            dense_ids=dense_ids,
            require_point_id_equals_dense_index=True,
        )
        qdrant_construction_ms = _round_ms(
            (
                time.perf_counter()
                - qdrant_construct_started
            )
            * 1000
        )

        first_workload = workloads[0]
        first_top_k = int(
            preset["top_k_values"][0]
        )

        first_file: dict[str, Any] | None = None
        first_qdrant: dict[str, Any] | None = None
        first_errors: list[dict[str, Any]] = []

        try:
            first_file = _backend_call(
                backend=file_backend,
                workload=first_workload,
                top_k=first_top_k,
            )
        except Exception as exc:
            first_errors.append(
                {
                    "backend": "file",
                    "error": _error_text(exc),
                }
            )

        try:
            first_qdrant = _backend_call(
                backend=qdrant_backend,
                workload=first_workload,
                top_k=first_top_k,
            )
        except Exception as exc:
            first_errors.append(
                {
                    "backend": "qdrant",
                    "error": _error_text(exc),
                }
            )

        first_comparison = None
        if (
            first_file is not None
            and first_qdrant is not None
        ):
            first_comparison = compare_id_lists(
                first_file["canonical_ids"],
                first_qdrant["canonical_ids"],
                top_k=first_top_k,
            )

        backend_cfg = preset["backend"]
        warmup_rounds = int(
            backend_cfg["warmup_rounds"]
        )
        measured_rounds = int(
            backend_cfg["measured_rounds"]
        )
        concurrency_levels = [
            int(value)
            for value in backend_cfg[
                "concurrency_levels"
            ]
        ]
        top_k_values = [
            int(value)
            for value in preset["top_k_values"]
        ]

        _warm_backend(
            backend=file_backend,
            workloads=workloads,
            top_k_values=top_k_values,
            rounds=warmup_rounds,
        )
        _warm_backend(
            backend=qdrant_backend,
            workloads=workloads,
            top_k_values=top_k_values,
            rounds=warmup_rounds,
        )

        file_sequential = _run_backend_sequential(
            backend_name="file",
            backend=file_backend,
            workloads=workloads,
            top_k_values=top_k_values,
            measured_rounds=measured_rounds,
            resources_cfg=resources_cfg,
        )
        qdrant_sequential = _run_backend_sequential(
            backend_name="qdrant",
            backend=qdrant_backend,
            workloads=workloads,
            top_k_values=top_k_values,
            measured_rounds=measured_rounds,
            resources_cfg=resources_cfg,
        )

        backend_sequential_quality = _compare_backend_records(
            file_records=file_sequential["records"],
            qdrant_records=qdrant_sequential["records"],
        )
        comparison_sections[
            "backend_sequential"
        ] = backend_sequential_quality

        file_concurrent = _run_backend_concurrent(
            backend_name="file",
            backend=file_backend,
            workloads=workloads,
            top_k_values=top_k_values,
            measured_rounds=measured_rounds,
            concurrency_levels=concurrency_levels,
            resources_cfg=resources_cfg,
        )
        qdrant_concurrent = _run_backend_concurrent(
            backend_name="qdrant",
            backend=qdrant_backend,
            workloads=workloads,
            top_k_values=top_k_values,
            measured_rounds=measured_rounds,
            concurrency_levels=concurrency_levels,
            resources_cfg=resources_cfg,
        )

        concurrent_quality: dict[str, Any] = {}
        for concurrency in concurrency_levels:
            file_row = next(
                row
                for row in file_concurrent
                if row["concurrency"] == concurrency
            )
            qdrant_row = next(
                row
                for row in qdrant_concurrent
                if row["concurrency"] == concurrency
            )
            quality = _compare_backend_records(
                file_records=file_row["records"],
                qdrant_records=qdrant_row["records"],
            )
            concurrent_quality[str(concurrency)] = quality
            comparison_sections[
                f"backend_concurrent_{concurrency}"
            ] = quality

        backend_section = {
            "skipped": False,
            "construction": {
                "file_ms": file_construction_ms,
                "qdrant_ms": qdrant_construction_ms,
            },
            "first_request": {
                "file": first_file,
                "qdrant": first_qdrant,
                "comparison": first_comparison,
                "errors": first_errors,
            },
            "warmup_rounds": warmup_rounds,
            "sequential": {
                "file": file_sequential,
                "qdrant": qdrant_sequential,
                "quality": backend_sequential_quality,
            },
            "concurrent": {
                "file": file_concurrent,
                "qdrant": qdrant_concurrent,
                "quality_by_concurrency": concurrent_quality,
            },
        }

    if not skip_api:
        api_cfg_preset = preset["api"]
        api_warmup_rounds = int(
            api_cfg_preset["warmup_rounds"]
        )
        api_measured_rounds = int(
            api_cfg_preset["measured_rounds"]
        )
        api_concurrency_levels = [
            int(value)
            for value in api_cfg_preset[
                "concurrency_levels"
            ]
        ]
        top_k_values = [
            int(value)
            for value in preset["top_k_values"]
        ]

        file_target_cfg = api_cfg["file_dense"]
        qdrant_target_cfg = api_cfg["qdrant"]

        fresh_section: dict[str, Any] = {
            "enabled": bool(
                preset["fresh_process"]["enabled"]
            )
        }

        if fresh_section["enabled"]:
            first_query = query_rows[0]
            first_top_k = top_k_values[0]

            try:
                fresh_file = _run_fresh_process_target(
                    api_cfg=api_cfg,
                    qdrant_cfg=qdrant_cfg,
                    resources_cfg=resources_cfg,
                    output_dir=output_dir,
                    run_ts=run_ts,
                    target_name="file_dense",
                    target_cfg=file_target_cfg,
                    query_row=first_query,
                    top_k=first_top_k,
                )
                fresh_section["file_dense"] = fresh_file
            except Exception as exc:
                fresh_section["file_dense"] = {
                    "error": _error_text(exc)
                }
                top_level_errors.append(
                    {
                        "stage": "api_fresh_file_dense",
                        "error": _error_text(exc),
                    }
                )

            try:
                fresh_qdrant = _run_fresh_process_target(
                    api_cfg=api_cfg,
                    qdrant_cfg=qdrant_cfg,
                    resources_cfg=resources_cfg,
                    output_dir=output_dir,
                    run_ts=run_ts,
                    target_name="qdrant",
                    target_cfg=qdrant_target_cfg,
                    query_row=first_query,
                    top_k=first_top_k,
                )
                fresh_section["qdrant"] = fresh_qdrant
            except Exception as exc:
                fresh_section["qdrant"] = {
                    "error": _error_text(exc)
                }
                top_level_errors.append(
                    {
                        "stage": "api_fresh_qdrant",
                        "error": _error_text(exc),
                    }
                )

            if (
                isinstance(
                    fresh_section.get("file_dense"),
                    Mapping,
                )
                and isinstance(
                    fresh_section.get("qdrant"),
                    Mapping,
                )
                and "first_request"
                in fresh_section["file_dense"]
                and "first_request"
                in fresh_section["qdrant"]
            ):
                fresh_reference_ids = [
                    str(value)
                    for value in fresh_section["file_dense"][
                        "first_request"
                    ]["canonical_ids"]
                ]
                fresh_candidate_ids = [
                    str(value)
                    for value in fresh_section["qdrant"][
                        "first_request"
                    ]["canonical_ids"]
                ]
                fresh_quality = compare_id_lists(
                    fresh_reference_ids,
                    fresh_candidate_ids,
                    top_k=first_top_k,
                )
                fresh_section["quality"] = fresh_quality
                comparison_sections["api_fresh"] = {
                    "comparison_count": 1,
                    "missing_comparison_count": 0,
                    "mean_overlap_at_k": fresh_quality[
                        "overlap_ratio"
                    ],
                    "min_overlap_at_k": fresh_quality[
                        "overlap_ratio"
                    ],
                    "exact_same_order_count": int(
                        fresh_quality[
                            "exact_same_order"
                        ]
                    ),
                    "exact_same_order_all": bool(
                        fresh_quality[
                            "exact_same_order"
                        ]
                    ),
                    "comparisons": [
                        {
                            "query_id": str(
                                first_query.get(
                                    "query_id"
                                )
                                or "fresh_query"
                            ),
                            "top_k": first_top_k,
                            "comparison_available": True,
                            "reference_ids": (
                                fresh_reference_ids[:first_top_k]
                            ),
                            "candidate_ids": (
                                fresh_candidate_ids[:first_top_k]
                            ),
                            "reference_ids_digest": (
                                result_ids_digest(
                                    fresh_reference_ids[:first_top_k]
                                )
                            ),
                            "candidate_ids_digest": (
                                result_ids_digest(
                                    fresh_candidate_ids[:first_top_k]
                                )
                            ),
                            **fresh_quality,
                        }
                    ],
                    "file_determinism": {
                        "failure_count": 0
                    },
                    "qdrant_determinism": {
                        "failure_count": 0
                    },
                }

        warm_api_payload: dict[str, Any]

        try:
            with running_api_process(
                api_cfg=api_cfg,
                qdrant_cfg=qdrant_cfg,
                output_dir=output_dir,
                run_ts=run_ts,
                label="warm",
            ) as api_process:
                timeout = float(
                    api_cfg["request_timeout_sec"]
                )

                with httpx.Client(
                    timeout=timeout,
                    limits=httpx.Limits(
                        max_connections=max(
                            api_concurrency_levels
                        )
                        * 2,
                        max_keepalive_connections=max(
                            api_concurrency_levels
                        ),
                    ),
                ) as client:
                    _warm_api_target(
                        client=client,
                        api_process=api_process,
                        target_name="file_dense",
                        target_cfg=file_target_cfg,
                        query_rows=query_rows,
                        top_k_values=top_k_values,
                        warmup_rounds=api_warmup_rounds,
                    )
                    _warm_api_target(
                        client=client,
                        api_process=api_process,
                        target_name="qdrant",
                        target_cfg=qdrant_target_cfg,
                        query_rows=query_rows,
                        top_k_values=top_k_values,
                        warmup_rounds=api_warmup_rounds,
                    )

                    file_api_sequential = _run_api_sequential(
                        client=client,
                        api_process=api_process,
                        target_name="file_dense",
                        target_cfg=file_target_cfg,
                        query_rows=query_rows,
                        top_k_values=top_k_values,
                        measured_rounds=api_measured_rounds,
                        resources_cfg=resources_cfg,
                    )
                    qdrant_api_sequential = _run_api_sequential(
                        client=client,
                        api_process=api_process,
                        target_name="qdrant",
                        target_cfg=qdrant_target_cfg,
                        query_rows=query_rows,
                        top_k_values=top_k_values,
                        measured_rounds=api_measured_rounds,
                        resources_cfg=resources_cfg,
                    )

                    api_sequential_quality = _compare_api_records(
                        file_records=file_api_sequential[
                            "records"
                        ],
                        qdrant_records=qdrant_api_sequential[
                            "records"
                        ],
                    )
                    comparison_sections[
                        "api_sequential"
                    ] = api_sequential_quality

                    file_api_concurrent = _run_api_concurrent(
                        client=client,
                        api_process=api_process,
                        target_name="file_dense",
                        target_cfg=file_target_cfg,
                        query_rows=query_rows,
                        top_k_values=top_k_values,
                        measured_rounds=api_measured_rounds,
                        concurrency_levels=api_concurrency_levels,
                        resources_cfg=resources_cfg,
                    )
                    qdrant_api_concurrent = _run_api_concurrent(
                        client=client,
                        api_process=api_process,
                        target_name="qdrant",
                        target_cfg=qdrant_target_cfg,
                        query_rows=query_rows,
                        top_k_values=top_k_values,
                        measured_rounds=api_measured_rounds,
                        concurrency_levels=api_concurrency_levels,
                        resources_cfg=resources_cfg,
                    )

                    api_concurrent_quality: dict[str, Any] = {}
                    for concurrency in api_concurrency_levels:
                        file_row = next(
                            row
                            for row in file_api_concurrent
                            if row["concurrency"]
                            == concurrency
                        )
                        qdrant_row = next(
                            row
                            for row in qdrant_api_concurrent
                            if row["concurrency"]
                            == concurrency
                        )
                        quality = _compare_api_records(
                            file_records=file_row[
                                "records"
                            ],
                            qdrant_records=qdrant_row[
                                "records"
                            ],
                        )
                        api_concurrent_quality[
                            str(concurrency)
                        ] = quality
                        comparison_sections[
                            f"api_concurrent_{concurrency}"
                        ] = quality

                    warm_api_payload = {
                        "startup_ms": api_process.startup_ms,
                        "process_pid": (
                            api_process.process.pid
                        ),
                        "log_path": normalize_path(
                            api_process.log_path
                        ),
                        "warmup_rounds": (
                            api_warmup_rounds
                        ),
                        "sequential": {
                            "file_dense": (
                                file_api_sequential
                            ),
                            "qdrant": (
                                qdrant_api_sequential
                            ),
                            "quality": (
                                api_sequential_quality
                            ),
                        },
                        "concurrent": {
                            "file_dense": (
                                file_api_concurrent
                            ),
                            "qdrant": (
                                qdrant_api_concurrent
                            ),
                            "quality_by_concurrency": (
                                api_concurrent_quality
                            ),
                        },
                    }

        except Exception as exc:
            warm_api_payload = {
                "error": _error_text(exc)
            }
            top_level_errors.append(
                {
                    "stage": "api_warm_process",
                    "error": _error_text(exc),
                }
            )

        if isinstance(warm_api_payload, Mapping):
            warm_process_meta = {
                key: value
                for key, value in warm_api_payload.items()
                if key not in {"sequential", "concurrent"}
            }
            warm_sequential = warm_api_payload.get(
                "sequential", {}
            )
            warm_concurrent = warm_api_payload.get(
                "concurrent", {}
            )
        else:
            warm_process_meta = {}
            warm_sequential = {}
            warm_concurrent = {}

        api_section = {
            "skipped": False,
            "fresh_process": fresh_section,
            "warm_process": warm_process_meta,
            "warm_sequential": warm_sequential,
            "warm_concurrent": warm_concurrent,
        }

    scenario_error_count = 0

    if not skip_backend:
        scenario_error_count += len(
            backend_section.get(
                "first_request", {}
            ).get("errors", [])
        )
        sequential = backend_section.get("sequential", {})
        scenario_error_count += int(
            sequential.get("file", {}).get("error_count", 0)
        )
        scenario_error_count += int(
            sequential.get("qdrant", {}).get("error_count", 0)
        )
        concurrent = backend_section.get("concurrent", {})
        scenario_error_count += sum(
            int(row.get("error_count", 0))
            for row in concurrent.get("file", [])
        )
        scenario_error_count += sum(
            int(row.get("error_count", 0))
            for row in concurrent.get("qdrant", [])
        )

    if not skip_api:
        sequential = api_section.get("warm_sequential", {})
        scenario_error_count += int(
            sequential.get("file_dense", {}).get(
                "error_count", 0
            )
        )
        scenario_error_count += int(
            sequential.get("qdrant", {}).get(
                "error_count", 0
            )
        )
        concurrent = api_section.get("warm_concurrent", {})
        scenario_error_count += sum(
            int(row.get("error_count", 0))
            for row in concurrent.get("file_dense", [])
        )
        scenario_error_count += sum(
            int(row.get("error_count", 0))
            for row in concurrent.get("qdrant", [])
        )

    total_error_count = (
        scenario_error_count + len(top_level_errors)
    )

    verdict = _quality_verdict(
        comparison_sections=comparison_sections,
        quality_cfg=quality_cfg,
        error_count=total_error_count,
    )

    _compact_repeated_records(
        backend_section=backend_section,
        api_section=api_section,
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc,
        "run_ts": run_ts,
        "preset": preset_name,
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
        "config_path": normalize_path(config_path),
        "config": config,
        "resolved_preset": preset,
        "environment": _python_environment(),
        "inputs": {
            "manifest_path": normalize_path(
                manifest_path
            ),
            "golden_queries_path": normalize_path(
                golden_queries_path
            ),
            "dense_embeddings_path": normalize_path(
                embeddings_path
            ),
            "dense_ids_path": normalize_path(ids_path),
            "dense_meta_path": normalize_path(meta_path),
        },
        "summary": {
            "build_id": build_id,
            "corpus_doc_count": corpus_doc_count,
            "embedding_model_name": model_name,
            "embedding_shape": [
                int(embeddings.shape[0]),
                int(embeddings.shape[1]),
            ],
            "query_count": len(query_rows),
            "top_k_values": list(
                preset["top_k_values"]
            ),
            "collection_name": str(
                qdrant_cfg["collection_name"]
            ),
            "profile_name": str(
                qdrant_cfg["profile"]["name"]
            ),
            "qdrant_transport": store.transport,
            "qdrant_rest_port": store.port,
            "qdrant_grpc_port": store.grpc_port,
            "error_count": total_error_count,
            "quality_ok": verdict["ok"],
        },
        "collection": collection,
        "query_set": {
            "enabled_query_count": len(raw_queries),
            "selected_query_count": len(query_rows),
            "selection": str(
                retrieval_cfg.get(
                    "query_selection",
                    "ordered",
                )
            ),
            "query_ids": [
                str(
                    row.get("query_id")
                    or f"query_{index}"
                )
                for index, row in enumerate(
                    query_rows,
                    start=1,
                )
            ],
            "queries": [
                {
                    "query_id": str(
                        row.get("query_id")
                        or f"query_{index}"
                    ),
                    "query_text": resolve_query_text(row),
                }
                for index, row in enumerate(
                    query_rows,
                    start=1,
                )
            ],
        },
        "encoding": encoding,
        "backend_only": backend_section,
        "api_serving": api_section,
        "quality": {
            "policy": dict(quality_cfg),
            "sections": comparison_sections,
        },
        "errors": top_level_errors,
        "verdict": verdict,
    }

    paths = _save_report(
        report=report,
        output_dir=output_dir,
        run_ts=run_ts,
    )
    report["report_paths"] = paths

    # Rewrite the latest/history JSON once so report_paths are included.
    paths = _save_report(
        report=report,
        output_dir=output_dir,
        run_ts=run_ts,
    )

    print(f"[OK] schema_version={SCHEMA_VERSION}")
    print(f"[OK] preset={preset_name}")
    print(f"[OK] query_count={len(query_rows)}")
    print(f"[OK] collection={collection.get('collection_name')}")
    print(f"[OK] build_id={build_id}")
    print(f"[OK] error_count={total_error_count}")
    print(f"[OK] quality_ok={verdict['ok']}")
    print(f"[OK] latest_json={paths['latest_json']}")
    print(f"[OK] latest_md={paths['latest_md']}")

    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
    )
    parser.add_argument(
        "--preset",
        choices=("smoke", "full"),
        default="smoke",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--skip-backend",
        action="store_true",
        help="Skip direct FileDenseBackend/QdrantDenseBackend scenarios.",
    )
    parser.add_argument(
        "--skip-api",
        action="store_true",
        help="Skip fresh and warm Uvicorn serving scenarios.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    report = run_benchmark(
        config_path=args.config_path,
        preset_name=args.preset,
        output_dir_override=args.output_dir,
        skip_backend=args.skip_backend,
        skip_api=args.skip_api,
    )

    if report["verdict"]["ok"] is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
