from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from radar_core.ingest.arxiv import ArxivIngestor, ArxivQuery
from radar_core.normalize.pipeline import deduplicate_documents, split_new_vs_updated
from radar_core.store.local_index import LocalDocumentIndex


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
    state_dir = Path("data/state")
    state_path = state_dir / "local_document_index.json"

    ensure_dir(raw_dir)
    ensure_dir(normalized_dir)
    ensure_dir(state_dir)

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

    local_index = LocalDocumentIndex(state_path)
    local_index.load()
    existing_hashes = local_index.get_content_hash_map(source="arxiv")

    ingestor = ArxivIngestor()
    raw_docs, normalized_docs = ingestor.ingest(query=query)

    deduped_docs = deduplicate_documents(normalized_docs)
    new_docs, updated_docs, unchanged_docs = split_new_vs_updated(
        deduped_docs,
        existing_hashes,
    )

    local_index.bulk_upsert_documents(deduped_docs, run_ts=run_ts)
    local_index.save()

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
        "state_path": str(state_path).replace("\\", "/"),
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
    print(f"[OK] state saved to: {state_path}")


if __name__ == "__main__":
    main()