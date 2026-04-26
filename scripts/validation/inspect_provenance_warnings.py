from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_REPORT_PATH = Path("artifacts/reports/validation/canonical_provenance_consistency_latest.json")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def index_by_canonical_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        cid = row.get("canonical_id")
        if cid:
            out[str(cid)] = row
    return out


def extract_warning_items(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """
    Tries to be tolerant to report structure differences.
    Expected useful shapes:
      - report["issues_by_type"][category] = [...]
      - report["issues"][category] = [...]
      - report["details"][category] = [...]
      - fallback: empty
    """
    candidates = [
        report.get("issues_by_type"),
        report.get("issues"),
        report.get("details"),
    ]

    for obj in candidates:
        if isinstance(obj, dict):
            normalized: dict[str, list[dict[str, Any]]] = {}
            for key, value in obj.items():
                if isinstance(value, list):
                    normalized[str(key)] = [
                        item for item in value if isinstance(item, dict)
                    ]
            if normalized:
                return normalized

    return {}


def compact_sources(row: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for src in row.get("sources") or []:
        if not isinstance(src, dict):
            continue
        out.append({
            "source": src.get("source"),
            "source_id": src.get("source_id"),
            "source_record_id": src.get("source_record_id"),
            "source_record_url": src.get("source_record_url"),
            "canonical_url": src.get("canonical_url"),
        })
    return out


def duplicate_source_families(row: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for src in row.get("sources") or []:
        if not isinstance(src, dict):
            continue
        family = src.get("source")
        if not family:
            continue
        family = str(family)
        counts[family] = counts.get(family, 0) + 1
    return {k: v for k, v in counts.items() if v > 1}


def build_entry(
    category: str,
    issue_item: dict[str, Any],
    canonical_row: dict[str, Any] | None,
) -> dict[str, Any]:
    cid = (
        issue_item.get("canonical_id")
        or issue_item.get("id")
        or issue_item.get("doc_id")
    )
    cid = str(cid) if cid is not None else None

    if canonical_row is None:
        return {
            "category": category,
            "canonical_id": cid,
            "missing_in_canonical": True,
            "issue_item": issue_item,
        }

    return {
        "category": category,
        "canonical_id": cid,
        "title": canonical_row.get("title"),
        "doi": canonical_row.get("doi"),
        "arxiv_id": canonical_row.get("arxiv_id"),
        "openalex_id": canonical_row.get("openalex_id"),
        "source_count": canonical_row.get("source_count"),
        "unique_source_count": canonical_row.get("unique_source_count"),
        "doc_ids_count": len(canonical_row.get("doc_ids") or []),
        "doc_ids": canonical_row.get("doc_ids") or [],
        "source_ids": canonical_row.get("source_ids") or {},
        "external_ids_keys": sorted((canonical_row.get("external_ids") or {}).keys()),
        "sources_compact": compact_sources(canonical_row),
        "duplicate_source_families": duplicate_source_families(canonical_row),
        "issue_item": issue_item,
    }


def print_entry(entry: dict[str, Any]) -> None:
    print("=" * 120)
    print(f"category: {entry.get('category')}")
    print(f"canonical_id: {entry.get('canonical_id')}")

    if entry.get("missing_in_canonical"):
        print("missing_in_canonical: True")
        print("issue_item:")
        print(json.dumps(entry.get("issue_item"), ensure_ascii=False, indent=2))
        return

    print(f"title: {entry.get('title')}")
    print(f"doi: {entry.get('doi')}")
    print(f"arxiv_id: {entry.get('arxiv_id')}")
    print(f"openalex_id: {entry.get('openalex_id')}")
    print(f"source_count: {entry.get('source_count')}")
    print(f"unique_source_count: {entry.get('unique_source_count')}")
    print(f"doc_ids_count: {entry.get('doc_ids_count')}")
    print(f"doc_ids: {entry.get('doc_ids')}")
    print(f"source_ids: {entry.get('source_ids')}")
    print(f"external_ids_keys: {entry.get('external_ids_keys')}")
    print(f"duplicate_source_families: {entry.get('duplicate_source_families')}")
    print("sources_compact:")
    print(json.dumps(entry.get("sources_compact"), ensure_ascii=False, indent=2))
    print("issue_item:")
    print(json.dumps(entry.get("issue_item"), ensure_ascii=False, indent=2))


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect canonical provenance warnings in a more human-readable way."
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Path to canonical_provenance_consistency report JSON.",
    )
    parser.add_argument(
        "--canonical-path",
        type=Path,
        default=DEFAULT_CANONICAL_PATH,
        help="Path to canonical JSONL file.",
    )
    parser.add_argument(
        "--category",
        action="append",
        default=[],
        help="Warning/info category to inspect. Can be passed multiple times.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="How many items per category to print.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write inspection JSON.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    report = load_json(args.report_path)
    canonical_rows = load_jsonl(args.canonical_path)
    canonical_by_id = index_by_canonical_id(canonical_rows)

    issues_by_type = extract_warning_items(report)
    available_categories = sorted(issues_by_type.keys())

    if not available_categories:
        print("[WARN] No structured issue details found in report.")
        print(f"[INFO] report_path={args.report_path}")
        return

    requested_categories = args.category or available_categories

    result: dict[str, Any] = {
        "report_path": str(args.report_path).replace("\\", "/"),
        "canonical_path": str(args.canonical_path).replace("\\", "/"),
        "available_categories": available_categories,
        "requested_categories": requested_categories,
        "inspected": {},
    }

    for category in requested_categories:
        items = issues_by_type.get(category)
        if items is None:
            print(f"[WARN] category not found in report: {category}")
            continue

        selected = items[: args.limit]
        entries: list[dict[str, Any]] = []

        print("\n" + "#" * 120)
        print(f"category={category} | total_items={len(items)} | showing={len(selected)}")

        for issue_item in selected:
            cid = (
                issue_item.get("canonical_id")
                or issue_item.get("id")
                or issue_item.get("doc_id")
            )
            cid = str(cid) if cid is not None else None
            canonical_row = canonical_by_id.get(cid) if cid else None
            entry = build_entry(category, issue_item, canonical_row)
            entries.append(entry)
            print_entry(entry)

        result["inspected"][category] = {
            "total_items": len(items),
            "shown_items": len(entries),
            "entries": entries,
        }

    if args.output_json is not None:
        dump_json(args.output_json, result)
        print(f"\n[OK] inspection JSON written: {args.output_json}")


if __name__ == "__main__":
    main()