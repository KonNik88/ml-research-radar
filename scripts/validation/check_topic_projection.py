from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_TOPIC_LATEST_PATH = Path("artifacts/clusters/topic/latest.json")
DEFAULT_RETRIEVAL_MANIFEST_PATH = Path("artifacts/retrieval/manifests/latest.json")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/clusters")


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


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except Exception:
        return False


def build_markdown(report: dict[str, Any]) -> str:
    verdict = report["verdict"]
    checks = report["checks"]
    values = report["extracted_values"]

    lines: list[str] = []
    lines.append("# Topic projection quality report")
    lines.append("")
    lines.append(f"- generated_at_utc: `{report['generated_at_utc']}`")
    lines.append(f"- ok: `{verdict['ok']}`")
    lines.append(f"- required_failed_count: `{verdict['required_failed_count']}`")
    lines.append(f"- required_failed_checks: `{verdict['required_failed_checks']}`")
    lines.append("")
    lines.append("## Extracted values")
    for key, value in values.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## Checks")
    for key, value in checks.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    if report.get("warnings"):
        lines.append("## Warnings")
        for warning in report["warnings"]:
            lines.append(f"- {warning}")
        lines.append("")
    return "\n".join(lines)


def validate_topic_projection(
    *,
    topic_latest_path: Path,
    retrieval_manifest_path: Path,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    warnings: list[str] = []

    checks["topic_latest_exists"] = topic_latest_path.exists()
    latest = load_json(topic_latest_path) if checks["topic_latest_exists"] else {}

    projection = latest.get("projection") if isinstance(latest.get("projection"), dict) else {}

    projection_path = Path(str(projection.get("projection_path") or ""))
    projection_summary_path = Path(str(projection.get("projection_summary_path") or ""))

    checks["projection_enabled"] = bool(projection.get("enabled"))
    checks["projection_path_present"] = bool(str(projection_path))
    checks["projection_summary_path_present"] = bool(str(projection_summary_path))
    checks["projection_exists"] = projection_path.exists()
    checks["projection_summary_exists"] = projection_summary_path.exists()

    retrieval_manifest = load_json(retrieval_manifest_path) if retrieval_manifest_path.exists() else {}
    projection_summary = (
        load_json(projection_summary_path) if checks["projection_summary_exists"] else {}
    )

    expected_cluster_build_id = latest.get("cluster_build_id")
    expected_retrieval_build_id = latest.get("retrieval_build_id")
    manifest_build_id = retrieval_manifest.get("build_id")

    rows_count = 0
    centroid_count = 0
    representative_count = 0
    sampled_count = 0
    bad_schema_count = 0
    missing_cluster_id_count = 0
    missing_point_type_count = 0
    bad_xy_count = 0
    missing_centroid_cluster_ids: set[int] = set()
    duplicate_centroid_cluster_ids: list[int] = []
    centroid_cluster_counter: Counter[int] = Counter()
    point_type_counter: Counter[str] = Counter()
    cluster_ids: set[int] = set()
    row_cluster_build_mismatch_count = 0
    row_retrieval_build_mismatch_count = 0

    if checks["projection_exists"]:
        for row, _line_no in iter_jsonl(projection_path):
            rows_count += 1

            if row.get("schema_version") != "topic_projection_2d.v1":
                bad_schema_count += 1

            if row.get("cluster_build_id") != expected_cluster_build_id:
                row_cluster_build_mismatch_count += 1
            if row.get("retrieval_build_id") != expected_retrieval_build_id:
                row_retrieval_build_mismatch_count += 1

            point_type = str(row.get("point_type") or "")
            if not point_type:
                missing_point_type_count += 1
            point_type_counter[point_type] += 1

            try:
                cluster_id = int(row.get("cluster_id"))
                cluster_ids.add(cluster_id)
            except Exception:
                missing_cluster_id_count += 1
                continue

            if point_type == "centroid":
                centroid_count += 1
                centroid_cluster_counter[cluster_id] += 1
            if bool(row.get("is_representative")):
                representative_count += 1
            if bool(row.get("is_sampled")):
                sampled_count += 1

            if not is_finite_number(row.get("x")) or not is_finite_number(row.get("y")):
                bad_xy_count += 1

    for cluster_id, count in centroid_cluster_counter.items():
        if count > 1:
            duplicate_centroid_cluster_ids.append(cluster_id)

    expected_cluster_count = safe_int(
        projection_summary.get("counts", {}).get("cluster_count"),
        default=safe_int(latest.get("cluster_count"), default=0),
    )
    if expected_cluster_count:
        missing_centroid_cluster_ids = set(range(expected_cluster_count)) - set(
            centroid_cluster_counter.keys()
        )

    summary_counts = projection_summary.get("counts") or {}
    summary_method = projection_summary.get("method") or {}

    checks["retrieval_manifest_exists"] = retrieval_manifest_path.exists()
    checks["projection_summary_schema_ok"] = (
        projection_summary.get("schema_version") == "topic_projection_summary.v1"
    )
    checks["summary_cluster_build_id_match"] = (
        projection_summary.get("cluster_build_id") == expected_cluster_build_id
    )
    checks["summary_retrieval_build_id_match"] = (
        projection_summary.get("retrieval_build_id") == expected_retrieval_build_id
    )
    checks["latest_vs_manifest_retrieval_build_id_match"] = (
        expected_retrieval_build_id == manifest_build_id
    )
    checks["summary_vs_manifest_retrieval_build_id_match"] = (
        projection_summary.get("retrieval_build_id") == manifest_build_id
    )
    checks["projection_rows_non_empty"] = rows_count > 0
    checks["projection_schema_ok"] = bad_schema_count == 0
    checks["projection_row_cluster_build_id_match"] = row_cluster_build_mismatch_count == 0
    checks["projection_row_retrieval_build_id_match"] = row_retrieval_build_mismatch_count == 0
    checks["projection_xy_finite"] = bad_xy_count == 0
    checks["projection_cluster_ids_present"] = missing_cluster_id_count == 0
    checks["projection_point_types_present"] = missing_point_type_count == 0
    checks["centroid_points_present"] = centroid_count > 0
    checks["representative_points_present"] = representative_count > 0
    checks["centroid_count_matches_cluster_count"] = (
        expected_cluster_count > 0 and centroid_count == expected_cluster_count
    )
    checks["one_centroid_per_cluster"] = (
        not duplicate_centroid_cluster_ids and not missing_centroid_cluster_ids
    )
    checks["summary_point_count_matches_rows"] = (
        safe_int(summary_counts.get("point_count"), default=-1) == rows_count
    )
    checks["summary_centroid_count_matches_rows"] = (
        safe_int(summary_counts.get("centroid_count"), default=-1) == centroid_count
    )
    checks["summary_representative_count_matches_rows"] = (
        safe_int(summary_counts.get("representative_count"), default=-1)
        == representative_count
    )
    checks["projection_algorithm_supported"] = (
        summary_method.get("algorithm") in {"umap", "pca_svd"}
    )

    if sampled_count == 0:
        warnings.append("sampled_count=0; projection is still valid but less informative")

    required_checks = [
        "topic_latest_exists",
        "projection_enabled",
        "projection_path_present",
        "projection_summary_path_present",
        "projection_exists",
        "projection_summary_exists",
        "retrieval_manifest_exists",
        "projection_summary_schema_ok",
        "summary_cluster_build_id_match",
        "summary_retrieval_build_id_match",
        "latest_vs_manifest_retrieval_build_id_match",
        "summary_vs_manifest_retrieval_build_id_match",
        "projection_rows_non_empty",
        "projection_schema_ok",
        "projection_row_cluster_build_id_match",
        "projection_row_retrieval_build_id_match",
        "projection_xy_finite",
        "projection_cluster_ids_present",
        "projection_point_types_present",
        "centroid_points_present",
        "representative_points_present",
        "centroid_count_matches_cluster_count",
        "one_centroid_per_cluster",
        "summary_point_count_matches_rows",
        "summary_centroid_count_matches_rows",
        "summary_representative_count_matches_rows",
        "projection_algorithm_supported",
    ]

    required_failed = [name for name in required_checks if not checks.get(name, False)]

    return {
        "report_name": "topic_projection_quality",
        "generated_at_utc": utc_now_iso(),
        "inputs": {
            "topic_latest_path": normalize_path(topic_latest_path),
            "retrieval_manifest_path": normalize_path(retrieval_manifest_path),
            "projection_path": normalize_path(projection_path),
            "projection_summary_path": normalize_path(projection_summary_path),
        },
        "extracted_values": {
            "projection_build_id": projection_summary.get("projection_build_id"),
            "cluster_build_id": expected_cluster_build_id,
            "retrieval_build_id": expected_retrieval_build_id,
            "manifest_build_id": manifest_build_id,
            "projection_algorithm": summary_method.get("algorithm"),
            "rows_count": rows_count,
            "centroid_count": centroid_count,
            "representative_count": representative_count,
            "sampled_count": sampled_count,
            "expected_cluster_count": expected_cluster_count,
            "actual_cluster_count": len(cluster_ids),
            "bad_schema_count": bad_schema_count,
            "bad_xy_count": bad_xy_count,
            "row_cluster_build_mismatch_count": row_cluster_build_mismatch_count,
            "row_retrieval_build_mismatch_count": row_retrieval_build_mismatch_count,
            "missing_cluster_id_count": missing_cluster_id_count,
            "missing_point_type_count": missing_point_type_count,
            "duplicate_centroid_cluster_ids": sorted(duplicate_centroid_cluster_ids),
            "missing_centroid_cluster_ids": sorted(missing_centroid_cluster_ids),
            "point_type_counts": dict(point_type_counter),
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate latest topic projection artifacts.")
    parser.add_argument("--topic-latest-path", type=Path, default=DEFAULT_TOPIC_LATEST_PATH)
    parser.add_argument("--retrieval-manifest-path", type=Path, default=DEFAULT_RETRIEVAL_MANIFEST_PATH)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    report = validate_topic_projection(
        topic_latest_path=args.topic_latest_path,
        retrieval_manifest_path=args.retrieval_manifest_path,
    )

    latest_json = args.reports_dir / "topic_projection_quality_latest.json"
    latest_md = args.reports_dir / "topic_projection_quality_latest.md"
    hist_json = args.reports_dir / "history" / f"topic_projection_quality_{run_ts}.json"
    hist_md = args.reports_dir / "history" / f"topic_projection_quality_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    verdict = report["verdict"]
    values = report["extracted_values"]

    print(f"[OK] report_json={latest_json}")
    print(f"[OK] report_md={latest_md}")
    print(f"[OK] projection_build_id={values.get('projection_build_id')}")
    print(f"[OK] cluster_build_id={values.get('cluster_build_id')}")
    print(f"[OK] retrieval_build_id={values.get('retrieval_build_id')}")
    print(f"[OK] projection_algorithm={values.get('projection_algorithm')}")
    print(f"[OK] rows_count={values.get('rows_count')}")
    print(f"[OK] centroid_count={values.get('centroid_count')}")
    print(f"[OK] representative_count={values.get('representative_count')}")
    print(f"[OK] sampled_count={values.get('sampled_count')}")
    print(f"[OK] required_failed_count={verdict['required_failed_count']}")

    if verdict["required_failed_checks"]:
        print(f"[FAIL] required_failed_checks={verdict['required_failed_checks']}")

    if args.strict and not verdict["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()