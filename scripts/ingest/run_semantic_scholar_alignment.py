from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from radar_core.contracts.document import NormalizedDocument
from radar_core.ingest.semantic_scholar import SemanticScholarIngestor, SemanticScholarQuery


DEFAULT_NORMALIZED_ROOT = Path("data/normalized")
DEFAULT_RAW_ROOT = Path("data/raw/semantic_scholar_alignment")
DEFAULT_OUTPUT_DIR = Path("data/normalized/semantic_scholar_alignment")
DEFAULT_REPORTS_DIR = Path("artifacts/reports")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ts_slug(dt: datetime | None = None) -> str:
    dt = dt or utc_now()
    return dt.strftime("%Y%m%dT%H%M%SZ")


def to_jsonable(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except TypeError:
            pass
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat().replace("+00:00", "Z")
    if isinstance(obj, list):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    return obj


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(to_jsonable(payload), f, ensure_ascii=False, indent=2)


def write_jsonl(path: Path, rows: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(to_jsonable(row), ensure_ascii=False))
            f.write("\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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

    pattern = re.compile(r"^documents\.\d{8}T\d{6}Z\.jsonl$")
    primary_snapshots = [p for p in candidates if pattern.match(p.name)]

    if primary_snapshots:
        return sorted(primary_snapshots)[-1]

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


def load_doi_candidates(path: Path, limit: int | None) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """
    Supports:
    1. plain text file with one DOI per line
    2. jsonl with at least field "doi"
    """
    if not path.exists():
        raise FileNotFoundError(f"DOI list file not found: {path}")

    doi_to_doc: dict[str, dict[str, Any]] = {}

    is_jsonl = path.suffix.lower() == ".jsonl"

    if is_jsonl:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                doi = normalize_doi(row.get("doi"))
                if not doi or doi in doi_to_doc:
                    continue
                doi_to_doc[doi] = row
                if limit is not None and len(doi_to_doc) >= limit:
                    break
    else:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                doi = normalize_doi(line.strip())
                if not doi or doi in doi_to_doc:
                    continue
                doi_to_doc[doi] = {
                    "doi": doi,
                    "source_bucket": "doi_list",
                    "input_file": str(path),
                }
                if limit is not None and len(doi_to_doc) >= limit:
                    break

    return sorted(doi_to_doc.keys()), doi_to_doc


def chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def build_markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Semantic Scholar alignment ingest",
        "",
        f"- generated_at: `{summary['generated_at']}`",
        f"- input_mode: `{summary['input_mode']}`",
        f"- input_file: `{summary['input_file']}`",
        f"- doi_candidates: **{summary['doi_candidates']}**",
        f"- doi_batches: **{summary['doi_batches']}**",
        f"- fetched_entries: **{summary['fetched_entries']}**",
        f"- normalized_docs: **{summary['normalized_docs']}**",
        f"- failed_batches: **{summary['failed_batches']}**",
        f"- raw_dir: `{summary['raw_dir']}`",
        f"- normalized_output: `{summary['normalized_output']}`",
    ]

    if summary.get("sample_dois"):
        lines.extend(["", "## Sample DOIs", ""])
        for doi in summary["sample_dois"]:
            lines.append(f"- `{doi}`")

    if summary.get("failed_batch_examples"):
        lines.extend(["", "## Failed batch examples", ""])
        for item in summary["failed_batch_examples"]:
            lines.append(
                f"- batch `{item['batch_index']}` / size `{item['batch_size']}` / error `{item['error']}`"
            )

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Semantic Scholar records aligned either from latest normalized arXiv DOIs or a selective DOI list."
    )
    parser.add_argument(
        "--input",
        help="Explicit normalized arXiv JSONL path. If omitted, latest under data/normalized/arxiv is used.",
    )
    parser.add_argument(
        "--doi-list",
        default=None,
        help="Optional path to DOI list input (.txt or .jsonl). If set, selective mode is used.",
    )
    parser.add_argument(
        "--normalized-root",
        default=str(DEFAULT_NORMALIZED_ROOT),
        help="Root directory containing normalized source subdirectories.",
    )
    parser.add_argument(
        "--raw-root",
        default=str(DEFAULT_RAW_ROOT),
        help="Root directory for raw Semantic Scholar alignment snapshots.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where normalized Semantic Scholar alignment JSONL files are written.",
    )
    parser.add_argument(
        "--reports-dir",
        default=str(DEFAULT_REPORTS_DIR),
        help="Directory for JSON/Markdown reports.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Optional Semantic Scholar API key.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Batch size for Semantic Scholar paper batch lookup.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on DOI candidates, useful for quick testing.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=1.5,
        help="Sleep between Semantic Scholar batches.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dt = utc_now()
    run_ts = ts_slug(run_dt)

    normalized_root = Path(args.normalized_root)
    raw_root = Path(args.raw_root)
    output_dir = Path(args.output_dir)
    reports_dir = Path(args.reports_dir)

    if args.doi_list:
        input_mode = "doi_list"
        input_path = Path(args.doi_list)
        doi_candidates, _doi_to_doc = load_doi_candidates(input_path, args.limit)

        print(f"[INFO] input_mode=doi_list")
        print(f"[INFO] doi_list_file resolved: {input_path}")
        print(f"[INFO] DOI candidates after limit: {len(doi_candidates)}")
    else:
        input_mode = "arxiv_snapshot"
        input_path = Path(args.input) if args.input else find_latest_normalized_file(normalized_root / "arxiv")
        input_rows = load_jsonl(input_path)

        doi_candidates, _doi_to_doc = extract_candidate_dois(input_rows)

        print(f"[INFO] input_mode=arxiv_snapshot")
        print(f"[INFO] input rows loaded: {len(input_rows)}")
        print(f"[INFO] DOI candidates before limit: {len(doi_candidates)}")
        print(f"[INFO] input file resolved: {input_path}")

        if args.limit is not None:
            doi_candidates = doi_candidates[: args.limit]

    if not doi_candidates:
        raise RuntimeError(
            f"No DOI candidates found for input: {input_path}"
        )

    ingestor = SemanticScholarIngestor()

    raw_run_dir = raw_root / run_ts
    raw_run_dir.mkdir(parents=True, exist_ok=True)

    normalized_docs: list[NormalizedDocument] = []
    fetched_entries_total = 0
    failed_batches = 0
    failed_batch_examples: list[dict[str, Any]] = []

    doi_batches = chunked(doi_candidates, max(1, args.batch_size))

    for batch_idx, doi_batch in enumerate(doi_batches):
        paper_ids = [f"DOI:{doi}" for doi in doi_batch]
        query = SemanticScholarQuery(
            paper_ids=paper_ids,
            api_key=args.api_key,
            timeout=args.timeout,
        )

        try:
            feed = ingestor.fetch_feed(query)
            entries = ingestor.iter_entries(feed)
            fetched_entries_total += len(entries)

            if (batch_idx + 1) % 10 == 0 or batch_idx == 0:
                print(
                    f"[INFO] batch {batch_idx + 1}/{len(doi_batches)} "
                    f"entries={len(entries)} "
                    f"fetched_total={fetched_entries_total}"
                )

            batch_raw_path = raw_run_dir / f"batch_{batch_idx:04d}.json"
            write_json(
                batch_raw_path,
                {
                    "query_paper_ids": paper_ids,
                    "response": feed,
                },
            )

            for entry_idx, entry in enumerate(entries):
                raw_artifact_name = f"batch_{batch_idx:04d}_entry_{entry_idx:05d}.json"
                raw_artifact_path = raw_run_dir / raw_artifact_name
                write_json(raw_artifact_path, entry)

                normalized = ingestor.parse_entry_to_normalized(
                    entry,
                    raw_artifact_path=raw_artifact_name,
                )
                normalized_docs.append(normalized)

        except Exception as exc:
            failed_batches += 1
            err_repr = repr(exc)

            print(
                f"[WARN] batch {batch_idx + 1}/{len(doi_batches)} failed: {err_repr}"
            )

            write_json(
                raw_run_dir / f"batch_{batch_idx:04d}.json",
                {
                    "query_paper_ids": paper_ids,
                    "error": err_repr,
                },
            )

            if len(failed_batch_examples) < 20:
                failed_batch_examples.append(
                    {
                        "batch_index": batch_idx + 1,
                        "batch_size": len(paper_ids),
                        "error": err_repr,
                    }
                )

        finally:
            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)

    normalized_output_path = output_dir / f"documents.{run_ts}.jsonl"
    write_jsonl(normalized_output_path, normalized_docs)

    summary = {
        "generated_at": run_ts,
        "input_mode": input_mode,
        "input_file": str(input_path).replace("/", "\\"),
        "doi_candidates": len(doi_candidates),
        "doi_batches": len(doi_batches),
        "fetched_entries": fetched_entries_total,
        "normalized_docs": len(normalized_docs),
        "failed_batches": failed_batches,
        "failed_batch_examples": failed_batch_examples,
        "raw_dir": str(raw_run_dir).replace("/", "\\"),
        "normalized_output": str(normalized_output_path).replace("/", "\\"),
        "sample_dois": doi_candidates[:10],
    }

    json_report_path = reports_dir / "semantic_scholar_alignment_ingest_latest.json"
    md_report_path = reports_dir / "semantic_scholar_alignment_ingest_latest.md"
    hist_json_path = reports_dir / "history" / f"semantic_scholar_alignment_ingest_{run_ts}.json"
    hist_md_path = reports_dir / "history" / f"semantic_scholar_alignment_ingest_{run_ts}.md"

    write_json(json_report_path, summary)
    write_json(hist_json_path, summary)

    md_report = build_markdown_report(summary)
    write_text(md_report_path, md_report)
    write_text(hist_md_path, md_report)

    print(f"[OK] input_mode: {input_mode}")
    print(f"[OK] input file: {input_path}")
    print(f"[OK] DOI candidates: {len(doi_candidates)}")
    print(f"[OK] DOI batches: {len(doi_batches)}")
    print(f"[OK] fetched entries: {fetched_entries_total}")
    print(f"[OK] normalized docs: {len(normalized_docs)}")
    print(f"[OK] failed batches: {failed_batches}")
    print(f"[OK] raw dir: {raw_run_dir}")
    print(f"[OK] normalized output: {normalized_output_path}")
    print(f"[OK] JSON report: {json_report_path}")
    print(f"[OK] Markdown report: {md_report_path}")


if __name__ == "__main__":
    main()