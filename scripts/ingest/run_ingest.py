from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from radar_core.ingest.arxiv import ArxivQuery
from radar_core.ingest.registry import get_ingestor
from radar_core.normalize.pipeline import deduplicate_documents, split_new_vs_updated
from radar_core.store.jsonl_store import JsonlDocumentStore
from radar_core.store.local_index import LocalDocumentIndex
from radar_core.store.run_manifest import IngestRunManifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        choices=["arxiv", "openalex"],
        default="arxiv",
        help="Источник данных для ingest",
    )
    parser.add_argument(
        "--mode",
        choices=["test", "full", "historical", "historical_2024"],
        default="test",
        help=(
            "test = быстрая latest-выборка, "
            "full = побольше latest-документов, "
            "historical = paper-centric historical slice для citation/reference анализа"
        ),
    )
    return parser


def build_openalex_query(mode: str):
    from radar_core.ingest.openalex import OpenAlexQuery

    api_key = os.getenv("OPENALEX_API_KEY")
    mailto = os.getenv("OPENALEX_MAILTO")

    # Latest radar slice: свежие paper-like работы
    latest_search_query = "machine learning deep learning neural network artificial intelligence"

    # Historical slice: чуть шире формулировка, чтобы собрать citation-rich корпус
    historical_search_query = (
        "machine learning deep learning artificial intelligence "
        "representation learning computer vision natural language processing"
    )

    if mode == "test":
        return OpenAlexQuery(
            search=latest_search_query,
            filter=(
                "from_publication_date:2025-01-01,"
                "type:article|preprint,"
                "has_abstract:true,"
                "has_doi:true,"
                "has_references:true"
            ),
            per_page=20,
            sort="publication_date:desc",
            mailto=mailto,
            api_key=api_key,
        )

    if mode == "full":
        return OpenAlexQuery(
            search=latest_search_query,
            filter=(
                "from_publication_date:2024-01-01,"
                "type:article|preprint,"
                "has_abstract:true,"
                "has_doi:true,"
                "has_references:true"
            ),
            per_page=50,
            sort="publication_date:desc",
            mailto=mailto,
            api_key=api_key,
        )

    if mode == "historical":
        return OpenAlexQuery(
            search=historical_search_query,
            filter=(
                "from_publication_date:2023-01-01,"
                "to_publication_date:2024-12-31,"
                "type:article|preprint,"
                "has_abstract:true,"
                "has_doi:true,"
                "has_references:true"
            ),
            per_page=100,
            sort="cited_by_count:desc",
            mailto=mailto,
            api_key=api_key,
        )

    if mode == "historical_2024":
        return OpenAlexQuery(
            search=historical_search_query,
            filter=(
                "from_publication_date:2024-01-01,"
                "to_publication_date:2024-12-31,"
                "type:article|preprint,"
                "has_abstract:true,"
                "has_doi:true,"
                "has_references:true"
            ),
            per_page=100,
            sort="cited_by_count:desc",
            mailto=mailto,
            api_key=api_key,
        )

    raise ValueError(f"Unsupported OpenAlex mode: {mode}")


def build_query(source: str, mode: str):
    if source == "arxiv":
        if mode == "test":
            return ArxivQuery(
                search_query="cat:cs.LG OR cat:cs.AI",
                start=0,
                max_results=10,
                sort_by="submittedDate",
                sort_order="descending",
            )

        # Для arXiv пока full и historical ведём одинаково,
        # чтобы не усложнять логику до следующей итерации.
        return ArxivQuery(
            search_query="cat:cs.LG OR cat:cs.AI OR cat:cs.CL",
            start=0,
            max_results=100,
            sort_by="submittedDate",
            sort_order="descending",
        )

    if source == "openalex":
        return build_openalex_query(mode)

    raise ValueError(f"Unsupported source for query builder: {source}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    source = args.source
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    store = JsonlDocumentStore(base_dir=Path("data"))
    raw_dir, normalized_dir, state_dir = store.prepare_run_dirs(source=source, run_ts=run_ts)

    state_path = state_dir / "local_document_index.json"

    query = build_query(source=source, mode=args.mode)

    local_index = LocalDocumentIndex(state_path)
    local_index.load()
    existing_hashes = local_index.get_content_hash_map(source=source)

    ingestor = get_ingestor(source)
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
    manifest_path = store.save_manifest(
        source=source,
        run_ts=run_ts,
        manifest=manifest.to_dict(),
    )

    print(f"[OK] source={source}")
    print(f"[OK] ingest finished: {len(deduped_docs)} documents")
    print(f"[OK] new={len(new_docs)} updated={len(updated_docs)} unchanged={len(unchanged_docs)}")
    print(f"[OK] raw saved to: {raw_dir}")
    print(f"[OK] normalized saved to: {normalized_dir}")
    print(f"[OK] state saved to: {state_path}")
    print(f"[OK] raw file: {raw_path}")
    print(f"[OK] manifest file: {manifest_path}")
    print(f"[OK] normalized all file: {normalized_paths['all']}")


if __name__ == "__main__":
    main()