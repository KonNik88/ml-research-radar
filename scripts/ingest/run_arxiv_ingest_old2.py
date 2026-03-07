from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from radar_core.ingest.arxiv import ArxivIngestor, ArxivQuery
from radar_core.normalize.pipeline import deduplicate_documents, split_new_vs_updated


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_existing_content_hashes(normalized_dir: Path) -> dict[str, str]:
    existing: dict[str, str] = {}

    if not normalized_dir.exists():
        return existing

    for file_path in sorted(normalized_dir.glob("documents.*.jsonl")):
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                doc_id = row["doc_id"]
                content_hash = row["content_hash"]
                existing[doc_id] = content_hash

    return existing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["test", "full"],
        default="test",
        help="test = быстрая выборка, full = побольше документов",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    raw_dir = Path("data/raw/arxiv") / run_ts
    normalized_dir = Path("data/normalized/arxiv")

    ensure_dir(raw_dir)
    ensure_dir(normalized_dir)

    if args.mode == "test":
        query = ArxivQuery(
            search_query="cat:cs.LG OR cat:cs.AI",
            start=0,
            max_results=10,
            sort_by="submittedDate",
            sort_order="descending",
        )
    else:
        query = ArxivQuery(
            search_query="cat:cs.LG OR cat:cs.AI OR cat:cs.CL",
            start=0,
            max_results=100,
            sort_by="submittedDate",
            sort_order="descending",
        )

    existing_hashes = load_existing_content_hashes(normalized_dir)

    ingestor = ArxivIngestor()
    raw_docs, normalized_docs = ingestor.ingest(query=query)

    deduped_docs = deduplicate_documents(normalized_docs)
    new_docs, updated_docs, unchanged_docs = split_new_vs_updated(
        deduped_docs,
        existing_hashes,
    )

    manifest = {
        "run_ts": run_ts,
        "source": "arxiv",
        "mode": args.mode,
        "query": query.__dict__,
        "raw_count": len(raw_docs),
        "normalized_count_before_dedup": len(normalized_docs),
        "normalized_count_after_dedup": len(deduped_docs),
        "new_count": len(new_docs),
        "updated_count": len(updated_docs),
        "unchanged_count": len(unchanged_docs),
    }
    write_json(raw_dir / "manifest.json", manifest)

    raw_rows = [doc.model_dump(mode="json") for doc in raw_docs]
    normalized_rows = [doc.model_dump(mode="json") for doc in deduped_docs]
    new_rows = [doc.model_dump(mode="json") for doc in new_docs]
    updated_rows = [doc.model_dump(mode="json") for doc in updated_docs]
    unchanged_rows = [doc.model_dump(mode="json") for doc in unchanged_docs]

    write_jsonl(raw_dir / "documents.raw.jsonl", raw_rows)
    write_jsonl(normalized_dir / f"documents.{run_ts}.jsonl", normalized_rows)
    write_jsonl(normalized_dir / f"documents.{run_ts}.new.jsonl", new_rows)
    write_jsonl(normalized_dir / f"documents.{run_ts}.updated.jsonl", updated_rows)
    write_jsonl(normalized_dir / f"documents.{run_ts}.unchanged.jsonl", unchanged_rows)

    print(f"[OK] arXiv ingest finished: {len(deduped_docs)} documents")
    print(f"[OK] new={len(new_docs)} updated={len(updated_docs)} unchanged={len(unchanged_docs)}")
    print(f"[OK] raw saved to: {raw_dir}")
    print(f"[OK] normalized saved to: {normalized_dir}")


if __name__ == "__main__":
    main()