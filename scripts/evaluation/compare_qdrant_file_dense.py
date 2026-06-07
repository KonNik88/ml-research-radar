"""Compare a selected Qdrant ANN profile with exact file-dense retrieval.

The report has two independent Qdrant paths:

* ``selected_profile`` — the ANN profile chosen by the profile sweep;
* ``exact_profile`` — a diagnostic exact Qdrant search that must match the
  exact file reference.

The script is read-only with respect to Qdrant. It does not create collections,
upload vectors, mutate canonical data, or change API runtime defaults.

Run from the project root::

    python -m scripts.evaluation.compare_qdrant_file_dense
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import yaml
from sentence_transformers import SentenceTransformer
from radar_core.retrieval.dense_backend import (
    DenseSearchRequest,
    FileDenseBackend,
    QdrantDenseBackend,
    QdrantSearchProfile,
)
from radar_core.retrieval.parity import (
    audit_qdrant_mapping,
    build_mismatch_details,
    check_repeat_determinism,
    classify_profile_difference,
    compare_ranked_results,
    file_backend_result_to_rows,
    qdrant_backend_result_to_rows,
    query_vector_metadata,
    summarize_latencies,
)
from radar_core.retrieval.qdrant_store import QdrantRetrievalStore


SCHEMA_VERSION = "qdrant_file_dense_comparison_v2"
CONFIG_SCHEMA_VERSION = "qdrant_parity_v2"
DEFAULT_CONFIG_PATH = Path("configs/qdrant_parity_v2.yaml")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/evaluation")


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: str | Path | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML mapping in {path}")
    return payload


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


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
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"Expected JSON object at {path}:{line_no}")
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
    return [row for row in read_jsonl(path) if row.get("enabled") is True]


def resolve_query_text(row: Mapping[str, Any]) -> str:
    for key in ("query", "query_text", "text"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    raise ValueError(f"Golden query row has no query text: {row.get('query_id')}")


def validate_profiles(raw_profiles: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_profiles, list) or not raw_profiles:
        raise ValueError("Config must contain a non-empty profiles list")

    profiles: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, raw in enumerate(raw_profiles):
        if not isinstance(raw, dict):
            raise ValueError(f"profiles[{index}] must be a mapping")
        name = str(raw.get("name") or "").strip()
        if not name:
            raise ValueError(f"profiles[{index}].name is required")
        if name in names:
            raise ValueError(f"Duplicate profile name: {name}")
        names.add(name)

        hnsw_ef = raw.get("hnsw_ef")
        if hnsw_ef is not None:
            hnsw_ef = int(hnsw_ef)
            if hnsw_ef <= 0:
                raise ValueError(f"Profile {name}: hnsw_ef must be positive")

        profiles.append(
            {
                "name": name,
                "exact": bool(raw.get("exact", False)),
                "hnsw_ef": hnsw_ef,
            }
        )
    return profiles


def collection_summary(
    store: QdrantRetrievalStore,
) -> dict[str, Any]:
    """Return the existing comparison-report collection shape."""

    info = store.get_collection_info()

    return {
        "collection_name": store.collection_name,
        "status": info.get("status"),
        "optimizer_status": info.get("optimizer_status"),
        "points_count": info.get("points_count"),
        "indexed_vectors_count": info.get("indexed_vectors_count"),
        "vector_size": info.get("vector_size"),
        "distance": info.get("distance"),
    }


def build_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    selected = report["selected_profile_summary"]
    exact = report["exact_profile_summary"]
    latency = report["latency_summary"]

    lines = [
        "# Qdrant vs File Dense Comparison v2",
        "",
        f"- schema_version: `{report['schema_version']}`",
        f"- generated_at_utc: `{report['generated_at_utc']}`",
        f"- build_id: `{summary.get('build_id')}`",
        f"- collection_name: `{summary.get('collection_name')}`",
        f"- query_count: `{summary.get('query_count')}`",
        f"- error_count: `{summary.get('error_count')}`",
        f"- selected_profile: `{summary.get('selected_profile_name')}`",
        f"- exact_profile: `{summary.get('exact_profile_name')}`",
        f"- selected_profile_full_match: `{summary.get('selected_profile_full_match')}`",
        f"- exact_profile_full_match: `{summary.get('exact_profile_full_match')}`",
        f"- blocking_classification_count: `{summary.get('blocking_classification_count')}`",
        "",
        "## Selected ANN profile",
        "",
        f"- profile: `{selected.get('profile')}`",
        f"- mean_overlap_at_k: `{selected.get('mean_overlap_at_k')}`",
        f"- min_overlap_at_k: `{selected.get('min_overlap_at_k')}`",
        f"- exact_same_order_count: `{selected.get('exact_same_order_count')}`",
        f"- mismatch_count: `{selected.get('mismatch_count')}`",
        f"- mapping_failure_count: `{selected.get('mapping_failure_count')}`",
        f"- latency: `{latency.get('selected_profile')}`",
        "",
        "## Exact diagnostic profile",
        "",
        f"- profile: `{exact.get('profile')}`",
        f"- mean_overlap_at_k: `{exact.get('mean_overlap_at_k')}`",
        f"- min_overlap_at_k: `{exact.get('min_overlap_at_k')}`",
        f"- exact_same_order_count: `{exact.get('exact_same_order_count')}`",
        f"- mismatch_count: `{exact.get('mismatch_count')}`",
        f"- mapping_failure_count: `{exact.get('mapping_failure_count')}`",
        f"- latency: `{latency.get('exact_profile')}`",
        "",
        f"- file_reference_latency: `{latency.get('file_reference')}`",
    ]

    mismatches = report.get("mismatch_queries", [])
    if mismatches:
        lines.extend(["", "## Mismatch queries", ""])
        for row in mismatches:
            lines.append(
                f"- `{row.get('query_id')}`: classification=`{row.get('classification')}`, "
                f"severity=`{row.get('severity')}`, overlap=`{row.get('overlap_ratio')}`, "
                f"best_missed_reference_rank=`{row.get('best_missed_reference_rank')}`"
            )

    errors = report.get("errors", [])
    if errors:
        lines.extend(["", "## Errors", ""])
        for error in errors:
            lines.append(f"- `{error}`")

    lines.append("")
    return "\n".join(lines)


def profile_summary(
    *,
    profile: Mapping[str, Any],
    query_results: list[dict[str, Any]],
    result_key: str,
) -> dict[str, Any]:
    rows = [row[result_key] for row in query_results if result_key in row]
    overlaps = [float(row["comparison"]["overlap_ratio"]) for row in rows]
    exact_count = sum(bool(row["comparison"]["exact_same_order"]) for row in rows)
    mismatches = [row for row in rows if not row["comparison"]["exact_same_order"]]
    mapping_failures = sum(int(row["mapping_audit"]["failure_count"]) for row in rows)
    return {
        "profile": dict(profile),
        "query_count": len(rows),
        "mean_overlap_at_k": float(np.mean(overlaps)) if overlaps else None,
        "min_overlap_at_k": min(overlaps) if overlaps else None,
        "exact_same_order_count": exact_count,
        "mismatch_count": len(mismatches),
        "mismatch_query_ids": [row["query_id"] for row in mismatches],
        "mapping_failure_count": mapping_failures,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--max-queries", type=int, default=None)
    args = parser.parse_args(argv)

    run_ts = utc_ts()
    config = load_yaml(args.config_path)
    if config.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise ValueError(
            f"Expected config schema {CONFIG_SCHEMA_VERSION!r}, "
            f"got {config.get('schema_version')!r}"
        )

    qdrant_cfg = config.get("qdrant") or {}
    retrieval_cfg = config.get("retrieval") or {}
    comparison_cfg = config.get("comparison") or {}
    diagnostics_cfg = config.get("diagnostics") or {}
    quality_cfg = config.get("quality") or {}
    output_cfg = config.get("output") or {}

    profiles = validate_profiles(config.get("profiles"))
    profile_by_name = {str(profile["name"]): profile for profile in profiles}
    selected_profile_name = str(
        comparison_cfg.get("selected_profile_name", "ef_256")
    )
    exact_profile_name = str(comparison_cfg.get("exact_profile_name", "exact"))
    if selected_profile_name not in profile_by_name:
        raise ValueError(f"Selected profile not found: {selected_profile_name}")
    if exact_profile_name not in profile_by_name:
        raise ValueError(f"Exact profile not found: {exact_profile_name}")

    selected_profile = profile_by_name[selected_profile_name]
    exact_profile = profile_by_name[exact_profile_name]
    if bool(selected_profile.get("exact")):
        raise ValueError("Selected ANN profile must not be exact")
    if not bool(exact_profile.get("exact")):
        raise ValueError("Exact diagnostic profile must have exact=true")

    external_top_k = int(retrieval_cfg.get("external_top_k", 20))
    boundary_window = int(retrieval_cfg.get("boundary_window", 10))
    if external_top_k <= 0:
        raise ValueError("external_top_k must be positive")
    if boundary_window < 0:
        raise ValueError("boundary_window must be non-negative")
    internal_top_k = external_top_k + boundary_window

    warmup_runs = int(diagnostics_cfg.get("warmup_runs", 1))
    repeated_runs = int(diagnostics_cfg.get("repeated_runs", 5))
    audit_mapping = bool(diagnostics_cfg.get("audit_mapping", True))
    require_point_id_equals_dense_index = bool(
        diagnostics_cfg.get("require_point_id_equals_dense_index", True)
    )

    manifest_path = Path(
        retrieval_cfg.get("manifest_path", "artifacts/retrieval/manifests/latest.json")
    )
    golden_queries_path = Path(
        retrieval_cfg.get(
            "golden_queries_path", "data/eval/retrieval/golden_queries.jsonl"
        )
    )
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError(f"Expected manifest object: {manifest_path}")

    embeddings_path = Path(manifest["dense_embeddings_path"])
    ids_path = Path(manifest["dense_ids_path"])
    meta_path = Path(manifest["dense_meta_path"])
    dense_meta = load_json(meta_path)
    if not isinstance(dense_meta, dict):
        raise ValueError(f"Expected dense meta object: {meta_path}")
    if dense_meta.get("normalized") is not True:
        raise ValueError("Exact file reference requires dense meta normalized=true")

    embeddings = np.load(embeddings_path, mmap_mode="r")
    ids = load_ids(ids_path)
    if embeddings.ndim != 2:
        raise ValueError(f"Expected 2D dense embeddings, got {embeddings.shape}")
    if len(ids) != int(embeddings.shape[0]):
        raise ValueError(f"dense ids count {len(ids)} != embeddings rows {embeddings.shape[0]}")

    queries = enabled_queries(golden_queries_path)
    if args.max_queries is not None:
        if args.max_queries <= 0:
            raise ValueError("--max-queries must be positive")
        queries = queries[: args.max_queries]

    model = SentenceTransformer(str(manifest["embedding_model_name"]))

    if bool(qdrant_cfg.get("prefer_grpc", False)):
        raise ValueError(
            "compare_qdrant_file_dense does not support prefer_grpc=true "
            "through QdrantRetrievalStore"
        )

    collection_name = str(
        qdrant_cfg.get(
            "collection_name",
            "ml_radar_dense_benchmark_v1",
        )
    )

    store = QdrantRetrievalStore(
        host=str(qdrant_cfg.get("host", "localhost")),
        port=int(qdrant_cfg.get("port", 6333)),
        collection_name=collection_name,
        timeout_sec=float(qdrant_cfg.get("timeout_sec", 120)),
        check_compatibility=bool(
            qdrant_cfg.get("check_compatibility", False)
        ),
    )

    build_id = str(manifest["build_id"])
    corpus_doc_count = int(manifest["corpus_doc_count"])
    vector_size = int(embeddings.shape[1])

    file_backend = FileDenseBackend(
        embeddings=embeddings,
        ids=ids,
        build_id=build_id,
        normalized=True,
    )

    selected_qdrant_profile = QdrantSearchProfile(
        name=str(selected_profile["name"]),
        exact=bool(selected_profile["exact"]),
        hnsw_ef=selected_profile.get("hnsw_ef"),
    )
    exact_qdrant_profile = QdrantSearchProfile(
        name=str(exact_profile["name"]),
        exact=bool(exact_profile["exact"]),
        hnsw_ef=exact_profile.get("hnsw_ef"),
    )

    selected_backend = QdrantDenseBackend(
        store=store,
        profile=selected_qdrant_profile,
        expected_build_id=build_id,
        expected_corpus_count=corpus_doc_count,
        expected_vector_size=vector_size,
        expected_distance="Cosine",
        dense_ids=ids,
        require_point_id_equals_dense_index=(
            require_point_id_equals_dense_index
        ),
    )
    exact_backend = QdrantDenseBackend(
        store=store,
        profile=exact_qdrant_profile,
        expected_build_id=build_id,
        expected_corpus_count=corpus_doc_count,
        expected_vector_size=vector_size,
        expected_distance="Cosine",
        dense_ids=ids,
        require_point_id_equals_dense_index=(
            require_point_id_equals_dense_index
        ),
    )

    collection = collection_summary(store)

    query_results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    file_latencies: list[float] = []
    selected_latencies: list[float] = []
    exact_latencies: list[float] = []

    for index, row in enumerate(queries, start=1):
        query_id = str(row.get("query_id") or f"query_{index}")
        try:
            query_text = resolve_query_text(row)
            print(f"[{index}/{len(queries)}] {query_id}: {query_text}")

            query_vector = model.encode(
                [query_text],
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )[0].astype(np.float32)
            vector_meta = query_vector_metadata(query_vector)

            request = DenseSearchRequest(
                query_vector=query_vector,
                top_k=internal_top_k,
            )

            file_backend_result = file_backend.search(request)
            file_rows = file_backend_result_to_rows(
                file_backend_result
            )
            file_latency_ms = float(
                file_backend_result.timing_ms.get(
                    "backend_search_ms",
                    0.0,
                )
            )

            selected_backend_result = selected_backend.search(request)
            selected_rows = qdrant_backend_result_to_rows(
                selected_backend_result
            )
            selected_latency_ms = float(
                selected_backend_result.timing_ms.get(
                    "backend_search_ms",
                    0.0,
                )
            )

            exact_backend_result = exact_backend.search(request)
            exact_rows = qdrant_backend_result_to_rows(
                exact_backend_result
            )
            exact_latency_ms = float(
                exact_backend_result.timing_ms.get(
                    "backend_search_ms",
                    0.0,
                )
            )

            selected_comparison = compare_ranked_results(
                reference_rows=file_rows,
                candidate_rows=selected_rows,
                top_k=external_top_k,
            )
            exact_comparison = compare_ranked_results(
                reference_rows=file_rows,
                candidate_rows=exact_rows,
                top_k=external_top_k,
            )

            if audit_mapping:
                selected_mapping = audit_qdrant_mapping(
                    rows=selected_rows,
                    ids=ids,
                    expected_build_id=str(manifest["build_id"]),
                    require_point_id_equals_dense_index=require_point_id_equals_dense_index,
                )
                exact_mapping = audit_qdrant_mapping(
                    rows=exact_rows,
                    ids=ids,
                    expected_build_id=str(manifest["build_id"]),
                    require_point_id_equals_dense_index=require_point_id_equals_dense_index,
                )
            else:
                selected_mapping = {"checked_count": 0, "failure_count": 0, "failures": []}
                exact_mapping = {"checked_count": 0, "failure_count": 0, "failures": []}

            determinism: dict[str, Any] | None = None
            if not bool(selected_comparison["exact_same_order"]):
                for _ in range(max(0, warmup_runs)):
                    selected_backend.search(request)

                repeated_rows: list[list[dict[str, Any]]] = []
                for _ in range(max(1, repeated_runs)):
                    repeat_result = selected_backend.search(request)
                    repeated_rows.append(
                        qdrant_backend_result_to_rows(
                            repeat_result
                        )
                    )

                determinism = check_repeat_determinism(
                    repeated_runs=repeated_rows,
                    top_k=internal_top_k,
                )

            selected_classification = classify_profile_difference(
                comparison=selected_comparison,
                exact_comparison=exact_comparison,
                mapping_audit=selected_mapping,
                determinism=determinism,
                is_exact_profile=False,
            )
            exact_classification = classify_profile_difference(
                comparison=exact_comparison,
                exact_comparison=exact_comparison,
                mapping_audit=exact_mapping,
                determinism=None,
                is_exact_profile=True,
            )

            selected_result = {
                "query_id": query_id,
                "profile": dict(selected_profile),
                "latency_ms": selected_latency_ms,
                "returned_count": len(selected_rows),
                "comparison": selected_comparison,
                "mismatch_details": build_mismatch_details(
                    comparison=selected_comparison,
                    reference_rows=file_rows,
                    candidate_rows=selected_rows,
                ),
                "mapping_audit": selected_mapping,
                "determinism": determinism,
                "classification": selected_classification,
                "results": selected_rows,
            }
            exact_result = {
                "query_id": query_id,
                "profile": dict(exact_profile),
                "latency_ms": exact_latency_ms,
                "returned_count": len(exact_rows),
                "comparison": exact_comparison,
                "mismatch_details": build_mismatch_details(
                    comparison=exact_comparison,
                    reference_rows=file_rows,
                    candidate_rows=exact_rows,
                ),
                "mapping_audit": exact_mapping,
                "determinism": None,
                "classification": exact_classification,
                "results": exact_rows,
            }

            query_results.append(
                {
                    "query_id": query_id,
                    "query": query_text,
                    "group": row.get("group"),
                    "query_vector": vector_meta,
                    "file_reference": {
                        "semantics": {
                            "query_normalization": (
                                "SentenceTransformer normalize_embeddings=True once"
                            ),
                            "query_dtype": "float32",
                            "stored_embeddings": "used_as_saved",
                            "score": "embeddings @ query_vector",
                            "ordering": "np.argsort(scores)[::-1]",
                        },
                        "latency_ms": file_latency_ms,
                        "returned_count": len(file_rows),
                        "results": file_rows,
                    },
                    "selected_profile": selected_result,
                    "exact_profile": exact_result,
                }
            )
            file_latencies.append(file_latency_ms)
            selected_latencies.append(selected_latency_ms)
            exact_latencies.append(exact_latency_ms)
        except Exception as exc:  # noqa: BLE001 - report all query failures
            errors.append(
                {
                    "query_id": query_id,
                    "query": row.get("query"),
                    "error": repr(exc),
                }
            )

    selected_summary = profile_summary(
        profile=selected_profile,
        query_results=query_results,
        result_key="selected_profile",
    )
    exact_summary = profile_summary(
        profile=exact_profile,
        query_results=query_results,
        result_key="exact_profile",
    )

    mismatch_queries: list[dict[str, Any]] = []
    blocking_classifications: list[dict[str, Any]] = []
    for row in query_results:
        selected_result = row["selected_profile"]
        classification = selected_result["classification"]
        if not selected_result["comparison"]["exact_same_order"]:
            mismatch_queries.append(
                {
                    "query_id": row["query_id"],
                    "query": row["query"],
                    "classification": classification["classification"],
                    "severity": classification["severity"],
                    "overlap_ratio": selected_result["comparison"]["overlap_ratio"],
                    "best_missed_reference_rank": selected_result["mismatch_details"].get(
                        "best_missed_reference_rank"
                    ),
                    "reference_only": selected_result["comparison"]["reference_only"],
                    "candidate_only": selected_result["comparison"]["candidate_only"],
                }
            )
        for result_key in ("selected_profile", "exact_profile"):
            result = row[result_key]
            if result["classification"].get("severity") == "blocking":
                blocking_classifications.append(
                    {
                        "query_id": row["query_id"],
                        "profile_role": result_key,
                        **result["classification"],
                    }
                )

    query_count = len(query_results)
    selected_full_match = (
        query_count > 0
        and selected_summary["exact_same_order_count"] == query_count
        and selected_summary["mismatch_count"] == 0
    )
    exact_full_match = (
        query_count > 0
        and exact_summary["exact_same_order_count"] == query_count
        and exact_summary["mismatch_count"] == 0
    )

    summary = {
        "build_id": manifest.get("build_id"),
        "corpus_doc_count": manifest.get("corpus_doc_count"),
        "embedding_model_name": manifest.get("embedding_model_name"),
        "embedding_shape": list(embeddings.shape),
        "collection_name": collection_name,
        "external_top_k": external_top_k,
        "boundary_window": boundary_window,
        "internal_top_k": internal_top_k,
        "enabled_queries_count": len(queries),
        "query_count": query_count,
        "error_count": len(errors),
        "selected_profile_name": selected_profile_name,
        "exact_profile_name": exact_profile_name,
        "selected_profile_full_match": selected_full_match,
        "exact_profile_full_match": exact_full_match,
        "blocking_classification_count": len(blocking_classifications),
    }

    quality_policy = {
        "max_error_count": int(quality_cfg.get("max_error_count", 0)),
        "require_selected_profile_full_match": bool(
            quality_cfg.get("require_selected_profile_full_match", True)
        ),
        "require_exact_profile_full_match": bool(
            quality_cfg.get("require_exact_profile_full_match", True)
        ),
        "min_mean_overlap_at_k": float(
            quality_cfg.get("min_mean_overlap_at_k", 0.99)
        ),
        "min_query_overlap_at_k": float(
            quality_cfg.get("min_query_overlap_at_k", 0.95)
        ),
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_iso(),
        "run_ts": run_ts,
        "config_path": normalize_path(args.config_path),
        "config": config,
        "inputs": {
            "manifest_path": normalize_path(manifest_path),
            "golden_queries_path": normalize_path(golden_queries_path),
            "dense_embeddings_path": normalize_path(embeddings_path),
            "dense_ids_path": normalize_path(ids_path),
            "dense_meta_path": normalize_path(meta_path),
        },
        "summary": summary,
        "quality_policy": quality_policy,
        "collection": collection,
        "dense_meta": dense_meta,
        "selected_profile_summary": selected_summary,
        "exact_profile_summary": exact_summary,
        "latency_summary": {
            "file_reference": summarize_latencies(file_latencies),
            "selected_profile": summarize_latencies(selected_latencies),
            "exact_profile": summarize_latencies(exact_latencies),
        },
        "mismatch_queries": mismatch_queries,
        "blocking_classifications": blocking_classifications,
        "query_results": query_results,
        "errors": errors,
        "verdict": {
            "ok": (
                len(errors) == 0
                and exact_full_match
                and len(blocking_classifications) == 0
                and (
                    selected_full_match
                    or not quality_policy["require_selected_profile_full_match"]
                )
            ),
            "error_count": len(errors),
        },
    }

    output_dir = Path(
        args.output_dir
        or output_cfg.get("output_dir")
        or DEFAULT_OUTPUT_DIR
    )
    latest_json = output_dir / "qdrant_file_dense_comparison_latest.json"
    latest_md = output_dir / "qdrant_file_dense_comparison_latest.md"
    history_json = output_dir / "history" / f"qdrant_file_dense_comparison_{run_ts}.json"
    history_md = output_dir / "history" / f"qdrant_file_dense_comparison_{run_ts}.md"

    dump_json(latest_json, report)
    dump_json(history_json, report)
    markdown = build_markdown(report)
    dump_text(latest_md, markdown)
    dump_text(history_md, markdown)

    print()
    print(f"[OK] schema_version={SCHEMA_VERSION}")
    print(f"[OK] build_id={summary['build_id']}")
    print(f"[OK] collection_name={collection_name}")
    print(f"[OK] enabled_queries_count={len(queries)}")
    print(f"[OK] query_count={query_count}")
    print(f"[OK] error_count={len(errors)}")
    print(f"[OK] selected_profile_name={selected_profile_name}")
    print(f"[OK] selected_profile_full_match={selected_full_match}")
    print(f"[OK] exact_profile_name={exact_profile_name}")
    print(f"[OK] exact_profile_full_match={exact_full_match}")
    print(f"[OK] blocking_classification_count={len(blocking_classifications)}")
    print(
        "[OK] selected_mean_overlap_at_k="
        f"{selected_summary['mean_overlap_at_k']}"
    )
    print(
        "[OK] selected_min_overlap_at_k="
        f"{selected_summary['min_overlap_at_k']}"
    )
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")


if __name__ == "__main__":
    main()
