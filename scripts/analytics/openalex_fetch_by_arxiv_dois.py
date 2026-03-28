from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from radar_core.ingest.openalex import OpenAlexIngestor


OPENALEX_WORKS_API_BASE = "https://api.openalex.org/works"
ARXIV_DIR = Path("data/normalized/arxiv")
REPORTS_DIR = Path("artifacts/reports")
OUTPUT_DIR = Path("data/analytics/experimental")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def dump_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def dump_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def find_latest_primary_jsonl(base_dir: Path) -> Path:
    candidates = []
    for path in base_dir.glob("documents.*.jsonl"):
        name = path.name
        if ".new." in name or ".updated." in name or ".unchanged." in name:
            continue
        candidates.append(path)

    candidates = sorted(candidates)
    if not candidates:
        raise FileNotFoundError(f"No primary jsonl files found in {base_dir}")
    return candidates[-1]


def normalize_doi(value: Any) -> str | None:
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


def choose_arxiv_doi_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in rows:
        doi = normalize_doi(row.get("doi"))
        if not doi or doi in seen:
            continue
        seen.add(doi)
        selected.append(row)
        if len(selected) >= limit:
            break

    return selected


def fetch_openalex_by_doi(doi: str, *, mailto: str | None = None, api_key: str | None = None) -> dict[str, Any] | None:
    params: dict[str, Any] = {
        "filter": f"doi:{doi}",
        "per_page": 5,
    }
    if mailto:
        params["mailto"] = mailto
    if api_key:
        params["api_key"] = api_key

    response = requests.get(OPENALEX_WORKS_API_BASE, params=params, timeout=60)
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results") or []
    if not results:
        return None
    return results[0]


def build_match_row(arxiv_row: dict[str, Any], openalex_row: dict[str, Any] | None) -> dict[str, Any]:
    arxiv_doi = normalize_doi(arxiv_row.get("doi"))

    if openalex_row is None:
        return {
            "status": "not_found",
            "arxiv_doc_id": arxiv_row.get("doc_id"),
            "arxiv_title": arxiv_row.get("title"),
            "arxiv_year": arxiv_row.get("year"),
            "arxiv_doi": arxiv_doi,
            "openalex_doc_id": None,
            "openalex_title": None,
            "openalex_year": None,
            "openalex_doi": None,
        }

    openalex_doi = normalize_doi(openalex_row.get("doi"))
    return {
        "status": "found",
        "arxiv_doc_id": arxiv_row.get("doc_id"),
        "arxiv_title": arxiv_row.get("title"),
        "arxiv_year": arxiv_row.get("year"),
        "arxiv_doi": arxiv_doi,
        "openalex_doc_id": openalex_row.get("id"),
        "openalex_title": openalex_row.get("display_name") or openalex_row.get("title"),
        "openalex_year": openalex_row.get("publication_year"),
        "openalex_doi": openalex_doi,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# OpenAlex fetch by arXiv DOIs")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- arXiv input file: `{report['inputs']['arxiv_file']}`")
    lines.append(f"- arXiv docs total: {report['inputs']['arxiv_docs_total']}")
    lines.append(f"- arXiv docs with DOI: {report['inputs']['arxiv_docs_with_doi']}")
    lines.append(f"- Requested DOI count: {report['inputs']['requested_doi_count']}")
    lines.append("")
    lines.append("## Result summary")
    for k, v in report["summary"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Examples")
    for item in report["examples"]:
        lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch OpenAlex records by DOI list derived from latest arXiv normalized slice.")
    parser.add_argument(
        "--arxiv",
        default=None,
        help="Path to normalized arXiv JSONL. Defaults to latest primary file.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="How many unique arXiv DOIs to test.",
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
        help="Sleep between OpenAlex requests.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    ts = utc_now_ts()
    arxiv_path = Path(args.arxiv) if args.arxiv else find_latest_primary_jsonl(ARXIV_DIR)
    arxiv_rows = load_jsonl(arxiv_path)

    arxiv_with_doi = [row for row in arxiv_rows if normalize_doi(row.get("doi"))]
    selected_rows = choose_arxiv_doi_rows(arxiv_rows, args.limit)

    ingestor = OpenAlexIngestor()

    raw_results: list[dict[str, Any]] = []
    normalized_results: list[dict[str, Any]] = []
    match_rows: list[dict[str, Any]] = []

    for idx, arxiv_row in enumerate(selected_rows, start=1):
        doi = normalize_doi(arxiv_row.get("doi"))
        if not doi:
            continue

        try:
            result = fetch_openalex_by_doi(
                doi,
                mailto=args.mailto,
                api_key=args.api_key,
            )
        except Exception as e:
            match_rows.append(
                {
                    "status": "error",
                    "arxiv_doc_id": arxiv_row.get("doc_id"),
                    "arxiv_title": arxiv_row.get("title"),
                    "arxiv_year": arxiv_row.get("year"),
                    "arxiv_doi": doi,
                    "error": repr(e),
                }
            )
            time.sleep(args.sleep_seconds)
            continue

        match_rows.append(build_match_row(arxiv_row, result))

        if result is not None:
            raw_doc = ingestor.parse_entry_to_raw(result)
            norm_doc = ingestor.parse_entry_to_normalized(result)

            raw_results.append(raw_doc.model_dump(mode="json"))
            normalized_results.append(norm_doc.model_dump(mode="json"))

        time.sleep(args.sleep_seconds)

    status_counter = Counter(row["status"] for row in match_rows)

    report = {
        "report_name": "openalex_fetch_by_arxiv_dois",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "arxiv_file": str(arxiv_path),
            "arxiv_docs_total": len(arxiv_rows),
            "arxiv_docs_with_doi": len(arxiv_with_doi),
            "requested_doi_count": len(selected_rows),
        },
        "summary": dict(status_counter),
        "examples": match_rows[:20],
        "artifacts": {
            "raw_jsonl": str(OUTPUT_DIR / f"openalex_by_arxiv_dois_raw.{ts}.jsonl"),
            "normalized_jsonl": str(OUTPUT_DIR / f"openalex_by_arxiv_dois_normalized.{ts}.jsonl"),
        },
    }

    raw_out = OUTPUT_DIR / f"openalex_by_arxiv_dois_raw.{ts}.jsonl"
    norm_out = OUTPUT_DIR / f"openalex_by_arxiv_dois_normalized.{ts}.jsonl"
    report_json = REPORTS_DIR / "openalex_fetch_by_arxiv_dois_latest.json"
    report_md = REPORTS_DIR / "openalex_fetch_by_arxiv_dois_latest.md"
    hist_json = REPORTS_DIR / "history" / f"openalex_fetch_by_arxiv_dois_{ts}.json"
    hist_md = REPORTS_DIR / "history" / f"openalex_fetch_by_arxiv_dois_{ts}.md"

    dump_jsonl(raw_out, raw_results)
    dump_jsonl(norm_out, normalized_results)
    dump_json(report_json, report)
    dump_text(report_md, render_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, render_markdown(report))

    print(f"[OK] arXiv docs total: {len(arxiv_rows)}")
    print(f"[OK] arXiv docs with DOI: {len(arxiv_with_doi)}")
    print(f"[OK] requested DOI count: {len(selected_rows)}")
    print(f"[OK] summary: {dict(status_counter)}")
    print(f"[OK] raw JSONL: {raw_out}")
    print(f"[OK] normalized JSONL: {norm_out}")
    print(f"[OK] report JSON: {report_json}")
    print(f"[OK] report MD: {report_md}")


if __name__ == "__main__":
    main()