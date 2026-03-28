from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from radar_core.contracts.document import NormalizedDocument, RawDocument
from radar_core.ingest.crossref import CrossrefIngestor, CrossrefQuery


ARXIV_NORMALIZED_DIR = Path("data/normalized/arxiv")
RAW_ALIGNMENT_ROOT = Path("data/raw/crossref_alignment")
NORMALIZED_ALIGNMENT_DIR = Path("data/normalized/crossref_alignment")
REPORTS_DIR = Path("artifacts/reports")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ts_slug(dt: datetime | None = None) -> str:
    dt = dt or utc_now()
    return dt.strftime("%Y%m%dT%H%M%SZ")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def write_jsonl(path: Path, rows: list[Any]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            if hasattr(row, "model_dump"):
                row = row.model_dump(mode="json")
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")


def write_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def find_latest_normalized_file(source_dir: Path) -> Path:
    candidates = sorted(source_dir.glob("documents*.jsonl"))
    if not candidates:
        raise FileNotFoundError(f"No normalized JSONL found in: {source_dir}")

    import re
    pattern = re.compile(r"^documents\.\d{8}T\d{6}Z\.jsonl$")
    primary = [p for p in candidates if pattern.match(p.name)]
    if primary:
        return sorted(primary)[-1]

    return candidates[-1]


def normalize_doi(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None

    prefixes = (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    )
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break

    text = text.strip().strip("/")
    return text or None


def extract_candidate_dois(rows: list[dict[str, Any]]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    doi_to_doc: dict[str, dict[str, Any]] = {}

    for row in rows:
        doi = normalize_doi(row.get("doi"))
        if not doi:
            ext = row.get("external_ids") or {}
            doi = normalize_doi(ext.get("doi") or ext.get("DOI"))
        if not doi:
            continue
        if doi not in doi_to_doc:
            doi_to_doc[doi] = row

    return sorted(doi_to_doc.keys()), doi_to_doc


def chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def build_match_row(
    arxiv_row: dict[str, Any],
    crossref_doc: Optional[NormalizedDocument],
    *,
    error: Optional[str] = None,
) -> dict[str, Any]:
    arxiv_doi = normalize_doi(arxiv_row.get("doi"))

    if error is not None:
        return {
            "status": "error",
            "arxiv_doc_id": arxiv_row.get("doc_id"),
            "arxiv_title": arxiv_row.get("title"),
            "arxiv_year": arxiv_row.get("year"),
            "arxiv_doi": arxiv_doi,
            "crossref_doi": None,
            "crossref_title": None,
            "crossref_year": None,
            "error": error,
        }

    if crossref_doc is None:
        return {
            "status": "not_found",
            "arxiv_doc_id": arxiv_row.get("doc_id"),
            "arxiv_title": arxiv_row.get("title"),
            "arxiv_year": arxiv_row.get("year"),
            "arxiv_doi": arxiv_doi,
            "crossref_doi": None,
            "crossref_title": None,
            "crossref_year": None,
        }

    return {
        "status": "found",
        "arxiv_doc_id": arxiv_row.get("doc_id"),
        "arxiv_title": arxiv_row.get("title"),
        "arxiv_year": arxiv_row.get("year"),
        "arxiv_doi": arxiv_doi,
        "crossref_doi": crossref_doc.doi,
        "crossref_title": crossref_doc.title,
        "crossref_year": crossref_doc.year,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Crossref alignment ingest",
        "",
        f"- generated_at: `{summary['generated_at']}`",
        f"- input_file: `{summary['input_file']}`",
        f"- doi_candidates: **{summary['doi_candidates']}**",
        f"- doi_batches: **{summary['doi_batches']}**",
        f"- fetched_entries: **{summary['fetched_entries']}**",
        f"- normalized_docs: **{summary['normalized_docs']}**",
        f"- raw_dir: `{summary['raw_dir']}`",
        f"- normalized_output: `{summary['normalized_output']}`",
        "",
        "## Summary",
        f"- found: **{summary['status_counts'].get('found', 0)}**",
        f"- not_found: **{summary['status_counts'].get('not_found', 0)}**",
        f"- error: **{summary['status_counts'].get('error', 0)}**",
    ]

    if summary.get("sample_dois"):
        lines.extend(["", "## Sample DOIs", ""])
        for doi in summary["sample_dois"]:
            lines.append(f"- `{doi}`")

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Crossref records aligned to latest normalized arXiv DOIs."
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Explicit normalized arXiv JSONL path. If omitted, latest under data/normalized/arxiv is used.",
    )
    parser.add_argument(
        "--mailto",
        default=None,
        help="Optional mailto for polite Crossref usage.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for Crossref requests. Crossref fetch is still one DOI per request internally.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional DOI cap for quick testing.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="HTTP timeout in seconds.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dt = utc_now()
    run_ts = ts_slug(run_dt)

    input_path = Path(args.input) if args.input else find_latest_normalized_file(ARXIV_NORMALIZED_DIR)
    input_rows = load_jsonl(input_path)

    doi_candidates, doi_to_doc = extract_candidate_dois(input_rows)

    if args.limit is not None:
        doi_candidates = doi_candidates[: args.limit]

    if not doi_candidates:
        raise RuntimeError(f"No DOI candidates found in normalized arXiv input: {input_path}")

    ingestor = CrossrefIngestor()

    raw_run_dir = RAW_ALIGNMENT_ROOT / run_ts
    raw_run_dir.mkdir(parents=True, exist_ok=True)

    normalized_docs: list[NormalizedDocument] = []
    raw_docs: list[RawDocument] = []
    match_rows: list[dict[str, Any]] = []
    fetched_entries_total = 0

    doi_batches = chunked(doi_candidates, max(1, args.batch_size))

    for batch_idx, doi_batch in enumerate(doi_batches):
        try:
            query = CrossrefQuery(
                dois=doi_batch,
                mailto=args.mailto,
                timeout=args.timeout,
            )
            feed = ingestor.fetch_feed(query)
            entries = ingestor.iter_entries(feed)
        except Exception as exc:
            for doi in doi_batch:
                arxiv_row = doi_to_doc.get(doi, {})
                match_rows.append(build_match_row(arxiv_row, None, error=repr(exc)))
            continue

        fetched_entries_total += len(entries)

        batch_raw_path = raw_run_dir / f"batch_{batch_idx:04d}.json"
        write_json(
            batch_raw_path,
            {
                "query_dois": doi_batch,
                "response": feed,
            },
        )

        found_by_doi: dict[str, NormalizedDocument] = {}

        for entry_idx, entry in enumerate(entries):
            raw_artifact_name = f"batch_{batch_idx:04d}_entry_{entry_idx:05d}.json"
            raw_artifact_path = raw_run_dir / raw_artifact_name
            write_json(raw_artifact_path, entry)

            raw_doc = ingestor.parse_entry_to_raw(entry)
            norm_doc = ingestor.parse_entry_to_normalized(
                entry,
                raw_artifact_path=raw_artifact_name,
            )

            raw_docs.append(raw_doc)
            normalized_docs.append(norm_doc)

            if norm_doc.doi:
                found_by_doi[norm_doc.doi] = norm_doc

        for doi in doi_batch:
            arxiv_row = doi_to_doc.get(doi, {})
            crossref_doc = found_by_doi.get(doi)
            match_rows.append(build_match_row(arxiv_row, crossref_doc))

    normalized_output_path = NORMALIZED_ALIGNMENT_DIR / f"documents.{run_ts}.jsonl"
    raw_output_path = raw_run_dir / "documents.raw.jsonl"

    write_jsonl(normalized_output_path, normalized_docs)
    write_jsonl(raw_output_path, raw_docs)

    status_counts = Counter(row["status"] for row in match_rows)

    summary = {
        "generated_at": run_ts,
        "input_file": str(input_path).replace("/", "\\"),
        "doi_candidates": len(doi_candidates),
        "doi_batches": len(doi_batches),
        "fetched_entries": fetched_entries_total,
        "normalized_docs": len(normalized_docs),
        "raw_docs": len(raw_docs),
        "raw_dir": str(raw_run_dir).replace("/", "\\"),
        "normalized_output": str(normalized_output_path).replace("/", "\\"),
        "status_counts": dict(status_counts),
        "sample_dois": doi_candidates[:10],
        "examples": {
            "match_rows": match_rows[:20],
            "normalized_examples": [doc.model_dump(mode="json") for doc in normalized_docs[:5]],
        },
    }

    latest_json = REPORTS_DIR / "crossref_alignment_ingest_latest.json"
    latest_md = REPORTS_DIR / "crossref_alignment_ingest_latest.md"
    hist_json = REPORTS_DIR / "history" / f"crossref_alignment_ingest_{run_ts}.json"
    hist_md = REPORTS_DIR / "history" / f"crossref_alignment_ingest_{run_ts}.md"

    write_json(latest_json, summary)
    write_json(hist_json, summary)

    md_report = build_markdown_report(summary)
    write_text(latest_md, md_report)
    write_text(hist_md, md_report)

    print(f"[OK] input file: {input_path}")
    print(f"[OK] DOI candidates: {len(doi_candidates)}")
    print(f"[OK] DOI batches: {len(doi_batches)}")
    print(f"[OK] fetched entries: {fetched_entries_total}")
    print(f"[OK] normalized docs: {len(normalized_docs)}")
    print(f"[OK] raw docs: {len(raw_docs)}")
    print(f"[OK] raw dir: {raw_run_dir}")
    print(f"[OK] normalized output: {normalized_output_path}")
    print(f"[OK] JSON report: {latest_json}")
    print(f"[OK] Markdown report: {latest_md}")


if __name__ == "__main__":
    main()