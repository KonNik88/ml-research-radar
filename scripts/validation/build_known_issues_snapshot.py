from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPORTS_DIR = Path("artifacts/reports")
DEFAULT_VALIDATION_DIR = DEFAULT_REPORTS_DIR / "validation"


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
        raise FileNotFoundError(f"Required JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = d
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def extract_retrieval_findings(retrieval_report: dict[str, Any]) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []

    for query_block in retrieval_report.get("query_runs", []):
        query = query_block.get("query")
        runs = query_block.get("runs", [])

        by_mode: dict[str, dict[str, Any]] = {
            run.get("effective_mode_label", ""): run for run in runs
        }

        entry: dict[str, Any] = {
            "query": query,
            "top_titles": {},
            "timing_ms": {},
        }

        for label, run in by_mode.items():
            results = run.get("results", []) or []
            top_titles = [
                (item.get("document") or {}).get("title")
                for item in results[:5]
                if (item.get("document") or {}).get("title")
            ]
            entry["top_titles"][label] = top_titles
            entry["timing_ms"][label] = {
                "wall": run.get("timing_ms_wall"),
                "service": safe_get(run, "meta", "timing_ms", default={}),
            }

        observations.append(entry)

    return {
        "queries_count": retrieval_report.get("queries_count", 0),
        "group_counts": retrieval_report.get("group_counts", {}),
        "build_id": retrieval_report.get("build_id"),
        "corpus_doc_count": retrieval_report.get("corpus_doc_count"),
        "observations": observations,
    }


def build_issue_list(
    *,
    postpass_report: dict[str, Any],
    retrieval_report: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    corpus_total = safe_get(postpass_report, "corpus_summary", "total_docs", default=0)
    multisource_docs = safe_get(postpass_report, "corpus_summary", "merge_stats", "multi_source_docs", default=0)

    doi_cov = safe_get(postpass_report, "key_field_coverage", "doi", "coverage", default=0.0)
    concepts_cov = safe_get(postpass_report, "key_field_coverage", "concepts", "coverage", default=0.0)
    cited_cov = safe_get(postpass_report, "key_field_coverage", "cited_by_count", "coverage", default=0.0)
    refs_cov = safe_get(postpass_report, "key_field_coverage", "references_count", "coverage", default=0.0)

    empty_authors_count = safe_get(postpass_report, "quality_anomalies", "empty_authors_count", default=0)

    issues.append(
        {
            "id": "corpus_historical_skew",
            "severity": "medium",
            "category": "corpus",
            "title": "Current 30k arXiv backbone is historically skewed",
            "details": (
                "The current medium-scale corpus is technically valid but not yet a recent-balanced "
                "product-like slice. Retrieval on modern ambiguous queries is affected by this."
            ),
        }
    )

    issues.append(
        {
            "id": "doi_enrichment_bias",
            "severity": "high",
            "category": "corpus",
            "title": "Enrichment coverage is concentrated on DOI-covered subset",
            "details": {
                "doi_coverage": doi_cov,
                "concepts_coverage": concepts_cov,
                "cited_by_count_coverage": cited_cov,
                "references_count_coverage": refs_cov,
                "multisource_docs": multisource_docs,
                "canonical_total_docs": corpus_total,
            },
        }
    )

    issues.append(
        {
            "id": "semantic_scholar_rate_limit_sensitivity",
            "severity": "medium",
            "category": "source",
            "title": "Semantic Scholar alignment path remains rate-limit-sensitive",
            "details": (
                "The path is working after retry/backoff improvements, but it should still be treated "
                "as rate-limit-sensitive operationally."
            ),
        }
    )

    issues.append(
        {
            "id": "config_vs_operational_preset_gap",
            "severity": "medium",
            "category": "config",
            "title": "sources.yaml medium_scale profile does not fully match actual 30k thematic preset",
            "details": (
                "The real successful 30k pass used a broader explicit thematic preset than the narrower "
                "medium_scale profile currently encoded in sources.yaml."
            ),
        }
    )

    issues.append(
        {
            "id": "ranking_not_fully_config_driven",
            "severity": "low",
            "category": "ranking",
            "title": "Ranking logic and scoring.yaml are aligned conceptually but not fully config-driven",
            "details": (
                "Weights and signals are close, but ranking implementation should be cleaned up to read "
                "its behaviour directly and consistently from config."
            ),
        }
    )

    issues.append(
        {
            "id": "venue_normalization_debt",
            "severity": "medium",
            "category": "merge",
            "title": "Venue/journal/conference normalization remains an active refinement area",
            "details": (
                "Current merge logic is conservative, but venue-family normalization still remains one of "
                "the clearest technical debt zones."
            ),
        }
    )

    issues.append(
        {
            "id": "license_normalization_debt",
            "severity": "medium",
            "category": "merge",
            "title": "License normalization remains incomplete",
            "details": (
                "Publisher TDM policy URLs and real content licenses still need stricter normalization "
                "and semantics."
            ),
        }
    )

    issues.append(
        {
            "id": "single_empty_authors_case",
            "severity": "low",
            "category": "data_quality",
            "title": "One canonical document currently has empty authors",
            "details": {
                "empty_authors_count": empty_authors_count,
                "empty_authors_ids": safe_get(postpass_report, "quality_anomalies", "empty_authors_ids", default=[]),
            },
        }
    )

    issues.append(
        {
            "id": "retrieval_ambiguous_query_failures",
            "severity": "medium",
            "category": "retrieval",
            "title": "Some ambiguous modern queries produce weak or misleading results",
            "details": (
                "Observed especially on queries like 'transformer language models' and 'diffusion models', "
                "where lexical ambiguity and corpus composition distort retrieval."
            ),
        }
    )

    issues.append(
        {
            "id": "next_engineering_question",
            "severity": "high",
            "category": "planning",
            "title": "Main next engineering question is incremental update strategy after Kaggle seed",
            "details": (
                "The next key step is to define how Kaggle bulk seed, arXiv incremental batches, "
                "selective enrichment, reconcile, export, and retrieval rebuild should work together."
            ),
        }
    )

    return issues


def build_operational_truth(
    *,
    postpass_report: dict[str, Any],
    retrieval_report: dict[str, Any],
) -> dict[str, Any]:
    return {
        "canonical_corpus_doc_count": safe_get(postpass_report, "corpus_summary", "total_docs", default=0),
        "retrieval_build_id": retrieval_report.get("build_id"),
        "retrieval_corpus_doc_count": retrieval_report.get("corpus_doc_count"),
        "multisource_docs": safe_get(postpass_report, "corpus_summary", "merge_stats", "multi_source_docs", default=0),
        "source_distribution": safe_get(postpass_report, "corpus_summary", "source_distribution", default={}),
        "known_empty_authors_count": safe_get(postpass_report, "quality_anomalies", "empty_authors_count", default=0),
        "known_empty_authors_ids": safe_get(postpass_report, "quality_anomalies", "empty_authors_ids", default=[]),
        "active_source_audits": postpass_report.get("source_audit_summary", {}),
        "retrieval_queries_count": retrieval_report.get("queries_count", 0),
    }


def build_next_steps() -> list[dict[str, Any]]:
    return [
        {
            "order": 1,
            "title": "Review retrieval validation results and record concrete good/bad query cases",
        },
        {
            "order": 2,
            "title": "Use post-pass audit findings as fixed operational baseline for current milestone",
        },
        {
            "order": 3,
            "title": "Design pragmatic incremental refresh strategy after Kaggle seed",
        },
        {
            "order": 4,
            "title": "Add selective enrichment flow for new/updated DOI candidates only",
        },
        {
            "order": 5,
            "title": "Only after stabilization, extend corpus coverage and serving/search ergonomics",
        },
    ]


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []

    lines.append("# Known issues snapshot")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append("")

    lines.append("## Operational truth")
    op = report["operational_truth"]
    lines.append(f"- canonical_corpus_doc_count: **{op['canonical_corpus_doc_count']}**")
    lines.append(f"- retrieval_build_id: `{op['retrieval_build_id']}`")
    lines.append(f"- retrieval_corpus_doc_count: **{op['retrieval_corpus_doc_count']}**")
    lines.append(f"- multisource_docs: **{op['multisource_docs']}**")
    lines.append(f"- source_distribution: `{op['source_distribution']}`")
    lines.append(f"- retrieval_queries_count: **{op['retrieval_queries_count']}**")
    lines.append("")

    lines.append("## Known issues")
    for issue in report["known_issues"]:
        lines.append(f"### {issue['id']}")
        lines.append(f"- severity: `{issue['severity']}`")
        lines.append(f"- category: `{issue['category']}`")
        lines.append(f"- title: {issue['title']}")
        details = issue.get("details")
        if isinstance(details, dict):
            lines.append(f"- details: `{details}`")
        elif details is not None:
            lines.append(f"- details: {details}")
        lines.append("")

    lines.append("## Next steps")
    for step in report["next_steps"]:
        lines.append(f"- {step['order']}. {step['title']}")
    lines.append("")

    lines.append("## Retrieval observation samples")
    observations = report["retrieval_findings"].get("observations", [])
    for item in observations[:5]:
        lines.append(f"### Query: `{item['query']}`")
        top_titles = item.get("top_titles", {})
        for mode_label, titles in top_titles.items():
            lines.append(f"- `{mode_label}`:")
            if titles:
                for title in titles[:5]:
                    lines.append(f"  - {title}")
            else:
                lines.append("  - <no results>")
        lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a machine-readable and human-readable known issues snapshot."
    )
    parser.add_argument(
        "--validation-dir",
        type=Path,
        default=DEFAULT_VALIDATION_DIR,
        help="Directory containing validation reports.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_VALIDATION_DIR,
        help="Directory where known issues snapshot should be written.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    validation_dir: Path = args.validation_dir
    output_dir: Path = args.output_dir

    retrieval_report = load_json(validation_dir / "retrieval_checks_latest.json")
    postpass_report = load_json(validation_dir / "postpass_audit_summary_latest.json")

    report = {
        "report_name": "known_issues_snapshot",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "operational_truth": build_operational_truth(
            postpass_report=postpass_report,
            retrieval_report=retrieval_report,
        ),
        "retrieval_findings": extract_retrieval_findings(retrieval_report),
        "known_issues": build_issue_list(
            postpass_report=postpass_report,
            retrieval_report=retrieval_report,
        ),
        "next_steps": build_next_steps(),
    }

    latest_json = output_dir / "known_issues_snapshot_latest.json"
    latest_md = output_dir / "known_issues_snapshot_latest.md"
    hist_json = output_dir / "history" / f"known_issues_snapshot_{run_ts}.json"
    hist_md = output_dir / "history" / f"known_issues_snapshot_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] canonical_corpus_doc_count={report['operational_truth']['canonical_corpus_doc_count']}")
    print(f"[OK] retrieval_build_id={report['operational_truth']['retrieval_build_id']}")
    print(f"[OK] known_issues_count={len(report['known_issues'])}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()