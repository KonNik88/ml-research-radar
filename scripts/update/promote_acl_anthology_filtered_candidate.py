from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_STABLE_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_FILTERED_BUILD_REPORT_PATH = Path(
    "artifacts/reports/source_audit/acl_anthology_filtered_candidate_latest.json"
)
DEFAULT_FILTERED_CHECK_REPORT_PATH = Path(
    "artifacts/reports/source_audit/acl_anthology_filtered_candidate_check_latest.json"
)
DEFAULT_REPORT_DIR = Path("artifacts/reports/source_audit")
DEFAULT_BACKUP_DIR = Path("artifacts/backups/canonical")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL: {path} line={line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row must be object: {path} line={line_no}")
            yield row


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def count_jsonl_rows(path: Path) -> int:
    return sum(1 for _ in iter_jsonl(path))


def canonical_doc_id(doc: dict[str, Any]) -> str | None:
    value = doc.get("canonical_id") or doc.get("doc_id") or doc.get("id")
    return str(value) if value else None


def collect_source_labels(doc: dict[str, Any]) -> set[str]:
    labels: set[str] = set()

    def add(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            text = value.strip()
            if text:
                labels.add(text)
            return
        if isinstance(value, dict):
            for key in ("source", "source_name", "name", "raw_source_name"):
                add(value.get(key))
            return
        if isinstance(value, list):
            for item in value:
                add(item)
            return

    for key in ("source", "raw_source_name", "sources", "source_names", "source_name", "source_set"):
        add(doc.get(key))

    source_ids = doc.get("source_ids")
    if isinstance(source_ids, dict):
        for key in source_ids.keys():
            add(key)

    external_ids = doc.get("external_ids")
    if isinstance(external_ids, dict):
        if external_ids.get("acl_anthology_id"):
            add("acl_anthology")
        if external_ids.get("arxiv") or external_ids.get("arxiv_id") or external_ids.get("arXiv"):
            add("arxiv")
        if external_ids.get("openalex") or external_ids.get("openalex_id"):
            add("openalex")
        if external_ids.get("semantic_scholar") or external_ids.get("semantic_scholar_id"):
            add("semantic_scholar")

    source_records = doc.get("source_records") or doc.get("source_documents")
    if isinstance(source_records, list):
        for record in source_records:
            add(record)

    return labels


def source_families(doc: dict[str, Any]) -> set[str]:
    labels = {label.lower() for label in collect_source_labels(doc)}
    families: set[str] = set()
    for label in labels:
        if label == "acl_anthology" or label.endswith(".acl") or (label.startswith("20") and ".acl" in label):
            families.add("acl_anthology")
        if "arxiv" in label or "arxiv_kaggle_snapshot" in label:
            families.add("arxiv")
        if "openalex" in label:
            families.add("openalex")
        if "semantic_scholar" in label or "semanticscholar" in label:
            families.add("semantic_scholar")
        if "crossref" in label:
            families.add("crossref")
    return families


def summarize_jsonl(path: Path) -> dict[str, Any]:
    rows_count = 0
    doc_ids: list[str] = []
    family_sets: Counter[str] = Counter()
    acl_docs = 0
    acl_only = 0

    for row in iter_jsonl(path):
        rows_count += 1
        doc_id = canonical_doc_id(row)
        if doc_id:
            doc_ids.append(doc_id)
        families = source_families(row)
        key = "+".join(sorted(families)) if families else "unknown"
        family_sets[key] += 1
        if "acl_anthology" in families:
            acl_docs += 1
        if families == {"acl_anthology"}:
            acl_only += 1

    doc_id_counts = Counter(doc_ids)
    return {
        "rows_count": rows_count,
        "doc_ids_count": len(doc_ids),
        "duplicate_doc_id_count": sum(1 for _, count in doc_id_counts.items() if count > 1),
        "duplicate_doc_ids_sample": [key for key, count in doc_id_counts.items() if count > 1][:20],
        "acl_family_docs_count": acl_docs,
        "acl_family_only_docs_count": acl_only,
        "source_family_sets_top20": dict(family_sets.most_common(20)),
    }


def resolve_filtered_candidate_path(args: argparse.Namespace, build_report: dict[str, Any] | None) -> Path:
    if args.filtered_candidate_path is not None:
        return args.filtered_candidate_path

    if build_report is None:
        raise RuntimeError("Cannot infer filtered candidate path without build report")

    output_path = (build_report.get("outputs") or {}).get("filtered_candidate_path")
    if not output_path:
        raise RuntimeError(
            "Filtered candidate path is missing from build report. "
            "Pass --filtered-candidate-path explicitly."
        )
    return Path(output_path)


def same_resolved_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except FileNotFoundError:
        return left.absolute() == right.absolute()


def build_markdown_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# ACL Anthology filtered candidate promotion report")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Mode: `{report['mode']}`")
    lines.append(f"- Execute: `{report['execute']}`")
    lines.append(f"- Target canonical path: `{report['target_canonical_path']}`")
    lines.append(f"- Filtered candidate path: `{report['filtered_candidate_path']}`")
    lines.append(f"- Backup path: `{report.get('backup_path')}`")
    lines.append("")
    lines.append("## Counts")
    for key in (
        "baseline_rows_count",
        "filtered_rows_count",
        "filtered_delta_vs_baseline",
        "filtered_acl_family_docs_count",
        "filtered_acl_family_only_docs_count",
    ):
        lines.append(f"- {key}: `{report.get(key)}`")
    lines.append("")
    lines.append("## Required checks")
    for key in report.get("required_check_names", []):
        lines.append(f"- {key}: `{report['checks'].get(key)}`")
    lines.append("")
    lines.append(f"- required_failed_count: `{report['required_failed_count']}`")
    lines.append(f"- ok: `{report['ok']}`")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Promote a validated ACL Anthology filtered candidate to stable canonical_documents.jsonl. "
            "Dry-run by default; writes only with --execute."
        )
    )
    parser.add_argument("--filtered-candidate-path", type=Path, default=None)
    parser.add_argument("--target-canonical-path", type=Path, default=DEFAULT_STABLE_CANONICAL_PATH)
    parser.add_argument("--build-report-path", type=Path, default=DEFAULT_FILTERED_BUILD_REPORT_PATH)
    parser.add_argument("--check-report-path", type=Path, default=DEFAULT_FILTERED_CHECK_REPORT_PATH)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--expected-filtered-rows", type=int, default=None)
    parser.add_argument("--expected-delta", type=int, default=None)
    parser.add_argument("--execute", action="store_true", help="Actually replace stable canonical after all required checks pass.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_ts = utc_now_ts()
    mode = "execute" if args.execute else "dry_run"

    build_report: dict[str, Any] | None = None
    if args.build_report_path.exists():
        build_report = load_json(args.build_report_path)

    check_report: dict[str, Any] | None = None
    if args.check_report_path.exists():
        check_report = load_json(args.check_report_path)

    filtered_candidate_path = resolve_filtered_candidate_path(args, build_report)
    target_canonical_path = args.target_canonical_path

    if not target_canonical_path.exists():
        raise FileNotFoundError(f"Target canonical file not found: {target_canonical_path}")
    if not filtered_candidate_path.exists():
        raise FileNotFoundError(f"Filtered candidate file not found: {filtered_candidate_path}")
    if same_resolved_path(filtered_candidate_path, target_canonical_path):
        raise RuntimeError("Refusing to promote because filtered candidate path equals target canonical path")

    baseline_summary = summarize_jsonl(target_canonical_path)
    filtered_summary = summarize_jsonl(filtered_candidate_path)

    baseline_rows_count = baseline_summary["rows_count"]
    filtered_rows_count = filtered_summary["rows_count"]
    delta = filtered_rows_count - baseline_rows_count

    build_report_filtered_path = None
    if build_report is not None:
        build_report_filtered_path = (build_report.get("outputs") or {}).get("filtered_candidate_path")

    check_report_filtered_path = None
    check_summary: dict[str, Any] = {}
    if check_report is not None:
        check_report_filtered_path = (check_report.get("inputs") or {}).get("filtered_candidate_path")
        check_summary = check_report.get("summary") if isinstance(check_report.get("summary"), dict) else {}

    expected_filtered_rows = args.expected_filtered_rows
    if expected_filtered_rows is None and check_summary.get("filtered_rows_count") is not None:
        expected_filtered_rows = int(check_summary["filtered_rows_count"])

    expected_delta = args.expected_delta
    if expected_delta is None and check_summary.get("filtered_delta_vs_baseline") is not None:
        expected_delta = int(check_summary["filtered_delta_vs_baseline"])

    build_acl_url_coverage = {}
    if build_report is not None and isinstance(build_report.get("filtered_acl_url_coverage"), dict):
        build_acl_url_coverage = build_report["filtered_acl_url_coverage"]

    checks = {
        "build_report_exists": build_report is not None,
        "build_report_ok": bool(build_report and build_report.get("ok") is True),
        "check_report_exists": check_report is not None,
        "check_report_ok": bool(check_report and check_report.get("ok") is True),
        "target_exists": target_canonical_path.exists(),
        "filtered_candidate_exists": filtered_candidate_path.exists(),
        "filtered_candidate_not_target": not same_resolved_path(filtered_candidate_path, target_canonical_path),
        "filtered_rows_above_baseline": filtered_rows_count > baseline_rows_count,
        "filtered_has_acl_docs": int(filtered_summary.get("acl_family_docs_count") or 0) > 0,
        "filtered_has_acl_only_docs": int(filtered_summary.get("acl_family_only_docs_count") or 0) > 0,
        "filtered_no_duplicate_doc_ids": int(filtered_summary.get("duplicate_doc_id_count") or 0) == 0,
        "check_no_missing_baseline_arxiv_base": int(check_summary.get("missing_baseline_arxiv_base_count") or 0) == 0,
        "check_no_duplicate_arxiv_base": int(check_summary.get("filtered_duplicate_arxiv_base_count") or 0) == 0,
        "check_no_duplicate_doc_ids": int(check_summary.get("filtered_duplicate_doc_id_count") or 0) == 0,
        "candidate_rows_match_check_report": (
            check_summary.get("filtered_rows_count") is not None
            and int(check_summary.get("filtered_rows_count") or -1) == filtered_rows_count
        ),
        "candidate_delta_match_check_report": (
            check_summary.get("filtered_delta_vs_baseline") is not None
            and int(check_summary.get("filtered_delta_vs_baseline") or -999999) == delta
        ),
        "candidate_rows_match_expected": expected_filtered_rows is None or filtered_rows_count == expected_filtered_rows,
        "candidate_delta_match_expected": expected_delta is None or delta == expected_delta,
        "build_report_path_matches_candidate": (
            build_report_filtered_path is not None
            and normalize_path(Path(build_report_filtered_path)) == normalize_path(filtered_candidate_path)
        ),
        "check_report_path_matches_candidate": (
            check_report_filtered_path is not None
            and normalize_path(Path(check_report_filtered_path)) == normalize_path(filtered_candidate_path)
        ),
        "acl_missing_any_url_zero": int(build_acl_url_coverage.get("missing_any_url_count") or 0) == 0,
        "acl_missing_canonical_url_zero": int(build_acl_url_coverage.get("missing_canonical_url_count") or 0) == 0,
        "acl_missing_source_record_url_zero": int(build_acl_url_coverage.get("missing_source_record_url_count") or 0) == 0,
    }

    required_check_names = [
        "build_report_exists",
        "build_report_ok",
        "check_report_exists",
        "check_report_ok",
        "target_exists",
        "filtered_candidate_exists",
        "filtered_candidate_not_target",
        "filtered_rows_above_baseline",
        "filtered_has_acl_docs",
        "filtered_has_acl_only_docs",
        "filtered_no_duplicate_doc_ids",
        "check_no_missing_baseline_arxiv_base",
        "check_no_duplicate_arxiv_base",
        "check_no_duplicate_doc_ids",
        "candidate_rows_match_check_report",
        "candidate_delta_match_check_report",
        "candidate_rows_match_expected",
        "candidate_delta_match_expected",
        "build_report_path_matches_candidate",
        "check_report_path_matches_candidate",
        "acl_missing_any_url_zero",
        "acl_missing_canonical_url_zero",
        "acl_missing_source_record_url_zero",
    ]

    required_failed_checks = [name for name in required_check_names if not checks.get(name)]

    target_sha256_before = file_sha256(target_canonical_path)
    filtered_sha256 = file_sha256(filtered_candidate_path)
    backup_path = args.backup_dir / f"canonical_documents_before_acl_anthology_promotion.{run_ts}.jsonl"

    report = {
        "report_name": "promote_acl_anthology_filtered_candidate",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "mode": mode,
        "execute": bool(args.execute),
        "target_canonical_path": normalize_path(target_canonical_path),
        "filtered_candidate_path": normalize_path(filtered_candidate_path),
        "build_report_path": normalize_path(args.build_report_path) if args.build_report_path.exists() else None,
        "check_report_path": normalize_path(args.check_report_path) if args.check_report_path.exists() else None,
        "backup_path": normalize_path(backup_path) if args.execute else None,
        "baseline_rows_count": baseline_rows_count,
        "filtered_rows_count": filtered_rows_count,
        "filtered_delta_vs_baseline": delta,
        "filtered_acl_family_docs_count": filtered_summary.get("acl_family_docs_count"),
        "filtered_acl_family_only_docs_count": filtered_summary.get("acl_family_only_docs_count"),
        "baseline_summary": baseline_summary,
        "filtered_summary": filtered_summary,
        "check_report_summary": check_summary,
        "build_acl_url_coverage": build_acl_url_coverage,
        "expected_filtered_rows": expected_filtered_rows,
        "expected_delta": expected_delta,
        "target_sha256_before": target_sha256_before,
        "filtered_candidate_sha256": filtered_sha256,
        "checks": checks,
        "required_check_names": required_check_names,
        "required_failed_checks": required_failed_checks,
        "required_failed_count": len(required_failed_checks),
        "ok": len(required_failed_checks) == 0,
    }

    latest_json = args.report_dir / "promote_acl_anthology_filtered_candidate_latest.json"
    latest_md = args.report_dir / "promote_acl_anthology_filtered_candidate_latest.md"
    history_json = args.report_dir / "history" / f"promote_acl_anthology_filtered_candidate_{run_ts}.json"
    history_md = args.report_dir / "history" / f"promote_acl_anthology_filtered_candidate_{run_ts}.md"

    if required_failed_checks:
        write_json(latest_json, report)
        write_json(history_json, report)
        write_text(latest_md, build_markdown_report(report))
        write_text(history_md, build_markdown_report(report))
        print(f"[FAIL] required_failed_count={len(required_failed_checks)}")
        print(f"[FAIL] required_failed_checks={required_failed_checks}")
        print(f"[OK] report JSON: {latest_json}")
        raise SystemExit(1)

    if args.execute:
        args.backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_canonical_path, backup_path)
        tmp_path = target_canonical_path.with_name(f"{target_canonical_path.name}.tmp_acl_promotion_{run_ts}")
        shutil.copy2(filtered_candidate_path, tmp_path)
        os.replace(tmp_path, target_canonical_path)
        report["target_sha256_after"] = file_sha256(target_canonical_path)
        report["promotion_performed"] = True
        report["message"] = "Filtered ACL Anthology candidate promoted to stable canonical_documents.jsonl. Derived layers must be rebuilt."
    else:
        report["target_sha256_after"] = target_sha256_before
        report["promotion_performed"] = False
        report["message"] = "Dry run completed; stable canonical was not modified. Re-run with --execute to promote."

    write_json(latest_json, report)
    write_json(history_json, report)
    write_text(latest_md, build_markdown_report(report))
    write_text(history_md, build_markdown_report(report))

    print(f"[OK] mode={mode}")
    print(f"[OK] baseline_rows_count={baseline_rows_count}")
    print(f"[OK] filtered_rows_count={filtered_rows_count}")
    print(f"[OK] filtered_delta_vs_baseline={delta}")
    print(f"[OK] filtered_acl_family_docs_count={filtered_summary.get('acl_family_docs_count')}")
    print(f"[OK] filtered_acl_family_only_docs_count={filtered_summary.get('acl_family_only_docs_count')}")
    print(f"[OK] required_failed_count={len(required_failed_checks)}")
    print(f"[OK] promotion_performed={report['promotion_performed']}")
    if args.execute:
        print(f"[OK] backup_path={backup_path}")
        print(f"[OK] promoted_to={target_canonical_path}")
    print(f"[OK] report JSON: {latest_json}")
    print(f"[OK] report MD: {latest_md}")


if __name__ == "__main__":
    main()
