from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPORTS_ROOT = Path("artifacts/reports")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/update")

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s,;]+", re.IGNORECASE)

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


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def find_latest_incremental_merge_report(reports_root: Path) -> Path | None:
    history_dir = reports_root / "history"
    if history_dir.exists():
        candidates = sorted(history_dir.glob("arxiv_incremental_merge_*.json"))
        if candidates:
            return candidates[-1]

    latest = reports_root / "arxiv_incremental_merge_latest.json"
    if latest.exists():
        return latest

    return None


def normalize_doi(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    lower = text.lower()
    prefixes = (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    )
    for prefix in prefixes:
        if lower.startswith(prefix):
            text = text[len(prefix):].strip()
            break

    tokens = [
        token.strip().strip(".,;()[]{}<>").lower().rstrip("/")
        for token in DOI_RE.findall(text)
    ]
    tokens = [token for token in tokens if token]

    unique_tokens = list(dict.fromkeys(tokens))
    if unique_tokens:
        return unique_tokens[0]

    return None


def collect_doi_rows(path: Path | None, source_label: str) -> tuple[list[dict[str, Any]], int]:
    if path is None or not path.exists():
        return [], 0

    rows: list[dict[str, Any]] = []
    total_docs = 0

    for doc in iter_jsonl(path):
        total_docs += 1
        doi = normalize_doi(doc.get("doi"))
        if not doi:
            continue

        rows.append(
            {
                "doi": doi,
                "doc_id": doc.get("doc_id"),
                "arxiv_id": doc.get("arxiv_id"),
                "title": doc.get("title"),
                "year": doc.get("year"),
                "source_bucket": source_label,
                "input_file": str(path),
            }
        )

    return rows, total_docs


def deduplicate_doi_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}

    for row in rows:
        doi = row["doi"]
        existing = seen.get(doi)
        if existing is None:
            seen[doi] = row
            continue

        # Предпочтём updated над new, если вдруг DOI встретился в обоих списках.
        existing_bucket = existing.get("source_bucket")
        current_bucket = row.get("source_bucket")
        if existing_bucket == "new" and current_bucket == "updated":
            seen[doi] = row

    return sorted(seen.values(), key=lambda x: x["doi"])


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []

    lines.append("# Incremental DOI candidates")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Merge report: `{report['merge_report_path']}`")
    lines.append("")

    lines.append("## Input files")
    lines.append(f"- new file: `{report['input_files']['new']}`")
    lines.append(f"- updated file: `{report['input_files']['updated']}`")
    lines.append("")

    lines.append("## Counts")
    counts = report["counts"]
    for key, value in counts.items():
        lines.append(f"- {key}: **{value}**")
    lines.append("")

    if report["sample_candidates"]:
        lines.append("## Sample DOI candidates")
        for item in report["sample_candidates"]:
            lines.append(
                f"- doi={item['doi']} | bucket={item['source_bucket']} | "
                f"arxiv_id={item.get('arxiv_id')} | title={item.get('title')}"
            )
        lines.append("")

    lines.append("## Output files")
    lines.append(f"- doi_jsonl: `{report['artifacts']['doi_jsonl']}`")
    lines.append(f"- doi_txt: `{report['artifacts']['doi_txt']}`")
    lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract unique DOI candidates from latest arXiv incremental merge outputs."
    )
    parser.add_argument(
        "--reports-root",
        type=Path,
        default=DEFAULT_REPORTS_ROOT,
        help="Root directory for existing reports.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for output reports and DOI candidate files.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    reports_root: Path = args.reports_root
    output_dir: Path = args.output_dir

    merge_report_path = find_latest_incremental_merge_report(reports_root)
    if merge_report_path is None:
        raise FileNotFoundError("No arxiv incremental merge report found.")

    merge_report = load_json(merge_report_path)
    output_files = merge_report.get("output_files", {}) or {}

    new_file = output_files.get("new")
    updated_file = output_files.get("updated")

    new_path = Path(new_file) if new_file else None
    updated_path = Path(updated_file) if updated_file else None

    new_rows, new_total_docs = collect_doi_rows(new_path, "new")
    updated_rows, updated_total_docs = collect_doi_rows(updated_path, "updated")

    all_rows = new_rows + updated_rows
    unique_rows = deduplicate_doi_rows(all_rows)

    doi_jsonl_path = output_dir / "doi_candidates_latest.jsonl"
    doi_txt_path = output_dir / "doi_candidates_latest.txt"
    latest_json = output_dir / "extract_incremental_doi_candidates_latest.json"
    latest_md = output_dir / "extract_incremental_doi_candidates_latest.md"
    hist_json = output_dir / "history" / f"extract_incremental_doi_candidates_{run_ts}.json"
    hist_md = output_dir / "history" / f"extract_incremental_doi_candidates_{run_ts}.md"

    ensure_parent(doi_jsonl_path)
    with doi_jsonl_path.open("w", encoding="utf-8") as f:
        for row in unique_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    ensure_parent(doi_txt_path)
    doi_txt_path.write_text(
        "\n".join(row["doi"] for row in unique_rows),
        encoding="utf-8",
    )

    report = {
        "report_name": "extract_incremental_doi_candidates",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "merge_report_path": str(merge_report_path),
        "input_files": {
            "new": None if new_path is None else str(new_path),
            "updated": None if updated_path is None else str(updated_path),
        },
        "counts": {
            "new_docs_total": new_total_docs,
            "updated_docs_total": updated_total_docs,
            "new_docs_with_doi": len(new_rows),
            "updated_docs_with_doi": len(updated_rows),
            "raw_doi_rows_total": len(all_rows),
            "unique_doi_candidates": len(unique_rows),
        },
        "sample_candidates": unique_rows[:10],
        "artifacts": {
            "doi_jsonl": str(doi_jsonl_path),
            "doi_txt": str(doi_txt_path),
        },
    }

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] merge_report={merge_report_path}")
    print(f"[OK] new_docs_total={new_total_docs}")
    print(f"[OK] updated_docs_total={updated_total_docs}")
    print(f"[OK] new_docs_with_doi={len(new_rows)}")
    print(f"[OK] updated_docs_with_doi={len(updated_rows)}")
    print(f"[OK] unique_doi_candidates={len(unique_rows)}")
    print(f"[OK] doi_jsonl: {doi_jsonl_path}")
    print(f"[OK] doi_txt: {doi_txt_path}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")


if __name__ == "__main__":
    main()