from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.ingest.kaggle_arxiv_snapshot_utils import load_arxiv_taxonomy_categories

DEFAULT_INPUT_DIR = Path("data/normalized/arxiv")
DEFAULT_OUTPUT_DIR = Path("data/analytics/working")
DEFAULT_REPORTS_DIR = Path("artifacts/reports")
DEFAULT_TAXONOMY_PATH = "configs/taxonomy.yaml"


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def find_latest_primary_jsonl(source_dir: Path) -> Path:
    candidates = sorted(source_dir.glob("documents.*.jsonl"))
    pattern = re.compile(r"^documents\.\d{8}T\d{6}Z\.jsonl$")
    primary = [p for p in candidates if pattern.match(p.name)]
    if primary:
        return primary[-1]
    if candidates:
        return candidates[-1]
    raise FileNotFoundError(f"No normalized arXiv JSONL found in: {source_dir}")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def matches_categories(row: dict[str, Any], wanted: set[str]) -> bool:
    categories = set(row.get("categories") or [])
    primary = row.get("primary_category")
    if primary:
        categories.add(primary)
    tags = set(row.get("tags") or [])
    return bool((categories | tags) & wanted)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a medium-scale arXiv working slice from normalized arXiv JSONL."
    )
    parser.add_argument("--input", default=None, help="Explicit normalized arXiv JSONL path.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--min-year", type=int, default=None)
    parser.add_argument("--max-year", type=int, default=None)
    parser.add_argument("--require-abstract", action="store_true")
    parser.add_argument("--require-english", action="store_true")
    parser.add_argument("--exclude-withdrawn", action="store_true")
    parser.add_argument(
        "--sort-by",
        choices=["year_desc", "year_asc", "input_order"],
        default="year_desc",
    )
    parser.add_argument(
        "--taxonomy-path",
        default=DEFAULT_TAXONOMY_PATH,
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
    return parser


def main() -> None:
    args = build_parser().parse_args()

    input_path = Path(args.input) if args.input else find_latest_primary_jsonl(Path(args.input_dir))
    output_dir = Path(args.output_dir)
    reports_dir = Path(args.reports_dir)

    if args.categories:
        wanted_categories = {c.strip() for c in args.categories if c and c.strip()}
        categories_mode = "explicit"
    else:
        wanted_categories = set(
            load_arxiv_taxonomy_categories(
                args.taxonomy_path,
                mode=args.categories_mode,
            )
        )
        categories_mode = args.categories_mode

    rows_out: list[dict[str, Any]] = []
    stats = Counter()
    category_counter: Counter[str] = Counter()
    year_counter: Counter[int] = Counter()

    for row in load_jsonl(input_path):
        stats["rows_seen"] += 1

        if wanted_categories and not matches_categories(row, wanted_categories):
            stats["filtered_category"] += 1
            continue

        year = row.get("year")
        if args.min_year is not None and (year is None or year < args.min_year):
            stats["filtered_min_year"] += 1
            continue

        if args.max_year is not None and (year is None or year > args.max_year):
            stats["filtered_max_year"] += 1
            continue

        if args.require_abstract and not row.get("abstract"):
            stats["filtered_missing_abstract"] += 1
            continue

        if args.require_english and row.get("language") not in {None, "en"}:
            stats["filtered_language"] += 1
            continue

        if args.exclude_withdrawn and row.get("is_withdrawn"):
            stats["filtered_withdrawn"] += 1
            continue

        rows_out.append(row)
        stats["selected"] += 1

        row_categories = set(row.get("categories") or [])
        primary = row.get("primary_category")
        if primary:
            row_categories.add(primary)

        for category in row_categories:
            if category in wanted_categories:
                category_counter[category] += 1

        if year is not None:
            year_counter[int(year)] += 1

    if args.sort_by == "year_desc":
        rows_out.sort(
            key=lambda r: (
                r.get("year") is not None,
                r.get("year") if r.get("year") is not None else -9999,
            ),
            reverse=True,
        )
    elif args.sort_by == "year_asc":
        rows_out.sort(
            key=lambda r: (
                r.get("year") is None,
                r.get("year") if r.get("year") is not None else 9999,
            ),
        )

    if args.limit is not None:
        rows_out = rows_out[: args.limit]

    if not rows_out:
        raise RuntimeError("Working slice is empty after filters")

    run_ts = utc_now_ts()
    out_path = output_dir / f"arxiv_working_slice.{run_ts}.jsonl"
    latest_path = output_dir / "arxiv_working_slice.latest.jsonl"

    write_jsonl(out_path, rows_out)
    write_jsonl(latest_path, rows_out)

    report = {
        "run_ts": run_ts,
        "input_path": str(input_path).replace("\\", "/"),
        "output_path": str(out_path).replace("\\", "/"),
        "latest_path": str(latest_path).replace("\\", "/"),
        "filters": {
            "categories": sorted(wanted_categories),
            "min_year": args.min_year,
            "max_year": args.max_year,
            "require_abstract": args.require_abstract,
            "require_english": args.require_english,
            "exclude_withdrawn": args.exclude_withdrawn,
            "limit": args.limit,
            "sort_by": args.sort_by,
            "taxonomy_path": str(args.taxonomy_path),
            "categories_mode": categories_mode,
        },
        "stats": dict(stats),
        "selected_count": len(rows_out),
        "doi_coverage": round(
            sum(1 for r in rows_out if r.get("doi")) / max(len(rows_out), 1),
            4,
        ),
        "abstract_coverage": round(
            sum(1 for r in rows_out if r.get("abstract")) / max(len(rows_out), 1),
            4,
        ),
        "top_categories": category_counter.most_common(20),
        "top_years": year_counter.most_common(20),
        "sample_ids": [row.get("arxiv_id") for row in rows_out[:10]],
    }

    write_json(reports_dir / "arxiv_working_slice_latest.json", report)
    write_json(reports_dir / "history" / f"arxiv_working_slice_{run_ts}.json", report)

    print("[OK] arXiv working slice built")
    print(f"input_path:        {input_path}")
    print(f"selected_count:    {len(rows_out)}")
    print(f"doi_coverage:      {report['doi_coverage']}")
    print(f"abstract_coverage: {report['abstract_coverage']}")
    print(f"output_path:       {out_path}")


if __name__ == "__main__":
    main()