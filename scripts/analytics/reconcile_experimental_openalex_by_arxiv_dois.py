from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from radar_core.contracts.document import NormalizedDocument
from radar_core.normalize.reconcile import reconcile_documents


REPORTS_DIR = Path("artifacts/reports")
OUTPUT_DIR = Path("data/analytics/experimental")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_normalized_jsonl(path: Path) -> list[NormalizedDocument]:
    rows: list[NormalizedDocument] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            rows.append(NormalizedDocument(**payload))
    return rows


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def dump_jsonl(path: Path, rows: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            if hasattr(row, "model_dump"):
                payload = row.model_dump(mode="json")
            elif hasattr(row, "dict"):
                payload = row.dict()
            else:
                payload = row
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def dump_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def normalize_doi(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    prefixes = (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    )
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    text = text.strip().strip("/")
    return text or None


def index_by_doi(rows: list[NormalizedDocument]) -> dict[str, list[NormalizedDocument]]:
    out: dict[str, list[NormalizedDocument]] = {}
    for row in rows:
        doi = normalize_doi(row.doi)
        if not doi:
            continue
        out.setdefault(doi, []).append(row)
    return out


def collect_source_names(doc: Any) -> list[str]:
    values: list[str] = []

    sources = getattr(doc, "sources", None) or []
    for src in sources:
        if isinstance(src, str):
            if src.strip():
                values.append(src.strip())
        elif isinstance(src, dict):
            source_name = (src.get("source") or src.get("raw_source_name") or "").strip()
            if source_name:
                values.append(source_name)
        else:
            source_name = getattr(src, "source", None)
            if source_name and str(source_name).strip():
                values.append(str(source_name).strip())

    return values


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Experimental reconcile: arXiv DOI subset + OpenAlex DOI fetch")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- arXiv input file: `{report['inputs']['arxiv_file']}`")
    lines.append(f"- OpenAlex input file: `{report['inputs']['openalex_file']}`")
    lines.append(f"- arXiv selected docs: {report['inputs']['arxiv_selected_count']}")
    lines.append(f"- OpenAlex docs: {report['inputs']['openalex_count']}")
    lines.append("")
    lines.append("## Summary")
    for k, v in report["summary"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Multi-source examples")
    for item in report["examples"]["multi_source_examples"]:
        lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    lines.append("")
    lines.append("## Not merged DOI examples")
    for item in report["examples"]["not_merged_doi_examples"]:
        lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run reconcile on DOI-aligned experimental arXiv/OpenAlex slice."
    )
    parser.add_argument(
        "--arxiv",
        required=True,
        help="Path to arXiv normalized JSONL used as source pool.",
    )
    parser.add_argument(
        "--openalex",
        required=True,
        help="Path to experimental OpenAlex normalized JSONL fetched by arXiv DOIs.",
    )
    parser.add_argument(
        "--output-jsonl",
        default=None,
        help="Optional output path for experimental canonical JSONL.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ts = utc_now_ts()

    arxiv_path = Path(args.arxiv)
    openalex_path = Path(args.openalex)

    arxiv_rows = load_normalized_jsonl(arxiv_path)
    openalex_rows = load_normalized_jsonl(openalex_path)

    openalex_dois = set(index_by_doi(openalex_rows).keys())

    arxiv_selected = [
        row for row in arxiv_rows
        if normalize_doi(row.doi) in openalex_dois
    ]

    combined = arxiv_selected + openalex_rows
    canonical_docs = reconcile_documents(combined)

    if args.output_jsonl:
        output_jsonl = Path(args.output_jsonl)
    else:
        output_jsonl = OUTPUT_DIR / f"canonical_experimental_openalex_by_arxiv_dois.{ts}.jsonl"

    dump_jsonl(output_jsonl, canonical_docs)

    multi_source_docs = []
    source_counter = Counter()

    for doc in canonical_docs:
        sources = collect_source_names(doc)
        for s in sources:
            source_counter[s] += 1

        if len(set(sources)) > 1:
            multi_source_docs.append(doc)

    merged_dois = {
        normalize_doi(doc.doi)
        for doc in multi_source_docs
        if normalize_doi(doc.doi)
    }

    openalex_by_doi = index_by_doi(openalex_rows)
    arxiv_by_doi = index_by_doi(arxiv_selected)

    not_merged_examples: list[dict[str, Any]] = []
    for doi in sorted(openalex_dois):
        if doi in merged_dois:
            continue

        oa = openalex_by_doi[doi][0]
        ax = arxiv_by_doi.get(doi, [None])[0]

        not_merged_examples.append(
            {
                "doi": doi,
                "openalex_title": oa.title,
                "openalex_year": oa.year,
                "arxiv_title": None if ax is None else ax.title,
                "arxiv_year": None if ax is None else ax.year,
            }
        )

        if len(not_merged_examples) >= 20:
            break

    multi_source_examples = []
    for doc in multi_source_docs[:20]:
        multi_source_examples.append(
            {
                "canonical_id": doc.canonical_id,
                "doi": doc.doi,
                "title": doc.title,
                "year": doc.year,
                "source_count": doc.source_count,
                "unique_source_count": doc.unique_source_count,
                "sources": collect_source_names(doc),
                "cited_by_count": doc.cited_by_count,
                "venue": doc.venue,
                "publication_type": doc.publication_type,
            }
        )

    report = {
        "report_name": "reconcile_experimental_openalex_by_arxiv_dois",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "arxiv_file": str(arxiv_path),
            "openalex_file": str(openalex_path),
            "arxiv_selected_count": len(arxiv_selected),
            "openalex_count": len(openalex_rows),
            "combined_input_count": len(combined),
        },
        "summary": {
            "canonical_count": len(canonical_docs),
            "multi_source_count": len(multi_source_docs),
            "merged_doi_count": len(merged_dois),
            "openalex_doi_count": len(openalex_dois),
            "source_distribution_in_canonical_sources": dict(source_counter),
        },
        "examples": {
            "multi_source_examples": multi_source_examples,
            "not_merged_doi_examples": not_merged_examples,
        },
        "artifacts": {
            "canonical_jsonl": str(output_jsonl),
        },
    }

    report_json = REPORTS_DIR / "reconcile_experimental_openalex_by_arxiv_dois_latest.json"
    report_md = REPORTS_DIR / "reconcile_experimental_openalex_by_arxiv_dois_latest.md"
    hist_json = REPORTS_DIR / "history" / f"reconcile_experimental_openalex_by_arxiv_dois_{ts}.json"
    hist_md = REPORTS_DIR / "history" / f"reconcile_experimental_openalex_by_arxiv_dois_{ts}.md"

    dump_json(report_json, report)
    dump_text(report_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] arXiv selected docs: {len(arxiv_selected)}")
    print(f"[OK] OpenAlex docs: {len(openalex_rows)}")
    print(f"[OK] combined input docs: {len(combined)}")
    print(f"[OK] canonical docs: {len(canonical_docs)}")
    print(f"[OK] multi-source canonical docs: {len(multi_source_docs)}")
    print(f"[OK] canonical JSONL: {output_jsonl}")
    print(f"[OK] report JSON: {report_json}")
    print(f"[OK] report MD: {report_md}")


if __name__ == "__main__":
    main()