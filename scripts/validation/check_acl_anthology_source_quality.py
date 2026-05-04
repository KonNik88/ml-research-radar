from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_NORMALIZED_PATH = Path("data/normalized/acl_anthology/documents_latest.jsonl")
DEFAULT_INGEST_REPORT_PATH = Path("artifacts/reports/source_audit/acl_anthology_ingest_latest.json")
DEFAULT_REPORT_DIR = Path("artifacts/reports/source_audit")
SOURCE_NAME = "acl_anthology"
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)


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


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row must be object at {path}:{line_no}")
            rows.append(row)
    return rows


def ratio(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def has_valid_acl_url(url: Any) -> bool:
    text = str(url or "")
    return text.startswith("https://aclanthology.org/")


def has_valid_pdf_url(url: Any) -> bool:
    text = str(url or "")
    return text.startswith("https://aclanthology.org/") and text.endswith(".pdf")


def normalize_title_key(title: Any, year: Any) -> str:
    title_text = re.sub(r"\s+", " ", str(title or "").strip().lower())
    return f"{title_text}::{year or 'missing'}"


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    doc_ids = [str(row.get("doc_id") or "") for row in rows if row.get("doc_id")]
    source_ids = [str(row.get("source_id") or "") for row in rows if row.get("source_id")]
    source_record_ids = [str(row.get("source_record_id") or "") for row in rows if row.get("source_record_id")]
    dois = [str(row.get("doi") or "") for row in rows if row.get("doi")]
    title_year_keys = [normalize_title_key(row.get("title"), row.get("year")) for row in rows if row.get("title")]

    duplicate_doc_ids = sorted([key for key, c in Counter(doc_ids).items() if c > 1])
    duplicate_source_ids = sorted([key for key, c in Counter(source_ids).items() if c > 1])
    duplicate_source_record_ids = sorted([key for key, c in Counter(source_record_ids).items() if c > 1])
    duplicate_dois = sorted([key for key, c in Counter(dois).items() if c > 1])
    duplicate_title_year = sorted([key for key, c in Counter(title_year_keys).items() if c > 1])

    missing_title = [row.get("source_id") or row.get("doc_id") for row in rows if not row.get("title")]
    missing_source_id = [row.get("doc_id") for row in rows if not row.get("source_id")]
    missing_authors = [row.get("source_id") for row in rows if not row.get("authors")]
    missing_year = [row.get("source_id") for row in rows if row.get("year") is None]
    missing_landing_page = [row.get("source_id") for row in rows if not row.get("landing_page_url")]
    missing_pdf = [row.get("source_id") for row in rows if not row.get("pdf_url")]
    bad_canonical_url = [row.get("source_id") for row in rows if not has_valid_acl_url(row.get("canonical_url"))]
    bad_source_record_url = [row.get("source_id") for row in rows if not has_valid_acl_url(row.get("source_record_url"))]
    bad_pdf_url = [row.get("source_id") for row in rows if row.get("pdf_url") and not has_valid_pdf_url(row.get("pdf_url"))]
    bad_doi = [row.get("source_id") for row in rows if row.get("doi") and not DOI_RE.match(str(row.get("doi")))]
    wrong_source = [row.get("source_id") for row in rows if row.get("source") != SOURCE_NAME]
    non_paper = [row.get("source_id") for row in rows if row.get("document_type") != "paper"]

    abstract_count = sum(1 for row in rows if row.get("abstract"))
    doi_count = sum(1 for row in rows if row.get("doi"))
    author_count = sum(1 for row in rows if row.get("authors"))
    year_count = sum(1 for row in rows if row.get("year") is not None)
    landing_page_count = sum(1 for row in rows if row.get("landing_page_url"))
    pdf_count = sum(1 for row in rows if row.get("pdf_url"))
    code_link_docs = sum(1 for row in rows if row.get("has_code_link"))
    dataset_link_docs = sum(1 for row in rows if row.get("has_dataset_link"))
    model_link_docs = sum(1 for row in rows if row.get("has_model_link"))

    by_year = Counter(str(row.get("year") or "missing") for row in rows)
    by_venue = Counter(str(row.get("venue") or "missing") for row in rows)
    by_publication_type = Counter(str(row.get("publication_type") or "missing") for row in rows)

    return {
        "rows_count": n,
        "source": SOURCE_NAME,
        "doc_ids_count": len(set(doc_ids)),
        "source_ids_count": len(set(source_ids)),
        "source_record_ids_count": len(set(source_record_ids)),
        "doi_count": doi_count,
        "doi_coverage": ratio(doi_count, n),
        "abstract_count": abstract_count,
        "abstract_coverage": ratio(abstract_count, n),
        "author_count": author_count,
        "author_coverage": ratio(author_count, n),
        "year_count": year_count,
        "year_coverage": ratio(year_count, n),
        "landing_page_count": landing_page_count,
        "landing_page_coverage": ratio(landing_page_count, n),
        "pdf_count": pdf_count,
        "pdf_coverage": ratio(pdf_count, n),
        "code_link_docs": code_link_docs,
        "dataset_link_docs": dataset_link_docs,
        "model_link_docs": model_link_docs,
        "duplicate_doc_id_count": len(duplicate_doc_ids),
        "duplicate_doc_ids_sample": duplicate_doc_ids[:20],
        "duplicate_source_id_count": len(duplicate_source_ids),
        "duplicate_source_ids_sample": duplicate_source_ids[:20],
        "duplicate_source_record_id_count": len(duplicate_source_record_ids),
        "duplicate_source_record_ids_sample": duplicate_source_record_ids[:20],
        "duplicate_doi_count": len(duplicate_dois),
        "duplicate_dois_sample": duplicate_dois[:20],
        "duplicate_title_year_count": len(duplicate_title_year),
        "duplicate_title_year_sample": duplicate_title_year[:20],
        "missing_title_count": len(missing_title),
        "missing_title_sample": missing_title[:20],
        "missing_source_id_count": len(missing_source_id),
        "missing_source_id_sample": missing_source_id[:20],
        "missing_authors_count": len(missing_authors),
        "missing_authors_sample": missing_authors[:20],
        "missing_year_count": len(missing_year),
        "missing_year_sample": missing_year[:20],
        "missing_landing_page_count": len(missing_landing_page),
        "missing_landing_page_sample": missing_landing_page[:20],
        "missing_pdf_count": len(missing_pdf),
        "missing_pdf_sample": missing_pdf[:20],
        "bad_canonical_url_count": len(bad_canonical_url),
        "bad_canonical_url_sample": bad_canonical_url[:20],
        "bad_source_record_url_count": len(bad_source_record_url),
        "bad_source_record_url_sample": bad_source_record_url[:20],
        "bad_pdf_url_count": len(bad_pdf_url),
        "bad_pdf_url_sample": bad_pdf_url[:20],
        "bad_doi_count": len(bad_doi),
        "bad_doi_sample": bad_doi[:20],
        "wrong_source_count": len(wrong_source),
        "wrong_source_sample": wrong_source[:20],
        "non_paper_count": len(non_paper),
        "non_paper_sample": non_paper[:20],
        "by_year": dict(sorted(by_year.items())),
        "by_venue": dict(sorted(by_venue.items())),
        "by_publication_type": dict(sorted(by_publication_type.items())),
    }


def build_checks(summary: dict[str, Any], *, strict: bool) -> tuple[dict[str, bool], list[str]]:
    checks = {
        "rows_non_empty": int(summary["rows_count"] or 0) > 0,
        "all_rows_source_acl_anthology": int(summary["wrong_source_count"] or 0) == 0,
        "all_rows_are_paper": int(summary["non_paper_count"] or 0) == 0,
        "doc_ids_unique": int(summary["duplicate_doc_id_count"] or 0) == 0,
        "source_ids_unique": int(summary["duplicate_source_id_count"] or 0) == 0,
        "source_record_ids_unique": int(summary["duplicate_source_record_id_count"] or 0) == 0,
        "titles_present": int(summary["missing_title_count"] or 0) == 0,
        "source_ids_present": int(summary["missing_source_id_count"] or 0) == 0,
        "authors_coverage_ok": float(summary["author_coverage"] or 0) >= 0.95,
        "year_coverage_ok": float(summary["year_coverage"] or 0) >= 0.95,
        "landing_page_coverage_ok": float(summary["landing_page_coverage"] or 0) >= 0.95,
        "pdf_coverage_ok": float(summary["pdf_coverage"] or 0) >= 0.95,
        "canonical_urls_valid": int(summary["bad_canonical_url_count"] or 0) == 0,
        "source_record_urls_valid": int(summary["bad_source_record_url_count"] or 0) == 0,
        "pdf_urls_valid": int(summary["bad_pdf_url_count"] or 0) == 0,
        "doi_values_valid": int(summary["bad_doi_count"] or 0) == 0,
    }

    required = [
        "rows_non_empty",
        "all_rows_source_acl_anthology",
        "all_rows_are_paper",
        "doc_ids_unique",
        "source_ids_unique",
        "source_record_ids_unique",
        "titles_present",
        "source_ids_present",
        "canonical_urls_valid",
        "source_record_urls_valid",
        "doi_values_valid",
    ]

    if strict:
        required.extend(
            [
                "authors_coverage_ok",
                "year_coverage_ok",
                "landing_page_coverage_ok",
                "pdf_coverage_ok",
                "pdf_urls_valid",
            ]
        )

    return checks, required


def build_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines: list[str] = []
    lines.append("# ACL Anthology source quality report")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Strict: `{report['strict']}`")
    lines.append(f"- Input: `{report['inputs']['normalized_path']}`")
    lines.append(f"- Rows: `{s['rows_count']}`")
    lines.append(f"- OK: `{report['ok']}`")
    lines.append(f"- Required failed count: `{report['required_failed_count']}`")
    lines.append("")
    lines.append("## Coverage")
    for key in [
        "abstract_coverage",
        "doi_coverage",
        "author_coverage",
        "year_coverage",
        "landing_page_coverage",
        "pdf_coverage",
    ]:
        lines.append(f"- {key}: `{s.get(key)}`")
    lines.append("")
    lines.append("## Integrity")
    for key in [
        "duplicate_doc_id_count",
        "duplicate_source_id_count",
        "duplicate_source_record_id_count",
        "duplicate_doi_count",
        "duplicate_title_year_count",
        "missing_title_count",
        "bad_doi_count",
        "wrong_source_count",
        "non_paper_count",
    ]:
        lines.append(f"- {key}: `{s.get(key)}`")
    lines.append("")
    lines.append("## Checks")
    for key, value in report["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## By year")
    for key, value in s.get("by_year", {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## By venue")
    for key, value in s.get("by_venue", {}).items():
        lines.append(f"- {key}: `{value}`")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate candidate-only ACL Anthology normalized snapshot. Does not touch canonical corpus or DB."
    )
    parser.add_argument("--normalized-path", type=Path, default=DEFAULT_NORMALIZED_PATH)
    parser.add_argument("--ingest-report-path", type=Path, default=DEFAULT_INGEST_REPORT_PATH)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_ts = utc_now_ts()

    normalized_exists = args.normalized_path.exists()
    ingest_report_exists = args.ingest_report_path.exists()
    load_errors: list[str] = []
    rows: list[dict[str, Any]] = []

    if normalized_exists:
        try:
            rows = load_jsonl(args.normalized_path)
        except Exception as exc:
            load_errors.append(repr(exc))

    ingest_report = load_json(args.ingest_report_path)
    summary = build_summary(rows) if rows else {
        "rows_count": 0,
        "source": SOURCE_NAME,
        "doc_ids_count": 0,
        "source_ids_count": 0,
        "source_record_ids_count": 0,
        "doi_count": 0,
        "doi_coverage": 0.0,
        "abstract_count": 0,
        "abstract_coverage": 0.0,
        "author_count": 0,
        "author_coverage": 0.0,
        "year_count": 0,
        "year_coverage": 0.0,
        "landing_page_count": 0,
        "landing_page_coverage": 0.0,
        "pdf_count": 0,
        "pdf_coverage": 0.0,
        "code_link_docs": 0,
        "dataset_link_docs": 0,
        "model_link_docs": 0,
        "duplicate_doc_id_count": 0,
        "duplicate_source_id_count": 0,
        "duplicate_source_record_id_count": 0,
        "duplicate_doi_count": 0,
        "duplicate_title_year_count": 0,
        "missing_title_count": 0,
        "missing_source_id_count": 0,
        "missing_authors_count": 0,
        "missing_year_count": 0,
        "missing_landing_page_count": 0,
        "missing_pdf_count": 0,
        "bad_canonical_url_count": 0,
        "bad_source_record_url_count": 0,
        "bad_pdf_url_count": 0,
        "bad_doi_count": 0,
        "wrong_source_count": 0,
        "non_paper_count": 0,
        "by_year": {},
        "by_venue": {},
        "by_publication_type": {},
    }

    checks, required = build_checks(summary, strict=args.strict)
    checks["normalized_path_exists"] = normalized_exists
    checks["ingest_report_exists"] = ingest_report_exists
    checks["no_load_errors"] = not load_errors
    checks["ingest_report_ok"] = bool(ingest_report and ingest_report.get("ok") is True)

    required = ["normalized_path_exists", "no_load_errors", *required]
    if args.strict:
        required.append("ingest_report_exists")
        required.append("ingest_report_ok")

    required_failed = [name for name in required if not checks.get(name, False)]

    report = {
        "report_name": "acl_anthology_source_quality",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "candidate_only": True,
        "inputs": {
            "normalized_path": normalize_path(args.normalized_path),
            "ingest_report_path": normalize_path(args.ingest_report_path),
        },
        "load_errors": load_errors,
        "summary": summary,
        "checks": checks,
        "required_check_names": required,
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
        "ok": len(required_failed) == 0,
    }

    latest_json = args.report_dir / "acl_anthology_source_quality_latest.json"
    latest_md = args.report_dir / "acl_anthology_source_quality_latest.md"
    history_json = args.report_dir / "history" / f"acl_anthology_source_quality_{run_ts}.json"
    history_md = args.report_dir / "history" / f"acl_anthology_source_quality_{run_ts}.md"

    write_json(latest_json, report)
    write_text(latest_md, build_markdown(report))
    write_json(history_json, report)
    write_text(history_md, build_markdown(report))

    print(f"[OK] report JSON: {latest_json}")
    print(f"[OK] report MD: {latest_md}")
    print(f"[CHECK] rows_count={summary['rows_count']}")
    print(f"[CHECK] doi_coverage={summary['doi_coverage']}")
    print(f"[CHECK] abstract_coverage={summary['abstract_coverage']}")
    print(f"[CHECK] author_coverage={summary['author_coverage']}")
    print(f"[CHECK] duplicate_doc_id_count={summary['duplicate_doc_id_count']}")
    print(f"[CHECK] duplicate_source_id_count={summary['duplicate_source_id_count']}")
    print(f"[CHECK] bad_doi_count={summary['bad_doi_count']}")
    print(f"[CHECK] strict={bool(args.strict)}")
    print(f"[CHECK] required_failed_count={len(required_failed)}")
    print(f"[CHECK] required_failed_checks={required_failed}")
    print(f"[CHECK] ok={report['ok']}")

    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
