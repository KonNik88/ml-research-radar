from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from radar_core.contracts.document import NormalizedDocument, RawDocument
from radar_core.ingest.openalex import OpenAlexIngestor


OPENALEX_WORKS_API_BASE = "https://api.openalex.org/works"

ARXIV_NORMALIZED_DIR = Path("data/normalized/arxiv")
RAW_ALIGNMENT_ROOT = Path("data/raw/openalex_alignment")
NORMALIZED_ALIGNMENT_DIR = Path("data/normalized/openalex_alignment")
REPORTS_DIR = Path("artifacts/reports")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def dump_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def latest_primary_jsonl(base_dir: Path) -> Path:
    candidates = sorted(
        p
        for p in base_dir.glob("documents.*.jsonl")
        if ".new." not in p.name
        and ".updated." not in p.name
        and ".unchanged." not in p.name
    )
    if not candidates:
        raise FileNotFoundError(f"No primary normalized JSONL files found in: {base_dir}")
    return candidates[-1]


def normalize_doi(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower()
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


def choose_unique_arxiv_rows_with_doi(rows: list[dict[str, Any]], limit: Optional[int]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_dois: set[str] = set()

    for row in rows:
        doi = normalize_doi(row.get("doi"))
        if not doi or doi in seen_dois:
            continue
        seen_dois.add(doi)
        selected.append(row)
        if limit is not None and len(selected) >= limit:
            break

    return selected


def load_doi_candidates(path: Path, limit: Optional[int]) -> list[dict[str, Any]]:
    """
    Supports:
    1. plain text file with one DOI per line
    2. jsonl with at least field "doi"
    """
    if not path.exists():
        raise FileNotFoundError(f"DOI list file not found: {path}")

    selected: list[dict[str, Any]] = []
    seen_dois: set[str] = set()

    is_jsonl = path.suffix.lower() == ".jsonl"

    if is_jsonl:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                doi = normalize_doi(row.get("doi"))
                if not doi or doi in seen_dois:
                    continue
                seen_dois.add(doi)

                selected.append(
                    {
                        "doc_id": row.get("doc_id"),
                        "title": row.get("title"),
                        "year": row.get("year"),
                        "doi": doi,
                        "arxiv_id": row.get("arxiv_id"),
                        "source_bucket": row.get("source_bucket"),
                        "input_file": row.get("input_file"),
                    }
                )
                if limit is not None and len(selected) >= limit:
                    break
    else:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                doi = normalize_doi(line.strip())
                if not doi or doi in seen_dois:
                    continue
                seen_dois.add(doi)
                selected.append(
                    {
                        "doc_id": None,
                        "title": None,
                        "year": None,
                        "doi": doi,
                        "arxiv_id": None,
                        "source_bucket": "doi_list",
                        "input_file": str(path),
                    }
                )
                if limit is not None and len(selected) >= limit:
                    break

    return selected


def fetch_openalex_by_doi(
    doi: str,
    *,
    mailto: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: int = 60,
) -> Optional[dict[str, Any]]:
    params: dict[str, Any] = {
        "filter": f"doi:{doi}",
        "per_page": 5,
    }
    if mailto:
        params["mailto"] = mailto
    if api_key:
        params["api_key"] = api_key

    response = requests.get(OPENALEX_WORKS_API_BASE, params=params, timeout=timeout)
    response.raise_for_status()

    payload = response.json()
    results = payload.get("results") or []
    if not results:
        return None

    return results[0]


def build_match_row(input_row: dict[str, Any], openalex_entry: Optional[dict[str, Any]], *, error: Optional[str] = None) -> dict[str, Any]:
    input_doi = normalize_doi(input_row.get("doi"))

    if error is not None:
        return {
            "status": "error",
            "input_doc_id": input_row.get("doc_id"),
            "input_title": input_row.get("title"),
            "input_year": input_row.get("year"),
            "input_arxiv_id": input_row.get("arxiv_id"),
            "input_doi": input_doi,
            "source_bucket": input_row.get("source_bucket"),
            "openalex_id": None,
            "openalex_title": None,
            "openalex_year": None,
            "openalex_doi": None,
            "error": error,
        }

    if openalex_entry is None:
        return {
            "status": "not_found",
            "input_doc_id": input_row.get("doc_id"),
            "input_title": input_row.get("title"),
            "input_year": input_row.get("year"),
            "input_arxiv_id": input_row.get("arxiv_id"),
            "input_doi": input_doi,
            "source_bucket": input_row.get("source_bucket"),
            "openalex_id": None,
            "openalex_title": None,
            "openalex_year": None,
            "openalex_doi": None,
        }

    openalex_doi = normalize_doi(openalex_entry.get("doi"))
    return {
        "status": "found",
        "input_doc_id": input_row.get("doc_id"),
        "input_title": input_row.get("title"),
        "input_year": input_row.get("year"),
        "input_arxiv_id": input_row.get("arxiv_id"),
        "input_doi": input_doi,
        "source_bucket": input_row.get("source_bucket"),
        "openalex_id": openalex_entry.get("id"),
        "openalex_title": openalex_entry.get("display_name") or openalex_entry.get("title"),
        "openalex_year": openalex_entry.get("publication_year"),
        "openalex_doi": openalex_doi,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# OpenAlex alignment ingest")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Input mode: `{report['inputs']['input_mode']}`")
    lines.append(f"- Requested DOI count: {report['inputs']['requested_doi_count']}")
    if report["inputs"].get("arxiv_file") is not None:
        lines.append(f"- arXiv input file: `{report['inputs']['arxiv_file']}`")
        lines.append(f"- arXiv total docs: {report['inputs']['arxiv_total_docs']}")
        lines.append(f"- arXiv docs with DOI: {report['inputs']['arxiv_docs_with_doi']}")
    if report["inputs"].get("doi_list_file") is not None:
        lines.append(f"- DOI list file: `{report['inputs']['doi_list_file']}`")
    lines.append("")
    lines.append("## Summary")
    for key, value in report["summary"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Artifacts")
    for key, value in report["artifacts"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## Example matches")
    for item in report["examples"]["match_rows"]:
        lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    lines.append("")
    lines.append("## Example normalized records")
    for item in report["examples"]["normalized_examples"]:
        lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch OpenAlex enrichment aligned either from latest arXiv DOI subset or from a selective DOI list."
    )
    parser.add_argument(
        "--arxiv",
        default=None,
        help="Path to normalized arXiv JSONL. Defaults to latest primary file.",
    )
    parser.add_argument(
        "--doi-list",
        default=None,
        help="Optional path to DOI list input (.txt or .jsonl). If set, selective mode is used.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of unique DOIs to request from OpenAlex.",
    )
    parser.add_argument(
        "--mailto",
        default=None,
        help="Optional mailto for OpenAlex polite pool.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Optional OpenAlex API key.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.2,
        help="Sleep between requests.",
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
    ts = utc_now_ts()

    raw_run_dir = RAW_ALIGNMENT_ROOT / ts
    raw_jsonl_path = raw_run_dir / "documents.raw.jsonl"
    raw_manifest_path = raw_run_dir / "manifest.json"
    normalized_jsonl_path = NORMALIZED_ALIGNMENT_DIR / f"documents.{ts}.jsonl"

    ingestor = OpenAlexIngestor()

    input_mode: str
    selected_rows: list[dict[str, Any]]
    arxiv_path_str: str | None = None
    arxiv_total_docs: int | None = None
    arxiv_docs_with_doi: int | None = None
    doi_list_file: str | None = None

    if args.doi_list:
        input_mode = "doi_list"
        doi_list_path = Path(args.doi_list)
        doi_list_file = str(doi_list_path)
        selected_rows = load_doi_candidates(doi_list_path, args.limit)
    else:
        input_mode = "arxiv_snapshot"
        arxiv_path = Path(args.arxiv) if args.arxiv else latest_primary_jsonl(ARXIV_NORMALIZED_DIR)
        arxiv_rows = load_jsonl(arxiv_path)
        arxiv_with_doi = [row for row in arxiv_rows if normalize_doi(row.get("doi"))]
        selected_rows = choose_unique_arxiv_rows_with_doi(arxiv_rows, args.limit)

        arxiv_path_str = str(arxiv_path)
        arxiv_total_docs = len(arxiv_rows)
        arxiv_docs_with_doi = len(arxiv_with_doi)

    raw_docs: list[dict[str, Any]] = []
    normalized_docs: list[dict[str, Any]] = []
    match_rows: list[dict[str, Any]] = []

    for idx, input_row in enumerate(selected_rows):
        doi = normalize_doi(input_row.get("doi"))
        if not doi:
            continue

        try:
            entry = fetch_openalex_by_doi(
                doi,
                mailto=args.mailto,
                api_key=args.api_key,
                timeout=args.timeout,
            )
        except Exception as e:
            match_rows.append(build_match_row(input_row, None, error=repr(e)))
            if idx < len(selected_rows) - 1:
                time.sleep(args.sleep_seconds)
            continue

        match_rows.append(build_match_row(input_row, entry))

        if entry is not None:
            raw_artifact_path = f"entry_{len(raw_docs):05d}.json"

            raw_doc: RawDocument = ingestor.parse_entry_to_raw(entry)
            normalized_doc: NormalizedDocument = ingestor.parse_entry_to_normalized(
                entry,
                raw_artifact_path=raw_artifact_path,
            )

            raw_docs.append(raw_doc.model_dump(mode="json"))
            normalized_docs.append(normalized_doc.model_dump(mode="json"))

        if idx < len(selected_rows) - 1:
            time.sleep(args.sleep_seconds)

    status_counter = Counter(row["status"] for row in match_rows)

    dump_jsonl(raw_jsonl_path, raw_docs)
    dump_jsonl(normalized_jsonl_path, normalized_docs)

    manifest = {
        "source": "openalex_alignment",
        "generated_at_utc": utc_now_iso(),
        "input_mode": input_mode,
        "arxiv_input_file": arxiv_path_str,
        "doi_list_file": doi_list_file,
        "raw_jsonl": str(raw_jsonl_path),
        "normalized_jsonl": str(normalized_jsonl_path),
        "requested_doi_count": len(selected_rows),
        "summary": dict(status_counter),
    }
    dump_json(raw_manifest_path, manifest)

    report = {
        "report_name": "openalex_alignment_ingest",
        "generated_at_utc": utc_now_iso(),
        "inputs": {
            "input_mode": input_mode,
            "arxiv_file": arxiv_path_str,
            "arxiv_total_docs": arxiv_total_docs,
            "arxiv_docs_with_doi": arxiv_docs_with_doi,
            "doi_list_file": doi_list_file,
            "requested_doi_count": len(selected_rows),
        },
        "summary": {
            "found": status_counter.get("found", 0),
            "not_found": status_counter.get("not_found", 0),
            "error": status_counter.get("error", 0),
            "raw_docs_written": len(raw_docs),
            "normalized_docs_written": len(normalized_docs),
        },
        "artifacts": {
            "raw_run_dir": str(raw_run_dir),
            "raw_jsonl": str(raw_jsonl_path),
            "raw_manifest": str(raw_manifest_path),
            "normalized_jsonl": str(normalized_jsonl_path),
        },
        "examples": {
            "match_rows": match_rows[:20],
            "normalized_examples": normalized_docs[:5],
        },
    }

    latest_json = REPORTS_DIR / "openalex_alignment_ingest_latest.json"
    latest_md = REPORTS_DIR / "openalex_alignment_ingest_latest.md"
    hist_json = REPORTS_DIR / "history" / f"openalex_alignment_ingest_{ts}.json"
    hist_md = REPORTS_DIR / "history" / f"openalex_alignment_ingest_{ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, render_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, render_markdown(report))

    if input_mode == "arxiv_snapshot":
        print(f"[OK] input_mode={input_mode}")
        print(f"[OK] arXiv total docs: {arxiv_total_docs}")
        print(f"[OK] arXiv docs with DOI: {arxiv_docs_with_doi}")
    else:
        print(f"[OK] input_mode={input_mode}")
        print(f"[OK] doi_list_file={doi_list_file}")

    print(f"[OK] requested DOI count: {len(selected_rows)}")
    print(f"[OK] summary: {dict(status_counter)}")
    print(f"[OK] raw saved to: {raw_run_dir}")
    print(f"[OK] normalized saved to: {normalized_jsonl_path}")
    print(f"[OK] raw manifest: {raw_manifest_path}")
    print(f"[OK] report JSON: {latest_json}")
    print(f"[OK] report MD: {latest_md}")


if __name__ == "__main__":
    main()