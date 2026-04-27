from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_ARTIFACT_ENTITIES_PATH = Path(
    "data/enriched/artifact_links/artifact_entities_latest.jsonl"
)
DEFAULT_GITHUB_METADATA_PATH = Path(
    "data/enriched/github_artifacts/github_artifact_metadata_latest.jsonl"
)
DEFAULT_REPORTS_DIR = Path("artifacts/reports/validation")

VALID_STATUSES = {
    "found",
    "not_found",
    "rate_limited",
    "forbidden",
    "error",
    "skipped_invalid_external_id",
}


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


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"JSONL row must be object at {path}:{line_no}")
            rows.append(payload)
    return rows


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def is_truthy_check(value: Any) -> bool:
    return bool(value)


def summarize_artifact_entities(rows: list[dict[str, Any]]) -> dict[str, Any]:
    github_rows = [r for r in rows if r.get("provider") == "github"]
    github_ids = [str(r.get("artifact_id") or "") for r in github_rows]
    github_ids_non_empty = [x for x in github_ids if x]

    duplicate_ids = sorted(
        artifact_id for artifact_id, count in Counter(github_ids_non_empty).items() if count > 1
    )

    missing_external_id = [
        str(r.get("artifact_id"))
        for r in github_rows
        if not r.get("external_id")
    ]

    invalid_external_id = [
        {
            "artifact_id": r.get("artifact_id"),
            "external_id": r.get("external_id"),
        }
        for r in github_rows
        if r.get("external_id") and "/" not in str(r.get("external_id"))
    ]

    return {
        "total_entities_count": len(rows),
        "github_entities_count": len(github_rows),
        "github_artifact_ids_count": len(set(github_ids_non_empty)),
        "github_duplicate_artifact_ids_count": len(duplicate_ids),
        "github_duplicate_artifact_ids_sample": duplicate_ids[:20],
        "github_missing_external_id_count": len(missing_external_id),
        "github_missing_external_id_sample": missing_external_id[:20],
        "github_invalid_external_id_count": len(invalid_external_id),
        "github_invalid_external_id_sample": invalid_external_id[:20],
        "github_artifact_ids": set(github_ids_non_empty),
    }


def summarize_github_metadata(
    rows: list[dict[str, Any]],
    known_github_artifact_ids: set[str],
) -> dict[str, Any]:
    artifact_ids = [str(r.get("artifact_id") or "") for r in rows]
    artifact_ids_non_empty = [x for x in artifact_ids if x]

    duplicate_ids = sorted(
        artifact_id for artifact_id, count in Counter(artifact_ids_non_empty).items() if count > 1
    )

    status_counts = Counter(str(r.get("status") or "missing_status") for r in rows)
    provider_counts = Counter(str(r.get("provider") or "missing_provider") for r in rows)

    unknown_artifact_ids = sorted(
        set(artifact_ids_non_empty) - set(known_github_artifact_ids)
    )
    missing_artifact_id_rows = [i for i, r in enumerate(rows) if not r.get("artifact_id")]
    missing_external_id_rows = [
        str(r.get("artifact_id") or f"row_{i}")
        for i, r in enumerate(rows)
        if not r.get("external_id")
    ]
    missing_status_rows = [
        str(r.get("artifact_id") or f"row_{i}")
        for i, r in enumerate(rows)
        if not r.get("status")
    ]
    invalid_status_rows = [
        {
            "artifact_id": r.get("artifact_id"),
            "status": r.get("status"),
        }
        for r in rows
        if r.get("status") and str(r.get("status")) not in VALID_STATUSES
    ]
    non_github_provider_rows = [
        {
            "artifact_id": r.get("artifact_id"),
            "provider": r.get("provider"),
        }
        for r in rows
        if r.get("provider") != "github"
    ]

    found_rows = [r for r in rows if r.get("status") == "found"]
    found_missing_http_200 = [
        r.get("artifact_id") for r in found_rows if safe_int(r.get("http_status"), -1) != 200
    ]

    found_missing_useful_metadata = [
        r.get("artifact_id")
        for r in found_rows
        if (
            r.get("stars") is None
            and r.get("forks") is None
            and r.get("language") is None
            and r.get("license") is None
            and not r.get("topics")
        )
    ]

    found_with_stars = [r for r in found_rows if r.get("stars") is not None]
    found_with_forks = [r for r in found_rows if r.get("forks") is not None]
    found_with_language = [r for r in found_rows if r.get("language")]
    found_with_license = [r for r in found_rows if r.get("license")]
    found_with_topics = [r for r in found_rows if r.get("topics")]

    rate_limit_remaining_values = [
        r.get("metadata", {}).get("rate_limit_remaining")
        for r in rows
        if isinstance(r.get("metadata"), dict)
        and r.get("metadata", {}).get("rate_limit_remaining") is not None
    ]

    return {
        "metadata_rows_count": len(rows),
        "metadata_artifact_ids_count": len(set(artifact_ids_non_empty)),
        "duplicate_artifact_id_count": len(duplicate_ids),
        "duplicate_artifact_ids_sample": duplicate_ids[:20],
        "missing_artifact_id_count": len(missing_artifact_id_rows),
        "missing_artifact_id_row_indices_sample": missing_artifact_id_rows[:20],
        "unknown_artifact_id_count": len(unknown_artifact_ids),
        "unknown_artifact_ids_sample": unknown_artifact_ids[:20],
        "missing_external_id_count": len(missing_external_id_rows),
        "missing_external_id_sample": missing_external_id_rows[:20],
        "missing_status_count": len(missing_status_rows),
        "missing_status_sample": missing_status_rows[:20],
        "invalid_status_count": len(invalid_status_rows),
        "invalid_status_sample": invalid_status_rows[:20],
        "non_github_provider_count": len(non_github_provider_rows),
        "non_github_provider_sample": non_github_provider_rows[:20],
        "provider_distribution": dict(sorted(provider_counts.items())),
        "status_distribution": dict(sorted(status_counts.items())),
        "found_count": status_counts.get("found", 0),
        "not_found_count": status_counts.get("not_found", 0),
        "forbidden_count": status_counts.get("forbidden", 0),
        "rate_limited_count": status_counts.get("rate_limited", 0),
        "error_count": status_counts.get("error", 0),
        "skipped_invalid_external_id_count": status_counts.get(
            "skipped_invalid_external_id", 0
        ),
        "found_missing_http_200_count": len(found_missing_http_200),
        "found_missing_http_200_sample": found_missing_http_200[:20],
        "found_missing_useful_metadata_count": len(found_missing_useful_metadata),
        "found_missing_useful_metadata_sample": found_missing_useful_metadata[:20],
        "found_with_stars_count": len(found_with_stars),
        "found_with_forks_count": len(found_with_forks),
        "found_with_language_count": len(found_with_language),
        "found_with_license_count": len(found_with_license),
        "found_with_topics_count": len(found_with_topics),
        "rate_limit_remaining_last": rate_limit_remaining_values[-1]
        if rate_limit_remaining_values
        else None,
    }


