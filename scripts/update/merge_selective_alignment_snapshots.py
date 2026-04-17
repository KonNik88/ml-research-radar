from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def dump_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_dt(value: Any) -> tuple[int, str]:
    if not value:
        return (0, "")
    try:
        s = str(value)
        return (1, s)
    except Exception:
        return (0, "")


def score_row(row: dict[str, Any]) -> tuple[int, tuple[int, str], tuple[int, str]]:
    """
    Higher is better.
    1) metadata_completeness_score
    2) updated_at / updated_source_at / ingested_at freshness
    3) content richness heuristic
    """
    completeness = row.get("metadata_completeness_score")
    try:
        completeness_score = int(float(completeness or 0) * 10000)
    except Exception:
        completeness_score = 0

    freshness = parse_dt(
        row.get("updated_at")
        or row.get("updated_source_at")
        or row.get("ingested_at")
        or row.get("created_at")
    )

    richness_fields = [
        "abstract",
        "doi",
        "arxiv_id",
        "openalex_id",
        "semantic_scholar_id",
        "venue",
        "journal",
        "conference",
        "publisher",
        "publication_type",
        "pdf_url",
        "license",
    ]
    richness = 0
    for field in richness_fields:
        value = row.get(field)
        if value not in (None, "", [], {}):
            richness += 1

    return (completeness_score, freshness, (richness, str(row.get("doc_id", ""))))


def choose_better(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    return incoming if score_row(incoming) > score_row(existing) else existing


def merge_rows(
    base_rows: list[dict[str, Any]],
    incremental_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    merged: dict[str, dict[str, Any]] = {}

    stats = {
        "base_rows": len(base_rows),
        "incremental_rows": len(incremental_rows),
        "base_loaded": 0,
        "incremental_inserted": 0,
        "incremental_replaced": 0,
        "incremental_skipped": 0,
        "missing_doc_id_rows": 0,
    }

    for row in base_rows:
        doc_id = row.get("doc_id")
        if not doc_id:
            stats["missing_doc_id_rows"] += 1
            continue
        merged[doc_id] = row
        stats["base_loaded"] += 1

    for row in incremental_rows:
        doc_id = row.get("doc_id")
        if not doc_id:
            stats["missing_doc_id_rows"] += 1
            continue

        if doc_id not in merged:
            merged[doc_id] = row
            stats["incremental_inserted"] += 1
            continue

        better = choose_better(merged[doc_id], row)
        if better is row:
            merged[doc_id] = row
            stats["incremental_replaced"] += 1
        else:
            stats["incremental_skipped"] += 1

    merged_rows = sorted(
        merged.values(),
        key=lambda r: (
            str(r.get("doi") or ""),
            str(r.get("arxiv_id") or ""),
            str(r.get("doc_id") or ""),
        ),
    )

    stats["merged_output_rows"] = len(merged_rows)
    return merged_rows, stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge selective alignment snapshot into a full alignment snapshot safely."
    )
    parser.add_argument("--source-name", required=True, help="Logical source name, e.g. openalex_alignment")
    parser.add_argument("--base", required=True, type=Path, help="Full/base normalized JSONL snapshot")
    parser.add_argument("--incremental", required=True, type=Path, help="Selective/incremental normalized JSONL snapshot")
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Output directory where merged normalized JSONL will be written",
    )
    parser.add_argument(
        "--report-dir",
        default=Path("artifacts/reports/update"),
        type=Path,
        help="Directory for merge reports",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    source_name = args.source_name
    base_path: Path = args.base
    incremental_path: Path = args.incremental
    output_dir: Path = args.output_dir
    report_dir: Path = args.report_dir

    if not base_path.exists():
        raise FileNotFoundError(f"Base snapshot not found: {base_path}")
    if not incremental_path.exists():
        raise FileNotFoundError(f"Incremental snapshot not found: {incremental_path}")

    base_rows = load_jsonl(base_path)
    incremental_rows = load_jsonl(incremental_path)
    merged_rows, stats = merge_rows(base_rows, incremental_rows)

    output_path = output_dir / f"documents.{run_ts}.jsonl"
    dump_jsonl(output_path, merged_rows)

    report = {
        "report_name": "merge_selective_alignment_snapshots",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "source_name": source_name,
        "inputs": {
            "base_snapshot": str(base_path).replace("\\", "/"),
            "incremental_snapshot": str(incremental_path).replace("\\", "/"),
        },
        "output": {
            "merged_snapshot": str(output_path).replace("\\", "/"),
        },
        "stats": stats,
    }

    latest_json = report_dir / f"merge_{source_name}_latest.json"
    hist_json = report_dir / "history" / f"merge_{source_name}_{run_ts}.json"

    dump_json(latest_json, report)
    dump_json(hist_json, report)

    print(f"[OK] source_name={source_name}")
    print(f"[OK] base_rows={stats['base_rows']}")
    print(f"[OK] incremental_rows={stats['incremental_rows']}")
    print(f"[OK] incremental_inserted={stats['incremental_inserted']}")
    print(f"[OK] incremental_replaced={stats['incremental_replaced']}")
    print(f"[OK] incremental_skipped={stats['incremental_skipped']}")
    print(f"[OK] merged_output_rows={stats['merged_output_rows']}")
    print(f"[OK] merged_snapshot={output_path}")
    print(f"[OK] latest_report={latest_json}")
    print(f"[OK] history_report={hist_json}")


if __name__ == "__main__":
    main()