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
DEFAULT_HUGGINGFACE_METADATA_PATH = Path(
    "data/enriched/huggingface_artifacts/huggingface_artifact_metadata_latest.jsonl"
)
DEFAULT_REPORTS_DIR = Path("artifacts/reports/validation")

HF_ARTIFACT_TYPES = {
    "huggingface_model",
    "huggingface_dataset",
    "huggingface_space",
}

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


def summarize_artifact_entities(rows: list[dict[str, Any]]) -> dict[str, Any]:
    hf_rows = [
        row
        for row in rows
        if row.get("provider") == "huggingface"
        and row.get("artifact_type") in HF_ARTIFACT_TYPES
    ]

    hf_ids = [str(row.get("artifact_id") or "") for row in hf_rows]
    hf_ids_non_empty = [artifact_id for artifact_id in hf_ids if artifact_id]

    duplicate_ids = sorted(
        artifact_id
        for artifact_id, count in Counter(hf_ids_non_empty).items()
        if count > 1
    )

    missing_external_id = [
        str(row.get("artifact_id"))
        for row in hf_rows
        if not row.get("external_id")
    ]

    invalid_external_id = [
        {
            "artifact_id": row.get("artifact_id"),
            "artifact_type": row.get("artifact_type"),
            "external_id": row.get("external_id"),
            "normalized_url": row.get("normalized_url"),
        }
        for row in hf_rows
        if row.get("external_id")
        and "/" not in str(row.get("external_id"))
        and not str(row.get("external_id")).startswith(("datasets/", "spaces/"))
    ]

    artifact_type_distribution = Counter(
        str(row.get("artifact_type") or "missing_artifact_type")
        for row in hf_rows
    )

    return {
        "total_entities_count": len(rows),
        "huggingface_entities_count": len(hf_rows),
        "huggingface_artifact_ids_count": len(set(hf_ids_non_empty)),
        "huggingface_duplicate_artifact_ids_count": len(duplicate_ids),
        "huggingface_duplicate_artifact_ids_sample": duplicate_ids[:20],
        "huggingface_missing_external_id_count": len(missing_external_id),
        "huggingface_missing_external_id_sample": missing_external_id[:20],
        "huggingface_invalid_external_id_count": len(invalid_external_id),
        "huggingface_invalid_external_id_sample": invalid_external_id[:20],
        "huggingface_artifact_type_distribution": dict(sorted(artifact_type_distribution.items())),
        "huggingface_artifact_ids": set(hf_ids_non_empty),
    }


def summarize_huggingface_metadata(
    rows: list[dict[str, Any]],
    known_hf_artifact_ids: set[str],
) -> dict[str, Any]:
    artifact_ids = [str(row.get("artifact_id") or "") for row in rows]
    artifact_ids_non_empty = [artifact_id for artifact_id in artifact_ids if artifact_id]

    duplicate_ids = sorted(
        artifact_id
        for artifact_id, count in Counter(artifact_ids_non_empty).items()
        if count > 1
    )

    status_counts = Counter(str(row.get("status") or "missing_status") for row in rows)
    provider_counts = Counter(str(row.get("provider") or "missing_provider") for row in rows)
    repo_type_counts = Counter(str(row.get("repo_type") or "missing_repo_type") for row in rows)
    artifact_type_counts = Counter(str(row.get("artifact_type") or "missing_artifact_type") for row in rows)

    unknown_artifact_ids = sorted(set(artifact_ids_non_empty) - set(known_hf_artifact_ids))
    missing_artifact_id_rows = [i for i, row in enumerate(rows) if not row.get("artifact_id")]
    missing_external_id_rows = [
        str(row.get("artifact_id") or f"row_{i}")
        for i, row in enumerate(rows)
        if not row.get("external_id")
    ]
    missing_repo_id_rows = [
        str(row.get("artifact_id") or f"row_{i}")
        for i, row in enumerate(rows)
        if not row.get("repo_id")
    ]
    missing_status_rows = [
        str(row.get("artifact_id") or f"row_{i}")
        for i, row in enumerate(rows)
        if not row.get("status")
    ]
    invalid_status_rows = [
        {
            "artifact_id": row.get("artifact_id"),
            "status": row.get("status"),
        }
        for row in rows
        if row.get("status") and str(row.get("status")) not in VALID_STATUSES
    ]
    non_hf_provider_rows = [
        {
            "artifact_id": row.get("artifact_id"),
            "provider": row.get("provider"),
        }
        for row in rows
        if row.get("provider") != "huggingface"
    ]

    invalid_repo_type_rows = [
        {
            "artifact_id": row.get("artifact_id"),
            "repo_type": row.get("repo_type"),
        }
        for row in rows
        if row.get("repo_type") not in {"model", "dataset", "space"}
    ]

    found_rows = [row for row in rows if row.get("status") == "found"]

    found_missing_http_200 = [
        row.get("artifact_id")
        for row in found_rows
        if safe_int(row.get("http_status"), -1) != 200
    ]

    found_missing_useful_metadata = [
        row.get("artifact_id")
        for row in found_rows
        if (
            row.get("downloads") is None
            and row.get("likes") is None
            and not row.get("tags")
            and not row.get("license")
            and not row.get("pipeline_tag")
            and not row.get("library_name")
        )
    ]

    found_with_downloads = [row for row in found_rows if row.get("downloads") is not None]
    found_with_likes = [row for row in found_rows if row.get("likes") is not None]
    found_with_tags = [row for row in found_rows if row.get("tags")]
    found_with_license = [row for row in found_rows if row.get("license")]
    found_with_pipeline_tag = [row for row in found_rows if row.get("pipeline_tag")]
    found_with_library_name = [row for row in found_rows if row.get("library_name")]

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
        "missing_repo_id_count": len(missing_repo_id_rows),
        "missing_repo_id_sample": missing_repo_id_rows[:20],
        "missing_status_count": len(missing_status_rows),
        "missing_status_sample": missing_status_rows[:20],
        "invalid_status_count": len(invalid_status_rows),
        "invalid_status_sample": invalid_status_rows[:20],
        "non_huggingface_provider_count": len(non_hf_provider_rows),
        "non_huggingface_provider_sample": non_hf_provider_rows[:20],
        "invalid_repo_type_count": len(invalid_repo_type_rows),
        "invalid_repo_type_sample": invalid_repo_type_rows[:20],
        "provider_distribution": dict(sorted(provider_counts.items())),
        "repo_type_distribution": dict(sorted(repo_type_counts.items())),
        "artifact_type_distribution": dict(sorted(artifact_type_counts.items())),
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
        "found_with_downloads_count": len(found_with_downloads),
        "found_with_likes_count": len(found_with_likes),
        "found_with_tags_count": len(found_with_tags),
        "found_with_license_count": len(found_with_license),
        "found_with_pipeline_tag_count": len(found_with_pipeline_tag),
        "found_with_library_name_count": len(found_with_library_name),
    }


