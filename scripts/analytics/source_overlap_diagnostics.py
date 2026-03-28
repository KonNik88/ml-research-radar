from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OPENALEX_DIR = Path("data/normalized/openalex")
ARXIV_DIR = Path("data/normalized/arxiv")
REPORTS_DIR = Path("artifacts/reports")

TITLE_CLEAN_RE = re.compile(r"[^\w\s]")


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


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip().lower()
    value = TITLE_CLEAN_RE.sub(" ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lower()
    prefixes = (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    )
    for p in prefixes:
        if value.startswith(p):
            value = value[len(p):]
            break
    value = value.strip().strip("/")
    return value or None


def extract_arxiv_id(doc: dict[str, Any]) -> str | None:
    candidates = [
        doc.get("arxiv_id"),
        (doc.get("external_ids") or {}).get("arxiv"),
        (doc.get("source_ids") or {}).get("arxiv"),
    ]
    for c in candidates:
        if c and str(c).strip():
            return str(c).strip().lower()
    return None


def title_key(doc: dict[str, Any]) -> str:
    return normalize_text(doc.get("title"))


def title_year_key(doc: dict[str, Any]) -> str:
    return f"{normalize_text(doc.get('title'))}::{doc.get('year')}"


def build_index(rows: list[dict[str, Any]], key_fn) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = key_fn(row)
        if not key or key == "::None":
            continue
        out.setdefault(key, []).append(row)
    return out


def sample_pairs(left_rows: list[dict[str, Any]], right_rows: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for l in left_rows[:limit]:
        for r in right_rows[:limit]:
            pairs.append(
                {
                    "openalex_doc_id": l.get("doc_id"),
                    "openalex_title": l.get("title"),
                    "openalex_year": l.get("year"),
                    "openalex_doi": l.get("doi"),
                    "arxiv_doc_id": r.get("doc_id"),
                    "arxiv_title": r.get("title"),
                    "arxiv_year": r.get("year"),
                    "arxiv_id": r.get("arxiv_id"),
                }
            )
            if len(pairs) >= limit:
                return pairs
    return pairs


def build_report(openalex_rows: list[dict[str, Any]], arxiv_rows: list[dict[str, Any]], openalex_path: Path, arxiv_path: Path) -> dict[str, Any]:
    openalex_by_doi = build_index(openalex_rows, lambda r: normalize_doi(r.get("doi")))
    arxiv_by_doi = build_index(arxiv_rows, lambda r: normalize_doi(r.get("doi")))

    openalex_by_arxiv = build_index(openalex_rows, extract_arxiv_id)
    arxiv_by_arxiv = build_index(arxiv_rows, extract_arxiv_id)

    openalex_by_title = build_index(openalex_rows, title_key)
    arxiv_by_title = build_index(arxiv_rows, title_key)

    openalex_by_title_year = build_index(openalex_rows, title_year_key)
    arxiv_by_title_year = build_index(arxiv_rows, title_year_key)

    doi_overlap_keys = sorted(set(openalex_by_doi) & set(arxiv_by_doi))
    arxiv_overlap_keys = sorted(set(openalex_by_arxiv) & set(arxiv_by_arxiv))
    title_overlap_keys = sorted(set(openalex_by_title) & set(arxiv_by_title))
    title_year_overlap_keys = sorted(set(openalex_by_title_year) & set(arxiv_by_title_year))

    title_overlap_examples: list[dict[str, Any]] = []
    for key in title_overlap_keys[:20]:
        title_overlap_examples.extend(sample_pairs(openalex_by_title[key], arxiv_by_title[key], limit=5))
        if len(title_overlap_examples) >= 20:
            break

    title_year_overlap_examples: list[dict[str, Any]] = []
    for key in title_year_overlap_keys[:20]:
        title_year_overlap_examples.extend(sample_pairs(openalex_by_title_year[key], arxiv_by_title_year[key], limit=5))
        if len(title_year_overlap_examples) >= 20:
            break

    year_counter_openalex = Counter(str(r.get("year")) for r in openalex_rows if r.get("year") is not None)
    year_counter_arxiv = Counter(str(r.get("year")) for r in arxiv_rows if r.get("year") is not None)

    return {
        "report_name": "source_overlap_diagnostics",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "openalex_file": str(openalex_path),
            "arxiv_file": str(arxiv_path),
            "openalex_count": len(openalex_rows),
            "arxiv_count": len(arxiv_rows),
        },
        "year_distribution": {
            "openalex": dict(year_counter_openalex.most_common(10)),
            "arxiv": dict(year_counter_arxiv.most_common(10)),
        },
        "overlap": {
            "doi_overlap_count": len(doi_overlap_keys),
            "arxiv_id_overlap_count": len(arxiv_overlap_keys),
            "title_overlap_count": len(title_overlap_keys),
            "title_year_overlap_count": len(title_year_overlap_keys),
            "doi_overlap_keys_sample": doi_overlap_keys[:20],
            "arxiv_id_overlap_keys_sample": arxiv_overlap_keys[:20],
            "title_overlap_examples": title_overlap_examples[:20],
            "title_year_overlap_examples": title_year_overlap_examples[:20],
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Source overlap diagnostics")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- OpenAlex file: `{report['inputs']['openalex_file']}`")
    lines.append(f"- arXiv file: `{report['inputs']['arxiv_file']}`")
    lines.append(f"- OpenAlex count: {report['inputs']['openalex_count']}")
    lines.append(f"- arXiv count: {report['inputs']['arxiv_count']}")
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
    lines.append(f"- DOI overlap: {ov['doi_overlap_count']}")
    lines.append(f"- arXiv ID overlap: {ov['arxiv_id_overlap_count']}")
    lines.append(f"- Title overlap: {ov['title_overlap_count']}")
    lines.append(f"- Title+year overlap: {ov['title_year_overlap_count']}")
    lines.append("")

    lines.append("## DOI overlap sample")
    if ov["doi_overlap_keys_sample"]:
        for item in ov["doi_overlap_keys_sample"]:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## arXiv ID overlap sample")
    if ov["arxiv_id_overlap_keys_sample"]:
        for item in ov["arxiv_id_overlap_keys_sample"]:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Title overlap examples")
    if ov["title_overlap_examples"]:
        for item in ov["title_overlap_examples"]:
            lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Title+year overlap examples")
    if ov["title_year_overlap_examples"]:
        for item in ov["title_year_overlap_examples"]:
            lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    else:
        lines.append("- none")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    openalex_path = find_latest_primary_jsonl(OPENALEX_DIR)
    arxiv_path = find_latest_primary_jsonl(ARXIV_DIR)

    openalex_rows = load_jsonl(openalex_path)
    arxiv_rows = load_jsonl(arxiv_path)

    report = build_report(openalex_rows, arxiv_rows, openalex_path=openalex_path, arxiv_path=arxiv_path)

    json_path = REPORTS_DIR / "source_overlap_diagnostics_latest.json"
    md_path = REPORTS_DIR / "source_overlap_diagnostics_latest.md"

    dump_json(json_path, report)
    dump_text(md_path, render_markdown(report))

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    hist_json = REPORTS_DIR / "history" / f"source_overlap_diagnostics_{ts}.json"
    hist_md = REPORTS_DIR / "history" / f"source_overlap_diagnostics_{ts}.md"

    dump_json(hist_json, report)
    dump_text(hist_md, render_markdown(report))

    print(f"[OK] OpenAlex docs: {len(openalex_rows)}")
    print(f"[OK] arXiv docs: {len(arxiv_rows)}")
    print(f"[OK] JSON report: {json_path}")
    print(f"[OK] Markdown report: {md_path}")
    print(f"[OK] snapshot JSON: {hist_json}")
    print(f"[OK] snapshot MD: {hist_md}")


if __name__ == "__main__":
    main()