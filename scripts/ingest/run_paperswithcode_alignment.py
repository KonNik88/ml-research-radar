from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from radar_core.ingest.paperswithcode import PapersWithCodeIngestor
from radar_core.ingest.pwc_client import (
    PWCRequestTrace,
    fetch_pwc_entry,
    normalize_arxiv_id,
    normalize_doi,
)


ARXIV_NORMALIZED_DIR = Path("data/normalized/arxiv")
RAW_ALIGNMENT_ROOT = Path("data/raw/paperswithcode_alignment")
NORMALIZED_ALIGNMENT_DIR = Path("data/normalized/paperswithcode_alignment")
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


def choose_unique_arxiv_rows(rows: list[dict[str, Any]], limit: Optional[int]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in rows:
        doi = normalize_doi(row.get("doi"))
        arxiv_id = normalize_arxiv_id(row.get("arxiv_id")) or normalize_arxiv_id(
            (row.get("external_ids") or {}).get("arxiv")
        )

        if not doi and not arxiv_id:
            continue

        key = f"doi::{doi}" if doi else f"arxiv::{arxiv_id}"
        if key in seen:
            continue

        seen.add(key)
        selected.append(row)

        if limit is not None and len(selected) >= limit:
            break

    return selected


def build_match_row(
    arxiv_row: dict[str, Any],
    pwc_entry: Optional[dict[str, Any]],
    *,
    error: Optional[str] = None,
) -> dict[str, Any]:
    arxiv_doi = normalize_doi(arxiv_row.get("doi"))
    arxiv_id = normalize_arxiv_id(arxiv_row.get("arxiv_id")) or normalize_arxiv_id(
        (arxiv_row.get("external_ids") or {}).get("arxiv")
    )

    if error is not None:
        return {
            "status": "error",
            "arxiv_doc_id": arxiv_row.get("doc_id"),
            "arxiv_title": arxiv_row.get("title"),
            "arxiv_year": arxiv_row.get("year"),
            "arxiv_doi": arxiv_doi,
            "arxiv_id": arxiv_id,
            "pwc_id": None,
            "pwc_title": None,
            "error": error,
        }

    if pwc_entry is None:
        return {
            "status": "not_found",
            "arxiv_doc_id": arxiv_row.get("doc_id"),
            "arxiv_title": arxiv_row.get("title"),
            "arxiv_year": arxiv_row.get("year"),
            "arxiv_doi": arxiv_doi,
            "arxiv_id": arxiv_id,
            "pwc_id": None,
            "pwc_title": None,
        }

    return {
        "status": "found",
        "arxiv_doc_id": arxiv_row.get("doc_id"),
        "arxiv_title": arxiv_row.get("title"),
        "arxiv_year": arxiv_row.get("year"),
        "arxiv_doi": arxiv_doi,
        "arxiv_id": arxiv_id,
        "pwc_id": pwc_entry.get("id") or pwc_entry.get("paper_id") or pwc_entry.get("slug"),
        "pwc_title": pwc_entry.get("title") or pwc_entry.get("paper_title"),
        "has_repo_signal": bool(
            pwc_entry.get("official_repository")
            or pwc_entry.get("repositories")
            or pwc_entry.get("implementation")
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Papers with Code alignment ingest")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- arXiv input file: `{report['inputs']['arxiv_file']}`")
    lines.append(f"- selected candidates: {report['inputs']['requested_candidate_count']}")
    lines.append("")
    lines.append("## Summary")
    for key, value in report["summary"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Artifacts")
    for key, value in report["artifacts"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## Example match rows")
    for item in report["examples"]["match_rows"]:
        lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    return "\n".join(lines)


def traces_to_jsonable(traces: list[PWCRequestTrace]) -> list[dict[str, Any]]:
    return [
        {
            "query_type": t.query_type,
            "query_value": t.query_value,
            "url": t.url,
            "params": t.params,
            "status_code": t.status_code,
            "ok": t.ok,
            "response_preview": t.response_preview,
            "error": t.error,
        }
        for t in traces
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Papers with Code enrichment aligned to latest normalized arXiv corpus."
    )
    parser.add_argument("--arxiv", default=None, help="Path to normalized arXiv JSONL.")
    parser.add_argument("--limit", type=int, default=30, help="Max unique arXiv candidates.")
    parser.add_argument("--sleep-seconds", type=float, default=0.2, help="Sleep between requests.")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout in seconds.")
    parser.add_argument(
        "--api-base",
        default="https://paperswithcode.com/api/v1",
        help="Base URL for Papers with Code-compatible API.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Store request/response diagnostics for first N queries.",
    )
    parser.add_argument(
        "--debug-limit",
        type=int,
        default=5,
        help="How many candidates to capture detailed debug traces for.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ts = utc_now_ts()

    arxiv_path = Path(args.arxiv) if args.arxiv else latest_primary_jsonl(ARXIV_NORMALIZED_DIR)
    arxiv_rows = load_jsonl(arxiv_path)
    selected_rows = choose_unique_arxiv_rows(arxiv_rows, args.limit)

    raw_run_dir = RAW_ALIGNMENT_ROOT / ts
    raw_jsonl_path = raw_run_dir / "documents.raw.jsonl"
    raw_manifest_path = raw_run_dir / "manifest.json"
    debug_json_path = raw_run_dir / "debug_requests.json"

    normalized_jsonl_path = NORMALIZED_ALIGNMENT_DIR / f"documents.{ts}.jsonl"

    ingestor = PapersWithCodeIngestor()

    raw_docs: list[dict[str, Any]] = []
    normalized_docs: list[dict[str, Any]] = []
    match_rows: list[dict[str, Any]] = []
    debug_traces: list[PWCRequestTrace] = []

    for idx, arxiv_row in enumerate(selected_rows):
        doi = normalize_doi(arxiv_row.get("doi"))
        arxiv_id = normalize_arxiv_id(arxiv_row.get("arxiv_id")) or normalize_arxiv_id(
            (arxiv_row.get("external_ids") or {}).get("arxiv")
        )
        title = arxiv_row.get("title")

        trace_bucket = debug_traces if args.debug and idx < args.debug_limit else None

        try:
            entry = fetch_pwc_entry(
                doi=doi,
                arxiv_id=arxiv_id,
                title=title,
                timeout=args.timeout,
                api_base=args.api_base,
                max_results_per_identifier=5,
                debug=bool(trace_bucket is not None),
                traces=trace_bucket,
                sleep_seconds=args.sleep_seconds,
            )
        except Exception as e:
            match_rows.append(build_match_row(arxiv_row, None, error=repr(e)))
            continue

        match_rows.append(build_match_row(arxiv_row, entry))

        if entry is None:
            continue

        raw_doc = ingestor.parse_entry_to_raw(entry)
        normalized_doc = ingestor.parse_entry_to_normalized(
            entry,
            raw_artifact_path=f"batch_0000_entry_{len(raw_docs):05d}.json",
        )

        raw_docs.append(raw_doc.model_dump(mode="json"))
        normalized_docs.append(normalized_doc.model_dump(mode="json"))

    dump_jsonl(raw_jsonl_path, raw_docs)
    dump_jsonl(normalized_jsonl_path, normalized_docs)

    status_counter = Counter(row["status"] for row in match_rows)
    repo_enriched = sum(
        1 for row in normalized_docs
        if row.get("repo_url") or row.get("code_links")
    )
    dataset_enriched = sum(
        1 for row in normalized_docs
        if row.get("dataset_links")
    )

    manifest = {
        "generated_at_utc": utc_now_iso(),
        "source": "paperswithcode_alignment",
        "input_arxiv_file": str(arxiv_path),
        "raw_jsonl": str(raw_jsonl_path),
        "normalized_jsonl": str(normalized_jsonl_path),
        "requested_candidate_count": len(selected_rows),
        "matched_count": status_counter.get("found", 0),
        "normalized_count": len(normalized_docs),
    }
    dump_json(raw_manifest_path, manifest)

    if args.debug:
        dump_json(debug_json_path, {"traces": traces_to_jsonable(debug_traces)})

    report = {
        "report_name": "paperswithcode_alignment_ingest",
        "generated_at_utc": utc_now_iso(),
        "inputs": {
            "arxiv_file": str(arxiv_path),
            "arxiv_total_docs": len(arxiv_rows),
            "requested_candidate_count": len(selected_rows),
            "debug_enabled": args.debug,
            "debug_limit": args.debug_limit,
        },
        "summary": {
            "found": status_counter.get("found", 0),
            "not_found": status_counter.get("not_found", 0),
            "error": status_counter.get("error", 0),
            "normalized_count": len(normalized_docs),
            "repo_enriched_count": repo_enriched,
            "dataset_enriched_count": dataset_enriched,
        },
        "artifacts": {
            "raw_jsonl": str(raw_jsonl_path),
            "raw_manifest": str(raw_manifest_path),
            "normalized_jsonl": str(normalized_jsonl_path),
            "debug_requests_json": str(debug_json_path) if args.debug else None,
        },
        "examples": {
            "match_rows": match_rows[:10],
            "normalized_examples": normalized_docs[:5],
        },
    }

    report_json_path = REPORTS_DIR / f"paperswithcode_alignment_ingest_{ts}.json"
    report_md_path = REPORTS_DIR / f"paperswithcode_alignment_ingest_{ts}.md"
    latest_json_path = REPORTS_DIR / "paperswithcode_alignment_ingest_latest.json"
    latest_md_path = REPORTS_DIR / "paperswithcode_alignment_ingest_latest.md"

    dump_json(report_json_path, report)
    dump_text(report_md_path, render_markdown(report))
    dump_json(latest_json_path, report)
    dump_text(latest_md_path, render_markdown(report))

    print(f"[OK] arXiv input: {arxiv_path}")
    print(f"[OK] selected candidates: {len(selected_rows)}")
    print(f"[OK] found: {status_counter.get('found', 0)}")
    print(f"[OK] not_found: {status_counter.get('not_found', 0)}")
    print(f"[OK] errors: {status_counter.get('error', 0)}")
    print(f"[OK] normalized docs: {len(normalized_docs)}")
    print(f"[OK] repo-enriched docs: {repo_enriched}")
    if args.debug:
        print(f"[OK] debug traces: {debug_json_path}")
    print(f"[OK] saved normalized slice: {normalized_jsonl_path}")


if __name__ == "__main__":
    main()