from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable


TITLE_CLEAN_RE = re.compile(r"[^\w\s]")
WS_RE = re.compile(r"\s+")

REPORTS_DIR = Path("artifacts/reports")
OPENALEX_DIR = Path("data/normalized/openalex")
ARXIV_DIR = Path("data/normalized/arxiv")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def dump_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def find_latest_primary_jsonl(base_dir: Path) -> Path:
    candidates = []
    for path in base_dir.glob("documents.*.jsonl"):
        name = path.name
        if ".new." in name or ".updated." in name or ".unchanged." in name:
            continue
        candidates.append(path)

    candidates = sorted(candidates)
    if not candidates:
        raise FileNotFoundError(f"No primary jsonl files found in {base_dir}")
    return candidates[-1]


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = TITLE_CLEAN_RE.sub(" ", text)
    text = WS_RE.sub(" ", text)
    return text.strip()


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


def normalize_arxiv_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None

    prefixes = (
        "https://arxiv.org/abs/",
        "http://arxiv.org/abs/",
        "https://export.arxiv.org/abs/",
        "http://export.arxiv.org/abs/",
        "arxiv:",
    )
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break

    text = text.strip().strip("/")
    return text or None


def get_external_id(doc: dict[str, Any], key: str) -> str | None:
    external_ids = doc.get("external_ids") or {}
    value = external_ids.get(key)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def extract_arxiv_id(doc: dict[str, Any]) -> str | None:
    candidates = [
        doc.get("arxiv_id"),
        get_external_id(doc, "arxiv"),
        (doc.get("source_ids") or {}).get("arxiv"),
    ]
    for value in candidates:
        normalized = normalize_arxiv_id(value)
        if normalized:
            return normalized
    return None


def title_key(doc: dict[str, Any]) -> str:
    return normalize_text(doc.get("title"))


def title_year_key(doc: dict[str, Any]) -> str:
    title = normalize_text(doc.get("title"))
    year = doc.get("year")
    if not title or year is None:
        return ""
    return f"{title}::{year}"


def first_author_key(doc: dict[str, Any]) -> str:
    authors = doc.get("authors") or []
    if not authors:
        return ""
    return normalize_text(authors[0])


def title_year_author_key(doc: dict[str, Any]) -> str:
    title = normalize_text(doc.get("title"))
    year = doc.get("year")
    first_author = first_author_key(doc)
    if not title or year is None:
        return ""
    return f"{title}::{year}::{first_author}"


def build_index(rows: list[dict[str, Any]], key_fn) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = key_fn(row)
        if not key:
            continue
        out.setdefault(key, []).append(row)
    return out


def sample_pair(left: dict[str, Any], right: dict[str, Any], *, reason: str, score: float | None = None) -> dict[str, Any]:
    payload = {
        "reason": reason,
        "openalex_doc_id": left.get("doc_id"),
        "openalex_openalex_id": left.get("openalex_id"),
        "openalex_doi": left.get("doi"),
        "openalex_arxiv_id": extract_arxiv_id(left),
        "openalex_title": left.get("title"),
        "openalex_year": left.get("year"),
        "arxiv_doc_id": right.get("doc_id"),
        "arxiv_doi": right.get("doi"),
        "arxiv_arxiv_id": extract_arxiv_id(right),
        "arxiv_title": right.get("title"),
        "arxiv_year": right.get("year"),
    }
    if score is not None:
        payload["similarity"] = round(score, 4)
    return payload


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def top_fuzzy_matches(
    openalex_rows: list[dict[str, Any]],
    arxiv_rows: list[dict[str, Any]],
    *,
    threshold: float,
    limit: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    arxiv_by_year: dict[int, list[dict[str, Any]]] = {}
    for row in arxiv_rows:
        year = row.get("year")
        if isinstance(year, int):
            arxiv_by_year.setdefault(year, []).append(row)

    for oa in openalex_rows:
        year = oa.get("year")
        title = title_key(oa)
        if not title or not isinstance(year, int):
            continue

        candidates = arxiv_by_year.get(year, [])
        for ax in candidates:
            ax_title = title_key(ax)
            if not ax_title:
                continue

            score = similarity(title, ax_title)
            if score < threshold:
                continue

            oa_author = first_author_key(oa)
            ax_author = first_author_key(ax)
            author_match = bool(oa_author and ax_author and oa_author == ax_author)
            if author_match:
                score = min(1.0, score + 0.02)

            results.append(sample_pair(oa, ax, reason="fuzzy_title_same_year", score=score))

    results.sort(key=lambda x: x.get("similarity", 0.0), reverse=True)

    deduped: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str | None, str | None]] = set()
    for item in results:
        pair_key = (item.get("openalex_doc_id"), item.get("arxiv_doc_id"))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        deduped.append(item)
        if len(deduped) >= limit:
            break

    return deduped