def build_checks(summary: dict[str, Any]) -> dict[str, bool]:
    return {
        "artifact_entities_exists": bool(summary["artifact_entities_exists"]),
        "github_metadata_exists": bool(summary["github_metadata_exists"]),
        "artifact_entities_non_empty": safe_int(summary["total_entities_count"]) > 0,
        "github_entities_non_empty": safe_int(summary["github_entities_count"]) > 0,
        "github_metadata_non_empty": safe_int(summary["metadata_rows_count"]) > 0,
        "metadata_rows_match_github_entities": (
            safe_int(summary["metadata_rows_count"])
            == safe_int(summary["github_entities_count"])
            and safe_int(summary["github_entities_count"]) > 0
        ),
        "metadata_artifact_ids_match_github_entities": (
            safe_int(summary["metadata_artifact_ids_count"])
            == safe_int(summary["github_artifact_ids_count"])
            and safe_int(summary["github_artifact_ids_count"]) > 0
        ),
        "no_duplicate_metadata_artifact_ids": safe_int(summary["duplicate_artifact_id_count"]) == 0,
        "no_unknown_artifact_ids": safe_int(summary["unknown_artifact_id_count"]) == 0,
        "metadata_rows_have_artifact_id": safe_int(summary["missing_artifact_id_count"]) == 0,
        "metadata_rows_have_external_id": safe_int(summary["missing_external_id_count"]) == 0,
        "metadata_rows_have_status": safe_int(summary["missing_status_count"]) == 0,
        "metadata_status_values_valid": safe_int(summary["invalid_status_count"]) == 0,
        "metadata_provider_is_github": safe_int(summary["non_github_provider_count"]) == 0,
        "found_count_non_empty": safe_int(summary["found_count"]) > 0,
        "no_rate_limited_rows": safe_int(summary["rate_limited_count"]) == 0,
        "no_error_rows": safe_int(summary["error_count"]) == 0,
        "found_rows_have_http_200": safe_int(summary["found_missing_http_200_count"]) == 0,
        "found_rows_have_some_useful_metadata": (
            safe_int(summary["found_missing_useful_metadata_count"]) == 0
        ),
    }


