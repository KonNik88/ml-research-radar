from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_NORMALIZED_ROOT = Path("data/normalized")
DEFAULT_RECONCILED_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_RETRIEVAL_MANIFEST = Path("artifacts/retrieval/manifests/latest.json")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/update")


PRIMARY_JSONL_RE = re.compile(r"^documents\.\d{8}T\d{6}Z\.jsonl$")
ARXIV_INCREMENTAL_MERGE_RE = re.compile(r"arxiv_incremental_merge_.*\.json$")


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


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def find_latest_primary_jsonl(source_dir: Path) -> Path | None:
    if not source_dir.exists():
        return None

    candidates = []
    for path in source_dir.glob("documents*.jsonl"):
        name = path.name
        if ".new." in name or ".updated." in name or ".unchanged." in name:
            continue
        if PRIMARY_JSONL_RE.match(name):
            candidates.append(path)

    if not candidates:
        all_candidates = [
            p for p in source_dir.glob("documents*.jsonl")
            if ".new." not in p.name and ".updated." not in p.name and ".unchanged." not in p.name
        ]
        if not all_candidates:
            return None
        return sorted(all_candidates)[-1]

    return sorted(candidates)[-1]


def find_latest_file(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None
    candidates = sorted(directory.glob(pattern))
    if not candidates:
        return None
    return candidates[-1]


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


def safe_len_jsonl(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def summarize_arxiv_snapshot(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {
            "path": None,
            "doc_count": 0,
            "doi_count": 0,
            "doi_coverage": 0.0,
            "year_min": None,
            "year_max": None,
            "sample_dois": [],
        }

    doc_count = 0
    doi_count = 0
    sample_dois: list[str] = []
    year_min: int | None = None
    year_max: int | None = None

    for row in iter_jsonl(path):
        doc_count += 1

        doi = normalize_doi(row.get("doi"))
        if doi:
            doi_count += 1
            if len(sample_dois) < 10:
                sample_dois.append(doi)

        year = row.get("year")
        if isinstance(year, int):
            year_min = year if year_min is None else min(year_min, year)
            year_max = year if year_max is None else max(year_max, year)

    doi_coverage = round(doi_count / doc_count, 4) if doc_count else 0.0

    return {
        "path": str(path),
        "doc_count": doc_count,
        "doi_count": doi_count,
        "doi_coverage": doi_coverage,
        "year_min": year_min,
        "year_max": year_max,
        "sample_dois": sample_dois,
    }


def summarize_generic_jsonl(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {
            "path": None,
            "doc_count": 0,
        }
    return {
        "path": str(path),
        "doc_count": safe_len_jsonl(path),
    }


def summarize_canonical(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {
            "path": None,
            "doc_count": 0,
            "multisource_docs": 0,
            "doi_count": 0,
        }

    doc_count = 0
    multisource_docs = 0
    doi_count = 0

    for row in iter_jsonl(path):
        doc_count += 1
        if normalize_doi(row.get("doi")):
            doi_count += 1

        usc = row.get("unique_source_count")
        if isinstance(usc, int) and usc > 1:
            multisource_docs += 1

    return {
        "path": str(path),
        "doc_count": doc_count,
        "multisource_docs": multisource_docs,
        "doi_count": doi_count,
    }


def summarize_retrieval_manifest(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {
            "path": None,
            "build_id": None,
            "corpus_doc_count": 0,
            "embedding_model_name": None,
        }

    payload = load_json(path)
    return {
        "path": str(path),
        "build_id": payload.get("build_id"),
        "corpus_doc_count": payload.get("corpus_doc_count", 0),
        "embedding_model_name": payload.get("embedding_model_name"),
        "corpus_path": payload.get("corpus_path"),
    }


def find_latest_incremental_merge_report(reports_dir: Path) -> Path | None:
    history_dir = reports_dir / "history"
    if not history_dir.exists():
        return None

    candidates = sorted(history_dir.glob("arxiv_incremental_merge_*.json"))
    if not candidates:
        latest = reports_dir / "arxiv_incremental_merge_latest.json"
        if latest.exists():
            return latest
        return None

    return candidates[-1]


def summarize_incremental_merge(report_path: Path | None) -> dict[str, Any]:
    if report_path is None or not report_path.exists():
        return {
            "path": None,
            "available": False,
            "summary": {},
        }

    payload = load_json(report_path)
    return {
        "path": str(report_path),
        "available": True,
        "summary": payload,
    }


def build_recommendations(
    *,
    canonical_summary: dict[str, Any],
    retrieval_summary: dict[str, Any],
    arxiv_summary: dict[str, Any],
    incremental_merge_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []

    canonical_docs = canonical_summary.get("doc_count", 0)
    retrieval_docs = retrieval_summary.get("corpus_doc_count", 0)

    if canonical_docs != retrieval_docs:
        recs.append(
            {
                "priority": "high",
                "action": "rebuild_retrieval",
                "reason": (
                    f"Canonical corpus doc count ({canonical_docs}) and retrieval corpus doc count "
                    f"({retrieval_docs}) do not match."
                ),
            }
        )
    else:
        recs.append(
            {
                "priority": "info",
                "action": "retrieval_in_sync",
                "reason": "Canonical corpus and retrieval manifest appear synchronized by document count.",
            }
        )

    if incremental_merge_summary.get("available"):
        recs.append(
            {
                "priority": "high",
                "action": "inspect_incremental_refresh_cycle",
                "reason": (
                    "Latest incremental merge report exists. Next step is to formalize how merged "
                    "incremental arXiv data should trigger selective enrichment, reconcile, export, "
                    "and retrieval rebuild."
                ),
            }
        )
    else:
        recs.append(
            {
                "priority": "medium",
                "action": "establish_incremental_baseline",
                "reason": (
                    "No incremental merge report was found. Before automating refresh strategy, confirm "
                    "the expected incremental state and merged-batch workflow."
                ),
            }
        )

    doi_cov = arxiv_summary.get("doi_coverage", 0.0)
    if doi_cov < 0.25:
        recs.append(
            {
                "priority": "medium",
                "action": "selective_doi_enrichment_only",
                "reason": (
                    f"Current arXiv DOI coverage is {doi_cov:.2%}; selective enrichment on new/updated DOI "
                    f"documents remains the most pragmatic next step."
                ),
            }
        )

    recs.append(
        {
            "priority": "high",
            "action": "design_plan_incremental_refresh_v1",
            "reason": (
                "Recommended v1 flow: arXiv incremental ingest -> merge incremental batches -> extract "
                "new/updated DOI candidates -> selective enrichment -> full reconcile -> full export -> full retrieval rebuild."
            ),
        }
    )

    return recs


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []

    lines.append("# Incremental refresh planning snapshot")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append("")

    arxiv = report["arxiv_primary_snapshot"]
    lines.append("## arXiv primary snapshot")
    lines.append(f"- path: `{arxiv['path']}`")
    lines.append(f"- doc_count: **{arxiv['doc_count']}**")
    lines.append(f"- doi_count: **{arxiv['doi_count']}**")
    lines.append(f"- doi_coverage: **{arxiv['doi_coverage']:.2%}**")
    lines.append(f"- year_range: **{arxiv['year_min']} .. {arxiv['year_max']}**")
    lines.append("")

    canonical = report["canonical_summary"]
    lines.append("## Canonical corpus")
    lines.append(f"- path: `{canonical['path']}`")
    lines.append(f"- doc_count: **{canonical['doc_count']}**")
    lines.append(f"- multisource_docs: **{canonical['multisource_docs']}**")
    lines.append(f"- doi_count: **{canonical['doi_count']}**")
    lines.append("")

    retrieval = report["retrieval_summary"]
    lines.append("## Retrieval manifest")
    lines.append(f"- path: `{retrieval['path']}`")
    lines.append(f"- build_id: `{retrieval['build_id']}`")
    lines.append(f"- corpus_doc_count: **{retrieval['corpus_doc_count']}**")
    lines.append(f"- embedding_model_name: `{retrieval['embedding_model_name']}`")
    lines.append("")

    lines.append("## Source snapshots")
    for source_name, item in report["source_snapshots"].items():
        lines.append(f"- {source_name}: path=`{item['path']}` docs={item['doc_count']}")
    lines.append("")

    incr = report["incremental_merge_summary"]
    lines.append("## Incremental merge report")
    lines.append(f"- available: **{incr['available']}**")
    lines.append(f"- path: `{incr['path']}`")
    if incr["available"]:
        summary = incr.get("summary", {})
        if summary:
            lines.append(f"- summary keys: `{sorted(summary.keys())}`")
    lines.append("")

    lines.append("## Recommendations")
    for item in report["recommendations"]:
        lines.append(f"- [{item['priority']}] {item['action']}: {item['reason']}")
    lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan the next pragmatic incremental refresh cycle after Kaggle bulk seed."
    )
    parser.add_argument(
        "--normalized-root",
        type=Path,
        default=DEFAULT_NORMALIZED_ROOT,
        help="Root directory with normalized source snapshots.",
    )
    parser.add_argument(
        "--canonical-path",
        type=Path,
        default=DEFAULT_RECONCILED_PATH,
        help="Path to canonical corpus JSONL.",
    )
    parser.add_argument(
        "--retrieval-manifest",
        type=Path,
        default=DEFAULT_RETRIEVAL_MANIFEST,
        help="Path to latest retrieval manifest.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Directory where planning reports should be stored.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    normalized_root: Path = args.normalized_root
    reports_dir: Path = args.reports_dir

    arxiv_primary = find_latest_primary_jsonl(normalized_root / "arxiv")
    openalex_primary = find_latest_primary_jsonl(normalized_root / "openalex_alignment")
    semantic_primary = find_latest_primary_jsonl(normalized_root / "semantic_scholar_alignment")
    crossref_primary = find_latest_primary_jsonl(normalized_root / "crossref_alignment")

    arxiv_summary = summarize_arxiv_snapshot(arxiv_primary)
    canonical_summary = summarize_canonical(args.canonical_path)
    retrieval_summary = summarize_retrieval_manifest(args.retrieval_manifest)

    incremental_merge_report = find_latest_incremental_merge_report(Path("artifacts/reports"))
    incremental_merge_summary = summarize_incremental_merge(incremental_merge_report)

    source_snapshots = {
        "arxiv": summarize_generic_jsonl(arxiv_primary),
        "openalex_alignment": summarize_generic_jsonl(openalex_primary),
        "semantic_scholar_alignment": summarize_generic_jsonl(semantic_primary),
        "crossref_alignment": summarize_generic_jsonl(crossref_primary),
    }

    report = {
        "report_name": "plan_incremental_refresh",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "arxiv_primary_snapshot": arxiv_summary,
        "canonical_summary": canonical_summary,
        "retrieval_summary": retrieval_summary,
        "source_snapshots": source_snapshots,
        "incremental_merge_summary": incremental_merge_summary,
        "recommendations": build_recommendations(
            canonical_summary=canonical_summary,
            retrieval_summary=retrieval_summary,
            arxiv_summary=arxiv_summary,
            incremental_merge_summary=incremental_merge_summary,
        ),
    }

    latest_json = reports_dir / "plan_incremental_refresh_latest.json"
    latest_md = reports_dir / "plan_incremental_refresh_latest.md"
    hist_json = reports_dir / "history" / f"plan_incremental_refresh_{run_ts}.json"
    hist_md = reports_dir / "history" / f"plan_incremental_refresh_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] arxiv_doc_count={arxiv_summary['doc_count']}")
    print(f"[OK] arxiv_doi_count={arxiv_summary['doi_count']}")
    print(f"[OK] canonical_doc_count={canonical_summary['doc_count']}")
    print(f"[OK] retrieval_build_id={retrieval_summary['build_id']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()