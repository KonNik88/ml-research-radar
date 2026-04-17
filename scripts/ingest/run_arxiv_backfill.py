from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from radar_core.config import load_sources_config
from radar_core.ingest.arxiv import ArxivIngestor, ArxivQuery
from radar_core.normalize.pipeline import deduplicate_documents, split_new_vs_updated
from radar_core.store.jsonl_store import JsonlDocumentStore
from radar_core.store.local_index import LocalDocumentIndex
from radar_core.store.run_manifest import IngestRunManifest


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_medium_scale_profile(profile_name: str) -> dict[str, Any]:
    cfg = load_sources_config()
    profiles = cfg.get("profiles", {})
    if profile_name not in profiles:
        raise ValueError(f"Profile not found in configs/sources.yaml: {profile_name}")

    profile = profiles[profile_name]
    arxiv_cfg = profile.get("arxiv")
    if not arxiv_cfg:
        raise ValueError(f"Profile '{profile_name}' does not define arxiv config")

    return arxiv_cfg


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill arXiv corpus in multiple batches and save one aggregated normalized snapshot."
    )
    parser.add_argument(
        "--profile",
        default="medium_scale",
        help="Profile name from configs/sources.yaml",
    )
    parser.add_argument(
        "--search-query",
        default=None,
        help="Override arXiv search query",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Override batch size per arXiv request",
    )
    parser.add_argument(
        "--target-total",
        type=int,
        default=None,
        help="Override target total number of fetched records before dedup",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Initial start offset for arXiv",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="Optional safety cap on number of batches",
    )
    parser.add_argument(
        "--sort-by",
        default=None,
        help="Override arXiv sort_by",
    )
    parser.add_argument(
        "--sort-order",
        default=None,
        help="Override arXiv sort_order",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    profile_cfg = load_medium_scale_profile(args.profile)

    search_query = (args.search_query or profile_cfg.get("search_query") or "").strip()
    batch_size = int(args.batch_size or profile_cfg.get("batch_size", 1000))
    target_total = int(args.target_total or profile_cfg.get("target_total", 10000))
    sort_by = args.sort_by or profile_cfg.get("sort_by", "submittedDate")
    sort_order = args.sort_order or profile_cfg.get("sort_order", "descending")

    if not search_query:
        raise ValueError("search_query must be provided either in profile or via --search-query")
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    if target_total <= 0:
        raise ValueError("target_total must be > 0")
    if args.start < 0:
        raise ValueError("--start must be >= 0")

    run_ts = utc_now_ts()
    source = "arxiv"

    store = JsonlDocumentStore(base_dir=Path("data"))
    raw_dir, normalized_dir, state_dir = store.prepare_run_dirs(source=source, run_ts=run_ts)

    state_path = state_dir / "local_document_index.json"
    local_index = LocalDocumentIndex(state_path)
    local_index.load()
    existing_hashes = local_index.get_content_hash_map(source=source)

    ingestor = ArxivIngestor()

    all_raw_docs = []
    all_normalized_docs = []
    batch_reports: list[dict[str, Any]] = []

    fetched_total = 0
    current_start = args.start
    batch_no = 0

    while fetched_total < target_total:
        if args.max_batches is not None and batch_no >= args.max_batches:
            break

        remaining = target_total - fetched_total
        request_size = min(batch_size, remaining)

        query = ArxivQuery(
            search_query=search_query,
            start=current_start,
            max_results=request_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        raw_docs, normalized_docs = ingestor.ingest(query=query)

        raw_count = len(raw_docs)
        norm_count = len(normalized_docs)

        batch_reports.append(
            {
                "batch_no": batch_no,
                "start": current_start,
                "requested_max_results": request_size,
                "raw_count": raw_count,
                "normalized_count": norm_count,
                "query": asdict(query),
            }
        )

        if raw_count == 0:
            break

        all_raw_docs.extend(raw_docs)
        all_normalized_docs.extend(normalized_docs)

        fetched_total += raw_count
        current_start += request_size
        batch_no += 1

        print(
            f"[OK] batch={batch_no:03d} "
            f"start={current_start - request_size} "
            f"requested={request_size} raw={raw_count} normalized={norm_count} "
            f"fetched_total={fetched_total}"
        )

        if raw_count < request_size:
            break

    if not all_normalized_docs:
        raise RuntimeError("No arXiv documents were fetched in backfill run")

    deduped_docs = deduplicate_documents(all_normalized_docs)
    new_docs, updated_docs, unchanged_docs = split_new_vs_updated(deduped_docs, existing_hashes)

    local_index.bulk_upsert_documents(deduped_docs, run_ts=run_ts)
    local_index.save()

    raw_rows = [doc.model_dump(mode="json") for doc in all_raw_docs]
    normalized_rows = [doc.model_dump(mode="json") for doc in deduped_docs]
    new_rows = [doc.model_dump(mode="json") for doc in new_docs]
    updated_rows = [doc.model_dump(mode="json") for doc in updated_docs]
    unchanged_rows = [doc.model_dump(mode="json") for doc in unchanged_docs]

    final_query = {
        "profile": args.profile,
        "search_query": search_query,
        "initial_start": args.start,
        "final_next_start": current_start,
        "batch_size": batch_size,
        "target_total": target_total,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "max_batches": args.max_batches,
    }

    manifest = IngestRunManifest(
        run_ts=run_ts,
        source=source,
        mode=f"backfill:{args.profile}",
        query=final_query,
        raw_count=len(all_raw_docs),
        normalized_count_before_dedup=len(all_normalized_docs),
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

    batch_report_path = raw_dir / "batches.json"
    dump_json(
        batch_report_path,
        {
            "run_ts": run_ts,
            "profile": args.profile,
            "source": source,
            "batch_count": len(batch_reports),
            "batches": batch_reports,
            "summary": {
                "raw_count": len(all_raw_docs),
                "normalized_count_before_dedup": len(all_normalized_docs),
                "normalized_count_after_dedup": len(deduped_docs),
                "new_count": len(new_docs),
                "updated_count": len(updated_docs),
                "unchanged_count": len(unchanged_docs),
            },
        },
    )

    print(f"[OK] arXiv backfill finished")
    print(f"[OK] profile={args.profile}")
    print(f"[OK] batches={len(batch_reports)}")
    print(f"[OK] raw_count={len(all_raw_docs)}")
    print(f"[OK] normalized_before_dedup={len(all_normalized_docs)}")
    print(f"[OK] normalized_after_dedup={len(deduped_docs)}")
    print(f"[OK] new={len(new_docs)} updated={len(updated_docs)} unchanged={len(unchanged_docs)}")
    print(f"[OK] raw saved to: {raw_dir}")
    print(f"[OK] raw file: {raw_path}")
    print(f"[OK] manifest file: {manifest_path}")
    print(f"[OK] normalized all file: {normalized_paths['all']}")
    print(f"[OK] batch report: {batch_report_path}")


if __name__ == "__main__":
    main()