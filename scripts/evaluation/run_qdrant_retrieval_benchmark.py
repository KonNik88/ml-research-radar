from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sentence_transformers import SentenceTransformer
from services.api.settings import get_settings

DEFAULT_CONFIG_PATH = Path("configs/qdrant_benchmark_v1.yaml")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/evaluation")
SCHEMA_VERSION = "qdrant_retrieval_benchmark_v1"


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def normalize_path(path: str | Path | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def to_path(value: str | Path) -> Path:
    return Path(str(value).replace("\\", "/"))


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected mapping in config: {path}")
    return payload


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if isinstance(item, dict):
                rows.append(item)
    return rows


def load_ids(path: Path) -> list[str]:
    payload = load_json(path)
    if isinstance(payload, list):
        return [str(x) for x in payload]
    if isinstance(payload, dict):
        for key in ("ids", "canonical_ids", "document_ids"):
            values = payload.get(key)
            if isinstance(values, list):
                return [str(x) for x in values]
    raise ValueError(f"Unsupported dense ids JSON shape: {path}")


def enabled_golden_queries(path: Path) -> list[dict[str, Any]]:
    return [row for row in load_jsonl(path) if row.get("enabled") is True]


def load_canonical_docs(path: Path) -> dict[str, dict[str, Any]]:
    docs: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return docs
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            cid = row.get("canonical_id")
            if cid:
                docs[str(cid)] = row
    return docs


def text_blob(doc: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in (
        "title",
        "abstract",
        "authors",
        "categories",
        "concepts",
        "keywords",
        "tags",
        "primary_category",
        "venue",
        "journal",
        "conference",
        "publisher",
        "publication_type",
    ):
        value = doc.get(field)
        if value is None:
            continue
        if isinstance(value, list):
            parts.extend(str(x) for x in value if x is not None)
        else:
            parts.append(str(value))
    return " ".join(parts).lower()


def explicit_relevance_ids(query_case: dict[str, Any]) -> set[str]:
    expected = query_case.get("expected") or {}
    ids: set[str] = set()
    for cid in expected.get("canonical_ids") or []:
        if cid:
            ids.add(str(cid))
    for item in query_case.get("graded_relevance") or []:
        if not isinstance(item, dict):
            continue
        cid = item.get("canonical_id")
        grade = item.get("grade")
        try:
            grade_int = int(grade) if grade is not None else 0
        except Exception:
            grade_int = 0
        if cid and grade_int > 0:
            ids.add(str(cid))
    return ids


def doc_matches_weak_patterns(query_case: dict[str, Any], doc: dict[str, Any]) -> bool:
    expected = query_case.get("expected") or {}
    title = str(doc.get("title") or "").lower()
    blob = text_blob(doc)

    title_terms: list[str] = []
    for key in ("title_substrings", "title_any_substrings"):
        value = expected.get(key) or []
        if isinstance(value, str):
            title_terms.append(value)
        elif isinstance(value, list):
            title_terms.extend(str(x) for x in value if x)

    if title_terms and any(term.lower() in title for term in title_terms):
        return True

    must_terms = expected.get("must_have_any_terms") or []
    if isinstance(must_terms, str):
        must_terms = [must_terms]
    if isinstance(must_terms, list) and must_terms:
        return any(str(term).lower() in blob for term in must_terms if term)

    return False


def is_relevant(query_case: dict[str, Any], canonical_id: str, docs: dict[str, dict[str, Any]]) -> bool:
    explicit_ids = explicit_relevance_ids(query_case)
    if explicit_ids:
        # Explicit golden cases must be evaluated only against the curated canonical_id set.
        # Weak title/term hints may exist in the same row, but they are retrieval hints/sanity
        # signals, not additional relevance labels. Counting them here inflates relevant_found
        # and can make nDCG > 1.0.
        return canonical_id in explicit_ids

    doc = docs.get(canonical_id)
    if not doc:
        return False
    return doc_matches_weak_patterns(query_case, doc)


def dcg(relevances: list[int]) -> float:
    total = 0.0
    for idx, rel in enumerate(relevances, start=1):
        total += float(rel) / math.log2(idx + 1)
    return total


def metrics_at_k(
    *,
    query_case: dict[str, Any],
    result_ids: list[str],
    docs: dict[str, dict[str, Any]],
    k: int,
) -> dict[str, Any]:
    top_ids = result_ids[:k]
    relevance_flags = [1 if is_relevant(query_case, cid, docs) else 0 for cid in top_ids]

    explicit_ids = explicit_relevance_ids(query_case)
    relevant_found = sum(relevance_flags)
    hit = relevant_found > 0

    mrr = 0.0
    for idx, flag in enumerate(relevance_flags, start=1):
        if flag:
            mrr = 1.0 / idx
            break

    if explicit_ids:
        expected_count = len(explicit_ids)
        recall_denominator = expected_count
        recall = min(relevant_found / recall_denominator, 1.0) if recall_denominator else 0.0
        ideal_relevant = min(expected_count, len(top_ids))
        ideal = [1] * ideal_relevant + [0] * max(0, len(top_ids) - ideal_relevant)
        ideal_dcg = dcg(ideal)
        ndcg = dcg(relevance_flags) / ideal_dcg if ideal_dcg > 0 else 0.0
    else:
        # Weak-pattern cases are smoke checks: there is no known finite set of all
        # relevant canonical_ids. Use binary hit/recall and normalize nDCG against
        # the number of matching returned results, so the metric remains in [0, 1].
        expected_count = None
        recall = 1.0 if hit else 0.0
        ideal_relevant = min(relevant_found, len(top_ids))
        ideal = [1] * ideal_relevant + [0] * max(0, len(top_ids) - ideal_relevant)
        ideal_dcg = dcg(ideal)
        ndcg = dcg(relevance_flags) / ideal_dcg if ideal_dcg > 0 else 0.0

    ndcg = min(max(ndcg, 0.0), 1.0)

    return {
        "hit_at_k": hit,
        "recall_at_k": finite_round(recall, 6),
        "mrr_at_k": finite_round(mrr, 6),
        "ndcg_at_k": finite_round(ndcg, 6),
        "relevant_found_at_k": int(relevant_found),
        "expected_relevant_count": expected_count,
    }


def percentile(values: list[float], q: float) -> float | None:
    finite_values = [finite_float(v, default=float("nan")) for v in values]
    finite_values = [v for v in finite_values if math.isfinite(v)]
    if not finite_values:
        return None
    return round(float(np.percentile(np.array(finite_values, dtype=float), q)), 3)


def finite_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return default
    if not math.isfinite(out):
        return default
    return out


def finite_round(value: Any, digits: int = 6, default: float = 0.0) -> float:
    return round(finite_float(value, default=default), digits)


def query_case_kind(query_case: dict[str, Any]) -> str:
    if explicit_relevance_ids(query_case):
        return "explicit"
    expected = query_case.get("expected") or {}
    if (
        expected.get("title_substrings")
        or expected.get("title_any_substrings")
        or expected.get("must_have_any_terms")
    ):
        return "weak_pattern"
    return "unknown"


def summarize_golden_queries(rows: list[dict[str, Any]]) -> dict[str, Any]:
    enabled = [row for row in rows if row.get("enabled") is True]
    explicit = [row for row in enabled if query_case_kind(row) == "explicit"]
    weak = [row for row in enabled if query_case_kind(row) == "weak_pattern"]
    unknown = [row for row in enabled if query_case_kind(row) == "unknown"]
    return {
        "rows_count": len(rows),
        "enabled_queries_count": len(enabled),
        "explicit_relevance_queries_count": len(explicit),
        "weak_pattern_queries_count": len(weak),
        "unknown_relevance_queries_count": len(unknown),
        "unknown_relevance_query_ids": [str(row.get("query_id")) for row in unknown],
    }


def collection_exists(client: QdrantClient, collection_name: str) -> bool:
    try:
        return bool(client.collection_exists(collection_name=collection_name))
    except Exception:
        try:
            client.get_collection(collection_name=collection_name)
            return True
        except Exception:
            return False


def recreate_collection(
    *,
    client: QdrantClient,
    collection_name: str,
    vector_size: int,
    recreate: bool,
) -> dict[str, Any]:
    existed_before = collection_exists(client, collection_name)
    deleted = False
    created = False

    if existed_before and recreate:
        client.delete_collection(collection_name=collection_name)
        deleted = True

    if recreate or not collection_exists(client, collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(
                size=vector_size,
                distance=qmodels.Distance.COSINE,
            ),
        )
        created = True

    return {
        "collection_name": collection_name,
        "existed_before": existed_before,
        "deleted": deleted,
        "created": created,
        "recreate_requested": recreate,
        "vector_size": vector_size,
        "distance": "cosine",
    }


def get_collection_count(client: QdrantClient, collection_name: str) -> int | None:
    try:
        count_result = client.count(collection_name=collection_name, exact=True)
        return int(count_result.count)
    except Exception:
        return None


def wait_for_collection_count(
    *,
    client: QdrantClient,
    collection_name: str,
    expected_count: int,
    timeout_sec: float,
    poll_sec: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    last_count: int | None = None
    attempts = 0

    while True:
        attempts += 1
        last_count = get_collection_count(client, collection_name)
        if last_count == expected_count:
            return {
                "ok": True,
                "count": last_count,
                "attempts": attempts,
                "elapsed_sec": round(time.perf_counter() - started, 3),
            }

        elapsed = time.perf_counter() - started
        if elapsed >= timeout_sec:
            return {
                "ok": False,
                "count": last_count,
                "attempts": attempts,
                "elapsed_sec": round(elapsed, 3),
            }

        time.sleep(poll_sec)


def upsert_embeddings(
    *,
    client: QdrantClient,
    collection_name: str,
    embeddings: np.ndarray,
    ids: list[str],
    build_id: str,
    batch_size: int,
    wait: bool,
    retry_count: int,
    retry_sleep_sec: float,
    count_wait_timeout_sec: float,
    count_wait_poll_sec: float,
) -> dict[str, Any]:
    uploaded = 0
    batch_latencies_ms: list[float] = []
    failed_batches: list[dict[str, Any]] = []

    for start in range(0, len(ids), batch_size):
        end = min(start + batch_size, len(ids))
        points = [
            qmodels.PointStruct(
                id=idx,
                vector=embeddings[idx].astype(float).tolist(),
                payload={
                    "canonical_id": ids[idx],
                    "build_id": build_id,
                    "dense_index": idx,
                },
            )
            for idx in range(start, end)
        ]

        last_error: str | None = None
        for attempt in range(1, retry_count + 2):
            t0 = time.perf_counter()
            try:
                client.upsert(collection_name=collection_name, points=points, wait=wait)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                batch_latencies_ms.append(elapsed_ms)
                uploaded += len(points)
                last_error = None
                break
            except Exception as exc:
                last_error = repr(exc)
                if attempt <= retry_count:
                    time.sleep(retry_sleep_sec)
                else:
                    failed_batches.append(
                        {
                            "start": start,
                            "end": end,
                            "attempts": attempt,
                            "error": last_error,
                        }
                    )

    wait_summary = wait_for_collection_count(
        client=client,
        collection_name=collection_name,
        expected_count=uploaded,
        timeout_sec=count_wait_timeout_sec,
        poll_sec=count_wait_poll_sec,
    )

    return {
        "uploaded_count": uploaded,
        "collection_points_count": wait_summary.get("count"),
        "batch_size": batch_size,
        "batch_count": math.ceil(len(ids) / batch_size) if batch_size else 0,
        "wait_for_upsert": wait,
        "retry_count": retry_count,
        "failed_batch_count": len(failed_batches),
        "failed_batches": failed_batches[:20],
        "count_wait_summary": wait_summary,
        "batch_latency_ms": {
            "p50": percentile(batch_latencies_ms, 50),
            "p95": percentile(batch_latencies_ms, 95),
            "max": round(max(batch_latencies_ms), 3) if batch_latencies_ms else None,
        },
    }


def qdrant_search(
    *,
    client: QdrantClient,
    collection_name: str,
    query_vector: np.ndarray,
    top_k: int,
) -> list[dict[str, Any]]:
    vector = query_vector.astype(float).tolist()

    try:
        response = client.query_points(
            collection_name=collection_name,
            query=vector,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        raw_points = getattr(response, "points", response)
    except Exception:
        raw_points = client.search(
            collection_name=collection_name,
            query_vector=vector,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )

    out: list[dict[str, Any]] = []
    for point in raw_points:
        payload = getattr(point, "payload", None) or {}
        out.append(
            {
                "point_id": getattr(point, "id", None),
                "canonical_id": payload.get("canonical_id"),
                "dense_index": payload.get("dense_index"),
                "score": getattr(point, "score", None),
            }
        )
    return out


def normalize_matrix(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def file_dense_search(
    *,
    normalized_embeddings: np.ndarray,
    ids: list[str],
    query_vector: np.ndarray,
    top_k: int,
) -> list[dict[str, Any]]:
    q = query_vector.astype(np.float32)
    q_norm = np.linalg.norm(q)
    if q_norm > 0:
        q = q / q_norm
    scores = normalized_embeddings @ q
    if top_k >= len(scores):
        top_idx = np.argsort(-scores)
    else:
        top_idx = np.argpartition(-scores, top_k)[:top_k]
        top_idx = top_idx[np.argsort(-scores[top_idx])]
    return [
        {
            "dense_index": int(idx),
            "canonical_id": ids[int(idx)],
            "score": float(scores[int(idx)]),
        }
        for idx in top_idx[:top_k]
    ]


def summarize_quality(query_results: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    metric_key = f"{mode}_metrics"
    rows = [item.get(metric_key) or {} for item in query_results if item.get(metric_key)]
    if not rows:
        return {}

    def avg(name: str) -> float:
        vals: list[float] = []
        for row in rows:
            value = row.get(name, 0.0)
            if isinstance(value, bool):
                value = 1.0 if value else 0.0
            x = finite_float(value, default=0.0)
            vals.append(x)
        return round(sum(vals) / len(vals), 6) if vals else 0.0

    return {
        "queries_count": len(rows),
        "hit_rate_at_k": avg("hit_at_k"),
        "recall_at_k": avg("recall_at_k"),
        "mrr_at_k": avg("mrr_at_k"),
        "ndcg_at_k": avg("ndcg_at_k"),
    }


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Qdrant retrieval benchmark")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Schema version: `{report['schema_version']}`")
    lines.append(f"- Build id: `{report['manifest']['build_id']}`")
    lines.append(f"- Corpus doc count: **{report['manifest']['corpus_doc_count']}**")
    lines.append(f"- Collection: `{report['qdrant']['collection_name']}`")
    lines.append("")

    lines.append("## Dense artifacts")
    dense = report["dense_artifacts"]
    for key in ("dense_embeddings_path", "dense_ids_path", "embedding_shape", "ids_count"):
        lines.append(f"- {key}: `{dense.get(key)}`")
    lines.append("")

    lines.append("## Upload summary")
    for key, value in report["upload_summary"].items():
        if key != "batch_latency_ms":
            lines.append(f"- {key}: `{value}`")
    lines.append(f"- batch_latency_ms: `{report['upload_summary'].get('batch_latency_ms')}`")
    lines.append("")

    lines.append("## Query summary")
    for key, value in report["query_summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Latency summary")
    for section, values in report["latency_summary"].items():
        lines.append(f"- {section}: `{values}`")
    lines.append("")

    lines.append("## Quality summary")
    for section, values in report["quality_summary"].items():
        lines.append(f"- {section}: `{values}`")
    lines.append("")

    if report.get("overlap_summary"):
        lines.append("## File dense vs Qdrant overlap")
        for key, value in report["overlap_summary"].items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")

    lines.append("## Query results")
    lines.append("")
    lines.append("| Query id | Group | Qdrant returned | Qdrant hit | Qdrant recall | File overlap@k |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for item in report["query_results"]:
        qm = item.get("qdrant_metrics") or {}
        overlap = item.get("file_dense_overlap") or {}
        lines.append(
            f"| {item.get('query_id')} | {item.get('group')} | "
            f"{item.get('qdrant_returned_count', 0)} | {qm.get('hit_at_k')} | "
            f"{qm.get('recall_at_k')} | {overlap.get('overlap_ratio_at_k', '-')} |"
        )
    lines.append("")

    lines.append("## Verdict")
    for key, value in report["verdict"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Qdrant dense retrieval benchmark over golden queries.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--max-vectors", type=int, default=None, help="Debug only: upload/search only the first N vectors.")
    parser.add_argument("--no-file-compare", action="store_true", help="Skip file dense overlap comparison.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    config = load_yaml(args.config)
    qdrant_cfg = config.get("qdrant") or {}
    settings = get_settings()
    retrieval_cfg = config.get("retrieval") or {}
    upload_cfg = config.get("upload") or {}
    output_cfg = config.get("output") or {}

    output_dir = args.output_dir or Path(output_cfg.get("output_dir") or DEFAULT_OUTPUT_DIR)
    latest_json = output_dir / "qdrant_retrieval_benchmark_latest.json"
    latest_md = output_dir / "qdrant_retrieval_benchmark_latest.md"
    hist_json = output_dir / "history" / f"qdrant_retrieval_benchmark_{run_ts}.json"
    hist_md = output_dir / "history" / f"qdrant_retrieval_benchmark_{run_ts}.md"

    manifest_path = to_path(retrieval_cfg.get("manifest_path", "artifacts/retrieval/manifests/latest.json"))
    golden_queries_path = to_path(retrieval_cfg.get("golden_queries_path", "data/eval/retrieval/golden_queries.jsonl"))
    top_k = int(retrieval_cfg.get("top_k", 20) or 20)
    batch_size = int(upload_cfg.get("batch_size", 128) or 128)
    wait_for_upsert = bool(upload_cfg.get("wait", False))
    retry_count = int(upload_cfg.get("retry_count", 2) or 0)
    retry_sleep_sec = float(upload_cfg.get("retry_sleep_sec", 2.0) or 0.0)
    count_wait_timeout_sec = float(upload_cfg.get("count_wait_timeout_sec", 120.0) or 120.0)
    count_wait_poll_sec = float(upload_cfg.get("count_wait_poll_sec", 2.0) or 2.0)
    max_vectors = args.max_vectors if args.max_vectors is not None else upload_cfg.get("max_vectors")
    max_vectors = int(max_vectors) if max_vectors is not None else None
    compare_file_dense = bool(retrieval_cfg.get("compare_file_dense", True)) and not args.no_file_compare

    manifest = load_json(manifest_path)
    build_id = str(manifest.get("build_id"))
    corpus_doc_count = int(manifest.get("corpus_doc_count") or 0)
    embedding_model_name = str(manifest.get("embedding_model_name"))
    dense_embeddings_path = to_path(manifest["dense_embeddings_path"])
    dense_ids_path = to_path(manifest["dense_ids_path"])
    corpus_path = to_path(manifest["corpus_path"])

    embeddings = np.load(dense_embeddings_path)
    ids = load_ids(dense_ids_path)

    if len(embeddings) != len(ids):
        raise ValueError(f"Embeddings rows ({len(embeddings)}) != ids count ({len(ids)})")
    if corpus_doc_count and len(ids) != corpus_doc_count:
        raise ValueError(f"Ids count ({len(ids)}) != manifest corpus_doc_count ({corpus_doc_count})")

    is_partial = False
    if max_vectors is not None:
        max_vectors = max(1, min(max_vectors, len(ids)))
        embeddings = embeddings[:max_vectors]
        ids = ids[:max_vectors]
        is_partial = max_vectors != corpus_doc_count

    vector_size = int(embeddings.shape[1])
    golden_query_rows = load_jsonl(golden_queries_path)
    enabled_queries = [row for row in golden_query_rows if row.get("enabled") is True]
    golden_query_summary = summarize_golden_queries(golden_query_rows)
    docs = load_canonical_docs(corpus_path)

    qdrant_host = str(qdrant_cfg.get("host", settings.qdrant_host))
    qdrant_port = int(qdrant_cfg.get("port", settings.qdrant_port))
    qdrant_timeout_sec = float(
        qdrant_cfg.get("timeout_sec", settings.qdrant_timeout_sec)
        or settings.qdrant_timeout_sec
    )
    qdrant_check_compatibility = bool(
        qdrant_cfg.get(
            "check_compatibility",
            settings.qdrant_check_compatibility,
        )
    )
    collection_name = str(
        qdrant_cfg.get("collection_name", settings.qdrant_collection_name)
    )

    client = QdrantClient(
        host=qdrant_host,
        port=qdrant_port,
        prefer_grpc=bool(qdrant_cfg.get("prefer_grpc", False)),
        timeout=qdrant_timeout_sec,
        check_compatibility=qdrant_check_compatibility,
    )

    collection_summary = recreate_collection(
        client=client,
        collection_name=collection_name,
        vector_size=vector_size,
        recreate=bool(qdrant_cfg.get("recreate_collection", True)),
    )

    upload_t0 = time.perf_counter()
    upload_summary = upsert_embeddings(
        client=client,
        collection_name=collection_name,
        embeddings=embeddings,
        ids=ids,
        build_id=build_id,
        batch_size=batch_size,
        wait=wait_for_upsert,
        retry_count=retry_count,
        retry_sleep_sec=retry_sleep_sec,
        count_wait_timeout_sec=count_wait_timeout_sec,
        count_wait_poll_sec=count_wait_poll_sec,
    )
    upload_summary["duration_sec"] = round(time.perf_counter() - upload_t0, 3)
    upload_summary["is_partial"] = is_partial
    upload_summary["uploaded_ratio_vs_manifest"] = round(upload_summary["uploaded_count"] / corpus_doc_count, 6) if corpus_doc_count else None

    model = SentenceTransformer(embedding_model_name)
    normalized_embeddings = normalize_matrix(embeddings.astype(np.float32)) if compare_file_dense else None

    query_results: list[dict[str, Any]] = []
    qdrant_latencies_ms: list[float] = []
    file_latencies_ms: list[float] = []
    error_count = 0

    for case in enabled_queries:
        qid = str(case.get("query_id"))
        query = str(case.get("query") or "")
        group = str(case.get("group") or "")
        item: dict[str, Any] = {
            "query_id": qid,
            "query": query,
            "group": group,
            "relevance_kind": query_case_kind(case),
        }

        try:
            query_vector = model.encode(query, normalize_embeddings=True, show_progress_bar=False)
            query_vector = np.asarray(query_vector, dtype=np.float32)

            t0 = time.perf_counter()
            qdrant_hits = qdrant_search(
                client=client,
                collection_name=collection_name,
                query_vector=query_vector,
                top_k=top_k,
            )
            q_ms = (time.perf_counter() - t0) * 1000.0
            qdrant_latencies_ms.append(q_ms)

            qdrant_ids = [str(hit.get("canonical_id")) for hit in qdrant_hits if hit.get("canonical_id")]
            item["qdrant_latency_ms"] = round(q_ms, 3)
            item["qdrant_returned_count"] = len(qdrant_ids)
            item["qdrant_results"] = qdrant_hits
            item["qdrant_metrics"] = metrics_at_k(
                query_case=case,
                result_ids=qdrant_ids,
                docs=docs,
                k=top_k,
            )

            if compare_file_dense and normalized_embeddings is not None:
                t0 = time.perf_counter()
                file_hits = file_dense_search(
                    normalized_embeddings=normalized_embeddings,
                    ids=ids,
                    query_vector=query_vector,
                    top_k=top_k,
                )
                f_ms = (time.perf_counter() - t0) * 1000.0
                file_latencies_ms.append(f_ms)
                file_ids = [str(hit.get("canonical_id")) for hit in file_hits if hit.get("canonical_id")]

                overlap = len(set(qdrant_ids) & set(file_ids))
                item["file_dense_latency_ms"] = round(f_ms, 3)
                item["file_dense_results"] = file_hits[:top_k]
                item["file_dense_metrics"] = metrics_at_k(
                    query_case=case,
                    result_ids=file_ids,
                    docs=docs,
                    k=top_k,
                )
                item["file_dense_overlap"] = {
                    "overlap_count_at_k": overlap,
                    "overlap_ratio_at_k": round(overlap / top_k, 6) if top_k else 0.0,
                    "exact_same_order": qdrant_ids == file_ids,
                }

        except Exception as exc:
            error_count += 1
            item["error"] = repr(exc)

        query_results.append(item)

    overlap_rows = [x.get("file_dense_overlap") or {} for x in query_results if x.get("file_dense_overlap")]
    overlap_values = [finite_float(x.get("overlap_ratio_at_k", 0.0), default=0.0) for x in overlap_rows]
    exact_order_count = sum(1 for x in overlap_rows if x.get("exact_same_order") is True)

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "config_path": normalize_path(args.config),
        "config": config,
        "manifest": {
            "path": normalize_path(manifest_path),
            "build_id": build_id,
            "corpus_doc_count": corpus_doc_count,
            "corpus_path": normalize_path(corpus_path),
            "embedding_model_name": embedding_model_name,
        },
        "dense_artifacts": {
            "dense_embeddings_path": normalize_path(dense_embeddings_path),
            "dense_ids_path": normalize_path(dense_ids_path),
            "embedding_shape": list(embeddings.shape),
            "ids_count": len(ids),
            "vector_size": vector_size,
            "is_partial": is_partial,
        },
        "qdrant": {
            "host": qdrant_host,
            "port": qdrant_port,
            "collection_name": collection_name,
            "timeout_sec": qdrant_timeout_sec,
            "check_compatibility": qdrant_check_compatibility,
            "collection_summary": collection_summary,
        },
        "upload_summary": upload_summary,
        "golden_query_summary": golden_query_summary,
        "enabled_queries_count": len(enabled_queries),
        "query_count": len(query_results),
        "query_summary": {
            "golden_queries_path": normalize_path(golden_queries_path),
            "enabled_queries_count": len(enabled_queries),
            "query_count": len(query_results),
            "explicit_relevance_queries_count": golden_query_summary["explicit_relevance_queries_count"],
            "weak_pattern_queries_count": golden_query_summary["weak_pattern_queries_count"],
            "unknown_relevance_queries_count": golden_query_summary["unknown_relevance_queries_count"],
            "top_k": top_k,
            "error_count": error_count,
            "queries_with_results": sum(1 for x in query_results if int(x.get("qdrant_returned_count", 0) or 0) > 0),
            "queries_without_results": [x.get("query_id") for x in query_results if int(x.get("qdrant_returned_count", 0) or 0) == 0],
        },
        "latency_summary": {
            "qdrant_query_ms": {
                "p50": percentile(qdrant_latencies_ms, 50),
                "p95": percentile(qdrant_latencies_ms, 95),
                "max": round(max(qdrant_latencies_ms), 3) if qdrant_latencies_ms else None,
            },
            "file_dense_query_ms": {
                "p50": percentile(file_latencies_ms, 50),
                "p95": percentile(file_latencies_ms, 95),
                "max": round(max(file_latencies_ms), 3) if file_latencies_ms else None,
            } if compare_file_dense else {},
        },
        "quality_summary": {
            "qdrant": summarize_quality(query_results, "qdrant"),
            "file_dense": summarize_quality(query_results, "file_dense") if compare_file_dense else {},
        },
        "overlap_summary": {
            "enabled": compare_file_dense,
            "queries_count": len(overlap_values),
            "mean_overlap_ratio_at_k": round(sum(overlap_values) / len(overlap_values), 6) if overlap_values else None,
            "min_overlap_ratio_at_k": round(min(overlap_values), 6) if overlap_values else None,
            "exact_same_order_count": exact_order_count,
        },
        "query_results": query_results,
        "artifacts": {
            "latest_json": normalize_path(latest_json),
            "latest_markdown": normalize_path(latest_md),
            "history_json": normalize_path(hist_json),
            "history_markdown": normalize_path(hist_md),
        },
        "verdict": {
            "ok": bool(error_count == 0 and upload_summary.get("failed_batch_count", 0) == 0 and upload_summary.get("collection_points_count") == upload_summary.get("uploaded_count")),
            "production_default_changed": False,
            "benchmark_only": True,
            "notes": [
                "Qdrant benchmark is a derived evaluation layer.",
                "This script does not modify retrieval manifest, SearchRuntime, API defaults, or canonical truth.",
            ],
        },
    }

    markdown = build_markdown(report)
    dump_json(latest_json, report)
    dump_json(hist_json, report)
    dump_text(latest_md, markdown)
    dump_text(hist_md, markdown)

    print(f"[OK] schema_version={SCHEMA_VERSION}")
    print(f"[OK] build_id={build_id}")
    print(f"[OK] corpus_doc_count={corpus_doc_count}")
    print(f"[OK] collection_name={collection_name}")
    print(f"[OK] uploaded_count={upload_summary['uploaded_count']}")
    print(f"[OK] collection_points_count={upload_summary.get('collection_points_count')}")
    print(f"[OK] enabled_queries_count={len(enabled_queries)}")
    print(f"[OK] error_count={error_count}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()
