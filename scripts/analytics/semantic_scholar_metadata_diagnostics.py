from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_NORMALIZED_ROOT = Path("data/normalized")
DEFAULT_REPORTS_DIR = Path("artifacts/reports")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ts_slug(dt: datetime | None = None) -> str:
    dt = dt or utc_now()
    return dt.strftime("%Y%m%dT%H%M%SZ")


def to_jsonable(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat().replace("+00:00", "Z")
    if isinstance(obj, Counter):
        return dict(obj)
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_jsonable(x) for x in obj]
    return obj


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(to_jsonable(payload), f, ensure_ascii=False, indent=2)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def find_latest_normalized_file(source_dir: Path) -> Path:
    candidates = sorted(source_dir.glob("documents*.jsonl"))
    if not candidates:
        raise FileNotFoundError(f"No normalized JSONL found in: {source_dir}")

    pattern = re.compile(r"^documents\.\d{8}T\d{6}Z\.jsonl$")
    primary_snapshots = [p for p in candidates if pattern.match(p.name)]
    if primary_snapshots:
        return sorted(primary_snapshots)[-1]

    return candidates[-1]


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def field_coverage(rows: list[dict[str, Any]], field_name: str) -> dict[str, Any]:
    total = len(rows)
    present_count = sum(1 for row in rows if is_present(row.get(field_name)))
    coverage = (present_count / total) if total else 0.0
    return {
        "present_count": present_count,
        "coverage": round(coverage, 4),
    }


def top_scalar_values(rows: list[dict[str, Any]], field_name: str, limit: int = 10) -> list[list[Any]]:
    counter = Counter()
    for row in rows:
        value = row.get(field_name)
        if isinstance(value, str) and value.strip():
            counter[value.strip()] += 1
    return [[k, v] for k, v in counter.most_common(limit)]


def top_list_values(rows: list[dict[str, Any]], field_name: str, limit: int = 15) -> list[list[Any]]:
    counter = Counter()
    for row in rows:
        values = row.get(field_name)
        if isinstance(values, list):
            for value in values:
                if isinstance(value, str) and value.strip():
                    counter[value.strip()] += 1
    return [[k, v] for k, v in counter.most_common(limit)]


