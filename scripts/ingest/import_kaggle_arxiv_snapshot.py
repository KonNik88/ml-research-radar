from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.ingest.kaggle_arxiv_snapshot_utils import (
    detect_snapshot_format,
    iter_snapshot_rows,
    load_arxiv_taxonomy_categories,
    map_kaggle_row_to_documents,
    normalize_text,
    parse_categories,
    row_matches_categories,
    ts_slug,
)

from radar_core.store.jsonl_store import JsonlDocumentStore
from radar_core.store.local_index import LocalDocumentIndex
from radar_core.normalize.pipeline import deduplicate_documents, split_new_vs_updated


DEFAULT_BASE_DIR = Path("data")
DEFAULT_STATE_PATH = Path("data/state/local_document_index.json")
DEFAULT_REPORTS_DIR = Path("artifacts/reports")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import Kaggle arXiv bulk snapshot into the existing arXiv normalized source axis."
    )
    parser.add_argument("--input", required=True, help="Path to Kaggle arXiv snapshot.")
    parser.add_argument("--format", default="auto", choices=["auto", "ndjson", "json_array"])
    parser.add_argument("--base-dir", default=str(DEFAULT_BASE_DIR))
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on imported rows after filtering.",
    )
    parser.add_argument(
        "--core-categories-only",
        action="store_true",
        help="Use only taxonomy.core_categories.arxiv.",
    )
    parser.add_argument("--min-year", type=int, default=None)
    parser.add_argument("--max-year", type=int, default=None)
    parser.add_argument("--require-abstract", action="store_true")
    parser.add_argument("--skip-raw", action="store_true", help="Do not persist RawDocument bundle.")
    parser.add_argument(
        "--taxonomy-path",
        default="configs/taxonomy.yaml",
        help="Path to taxonomy config.",
    )
    parser.add_argument(
        "--categories-mode",
        choices=["expanded", "core"],
        default="expanded",
        help="Use taxonomy core categories only or expanded core+topic-group categories.",
    )
    parser.add_argument(
        "--categories",
        nargs="*",
        default=None,
        help="Explicit category override. If provided, taxonomy categories are ignored.",
    )
    parser.add_argument("--report-every", type=int, default=5000)
    return parser


