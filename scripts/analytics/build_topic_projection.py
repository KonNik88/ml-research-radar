from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


DEFAULT_TOPIC_LATEST_PATH = Path("artifacts/clusters/topic/latest.json")
DEFAULT_RETRIEVAL_MANIFEST_PATH = Path("artifacts/retrieval/manifests/latest.json")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/clusters")

SCHEMA_VERSION = "topic_projection_2d.v1"


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON must be an object: {path}")
    return payload


def iter_jsonl(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line), line_no
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL: {path} line={line_no}: {exc}") from exc


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def dump_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        x = float(value)
        if not math.isfinite(x):
            return default
        return x
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def read_dense_paths(manifest: dict[str, Any]) -> tuple[Path, Path]:
    dense_embeddings_path = (
        manifest.get("dense_embeddings_path")
        or manifest.get("embeddings_path")
        or ((manifest.get("dense") or {}).get("embeddings_path"))
    )
    dense_ids_path = (
        manifest.get("dense_ids_path")
        or manifest.get("ids_path")
        or ((manifest.get("dense") or {}).get("ids_path"))
    )

    if not dense_embeddings_path:
        raise ValueError("Retrieval manifest has no dense embeddings path")
    if not dense_ids_path:
        raise ValueError("Retrieval manifest has no dense ids path")

    return Path(str(dense_embeddings_path)), Path(str(dense_ids_path))