def build_markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Semantic Scholar metadata diagnostics",
        "",
        f"- generated_at: `{summary['generated_at']}`",
        f"- input_file: `{summary['input_file']}`",
        f"- total_docs: **{summary['total_docs']}**",
        "",
        "## Field coverage",
        "",
    ]

    for field_name, payload in summary["field_coverage"].items():
        lines.append(
            f"- `{field_name}`: {payload['present_count']} / {summary['total_docs']} "
            f"({payload['coverage']:.4f})"
        )

    lines.extend(
        [
            "",
            "## Publication types",
            "",
        ]
    )
    for value, count in summary["publication_type_distribution"]:
        lines.append(f"- `{value}`: {count}")

    lines.extend(
        [
            "",
            "## Top venues",
            "",
        ]
    )
    for value, count in summary["top_venues"]:
        lines.append(f"- `{value}`: {count}")

    lines.extend(
        [
            "",
            "## Top journals",
            "",
        ]
    )
    for value, count in summary["top_journals"]:
        lines.append(f"- `{value}`: {count}")

    lines.extend(
        [
            "",
            "## Sample identifiers",
            "",
        ]
    )
    for row in summary["sample_records"]:
        lines.append(
            f"- title: `{row.get('title')}` | doi: `{row.get('doi')}` | "
            f"semantic_scholar_id: `{row.get('semantic_scholar_id')}` | "
            f"arxiv_id: `{row.get('arxiv_id')}`"
        )

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run metadata diagnostics on latest normalized semantic_scholar_alignment file."
    )
    parser.add_argument(
        "--input",
        help="Explicit normalized semantic_scholar_alignment JSONL path.",
    )
    parser.add_argument(
        "--normalized-root",
        default=str(DEFAULT_NORMALIZED_ROOT),
        help="Root directory containing normalized source subdirectories.",
    )
    parser.add_argument(
        "--reports-dir",
        default=str(DEFAULT_REPORTS_DIR),
        help="Directory for JSON/Markdown reports.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_ts = ts_slug()

    normalized_root = Path(args.normalized_root)
    reports_dir = Path(args.reports_dir)

    input_path = (
        Path(args.input)
        if args.input
        else find_latest_normalized_file(normalized_root / "semantic_scholar_alignment")
    )

    rows = load_jsonl(input_path)
    total_docs = len(rows)

    if total_docs == 0:
        raise RuntimeError(f"No rows found in file: {input_path}")

    field_names = [
        "doi",
        "arxiv_id",
        "semantic_scholar_id",
        "title",
        "abstract",
        "authors",
        "year",
        "publication_date",
        "venue",
        "journal",
        "publication_type",
        "cited_by_count",
        "references_count",
        "landing_page_url",
        "pdf_url",
        "open_access",
        "is_open_access",
    ]

    coverage = {field: field_coverage(rows, field) for field in field_names}

    publication_type_distribution = Counter(
        row.get("publication_type")
        for row in rows
        if is_present(row.get("publication_type"))
    )

    top_venues = top_scalar_values(rows, "venue", limit=10)
    top_journals = top_scalar_values(rows, "journal", limit=10)
    top_authors = top_list_values(rows, "authors", limit=10)

    citation_graph_available = sum(
        1 for row in rows if bool(row.get("citation_graph_available"))
    )
    preprint_count = sum(
        1 for row in rows if bool(row.get("is_preprint"))
    )
    review_count = sum(
        1 for row in rows if bool(row.get("is_review"))
    )
    survey_count = sum(
        1 for row in rows if bool(row.get("is_survey"))
    )

    sample_records = []
    for row in rows[:10]:
        sample_records.append(
            {
                "title": row.get("title"),
                "doi": row.get("doi"),
                "semantic_scholar_id": row.get("semantic_scholar_id"),
                "arxiv_id": row.get("arxiv_id"),
            }
        )

    summary = {
        "generated_at": run_ts,
        "input_file": str(input_path).replace("/", "\\"),
        "total_docs": total_docs,
        "field_coverage": coverage,
        "publication_type_distribution": [
            [k, v] for k, v in publication_type_distribution.most_common(10)
        ],
        "top_venues": top_venues,
        "top_journals": top_journals,
        "top_authors": top_authors,
        "citation_graph_available_count": citation_graph_available,
        "citation_graph_available_rate": round(citation_graph_available / total_docs, 4),
        "preprint_count": preprint_count,
        "preprint_rate": round(preprint_count / total_docs, 4),
        "review_count": review_count,
        "review_rate": round(review_count / total_docs, 4),
        "survey_count": survey_count,
        "survey_rate": round(survey_count / total_docs, 4),
        "sample_records": sample_records,
    }

    json_report_path = reports_dir / "semantic_scholar_metadata_diagnostics_latest.json"
    md_report_path = reports_dir / "semantic_scholar_metadata_diagnostics_latest.md"
    hist_json_path = reports_dir / "history" / f"semantic_scholar_metadata_diagnostics_{run_ts}.json"
    hist_md_path = reports_dir / "history" / f"semantic_scholar_metadata_diagnostics_{run_ts}.md"

    write_json(json_report_path, summary)
    write_json(hist_json_path, summary)

    md_report = build_markdown_report(summary)
    write_text(md_report_path, md_report)
    write_text(hist_md_path, md_report)

    print(f"[OK] loaded docs: {total_docs}")
    print(f"[OK] input: {input_path}")
    print(f"[OK] JSON report: {json_report_path}")
    print(f"[OK] Markdown report: {md_report_path}")
    print(f"[OK] snapshot JSON: {hist_json_path}")
    print(f"[OK] snapshot MD: {hist_md_path}")


if __name__ == "__main__":
    main()