from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


FIELDS_TO_COMPARE = [
    "doi",
    "landing_page_url",
    "pdf_url",
    "repo_url",
    "license",
    "open_access",
    "is_open_access",
    "primary_category",
    "categories",
    "concepts",
    "keywords",
    "tags",
    "venue",
    "journal",
    "conference",
    "publisher",
    "publication_type",
    "language",
    "comment",
    "journal_ref",
    "cited_by_count",
    "references_count",
    "referenced_ids",
    "referenced_dois",
    "referenced_arxiv_ids",
    "citation_graph_available",
    "has_code_link",
    "code_links",
    "dataset_links",
    "model_links",
    "has_dataset_link",
    "has_model_link",
    "is_preprint",
    "is_review",
    "is_survey",
    "is_withdrawn",
]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_cov(report: dict[str, Any], field: str) -> float:
    return float(report.get("field_coverage", {}).get(field, {}).get("coverage", 0.0))


def get_true_rate(report: dict[str, Any], field: str) -> float | None:
    value = report.get("field_coverage", {}).get(field, {}).get("true_rate")
    return None if value is None else float(value)


def pct(x: float) -> str:
    return f"{x:.2%}"

def normalize_source_name_for_distribution(source_name: str) -> str:
    mapping = {
        "semantic_scholar_alignment": "semantic_scholar",
        "openalex_alignment": "openalex",
        "crossref_alignment": "crossref",
    }
    return mapping.get(source_name, source_name)


def build_rows(
    canonical: dict[str, Any],
    source_reports: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rows: dict[str, Any] = {}

    source_distribution = canonical.get("source_distribution", {})
    total_docs = int(canonical.get("total_docs", 0))

    source_doc_counts: dict[str, int] = {}
    for source_name in source_reports:
        dist_key = normalize_source_name_for_distribution(source_name)
        source_doc_counts[source_name] = int(source_distribution.get(dist_key, 0))

    for field in FIELDS_TO_COMPARE:
        canonical_cov = get_cov(canonical, field)

        weighted_source_cov = 0.0
        if total_docs > 0:
            weighted_source_cov = sum(
                get_cov(report, field) * source_doc_counts[source_name]
                for source_name, report in source_reports.items()
            ) / total_docs

        retention = canonical_cov / weighted_source_cov if weighted_source_cov > 0 else None

        row = {
            "canonical_coverage": canonical_cov,
            "weighted_source_coverage": round(weighted_source_cov, 6),
            "retention_rate": None if retention is None else round(retention, 6),
            "sources": {},
        }

        for source_name, report in source_reports.items():
            row["sources"][source_name] = {
                "coverage": get_cov(report, field),
            }

            true_rate = get_true_rate(report, field)
            if true_rate is not None:
                row["sources"][source_name]["true_rate"] = true_rate

        canon_true = get_true_rate(canonical, field)
        if canon_true is not None:
            row["canonical_true_rate"] = canon_true

        rows[field] = row

    return {
        "canonical_total_docs": total_docs,
        "source_doc_counts": source_doc_counts,
        "rows": rows,
    }


def build_markdown(report: dict[str, Any]) -> str:
    source_names = list(report["source_doc_counts"].keys())

    lines = []
    lines.append("# Source → Canonical Retention Report")
    lines.append("")
    lines.append(f"- Canonical total docs: **{report['canonical_total_docs']}**")
    for source_name, count in report["source_doc_counts"].items():
        lines.append(f"- {source_name} docs in canonical: **{count}**")
    lines.append("")

    header = "| Field | " + " | ".join(source_names) + " | Weighted source | Canonical | Retention |"
    sep = "|---|" + "|".join(["---:" for _ in source_names]) + "|---:|---:|---:|"
    lines.append(header)
    lines.append(sep)

    for field, row in sorted(report["rows"].items()):
        retention = "-" if row["retention_rate"] is None else pct(row["retention_rate"])
        source_cells = []
        for source_name in source_names:
            source_cov = row["sources"][source_name]["coverage"]
            source_cells.append(pct(source_cov))

        lines.append(
            f"| {field} | " +
            " | ".join(source_cells) +
            f" | {pct(row['weighted_source_coverage'])} | {pct(row['canonical_coverage'])} | {retention} |"
        )

    lines.append("")
    return "\n".join(lines)


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare source audit reports to canonical audit.")
    parser.add_argument(
        "--canonical",
        default="artifacts/reports/corpus_audit_latest.json",
        help="Canonical corpus audit JSON",
    )
    parser.add_argument(
        "--arxiv",
        default="artifacts/reports/source_audit/arxiv_latest.json",
        help="arXiv source audit JSON",
    )
    parser.add_argument(
        "--openalex",
        default="artifacts/reports/source_audit/openalex_alignment_latest.json",
        help="OpenAlex source audit JSON",
    )
    parser.add_argument(
        "--semantic-scholar",
        default="artifacts/reports/source_audit/semantic_scholar_alignment_latest.json",
        help="Semantic Scholar alignment source audit JSON",
    )
    parser.add_argument(
        "--crossref",
        default="artifacts/reports/source_audit/crossref_alignment_latest.json",
        help="Crossref alignment source audit JSON",
    )
    parser.add_argument(
        "--output-json",
        default="artifacts/reports/source_to_canonical_latest.json",
        help="Output JSON report",
    )
    parser.add_argument(
        "--output-md",
        default="artifacts/reports/source_to_canonical_latest.md",
        help="Output Markdown report",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    canonical = load_json(Path(args.canonical))
    source_reports = {
        "arxiv": load_json(Path(args.arxiv)),
        "openalex_alignment": load_json(Path(args.openalex)),
        "semantic_scholar_alignment": load_json(Path(args.semantic_scholar)),
        "crossref_alignment": load_json(Path(args.crossref)),
    }

    report = build_rows(canonical=canonical, source_reports=source_reports)
    md = build_markdown(report)

    save_json(Path(args.output_json), report)
    save_text(Path(args.output_md), md)

    print(f"[OK] canonical: {args.canonical}")
    print(f"[OK] arxiv: {args.arxiv}")
    print(f"[OK] openalex: {args.openalex}")
    print(f"[OK] semantic_scholar: {args.semantic_scholar}")
    print(f"[OK] crossref: {args.crossref}")
    print(f"[OK] JSON report: {args.output_json}")
    print(f"[OK] Markdown report: {args.output_md}")


if __name__ == "__main__":
    main()