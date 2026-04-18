from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/analytics")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    return text or None


def pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(part / total, 4)


def classify_text_length(word_count: int) -> str:
    if word_count == 0:
        return "empty"
    if word_count < 50:
        return "very_short"
    if word_count < 150:
        return "short"
    if word_count < 300:
        return "medium"
    return "long"


def build_markdown(report: dict[str, Any]) -> str:
    c = report["coverage"]
    qc = report["quality_checks"]
    lines: list[str] = []
    lines.append("# Canonical text coverage report")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Canonical path: `{report['canonical_path']}`")
    lines.append("")
    lines.append("## Coverage")
    for key, value in c.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## Quality checks")
    for key, value in qc.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## Top years")
    for year, count in report["top_years"]:
        lines.append(f"- {year}: {count}")
    lines.append("")
    lines.append("## Top categories")
    for cat, count in report["top_categories"]:
        lines.append(f"- {cat}: {count}")
    lines.append("")
    lines.append("## Abstract length buckets")
    for bucket, count in report["abstract_length_buckets"].items():
        lines.append(f"- {bucket}: {count}")
    lines.append("")
    lines.append("## Sample records missing abstract")
    for item in report["samples_missing_abstract"]:
        lines.append(
            f"- canonical_id={item.get('canonical_id')} | year={item.get('year')} | title={item.get('title')}"
        )
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure text/metadata coverage of the canonical corpus before embeddings/full-text work."
    )
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--sample-missing", type=int, default=20)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    if not args.canonical_path.exists():
        raise FileNotFoundError(f"Canonical corpus not found: {args.canonical_path}")

    total_docs = 0
    with_title = 0
    with_abstract = 0
    with_authors = 0
    with_year = 0
    with_doi = 0
    with_categories = 0
    with_concepts = 0
    with_keywords = 0
    with_tags = 0
    with_pdf = 0
    multisource_docs = 0

    abstract_word_counts: list[int] = []
    abstract_length_buckets: Counter[str] = Counter()
    year_counter: Counter[int] = Counter()
    category_counter: Counter[str] = Counter()
    samples_missing_abstract: list[dict[str, Any]] = []

    for row in iter_jsonl(args.canonical_path):
        total_docs += 1

        title = normalize_text(row.get("title"))
        abstract = normalize_text(row.get("abstract"))
        authors = row.get("authors") or []
        year = row.get("year")
        doi = normalize_text(row.get("doi"))
        categories = row.get("categories") or []
        concepts = row.get("concepts") or []
        keywords = row.get("keywords") or []
        tags = row.get("tags") or []
        pdf_url = normalize_text(row.get("pdf_url"))

        if title:
            with_title += 1
        if abstract:
            with_abstract += 1
            wc = len(abstract.split())
            abstract_word_counts.append(wc)
            abstract_length_buckets[classify_text_length(wc)] += 1
        else:
            abstract_length_buckets["empty"] += 1
            if len(samples_missing_abstract) < args.sample_missing:
                samples_missing_abstract.append(
                    {
                        "canonical_id": row.get("canonical_id"),
                        "title": row.get("title"),
                        "year": row.get("year"),
                    }
                )

        if authors:
            with_authors += 1
        if year is not None:
            with_year += 1
            try:
                year_counter[int(year)] += 1
            except Exception:
                pass
        if doi:
            with_doi += 1
        if categories:
            with_categories += 1
            for cat in categories:
                if cat:
                    category_counter[str(cat)] += 1
        if concepts:
            with_concepts += 1
        if keywords:
            with_keywords += 1
        if tags:
            with_tags += 1
        if pdf_url:
            with_pdf += 1

        if int(row.get("unique_source_count", 0) or 0) > 1:
            multisource_docs += 1

    avg_abstract_words = round(sum(abstract_word_counts) / len(abstract_word_counts), 2) if abstract_word_counts else 0.0
    median_abstract_words = 0
    if abstract_word_counts:
        sorted_counts = sorted(abstract_word_counts)
        mid = len(sorted_counts) // 2
        if len(sorted_counts) % 2 == 0:
            median_abstract_words = round((sorted_counts[mid - 1] + sorted_counts[mid]) / 2, 2)
        else:
            median_abstract_words = sorted_counts[mid]

    coverage = {
        "total_docs": total_docs,
        "with_title": with_title,
        "with_title_pct": pct(with_title, total_docs),
        "with_abstract": with_abstract,
        "with_abstract_pct": pct(with_abstract, total_docs),
        "with_authors": with_authors,
        "with_authors_pct": pct(with_authors, total_docs),
        "with_year": with_year,
        "with_year_pct": pct(with_year, total_docs),
        "with_doi": with_doi,
        "with_doi_pct": pct(with_doi, total_docs),
        "with_categories": with_categories,
        "with_categories_pct": pct(with_categories, total_docs),
        "with_concepts": with_concepts,
        "with_concepts_pct": pct(with_concepts, total_docs),
        "with_keywords": with_keywords,
        "with_keywords_pct": pct(with_keywords, total_docs),
        "with_tags": with_tags,
        "with_tags_pct": pct(with_tags, total_docs),
        "with_pdf": with_pdf,
        "with_pdf_pct": pct(with_pdf, total_docs),
        "multisource_docs": multisource_docs,
        "multisource_docs_pct": pct(multisource_docs, total_docs),
        "avg_abstract_words": avg_abstract_words,
        "median_abstract_words": median_abstract_words,
    }

    quality_checks = {
        "ready_for_abstract_embeddings": coverage["with_title_pct"] >= 0.95 and coverage["with_abstract_pct"] >= 0.70,
        "ready_for_fulltext_candidate_sampling": coverage["with_pdf_pct"] >= 0.20,
        "strong_metadata_for_similarity": coverage["with_authors_pct"] >= 0.90 and coverage["with_year_pct"] >= 0.95,
    }

    report = {
        "report_name": "check_text_coverage",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "canonical_path": str(args.canonical_path).replace("\\", "/"),
        "coverage": coverage,
        "quality_checks": quality_checks,
        "top_years": year_counter.most_common(20),
        "top_categories": category_counter.most_common(20),
        "abstract_length_buckets": dict(abstract_length_buckets),
        "samples_missing_abstract": samples_missing_abstract,
    }

    latest_json = args.reports_dir / "check_text_coverage_latest.json"
    latest_md = args.reports_dir / "check_text_coverage_latest.md"
    hist_json = args.reports_dir / "history" / f"check_text_coverage_{run_ts}.json"
    hist_md = args.reports_dir / "history" / f"check_text_coverage_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] total_docs={total_docs}")
    print(f"[OK] with_abstract={with_abstract} ({coverage['with_abstract_pct']})")
    print(f"[OK] with_pdf={with_pdf} ({coverage['with_pdf_pct']})")
    print(f"[OK] multisource_docs={multisource_docs} ({coverage['multisource_docs_pct']})")
    print(f"[OK] latest_json={latest_json}")
    print(f"[OK] latest_md={latest_md}")


if __name__ == "__main__":
    main()
