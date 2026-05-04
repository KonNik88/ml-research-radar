from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
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


@dataclass
class SelectedCandidate:
    normalized_document: Any
    raw_document_payload: dict[str, Any] | None
    categories: list[str]
    row_index: int
    year: int | None


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
        "--selection-strategy",
        choices=["first", "balanced_by_year"],
        default="first",
        help=(
            "Selection strategy after filters. "
            "'first' preserves the historical streaming behavior. "
            "'balanced_by_year' scans the snapshot and selects approximately equal yearly quotas."
        ),
    )
    parser.add_argument(
        "--balanced-fill-order",
        choices=["newest", "oldest", "input_order"],
        default="newest",
        help=(
            "When --selection-strategy=balanced_by_year and some year has fewer rows than its quota, "
            "fill the remaining slots from overflow candidates using this order."
        ),
    )
    parser.add_argument(
        "--max-overflow-candidates",
        type=int,
        default=100000,
        help=(
            "Maximum number of overflow candidates retained for balanced_by_year deficit filling. "
            "Only used when a year exceeds its quota before final selection."
        ),
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


def _candidate_from_mapping(
    mapped: Any,
    *,
    row_index: int,
    skip_raw: bool,
) -> SelectedCandidate:
    doc = mapped.normalized_document
    raw_payload = None if skip_raw else mapped.raw_document.model_dump(mode="json")

    return SelectedCandidate(
        normalized_document=doc,
        raw_document_payload=raw_payload,
        categories=list(mapped.categories or []),
        row_index=row_index,
        year=doc.year,
    )


def _candidate_sort_key(candidate: SelectedCandidate) -> tuple[int, int]:
    year = int(candidate.year or 0)
    return (year, candidate.row_index)


def _compute_year_quotas(
    *,
    years: list[int],
    limit: int | None,
) -> dict[int, int]:
    if not years or limit is None:
        return {}

    base = limit // len(years)
    remainder = limit % len(years)

    quotas: dict[int, int] = {}
    for idx, year in enumerate(years):
        quotas[year] = base + (1 if idx < remainder else 0)

    return quotas


def _resolve_balance_years(args: argparse.Namespace) -> list[int]:
    if args.min_year is not None and args.max_year is not None:
        if args.max_year < args.min_year:
            raise ValueError("--max-year must be >= --min-year")
        return list(range(args.min_year, args.max_year + 1))

    if args.min_year is not None:
        return [args.min_year]

    if args.max_year is not None:
        return [args.max_year]

    raise ValueError(
        "--selection-strategy=balanced_by_year requires both --min-year and --max-year "
        "for deterministic yearly quotas."
    )


def _iter_filtered_candidates(
    *,
    args: argparse.Namespace,
    input_path: Path,
    resolved_format: str,
    wanted_categories: set[str] | None,
    seen_doc_ids: set[str],
    stats: Counter,
) -> Any:
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

        yield _candidate_from_mapping(
            mapped,
            row_index=row_index,
            skip_raw=args.skip_raw,
        )


def _collect_first_strategy(
    *,
    args: argparse.Namespace,
    input_path: Path,
    resolved_format: str,
    wanted_categories: set[str] | None,
    stats: Counter,
) -> list[SelectedCandidate]:
    selected: list[SelectedCandidate] = []
    seen_doc_ids: set[str] = set()

    for candidate in _iter_filtered_candidates(
        args=args,
        input_path=input_path,
        resolved_format=resolved_format,
        wanted_categories=wanted_categories,
        seen_doc_ids=seen_doc_ids,
        stats=stats,
    ):
        selected.append(candidate)
        stats["selected"] += 1

        if args.report_every > 0 and stats["rows_seen"] % args.report_every == 0:
            print_progress(stats, strategy=args.selection_strategy)

        if args.limit is not None and stats["selected"] >= args.limit:
            break

    return selected


def _collect_balanced_by_year_strategy(
    *,
    args: argparse.Namespace,
    input_path: Path,
    resolved_format: str,
    wanted_categories: set[str] | None,
    stats: Counter,
) -> list[SelectedCandidate]:
    if args.limit is None:
        raise ValueError("--selection-strategy=balanced_by_year requires --limit")

    years = _resolve_balance_years(args)
    quotas = _compute_year_quotas(years=years, limit=args.limit)

    selected_by_year: dict[int, list[SelectedCandidate]] = {year: [] for year in years}
    overflow: list[SelectedCandidate] = []
    seen_doc_ids: set[str] = set()

    candidate_year_counter: Counter[int] = Counter()
    selected_year_counter: Counter[int] = Counter()

    for candidate in _iter_filtered_candidates(
        args=args,
        input_path=input_path,
        resolved_format=resolved_format,
        wanted_categories=wanted_categories,
        seen_doc_ids=seen_doc_ids,
        stats=stats,
    ):
        year = candidate.year
        if year is None:
            stats["filtered_missing_year"] += 1
            continue

        candidate_year_counter[year] += 1
        stats["candidate_pool"] += 1

        quota = quotas.get(year, 0)
        bucket = selected_by_year.setdefault(year, [])

        if len(bucket) < quota:
            bucket.append(candidate)
            selected_year_counter[year] += 1
        else:
            if len(overflow) < max(0, args.max_overflow_candidates):
                overflow.append(candidate)
            else:
                stats["overflow_dropped"] += 1

        if args.report_every > 0 and stats["rows_seen"] % args.report_every == 0:
            stats["provisional_selected"] = sum(len(v) for v in selected_by_year.values())
            stats["overflow_candidates"] = len(overflow)
            print_progress(stats, strategy=args.selection_strategy)

    selected: list[SelectedCandidate] = []
    for year in years:
        selected.extend(selected_by_year.get(year, []))

    if len(selected) < args.limit and overflow:
        remaining = args.limit - len(selected)

        if args.balanced_fill_order == "newest":
            overflow_sorted = sorted(overflow, key=_candidate_sort_key, reverse=True)
        elif args.balanced_fill_order == "oldest":
            overflow_sorted = sorted(overflow, key=_candidate_sort_key)
        else:
            overflow_sorted = overflow

        fill = overflow_sorted[:remaining]
        selected.extend(fill)

        for candidate in fill:
            if candidate.year is not None:
                selected_year_counter[candidate.year] += 1

    if len(selected) > args.limit:
        selected = selected[: args.limit]

    stats["candidate_pool"] = sum(candidate_year_counter.values())
    stats["selected"] = len(selected)
    stats["overflow_candidates"] = len(overflow)
    stats["year_quota_count"] = len(quotas)

    # Counter with int keys is not ideal for JSON stability. Manifest converts this later.
    stats["_candidate_year_counter"] = candidate_year_counter
    stats["_selected_year_counter"] = selected_year_counter
    stats["_year_quotas"] = quotas

    return selected


def print_progress(stats: Counter, *, strategy: str) -> None:
    extra = ""
    if strategy == "balanced_by_year":
        extra = (
            f" candidate_pool={stats.get('candidate_pool', 0)} "
            f"provisional_selected={stats.get('provisional_selected', 0)} "
            f"overflow_candidates={stats.get('overflow_candidates', 0)}"
        )

    print(
        f"[INFO] rows_seen={stats['rows_seen']} "
        f"selected={stats.get('selected', 0)}"
        f"{extra} "
        f"filtered_category={stats.get('filtered_category', 0)} "
        f"filtered_missing_abstract={stats.get('filtered_missing_abstract', 0)} "
        f"filtered_min_year={stats.get('filtered_min_year', 0)} "
        f"filtered_max_year={stats.get('filtered_max_year', 0)} "
        f"dedup_skipped={stats.get('dedup_skipped', 0)}"
    )


def _counter_to_sorted_dict(counter: Counter[int] | dict[int, int]) -> dict[str, int]:
    return {str(k): int(v) for k, v in sorted(counter.items(), key=lambda kv: kv[0])}


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

    stats: Counter = Counter()

    if args.selection_strategy == "first":
        selected_candidates = _collect_first_strategy(
            args=args,
            input_path=input_path,
            resolved_format=resolved_format,
            wanted_categories=wanted_categories,
            stats=stats,
        )
    elif args.selection_strategy == "balanced_by_year":
        selected_candidates = _collect_balanced_by_year_strategy(
            args=args,
            input_path=input_path,
            resolved_format=resolved_format,
            wanted_categories=wanted_categories,
            stats=stats,
        )
    else:  # pragma: no cover - argparse choices should prevent this.
        raise ValueError(f"Unsupported selection strategy: {args.selection_strategy}")

    if not selected_candidates:
        raise RuntimeError("No documents selected from Kaggle snapshot after filters")

    normalized_docs = [candidate.normalized_document for candidate in selected_candidates]
    raw_rows = [
        candidate.raw_document_payload
        for candidate in selected_candidates
        if candidate.raw_document_payload is not None
    ]

    category_counter: Counter[str] = Counter()
    selected_year_counter: Counter[int] = Counter()
    for candidate in selected_candidates:
        selected_year_counter[candidate.year or 0] += 1
        for category in candidate.categories:
            category_counter[category] += 1

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

    candidate_year_counter = stats.pop("_candidate_year_counter", Counter())
    balanced_selected_year_counter = stats.pop("_selected_year_counter", Counter())
    year_quotas = stats.pop("_year_quotas", {})

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
            "selection_strategy": args.selection_strategy,
            "balanced_fill_order": args.balanced_fill_order,
            "max_overflow_candidates": args.max_overflow_candidates,
        },
        "stats": dict(stats),
        "year_quotas": _counter_to_sorted_dict(year_quotas),
        "candidate_year_counts": _counter_to_sorted_dict(candidate_year_counter),
        "balanced_selected_year_counts": _counter_to_sorted_dict(balanced_selected_year_counter),
        "selected_year_counts": _counter_to_sorted_dict(selected_year_counter),
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
    print(f"selection_strategy:        {args.selection_strategy}")
    print(f"selected_before_dedup:     {stats['selected']}")
    print(f"normalized_after_dedup:    {len(deduped_docs)}")
    print(f"new/updated/unchanged:     {len(new_docs)}/{len(updated_docs)}/{len(unchanged_docs)}")
    print(f"selected_year_counts:      {_counter_to_sorted_dict(selected_year_counter)}")
    print(f"normalized_all:            {normalized_paths['all']}")
    if raw_path:
        print(f"raw_file:                  {raw_path}")


if __name__ == "__main__":
    main()