def _parse_wanted_categories(args: argparse.Namespace) -> set[str] | None:
    if args.categories:
        return {c.strip() for c in args.categories if c and c.strip()}

    if args.core_categories_only:
        return set(
            load_arxiv_taxonomy_categories(
                args.taxonomy_path,
                mode="core",
            )
        )

    return set(
        load_arxiv_taxonomy_categories(
            args.taxonomy_path,
            mode=args.categories_mode,
        )
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = build_parser().parse_args()
    run_ts = ts_slug()

    input_path = Path(args.input)
    base_dir = Path(args.base_dir)
    state_path = Path(args.state_path)
    reports_dir = Path(args.reports_dir)

    resolved_format = (
        detect_snapshot_format(input_path).format_name
        if args.format == "auto"
        else args.format
    )

    wanted_categories = _parse_wanted_categories(args)

    store = JsonlDocumentStore(base_dir=base_dir)
    store.prepare_run_dirs(source="arxiv", run_ts=run_ts)

    local_index = LocalDocumentIndex(state_path)
    local_index.load()
    existing_hashes = local_index.get_content_hash_map(source="arxiv")

    raw_rows: list[dict[str, Any]] = []
    normalized_docs = []
    seen_doc_ids: set[str] = set()

    stats = Counter()
    category_counter: Counter[str] = Counter()

    for row_index, row in iter_snapshot_rows(input_path, format_name=resolved_format):
        stats["rows_seen"] += 1

        categories = parse_categories(row.get("categories"))
        if wanted_categories and not row_matches_categories(categories, wanted_categories):
            stats["filtered_category"] += 1
            continue

        mapped = map_kaggle_row_to_documents(
            row,
            raw_artifact_path=f"{input_path.name}#row={row_index}",
        )
        doc = mapped.normalized_document

        if args.require_abstract and not normalize_text(doc.abstract):
            stats["filtered_missing_abstract"] += 1
            continue

        if args.min_year is not None and (doc.year is None or doc.year < args.min_year):
            stats["filtered_min_year"] += 1
            continue

        if args.max_year is not None and (doc.year is None or doc.year > args.max_year):
            stats["filtered_max_year"] += 1
            continue

        if doc.doc_id in seen_doc_ids:
            stats["dedup_skipped"] += 1
            continue
        seen_doc_ids.add(doc.doc_id)

        normalized_docs.append(doc)

        if not args.skip_raw:
            raw_rows.append(mapped.raw_document.model_dump(mode="json"))

        stats["selected"] += 1

        for category in mapped.categories:
            category_counter[category] += 1

        if args.report_every > 0 and stats["rows_seen"] % args.report_every == 0:
            print(
                f"[INFO] rows_seen={stats['rows_seen']} "
                f"selected={stats['selected']} "
                f"filtered_category={stats.get('filtered_category', 0)} "
                f"filtered_missing_abstract={stats.get('filtered_missing_abstract', 0)} "
                f"filtered_min_year={stats.get('filtered_min_year', 0)} "
                f"filtered_max_year={stats.get('filtered_max_year', 0)} "
                f"dedup_skipped={stats.get('dedup_skipped', 0)}"
            )

        if args.limit is not None and stats["selected"] >= args.limit:
            break

    if not normalized_docs:
        raise RuntimeError("No documents selected from Kaggle snapshot after filters")

    deduped_docs = deduplicate_documents(normalized_docs)
    new_docs, updated_docs, unchanged_docs = split_new_vs_updated(deduped_docs, existing_hashes)

    local_index.bulk_upsert_documents(deduped_docs, run_ts=run_ts)
    local_index.save()

    if not args.skip_raw:
        raw_path = store.save_raw_documents(source="arxiv", run_ts=run_ts, rows=raw_rows)
    else:
        raw_path = None

    normalized_paths = store.save_normalized_bundle(
        source="arxiv",
        run_ts=run_ts,
        normalized_rows=[doc.model_dump(mode="json") for doc in deduped_docs],
        new_rows=[doc.model_dump(mode="json") for doc in new_docs],
        updated_rows=[doc.model_dump(mode="json") for doc in updated_docs],
        unchanged_rows=[doc.model_dump(mode="json") for doc in unchanged_docs],
    )

    manifest = {
        "run_ts": run_ts,
        "source": "arxiv",
        "mode": "kaggle_snapshot_import",
        "input_path": str(input_path).replace("\\", "/"),
        "resolved_format": resolved_format,
        "filters": {
            "wanted_categories": sorted(wanted_categories) if wanted_categories else None,
            "min_year": args.min_year,
            "max_year": args.max_year,
            "require_abstract": args.require_abstract,
            "limit": args.limit,
            "taxonomy_path": str(args.taxonomy_path),
            "categories_mode": (
                "explicit"
                if args.categories
                else ("core" if args.core_categories_only else args.categories_mode)
            ),
        },
        "stats": dict(stats),
        "normalized_count_after_dedup": len(deduped_docs),
        "new_count": len(new_docs),
        "updated_count": len(updated_docs),
        "unchanged_count": len(unchanged_docs),
        "state_path": str(state_path).replace("\\", "/"),
        "output_files": {
            key: str(value).replace("\\", "/")
            for key, value in normalized_paths.items()
        },
        "raw_file": str(raw_path).replace("\\", "/") if raw_path else None,
        "top_categories": category_counter.most_common(20),
    }

    store.save_manifest(source="arxiv", run_ts=run_ts, manifest=manifest)
    _write_json(reports_dir / "kaggle_arxiv_import_latest.json", manifest)
    _write_json(reports_dir / "history" / f"kaggle_arxiv_import_{run_ts}.json", manifest)

    print("[OK] Kaggle arXiv snapshot import finished")
    print(f"rows_seen:                 {stats['rows_seen']}")
    print(f"selected_before_dedup:     {stats['selected']}")
    print(f"normalized_after_dedup:    {len(deduped_docs)}")
    print(f"new/updated/unchanged:     {len(new_docs)}/{len(updated_docs)}/{len(unchanged_docs)}")
    print(f"normalized_all:            {normalized_paths['all']}")
    if raw_path:
        print(f"raw_file:                  {raw_path}")


if __name__ == "__main__":
    main()