def build_checks(summary: dict[str, Any]) -> dict[str, bool]:
    return {
        "artifact_entities_exists": bool(summary["artifact_entities_exists"]),
        "huggingface_metadata_exists": bool(summary["huggingface_metadata_exists"]),
        "artifact_entities_non_empty": safe_int(summary["total_entities_count"]) > 0,
        "huggingface_entities_non_empty": safe_int(summary["huggingface_entities_count"]) > 0,
        "huggingface_metadata_non_empty": safe_int(summary["metadata_rows_count"]) > 0,
        "metadata_rows_match_huggingface_entities": (
            safe_int(summary["metadata_rows_count"])
            == safe_int(summary["huggingface_entities_count"])
            and safe_int(summary["huggingface_entities_count"]) > 0
        ),
        "metadata_artifact_ids_match_huggingface_entities": (
            safe_int(summary["metadata_artifact_ids_count"])
            == safe_int(summary["huggingface_artifact_ids_count"])
            and safe_int(summary["huggingface_artifact_ids_count"]) > 0
        ),
        "no_duplicate_metadata_artifact_ids": safe_int(summary["duplicate_artifact_id_count"]) == 0,
        "no_unknown_artifact_ids": safe_int(summary["unknown_artifact_id_count"]) == 0,
        "metadata_rows_have_artifact_id": safe_int(summary["missing_artifact_id_count"]) == 0,
        "metadata_rows_have_external_id": safe_int(summary["missing_external_id_count"]) == 0,
        "metadata_rows_have_repo_id": safe_int(summary["missing_repo_id_count"]) == 0,
        "metadata_rows_have_status": safe_int(summary["missing_status_count"]) == 0,
        "metadata_status_values_valid": safe_int(summary["invalid_status_count"]) == 0,
        "metadata_provider_is_huggingface": safe_int(summary["non_huggingface_provider_count"]) == 0,
        "metadata_repo_type_valid": safe_int(summary["invalid_repo_type_count"]) == 0,
        "found_count_non_empty": safe_int(summary["found_count"]) > 0,
        "no_rate_limited_rows": safe_int(summary["rate_limited_count"]) == 0,
        "no_error_rows": safe_int(summary["error_count"]) == 0,
        "found_rows_have_http_200": safe_int(summary["found_missing_http_200_count"]) == 0,
    }


