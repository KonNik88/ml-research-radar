"""Compare existing Qdrant dense retrieval against file-based dense retrieval.

This script is intentionally read-only with respect to Qdrant: it does not
create collections and does not upload vectors. Use the full benchmark first:

    python -m scripts.evaluation.run_qdrant_retrieval_benchmark

Then use this script for fast Qdrant-vs-file-dense parity checks.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from sentence_transformers import SentenceTransformer

from radar_core.retrieval.qdrant_store import QdrantRetrievalStore

SCHEMA_VERSION = "qdrant_file_dense_comparison_v1"
DEFAULT_CONFIG_PATH = Path("configs/qdrant_benchmark_v1.yaml")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/evaluation")


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"JSONL row {line_no} is not an object: {path}")
        rows.append(row)
    return rows


def enabled_queries(path: Path) -> list[dict[str, Any]]:
    return [row for row in read_jsonl(path) if row.get("enabled") is True]


def normalize_vector(vector: np.ndarray) -> np.ndarray:
    vector = vector.astype("float32", copy=False)
    norm = float(np.linalg.norm(vector))
    if norm == 0.0 or not math.isfinite(norm):
        return vector
    return vector / norm


def normalize_matrix(matrix: np.ndarray) -> np.ndarray:
    matrix = matrix.astype("float32", copy=False)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def file_dense_search(
    *,
    query_vector: np.ndarray,
    embeddings_norm: np.ndarray,
    ids: list[str],
    top_k: int,
) -> list[dict[str, Any]]:
    scores = embeddings_norm @ query_vector.astype("float32")
    if top_k >= scores.shape[0]:
        top_indices = np.argsort(-scores)
    else:
        candidate = np.argpartition(-scores, top_k - 1)[:top_k]
        top_indices = candidate[np.argsort(-scores[candidate])]

    results: list[dict[str, Any]] = []
    for idx in top_indices[:top_k]:
        dense_index = int(idx)
        results.append(
            {
                "dense_index": dense_index,
                "canonical_id": ids[dense_index],
                "score": round(float(scores[dense_index]), 8),
            }
        )
    return results


def overlap_at_k(left_ids: list[str], right_ids: list[str], top_k: int) -> dict[str, Any]:
    left = left_ids[:top_k]
    right = right_ids[:top_k]
    overlap_count = len(set(left) & set(right))
    denom = max(1, min(top_k, len(left), len(right)))
    return {
        "overlap_count_at_k": overlap_count,
        "overlap_ratio_at_k": round(overlap_count / denom, 6),
        "exact_same_order": left == right,
    }


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return round(float(np.percentile(np.asarray(values, dtype="float64"), q)), 3)


def summarize_latency(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "mean_ms": round(float(np.mean(values)), 3) if values else None,
        "p50_ms": percentile(values, 50),
        "p95_ms": percentile(values, 95),
        "max_ms": round(max(values), 3) if values else None,
    }


def build_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    overlap = report["overlap_summary"]
    latency = report["latency_summary"]
    verdict = report["verdict"]
    lines = [
        "# Qdrant vs File Dense Comparison",
        "",
        f"- schema_version: `{report['schema_version']}`",
        f"- build_id: `{summary.get('build_id')}`",
        f"- collection_name: `{summary.get('collection_name')}`",
        f"- query_count: `{summary.get('query_count')}`",
        f"- error_count: `{summary.get('error_count')}`",
        f"- ok: `{verdict.get('ok')}`",
        "",
        "## Overlap",
        "",
        f"- mean_overlap_ratio_at_k: `{overlap.get('mean_overlap_ratio_at_k')}`",
        f"- min_overlap_ratio_at_k: `{overlap.get('min_overlap_ratio_at_k')}`",
        f"- exact_same_order_count: `{overlap.get('exact_same_order_count')}`",
        f"- queries_count: `{overlap.get('queries_count')}`",
        "",
        "## Latency",
        "",
        f"- qdrant: `{latency.get('qdrant')}`",
        f"- file_dense: `{latency.get('file_dense')}`",
        "",
        "## Worst overlap queries",
        "",
    ]
    for row in report.get("worst_overlap_queries", [])[:10]:
        lines.append(
            f"- `{row.get('query_id')}`: overlap={row.get('overlap_ratio_at_k')} "
            f"exact_same_order={row.get('exact_same_order')}"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--max-queries", type=int, default=None)
    args = parser.parse_args(argv)

    run_ts = utc_ts()
    config = load_yaml(args.config_path)
    retrieval_cfg = config.get("retrieval", {})
    qdrant_cfg = config.get("qdrant", {})

    manifest_path = Path(retrieval_cfg.get("manifest_path", "artifacts/retrieval/manifests/latest.json"))
    golden_queries_path = Path(retrieval_cfg.get("golden_queries_path", "data/eval/retrieval/golden_queries.jsonl"))
    top_k = int(args.top_k or retrieval_cfg.get("top_k", retrieval_cfg.get("query_top_k", 20)))

    manifest = load_json(manifest_path)
    embeddings_path = Path(manifest["dense_embeddings_path"])
    ids_path = Path(manifest["dense_ids_path"])
    ids = load_json(ids_path)
    embeddings = np.load(embeddings_path)

    if len(ids) != int(embeddings.shape[0]):
        raise ValueError(f"dense ids count {len(ids)} != embeddings rows {embeddings.shape[0]}")

    embeddings_norm = normalize_matrix(embeddings)
    queries = enabled_queries(golden_queries_path)
    if args.max_queries is not None:
        queries = queries[: args.max_queries]

    model = SentenceTransformer(str(manifest["embedding_model_name"]))
    store = QdrantRetrievalStore(
        host=str(qdrant_cfg.get("host", "localhost")),
        port=int(qdrant_cfg.get("port", 6333)),
        collection_name=str(qdrant_cfg.get("collection_name", "ml_radar_dense_benchmark_v1")),
        timeout_sec=int(qdrant_cfg.get("timeout_sec", 120)),
        check_compatibility=bool(qdrant_cfg.get("check_compatibility", False)),
    )

    query_results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    qdrant_latencies: list[float] = []
    file_latencies: list[float] = []
    overlaps: list[float] = []
    exact_same_order_count = 0

    for row in queries:
        query_id = str(row.get("query_id"))
        query_text = str(row.get("query", "")).strip()
        if not query_text:
            errors.append({"query_id": query_id, "error": "empty query text"})
            continue

        try:
            query_vector = model.encode(query_text, normalize_embeddings=True)
            query_vector = normalize_vector(np.asarray(query_vector, dtype="float32"))

            t0 = time.perf_counter()
            qdrant_results_raw = store.search_vector(query_vector.tolist(), top_k=top_k)
            qdrant_latency_ms = (time.perf_counter() - t0) * 1000.0

            t1 = time.perf_counter()
            file_results = file_dense_search(
                query_vector=query_vector,
                embeddings_norm=embeddings_norm,
                ids=ids,
                top_k=top_k,
            )
            file_latency_ms = (time.perf_counter() - t1) * 1000.0

            qdrant_results = [result.to_dict() for result in qdrant_results_raw]
            qdrant_ids = [str(result.get("canonical_id")) for result in qdrant_results if result.get("canonical_id")]
            file_ids = [str(result.get("canonical_id")) for result in file_results if result.get("canonical_id")]
            overlap = overlap_at_k(qdrant_ids, file_ids, top_k=top_k)

            qdrant_latencies.append(qdrant_latency_ms)
            file_latencies.append(file_latency_ms)
            overlaps.append(float(overlap["overlap_ratio_at_k"]))
            if overlap["exact_same_order"]:
                exact_same_order_count += 1

            query_results.append(
                {
                    "query_id": query_id,
                    "query": query_text,
                    "group": row.get("group"),
                    "qdrant_latency_ms": round(qdrant_latency_ms, 3),
                    "file_dense_latency_ms": round(file_latency_ms, 3),
                    "qdrant_returned_count": len(qdrant_results),
                    "file_dense_returned_count": len(file_results),
                    "overlap": overlap,
                    "qdrant_results": qdrant_results,
                    "file_dense_results": file_results,
                }
            )
        except Exception as exc:  # noqa: BLE001 - benchmark should report all query failures
            errors.append({"query_id": query_id, "query": query_text, "error": repr(exc)})

    overlap_summary = {
        "queries_count": len(query_results),
        "mean_overlap_ratio_at_k": round(float(np.mean(overlaps)), 6) if overlaps else None,
        "min_overlap_ratio_at_k": round(float(np.min(overlaps)), 6) if overlaps else None,
        "exact_same_order_count": exact_same_order_count,
    }
    latency_summary = {
        "qdrant": summarize_latency(qdrant_latencies),
        "file_dense": summarize_latency(file_latencies),
    }
    worst_overlap_queries = sorted(
        [
            {
                "query_id": row["query_id"],
                "query": row["query"],
                "overlap_ratio_at_k": row["overlap"]["overlap_ratio_at_k"],
                "exact_same_order": row["overlap"]["exact_same_order"],
            }
            for row in query_results
        ],
        key=lambda item: (item["overlap_ratio_at_k"], item["query_id"]),
    )[:10]

    summary = {
        "build_id": manifest.get("build_id"),
        "corpus_doc_count": manifest.get("corpus_doc_count"),
        "embedding_model_name": manifest.get("embedding_model_name"),
        "collection_name": store.collection_name,
        "top_k": top_k,
        "enabled_queries_count": len(queries),
        "query_count": len(query_results),
        "error_count": len(errors),
    }
    verdict = {
        "ok": len(errors) == 0,
        "error_count": len(errors),
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_ts": run_ts,
        "config_path": str(args.config_path),
        "inputs": {
            "manifest_path": str(manifest_path),
            "golden_queries_path": str(golden_queries_path),
            "dense_embeddings_path": str(embeddings_path),
            "dense_ids_path": str(ids_path),
        },
        "summary": summary,
        "overlap_summary": overlap_summary,
        "latency_summary": latency_summary,
        "worst_overlap_queries": worst_overlap_queries,
        "query_results": query_results,
        "errors": errors,
        "verdict": verdict,
    }

    latest_json = args.output_dir / "qdrant_file_dense_comparison_latest.json"
    latest_md = args.output_dir / "qdrant_file_dense_comparison_latest.md"
    history_json = args.output_dir / "history" / f"qdrant_file_dense_comparison_{run_ts}.json"
    history_md = args.output_dir / "history" / f"qdrant_file_dense_comparison_{run_ts}.md"

    dump_json(latest_json, report)
    dump_json(history_json, report)
    markdown = build_markdown(report)
    dump_text(latest_md, markdown)
    dump_text(history_md, markdown)

    print(f"[OK] schema_version={SCHEMA_VERSION}")
    print(f"[OK] build_id={manifest.get('build_id')}")
    print(f"[OK] collection_name={store.collection_name}")
    print(f"[OK] enabled_queries_count={len(queries)}")
    print(f"[OK] query_count={len(query_results)}")
    print(f"[OK] error_count={len(errors)}")
    print(f"[OK] mean_overlap_ratio_at_k={overlap_summary['mean_overlap_ratio_at_k']}")
    print(f"[OK] min_overlap_ratio_at_k={overlap_summary['min_overlap_ratio_at_k']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")


if __name__ == "__main__":
    main()
