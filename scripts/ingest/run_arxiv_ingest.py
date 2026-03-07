from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from radar_core.ingest.arxiv import ArxivIngestor, ArxivQuery
from radar_core.normalize.pipeline import deduplicate_documents, split_new_vs_updated
from radar_core.store.jsonl_store import JsonlDocumentStore
from radar_core.store.local_index import LocalDocumentIndex
from radar_core.store.run_manifest import IngestRunManifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["test", "full"],
        default="test",
        help="test = быстрая выборка, full = побольше документов",
    )
    return parser


def build_query(mode: str) -> ArxivQuery:
    if mode == "test":
        return ArxivQuery(
            search_query="cat:cs.LG OR cat:cs.AI",
            start=0,
            max_results=10,
            sort_by="submittedDate",
            sort_order="descending",
        )

    return ArxivQuery(
        search_query="cat:cs.LG OR cat:cs.AI OR cat:cs.CL",
        start=0,
        max_results=100,
        sort_by="submittedDate",
        sort_order="descending",
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    source = "arxiv"
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    store = JsonlDocumentStore(base_dir=Path("data"))
    raw_dir, normalized_dir, state_dir = store.prepare_run_dirs(source=source, run_ts=run_ts)

    state_path = state_dir / "local_document_index.json"

    query = build_query(args.mode)

    local_index = LocalDocumentIndex(state_path)
    local_index.load()
    existing_hashes = local_index.get_content_hash_map(source=source)

    ingestor = ArxivIngestor()
    raw_docs, normalized_docs = ingestor.ingest(query=query)

    deduped_docs = deduplicate_documents(normalized_docs)
    new_docs, updated_docs, unchanged_docs = split_new_vs_updated(
        deduped_docs,
        existing_hashes,
    )

    local_index.bulk_upsert_documents(deduped_docs, run_ts=run_ts)
    local_index.save()

    raw_rows = [doc.model_dump(mode="json") for doc in raw_docs]
    normalized_rows = [doc.model_dump(mode="json") for doc in deduped_docs]
    new_rows = [doc.model_dump(mode="json") for doc in new_docs]
    updated_rows = [doc.model_dump(mode="json") for doc in updated_docs]
    unchanged_rows = [doc.model_dump(mode="json") for doc in unchanged_docs]

    manifest = IngestRunManifest(
        run_ts=run_ts,
        source=source,
        mode=args.mode,
        query=query.__dict__,
        raw_count=len(raw_docs),
        normalized_count_before_dedup=len(normalized_docs),
        normalized_count_after_dedup=len(deduped_docs),
        new_count=len(new_docs),
        updated_count=len(updated_docs),
        unchanged_count=len(unchanged_docs),
        state_path=str(state_path).replace("\\", "/"),
    )

    raw_path = store.save_raw_documents(source=source, run_ts=run_ts, rows=raw_rows)
    normalized_paths = store.save_normalized_bundle(
        source=source,
        run_ts=run_ts,
        normalized_rows=normalized_rows,
        new_rows=new_rows,
        updated_rows=updated_rows,
        unchanged_rows=unchanged_rows,
    )
    manifest_path = store.save_manifest(source=source, run_ts=run_ts, manifest=manifest.to_dict())

    print(f"[OK] arXiv ingest finished: {len(deduped_docs)} documents")
    print(f"[OK] new={len(new_docs)} updated={len(updated_docs)} unchanged={len(unchanged_docs)}")
    print(f"[OK] raw saved to: {raw_dir}")
    print(f"[OK] normalized saved to: {normalized_dir}")
    print(f"[OK] state saved to: {state_path}")
    print(f"[OK] raw file: {raw_path}")
    print(f"[OK] manifest file: {manifest_path}")
    print(f"[OK] normalized all file: {normalized_paths['all']}")


if __name__ == "__main__":
    main()