def build_required_check_names(strict: bool) -> list[str]:
    base = [
        "artifact_entities_exists",
        "huggingface_metadata_exists",
        "artifact_entities_non_empty",
        "huggingface_entities_non_empty",
        "huggingface_metadata_non_empty",
        "no_unknown_artifact_ids",
        "metadata_rows_have_artifact_id",
        "metadata_rows_have_external_id",
        "metadata_rows_have_repo_id",
        "metadata_rows_have_status",
        "metadata_status_values_valid",
        "metadata_provider_is_huggingface",
        "metadata_repo_type_valid",
        "found_count_non_empty",
    ]

    if strict:
        base.extend(
            [
                "metadata_rows_match_huggingface_entities",
                "metadata_artifact_ids_match_huggingface_entities",
                "no_duplicate_metadata_artifact_ids",
                "no_rate_limited_rows",
                "no_error_rows",
                "found_rows_have_http_200",
            ]
        )

    return base


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Hugging Face artifact enrichment check")
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

    lines.append("## Repo type distribution")
    for key, value in report["summary"].get("repo_type_distribution", {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Artifact type distribution")
    for key, value in report["summary"].get("artifact_type_distribution", {}).items():
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
            "Validate Hugging Face artifact enrichment snapshot against extracted "
            "artifact_entities_latest.jsonl. This check does not call Hugging Face API "
            "and does not touch DB/canonical data."
        )
    )
    parser.add_argument(
        "--huggingface-metadata-path",
        type=Path,
        default=DEFAULT_HUGGINGFACE_METADATA_PATH,
        help="Path to huggingface_artifact_metadata_latest.jsonl",
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
            "Require full coverage against Hugging Face entities and no rate-limited/error rows. "
            "not_found rows remain allowed."
        ),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    artifact_entities_exists = args.artifact_entities_path.exists()
    hf_metadata_exists = args.huggingface_metadata_path.exists()

    artifact_rows: list[dict[str, Any]] = []
    hf_metadata_rows: list[dict[str, Any]] = []
    load_errors: list[str] = []

    if artifact_entities_exists:
        try:
            artifact_rows = load_jsonl(args.artifact_entities_path)
        except Exception as exc:
            load_errors.append(f"artifact_entities_load_error: {exc}")

    if hf_metadata_exists:
        try:
            hf_metadata_rows = load_jsonl(args.huggingface_metadata_path)
        except Exception as exc:
            load_errors.append(f"huggingface_metadata_load_error: {exc}")

    artifact_summary = summarize_artifact_entities(artifact_rows)
    metadata_summary = summarize_huggingface_metadata(
        hf_metadata_rows,
        known_hf_artifact_ids=artifact_summary["huggingface_artifact_ids"],
    )

    summary = {
        "artifact_entities_exists": artifact_entities_exists,
        "huggingface_metadata_exists": hf_metadata_exists,
        "load_errors": load_errors,
        **{
            k: v
            for k, v in artifact_summary.items()
            if k != "huggingface_artifact_ids"
        },
        **metadata_summary,
    }

    checks = build_checks(summary)
    required_check_names = build_required_check_names(strict=args.strict)

    if load_errors:
        checks["no_load_errors"] = False
        required_check_names.append("no_load_errors")
    else:
        checks["no_load_errors"] = True

    required_failed = [
        name
        for name in required_check_names
        if not checks.get(name, False)
    ]

    verdict = {
        "strict": bool(args.strict),
        "required_check_count": len(required_check_names),
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
        "ok": len(required_failed) == 0,
    }

    report = {
        "report_name": "huggingface_artifact_enrichment_check",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            "artifact_entities_path": normalize_path(args.artifact_entities_path),
            "huggingface_metadata_path": normalize_path(args.huggingface_metadata_path),
        },
        "summary": summary,
        "checks": checks,
        "verdict": verdict,
        "required_failed_count": verdict["required_failed_count"],
        "ok": verdict["ok"],
    }

    latest_json = args.reports_dir / "huggingface_artifact_enrichment_check_latest.json"
    latest_md = args.reports_dir / "huggingface_artifact_enrichment_check_latest.md"
    history_json = args.reports_dir / "history" / f"huggingface_artifact_enrichment_check_{run_ts}.json"
    history_md = args.reports_dir / "history" / f"huggingface_artifact_enrichment_check_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(history_json, report)
    dump_text(history_md, build_markdown(report))

    print(f"[OK] report JSON: {latest_json}")
    print(f"[OK] report MD: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history MD: {history_md}")

    print(f"[CHECK] huggingface_entities_count={summary['huggingface_entities_count']}")
    print(f"[CHECK] metadata_rows_count={summary['metadata_rows_count']}")
    print(f"[CHECK] found_count={summary['found_count']}")
    print(f"[CHECK] not_found_count={summary['not_found_count']}")
    print(f"[CHECK] forbidden_count={summary['forbidden_count']}")
    print(f"[CHECK] rate_limited_count={summary['rate_limited_count']}")
    print(f"[CHECK] error_count={summary['error_count']}")
    print(f"[CHECK] duplicate_artifact_id_count={summary['duplicate_artifact_id_count']}")
    print(f"[CHECK] unknown_artifact_id_count={summary['unknown_artifact_id_count']}")
    print(f"[CHECK] strict={bool(args.strict)}")
    print(f"[CHECK] required_failed_count={verdict['required_failed_count']}")
    print(f"[CHECK] required_failed_checks={verdict['required_failed_checks']}")
    print(f"[CHECK] ok={verdict['ok']}")

    if not verdict["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()