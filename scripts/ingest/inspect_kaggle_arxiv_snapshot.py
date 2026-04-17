from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.ingest.kaggle_arxiv_snapshot_utils import (
    detect_snapshot_format,
    iter_snapshot_rows,
    normalize_text,
    parse_categories,
    parse_versions,
    summarize_rows,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect Kaggle arXiv bulk snapshot format and lightweight field coverage."
    )
    parser.add_argument("--input", required=True, help="Path to Kaggle arXiv snapshot (.json, .jsonl, .gz).")
    parser.add_argument("--format", default="auto", choices=["auto", "ndjson", "json_array"])
    parser.add_argument("--sample-rows", type=int, default=5000, help="How many rows to inspect for summary stats.")
    parser.add_argument("--show-samples", type=int, default=3, help="How many raw sample rows to print.")
    parser.add_argument("--report-json", default=None, help="Optional path to write JSON report.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    input_path = Path(args.input)

    format_info = detect_snapshot_format(input_path)
    resolved_format = format_info.format_name if args.format == "auto" else args.format

    samples: list[dict[str, Any]] = []
    projected_rows: list[dict[str, Any]] = []
    for idx, row in iter_snapshot_rows(input_path, format_name=resolved_format):
        projected_rows.append(row)
        if len(samples) < args.show_samples:
            versions = parse_versions(row.get("versions"))
            samples.append(
                {
                    "row_index": idx,
                    "id": normalize_text(row.get("id")),
                    "title": normalize_text(row.get("title")),
                    "doi": normalize_text(row.get("doi")),
                    "categories": parse_categories(row.get("categories")),
                    "version_count": len(versions),
                    "keys": sorted(list(row.keys()))[:30],
                }
            )
        if len(projected_rows) >= args.sample_rows:
            break

    summary = summarize_rows(projected_rows)
    report = {
        "input_path": str(input_path),
        "compression": format_info.compression,
        "detected_format": format_info.format_name,
        "resolved_format": resolved_format,
        "sample_bytes_first_non_ws": format_info.first_non_ws,
        "sample_line_count": format_info.sample_line_count,
        "summary": summary,
        "samples": samples,
    }

    if args.report_json:
        out_path = Path(args.report_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[OK] Kaggle arXiv snapshot inspection finished")
    print(f"input_path:       {input_path}")
    print(f"compression:      {format_info.compression}")
    print(f"detected_format:  {format_info.format_name}")
    print(f"resolved_format:  {resolved_format}")
    print(f"rows_inspected:   {report['summary']['total_rows_seen']}")
    print(f"abstract_coverage:{report['summary']['abstract_coverage']}")
    print(f"doi_coverage:     {report['summary']['doi_coverage']}")
    print(f"top_categories:   {report['summary']['top_categories'][:10]}")
    print(f"top_years:        {report['summary']['top_years'][:10]}")
    print("samples:")
    for sample in samples:
        print(json.dumps(sample, ensure_ascii=False))


if __name__ == "__main__":
    main()
