from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPORT_PATH = Path("artifacts/reports/source_audit/acl_anthology_filtered_candidate_latest.json")
DEFAULT_BASELINE_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")

ARXIV_VERSION_RE = re.compile(r"v\d+$", re.IGNORECASE)
DOI_RE = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)


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


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL {path} line={line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row must be object: {path} line={line_no}")
            yield row


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return list(iter_jsonl(path))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def canonical_doc_id(doc: dict[str, Any]) -> str | None:
    return str(doc.get("canonical_id") or doc.get("doc_id") or doc.get("id") or "") or None


def normalize_arxiv_base(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("https://arxiv.org/abs/", "")
    text = text.replace("http://arxiv.org/abs/", "")
    text = text.replace("arXiv:", "")
    text = text.replace("arxiv:", "")
    text = text.split()[0].strip().strip("/.,;:)")
    text = ARXIV_VERSION_RE.sub("", text)
    return text or None


def doc_arxiv_bases(doc: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for key in ("arxiv_id", "arxiv_base_id"):
        value = normalize_arxiv_base(doc.get(key))
        if value:
            out.add(value)

    external_ids = doc.get("external_ids")
    if isinstance(external_ids, dict):
        for key in ("arxiv", "arxiv_id", "arXiv", "arxiv_base_id"):
            value = normalize_arxiv_base(external_ids.get(key))
            if value:
                out.add(value)

    source_ids = doc.get("source_ids")
    if isinstance(source_ids, dict):
        for key, value in source_ids.items():
            if "arxiv" in str(key).lower():
                value = normalize_arxiv_base(value)
                if value:
                    out.add(value)
    return out


def normalize_doi(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    text = text.replace("https://doi.org/", "")
    text = text.replace("http://doi.org/", "")
    if text.startswith("doi:"):
        text = text[4:].strip()
    match = DOI_RE.search(text)
    if not match:
        return None
    return match.group(0).strip().rstrip(".,;:)/]")


def doc_doi(doc: dict[str, Any]) -> str | None:
    doi = normalize_doi(doc.get("doi"))
    if doi:
        return doi
    external_ids = doc.get("external_ids")
    if isinstance(external_ids, dict):
        return normalize_doi(external_ids.get("doi") or external_ids.get("DOI"))
    return None


def collect_source_labels(doc: dict[str, Any]) -> set[str]:
    labels: set[str] = set()

    def add(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            if value.strip():
                labels.add(value.strip())
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


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    doc_ids = [canonical_doc_id(row) for row in rows if canonical_doc_id(row)]
    arxiv_bases: list[str] = []
    dois: list[str] = []
    family_sets: Counter[str] = Counter()
    for row in rows:
        arxiv_bases.extend(sorted(doc_arxiv_bases(row)))
        doi = doc_doi(row)
        if doi:
            dois.append(doi)
        families = sorted(source_families(row))
        family_sets["+".join(families) if families else "unknown"] += 1
    doc_id_counts = Counter(doc_ids)
    arxiv_counts = Counter(arxiv_bases)
    doi_counts = Counter(dois)
    return {
        "rows_count": len(rows),
        "doc_id_count": len(doc_ids),
        "duplicate_doc_id_count": sum(1 for _, count in doc_id_counts.items() if count > 1),
        "arxiv_base_count": len(set(arxiv_bases)),
        "duplicate_arxiv_base_count": sum(1 for _, count in arxiv_counts.items() if count > 1),
        "doi_count": len(dois),
        "duplicate_doi_count": sum(1 for _, count in doi_counts.items() if count > 1),
        "acl_family_docs_count": sum(1 for row in rows if "acl_anthology" in source_families(row)),
        "acl_family_only_docs_count": sum(1 for row in rows if source_families(row) == {"acl_anthology"}),
        "source_family_sets_top20": dict(family_sets.most_common(20)),
    }


def arxiv_bases(rows: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for row in rows:
        out.update(doc_arxiv_bases(row))
    return out


def build_markdown(report: dict[str, Any]) -> str:
    lines = ["# ACL Anthology filtered candidate validation", ""]
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Filtered candidate path: `{report['inputs']['filtered_candidate_path']}`")
    lines.append("")
    lines.append("## Summary")
    for key, value in report["summary"].items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## Checks")
    for key, value in report["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append(f"- required_failed_count: `{report['required_failed_count']}`")
    lines.append(f"- ok: `{report['ok']}`")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate ACL Anthology filtered canonical candidate.")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--baseline-path", type=Path, default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--filtered-candidate-path", type=Path, default=None)
    parser.add_argument("--output-report-dir", type=Path, default=Path("artifacts/reports/source_audit"))
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_ts = utc_now_ts()

    if not args.report_path.exists() and args.filtered_candidate_path is None:
        raise FileNotFoundError(
            f"Filtered candidate report not found and --filtered-candidate-path not provided: {args.report_path}"
        )

    build_report: dict[str, Any] | None = None
    filtered_candidate_path = args.filtered_candidate_path
    if args.report_path.exists():
        build_report = load_json(args.report_path)
        if filtered_candidate_path is None:
            output_path = (build_report.get("outputs") or {}).get("filtered_candidate_path")
            if output_path:
                filtered_candidate_path = Path(output_path)

    if filtered_candidate_path is None:
        raise RuntimeError("Cannot determine filtered candidate path")
    if not filtered_candidate_path.exists():
        raise FileNotFoundError(f"Filtered candidate file not found: {filtered_candidate_path}")
    if not args.baseline_path.exists():
        raise FileNotFoundError(f"Baseline canonical file not found: {args.baseline_path}")

    baseline_rows = load_jsonl(args.baseline_path)
    filtered_rows = load_jsonl(filtered_candidate_path)

    baseline_summary = summarize(baseline_rows)
    filtered_summary = summarize(filtered_rows)
    missing_arxiv = sorted(arxiv_bases(baseline_rows) - arxiv_bases(filtered_rows))

    summary = {
        "baseline_rows_count": len(baseline_rows),
        "filtered_rows_count": len(filtered_rows),
        "filtered_delta_vs_baseline": len(filtered_rows) - len(baseline_rows),
        "missing_baseline_arxiv_base_count": len(missing_arxiv),
        "missing_baseline_arxiv_base_sample": missing_arxiv[:20],
        "filtered_duplicate_doc_id_count": filtered_summary["duplicate_doc_id_count"],
        "filtered_duplicate_arxiv_base_count": filtered_summary["duplicate_arxiv_base_count"],
        "filtered_duplicate_doi_count": filtered_summary["duplicate_doi_count"],
        "filtered_acl_family_docs_count": filtered_summary["acl_family_docs_count"],
        "filtered_acl_family_only_docs_count": filtered_summary["acl_family_only_docs_count"],
        "filtered_source_family_sets_top20": filtered_summary["source_family_sets_top20"],
    }

    checks = {
        "baseline_rows_non_empty": len(baseline_rows) > 0,
        "filtered_rows_non_empty": len(filtered_rows) > 0,
        "filtered_count_not_below_baseline": len(filtered_rows) >= len(baseline_rows),
        "filtered_has_acl_family_docs": filtered_summary["acl_family_docs_count"] > 0,
        "filtered_has_acl_family_only_docs": filtered_summary["acl_family_only_docs_count"] > 0,
        "no_missing_baseline_arxiv_base": len(missing_arxiv) == 0,
        "filtered_no_duplicate_doc_ids": filtered_summary["duplicate_doc_id_count"] == 0,
        "filtered_no_duplicate_arxiv_base": filtered_summary["duplicate_arxiv_base_count"] == 0,
        "build_report_ok": True if build_report is None else bool(build_report.get("ok")),
    }

    required = [
        "baseline_rows_non_empty",
        "filtered_rows_non_empty",
        "filtered_count_not_below_baseline",
        "filtered_has_acl_family_docs",
        "filtered_has_acl_family_only_docs",
        "no_missing_baseline_arxiv_base",
        "filtered_no_duplicate_doc_ids",
        "filtered_no_duplicate_arxiv_base",
        "build_report_ok",
    ]

    if args.strict:
        required.extend([])

    failed = [name for name in required if not checks.get(name)]

    report = {
        "report_name": "acl_anthology_filtered_candidate_check",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            "baseline_path": normalize_path(args.baseline_path),
            "filtered_candidate_path": normalize_path(filtered_candidate_path),
            "build_report_path": normalize_path(args.report_path) if args.report_path.exists() else None,
        },
        "summary": summary,
        "baseline_summary": baseline_summary,
        "filtered_summary": filtered_summary,
        "checks": checks,
        "required_check_names": required,
        "required_failed_checks": failed,
        "required_failed_count": len(failed),
        "ok": len(failed) == 0,
    }

    latest_json = args.output_report_dir / "acl_anthology_filtered_candidate_check_latest.json"
    latest_md = args.output_report_dir / "acl_anthology_filtered_candidate_check_latest.md"
    history_json = args.output_report_dir / "history" / f"acl_anthology_filtered_candidate_check_{run_ts}.json"
    history_md = args.output_report_dir / "history" / f"acl_anthology_filtered_candidate_check_{run_ts}.md"

    write_json(latest_json, report)
    write_json(history_json, report)
    write_text(latest_md, build_markdown(report))
    write_text(history_md, build_markdown(report))

    print(f"[OK] report JSON: {latest_json}")
    print(f"[OK] report MD: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history MD: {history_md}")
    for key in (
        "baseline_rows_count",
        "filtered_rows_count",
        "filtered_delta_vs_baseline",
        "missing_baseline_arxiv_base_count",
        "filtered_duplicate_doc_id_count",
        "filtered_duplicate_arxiv_base_count",
        "filtered_duplicate_doi_count",
        "filtered_acl_family_docs_count",
        "filtered_acl_family_only_docs_count",
    ):
        print(f"[CHECK] {key}={summary.get(key)}")
    print(f"[CHECK] strict={args.strict}")
    print(f"[CHECK] required_failed_count={len(failed)}")
    print(f"[CHECK] required_failed_checks={failed}")
    print(f"[CHECK] ok={report['ok']}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
