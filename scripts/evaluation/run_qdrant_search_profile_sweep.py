"""Evaluate Qdrant search profiles against the exact file-dense reference.

This script is read-only with respect to Qdrant. It does not create collections,
upload vectors, mutate canonical data, or change API defaults.

Run from the project root:

    python -m scripts.evaluation.run_qdrant_search_profile_sweep
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
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


SCHEMA_VERSION = "qdrant_search_profile_sweep_v1"
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
    exact_count = 0

    for index, raw in enumerate(raw_profiles):
        if not isinstance(raw, dict):
            raise ValueError(f"profiles[{index}] must be a mapping")

        name = str(raw.get("name") or "").strip()
        if not name:
            raise ValueError(f"profiles[{index}].name is required")
        if name in names:
            raise ValueError(f"Duplicate profile name: {name}")
        names.add(name)

        exact = bool(raw.get("exact", False))
        hnsw_ef = raw.get("hnsw_ef")
        if hnsw_ef is not None:
            hnsw_ef = int(hnsw_ef)
            if hnsw_ef <= 0:
                raise ValueError(f"Profile {name}: hnsw_ef must be positive")
        if exact:
            exact_count += 1

        profiles.append(
            {
                "name": name,
                "exact": exact,
                "hnsw_ef": hnsw_ef,
            }
        )

    if exact_count != 1:
        raise ValueError(f"Exactly one exact profile is required, found {exact_count}")

    return profiles

def collection_summary(
    store: QdrantRetrievalStore,
) -> dict[str, Any]:
    """Return the existing sweep-report collection shape."""

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


def profile_summary(
    *,
    profile: Mapping[str, Any],
    query_results: list[dict[str, Any]],
) -> dict[str, Any]:
    name = str(profile["name"])
    rows = [row["profiles"][name] for row in query_results if name in row.get("profiles", {})]

    overlaps = [float(row["comparison"]["overlap_ratio"]) for row in rows]
    exact_count = sum(bool(row["comparison"]["exact_same_order"]) for row in rows)
    mismatch_rows = [row for row in rows if not row["comparison"]["exact_same_order"]]
    mapping_failure_count = sum(int(row["mapping_audit"]["failure_count"]) for row in rows)
    classification_counts = Counter(
        str(row["classification"]["classification"]) for row in rows
    )

    missed_ranks = [
        row["mismatch_details"].get("best_missed_reference_rank")
        for row in mismatch_rows
        if isinstance(row["mismatch_details"].get("best_missed_reference_rank"), int)
    ]

    latencies = [float(row["latency_ms"]) for row in rows]

    return {
        "profile": dict(profile),
        "query_count": len(rows),
        "mean_overlap_at_k": float(np.mean(overlaps)) if overlaps else None,
        "min_overlap_at_k": min(overlaps) if overlaps else None,
        "exact_same_order_count": exact_count,
        "mismatch_count": len(mismatch_rows),
        "mismatch_query_ids": [row["query_id"] for row in mismatch_rows],
        "best_missed_reference_rank": min(missed_ranks) if missed_ranks else None,
        "mapping_failure_count": mapping_failure_count,
        "classification_counts": dict(sorted(classification_counts.items())),
        "latency": summarize_latencies(latencies),
    }


def build_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Qdrant Search Profile Sweep",
        "",
        f"- schema_version: `{report['schema_version']}`",
        f"- generated_at_utc: `{report['generated_at_utc']}`",
        f"- build_id: `{summary.get('build_id')}`",
        f"- collection_name: `{summary.get('collection_name')}`",
        f"- query_count: `{summary.get('query_count')}`",
        f"- error_count: `{summary.get('error_count')}`",
        f"- exact_profile_name: `{summary.get('exact_profile_name')}`",
        f"- exact_profile_full_match: `{summary.get('exact_profile_full_match')}`",
        "",
        "## Profiles",
        "",
        "| profile | exact | hnsw_ef | mean overlap | min overlap | exact order | mismatches | best missed rank | p50 ms | p95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for row in report.get("profile_summaries", []):
        profile = row["profile"]
        latency = row["latency"]
        lines.append(
            "| {name} | {exact} | {ef} | {mean} | {minimum} | {exact_count}/{queries} | "
            "{mismatches} | {missed_rank} | {p50} | {p95} |".format(
                name=profile.get("name"),
                exact=profile.get("exact"),
                ef=profile.get("hnsw_ef"),
                mean=row.get("mean_overlap_at_k"),
                minimum=row.get("min_overlap_at_k"),
                exact_count=row.get("exact_same_order_count"),
                queries=row.get("query_count"),
                mismatches=row.get("mismatch_count"),
                missed_rank=row.get("best_missed_reference_rank"),
                p50=latency.get("p50_ms"),
                p95=latency.get("p95_ms"),
            )
        )

    mismatches = report.get("mismatch_queries", [])
    if mismatches:
        lines.extend(["", "## Mismatch queries", ""])
        for row in mismatches:
            lines.append(
                f"- `{row['query_id']}` / `{row['profile_name']}`: "
                f"classification=`{row['classification']}`, "
                f"overlap=`{row['overlap_ratio']}`, "
                f"best_missed_reference_rank=`{row.get('best_missed_reference_rank')}`"
            )

    errors = report.get("errors", [])
    if errors:
        lines.extend(["", "## Errors", ""])
        for error in errors:
            lines.append(f"- `{error}`")

    lines.append("")
    return "\n".join(lines)


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
    diagnostics_cfg = config.get("diagnostics") or {}
    quality_cfg = config.get("quality") or {}
    output_cfg = config.get("output") or {}
    profiles = validate_profiles(config.get("profiles"))
    exact_profile = next(profile for profile in profiles if profile["exact"])
    exact_profile_name = str(exact_profile["name"])

    external_top_k = int(retrieval_cfg.get("external_top_k", 20))
    boundary_window = int(retrieval_cfg.get("boundary_window", 10))
    if external_top_k <= 0:
        raise ValueError("external_top_k must be positive")
    if boundary_window < 0:
        raise ValueError("boundary_window must be non-negative")
    internal_top_k = external_top_k + boundary_window

    warmup_runs = int(diagnostics_cfg.get("warmup_runs", 1))
    repeated_runs = int(diagnostics_cfg.get("repeated_runs", 5))
    repeat_only_mismatches = bool(diagnostics_cfg.get("repeat_only_mismatches", True))
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
        raise RuntimeError(
            "Exact file reference requires dense metadata normalized=true; "
            "refusing to silently change semantics"
        )

    embeddings = np.load(embeddings_path, mmap_mode="r")
    ids = load_ids(ids_path)
    if len(ids) != int(embeddings.shape[0]):
        raise ValueError(f"dense ids count {len(ids)} != embeddings rows {embeddings.shape[0]}")

    queries = enabled_queries(golden_queries_path)
    if args.max_queries is not None:
        if args.max_queries <= 0:
            raise ValueError("--max-queries must be positive")
        queries = queries[: args.max_queries]

    model_name = str(manifest["embedding_model_name"])
    model = SentenceTransformer(model_name)

    if bool(qdrant_cfg.get("prefer_grpc", False)):
        raise ValueError(
            "run_qdrant_search_profile_sweep does not support "
            "prefer_grpc=true through QdrantRetrievalStore"
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
        normalized=bool(dense_meta.get("normalized")),
    )

    profile_backends: dict[str, QdrantDenseBackend] = {}

    for profile in profiles:
        profile_name = str(profile["name"])

        qdrant_profile = QdrantSearchProfile(
            name=profile_name,
            exact=bool(profile["exact"]),
            hnsw_ef=profile.get("hnsw_ef"),
        )

        profile_backends[profile_name] = QdrantDenseBackend(
            store=store,
            profile=qdrant_profile,
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

    try:
        for query_index, query_row in enumerate(queries, start=1):
            query_id = str(query_row.get("query_id") or f"query_{query_index}")
            query_text = resolve_query_text(query_row)
            print(f"[{query_index}/{len(queries)}] {query_id}: {query_text}")

            try:
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
                reference_rows = file_backend_result_to_rows(
                    file_backend_result
                )
                file_latency_ms = float(
                    file_backend_result.timing_ms.get(
                        "backend_search_ms",
                        0.0,
                    )
                )

                profile_payloads: dict[str, dict[str, Any]] = {}

                for profile in profiles:
                    profile_name = str(profile["name"])
                    backend = profile_backends[profile_name]

                    backend_result = backend.search(request)
                    rows = qdrant_backend_result_to_rows(
                        backend_result
                    )
                    latency_ms = float(
                        backend_result.timing_ms.get(
                            "backend_search_ms",
                            0.0,
                        )
                    )
                    comparison = compare_ranked_results(
                        reference_rows=reference_rows,
                        candidate_rows=rows,
                        top_k=external_top_k,
                    )
                    mismatch_details = build_mismatch_details(
                        comparison=comparison,
                        reference_rows=reference_rows,
                        candidate_rows=rows,
                    )
                    mapping = (
                        audit_qdrant_mapping(
                            rows=rows,
                            ids=ids,
                            expected_build_id=str(manifest["build_id"]),
                            require_point_id_equals_dense_index=(
                                require_point_id_equals_dense_index
                            ),
                        )
                        if audit_mapping
                        else {
                            "checked_count": 0,
                            "failure_count": 0,
                            "reason_counts": {},
                            "failures": [],
                        }
                    )

                    profile_payloads[profile_name] = {
                        "query_id": query_id,
                        "profile": dict(profile),
                        "latency_ms": latency_ms,
                        "returned_count": len(rows),
                        "comparison": comparison,
                        "mismatch_details": mismatch_details,
                        "mapping_audit": mapping,
                        "determinism": None,
                        "classification": None,
                        "results": rows,
                    }

                exact_comparison = profile_payloads[exact_profile_name]["comparison"]

                for profile in profiles:
                    name = str(profile["name"])
                    payload = profile_payloads[name]
                    mismatch = not bool(payload["comparison"]["exact_same_order"])
                    should_repeat = repeated_runs > 0 and (
                        mismatch or not repeat_only_mismatches
                    )

                    determinism: dict[str, Any] | None = None
                    if should_repeat:
                        backend = profile_backends[name]

                        for _ in range(max(0, warmup_runs)):
                            backend.search(request)

                        recorded: list[list[dict[str, Any]]] = []
                        repeat_latencies: list[float] = []

                        for _ in range(repeated_runs):
                            repeat_result = backend.search(request)
                            repeat_rows = qdrant_backend_result_to_rows(
                                repeat_result
                            )
                            repeat_latency = float(
                                repeat_result.timing_ms.get(
                                    "backend_search_ms",
                                    0.0,
                                )
                            )

                            recorded.append(repeat_rows)
                            repeat_latencies.append(repeat_latency)

                        determinism = check_repeat_determinism(
                            repeated_runs=recorded,
                            top_k=internal_top_k,
                        )
                        determinism["warmup_runs"] = max(0, warmup_runs)
                        determinism["latency"] = summarize_latencies(repeat_latencies)

                    payload["determinism"] = determinism
                    payload["classification"] = classify_profile_difference(
                        comparison=payload["comparison"],
                        exact_comparison=exact_comparison,
                        mapping_audit=payload["mapping_audit"],
                        determinism=determinism,
                        is_exact_profile=bool(profile["exact"]),
                    )

                query_results.append(
                    {
                        "query_id": query_id,
                        "query": query_text,
                        "group": query_row.get("group"),
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
                            "returned_count": len(reference_rows),
                            "results": reference_rows,
                        },
                        "profiles": profile_payloads,
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "query_id": query_id,
                        "query": query_text,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
                print(f"[ERROR] {query_id}: {type(exc).__name__}: {exc}")
    finally:
        close = getattr(store.client, "close", None)
        if callable(close):
            close()

    profile_summaries = [
        profile_summary(profile=profile, query_results=query_results)
        for profile in profiles
    ]
    summary_by_name = {
        row["profile"]["name"]: row for row in profile_summaries
    }
    exact_summary = summary_by_name[exact_profile_name]
    exact_profile_full_match = (
        exact_summary["query_count"] == len(queries)
        and exact_summary["mismatch_count"] == 0
        and exact_summary["mapping_failure_count"] == 0
        and exact_summary["mean_overlap_at_k"] == 1.0
        and exact_summary["min_overlap_at_k"] == 1.0
    )

    mismatch_queries: list[dict[str, Any]] = []
    for query_result in query_results:
        for profile_name, payload in query_result["profiles"].items():
            if payload["comparison"]["exact_same_order"]:
                continue
            mismatch_queries.append(
                {
                    "query_id": query_result["query_id"],
                    "query": query_result["query"],
                    "profile_name": profile_name,
                    "overlap_ratio": payload["comparison"]["overlap_ratio"],
                    "classification": payload["classification"]["classification"],
                    "severity": payload["classification"]["severity"],
                    "best_missed_reference_rank": payload["mismatch_details"].get(
                        "best_missed_reference_rank"
                    ),
                    "reference_only": payload["comparison"]["reference_only"],
                    "candidate_only": payload["comparison"]["candidate_only"],
                }
            )

    max_error_count = int(quality_cfg.get("max_error_count", 0))
    require_exact_full_match = bool(
        quality_cfg.get("require_exact_profile_full_match", True)
    )
    verdict_ok = len(errors) <= max_error_count and (
        exact_profile_full_match or not require_exact_full_match
    )

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
        "summary": {
            "build_id": manifest.get("build_id"),
            "corpus_doc_count": manifest.get("corpus_doc_count"),
            "embedding_model_name": model_name,
            "embedding_shape": list(embeddings.shape),
            "collection_name": collection_name,
            "external_top_k": external_top_k,
            "boundary_window": boundary_window,
            "internal_top_k": internal_top_k,
            "enabled_queries_count": len(queries),
            "query_count": len(query_results),
            "error_count": len(errors),
            "exact_profile_name": exact_profile_name,
            "exact_profile_full_match": exact_profile_full_match,
        },
        "collection": collection,
        "dense_meta": dense_meta,
        "profile_summaries": profile_summaries,
        "mismatch_queries": mismatch_queries,
        "query_results": query_results,
        "errors": errors,
        "verdict": {
            "ok": verdict_ok,
            "max_error_count": max_error_count,
            "require_exact_profile_full_match": require_exact_full_match,
        },
    }

    output_dir = args.output_dir or Path(
        output_cfg.get("output_dir", DEFAULT_OUTPUT_DIR)
    )
    latest_json = output_dir / "qdrant_search_profile_sweep_latest.json"
    latest_md = output_dir / "qdrant_search_profile_sweep_latest.md"
    history_json = (
        output_dir / "history" / f"qdrant_search_profile_sweep_{run_ts}.json"
    )
    history_md = (
        output_dir / "history" / f"qdrant_search_profile_sweep_{run_ts}.md"
    )

    markdown = build_markdown(report)
    dump_json(latest_json, report)
    dump_text(latest_md, markdown)
    dump_json(history_json, report)
    dump_text(history_md, markdown)

    print()
    print(f"[OK] schema_version={SCHEMA_VERSION}")
    print(f"[OK] build_id={manifest.get('build_id')}")
    print(f"[OK] collection_name={collection_name}")
    print(f"[OK] query_count={len(query_results)}")
    print(f"[OK] error_count={len(errors)}")
    print(f"[OK] exact_profile_name={exact_profile_name}")
    print(f"[OK] exact_profile_full_match={exact_profile_full_match}")
    for row in profile_summaries:
        print(
            "[PROFILE] {name}: mean_overlap={mean:.6f} min_overlap={minimum:.6f} "
            "exact={exact_count}/{count} mismatches={mismatches} p50_ms={p50:.3f} "
            "p95_ms={p95:.3f}".format(
                name=row["profile"]["name"],
                mean=float(row["mean_overlap_at_k"] or 0.0),
                minimum=float(row["min_overlap_at_k"] or 0.0),
                exact_count=row["exact_same_order_count"],
                count=row["query_count"],
                mismatches=row["mismatch_count"],
                p50=float(row["latency"]["p50_ms"] or 0.0),
                p95=float(row["latency"]["p95_ms"] or 0.0),
            )
        )
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")



if __name__ == "__main__":
    main()
