from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            docs.append(json.loads(line))
    return docs


def is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def is_non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def valid_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    value = value.strip().lower()
    return value.startswith("http://") or value.startswith("https://")


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: str  # scalar | list | bool | numeric


FIELD_SPECS: list[FieldSpec] = [
    FieldSpec("doi", "scalar"),
    FieldSpec("arxiv_id", "scalar"),
    FieldSpec("openalex_id", "scalar"),
    FieldSpec("landing_page_url", "scalar"),
    FieldSpec("pdf_url", "scalar"),
    FieldSpec("repo_url", "scalar"),
    FieldSpec("license", "scalar"),
    FieldSpec("open_access", "bool"),
    FieldSpec("is_open_access", "bool"),
    FieldSpec("primary_category", "scalar"),
    FieldSpec("categories", "list"),
    FieldSpec("concepts", "list"),
    FieldSpec("keywords", "list"),
    FieldSpec("tags", "list"),
    FieldSpec("venue", "scalar"),
    FieldSpec("journal", "scalar"),
    FieldSpec("conference", "scalar"),
    FieldSpec("publisher", "scalar"),
    FieldSpec("publication_type", "scalar"),
    FieldSpec("language", "scalar"),
    FieldSpec("comment", "scalar"),
    FieldSpec("journal_ref", "scalar"),
    FieldSpec("cited_by_count", "numeric"),
    FieldSpec("references_count", "numeric"),
    FieldSpec("referenced_ids", "list"),
    FieldSpec("referenced_dois", "list"),
    FieldSpec("referenced_arxiv_ids", "list"),
    FieldSpec("citation_graph_available", "bool"),
    FieldSpec("has_code_link", "bool"),
    FieldSpec("code_links", "list"),
    FieldSpec("dataset_links", "list"),
    FieldSpec("model_links", "list"),
    FieldSpec("has_dataset_link", "bool"),
    FieldSpec("has_model_link", "bool"),
    FieldSpec("is_preprint", "bool"),
    FieldSpec("is_review", "bool"),
    FieldSpec("is_survey", "bool"),
    FieldSpec("is_withdrawn", "bool"),
    FieldSpec("metadata_completeness_score", "numeric"),
    FieldSpec("source_count", "numeric"),
    FieldSpec("unique_source_count", "numeric"),
]


