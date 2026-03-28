from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


RAW_DIR = Path("data/raw/openalex")
NORMALIZED_DIR = Path("data/normalized/openalex")
REPORTS_DIR = Path("artifacts/reports")


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


def find_latest_raw_file() -> Path:
    run_dirs = sorted([p for p in RAW_DIR.iterdir() if p.is_dir()])
    if not run_dirs:
        raise FileNotFoundError(f"No raw OpenAlex runs found in {RAW_DIR}")
    candidate = run_dirs[-1] / "documents.raw.jsonl"
    if not candidate.exists():
        raise FileNotFoundError(f"Raw file not found: {candidate}")
    return candidate


def find_latest_normalized_file() -> Path:
    candidates = []
    for path in NORMALIZED_DIR.glob("documents.*.jsonl"):
        name = path.name
        if ".new." in name or ".updated." in name or ".unchanged." in name:
            continue
        candidates.append(path)

    candidates = sorted(candidates)
    if not candidates:
        raise FileNotFoundError(f"No primary normalized OpenAlex files found in {NORMALIZED_DIR}")
    return candidates[-1]


def extract_raw_metrics(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload") or {}
    return {
        "doc_id": row.get("doc_id"),
        "title": payload.get("display_name") or payload.get("title"),
        "publication_year": payload.get("publication_year"),
        "publication_date": payload.get("publication_date"),
        "cited_by_count": payload.get("cited_by_count"),
        "referenced_works_count": len(payload.get("referenced_works") or []),
        "doi": payload.get("doi"),
        "source_id": payload.get("id"),
    }


def extract_normalized_metrics(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_id": row.get("doc_id"),
        "title": row.get("title"),
        "year": row.get("year"),
        "publication_date": row.get("publication_date"),
        "cited_by_count": row.get("cited_by_count"),
        "references_count": row.get("references_count"),
        "referenced_ids_count": len(row.get("referenced_ids") or []),
        "doi": row.get("doi"),
        "source_id": row.get("source_id"),
    }


def summarize_counts(values: list[Optional[int]]) -> dict[str, Any]:
    clean = [v for v in values if isinstance(v, int)]
    if not clean:
        return {
            "count_with_int": 0,
            "min": None,
            "max": None,
            "mean": None,
            "gt_0": 0,
            "eq_0": 0,
        }

    mean_value = round(sum(clean) / len(clean), 4)
    return {
        "count_with_int": len(clean),
        "min": min(clean),
        "max": max(clean),
        "mean": mean_value,
        "gt_0": sum(1 for v in clean if v > 0),
        "eq_0": sum(1 for v in clean if v == 0),
    }


def bucketize(values: list[Optional[int]]) -> dict[str, int]:
    buckets = Counter()

    for v in values:
        if v is None:
            buckets["missing"] += 1
        elif v == 0:
            buckets["0"] += 1
        elif 1 <= v <= 5:
            buckets["1-5"] += 1
        elif 6 <= v <= 20:
            buckets["6-20"] += 1
        elif 21 <= v <= 100:
            buckets["21-100"] += 1
        else:
            buckets["100+"] += 1

    return dict(buckets)


def index_by_doc_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out = {}
    for row in rows:
        doc_id = row.get("doc_id")
        if doc_id:
            out[doc_id] = row
    return out


def build_report(raw_rows: list[dict[str, Any]], norm_rows: list[dict[str, Any]], raw_path: Path, norm_path: Path) -> dict[str, Any]:
    raw_metrics = [extract_raw_metrics(r) for r in raw_rows]
    norm_metrics = [extract_normalized_metrics(r) for r in norm_rows]

    raw_cited = [r["cited_by_count"] for r in raw_metrics]
    norm_cited = [r["cited_by_count"] for r in norm_metrics]

    raw_idx = index_by_doc_id(raw_metrics)
    norm_idx = index_by_doc_id(norm_metrics)

    mismatches: list[dict[str, Any]] = []
    for doc_id, raw_row in raw_idx.items():
        norm_row = norm_idx.get(doc_id)
        if not norm_row:
            continue
        if raw_row["cited_by_count"] != norm_row["cited_by_count"]:
            mismatches.append(
                {
                    "doc_id": doc_id,
                    "title": raw_row["title"] or norm_row["title"],
                    "raw_cited_by_count": raw_row["cited_by_count"],
                    "normalized_cited_by_count": norm_row["cited_by_count"],
                    "publication_year": raw_row["publication_year"],
                    "publication_date": raw_row["publication_date"],
                }
            )

    raw_refs_gt0 = [
        r for r in raw_metrics
        if isinstance(r["referenced_works_count"], int) and r["referenced_works_count"] > 0
    ]

    sample_raw_refs = raw_refs_gt0[:10]

    report = {
        "report_name": "openalex_cited_by_check",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": {
            "raw_file": str(raw_path),
            "normalized_file": str(norm_path),
            "raw_count": len(raw_rows),
            "normalized_count": len(norm_rows),
        },
        "raw_cited_by": {
            "summary": summarize_counts(raw_cited),
            "buckets": bucketize(raw_cited),
        },
        "normalized_cited_by": {
            "summary": summarize_counts(norm_cited),
            "buckets": bucketize(norm_cited),
        },
        "comparison": {
            "mismatch_count": len(mismatches),
            "mismatches_sample": mismatches[:20],
        },
        "references_raw": {
            "docs_with_referenced_works_gt_0": len(raw_refs_gt0),
            "sample": sample_raw_refs,
        },
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []

    lines.append("# OpenAlex cited_by / references check")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Raw file: `{report['input']['raw_file']}`")
    lines.append(f"- Normalized file: `{report['input']['normalized_file']}`")
    lines.append(f"- Raw count: {report['input']['raw_count']}")
    lines.append(f"- Normalized count: {report['input']['normalized_count']}")
    lines.append("")

    for block_key, title in [
        ("raw_cited_by", "Raw cited_by_count"),
        ("normalized_cited_by", "Normalized cited_by_count"),
    ]:
        block = report[block_key]
        summary = block["summary"]
        lines.append(f"## {title}")
        lines.append(f"- count_with_int: {summary['count_with_int']}")
        lines.append(f"- min: {summary['min']}")
        lines.append(f"- max: {summary['max']}")
        lines.append(f"- mean: {summary['mean']}")
        lines.append(f"- gt_0: {summary['gt_0']}")
        lines.append(f"- eq_0: {summary['eq_0']}")
        lines.append("- buckets:")
        for k, v in block["buckets"].items():
            lines.append(f"  - {k}: {v}")
        lines.append("")

    comp = report["comparison"]
    lines.append("## Raw vs normalized comparison")
    lines.append(f"- mismatch_count: {comp['mismatch_count']}")
    if comp["mismatches_sample"]:
        lines.append("- mismatches_sample:")
        for item in comp["mismatches_sample"]:
            lines.append(f"  - {json.dumps(item, ensure_ascii=False)}")
    lines.append("")

    refs = report["references_raw"]
    lines.append("## Raw references")
    lines.append(f"- docs_with_referenced_works_gt_0: {refs['docs_with_referenced_works_gt_0']}")
    if refs["sample"]:
        lines.append("- sample:")
        for item in refs["sample"]:
            lines.append(f"  - {json.dumps(item, ensure_ascii=False)}")

    return "\n".join(lines)


def main() -> None:
    raw_path = find_latest_raw_file()
    norm_path = find_latest_normalized_file()

    raw_rows = load_jsonl(raw_path)
    norm_rows = load_jsonl(norm_path)

    report = build_report(raw_rows, norm_rows, raw_path=raw_path, norm_path=norm_path)

    json_path = REPORTS_DIR / "openalex_cited_by_check_latest.json"
    md_path = REPORTS_DIR / "openalex_cited_by_check_latest.md"

    dump_json(json_path, report)
    dump_text(md_path, render_markdown(report))

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    hist_json = REPORTS_DIR / "history" / f"openalex_cited_by_check_{ts}.json"
    hist_md = REPORTS_DIR / "history" / f"openalex_cited_by_check_{ts}.md"

    dump_json(hist_json, report)
    dump_text(hist_md, render_markdown(report))

    print(f"[OK] raw docs: {len(raw_rows)}")
    print(f"[OK] normalized docs: {len(norm_rows)}")
    print(f"[OK] JSON report: {json_path}")
    print(f"[OK] Markdown report: {md_path}")
    print(f"[OK] snapshot JSON: {hist_json}")
    print(f"[OK] snapshot MD: {hist_md}")


if __name__ == "__main__":
    main()