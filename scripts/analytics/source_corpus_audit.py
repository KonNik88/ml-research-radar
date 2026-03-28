from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


BOOL_FIELDS = {
    "open_access",
    "has_code_link",
    "has_dataset_link",
    "has_model_link",
    "is_preprint",
    "is_review",
    "is_survey",
    "is_withdrawn",
    "citation_graph_available",
}

FIELD_NAMES = [
    "title",
    "abstract",
    "authors",
    "doi",
    "arxiv_id",
    "openalex_id",
    "landing_page_url",
    "pdf_url",
    "repo_url",
    "license",
    "open_access",
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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    docs = []
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


def latest_jsonl_in_dir(directory: Path) -> Path:
    candidates = sorted(
        [
            p
            for p in directory.glob("documents.*.jsonl")
            if not p.name.endswith(".new.jsonl")
            and not p.name.endswith(".updated.jsonl")
            and not p.name.endswith(".unchanged.jsonl")
        ]
    )
    if not candidates:
        raise FileNotFoundError(f"No normalized JSONL files found in {directory}")
    return candidates[-1]


def coverage_for_docs(docs: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(docs)
    out = {}

    for field in FIELD_NAMES:
        present = 0
        true_count = 0
        top_values = Counter()

        for doc in docs:
            value = doc.get(field)

            if field in BOOL_FIELDS:
                if value is not None:
                    present += 1
                if value is True:
                    true_count += 1
                continue

            if is_non_empty(value):
                present += 1
                if isinstance(value, str):
                    top_values[value.strip()] += 1
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str) and item.strip():
                            top_values[item.strip()] += 1

        entry = {
            "present_count": present,
            "coverage": round(present / total, 4) if total else 0.0,
        }

        if field in BOOL_FIELDS:
            entry["true_count"] = true_count
            entry["true_rate"] = round(true_count / total, 4) if total else 0.0

        if top_values:
            entry["top_values"] = top_values.most_common(15)

        out[field] = entry

    return out


def build_report(source: str, path: Path, docs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "source": source,
        "input_path": str(path),
        "total_docs": len(docs),
        "field_coverage": coverage_for_docs(docs),
    }


def build_markdown(report: dict[str, Any]) -> str:
    lines = []
    lines.append(f"# Source Corpus Audit: {report['source']}")
    lines.append("")
    lines.append(f"- Input path: `{report['input_path']}`")
    lines.append(f"- Total docs: **{report['total_docs']}**")
    lines.append("")
    lines.append("| Field | Present | Coverage | True count | True rate |")
    lines.append("|---|---:|---:|---:|---:|")

    for field in sorted(report["field_coverage"].keys()):
        item = report["field_coverage"][field]
        if field in BOOL_FIELDS:
            lines.append(
                f"| {field} | {item['present_count']} | {item['coverage']:.2%} | "
                f"{item.get('true_count', 0)} | {item.get('true_rate', 0.0):.2%} |"
            )
        else:
            lines.append(
                f"| {field} | {item['present_count']} | {item['coverage']:.2%} | - | - |"
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
    parser = argparse.ArgumentParser(description="Audit latest normalized docs by source.")
    parser.add_argument(
        "--normalized-root",
        default="data/normalized",
        help="Root directory containing source subdirectories",
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        default=["openalex_alignment", "arxiv", "semantic_scholar_alignment", "crossref_alignment"],
        help="Sources to audit",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/reports/source_audit",
        help="Directory to store source audit reports",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    normalized_root = Path(args.normalized_root)
    output_dir = Path(args.output_dir)

    for source in args.sources:
        source_dir = normalized_root / source
        latest_path = latest_jsonl_in_dir(source_dir)
        docs = load_jsonl(latest_path)
        report = build_report(source, latest_path, docs)
        md = build_markdown(report)

        json_path = output_dir / f"{source}_latest.json"
        md_path = output_dir / f"{source}_latest.md"
        save_json(json_path, report)
        save_text(md_path, md)

        print(f"[OK] source={source}")
        print(f"[OK] input: {latest_path}")
        print(f"[OK] docs: {len(docs)}")
        print(f"[OK] JSON report: {json_path}")
        print(f"[OK] Markdown report: {md_path}")


if __name__ == "__main__":
    main()