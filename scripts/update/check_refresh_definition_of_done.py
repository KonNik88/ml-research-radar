from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_MANIFEST_PATH = Path("artifacts/retrieval/manifests/latest.json")
DEFAULT_RETRIEVAL_CHECKS_PATH = Path(
    "artifacts/reports/validation/retrieval_checks_latest.json"
)
DEFAULT_POSTPASS_AUDIT_PATH = Path(
    "artifacts/reports/validation/postpass_audit_summary_latest.json"
)
DEFAULT_KNOWN_ISSUES_PATH = Path(
    "artifacts/reports/validation/known_issues_snapshot_latest.json"
)
DEFAULT_CANONICAL_CONTRACT_PATH = Path(
    "artifacts/reports/validation/canonical_contract_latest.json"
)

DEFAULT_ARTIFACT_QUALITY_PATH = Path(
    "artifacts/reports/validation/check_artifact_links_quality_latest.json"
)
DEFAULT_ARTIFACT_EXPORT_PATH = Path(
    "artifacts/reports/export/export_artifacts_postgres_v1_latest.json"
)
DEFAULT_ARTIFACT_DB_READ_PATH = Path(
    "artifacts/reports/export/test_artifact_db_read_latest.json"
)

DEFAULT_GITHUB_ENRICHMENT_CHECK_PATH = Path(
    "artifacts/reports/validation/github_artifact_enrichment_check_latest.json"
)
DEFAULT_HUGGINGFACE_ENRICHMENT_CHECK_PATH = Path(
    "artifacts/reports/validation/huggingface_artifact_enrichment_check_latest.json"
)

DEFAULT_PAPER_FEATURES_PATH = Path("data/features/paper_features_latest.jsonl")
DEFAULT_PAPER_FEATURES_QUALITY_PATH = Path(
    "artifacts/reports/features/paper_features_quality_latest.json"
)

DEFAULT_REPORTS_DIR = Path("artifacts/reports/update")


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


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return load_json(path)


def dig(data: Any, *keys: str, default: Any = None) -> Any:
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def first_present(
    data: dict[str, Any],
    paths: list[tuple[str, ...]],
    default: Any = None,
) -> Any:
    for path in paths:
        val = dig(data, *path, default=None)
        if val is not None:
            return val
    return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def report_ok(report: dict[str, Any] | None) -> bool:
    if report is None:
        return False

    if "ok" in report:
        return bool(report.get("ok"))

    verdict_ok = dig(report, "verdict", "ok", default=None)
    if verdict_ok is not None:
        return bool(verdict_ok)

    dod_passed = dig(report, "verdict", "dod_passed", default=None)
    if dod_passed is not None:
        return bool(dod_passed)

    required_failed_count = first_present(
        report,
        [
            ("required_failed_count",),
            ("verdict", "required_failed_count"),
        ],
        default=None,
    )
    if required_failed_count is not None:
        return safe_int(required_failed_count, default=999999) == 0

    return False


