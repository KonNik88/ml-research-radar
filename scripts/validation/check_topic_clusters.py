from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from radar_core.retrieval.similar import load_ids, normalize_path


DEFAULT_LATEST_PATH = Path("artifacts/clusters/topic/latest.json")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/clusters")
DEFAULT_RETRIEVAL_MANIFEST_PATH = Path("artifacts/retrieval/manifests/latest.json")
DEFAULT_FEATURES_PATH = Path("data/features/paper_features_latest.jsonl")
DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


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


def count_jsonl_rows(path: Path) -> int:
    return sum(1 for _row, _line_no in iter_jsonl(path))


def read_embedding_shape(path: Path) -> list[int]:
    if not path.exists():
        raise FileNotFoundError(f"Embedding file not found: {path}")
    arr = np.load(path, mmap_mode="r", allow_pickle=False)
    return [int(x) for x in arr.shape]


def is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except Exception:
        return False


def in_unit_range(value: Any) -> bool:
    try:
        x = float(value)
        return 0.0 <= x <= 1.0
    except Exception:
        return False


def build_markdown(report: dict[str, Any]) -> str:
    verdict = report["verdict"]
    checks = report["checks"]
    counts = report["extracted_values"]

    lines: list[str] = []
    lines.append("# Topic clusters quality report")
    lines.append("")
    lines.append(f"- generated_at_utc: `{report['generated_at_utc']}`")
    lines.append(f"- ok: `{verdict['ok']}`")
    lines.append(f"- required_failed_count: `{verdict['required_failed_count']}`")
    lines.append(f"- required_failed_checks: `{verdict['required_failed_checks']}`")
    lines.append("")
    lines.append("## Extracted values")
    for key, value in counts.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## Checks")
    for key, value in checks.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    if report.get("warnings"):
        lines.append("## Warnings")
        for item in report["warnings"]:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate latest topic cluster run artifacts."
    )
    parser.add_argument("--latest-path", type=Path, default=DEFAULT_LATEST_PATH)
    parser.add_argument("--retrieval-manifest-path", type=Path, default=DEFAULT_RETRIEVAL_MANIFEST_PATH)
    parser.add_argument("--features-path", type=Path, default=DEFAULT_FEATURES_PATH)
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--strict", action="store_true")
    return parser


