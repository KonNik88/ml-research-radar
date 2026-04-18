from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.cluster import KMeans

from radar_core.retrieval.similarity import (
    DEFAULT_CANONICAL_PATH,
    load_canonical_map,
    load_similarity_artifacts,
)


DEFAULT_OUTPUT_DIR = Path("artifacts/clusters/abstract")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/analytics")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def shorten(text: str, max_len: int = 160) -> str:
    text = " ".join((text or "").split()).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def top_terms_from_categories(rows: list[dict[str, Any]], top_n: int = 10) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for row in rows:
        for item in row.get("categories") or []:
            if item:
                counter[str(item)] += 1
        for item in row.get("tags") or []:
            if item:
                counter[str(item)] += 1
    return counter.most_common(top_n)


def build_cluster_examples(
    assignments: list[dict[str, Any]],
    *,
    canonical_map: dict[str, dict[str, Any]],
    top_clusters: list[int],
    examples_per_cluster: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in assignments:
        cid = int(row["cluster_id"])
        if cid in top_clusters:
            grouped[cid].append(row)

    out: dict[str, list[dict[str, Any]]] = {}
    for cid in top_clusters:
        cluster_rows = sorted(grouped.get(cid, []), key=lambda x: float(x["distance_to_center"]))
        examples: list[dict[str, Any]] = []

        for item in cluster_rows[:examples_per_cluster]:
            can_row = canonical_map.get(item["canonical_id"], {})
            examples.append(
                {
                    "canonical_id": item["canonical_id"],
                    "title": shorten(str(can_row.get("title") or "")),
                    "year": can_row.get("year"),
                    "categories": can_row.get("categories") or [],
                    "distance_to_center": item["distance_to_center"],
                }
            )
        out[str(cid)] = examples

    return out


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Abstract clustering report")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append("")
    lines.append("## Inputs")
    for k, v in report["inputs"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Results")
    for k, v in report["results"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Largest clusters")
    for item in report["largest_clusters"]:
        lines.append(
            f"- cluster={item['cluster_id']} | size={item['size']} | "
            f"top_terms={item['top_terms']}"
        )
    lines.append("")
    lines.append("## Example papers")
    for cluster_id, examples in report["cluster_examples"].items():
        lines.append(f"### Cluster {cluster_id}")
        for ex in examples:
            lines.append(
                f"- dist={ex['distance_to_center']:.4f} | year={ex['year']} | title={ex['title']}"
            )
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cluster abstract embeddings into coarse semantic groups."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument("--n-clusters", type=int, default=50)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--max-iter", type=int, default=300)
    parser.add_argument("--n-init", type=int, default=10)
    parser.add_argument("--top-clusters", type=int, default=10)
    parser.add_argument("--examples-per-cluster", type=int, default=5)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    artifacts = load_similarity_artifacts()
    canonical_map = load_canonical_map(args.canonical_path)
    embeddings = artifacts.embeddings
    ids = artifacts.ids

    if len(ids) != embeddings.shape[0]:
        raise ValueError("Mismatch between ids and embeddings row count")

    print(f"[INFO] count={len(ids)}")
    print(f"[INFO] embedding_dim={embeddings.shape[1]}")
    print(f"[INFO] n_clusters={args.n_clusters}")
    print(f"[INFO] model_name={artifacts.model_name}")
    print(f"[INFO] text_builder={artifacts.text_builder}")
    print(f"[INFO] normalize_embeddings={artifacts.normalize_embeddings}")

    km = KMeans(
        n_clusters=args.n_clusters,
        random_state=args.random_state,
        n_init=args.n_init,
        max_iter=args.max_iter,
    )
    labels = km.fit_predict(embeddings)

    distances = np.linalg.norm(embeddings - km.cluster_centers_[labels], axis=1)

    assignments: list[dict[str, Any]] = []
    cluster_sizes: Counter[int] = Counter()

    for cid, cluster_id, dist in zip(ids, labels.tolist(), distances.tolist()):
        cluster_sizes[int(cluster_id)] += 1
        assignments.append(
            {
                "canonical_id": cid,
                "cluster_id": int(cluster_id),
                "distance_to_center": round(float(dist), 6),
            }
        )

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    assignments_path = output_dir / f"assignments_{run_ts}.jsonl"
    summary_path = output_dir / f"summary_{run_ts}.json"
    latest_path = output_dir / "latest.json"

    dump_jsonl(assignments_path, assignments)

    largest_cluster_ids = [cid for cid, _ in cluster_sizes.most_common(args.top_clusters)]
    largest_clusters: list[dict[str, Any]] = []

    assignments_by_cluster: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in assignments:
        assignments_by_cluster[int(item["cluster_id"])].append(item)

    for cid, size in cluster_sizes.most_common(args.top_clusters):
        rows_for_terms: list[dict[str, Any]] = []
        for item in assignments_by_cluster[cid][:1000]:
            can_row = canonical_map.get(item["canonical_id"], {})
            if can_row:
                rows_for_terms.append(can_row)

        largest_clusters.append(
            {
                "cluster_id": int(cid),
                "size": int(size),
                "top_terms": top_terms_from_categories(rows_for_terms, top_n=8),
            }
        )

    cluster_examples = build_cluster_examples(
        assignments,
        canonical_map=canonical_map,
        top_clusters=largest_cluster_ids,
        examples_per_cluster=args.examples_per_cluster,
    )

    summary = {
        "run_ts": run_ts,
        "generated_at_utc": utc_now_iso(),
        "inputs": {
            "model_name": artifacts.model_name,
            "text_builder": artifacts.text_builder,
            "normalize_embeddings": artifacts.normalize_embeddings,
            "count": artifacts.count,
            "embedding_dim": artifacts.embedding_dim,
            "canonical_path": str(args.canonical_path).replace("\\", "/"),
            "n_clusters": args.n_clusters,
            "random_state": args.random_state,
            "max_iter": args.max_iter,
            "n_init": args.n_init,
        },
        "results": {
            "assignments_count": len(assignments),
            "unique_clusters": len(set(labels.tolist())),
            "largest_cluster_size": int(max(cluster_sizes.values())) if cluster_sizes else 0,
            "smallest_cluster_size": int(min(cluster_sizes.values())) if cluster_sizes else 0,
            "inertia": float(km.inertia_),
            "assignments_path": str(assignments_path).replace("\\", "/"),
        },
        "largest_clusters": largest_clusters,
        "cluster_examples": cluster_examples,
    }

    dump_json(summary_path, summary)

    latest = {
        "run_ts": run_ts,
        "algorithm": "kmeans",
        "model_name": artifacts.model_name,
        "text_builder": artifacts.text_builder,
        "normalize_embeddings": artifacts.normalize_embeddings,
        "count": artifacts.count,
        "embedding_dim": artifacts.embedding_dim,
        "n_clusters": args.n_clusters,
        "assignments_path": str(assignments_path).replace("\\", "/"),
        "summary_path": str(summary_path).replace("\\", "/"),
    }
    dump_json(latest_path, latest)

    latest_report_json = args.reports_dir / "cluster_papers_latest.json"
    latest_report_md = args.reports_dir / "cluster_papers_latest.md"
    hist_report_json = args.reports_dir / "history" / f"cluster_papers_{run_ts}.json"
    hist_report_md = args.reports_dir / "history" / f"cluster_papers_{run_ts}.md"

    dump_json(latest_report_json, summary)
    dump_text(latest_report_md, build_markdown(summary))
    dump_json(hist_report_json, summary)
    dump_text(hist_report_md, build_markdown(summary))

    print(f"[OK] assignments_count={len(assignments)}")
    print(f"[OK] unique_clusters={len(set(labels.tolist()))}")
    print(f"[OK] inertia={km.inertia_:.4f}")
    print(f"[OK] assignments_path={assignments_path}")
    print(f"[OK] summary_path={summary_path}")
    print(f"[OK] latest_path={latest_path}")
    print(f"[OK] report_json={latest_report_json}")
    print(f"[OK] report_md={latest_report_md}")


if __name__ == "__main__":
    main()
