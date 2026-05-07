from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPORTS_DIR = Path("artifacts/reports")
DEFAULT_VALIDATION_DIR = DEFAULT_REPORTS_DIR / "validation"
DEFAULT_SOURCE_AUDIT_DIR = DEFAULT_REPORTS_DIR / "source_audit"
DEFAULT_CANONICAL_CONTRACT_PATH = DEFAULT_VALIDATION_DIR / "canonical_contract_latest.json"


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


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return load_json(path)


def safe_get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = d
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def first_present(
    data: dict[str, Any],
    paths: list[tuple[str, ...]],
    default: Any = None,
) -> Any:
    for path in paths:
        val = safe_get(data, *path, default=None)
        if val is not None:
            return val
    return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def report_ok(report: dict[str, Any] | None) -> bool:
    if report is None:
        return False

    if "ok" in report:
        return bool(report.get("ok"))

    verdict_ok = safe_get(report, "verdict", "ok", default=None)
    if verdict_ok is not None:
        return bool(verdict_ok)

    dod_passed = safe_get(report, "verdict", "dod_passed", default=None)
    if dod_passed is not None:
        return bool(dod_passed)

    required_failed_count = first_present(
        report,
        [
            ("required_failed_count",),
            ("verdict", "required_failed_count"),
        ],
        default=None,
    )
    if required_failed_count is not None:
        return safe_int(required_failed_count, default=999999) == 0

    return False