def load_dense_ids(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Dense ids JSON must be a list: {path}")
    return [str(x) for x in payload]


def l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def project_2d(matrix: np.ndarray, *, random_state: int, prefer_umap: bool) -> tuple[np.ndarray, str, dict[str, Any]]:
    if prefer_umap:
        try:
            import umap  # type: ignore

            reducer = umap.UMAP(
                n_components=2,
                metric="cosine",
                random_state=random_state,
                n_neighbors=min(15, max(2, len(matrix) - 1)),
                min_dist=0.10,
            )
            coords = reducer.fit_transform(matrix)
            return coords.astype(float), "umap", {
                "n_components": 2,
                "metric": "cosine",
                "random_state": random_state,
                "n_neighbors": min(15, max(2, len(matrix) - 1)),
                "min_dist": 0.10,
            }
        except Exception as exc:
            print(f"[WARN] UMAP unavailable or failed, falling back to PCA: {exc}")

    centered = matrix - matrix.mean(axis=0, keepdims=True)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    coords = centered @ vt[:2].T
    return coords.astype(float), "pca_svd", {
        "n_components": 2,
        "random_state": random_state,
        "fallback": True,
    }


def compact_cluster_label(cluster: dict[str, Any]) -> str | None:
    labels = cluster.get("label_candidates") or []
    if labels:
        return str(labels[0])
    return None


def build_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    verdict = report["verdict"]

    lines: list[str] = []
    lines.append("# Topic projection report")
    lines.append("")
    lines.append(f"- generated_at_utc: `{report['generated_at_utc']}`")
    lines.append(f"- projection_build_id: `{summary['projection_build_id']}`")
    lines.append(f"- cluster_build_id: `{summary['cluster_build_id']}`")
    lines.append(f"- retrieval_build_id: `{summary['retrieval_build_id']}`")
    lines.append(f"- method: `{summary['method']['algorithm']}`")
    lines.append(f"- point_count: `{summary['counts']['point_count']}`")
    lines.append(f"- centroid_count: `{summary['counts']['centroid_count']}`")
    lines.append(f"- representative_count: `{summary['counts']['representative_count']}`")
    lines.append(f"- sampled_count: `{summary['counts']['sampled_count']}`")
    lines.append(f"- ok: `{verdict['ok']}`")
    lines.append("")
    lines.append("## Outputs")
    for k, v in report["outputs"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    return "\n".join(lines)


def build_topic_projection(
    *,
    topic_latest_path: Path,
    retrieval_manifest_path: Path,
    reports_dir: Path,
    representatives_per_cluster: int,
    samples_per_cluster: int,
    random_state: int,
    prefer_umap: bool,
    no_write_latest: bool,
) -> dict[str, Any]:
    projection_build_id = utc_now_ts()

    topic_latest = load_json(topic_latest_path)
    retrieval_manifest = load_json(retrieval_manifest_path)

    cluster_build_id = str(topic_latest.get("cluster_build_id") or "")
    retrieval_build_id = str(topic_latest.get("retrieval_build_id") or "")
    cluster_config_hash = topic_latest.get("cluster_config_hash")

    if not cluster_build_id:
        raise ValueError("Topic latest has no cluster_build_id")
    if not retrieval_build_id:
        raise ValueError("Topic latest has no retrieval_build_id")

    manifest_build_id = str(retrieval_manifest.get("build_id") or "")
    if retrieval_build_id != manifest_build_id:
        raise ValueError(
            f"Retrieval build mismatch: topic={retrieval_build_id} manifest={manifest_build_id}"
        )

    run_dir = Path(str(topic_latest.get("run_dir") or ""))
    assignments_path = Path(str(topic_latest.get("assignments_path") or run_dir / "assignments.jsonl"))
    summary_path = Path(str(topic_latest.get("summary_path") or run_dir / "summary.json"))

    summary = load_json(summary_path)
    clusters = summary.get("clusters") or []
    if not isinstance(clusters, list) or not clusters:
        raise ValueError(f"summary.clusters must be a non-empty list: {summary_path}")

    dense_embeddings_path, dense_ids_path = read_dense_paths(retrieval_manifest)
    embeddings = np.load(dense_embeddings_path, mmap_mode="r", allow_pickle=False)
    dense_ids = load_dense_ids(dense_ids_path)

    if embeddings.ndim != 2:
        raise ValueError(f"Dense embeddings must be 2D, got shape={embeddings.shape}")
    if len(dense_ids) != int(embeddings.shape[0]):
        raise ValueError(
            f"Dense ids count mismatch: ids={len(dense_ids)} embeddings_rows={embeddings.shape[0]}"
        )

    id_to_idx = {canonical_id: idx for idx, canonical_id in enumerate(dense_ids)}

    assignments_by_cluster: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row, _line_no in iter_jsonl(assignments_path):
        cluster_id = safe_int(row.get("cluster_id"), default=-1)
        if cluster_id < 0:
            continue
        assignments_by_cluster[cluster_id].append(row)

    rng = random.Random(random_state)

    vectors: list[np.ndarray] = []
    point_meta: list[dict[str, Any]] = []

    cluster_by_id = {safe_int(c.get("cluster_id")): c for c in clusters}

    # 1) centroids computed from all member vectors, but output only 1 point per cluster.
    for cluster_id, cluster in sorted(cluster_by_id.items()):
        rows = assignments_by_cluster.get(cluster_id, [])
        member_indices = [
            id_to_idx[str(row["canonical_id"])]
            for row in rows
            if row.get("canonical_id") and str(row["canonical_id"]) in id_to_idx
        ]
        if not member_indices:
            continue

        member_matrix = np.asarray(embeddings[member_indices], dtype=np.float32)
        centroid = member_matrix.mean(axis=0)
        vectors.append(centroid)

        point_meta.append(
            {
                "point_type": "centroid",
                "cluster_id": cluster_id,
                "canonical_id": None,
                "title": None,
                "year": None,
                "label": compact_cluster_label(cluster),
                "label_candidates": cluster.get("label_candidates") or [],
                "cluster_size": safe_int(cluster.get("size")),
                "artifact_ready_count": safe_int(cluster.get("artifact_ready_count")),
                "mean_radar_score": safe_float(cluster.get("mean_radar_score")),
                "mean_implementation_readiness_score": safe_float(
                    cluster.get("mean_implementation_readiness_score")
                ),
                "is_representative": False,
                "is_sampled": False,
                "rank_within_cluster": None,
            }
        )

    # 2) representative papers from summary.
    representative_ids_by_cluster: dict[int, set[str]] = defaultdict(set)
    for cluster_id, cluster in sorted(cluster_by_id.items()):
        reps = cluster.get("representative_papers") or []
        for rep in reps[:representatives_per_cluster]:
            canonical_id = str(rep.get("canonical_id") or "")
            if not canonical_id or canonical_id not in id_to_idx:
                continue

            representative_ids_by_cluster[cluster_id].add(canonical_id)
            vectors.append(np.asarray(embeddings[id_to_idx[canonical_id]], dtype=np.float32))

            point_meta.append(
                {
                    "point_type": "paper",
                    "cluster_id": cluster_id,
                    "canonical_id": canonical_id,
                    "title": rep.get("title"),
                    "year": rep.get("year"),
                    "label": compact_cluster_label(cluster),
                    "label_candidates": cluster.get("label_candidates") or [],
                    "cluster_size": safe_int(cluster.get("size")),
                    "artifact_ready_count": safe_int(cluster.get("artifact_ready_count")),
                    "mean_radar_score": safe_float(cluster.get("mean_radar_score")),
                    "mean_implementation_readiness_score": safe_float(
                        cluster.get("mean_implementation_readiness_score")
                    ),
                    "is_representative": True,
                    "is_sampled": False,
                    "rank_within_cluster": rep.get("rank_within_cluster"),
                    "radar_score": rep.get("radar_score"),
                    "implementation_readiness_score": rep.get(
                        "implementation_readiness_score"
                    ),
                }
            )

    # 3) bounded random sample per cluster, excluding representatives.
    for cluster_id, cluster in sorted(cluster_by_id.items()):
        rows = [
            row
            for row in assignments_by_cluster.get(cluster_id, [])
            if row.get("canonical_id")
            and str(row["canonical_id"]) in id_to_idx
            and str(row["canonical_id"]) not in representative_ids_by_cluster[cluster_id]
        ]

        if samples_per_cluster > 0 and rows:
            sample_n = min(samples_per_cluster, len(rows))
            sampled = rng.sample(rows, k=sample_n)
        else:
            sampled = []

        for row in sampled:
            canonical_id = str(row["canonical_id"])
            vectors.append(np.asarray(embeddings[id_to_idx[canonical_id]], dtype=np.float32))

            point_meta.append(
                {
                    "point_type": "paper",
                    "cluster_id": cluster_id,
                    "canonical_id": canonical_id,
                    "title": row.get("title"),
                    "year": row.get("year"),
                    "label": compact_cluster_label(cluster),
                    "label_candidates": cluster.get("label_candidates") or [],
                    "cluster_size": safe_int(cluster.get("size")),
                    "artifact_ready_count": safe_int(cluster.get("artifact_ready_count")),
                    "mean_radar_score": safe_float(cluster.get("mean_radar_score")),
                    "mean_implementation_readiness_score": safe_float(
                        cluster.get("mean_implementation_readiness_score")
                    ),
                    "is_representative": False,
                    "is_sampled": True,
                    "rank_within_cluster": row.get("rank_within_cluster"),
                    "radar_score": row.get("radar_score"),
                    "implementation_readiness_score": row.get(
                        "implementation_readiness_score"
                    ),
                }
            )

    if not vectors:
        raise ValueError("No vectors selected for projection")

    matrix = np.vstack(vectors).astype(np.float32)
    matrix = l2_normalize(matrix).astype(np.float32)

    coords, algorithm, method_params = project_2d(
        matrix,
        random_state=random_state,
        prefer_umap=prefer_umap,
    )

    rows: list[dict[str, Any]] = []
    for idx, meta in enumerate(point_meta):
        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "projection_build_id": projection_build_id,
                "cluster_build_id": cluster_build_id,
                "retrieval_build_id": retrieval_build_id,
                "cluster_config_hash": cluster_config_hash,
                "projection_algorithm": algorithm,
                "x": round(float(coords[idx, 0]), 8),
                "y": round(float(coords[idx, 1]), 8),
                **meta,
            }
        )

    centroid_count = sum(1 for row in rows if row["point_type"] == "centroid")
    representative_count = sum(1 for row in rows if row.get("is_representative"))
    sampled_count = sum(1 for row in rows if row.get("is_sampled"))

    projection_path = run_dir / "projection_2d.jsonl"
    projection_summary_path = run_dir / "projection_summary.json"

    projection_summary = {
        "schema_version": "topic_projection_summary.v1",
        "projection_build_id": projection_build_id,
        "cluster_build_id": cluster_build_id,
        "retrieval_build_id": retrieval_build_id,
        "cluster_config_hash": cluster_config_hash,
        "created_at": utc_now_iso(),
        "method": {
            "algorithm": algorithm,
            "params": method_params,
        },
        "selection": {
            "representatives_per_cluster": representatives_per_cluster,
            "samples_per_cluster": samples_per_cluster,
            "random_state": random_state,
        },
        "inputs": {
            "topic_latest_path": normalize_path(topic_latest_path),
            "retrieval_manifest_path": normalize_path(retrieval_manifest_path),
            "assignments_path": normalize_path(assignments_path),
            "summary_path": normalize_path(summary_path),
            "dense_embeddings_path": normalize_path(dense_embeddings_path),
            "dense_ids_path": normalize_path(dense_ids_path),
        },
        "outputs": {
            "projection_path": normalize_path(projection_path),
            "projection_summary_path": normalize_path(projection_summary_path),
        },
        "counts": {
            "point_count": len(rows),
            "centroid_count": centroid_count,
            "representative_count": representative_count,
            "sampled_count": sampled_count,
            "cluster_count": len(cluster_by_id),
        },
    }

    report = {
        "report_name": "topic_projection",
        "generated_at_utc": utc_now_iso(),
        "summary": projection_summary,
        "outputs": {
            "projection_path": normalize_path(projection_path),
            "projection_summary_path": normalize_path(projection_summary_path),
        },
        "verdict": {
            "ok": True,
            "required_failed_count": 0,
            "required_failed_checks": [],
        },
    }

    dump_jsonl(projection_path, rows)
    dump_json(projection_summary_path, projection_summary)

    latest_json = reports_dir / "topic_projection_latest.json"
    latest_md = reports_dir / "topic_projection_latest.md"
    hist_json = reports_dir / "history" / f"topic_projection_{projection_build_id}.json"
    hist_md = reports_dir / "history" / f"topic_projection_{projection_build_id}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    if not no_write_latest:
        enriched_latest = dict(topic_latest)
        enriched_latest["projection"] = {
            "enabled": True,
            "schema_version": SCHEMA_VERSION,
            "projection_build_id": projection_build_id,
            "projection_path": normalize_path(projection_path),
            "projection_summary_path": normalize_path(projection_summary_path),
            "point_count": len(rows),
            "centroid_count": centroid_count,
            "representative_count": representative_count,
            "sampled_count": sampled_count,
            "algorithm": algorithm,
        }
        dump_json(topic_latest_path, enriched_latest)

    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build lightweight 2D topic projection over topic cluster centroids, representatives and samples."
    )
    parser.add_argument("--topic-latest-path", type=Path, default=DEFAULT_TOPIC_LATEST_PATH)
    parser.add_argument("--retrieval-manifest-path", type=Path, default=DEFAULT_RETRIEVAL_MANIFEST_PATH)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--representatives-per-cluster", type=int, default=10)
    parser.add_argument("--samples-per-cluster", type=int, default=15)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--prefer-pca", action="store_true", help="Use PCA/SVD fallback directly instead of trying UMAP.")
    parser.add_argument("--no-write-latest", action="store_true", help="Do not update topic latest.json with projection metadata.")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.representatives_per_cluster < 0:
        raise SystemExit("--representatives-per-cluster must be >= 0")
    if args.samples_per_cluster < 0:
        raise SystemExit("--samples-per-cluster must be >= 0")

    report = build_topic_projection(
        topic_latest_path=args.topic_latest_path,
        retrieval_manifest_path=args.retrieval_manifest_path,
        reports_dir=args.reports_dir,
        representatives_per_cluster=args.representatives_per_cluster,
        samples_per_cluster=args.samples_per_cluster,
        random_state=args.random_state,
        prefer_umap=not args.prefer_pca,
        no_write_latest=args.no_write_latest,
    )

    summary = report["summary"]
    counts = summary["counts"]

    print("[OK] topic projection built")
    print(f"[OK] projection_build_id={summary['projection_build_id']}")
    print(f"[OK] cluster_build_id={summary['cluster_build_id']}")
    print(f"[OK] retrieval_build_id={summary['retrieval_build_id']}")
    print(f"[OK] algorithm={summary['method']['algorithm']}")
    print(f"[OK] point_count={counts['point_count']}")
    print(f"[OK] centroid_count={counts['centroid_count']}")
    print(f"[OK] representative_count={counts['representative_count']}")
    print(f"[OK] sampled_count={counts['sampled_count']}")
    print(f"[OK] projection_path={summary['outputs']['projection_path']}")
    print(f"[OK] projection_summary_path={summary['outputs']['projection_summary_path']}")


if __name__ == "__main__":
    main()