def summarize_canonical(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Canonical corpus not found: {path}")

    doc_count = 0
    multisource_docs = 0
    doi_count = 0
    max_source_count = 0

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            payload = json.loads(line)
            doc_count += 1

            source_count = int(payload.get("source_count", 0) or 0)
            if source_count > 1:
                multisource_docs += 1
            max_source_count = max(max_source_count, source_count)

            if payload.get("doi"):
                doi_count += 1

    return {
        "path": normalize_path(path),
        "doc_count": doc_count,
        "multisource_docs": multisource_docs,
        "doi_count": doi_count,
        "max_source_count": max_source_count,
    }


def run_db_smoke() -> dict[str, Any]:
    cmd = [sys.executable, "-m", "scripts.export.test_db_read"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    stdout = result.stdout or ""
    stderr = result.stderr or ""

    ping_match = re.search(r"Ping:\s*(True|False)", stdout)
    total_docs_match = re.search(r"Total docs:\s*(\d+)", stdout)

    return {
        "cmd": " ".join(cmd),
        "returncode": result.returncode,
        "ping": (ping_match.group(1) == "True") if ping_match else None,
        "total_docs": int(total_docs_match.group(1)) if total_docs_match else None,
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
        "ok": result.returncode == 0 and (ping_match is not None),
    }


def extract_postpass_values(postpass_audit: dict[str, Any]) -> dict[str, Any]:
    total_docs = first_present(
        postpass_audit,
        [
            ("total_docs",),
            ("summary", "total_docs"),
            ("corpus_summary", "total_docs"),
            ("audit_summary", "total_docs"),
        ],
    )

    merge_stats = first_present(
        postpass_audit,
        [
            ("merge_stats",),
            ("summary", "merge_stats"),
            ("corpus_summary", "merge_stats"),
            ("audit_summary", "merge_stats"),
        ],
        default={},
    ) or {}

    multi_source_docs = None
    if isinstance(merge_stats, dict):
        multi_source_docs = first_present(
            merge_stats,
            [
                ("multi_source_docs",),
                ("source_count_gt1_docs",),
            ],
        )

    return {
        "total_docs": total_docs,
        "merge_stats": merge_stats,
        "multi_source_docs": multi_source_docs,
    }


def extract_known_issues_values(known_issues: dict[str, Any] | None) -> dict[str, Any]:
    if known_issues is None:
        return {
            "canonical_corpus_doc_count": None,
            "retrieval_build_id": None,
        }

    canonical_corpus_doc_count = first_present(
        known_issues,
        [
            ("canonical_corpus_doc_count",),
            ("summary", "canonical_corpus_doc_count"),
            ("current_state", "canonical_corpus_doc_count"),
            ("snapshot", "canonical_corpus_doc_count"),
            ("operational_truth", "canonical_corpus_doc_count"),
        ],
    )

    retrieval_build_id = first_present(
        known_issues,
        [
            ("retrieval_build_id",),
            ("summary", "retrieval_build_id"),
            ("current_state", "retrieval_build_id"),
            ("snapshot", "retrieval_build_id"),
            ("operational_truth", "retrieval_build_id"),
            ("retrieval_findings", "build_id"),
        ],
    )

    return {
        "canonical_corpus_doc_count": canonical_corpus_doc_count,
        "retrieval_build_id": retrieval_build_id,
    }


def extract_canonical_contract_values(
    canonical_contract: dict[str, Any] | None,
) -> dict[str, Any]:
    report = canonical_contract or {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    verdict = report.get("verdict") if isinstance(report.get("verdict"), dict) else {}

    return {
        "canonical_contract_ok": report_ok(canonical_contract),
        "canonical_contract_rows_count": summary.get("rows_count"),
        "canonical_contract_valid_rows_count": summary.get("valid_rows_count"),
        "canonical_contract_bad_rows_count": summary.get("bad_rows_count"),
        "canonical_contract_extra_fields_count": summary.get("extra_fields_count"),
        "canonical_contract_extra_field_rows_count": summary.get("extra_field_rows_count"),
        "canonical_contract_missing_canonical_id_count": summary.get(
            "missing_canonical_id_count"
        ),
        "canonical_contract_duplicate_canonical_id_count": summary.get(
            "duplicate_canonical_id_count"
        ),
        "canonical_contract_duplicate_doc_id_values_across_canonical_count": summary.get(
            "duplicate_doc_id_values_across_canonical_count"
        ),
        "canonical_contract_doc_ids_not_list_count": summary.get("doc_ids_not_list_count"),
        "canonical_contract_duplicate_doc_ids_within_row_count": summary.get(
            "duplicate_doc_ids_within_row_count"
        ),
        "canonical_contract_required_failed_count": verdict.get("required_failed_count"),
        "canonical_contract_required_failed_checks": verdict.get("required_failed_checks"),
    }


def extract_artifact_values(
    artifact_quality: dict[str, Any] | None,
    artifact_export: dict[str, Any] | None,
    artifact_db_read: dict[str, Any] | None,
) -> dict[str, Any]:
    quality = artifact_quality or {}
    export = artifact_export or {}
    db_read = artifact_db_read or {}

    return {
        "artifact_quality_ok": report_ok(artifact_quality),
        "artifact_quality_required_failed_count": first_present(
            quality,
            [
                ("required_failed_count",),
                ("verdict", "required_failed_count"),
            ],
        ),
        "artifact_quality_entities_count": first_present(
            quality,
            [
                ("entities_count",),
                ("summary", "entities_count"),
            ],
        ),
        "artifact_quality_observations_count": first_present(
            quality,
            [
                ("observations_count",),
                ("summary", "observations_count"),
            ],
        ),
        "artifact_quality_trusted_links_count": first_present(
            quality,
            [
                ("trusted_unique_paper_artifact_links_count",),
                ("trusted_paper_artifact_links_count",),
                ("summary", "trusted_unique_paper_artifact_links_count"),
                ("summary", "trusted_paper_artifact_links_count"),
            ],
        ),
        "artifact_export_ok": report_ok(artifact_export),
        "artifact_export_raw_entities_count": export.get("raw_entities_count"),
        "artifact_export_db_entities_count": export.get("db_entities_count"),
        "artifact_export_observations_count": export.get("observations_count"),
        "artifact_export_trusted_links_count": export.get(
            "trusted_paper_artifact_links_count"
        ),
        "artifact_export_entities_db_count": export.get("artifact_entities_db_count"),
        "artifact_export_observations_db_count": export.get(
            "artifact_observations_db_count"
        ),
        "artifact_export_links_db_count": export.get("paper_artifact_links_db_count"),
        "artifact_db_read_ok": report_ok(artifact_db_read),
        "artifact_db_read_entities_count": db_read.get("artifact_entities_count"),
        "artifact_db_read_observations_count": db_read.get("artifact_observations_count"),
        "artifact_db_read_links_count": db_read.get("paper_artifact_links_count"),
        "artifact_db_read_join_links_count": db_read.get(
            "join_canonical_artifact_entities_count"
        ),
        "artifact_db_read_required_failed_count": db_read.get("required_failed_count"),
    }


def extract_github_enrichment_values(
    github_enrichment_check: dict[str, Any] | None,
) -> dict[str, Any]:
    report = github_enrichment_check or {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}

    github_entities_count = first_present(
        report,
        [("summary", "github_entities_count"), ("github_entities_count",)],
    )
    metadata_rows_count = first_present(
        report,
        [("summary", "metadata_rows_count"), ("metadata_rows_count",)],
    )
    found_count = first_present(report, [("summary", "found_count"), ("found_count",)])
    not_found_count = first_present(
        report, [("summary", "not_found_count"), ("not_found_count",)]
    )
    forbidden_count = first_present(
        report, [("summary", "forbidden_count"), ("forbidden_count",)]
    )
    rate_limited_count = first_present(
        report,
        [("summary", "rate_limited_count"), ("rate_limited_count",)],
    )
    error_count = first_present(report, [("summary", "error_count"), ("error_count",)])
    duplicate_artifact_id_count = first_present(
        report,
        [("summary", "duplicate_artifact_id_count"), ("duplicate_artifact_id_count",)],
    )
    unknown_artifact_id_count = first_present(
        report,
        [("summary", "unknown_artifact_id_count"), ("unknown_artifact_id_count",)],
    )

    metadata_vs_entities_match = checks.get("metadata_vs_github_entities_count_match")
    if metadata_vs_entities_match is None:
        metadata_vs_entities_match = (
            safe_int(metadata_rows_count) == safe_int(github_entities_count)
            and safe_int(github_entities_count) > 0
        )

    return {
        "github_enrichment_check_ok": report_ok(github_enrichment_check),
        "github_enrichment_required_failed_count": first_present(
            report,
            [("required_failed_count",), ("verdict", "required_failed_count")],
        ),
        "github_enrichment_strict": first_present(
            report,
            [("strict",), ("verdict", "strict")],
        ),
        "github_enrichment_github_entities_count": github_entities_count,
        "github_enrichment_metadata_rows_count": metadata_rows_count,
        "github_enrichment_found_count": found_count,
        "github_enrichment_not_found_count": not_found_count,
        "github_enrichment_forbidden_count": forbidden_count,
        "github_enrichment_rate_limited_count": rate_limited_count,
        "github_enrichment_error_count": error_count,
        "github_enrichment_duplicate_artifact_id_count": duplicate_artifact_id_count,
        "github_enrichment_unknown_artifact_id_count": unknown_artifact_id_count,
        "github_enrichment_metadata_vs_entities_match": metadata_vs_entities_match,
        "github_enrichment_status_distribution": summary.get("status_distribution"),
    }


def extract_huggingface_enrichment_values(
    huggingface_enrichment_check: dict[str, Any] | None,
) -> dict[str, Any]:
    report = huggingface_enrichment_check or {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}

    huggingface_entities_count = first_present(
        report,
        [
            ("summary", "huggingface_entities_count"),
            ("huggingface_entities_count",),
        ],
    )
    metadata_rows_count = first_present(
        report,
        [
            ("summary", "metadata_rows_count"),
            ("metadata_rows_count",),
        ],
    )
    found_count = first_present(report, [("summary", "found_count"), ("found_count",)])
    not_found_count = first_present(
        report, [("summary", "not_found_count"), ("not_found_count",)]
    )
    forbidden_count = first_present(
        report, [("summary", "forbidden_count"), ("forbidden_count",)]
    )
    skipped_invalid_external_id_count = first_present(
        report,
        [
            ("summary", "skipped_invalid_external_id_count"),
            ("skipped_invalid_external_id_count",),
        ],
    )
    rate_limited_count = first_present(
        report,
        [("summary", "rate_limited_count"), ("rate_limited_count",)],
    )
    error_count = first_present(report, [("summary", "error_count"), ("error_count",)])
    duplicate_artifact_id_count = first_present(
        report,
        [("summary", "duplicate_artifact_id_count"), ("duplicate_artifact_id_count",)],
    )
    unknown_artifact_id_count = first_present(
        report,
        [("summary", "unknown_artifact_id_count"), ("unknown_artifact_id_count",)],
    )

    metadata_vs_entities_match = checks.get("metadata_rows_match_huggingface_entities")
    if metadata_vs_entities_match is None:
        metadata_vs_entities_match = (
            safe_int(metadata_rows_count) == safe_int(huggingface_entities_count)
            and safe_int(huggingface_entities_count) > 0
        )

    return {
        "huggingface_enrichment_check_ok": report_ok(huggingface_enrichment_check),
        "huggingface_enrichment_required_failed_count": first_present(
            report,
            [("required_failed_count",), ("verdict", "required_failed_count")],
        ),
        "huggingface_enrichment_strict": first_present(
            report,
            [("strict",), ("verdict", "strict")],
        ),
        "huggingface_enrichment_huggingface_entities_count": huggingface_entities_count,
        "huggingface_enrichment_metadata_rows_count": metadata_rows_count,
        "huggingface_enrichment_found_count": found_count,
        "huggingface_enrichment_not_found_count": not_found_count,
        "huggingface_enrichment_forbidden_count": forbidden_count,
        "huggingface_enrichment_skipped_invalid_external_id_count": (
            skipped_invalid_external_id_count
        ),
        "huggingface_enrichment_rate_limited_count": rate_limited_count,
        "huggingface_enrichment_error_count": error_count,
        "huggingface_enrichment_duplicate_artifact_id_count": duplicate_artifact_id_count,
        "huggingface_enrichment_unknown_artifact_id_count": unknown_artifact_id_count,
        "huggingface_enrichment_metadata_vs_entities_match": metadata_vs_entities_match,
        "huggingface_enrichment_status_distribution": summary.get("status_distribution"),
    }


def extract_paper_features_values(
    paper_features_quality: dict[str, Any] | None,
) -> dict[str, Any]:
    report = paper_features_quality or {}

    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
    verdict = report.get("verdict") if isinstance(report.get("verdict"), dict) else {}

    return {
        "paper_features_quality_ok": report_ok(paper_features_quality),
        "paper_features_required_failed_count": verdict.get("required_failed_count"),
        "paper_features_required_failed_checks": verdict.get("required_failed_checks"),
        "paper_features_canonical_rows_count": summary.get("canonical_rows_count"),
        "paper_features_rows_count": summary.get("features_rows_count"),
        "paper_features_build_report_exists": summary.get("build_report_exists"),
        "paper_features_build_report_ok": summary.get("build_report_ok"),
        "paper_features_build_report_rows_written": summary.get("build_report_rows_written"),
        "paper_features_missing_canonical_id_count": summary.get(
            "missing_canonical_id_count"
        ),
        "paper_features_duplicate_canonical_id_count": summary.get(
            "duplicate_canonical_id_count"
        ),
        "paper_features_missing_required_fields_total": summary.get(
            "missing_required_fields_total"
        ),
        "paper_features_score_range_violations_count": summary.get(
            "score_range_violations_count"
        ),
        "paper_features_non_negative_count_violations_count": summary.get(
            "non_negative_count_violations_count"
        ),
        "paper_features_source_family_pollution_count": summary.get(
            "source_family_pollution_count"
        ),
        "paper_features_malformed_source_families_count": summary.get(
            "malformed_source_families_count"
        ),
        "paper_features_malformed_provider_counts_count": summary.get(
            "malformed_provider_counts_count"
        ),
        "paper_features_malformed_type_counts_count": summary.get(
            "malformed_type_counts_count"
        ),
        "paper_features_features_vs_canonical_rows_match": checks.get(
            "features_vs_canonical_rows_match"
        ),
        "paper_features_build_report_rows_match_features": checks.get(
            "build_report_rows_match_features"
        ),
        "paper_features_canonical_ids_present": checks.get("canonical_ids_present"),
        "paper_features_canonical_ids_unique": checks.get("canonical_ids_unique"),
        "paper_features_required_fields_present": checks.get("required_fields_present"),
        "paper_features_scores_in_range": checks.get("scores_in_range"),
        "paper_features_counts_non_negative": checks.get("counts_non_negative"),
        "paper_features_source_families_shape_ok": checks.get("source_families_shape_ok"),
        "paper_features_source_families_not_polluted": checks.get(
            "source_families_not_polluted"
        ),
        "paper_features_artifact_provider_counts_shape_ok": checks.get(
            "artifact_provider_counts_shape_ok"
        ),
        "paper_features_artifact_type_counts_shape_ok": checks.get(
            "artifact_type_counts_shape_ok"
        ),
    }


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Refresh Definition of Done check")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append("")

    lines.append("## Inputs")
    for k, v in report["inputs"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    lines.append("## Canonical summary")
    for k, v in report["canonical_summary"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    lines.append("## Extracted values")
    for k, v in report["extracted_values"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    lines.append("## Checks")
    for k, v in report["checks"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    lines.append("## Verdict")
    for k, v in report["verdict"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    if report.get("db_smoke"):
        lines.append("## DB smoke")
        db = report["db_smoke"]
        for k in ("cmd", "returncode", "ping", "total_docs", "ok"):
            lines.append(f"- {k}: `{db.get(k)}`")
        lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Check refresh Definition of Done against canonical, canonical contract, "
            "DB, retrieval, validation, optional artifact outputs, optional "
            "GitHub/Hugging Face enrichment checks, and optional paper_features "
            "derived layer quality."
        )
    )
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument(
        "--retrieval-checks-path",
        type=Path,
        default=DEFAULT_RETRIEVAL_CHECKS_PATH,
    )
    parser.add_argument(
        "--postpass-audit-path",
        type=Path,
        default=DEFAULT_POSTPASS_AUDIT_PATH,
    )
    parser.add_argument("--known-issues-path", type=Path, default=DEFAULT_KNOWN_ISSUES_PATH)
    parser.add_argument(
        "--canonical-contract-path",
        type=Path,
        default=DEFAULT_CANONICAL_CONTRACT_PATH,
        help="CanonicalDocument contract validation report path.",
    )

    parser.add_argument(
        "--artifact-quality-path",
        type=Path,
        default=DEFAULT_ARTIFACT_QUALITY_PATH,
    )
    parser.add_argument(
        "--artifact-export-path",
        type=Path,
        default=DEFAULT_ARTIFACT_EXPORT_PATH,
    )
    parser.add_argument(
        "--artifact-db-read-path",
        type=Path,
        default=DEFAULT_ARTIFACT_DB_READ_PATH,
    )

    parser.add_argument(
        "--github-enrichment-check-path",
        type=Path,
        default=DEFAULT_GITHUB_ENRICHMENT_CHECK_PATH,
        help="GitHub artifact enrichment validation report path.",
    )
    parser.add_argument(
        "--huggingface-enrichment-check-path",
        type=Path,
        default=DEFAULT_HUGGINGFACE_ENRICHMENT_CHECK_PATH,
        help="Hugging Face artifact enrichment validation report path.",
    )

    parser.add_argument(
        "--paper-features-path",
        type=Path,
        default=DEFAULT_PAPER_FEATURES_PATH,
        help="paper_features latest JSONL path.",
    )
    parser.add_argument(
        "--paper-features-quality-path",
        type=Path,
        default=DEFAULT_PAPER_FEATURES_QUALITY_PATH,
        help="paper_features quality validation report path.",
    )

    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)

    parser.add_argument(
        "--require-known-issues",
        action="store_true",
        help=(
            "Treat known_issues_snapshot presence and consistency as a required "
            "DoD condition."
        ),
    )
    parser.add_argument(
        "--require-artifacts",
        action="store_true",
        help="Treat artifact quality/export/DB smoke reports as required DoD conditions.",
    )
    parser.add_argument(
        "--require-github-enrichment",
        action="store_true",
        help=(
            "Treat GitHub artifact enrichment validation as a required DoD condition. "
            "This is intentionally separate from --require-artifacts because GitHub "
            "is an optional external enrichment layer."
        ),
    )
    parser.add_argument(
        "--require-huggingface-enrichment",
        action="store_true",
        help=(
            "Treat Hugging Face artifact enrichment validation as a required DoD "
            "condition. This is intentionally separate from --require-artifacts "
            "because Hugging Face is an optional external enrichment layer."
        ),
    )
    parser.add_argument(
        "--require-paper-features",
        action="store_true",
        help="Treat paper_features derived layer quality as a required DoD condition.",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    canonical_summary = summarize_canonical(args.canonical_path)

    manifest = load_json(args.manifest_path)
    retrieval_checks = load_json(args.retrieval_checks_path)
    postpass_audit = load_json(args.postpass_audit_path)

    known_issues = load_json_if_exists(args.known_issues_path)
    known_issues_exists = known_issues is not None

    canonical_contract = load_json_if_exists(args.canonical_contract_path)
    canonical_contract_exists = canonical_contract is not None
    canonical_contract_values = extract_canonical_contract_values(canonical_contract)

    artifact_quality = load_json_if_exists(args.artifact_quality_path)
    artifact_export = load_json_if_exists(args.artifact_export_path)
    artifact_db_read = load_json_if_exists(args.artifact_db_read_path)

    artifact_quality_exists = artifact_quality is not None
    artifact_export_exists = artifact_export is not None
    artifact_db_read_exists = artifact_db_read is not None

    artifact_values = extract_artifact_values(
        artifact_quality=artifact_quality,
        artifact_export=artifact_export,
        artifact_db_read=artifact_db_read,
    )

    github_enrichment_check = load_json_if_exists(args.github_enrichment_check_path)
    github_enrichment_check_exists = github_enrichment_check is not None
    github_enrichment_values = extract_github_enrichment_values(github_enrichment_check)

    huggingface_enrichment_check = load_json_if_exists(
        args.huggingface_enrichment_check_path
    )
    huggingface_enrichment_check_exists = huggingface_enrichment_check is not None
    huggingface_enrichment_values = extract_huggingface_enrichment_values(
        huggingface_enrichment_check
    )

    paper_features_exists = args.paper_features_path.exists()
    paper_features_quality = load_json_if_exists(args.paper_features_quality_path)
    paper_features_quality_exists = paper_features_quality is not None
    paper_features_values = extract_paper_features_values(paper_features_quality)

    db_smoke = run_db_smoke()

    manifest_doc_count = manifest.get("corpus_doc_count")
    manifest_build_id = manifest.get("build_id")

    retrieval_checks_doc_count = retrieval_checks.get("corpus_doc_count")
    retrieval_checks_build_id = retrieval_checks.get("build_id")

    postpass_values = extract_postpass_values(postpass_audit)
    postpass_total_docs = postpass_values["total_docs"]
    postpass_multisource_docs = postpass_values["multi_source_docs"]

    known_issues_values = extract_known_issues_values(known_issues)
    known_issues_doc_count = known_issues_values["canonical_corpus_doc_count"]
    known_issues_build_id = known_issues_values["retrieval_build_id"]

    canonical_contract_rows_count = safe_int(
        canonical_contract_values["canonical_contract_rows_count"],
        default=-1,
    )
    canonical_contract_bad_rows_count = safe_int(
        canonical_contract_values["canonical_contract_bad_rows_count"],
        default=999999,
    )
    canonical_contract_extra_fields_count = safe_int(
        canonical_contract_values["canonical_contract_extra_fields_count"],
        default=999999,
    )
    canonical_contract_missing_canonical_id_count = safe_int(
        canonical_contract_values["canonical_contract_missing_canonical_id_count"],
        default=999999,
    )
    canonical_contract_duplicate_canonical_id_count = safe_int(
        canonical_contract_values["canonical_contract_duplicate_canonical_id_count"],
        default=999999,
    )
    canonical_contract_doc_ids_not_list_count = safe_int(
        canonical_contract_values["canonical_contract_doc_ids_not_list_count"],
        default=999999,
    )
    canonical_contract_duplicate_doc_ids_within_row_count = safe_int(
        canonical_contract_values["canonical_contract_duplicate_doc_ids_within_row_count"],
        default=999999,
    )

    paper_features_rows_count = safe_int(
        paper_features_values["paper_features_rows_count"],
        default=-1,
    )
    paper_features_canonical_rows_count = safe_int(
        paper_features_values["paper_features_canonical_rows_count"],
        default=-1,
    )

    checks = {
        # canonical / retrieval / DB baseline
        "canonical_exists": args.canonical_path.exists(),
        "manifest_exists": args.manifest_path.exists(),
        "retrieval_checks_exists": args.retrieval_checks_path.exists(),
        "postpass_audit_exists": args.postpass_audit_path.exists(),
        "db_smoke_ok": db_smoke["ok"],
        "db_ping_true": db_smoke["ping"] is True,
        "canonical_vs_manifest_doc_count_match": (
            canonical_summary["doc_count"] == manifest_doc_count
        ),
        "canonical_vs_retrieval_checks_doc_count_match": (
            canonical_summary["doc_count"] == retrieval_checks_doc_count
        ),
        "canonical_vs_postpass_doc_count_match": (
            canonical_summary["doc_count"] == postpass_total_docs
        ),
        "canonical_vs_postpass_multisource_match": (
            canonical_summary["multisource_docs"] == postpass_multisource_docs
        ),
        "manifest_vs_retrieval_checks_build_id_match": (
            manifest_build_id == retrieval_checks_build_id
        ),
        "canonical_vs_db_doc_count_match": (
            canonical_summary["doc_count"] == db_smoke["total_docs"]
        ),

        # required canonical contract block
        "canonical_contract_exists": canonical_contract_exists,
        "canonical_contract_ok": canonical_contract_values["canonical_contract_ok"],
        "canonical_contract_rows_count_match": (
            canonical_contract_rows_count == canonical_summary["doc_count"]
        ),
        "canonical_contract_no_bad_rows": canonical_contract_bad_rows_count == 0,
        "canonical_contract_no_extra_fields": canonical_contract_extra_fields_count == 0,
        "canonical_contract_no_missing_canonical_id": (
            canonical_contract_missing_canonical_id_count == 0
        ),
        "canonical_contract_no_duplicate_canonical_id": (
            canonical_contract_duplicate_canonical_id_count == 0
        ),
        "canonical_contract_doc_ids_shape_ok": (
            canonical_contract_doc_ids_not_list_count == 0
        ),
        "canonical_contract_no_duplicate_doc_ids_within_row": (
            canonical_contract_duplicate_doc_ids_within_row_count == 0
        ),

        # optional known issues block
        "known_issues_exists": known_issues_exists,
        "canonical_vs_known_issues_doc_count_match": (
            known_issues_doc_count == canonical_summary["doc_count"]
            if known_issues is not None
            else False
        ),
        "manifest_vs_known_issues_build_id_match": (
            known_issues_build_id == manifest_build_id
            if known_issues is not None
            else False
        ),

        # optional artifact block
        "artifact_quality_exists": artifact_quality_exists,
        "artifact_quality_ok": artifact_values["artifact_quality_ok"],
        "artifact_export_exists": artifact_export_exists,
        "artifact_export_ok": artifact_values["artifact_export_ok"],
        "artifact_db_read_exists": artifact_db_read_exists,
        "artifact_db_read_ok": artifact_values["artifact_db_read_ok"],
        "artifact_entities_db_non_empty": (
            safe_int(artifact_values["artifact_db_read_entities_count"]) > 0
        ),
        "artifact_observations_db_non_empty": (
            safe_int(artifact_values["artifact_db_read_observations_count"]) > 0
        ),
        "paper_artifact_links_db_non_empty": (
            safe_int(artifact_values["artifact_db_read_links_count"]) > 0
        ),
        "artifact_links_join_all_rows": (
            safe_int(artifact_values["artifact_db_read_join_links_count"])
            == safe_int(artifact_values["artifact_db_read_links_count"])
            and safe_int(artifact_values["artifact_db_read_links_count"]) > 0
        ),
        "artifact_export_vs_db_entities_match": (
            safe_int(artifact_values["artifact_export_entities_db_count"])
            == safe_int(artifact_values["artifact_db_read_entities_count"])
            and safe_int(artifact_values["artifact_db_read_entities_count"]) > 0
        ),
        "artifact_export_vs_db_observations_match": (
            safe_int(artifact_values["artifact_export_observations_db_count"])
            == safe_int(artifact_values["artifact_db_read_observations_count"])
            and safe_int(artifact_values["artifact_db_read_observations_count"]) > 0
        ),
        "artifact_export_vs_db_links_match": (
            safe_int(artifact_values["artifact_export_links_db_count"])
            == safe_int(artifact_values["artifact_db_read_links_count"])
            and safe_int(artifact_values["artifact_db_read_links_count"]) > 0
        ),
        "artifact_quality_vs_export_entities_match": (
            safe_int(artifact_values["artifact_quality_entities_count"])
            == safe_int(artifact_values["artifact_export_raw_entities_count"])
            and safe_int(artifact_values["artifact_export_raw_entities_count"]) > 0
        ),
        "artifact_quality_vs_export_observations_match": (
            safe_int(artifact_values["artifact_quality_observations_count"])
            == safe_int(artifact_values["artifact_export_observations_count"])
            and safe_int(artifact_values["artifact_export_observations_count"]) > 0
        ),
        "artifact_quality_vs_export_links_match": (
            safe_int(artifact_values["artifact_quality_trusted_links_count"])
            == safe_int(artifact_values["artifact_export_trusted_links_count"])
            and safe_int(artifact_values["artifact_export_trusted_links_count"]) > 0
        ),

        # optional GitHub enrichment block
        "github_enrichment_check_exists": github_enrichment_check_exists,
        "github_enrichment_check_ok": github_enrichment_values[
            "github_enrichment_check_ok"
        ],
        "github_enrichment_rows_non_empty": (
            safe_int(github_enrichment_values["github_enrichment_metadata_rows_count"])
            > 0
        ),
        "github_enrichment_found_non_empty": (
            safe_int(github_enrichment_values["github_enrichment_found_count"]) > 0
        ),
        "github_enrichment_no_rate_limited": (
            safe_int(github_enrichment_values["github_enrichment_rate_limited_count"])
            == 0
        ),
        "github_enrichment_no_errors": (
            safe_int(github_enrichment_values["github_enrichment_error_count"]) == 0
        ),
        "github_enrichment_metadata_vs_entities_match": bool(
            github_enrichment_values["github_enrichment_metadata_vs_entities_match"]
        ),
        "github_enrichment_no_unknown_artifact_ids": (
            safe_int(github_enrichment_values["github_enrichment_unknown_artifact_id_count"])
            == 0
        ),
        "github_enrichment_no_duplicate_artifact_ids": (
            safe_int(
                github_enrichment_values["github_enrichment_duplicate_artifact_id_count"]
            )
            == 0
        ),
        # Diagnostic only for current policy. Not required below.
        "github_enrichment_no_forbidden": (
            safe_int(github_enrichment_values["github_enrichment_forbidden_count"]) == 0
        ),

        # optional Hugging Face enrichment block
        "huggingface_enrichment_check_exists": huggingface_enrichment_check_exists,
        "huggingface_enrichment_check_ok": huggingface_enrichment_values[
            "huggingface_enrichment_check_ok"
        ],
        "huggingface_enrichment_rows_non_empty": (
            safe_int(
                huggingface_enrichment_values[
                    "huggingface_enrichment_metadata_rows_count"
                ]
            )
            > 0
        ),
        "huggingface_enrichment_found_non_empty": (
            safe_int(huggingface_enrichment_values["huggingface_enrichment_found_count"])
            > 0
        ),
        "huggingface_enrichment_no_rate_limited": (
            safe_int(
                huggingface_enrichment_values[
                    "huggingface_enrichment_rate_limited_count"
                ]
            )
            == 0
        ),
        "huggingface_enrichment_no_errors": (
            safe_int(huggingface_enrichment_values["huggingface_enrichment_error_count"])
            == 0
        ),
        "huggingface_enrichment_metadata_vs_entities_match": bool(
            huggingface_enrichment_values[
                "huggingface_enrichment_metadata_vs_entities_match"
            ]
        ),
        "huggingface_enrichment_no_unknown_artifact_ids": (
            safe_int(
                huggingface_enrichment_values[
                    "huggingface_enrichment_unknown_artifact_id_count"
                ]
            )
            == 0
        ),
        "huggingface_enrichment_no_duplicate_artifact_ids": (
            safe_int(
                huggingface_enrichment_values[
                    "huggingface_enrichment_duplicate_artifact_id_count"
                ]
            )
            == 0
        ),
        # Diagnostic only: forbidden/skipped_invalid are allowed provider/extraction states.
        "huggingface_enrichment_no_forbidden": (
            safe_int(huggingface_enrichment_values["huggingface_enrichment_forbidden_count"])
            == 0
        ),
        "huggingface_enrichment_no_skipped_invalid_external_ids": (
            safe_int(
                huggingface_enrichment_values[
                    "huggingface_enrichment_skipped_invalid_external_id_count"
                ]
            )
            == 0
        ),

        # optional paper_features derived layer block
        "paper_features_exists": paper_features_exists,
        "paper_features_quality_exists": paper_features_quality_exists,
        "paper_features_quality_ok": paper_features_values["paper_features_quality_ok"],
        "paper_features_rows_match_canonical": (
            paper_features_rows_count == canonical_summary["doc_count"]
        ),
        "paper_features_quality_canonical_rows_match": (
            paper_features_canonical_rows_count == canonical_summary["doc_count"]
        ),
        "paper_features_build_report_exists": bool(
            paper_features_values["paper_features_build_report_exists"]
        ),
        "paper_features_build_report_ok": bool(
            paper_features_values["paper_features_build_report_ok"]
        ),
        "paper_features_build_report_rows_match": bool(
            paper_features_values["paper_features_build_report_rows_match_features"]
        ),
        "paper_features_no_missing_canonical_id": (
            safe_int(
                paper_features_values["paper_features_missing_canonical_id_count"],
                default=999999,
            )
            == 0
        ),
        "paper_features_no_duplicate_canonical_id": (
            safe_int(
                paper_features_values["paper_features_duplicate_canonical_id_count"],
                default=999999,
            )
            == 0
        ),
        "paper_features_required_fields_present": bool(
            paper_features_values["paper_features_required_fields_present"]
        ),
        "paper_features_scores_in_range": bool(
            paper_features_values["paper_features_scores_in_range"]
        ),
        "paper_features_counts_non_negative": bool(
            paper_features_values["paper_features_counts_non_negative"]
        ),
        "paper_features_source_families_shape_ok": bool(
            paper_features_values["paper_features_source_families_shape_ok"]
        ),
        "paper_features_source_families_not_polluted": bool(
            paper_features_values["paper_features_source_families_not_polluted"]
        ),
        "paper_features_artifact_provider_counts_shape_ok": bool(
            paper_features_values["paper_features_artifact_provider_counts_shape_ok"]
        ),
        "paper_features_artifact_type_counts_shape_ok": bool(
            paper_features_values["paper_features_artifact_type_counts_shape_ok"]
        ),
    }

    required_check_names = [
        "canonical_exists",
        "manifest_exists",
        "retrieval_checks_exists",
        "postpass_audit_exists",
        "db_smoke_ok",
        "db_ping_true",
        "canonical_vs_manifest_doc_count_match",
        "canonical_vs_retrieval_checks_doc_count_match",
        "canonical_vs_postpass_doc_count_match",
        "canonical_vs_postpass_multisource_match",
        "manifest_vs_retrieval_checks_build_id_match",
        "canonical_vs_db_doc_count_match",

        # Canonical contract is now a required DoD gate.
        "canonical_contract_exists",
        "canonical_contract_ok",
        "canonical_contract_rows_count_match",
        "canonical_contract_no_bad_rows",
        "canonical_contract_no_extra_fields",
        "canonical_contract_no_missing_canonical_id",
        "canonical_contract_no_duplicate_canonical_id",
        "canonical_contract_doc_ids_shape_ok",
        "canonical_contract_no_duplicate_doc_ids_within_row",
    ]

    if args.require_known_issues:
        required_check_names.extend(
            [
                "known_issues_exists",
                "canonical_vs_known_issues_doc_count_match",
                "manifest_vs_known_issues_build_id_match",
            ]
        )

    if args.require_artifacts:
        required_check_names.extend(
            [
                "artifact_quality_exists",
                "artifact_quality_ok",
                "artifact_export_exists",
                "artifact_export_ok",
                "artifact_db_read_exists",
                "artifact_db_read_ok",
                "artifact_entities_db_non_empty",
                "artifact_observations_db_non_empty",
                "paper_artifact_links_db_non_empty",
                "artifact_links_join_all_rows",
                "artifact_export_vs_db_entities_match",
                "artifact_export_vs_db_observations_match",
                "artifact_export_vs_db_links_match",
                "artifact_quality_vs_export_entities_match",
                "artifact_quality_vs_export_observations_match",
                "artifact_quality_vs_export_links_match",
            ]
        )

    if args.require_github_enrichment:
        required_check_names.extend(
            [
                "github_enrichment_check_exists",
                "github_enrichment_check_ok",
                "github_enrichment_rows_non_empty",
                "github_enrichment_found_non_empty",
                "github_enrichment_no_rate_limited",
                "github_enrichment_no_errors",
                "github_enrichment_metadata_vs_entities_match",
                "github_enrichment_no_unknown_artifact_ids",
                "github_enrichment_no_duplicate_artifact_ids",
            ]
        )

    if args.require_huggingface_enrichment:
        required_check_names.extend(
            [
                "huggingface_enrichment_check_exists",
                "huggingface_enrichment_check_ok",
                "huggingface_enrichment_rows_non_empty",
                "huggingface_enrichment_found_non_empty",
                "huggingface_enrichment_no_rate_limited",
                "huggingface_enrichment_no_errors",
                "huggingface_enrichment_metadata_vs_entities_match",
                "huggingface_enrichment_no_unknown_artifact_ids",
                "huggingface_enrichment_no_duplicate_artifact_ids",
            ]
        )

    if args.require_paper_features:
        required_check_names.extend(
            [
                "paper_features_exists",
                "paper_features_quality_exists",
                "paper_features_quality_ok",
                "paper_features_rows_match_canonical",
                "paper_features_quality_canonical_rows_match",
                "paper_features_build_report_exists",
                "paper_features_build_report_ok",
                "paper_features_build_report_rows_match",
                "paper_features_no_missing_canonical_id",
                "paper_features_no_duplicate_canonical_id",
                "paper_features_required_fields_present",
                "paper_features_scores_in_range",
                "paper_features_counts_non_negative",
                "paper_features_source_families_shape_ok",
                "paper_features_source_families_not_polluted",
                "paper_features_artifact_provider_counts_shape_ok",
                "paper_features_artifact_type_counts_shape_ok",
            ]
        )

    required_failed = [name for name in required_check_names if not checks.get(name, False)]

    verdict = {
        "required_check_count": len(required_check_names),
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
        "dod_passed": len(required_failed) == 0,
        "known_issues_required": bool(args.require_known_issues),
        "artifacts_required": bool(args.require_artifacts),
        "github_enrichment_required": bool(args.require_github_enrichment),
        "huggingface_enrichment_required": bool(args.require_huggingface_enrichment),
        "paper_features_required": bool(args.require_paper_features),
    }

    report = {
        "report_name": "check_refresh_definition_of_done",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "inputs": {
            "canonical_path": normalize_path(args.canonical_path),
            "manifest_path": normalize_path(args.manifest_path),
            "retrieval_checks_path": normalize_path(args.retrieval_checks_path),
            "postpass_audit_path": normalize_path(args.postpass_audit_path),
            "known_issues_path": normalize_path(args.known_issues_path),
            "canonical_contract_path": normalize_path(args.canonical_contract_path),
            "artifact_quality_path": normalize_path(args.artifact_quality_path),
            "artifact_export_path": normalize_path(args.artifact_export_path),
            "artifact_db_read_path": normalize_path(args.artifact_db_read_path),
            "github_enrichment_check_path": normalize_path(
                args.github_enrichment_check_path
            ),
            "huggingface_enrichment_check_path": normalize_path(
                args.huggingface_enrichment_check_path
            ),
            "paper_features_path": normalize_path(args.paper_features_path),
            "paper_features_quality_path": normalize_path(args.paper_features_quality_path),
        },
        "canonical_summary": canonical_summary,
        "extracted_values": {
            "manifest_doc_count": manifest_doc_count,
            "manifest_build_id": manifest_build_id,
            "retrieval_checks_doc_count": retrieval_checks_doc_count,
            "retrieval_checks_build_id": retrieval_checks_build_id,
            "postpass_total_docs": postpass_total_docs,
            "postpass_multisource_docs": postpass_multisource_docs,
            "db_total_docs": db_smoke["total_docs"],
            "known_issues_doc_count": known_issues_doc_count,
            "known_issues_build_id": known_issues_build_id,
            **canonical_contract_values,
            **artifact_values,
            **github_enrichment_values,
            **huggingface_enrichment_values,
            **paper_features_values,
        },
        "checks": checks,
        "verdict": verdict,
        "db_smoke": db_smoke,
    }

    latest_json = args.reports_dir / "check_refresh_definition_of_done_latest.json"
    latest_md = args.reports_dir / "check_refresh_definition_of_done_latest.md"
    hist_json = (
        args.reports_dir / "history" / f"check_refresh_definition_of_done_{run_ts}.json"
    )
    hist_md = (
        args.reports_dir / "history" / f"check_refresh_definition_of_done_{run_ts}.md"
    )

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] canonical_doc_count={canonical_summary['doc_count']}")
    print(f"[OK] canonical_multisource_docs={canonical_summary['multisource_docs']}")
    for k, v in checks.items():
        print(f"[OK] {k}={v}")
    print(f"[OK] dod_passed={verdict['dod_passed']}")
    print(f"[OK] required_failed_count={verdict['required_failed_count']}")
    print(f"[OK] required_failed_checks={verdict['required_failed_checks']}")
    print(f"[OK] known_issues_required={verdict['known_issues_required']}")
    print(f"[OK] artifacts_required={verdict['artifacts_required']}")
    print(f"[OK] github_enrichment_required={verdict['github_enrichment_required']}")
    print(
        f"[OK] huggingface_enrichment_required="
        f"{verdict['huggingface_enrichment_required']}"
    )
    print(f"[OK] paper_features_required={verdict['paper_features_required']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()