def validate_topic_clusters(
    *,
    latest_path: Path,
    retrieval_manifest_path: Path,
    features_path: Path,
    canonical_path: Path,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    warnings: list[str] = []

    checks["latest_exists"] = latest_path.exists()
    latest = load_json(latest_path) if checks["latest_exists"] else {}

    run_dir = Path(str(latest.get("run_dir") or "")) if latest else Path("")
    assignments_path = Path(str(latest.get("assignments_path") or "")) if latest else Path("")
    summary_path = Path(str(latest.get("summary_path") or "")) if latest else Path("")
    label_candidates_path = Path(str(latest.get("label_candidates_path") or "")) if latest else Path("")

    checks["run_dir_exists"] = bool(run_dir) and run_dir.exists()
    checks["assignments_exists"] = bool(assignments_path) and assignments_path.exists()
    checks["summary_exists"] = bool(summary_path) and summary_path.exists()
    checks["label_candidates_exists"] = bool(label_candidates_path) and label_candidates_path.exists()
    checks["retrieval_manifest_exists"] = retrieval_manifest_path.exists()
    checks["features_exists"] = features_path.exists()
    checks["canonical_exists"] = canonical_path.exists()

    summary = load_json(summary_path) if checks["summary_exists"] else {}
    labels = load_json(label_candidates_path) if checks["label_candidates_exists"] else {}
    manifest = load_json(retrieval_manifest_path) if checks["retrieval_manifest_exists"] else {}

    latest_retrieval_build_id = latest.get("retrieval_build_id")
    summary_retrieval_build_id = summary.get("retrieval_build_id")
    manifest_build_id = manifest.get("build_id")

    checks["latest_vs_manifest_retrieval_build_id_match"] = (
        bool(latest_retrieval_build_id)
        and latest_retrieval_build_id == manifest_build_id
    )
    checks["summary_vs_manifest_retrieval_build_id_match"] = (
        bool(summary_retrieval_build_id)
        and summary_retrieval_build_id == manifest_build_id
    )
    checks["latest_vs_summary_cluster_build_id_match"] = (
        latest.get("cluster_build_id") is not None
        and latest.get("cluster_build_id") == summary.get("cluster_build_id")
    )
    checks["cluster_config_hash_present"] = bool(latest.get("cluster_config_hash") and summary.get("cluster_config_hash"))

    embedding_path = Path(str(manifest.get("dense_embeddings_path") or ""))
    ids_path = Path(str(manifest.get("dense_ids_path") or ""))
    latest_embedding_shape = latest.get("embedding_shape") or []

    checks["manifest_dense_embeddings_exists"] = bool(embedding_path) and embedding_path.exists()
    checks["manifest_dense_ids_exists"] = bool(ids_path) and ids_path.exists()

    embedding_shape: list[int] = []
    dense_ids_count = 0

    if checks["manifest_dense_embeddings_exists"]:
        embedding_shape = read_embedding_shape(embedding_path)

    if checks["manifest_dense_ids_exists"]:
        dense_ids_count = len(load_ids(ids_path))

    manifest_doc_count = int(manifest.get("corpus_doc_count") or 0)
    embedding_rows = int(embedding_shape[0]) if len(embedding_shape) == 2 else 0

    checks["embedding_shape_is_2d"] = len(embedding_shape) == 2 and embedding_rows > 0
    checks["embedding_rows_match_dense_ids"] = bool(embedding_rows) and embedding_rows == dense_ids_count
    checks["embedding_rows_match_manifest_doc_count"] = bool(embedding_rows) and embedding_rows == manifest_doc_count
    checks["latest_embedding_shape_matches_manifest_embedding_shape"] = (
        bool(latest_embedding_shape)
        and [int(x) for x in latest_embedding_shape] == embedding_shape
    )

    features_rows_count = count_jsonl_rows(features_path) if checks["features_exists"] else 0
    canonical_rows_count = count_jsonl_rows(canonical_path) if checks["canonical_exists"] else 0

    assignment_count = 0
    assignment_ids: set[str] = set()
    duplicate_ids: list[str] = []
    missing_canonical_id_count = 0
    non_finite_distance_count = 0
    non_finite_similarity_count = 0
    bad_rank_count = 0
    bad_score_range_count = 0
    cluster_counter: Counter[int] = Counter()
    assignment_schema_bad_count = 0
    assignment_retrieval_mismatch_count = 0
    assignment_cluster_build_mismatch_count = 0

    expected_cluster_build_id = latest.get("cluster_build_id")
    expected_retrieval_build_id = latest.get("retrieval_build_id")

    if checks["assignments_exists"]:
        for row, _line_no in iter_jsonl(assignments_path):
            assignment_count += 1

            if row.get("schema_version") != "topic_cluster_assignment.v1":
                assignment_schema_bad_count += 1

            canonical_id = row.get("canonical_id")
            if not canonical_id:
                missing_canonical_id_count += 1
            else:
                canonical_id = str(canonical_id)
                if canonical_id in assignment_ids:
                    duplicate_ids.append(canonical_id)
                assignment_ids.add(canonical_id)

            if row.get("retrieval_build_id") != expected_retrieval_build_id:
                assignment_retrieval_mismatch_count += 1
            if row.get("cluster_build_id") != expected_cluster_build_id:
                assignment_cluster_build_mismatch_count += 1

            try:
                cluster_counter[int(row.get("cluster_id"))] += 1
            except Exception:
                pass

            if not is_finite_number(row.get("distance_to_centroid")):
                non_finite_distance_count += 1
            if not is_finite_number(row.get("similarity_to_centroid")):
                non_finite_similarity_count += 1
            if int(row.get("rank_within_cluster") or 0) <= 0:
                bad_rank_count += 1

            for score_key in [
                "radar_score",
                "implementation_readiness_score",
                "source_confidence_score",
                "citation_signal_score",
                "recency_score",
            ]:
                if not in_unit_range(row.get(score_key)):
                    bad_score_range_count += 1

    expected_cluster_count = int(((summary.get("counts") or {}).get("expected_cluster_count")) or (latest.get("algorithm_params") or {}).get("n_clusters") or 0)
    actual_cluster_count = len(cluster_counter)
    empty_cluster_count = max(0, expected_cluster_count - actual_cluster_count) if expected_cluster_count else 0

    summary_counts = summary.get("counts") or {}
    label_clusters = labels.get("clusters") or []
    summary_clusters = summary.get("clusters") or []

    representative_missing_count = 0
    for cluster in summary_clusters:
        reps = cluster.get("representative_papers") or []
        if not reps:
            representative_missing_count += 1

    label_candidates_missing_count = 0
    for item in label_clusters:
        if not item.get("label_candidates"):
            label_candidates_missing_count += 1

    checks["assignment_schema_ok"] = assignment_schema_bad_count == 0
    checks["assignment_retrieval_build_id_match"] = assignment_retrieval_mismatch_count == 0
    checks["assignment_cluster_build_id_match"] = assignment_cluster_build_mismatch_count == 0
    checks["assignments_count_matches_embedding_rows"] = bool(assignment_count) and assignment_count == embedding_rows
    checks["assignments_count_matches_features_rows"] = bool(assignment_count) and assignment_count == features_rows_count
    checks["assignments_count_matches_canonical_rows"] = bool(assignment_count) and assignment_count == canonical_rows_count
    checks["summary_assigned_rows_count_matches_assignments"] = int(summary_counts.get("assigned_rows_count") or 0) == assignment_count
    checks["no_missing_canonical_id"] = missing_canonical_id_count == 0
    checks["no_duplicate_canonical_id"] = len(duplicate_ids) == 0
    checks["cluster_count_positive"] = actual_cluster_count > 1
    checks["cluster_count_matches_expected"] = bool(expected_cluster_count) and actual_cluster_count == expected_cluster_count
    checks["empty_cluster_count_zero"] = empty_cluster_count == 0 and int(summary_counts.get("empty_cluster_count") or 0) == 0
    checks["distances_finite"] = non_finite_distance_count == 0
    checks["similarities_finite"] = non_finite_similarity_count == 0
    checks["ranks_valid"] = bad_rank_count == 0
    checks["score_ranges_valid"] = bad_score_range_count == 0
    checks["summary_clusters_present"] = len(summary_clusters) == actual_cluster_count and actual_cluster_count > 0
    checks["label_clusters_present"] = len(label_clusters) == actual_cluster_count and actual_cluster_count > 0
    checks["representative_papers_present"] = representative_missing_count == 0
    checks["label_candidates_present"] = label_candidates_missing_count == 0
    checks["projection_disabled_v1"] = not bool((summary.get("projection") or {}).get("enabled"))

    largest_cluster_ratio = float((summary.get("global_metrics") or {}).get("largest_cluster_ratio") or 0.0)
    if largest_cluster_ratio > 0.10:
        warnings.append(f"largest_cluster_ratio is high: {largest_cluster_ratio}")

    if label_candidates_missing_count:
        warnings.append(f"label_candidates_missing_count={label_candidates_missing_count}")

    required_checks = [
        "latest_exists",
        "run_dir_exists",
        "assignments_exists",
        "summary_exists",
        "label_candidates_exists",
        "retrieval_manifest_exists",
        "features_exists",
        "canonical_exists",
        "latest_vs_manifest_retrieval_build_id_match",
        "summary_vs_manifest_retrieval_build_id_match",
        "latest_vs_summary_cluster_build_id_match",
        "cluster_config_hash_present",
        "manifest_dense_embeddings_exists",
        "manifest_dense_ids_exists",
        "embedding_shape_is_2d",
        "embedding_rows_match_dense_ids",
        "embedding_rows_match_manifest_doc_count",
        "latest_embedding_shape_matches_manifest_embedding_shape",
        "assignment_schema_ok",
        "assignment_retrieval_build_id_match",
        "assignment_cluster_build_id_match",
        "assignments_count_matches_embedding_rows",
        "assignments_count_matches_features_rows",
        "assignments_count_matches_canonical_rows",
        "summary_assigned_rows_count_matches_assignments",
        "no_missing_canonical_id",
        "no_duplicate_canonical_id",
        "cluster_count_positive",
        "cluster_count_matches_expected",
        "empty_cluster_count_zero",
        "distances_finite",
        "similarities_finite",
        "ranks_valid",
        "score_ranges_valid",
        "summary_clusters_present",
        "label_clusters_present",
        "representative_papers_present",
        "label_candidates_present",
        "projection_disabled_v1",
    ]

    required_failed = [name for name in required_checks if not checks.get(name, False)]

    return {
        "report_name": "topic_clusters_quality",
        "generated_at_utc": utc_now_iso(),
        "inputs": {
            "latest_path": normalize_path(latest_path),
            "retrieval_manifest_path": normalize_path(retrieval_manifest_path),
            "features_path": normalize_path(features_path),
            "canonical_path": normalize_path(canonical_path),
        },
        "extracted_values": {
            "cluster_build_id": latest.get("cluster_build_id"),
            "retrieval_build_id": latest.get("retrieval_build_id"),
            "manifest_build_id": manifest_build_id,
            "embedding_path": normalize_path(embedding_path),
            "ids_path": normalize_path(ids_path),
            "embedding_shape": embedding_shape,
            "embedding_rows": embedding_rows,
            "dense_ids_count": dense_ids_count,
            "manifest_doc_count": manifest_doc_count,
            "features_rows_count": features_rows_count,
            "canonical_rows_count": canonical_rows_count,
            "assignment_count": assignment_count,
            "actual_cluster_count": actual_cluster_count,
            "expected_cluster_count": expected_cluster_count,
            "empty_cluster_count": empty_cluster_count,
            "largest_cluster_ratio": largest_cluster_ratio,
            "duplicate_canonical_id_count": len(duplicate_ids),
            "missing_canonical_id_count": missing_canonical_id_count,
            "non_finite_distance_count": non_finite_distance_count,
            "non_finite_similarity_count": non_finite_similarity_count,
            "bad_rank_count": bad_rank_count,
            "bad_score_range_count": bad_score_range_count,
            "representative_missing_count": representative_missing_count,
            "label_candidates_missing_count": label_candidates_missing_count,
        },
        "checks": checks,
        "warnings": warnings,
        "verdict": {
            "required_check_count": len(required_checks),
            "required_failed_count": len(required_failed),
            "required_failed_checks": required_failed,
            "ok": len(required_failed) == 0,
        },
    }


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    report = validate_topic_clusters(
        latest_path=args.latest_path,
        retrieval_manifest_path=args.retrieval_manifest_path,
        features_path=args.features_path,
        canonical_path=args.canonical_path,
    )

    latest_json = args.reports_dir / "topic_clusters_quality_latest.json"
    latest_md = args.reports_dir / "topic_clusters_quality_latest.md"
    hist_json = args.reports_dir / "history" / f"topic_clusters_quality_{run_ts}.json"
    hist_md = args.reports_dir / "history" / f"topic_clusters_quality_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    verdict = report["verdict"]
    values = report["extracted_values"]

    print(f"[OK] report_json={latest_json}")
    print(f"[OK] report_md={latest_md}")
    print(f"[OK] cluster_build_id={values.get('cluster_build_id')}")
    print(f"[OK] retrieval_build_id={values.get('retrieval_build_id')}")
    print(f"[OK] assignment_count={values.get('assignment_count')}")
    print(f"[OK] actual_cluster_count={values.get('actual_cluster_count')}")
    print(f"[OK] empty_cluster_count={values.get('empty_cluster_count')}")
    print(f"[OK] required_failed_count={verdict['required_failed_count']}")

    if verdict["required_failed_checks"]:
        print(f"[FAIL] required_failed_checks={verdict['required_failed_checks']}")

    if args.strict and not verdict["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
