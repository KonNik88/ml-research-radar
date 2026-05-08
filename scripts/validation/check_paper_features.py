from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "PyYAML is required for configs/paper_features_v1.yaml."
    ) from exc


DEFAULT_CONFIG_PATH = Path("configs/paper_features_v1.yaml")
DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_FEATURES_PATH = Path("data/features/paper_features_latest.jsonl")
DEFAULT_BUILD_REPORT_PATH = Path("artifacts/reports/features/paper_features_latest.json")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/features")

SCORE_FIELDS = [
    "recency_score",
    "source_confidence_score",
    "implementation_readiness_score",
    "citation_signal_score",
    "radar_score",
]

NON_NEGATIVE_COUNT_FIELDS = [
    "source_count",
    "source_family_count",
    "trusted_artifact_links_count",
    "trusted_code_links_count",
    "trusted_dataset_links_count",
    "trusted_model_links_count",
    "trusted_demo_links_count",
    "github_repo_count",
    "github_found_repo_count",
    "github_not_found_repo_count",
    "github_stars_max",
    "github_stars_sum",
    "github_forks_max",
    "github_forks_sum",
    "hf_model_count",
    "hf_dataset_count",
    "hf_space_count",
    "hf_found_count",
    "hf_downloads_max",
    "hf_likes_max",
    "citation_count",
    "concepts_count",
]


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
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}

    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a YAML mapping: {path}")

    return payload


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def iter_jsonl(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line), line_number
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL: {path} line={line_number}: {exc}") from exc


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def count_canonical_rows(path: Path) -> int:
    return sum(1 for _row, _line_no in iter_jsonl(path))


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Paper features quality check")
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
        if key == "samples":
            continue
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

    samples = report["summary"].get("samples") or {}
    non_empty_samples = {key: value for key, value in samples.items() if value}
    if non_empty_samples:
        lines.append("## Samples")
        for key, value in non_empty_samples.items():
            lines.append(f"### {key}")
            lines.append("```json")
            lines.append(json.dumps(value, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")

    return "\n".join(lines)


def check_features(
    *,
    config_path: Path,
    canonical_path: Path,
    features_path: Path,
    build_report_path: Path,
    sample_limit: int,
) -> dict[str, Any]:
    config = load_yaml(config_path)
    required_fields = list(config.get("required_feature_fields") or [])

    canonical_rows_count = count_canonical_rows(canonical_path)
    build_report = load_json(build_report_path) if build_report_path.exists() else None

    rows_count = 0
    canonical_id_counts: Counter[str] = Counter()
    missing_canonical_id_count = 0
    missing_required_field_counts: Counter[str] = Counter()
    score_range_violations_count = 0
    non_negative_count_violations_count = 0
    source_family_pollution_count = 0
    malformed_source_families_count = 0
    malformed_provider_counts_count = 0
    malformed_type_counts_count = 0

    score_range_samples: list[dict[str, Any]] = []
    missing_required_samples: list[dict[str, Any]] = []
    source_family_pollution_samples: list[dict[str, Any]] = []
    count_violation_samples: list[dict[str, Any]] = []

    feature_schema_versions: Counter[str] = Counter()

    feature_coverage = {
        "has_arxiv_count": 0,
        "has_acl_count": 0,
        "has_doi_count": 0,
        "has_code_artifact_count": 0,
        "has_dataset_artifact_count": 0,
        "has_model_artifact_count": 0,
        "has_demo_artifact_count": 0,
        "github_found_repo_paper_count": 0,
        "hf_found_paper_count": 0,
    }

    for row, line_number in iter_jsonl(features_path):
        rows_count += 1

        canonical_id = row.get("canonical_id")
        if canonical_id:
            canonical_id_counts[str(canonical_id)] += 1
        else:
            missing_canonical_id_count += 1

        schema_version = row.get("schema_version")
        if schema_version:
            feature_schema_versions[str(schema_version)] += 1

        missing_fields = [field for field in required_fields if field not in row]
        if missing_fields:
            missing_required_field_counts.update(missing_fields)
            if len(missing_required_samples) < sample_limit:
                missing_required_samples.append(
                    {
                        "line_number": line_number,
                        "canonical_id": canonical_id,
                        "missing_fields": missing_fields,
                    }
                )

        for field in SCORE_FIELDS:
            value = safe_float(row.get(field), default=-1.0)
            if not (0.0 <= value <= 1.0):
                score_range_violations_count += 1
                if len(score_range_samples) < sample_limit:
                    score_range_samples.append(
                        {
                            "line_number": line_number,
                            "canonical_id": canonical_id,
                            "field": field,
                            "value": row.get(field),
                        }
                    )

        for field in NON_NEGATIVE_COUNT_FIELDS:
            value = safe_float(row.get(field), default=0.0)
            if value < 0:
                non_negative_count_violations_count += 1
                if len(count_violation_samples) < sample_limit:
                    count_violation_samples.append(
                        {
                            "line_number": line_number,
                            "canonical_id": canonical_id,
                            "field": field,
                            "value": row.get(field),
                        }
                    )

        source_families = row.get("source_families")
        if not isinstance(source_families, list):
            malformed_source_families_count += 1
        else:
            polluted = [
                str(item)
                for item in source_families
                if str(item).startswith("{") or str(item).startswith("[")
            ]
            if polluted:
                source_family_pollution_count += 1
                if len(source_family_pollution_samples) < sample_limit:
                    source_family_pollution_samples.append(
                        {
                            "line_number": line_number,
                            "canonical_id": canonical_id,
                            "source_families": source_families,
                        }
                    )

        if not isinstance(row.get("artifact_provider_counts"), dict):
            malformed_provider_counts_count += 1

        if not isinstance(row.get("artifact_type_counts"), dict):
            malformed_type_counts_count += 1

        if row.get("has_arxiv"):
            feature_coverage["has_arxiv_count"] += 1
        if row.get("has_acl"):
            feature_coverage["has_acl_count"] += 1
        if row.get("has_doi"):
            feature_coverage["has_doi_count"] += 1
        if row.get("has_code_artifact"):
            feature_coverage["has_code_artifact_count"] += 1
        if row.get("has_dataset_artifact"):
            feature_coverage["has_dataset_artifact_count"] += 1
        if row.get("has_model_artifact"):
            feature_coverage["has_model_artifact_count"] += 1
        if row.get("has_demo_artifact"):
            feature_coverage["has_demo_artifact_count"] += 1
        if safe_int(row.get("github_found_repo_count"), default=0) > 0:
            feature_coverage["github_found_repo_paper_count"] += 1
        if safe_int(row.get("hf_found_count"), default=0) > 0:
            feature_coverage["hf_found_paper_count"] += 1

    duplicate_canonical_ids = {
        canonical_id: count
        for canonical_id, count in canonical_id_counts.items()
        if count > 1
    }

    build_report_summary = (
        build_report.get("summary", {}) if isinstance(build_report, dict) else {}
    )
    build_report_rows_written = build_report_summary.get("rows_written")
    build_report_ok = bool(build_report_summary.get("ok")) if build_report_summary else False

    summary = {
        "canonical_rows_count": canonical_rows_count,
        "features_rows_count": rows_count,
        "build_report_exists": build_report is not None,
        "build_report_ok": build_report_ok,
        "build_report_rows_written": build_report_rows_written,
        "missing_canonical_id_count": missing_canonical_id_count,
        "duplicate_canonical_id_count": len(duplicate_canonical_ids),
        "missing_required_field_counts": dict(sorted(missing_required_field_counts.items())),
        "missing_required_fields_total": sum(missing_required_field_counts.values()),
        "score_range_violations_count": score_range_violations_count,
        "non_negative_count_violations_count": non_negative_count_violations_count,
        "source_family_pollution_count": source_family_pollution_count,
        "malformed_source_families_count": malformed_source_families_count,
        "malformed_provider_counts_count": malformed_provider_counts_count,
        "malformed_type_counts_count": malformed_type_counts_count,
        "feature_schema_versions": dict(sorted(feature_schema_versions.items())),
        "feature_coverage": feature_coverage,
        "samples": {
            "missing_required_fields": missing_required_samples,
            "score_range_violations": score_range_samples,
            "count_violations": count_violation_samples,
            "source_family_pollution": source_family_pollution_samples,
            "duplicate_canonical_ids": [
                {"canonical_id": canonical_id, "count": count}
                for canonical_id, count in list(sorted(duplicate_canonical_ids.items()))[:sample_limit]
            ],
        },
    }

    checks = {
        "canonical_exists": canonical_path.exists(),
        "features_exists": features_path.exists(),
        "build_report_exists": build_report is not None,
        "build_report_ok": build_report_ok,
        "features_rows_non_empty": rows_count > 0,
        "features_vs_canonical_rows_match": rows_count == canonical_rows_count,
        "build_report_rows_match_features": safe_int(build_report_rows_written, -1) == rows_count,
        "canonical_ids_present": missing_canonical_id_count == 0,
        "canonical_ids_unique": len(duplicate_canonical_ids) == 0,
        "required_fields_present": sum(missing_required_field_counts.values()) == 0,
        "scores_in_range": score_range_violations_count == 0,
        "counts_non_negative": non_negative_count_violations_count == 0,
        "source_families_shape_ok": malformed_source_families_count == 0,
        "source_families_not_polluted": source_family_pollution_count == 0,
        "artifact_provider_counts_shape_ok": malformed_provider_counts_count == 0,
        "artifact_type_counts_shape_ok": malformed_type_counts_count == 0,
    }

    required_check_names = [
        "canonical_exists",
        "features_exists",
        "build_report_exists",
        "build_report_ok",
        "features_rows_non_empty",
        "features_vs_canonical_rows_match",
        "build_report_rows_match_features",
        "canonical_ids_present",
        "canonical_ids_unique",
        "required_fields_present",
        "scores_in_range",
        "counts_non_negative",
        "source_families_shape_ok",
        "source_families_not_polluted",
        "artifact_provider_counts_shape_ok",
        "artifact_type_counts_shape_ok",
    ]

    required_failed_checks = [
        name for name in required_check_names if not checks.get(name, False)
    ]

    verdict = {
        "required_check_count": len(required_check_names),
        "required_failed_count": len(required_failed_checks),
        "required_failed_checks": required_failed_checks,
        "ok": len(required_failed_checks) == 0,
    }

    return {
        "summary": summary,
        "checks": checks,
        "verdict": verdict,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate paper_features_latest.jsonl as a derived feature contract."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument("--features-path", type=Path, default=DEFAULT_FEATURES_PATH)
    parser.add_argument("--build-report-path", type=Path, default=DEFAULT_BUILD_REPORT_PATH)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    result = check_features(
        config_path=args.config,
        canonical_path=args.canonical_path,
        features_path=args.features_path,
        build_report_path=args.build_report_path,
        sample_limit=max(1, args.sample_limit),
    )

    report = {
        "report_name": "paper_features_quality",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            "config_path": normalize_path(args.config),
            "canonical_path": normalize_path(args.canonical_path),
            "features_path": normalize_path(args.features_path),
            "build_report_path": normalize_path(args.build_report_path),
            "reports_dir": normalize_path(args.reports_dir),
        },
        "summary": result["summary"],
        "checks": result["checks"],
        "verdict": result["verdict"],
    }

    latest_json = args.reports_dir / "paper_features_quality_latest.json"
    latest_md = args.reports_dir / "paper_features_quality_latest.md"
    history_json = args.reports_dir / "history" / f"paper_features_quality_{run_ts}.json"
    history_md = args.reports_dir / "history" / f"paper_features_quality_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(history_json, report)
    dump_text(history_md, build_markdown(report))

    summary = report["summary"]
    verdict = report["verdict"]

    print(f"[OK] canonical_rows_count={summary['canonical_rows_count']}")
    print(f"[OK] features_rows_count={summary['features_rows_count']}")
    print(f"[OK] build_report_exists={summary['build_report_exists']}")
    print(f"[OK] build_report_ok={summary['build_report_ok']}")
    print(f"[OK] missing_canonical_id_count={summary['missing_canonical_id_count']}")
    print(f"[OK] duplicate_canonical_id_count={summary['duplicate_canonical_id_count']}")
    print(f"[OK] missing_required_fields_total={summary['missing_required_fields_total']}")
    print(f"[OK] score_range_violations_count={summary['score_range_violations_count']}")
    print(f"[OK] non_negative_count_violations_count={summary['non_negative_count_violations_count']}")
    print(f"[OK] source_family_pollution_count={summary['source_family_pollution_count']}")
    print(f"[OK] malformed_source_families_count={summary['malformed_source_families_count']}")
    print(f"[OK] malformed_provider_counts_count={summary['malformed_provider_counts_count']}")
    print(f"[OK] malformed_type_counts_count={summary['malformed_type_counts_count']}")

    for key, value in report["checks"].items():
        print(f"[OK] {key}={value}")

    print(f"[OK] ok={verdict['ok']}")
    print(f"[OK] required_failed_count={verdict['required_failed_count']}")
    print(f"[OK] required_failed_checks={verdict['required_failed_checks']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history Markdown: {history_md}")

    if args.strict and not verdict["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()