def build_required_check_names(strict: bool) -> list[str]:
    base = [
        "artifact_entities_exists",
        "github_metadata_exists",
        "artifact_entities_non_empty",
        "github_entities_non_empty",
        "github_metadata_non_empty",
        "no_unknown_artifact_ids",
        "metadata_rows_have_artifact_id",
        "metadata_rows_have_external_id",
        "metadata_rows_have_status",
        "metadata_status_values_valid",
        "metadata_provider_is_github",
        "found_count_non_empty",
    ]

    if strict:
        base.extend(
            [
                "metadata_rows_match_github_entities",
                "metadata_artifact_ids_match_github_entities",
                "no_duplicate_metadata_artifact_ids",
                "no_rate_limited_rows",
                "no_error_rows",
                "found_rows_have_http_200",
                "found_rows_have_some_useful_metadata",
            ]
        )

    return base


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# GitHub artifact enrichment check")
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
        if key.endswith("_sample") or key.endswith("_ids"):
            continue
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Status distribution")
    for key, value in report["summary"].get("status_distribution", {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Checks")
    for key, value in report["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Verdict")
    for key, value in report["verdict"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate GitHub artifact enrichment snapshot against extracted "
            "artifact_entities_latest.jsonl. This check does not call GitHub API "
            "and does not touch DB/canonical data."
        )
    )
    parser.add_argument(
        "--github-metadata-path",
        type=Path,
        default=DEFAULT_GITHUB_METADATA_PATH,
        help="Path to github_artifact_metadata_latest.jsonl",
    )
    parser.add_argument(
        "--artifact-entities-path",
        type=Path,
        default=DEFAULT_ARTIFACT_ENTITIES_PATH,
        help="Path to artifact_entities_latest.jsonl",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Directory for validation reports.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Require full coverage against GitHub entities and no rate-limited/error rows. "
            "not_found rows remain allowed."
        ),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    artifact_entities_exists = args.artifact_entities_path.exists()
    github_metadata_exists = args.github_metadata_path.exists()

    artifact_rows: list[dict[str, Any]] = []
    github_metadata_rows: list[dict[str, Any]] = []

    load_errors: list[str] = []

    if artifact_entities_exists:
        try:
            artifact_rows = load_jsonl(args.artifact_entities_path)
        except Exception as exc:
            load_errors.append(f"artifact_entities_load_error: {exc}")

    if github_metadata_exists:
        try:
            github_metadata_rows = load_jsonl(args.github_metadata_path)
        except Exception as exc:
            load_errors.append(f"github_metadata_load_error: {exc}")

    entity_summary = summarize_artifact_entities(artifact_rows)
    known_github_artifact_ids = entity_summary.pop("github_artifact_ids")
    metadata_summary = summarize_github_metadata(
        rows=github_metadata_rows,
        known_github_artifact_ids=known_github_artifact_ids,
    )

    summary: dict[str, Any] = {
        "artifact_entities_exists": artifact_entities_exists,
        "github_metadata_exists": github_metadata_exists,
        "load_errors_count": len(load_errors),
        "load_errors": load_errors,
        **entity_summary,
        **metadata_summary,
    }

    checks = build_checks(summary)
    checks["no_load_errors"] = len(load_errors) == 0

    required_check_names = build_required_check_names(strict=args.strict)
    required_check_names.append("no_load_errors")

    required_failed = [name for name in required_check_names if not checks.get(name, False)]

    verdict = {
        "ok": len(required_failed) == 0,
        "strict": bool(args.strict),
        "required_check_count": len(required_check_names),
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
    }

    report = {
        "report_name": "github_artifact_enrichment_check",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            "github_metadata_path": normalize_path(args.github_metadata_path),
            "artifact_entities_path": normalize_path(args.artifact_entities_path),
            "reports_dir": normalize_path(args.reports_dir),
        },
        "summary": summary,
        "checks": checks,
        "verdict": verdict,
    }

    latest_json = args.reports_dir / "github_artifact_enrichment_check_latest.json"
    latest_md = args.reports_dir / "github_artifact_enrichment_check_latest.md"
    hist_json = args.reports_dir / "history" / f"github_artifact_enrichment_check_{run_ts}.json"
    hist_md = args.reports_dir / "history" / f"github_artifact_enrichment_check_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] github_entities_count={summary['github_entities_count']}")
    print(f"[OK] metadata_rows_count={summary['metadata_rows_count']}")
    print(f"[OK] found_count={summary['found_count']}")
    print(f"[OK] not_found_count={summary['not_found_count']}")
    print(f"[OK] forbidden_count={summary['forbidden_count']}")
    print(f"[OK] rate_limited_count={summary['rate_limited_count']}")
    print(f"[OK] error_count={summary['error_count']}")
    print(f"[OK] duplicate_artifact_id_count={summary['duplicate_artifact_id_count']}")
    print(f"[OK] unknown_artifact_id_count={summary['unknown_artifact_id_count']}")
    print(f"[OK] strict={verdict['strict']}")
    print(f"[OK] ok={verdict['ok']}")
    print(f"[OK] required_failed_count={verdict['required_failed_count']}")
    print(f"[OK] required_failed_checks={verdict['required_failed_checks']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")

    if not verdict["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
