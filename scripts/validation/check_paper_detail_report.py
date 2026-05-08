from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DETAIL_REPORT_PATH = Path("artifacts/reports/details/paper_detail_latest.json")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/details")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")

    return json.loads(path.read_text(encoding="utf-8"))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def score_in_range(value: Any) -> bool:
    try:
        numeric = float(value)
    except Exception:
        return False
    return 0.0 <= numeric <= 1.0


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Paper detail quality check")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Strict: `{report['strict']}`")
    lines.append("")

    lines.append("## Inputs")
    for key, value in report["inputs"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Summary")
    for key, value in report["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Checks")
    for key, value in report["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Counters")
    for key, value in report["counters"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Verdict")
    for key, value in report["verdict"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate latest paper detail report."
    )
    parser.add_argument(
        "--detail-report-path",
        type=Path,
        default=DEFAULT_DETAIL_REPORT_PATH,
    )
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    detail_report_exists = args.detail_report_path.exists()
    detail_report: dict[str, Any] = {}

    if detail_report_exists:
        detail_report = load_json(args.detail_report_path)

    detail = detail_report.get("detail") or {}
    scores = detail.get("scores") or {}
    artifacts = detail.get("artifacts") or []
    artifact_summary = detail.get("artifact_summary") or {}

    score_keys = [
        "radar_score",
        "implementation_readiness_score",
        "source_confidence_score",
        "citation_signal_score",
        "recency_score",
    ]

    missing_score_keys = [
        key for key in score_keys if key not in scores or scores.get(key) is None
    ]
    score_range_violations = [
        key for key in score_keys if key in scores and scores.get(key) is not None and not score_in_range(scores.get(key))
    ]

    artifact_rows_missing_artifact_id = [
        idx for idx, artifact in enumerate(artifacts, start=1) if not artifact.get("artifact_id")
    ]
    artifact_rows_missing_relation_type = [
        idx for idx, artifact in enumerate(artifacts, start=1) if not artifact.get("relation_type")
    ]
    artifact_rows_bad_metadata_shape = [
        idx
        for idx, artifact in enumerate(artifacts, start=1)
        if artifact.get("github_metadata") is not None
        and not isinstance(artifact.get("github_metadata"), dict)
        or artifact.get("huggingface_metadata") is not None
        and not isinstance(artifact.get("huggingface_metadata"), dict)
    ]

    artifact_detail_rows_count = artifact_summary.get("artifact_detail_rows_count")

    checks = {
        "detail_report_exists": detail_report_exists,
        "report_name_ok": detail_report.get("report_name") == "paper_detail",
        "canonical_id_present": bool(detail_report.get("canonical_id")),
        "detail_present": bool(detail),
        "paper_found": bool(detail.get("found")),
        "canonical_found": bool(detail.get("canonical_found")),
        "features_found": bool(detail.get("features_found")),
        "title_present": bool(detail.get("title")),
        "scores_present": bool(scores),
        "required_scores_present": len(missing_score_keys) == 0,
        "scores_in_range": len(score_range_violations) == 0,
        "artifacts_shape_ok": isinstance(artifacts, list),
        "artifact_count_matches_summary": artifact_detail_rows_count == len(artifacts),
        "artifact_ids_present": len(artifact_rows_missing_artifact_id) == 0,
        "artifact_relation_types_present": len(artifact_rows_missing_relation_type) == 0,
        "artifact_metadata_shape_ok": len(artifact_rows_bad_metadata_shape) == 0,
        "source_evidence_present": bool(detail.get("source_evidence")),
        "identifiers_present": bool(detail.get("identifiers")),
    }

    required_failed_checks = [name for name, ok in checks.items() if not ok]

    report = {
        "report_name": "paper_detail_quality",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            "detail_report_path": normalize_path(args.detail_report_path),
            "reports_dir": normalize_path(args.reports_dir),
        },
        "summary": {
            "canonical_id": detail_report.get("canonical_id"),
            "title": detail.get("title"),
            "year": detail.get("year"),
            "found": detail.get("found"),
            "canonical_found": detail.get("canonical_found"),
            "features_found": detail.get("features_found"),
            "artifact_rows_count": len(artifacts),
        },
        "counters": {
            "missing_score_keys": missing_score_keys,
            "score_range_violations": score_range_violations,
            "artifact_rows_missing_artifact_id_count": len(artifact_rows_missing_artifact_id),
            "artifact_rows_missing_relation_type_count": len(artifact_rows_missing_relation_type),
            "artifact_rows_bad_metadata_shape_count": len(artifact_rows_bad_metadata_shape),
        },
        "checks": checks,
        "verdict": {
            "ok": len(required_failed_checks) == 0,
            "required_failed_count": len(required_failed_checks),
            "required_failed_checks": required_failed_checks,
        },
    }

    latest_json = args.reports_dir / "paper_detail_quality_latest.json"
    latest_md = args.reports_dir / "paper_detail_quality_latest.md"
    history_json = args.reports_dir / "history" / f"paper_detail_quality_{run_ts}.json"
    history_md = args.reports_dir / "history" / f"paper_detail_quality_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(history_json, report)
    dump_text(history_md, build_markdown(report))

    for key, value in report["summary"].items():
        print(f"[OK] {key}={value}")

    for key, value in checks.items():
        print(f"[OK] {key}={value}")

    print(f"[OK] ok={report['verdict']['ok']}")
    print(f"[OK] required_failed_count={report['verdict']['required_failed_count']}")
    print(f"[OK] required_failed_checks={report['verdict']['required_failed_checks']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history Markdown: {history_md}")

    if args.strict and not report["verdict"]["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()