def compact_report_summary(path: Path, report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    verdict = report.get("verdict") if isinstance(report.get("verdict"), dict) else {}

    rows_count = first_present(
        report,
        [
            ("rows_count",),
            ("documents_count",),
            ("doc_count",),
            ("source_docs_count",),
            ("normalized_docs_count",),
            ("summary", "rows_count"),
            ("summary", "documents_count"),
            ("summary", "doc_count"),
            ("summary", "source_docs_count"),
            ("summary", "normalized_docs_count"),
        ],
        default=None,
    )

    return {
        "path": normalize_path(path),
        "report_name": report.get("report_name"),
        "generated_at_utc": report.get("generated_at_utc"),
        "run_ts": report.get("run_ts"),
        "ok": report_ok(report),
        "required_failed_count": first_present(
            report,
            [
                ("required_failed_count",),
                ("verdict", "required_failed_count"),
            ],
            default=None,
        ),
        "rows_count": rows_count,
        "summary_keys": sorted(summary.keys()) if isinstance(summary, dict) else [],
        "verdict_keys": sorted(verdict.keys()) if isinstance(verdict, dict) else [],
    }


def classify_acl_report(path: Path, report: dict[str, Any]) -> str:
    name = path.name.lower()
    report_name = str(report.get("report_name") or "").lower()

    text = f"{name} {report_name}"

    if "source_quality" in text or "quality" in text:
        return "source_quality"
    if "canonical_impact" in text or "impact" in text:
        return "canonical_impact"
    if "filtered_candidate" in text and "check" in text:
        return "filtered_candidate_check"
    if "filtered_candidate" in text:
        return "filtered_candidate"
    if "promotion" in text or "promote" in text:
        return "promotion"
    if "reconcile" in text:
        return "reconcile_candidate"
    if "ingest" in text:
        return "ingest"

    return report_name or path.stem


def collect_acl_source_audit_summary(source_audit_dir: Path) -> dict[str, Any]:
    if not source_audit_dir.exists():
        return {
            "source": "acl_anthology",
            "source_audit_dir": normalize_path(source_audit_dir),
            "reports_found_count": 0,
            "reports": {},
            "ok": False,
            "note": "source_audit_dir does not exist",
        }

    paths: list[Path] = []
    for pattern in (
        "*acl_anthology*latest.json",
        "acl*latest.json",
        "*acl*anthology*latest.json",
    ):
        paths.extend(source_audit_dir.glob(pattern))

    unique_paths = sorted({p.resolve(): p for p in paths}.values(), key=lambda p: p.name)

    reports: dict[str, Any] = {}
    report_ok_values: list[bool] = []

    for path in unique_paths:
        try:
            payload = load_json(path)
        except Exception as exc:
            reports[path.stem] = {
                "path": normalize_path(path),
                "ok": False,
                "error": str(exc),
            }
            report_ok_values.append(False)
            continue

        key = classify_acl_report(path, payload)
        compact = compact_report_summary(path, payload)

        # Avoid accidental overwrite when several files map to the same semantic bucket.
        if key in reports:
            suffix = 2
            new_key = f"{key}_{suffix}"
            while new_key in reports:
                suffix += 1
                new_key = f"{key}_{suffix}"
            key = new_key

        reports[key] = compact
        report_ok_values.append(bool(compact["ok"]))

    required_report_keys = [
        "source_quality",
        "canonical_impact",
        "filtered_candidate_check",
    ]
    required_reports_present = all(key in reports for key in required_report_keys)

    # ACL source audit is considered visible if at least one ACL report is found.
    # It is considered fully OK when the key post-ACL reports are present and OK.
    required_reports_ok = all(
        bool(reports.get(key, {}).get("ok")) for key in required_report_keys
    )

    return {
        "source": "acl_anthology",
        "source_audit_dir": normalize_path(source_audit_dir),
        "reports_found_count": len(reports),
        "required_report_keys": required_report_keys,
        "required_reports_present": required_reports_present,
        "required_reports_ok": required_reports_ok,
        "ok": len(reports) > 0 and required_reports_present and required_reports_ok,
        "reports": reports,
    }


def extract_canonical_contract_summary(
    canonical_contract_report: dict[str, Any] | None,
    *,
    canonical_contract_path: Path,
) -> dict[str, Any]:
    report = canonical_contract_report or {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    verdict = report.get("verdict") if isinstance(report.get("verdict"), dict) else {}

    return {
        "path": normalize_path(canonical_contract_path),
        "exists": canonical_contract_report is not None,
        "ok": report_ok(canonical_contract_report),
        "rows_count": summary.get("rows_count"),
        "valid_rows_count": summary.get("valid_rows_count"),
        "bad_rows_count": summary.get("bad_rows_count"),
        "extra_fields_count": summary.get("extra_fields_count"),
        "extra_field_rows_count": summary.get("extra_field_rows_count"),
        "missing_canonical_id_count": summary.get("missing_canonical_id_count"),
        "duplicate_canonical_id_count": summary.get("duplicate_canonical_id_count"),
        "duplicate_doc_id_values_across_canonical_count": summary.get(
            "duplicate_doc_id_values_across_canonical_count"
        ),
        "required_failed_count": verdict.get("required_failed_count"),
        "required_failed_checks": verdict.get("required_failed_checks"),
    }


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
    acl_source_audit_summary: dict[str, Any],
    canonical_contract_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    corpus_total = safe_get(postpass_report, "corpus_summary", "total_docs", default=0)
    multisource_docs = safe_get(
        postpass_report,
        "corpus_summary",
        "merge_stats",
        "multi_source_docs",
        default=0,
    )

    doi_cov = safe_get(postpass_report, "key_field_coverage", "doi", "coverage", default=0.0)
    concepts_cov = safe_get(
        postpass_report, "key_field_coverage", "concepts", "coverage", default=0.0
    )
    cited_cov = safe_get(
        postpass_report,
        "key_field_coverage",
        "cited_by_count",
        "coverage",
        default=0.0,
    )
    refs_cov = safe_get(
        postpass_report,
        "key_field_coverage",
        "references_count",
        "coverage",
        default=0.0,
    )

    empty_authors_count = safe_get(
        postpass_report, "quality_anomalies", "empty_authors_count", default=0
    )

    issues.append(
        {
            "id": "corpus_composition_and_temporal_bias",
            "severity": "medium",
            "category": "corpus",
            "title": "Current 60k+ corpus is operationally green but still composition-sensitive",
            "details": (
                "The current corpus is technically valid and includes a stable arXiv backbone plus "
                "ACL Anthology expansion, but retrieval on modern ambiguous queries can still be "
                "affected by corpus composition, source coverage, and temporal/topic distribution."
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
            "title": "Configured source/corpus presets need sync with the current operational 60k+ state",
            "details": (
                "The successful operational corpus has evolved through Kaggle arXiv backbone selection, "
                "alignment snapshots, ACL Anthology promotion, artifact enrichment, and green DoD. "
                "configs/sources.yaml and related docs should explicitly reflect the current working "
                "preset rather than older 30k-era assumptions."
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
                "empty_authors_ids": safe_get(
                    postpass_report,
                    "quality_anomalies",
                    "empty_authors_ids",
                    default=[],
                ),
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
            "id": "source_documents_materialization_semantics",
            "severity": "medium",
            "category": "serving",
            "title": "Postgres source_documents counts should not be interpreted as full source snapshot coverage for every source",
            "details": (
                "For some alignment sources, canonical_source_links is currently more representative "
                "of source coverage than source_documents table counts. This is a materialization/reporting "
                "semantics issue, not necessarily a source integration failure."
            ),
        }
    )

    issues.append(
        {
            "id": "next_engineering_question",
            "severity": "high",
            "category": "planning",
            "title": "Main next engineering question is feature-ready foundation after post-ACL hardening",
            "details": (
                "After canonical contract gating and source audit sync, the next high-value step is "
                "building paper_features v1 and simple rule-based scores before adding more sources."
            ),
        }
    )

    if not canonical_contract_summary.get("ok"):
        issues.append(
            {
                "id": "canonical_contract_not_green",
                "severity": "critical",
                "category": "contract",
                "title": "Canonical contract report is missing or not green",
                "details": canonical_contract_summary,
            }
        )

    if not acl_source_audit_summary.get("reports_found_count"):
        issues.append(
            {
                "id": "acl_source_audit_reports_missing_from_summary",
                "severity": "medium",
                "category": "reporting",
                "title": "ACL Anthology source audit reports were not found by known issues snapshot builder",
                "details": acl_source_audit_summary,
            }
        )
    elif not acl_source_audit_summary.get("ok"):
        issues.append(
            {
                "id": "acl_source_audit_summary_incomplete",
                "severity": "medium",
                "category": "reporting",
                "title": "ACL Anthology source audit reports are visible but incomplete or not fully green",
                "details": acl_source_audit_summary,
            }
        )

    return issues


def build_active_source_audits(
    *,
    postpass_report: dict[str, Any],
    source_audit_dir: Path,
) -> dict[str, Any]:
    active_source_audits = postpass_report.get("source_audit_summary", {})
    if not isinstance(active_source_audits, dict):
        active_source_audits = {}

    active_source_audits = dict(active_source_audits)
    acl_summary = collect_acl_source_audit_summary(source_audit_dir)

    if acl_summary.get("reports_found_count", 0) > 0:
        active_source_audits["acl_anthology"] = acl_summary

    return active_source_audits


def build_operational_truth(
    *,
    postpass_report: dict[str, Any],
    retrieval_report: dict[str, Any],
    source_audit_dir: Path,
    canonical_contract_summary: dict[str, Any],
) -> dict[str, Any]:
    active_source_audits = build_active_source_audits(
        postpass_report=postpass_report,
        source_audit_dir=source_audit_dir,
    )

    return {
        "canonical_corpus_doc_count": safe_get(
            postpass_report, "corpus_summary", "total_docs", default=0
        ),
        "retrieval_build_id": retrieval_report.get("build_id"),
        "retrieval_corpus_doc_count": retrieval_report.get("corpus_doc_count"),
        "multisource_docs": safe_get(
            postpass_report,
            "corpus_summary",
            "merge_stats",
            "multi_source_docs",
            default=0,
        ),
        "source_distribution": safe_get(
            postpass_report,
            "corpus_summary",
            "source_distribution",
            default={},
        ),
        "known_empty_authors_count": safe_get(
            postpass_report, "quality_anomalies", "empty_authors_count", default=0
        ),
        "known_empty_authors_ids": safe_get(
            postpass_report, "quality_anomalies", "empty_authors_ids", default=[]
        ),
        "active_source_audits": active_source_audits,
        "active_source_audits_sources": sorted(active_source_audits.keys()),
        "canonical_contract": canonical_contract_summary,
        "retrieval_queries_count": retrieval_report.get("queries_count", 0),
    }


def build_next_steps() -> list[dict[str, Any]]:
    return [
        {
            "order": 1,
            "title": "Commit post-ACL hardening after canonical contract and DoD gates are green",
        },
        {
            "order": 2,
            "title": "Use post-pass audit and known issues snapshot as fixed operational baseline for current milestone",
        },
        {
            "order": 3,
            "title": "Design paper_features v1 as a file-first derived feature layer over canonical/artifact/enrichment files",
        },
        {
            "order": 4,
            "title": "Add simple rule-based implementation_readiness_score and radar_score v1",
        },
        {
            "order": 5,
            "title": "Only then choose the next source by functional value: OpenReview signal layer or ACL expansion",
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
    lines.append(f"- active_source_audits_sources: `{op['active_source_audits_sources']}`")
    lines.append(f"- retrieval_queries_count: **{op['retrieval_queries_count']}**")
    lines.append("")

    lines.append("## Canonical contract")
    for key, value in op.get("canonical_contract", {}).items():
        lines.append(f"- {key}: `{value}`")
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
        "--source-audit-dir",
        type=Path,
        default=DEFAULT_SOURCE_AUDIT_DIR,
        help="Directory containing source audit reports.",
    )
    parser.add_argument(
        "--canonical-contract-path",
        type=Path,
        default=DEFAULT_CANONICAL_CONTRACT_PATH,
        help="Canonical contract validation report path.",
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
    canonical_contract_report = load_json_if_exists(args.canonical_contract_path)

    canonical_contract_summary = extract_canonical_contract_summary(
        canonical_contract_report,
        canonical_contract_path=args.canonical_contract_path,
    )
    acl_source_audit_summary = collect_acl_source_audit_summary(args.source_audit_dir)

    report = {
        "report_name": "known_issues_snapshot",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "inputs": {
            "validation_dir": normalize_path(args.validation_dir),
            "source_audit_dir": normalize_path(args.source_audit_dir),
            "canonical_contract_path": normalize_path(args.canonical_contract_path),
            "output_dir": normalize_path(args.output_dir),
        },
        "operational_truth": build_operational_truth(
            postpass_report=postpass_report,
            retrieval_report=retrieval_report,
            source_audit_dir=args.source_audit_dir,
            canonical_contract_summary=canonical_contract_summary,
        ),
        "source_audit_findings": {
            "acl_anthology": acl_source_audit_summary,
        },
        "retrieval_findings": extract_retrieval_findings(retrieval_report),
        "known_issues": build_issue_list(
            postpass_report=postpass_report,
            retrieval_report=retrieval_report,
            acl_source_audit_summary=acl_source_audit_summary,
            canonical_contract_summary=canonical_contract_summary,
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

    op = report["operational_truth"]

    print(f"[OK] canonical_corpus_doc_count={op['canonical_corpus_doc_count']}")
    print(f"[OK] retrieval_build_id={op['retrieval_build_id']}")
    print(f"[OK] canonical_contract_ok={op['canonical_contract']['ok']}")
    print(f"[OK] active_source_audits_sources={op['active_source_audits_sources']}")
    print(
        f"[OK] acl_source_audit_reports_found_count="
        f"{acl_source_audit_summary['reports_found_count']}"
    )
    print(f"[OK] acl_source_audit_ok={acl_source_audit_summary['ok']}")
    print(f"[OK] known_issues_count={len(report['known_issues'])}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()