def compute_field_coverage(docs: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(docs)
    fields: dict[str, Any] = {}

    for spec in FIELD_SPECS:
        present = 0
        true_count = 0
        numeric_non_null = 0
        non_zero_numeric = 0
        avg_list_len_values: list[int] = []
        top_values = Counter()

        for doc in docs:
            value = doc.get(spec.name)

            if spec.kind == "scalar":
                if is_non_empty(value):
                    present += 1
                    if isinstance(value, str):
                        top_values[value.strip()] += 1
                    else:
                        top_values[str(value)] += 1

            elif spec.kind == "list":
                if is_non_empty_list(value):
                    present += 1
                    avg_list_len_values.append(len(value))
                    for item in value:
                        if isinstance(item, str) and item.strip():
                            top_values[item.strip()] += 1

            elif spec.kind == "bool":
                if value is not None:
                    present += 1
                if value is True:
                    true_count += 1

            elif spec.kind == "numeric":
                num = safe_float(value)
                if num is not None:
                    present += 1
                    numeric_non_null += 1
                    if num != 0:
                        non_zero_numeric += 1

        entry: dict[str, Any] = {
            "kind": spec.kind,
            "present_count": present,
            "coverage": round(present / total, 4) if total else 0.0,
        }

        if spec.kind == "bool":
            entry["true_count"] = true_count
            entry["true_rate"] = round(true_count / total, 4) if total else 0.0

        if spec.kind == "numeric":
            entry["non_zero_count"] = non_zero_numeric
            entry["non_zero_rate"] = round(non_zero_numeric / total, 4) if total else 0.0

        if spec.kind == "list":
            entry["avg_list_len"] = round(sum(avg_list_len_values) / len(avg_list_len_values), 3) if avg_list_len_values else 0.0

        if top_values:
            entry["top_values"] = top_values.most_common(15)

        fields[spec.name] = entry

    return fields


def compute_source_distribution(docs: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter()

    for doc in docs:
        sources = doc.get("sources") or []

        if isinstance(sources, list) and sources:
            for src in sources:
                if isinstance(src, str):
                    value = src.strip()
                    if value:
                        counter[value] += 1
                elif isinstance(src, dict):
                    value = (src.get("source") or src.get("raw_source_name") or "").strip()
                    if value:
                        counter[value] += 1

        else:
            src = doc.get("raw_source_name")
            if isinstance(src, str) and src.strip():
                counter[src.strip()] += 1

    return dict(counter)


def compute_merge_stats(docs: list[dict[str, Any]]) -> dict[str, Any]:
    multi_source_docs = 0
    source_count_gt1 = 0

    for doc in docs:
        unique_source_count = safe_int(doc.get("unique_source_count")) or 0
        source_count = safe_int(doc.get("source_count")) or 0

        if unique_source_count > 1:
            multi_source_docs += 1
        if source_count > 1:
            source_count_gt1 += 1

    return {
        "multi_source_docs": multi_source_docs,
        "source_count_gt1_docs": source_count_gt1,
    }


def collect_unique_values(docs: list[dict[str, Any]], field: str) -> list[str]:
    values = set()
    for doc in docs:
        value = doc.get(field)
        if isinstance(value, str) and value.strip():
            values.add(value.strip())
    return sorted(values)


def compute_quality_anomalies(docs: list[dict[str, Any]]) -> dict[str, Any]:
    current_year = datetime.now().year
    future_year_docs = []
    missing_title_ids = []
    empty_authors_ids = []
    invalid_url_fields = {
        "landing_page_url": [],
        "pdf_url": [],
        "repo_url": [],
    }
    negative_numeric_fields = {
        "cited_by_count": [],
        "references_count": [],
    }

    for doc in docs:
        cid = doc.get("canonical_id") or doc.get("id") or "<unknown>"

        year = safe_int(doc.get("year"))
        if year is not None and year > current_year + 1:
            future_year_docs.append({"canonical_id": cid, "year": year, "title": doc.get("title")})

        title = doc.get("title")
        if not (isinstance(title, str) and title.strip()):
            missing_title_ids.append(cid)

        authors = doc.get("authors")
        if not isinstance(authors, list) or len(authors) == 0:
            empty_authors_ids.append(cid)

        for field in invalid_url_fields:
            value = doc.get(field)
            if is_non_empty(value) and not valid_url(value):
                invalid_url_fields[field].append({"canonical_id": cid, "value": value})

        for field in negative_numeric_fields:
            value = safe_float(doc.get(field))
            if value is not None and value < 0:
                negative_numeric_fields[field].append({"canonical_id": cid, "value": value})

    return {
        "future_year_docs": future_year_docs,
        "future_year_count": len(future_year_docs),
        "missing_title_count": len(missing_title_ids),
        "missing_title_ids": missing_title_ids[:20],
        "empty_authors_count": len(empty_authors_ids),
        "empty_authors_ids": empty_authors_ids[:20],
        "invalid_url_fields": invalid_url_fields,
        "negative_numeric_fields": negative_numeric_fields,
    }


def build_report(docs: list[dict[str, Any]], input_path: str) -> dict[str, Any]:
    source_distribution = compute_source_distribution(docs)
    merge_stats = compute_merge_stats(docs)

    report = {
        "generated_at": utc_now_ts(),
        "input_path": input_path,
        "total_docs": len(docs),
        "source_distribution": source_distribution,
        "field_coverage": compute_field_coverage(docs),
        "merge_stats": merge_stats,
        "quality_anomalies": compute_quality_anomalies(docs),
        "corpus_summary": {
            "unique_primary_categories": len(collect_unique_values(docs, "primary_category")),
            "unique_venues": len(collect_unique_values(docs, "venue")),
            "unique_publication_types": len(collect_unique_values(docs, "publication_type")),
            "unique_publishers": len(collect_unique_values(docs, "publisher")),
        },
    }
    return report


def markdown_table(rows: Iterable[tuple[str, str, str]]) -> str:
    lines = ["| Field | Present | Coverage |", "|---|---:|---:|"]
    for field, present, coverage in rows:
        lines.append(f"| {field} | {present} | {coverage} |")
    return "\n".join(lines)


def build_markdown(report: dict[str, Any]) -> str:
    total_docs = report["total_docs"]
    lines: list[str] = []
    lines.append("# Corpus Audit Report")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at']}`")
    lines.append(f"- Input path: `{report['input_path']}`")
    lines.append(f"- Total docs: **{total_docs}**")
    lines.append(f"- Source distribution: `{report['source_distribution']}`")
    lines.append(f"- Merge stats: `{report['merge_stats']}`")
    lines.append("")

    lines.append("## Coverage")
    lines.append("")
    rows = []
    for field, stats in report["field_coverage"].items():
        rows.append((field, str(stats["present_count"]), f"{stats['coverage']:.2%}"))
    rows.sort(key=lambda x: x[0])
    lines.append(markdown_table(rows))
    lines.append("")

    lines.append("## Corpus Summary")
    lines.append("")
    for k, v in report["corpus_summary"].items():
        lines.append(f"- {k}: **{v}**")
    lines.append("")

    anomalies = report["quality_anomalies"]
    lines.append("## Quality Anomalies")
    lines.append("")
    lines.append(f"- future_year_count: **{anomalies['future_year_count']}**")
    lines.append(f"- missing_title_count: **{anomalies['missing_title_count']}**")
    lines.append(f"- empty_authors_count: **{anomalies['empty_authors_count']}**")
    lines.append("")

    if anomalies["future_year_docs"]:
        lines.append("### Future-dated documents")
        lines.append("")
        lines.append("| Canonical ID | Year | Title |")
        lines.append("|---|---:|---|")
        for item in anomalies["future_year_docs"][:20]:
            lines.append(f"| {item['canonical_id']} | {item['year']} | {item.get('title', '')} |")
        lines.append("")

    return "\n".join(lines)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def save_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def save_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit canonical corpus coverage and quality.")
    parser.add_argument(
        "--input",
        default="data/analytics/reconciled/canonical_documents.jsonl",
        help="Path to canonical_documents.jsonl",
    )
    parser.add_argument(
        "--output-json",
        default="artifacts/reports/corpus_audit_latest.json",
        help="Path to latest JSON audit report",
    )
    parser.add_argument(
        "--output-md",
        default="artifacts/reports/corpus_audit_latest.md",
        help="Path to latest Markdown audit report",
    )
    parser.add_argument(
        "--snapshot-dir",
        default="artifacts/reports/history",
        help="Directory for timestamped snapshots",
    )
    parser.add_argument(
        "--no-snapshot",
        action="store_true",
        help="Do not save timestamped snapshot files",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_path = Path(args.input)
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    snapshot_dir = Path(args.snapshot_dir)

    docs = load_jsonl(input_path)
    report = build_report(docs, str(input_path))
    md = build_markdown(report)

    save_json(output_json, report)
    save_text(output_md, md)

    print(f"[OK] loaded docs: {len(docs)}")
    print(f"[OK] JSON report: {output_json}")
    print(f"[OK] Markdown report: {output_md}")
    print(f"[OK] merged docs: {report['merge_stats']['multi_source_docs']}")
    print(f"[OK] source distribution: {report['source_distribution']}")

    if not args.no_snapshot:
        ts = report["generated_at"]
        snap_json = snapshot_dir / f"corpus_audit_{ts}.json"
        snap_md = snapshot_dir / f"corpus_audit_{ts}.md"
        save_json(snap_json, report)
        save_text(snap_md, md)
        print(f"[OK] snapshot JSON: {snap_json}")
        print(f"[OK] snapshot MD: {snap_md}")


if __name__ == "__main__":
    main()