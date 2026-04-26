from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/validation")


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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Canonical JSONL not found: {path}")

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at line {line_no} in {path}: {exc}") from exc
    return rows


def sample_payload(
    row: dict[str, Any],
    provenance_sources: list[str],
    sources_len: int,
    doc_ids_len: int,
    source_ids_keys: list[str],
) -> dict[str, Any]:
    return {
        "canonical_id": row.get("canonical_id"),
        "title": row.get("title"),
        "source_count": int(row.get("source_count", 0) or 0),
        "unique_source_count": int(row.get("unique_source_count", 0) or 0),
        "sources_len": sources_len,
        "doc_ids_len": doc_ids_len,
        "source_ids_keys": source_ids_keys,
        "provenance_sources": provenance_sources,
        "arxiv_id": row.get("arxiv_id"),
        "openalex_id": row.get("openalex_id"),
        "doi": row.get("doi"),
        "reconciliation_key": row.get("reconciliation_key"),
    }


def add_issue(
    bucket: dict[str, list[dict[str, Any]]],
    issue_type: str,
    payload: dict[str, Any],
) -> None:
    bucket[issue_type].append(payload)


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Canonical provenance consistency report v2")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Canonical path: `{report['canonical_path']}`")
    lines.append("")

    lines.append("## Summary")
    for k, v in report["summary"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    lines.append("## Errors")
    if report["error_counts"]:
        for k, v in report["error_counts"].items():
            lines.append(f"- {k}: `{v}`")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Warnings")
    if report["warning_counts"]:
        for k, v in report["warning_counts"].items():
            lines.append(f"- {k}: `{v}`")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Info signals")
    if report["info_counts"]:
        for k, v in report["info_counts"].items():
            lines.append(f"- {k}: `{v}`")
    else:
        lines.append("- none")
    lines.append("")

    for section_name in ("sample_errors", "sample_warnings", "sample_info"):
        lines.append(f"## {section_name.replace('_', ' ').title()}")
        section = report[section_name]
        if not section:
            lines.append("- none")
            lines.append("")
            continue

        for issue_type, items in section.items():
            lines.append(f"### {issue_type}")
            for item in items:
                lines.append(
                    f"- canonical_id=`{item['canonical_id']}` | "
                    f"title=`{item['title']}` | "
                    f"source_count={item['source_count']} | "
                    f"unique_source_count={item['unique_source_count']} | "
                    f"sources_len={item['sources_len']} | "
                    f"doc_ids_len={item['doc_ids_len']} | "
                    f"source_ids_keys={item['source_ids_keys']}"
                )
            lines.append("")

    return "\n".join(lines)


def audit_canonical(rows: list[dict[str, Any]]) -> dict[str, Any]:
    errors: dict[str, list[dict[str, Any]]] = defaultdict(list)
    warnings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    info: dict[str, list[dict[str, Any]]] = defaultdict(list)

    total_docs = 0

    for row in rows:
        total_docs += 1

        source_count = int(row.get("source_count", 0) or 0)
        unique_source_count = int(row.get("unique_source_count", 0) or 0)

        sources = row.get("sources") or []
        if not isinstance(sources, list):
            sources = []

        doc_ids = row.get("doc_ids") or []
        if not isinstance(doc_ids, list):
            doc_ids = []

        source_ids = row.get("source_ids") or {}
        if not isinstance(source_ids, dict):
            source_ids = {}

        sources_len = len(sources)
        doc_ids_len = len(doc_ids)
        source_ids_keys = sorted(source_ids.keys())

        provenance_source_names: list[str] = []
        exact_source_keys: list[tuple[str | None, str | None]] = []
        source_entries_missing_name = 0

        for s in sources:
            if not isinstance(s, dict):
                continue
            src_name = s.get("source")
            src_record_id = s.get("source_record_id")
            if src_name:
                provenance_source_names.append(src_name)
            else:
                source_entries_missing_name += 1
            exact_source_keys.append((src_name, src_record_id))

        unique_provenance_sources = sorted(set(provenance_source_names))
        unique_provenance_count = len(unique_provenance_sources)

        payload = sample_payload(
            row=row,
            provenance_sources=unique_provenance_sources,
            sources_len=sources_len,
            doc_ids_len=doc_ids_len,
            source_ids_keys=source_ids_keys,
        )

        # ---- ERRORS: structural inconsistencies ----
        if source_count != sources_len:
            add_issue(errors, "source_count_mismatch", payload)

        if unique_source_count != unique_provenance_count:
            add_issue(errors, "unique_source_count_mismatch", payload)

        if source_entries_missing_name > 0:
            p = dict(payload)
            p["source_entries_missing_name"] = source_entries_missing_name
            add_issue(errors, "source_entries_missing_source_name", p)

        exact_key_counts = Counter(exact_source_keys)
        duplicated_exact_keys = [
            {"source": src, "source_record_id": rec_id, "count": cnt}
            for (src, rec_id), cnt in exact_key_counts.items()
            if src is not None and rec_id is not None and cnt > 1
        ]
        if duplicated_exact_keys:
            p = dict(payload)
            p["duplicated_exact_source_entries"] = duplicated_exact_keys
            add_issue(errors, "duplicate_exact_provenance_entries", p)

        # ---- WARNINGS: suspicious and still worth surfacing ----
        if row.get("openalex_id") and "openalex" not in unique_provenance_sources:
            add_issue(warnings, "openalex_identifier_without_openalex_provenance", payload)

        # ---- INFO: expected under current design / source asymmetry ----
        if len(source_ids_keys) > 1 and unique_provenance_count <= 1:
            add_issue(info, "single_provenance_family_but_multi_family_identifier_map", payload)

        if row.get("arxiv_id") and "arxiv" not in unique_provenance_sources:
            add_issue(info, "arxiv_identifier_without_arxiv_provenance", payload)

        if doc_ids_len < sources_len:
            add_issue(info, "doc_ids_shorter_than_sources", payload)

        family_counts = Counter(provenance_source_names)
        duplicated_families = [
            {"source": src, "count": cnt}
            for src, cnt in family_counts.items()
            if cnt > 1
        ]
        if duplicated_families:
            p = dict(payload)
            p["duplicated_source_families"] = duplicated_families
            add_issue(info, "duplicate_source_family_entries", p)

    docs_with_error = len(
        {
            item["canonical_id"]
            for items in errors.values()
            for item in items
            if item.get("canonical_id") is not None
        }
    )
    docs_with_warning = len(
        {
            item["canonical_id"]
            for items in warnings.values()
            for item in items
            if item.get("canonical_id") is not None
        }
    )
    docs_with_info = len(
        {
            item["canonical_id"]
            for items in info.values()
            for item in items
            if item.get("canonical_id") is not None
        }
    )

    error_counts = {k: len(v) for k, v in errors.items()}
    warning_counts = {k: len(v) for k, v in warnings.items()}
    info_counts = {k: len(v) for k, v in info.items()}

    report = {
        "summary": {
            "total_docs": total_docs,
            "docs_with_error": docs_with_error,
            "docs_with_warning": docs_with_warning,
            "docs_with_info": docs_with_info,
            "all_error_checks_clean": docs_with_error == 0,
        },
        "error_counts": error_counts,
        "warning_counts": warning_counts,
        "info_counts": info_counts,
        "sample_errors": {k: v[:10] for k, v in errors.items()},
        "sample_warnings": {k: v[:10] for k, v in warnings.items()},
        "sample_info": {k: v[:10] for k, v in info.items()},
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit canonical provenance consistency (v2, semantics-aware)."
    )
    parser.add_argument(
        "--canonical-path",
        type=Path,
        default=DEFAULT_CANONICAL_PATH,
        help="Path to canonical JSONL file to audit.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Directory where validation reports are written.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    canonical_path: Path = args.canonical_path
    reports_dir: Path = args.reports_dir

    rows = load_jsonl(canonical_path)
    audit = audit_canonical(rows)

    report = {
        "report_name": "canonical_provenance_consistency_v2",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "canonical_path": normalize_path(canonical_path),
        "summary": audit["summary"],
        "error_counts": audit["error_counts"],
        "warning_counts": audit["warning_counts"],
        "info_counts": audit["info_counts"],
        "sample_errors": audit["sample_errors"],
        "sample_warnings": audit["sample_warnings"],
        "sample_info": audit["sample_info"],
    }

    latest_json = reports_dir / "canonical_provenance_consistency_latest.json"
    latest_md = reports_dir / "canonical_provenance_consistency_latest.md"
    hist_json = reports_dir / "history" / f"canonical_provenance_consistency_{run_ts}.json"
    hist_md = reports_dir / "history" / f"canonical_provenance_consistency_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] canonical_path={normalize_path(canonical_path)}")
    print(f"[OK] total_docs={report['summary']['total_docs']}")
    print(f"[OK] docs_with_error={report['summary']['docs_with_error']}")
    print(f"[OK] docs_with_warning={report['summary']['docs_with_warning']}")
    print(f"[OK] docs_with_info={report['summary']['docs_with_info']}")
    print(f"[OK] all_error_checks_clean={report['summary']['all_error_checks_clean']}")
    for k, v in report["error_counts"].items():
        print(f"[OK] error::{k}={v}")
    for k, v in report["warning_counts"].items():
        print(f"[OK] warning::{k}={v}")
    for k, v in report["info_counts"].items():
        print(f"[OK] info::{k}={v}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()