def summarize_years(rows: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(str(r.get("year")) for r in rows if r.get("year") is not None)
    return dict(counter.most_common(10))


def build_report(
    *,
    openalex_rows: list[dict[str, Any]],
    arxiv_rows: list[dict[str, Any]],
    openalex_path: Path,
    arxiv_path: Path,
    fuzzy_threshold: float,
    fuzzy_limit: int,
) -> dict[str, Any]:
    openalex_by_doi = build_index(openalex_rows, lambda r: normalize_doi(r.get("doi")))
    arxiv_by_doi = build_index(arxiv_rows, lambda r: normalize_doi(r.get("doi")))

    openalex_by_arxiv = build_index(openalex_rows, extract_arxiv_id)
    arxiv_by_arxiv = build_index(arxiv_rows, extract_arxiv_id)

    openalex_by_title = build_index(openalex_rows, title_key)
    arxiv_by_title = build_index(arxiv_rows, title_key)

    openalex_by_title_year = build_index(openalex_rows, title_year_key)
    arxiv_by_title_year = build_index(arxiv_rows, title_year_key)

    openalex_by_tya = build_index(openalex_rows, title_year_author_key)
    arxiv_by_tya = build_index(arxiv_rows, title_year_author_key)

    doi_overlap = sorted(set(openalex_by_doi) & set(arxiv_by_doi))
    arxiv_overlap = sorted(set(openalex_by_arxiv) & set(arxiv_by_arxiv))
    title_overlap = sorted(set(openalex_by_title) & set(arxiv_by_title))
    title_year_overlap = sorted(set(openalex_by_title_year) & set(arxiv_by_title_year))
    tya_overlap = sorted(set(openalex_by_tya) & set(arxiv_by_tya))

    doi_examples: list[dict[str, Any]] = []
    for key in doi_overlap[:20]:
        for oa in openalex_by_doi[key][:3]:
            for ax in arxiv_by_doi[key][:3]:
                doi_examples.append(sample_pair(oa, ax, reason="doi_exact"))
                if len(doi_examples) >= 20:
                    break
            if len(doi_examples) >= 20:
                break
        if len(doi_examples) >= 20:
            break

    arxiv_id_examples: list[dict[str, Any]] = []
    for key in arxiv_overlap[:20]:
        for oa in openalex_by_arxiv[key][:3]:
            for ax in arxiv_by_arxiv[key][:3]:
                arxiv_id_examples.append(sample_pair(oa, ax, reason="arxiv_id_exact"))
                if len(arxiv_id_examples) >= 20:
                    break
            if len(arxiv_id_examples) >= 20:
                break
        if len(arxiv_id_examples) >= 20:
            break

    title_year_author_examples: list[dict[str, Any]] = []
    for key in tya_overlap[:20]:
        for oa in openalex_by_tya[key][:3]:
            for ax in arxiv_by_tya[key][:3]:
                title_year_author_examples.append(sample_pair(oa, ax, reason="title_year_first_author_exact"))
                if len(title_year_author_examples) >= 20:
                    break
            if len(title_year_author_examples) >= 20:
                break
        if len(title_year_author_examples) >= 20:
            break

    fuzzy_examples = top_fuzzy_matches(
        openalex_rows,
        arxiv_rows,
        threshold=fuzzy_threshold,
        limit=fuzzy_limit,
    )

    arxiv_with_doi = sum(1 for row in arxiv_rows if normalize_doi(row.get("doi")))
    arxiv_with_arxiv_id = sum(1 for row in arxiv_rows if extract_arxiv_id(row))
    openalex_with_doi = sum(1 for row in openalex_rows if normalize_doi(row.get("doi")))
    openalex_with_arxiv_id = sum(1 for row in openalex_rows if extract_arxiv_id(row))

    report = {
        "report_name": "arxiv_openalex_presence_check",
        "generated_at_utc": utc_now_iso(),
        "inputs": {
            "openalex_file": str(openalex_path),
            "arxiv_file": str(arxiv_path),
            "openalex_count": len(openalex_rows),
            "arxiv_count": len(arxiv_rows),
        },
        "coverage": {
            "openalex_with_doi_count": openalex_with_doi,
            "openalex_with_arxiv_id_count": openalex_with_arxiv_id,
            "arxiv_with_doi_count": arxiv_with_doi,
            "arxiv_with_arxiv_id_count": arxiv_with_arxiv_id,
        },
        "year_distribution": {
            "openalex": summarize_years(openalex_rows),
            "arxiv": summarize_years(arxiv_rows),
        },
        "overlap": {
            "doi_exact_count": len(doi_overlap),
            "arxiv_id_exact_count": len(arxiv_overlap),
            "title_exact_count": len(title_overlap),
            "title_year_exact_count": len(title_year_overlap),
            "title_year_first_author_exact_count": len(tya_overlap),
            "doi_exact_examples": doi_examples,
            "arxiv_id_exact_examples": arxiv_id_examples,
            "title_year_first_author_exact_examples": title_year_author_examples,
            "fuzzy_title_same_year_examples": fuzzy_examples,
            "fuzzy_threshold": fuzzy_threshold,
        },
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []

    lines.append("# arXiv ↔ OpenAlex presence check")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- OpenAlex file: `{report['inputs']['openalex_file']}`")
    lines.append(f"- arXiv file: `{report['inputs']['arxiv_file']}`")
    lines.append(f"- OpenAlex docs: {report['inputs']['openalex_count']}")
    lines.append(f"- arXiv docs: {report['inputs']['arxiv_count']}")
    lines.append("")

    lines.append("## Coverage")
    for key, value in report["coverage"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")

    lines.append("## Year distribution")
    lines.append("### OpenAlex")
    for k, v in report["year_distribution"]["openalex"].items():
        lines.append(f"- {k}: {v}")
    lines.append("### arXiv")
    for k, v in report["year_distribution"]["arxiv"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    ov = report["overlap"]
    lines.append("## Overlap counts")
    lines.append(f"- doi_exact_count: {ov['doi_exact_count']}")
    lines.append(f"- arxiv_id_exact_count: {ov['arxiv_id_exact_count']}")
    lines.append(f"- title_exact_count: {ov['title_exact_count']}")
    lines.append(f"- title_year_exact_count: {ov['title_year_exact_count']}")
    lines.append(f"- title_year_first_author_exact_count: {ov['title_year_first_author_exact_count']}")
    lines.append(f"- fuzzy_threshold: {ov['fuzzy_threshold']}")
    lines.append("")

    for section_key, title in [
        ("doi_exact_examples", "DOI exact examples"),
        ("arxiv_id_exact_examples", "arXiv ID exact examples"),
        ("title_year_first_author_exact_examples", "Title+year+first_author exact examples"),
        ("fuzzy_title_same_year_examples", "Fuzzy title same-year examples"),
    ]:
        lines.append(f"## {title}")
        examples = ov.get(section_key) or []
        if not examples:
            lines.append("- none")
        else:
            for item in examples:
                lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
        lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check real cross-source presence between normalized arXiv and OpenAlex slices.")
    parser.add_argument(
        "--openalex",
        default=None,
        help="Path to normalized OpenAlex JSONL. Defaults to latest primary file.",
    )
    parser.add_argument(
        "--arxiv",
        default=None,
        help="Path to normalized arXiv JSONL. Defaults to latest primary file.",
    )
    parser.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=0.94,
        help="SequenceMatcher threshold for fuzzy title same-year examples.",
    )
    parser.add_argument(
        "--fuzzy-limit",
        type=int,
        default=30,
        help="Maximum number of fuzzy examples to keep.",
    )
    parser.add_argument(
        "--output-json",
        default="artifacts/reports/arxiv_openalex_presence_check_latest.json",
        help="Output JSON report path.",
    )
    parser.add_argument(
        "--output-md",
        default="artifacts/reports/arxiv_openalex_presence_check_latest.md",
        help="Output Markdown report path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    openalex_path = Path(args.openalex) if args.openalex else find_latest_primary_jsonl(OPENALEX_DIR)
    arxiv_path = Path(args.arxiv) if args.arxiv else find_latest_primary_jsonl(ARXIV_DIR)

    openalex_rows = load_jsonl(openalex_path)
    arxiv_rows = load_jsonl(arxiv_path)

    report = build_report(
        openalex_rows=openalex_rows,
        arxiv_rows=arxiv_rows,
        openalex_path=openalex_path,
        arxiv_path=arxiv_path,
        fuzzy_threshold=args.fuzzy_threshold,
        fuzzy_limit=args.fuzzy_limit,
    )

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)

    dump_json(output_json, report)
    dump_text(output_md, render_markdown(report))

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    hist_json = REPORTS_DIR / "history" / f"arxiv_openalex_presence_check_{ts}.json"
    hist_md = REPORTS_DIR / "history" / f"arxiv_openalex_presence_check_{ts}.md"

    dump_json(hist_json, report)
    dump_text(hist_md, render_markdown(report))

    print(f"[OK] OpenAlex docs: {len(openalex_rows)}")
    print(f"[OK] arXiv docs: {len(arxiv_rows)}")
    print(f"[OK] JSON report: {output_json}")
    print(f"[OK] Markdown report: {output_md}")
    print(f"[OK] snapshot JSON: {hist_json}")
    print(f"[OK] snapshot MD: {hist_md}")


if __name__ == "__main__":
    main()