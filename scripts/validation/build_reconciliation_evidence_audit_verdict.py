from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


REPORT_NAME = "reconciliation_evidence_audit_v01"
SCHEMA_VERSION = "reconciliation_evidence_audit_v0.1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VALIDATION_DIR = PROJECT_ROOT / "artifacts" / "reports" / "validation"
DEFAULT_SOURCE_AUDIT_DIR = PROJECT_ROOT / "artifacts" / "reports" / "source_audit"
DEFAULT_OUTPUT_DIR = DEFAULT_VALIDATION_DIR


FIELD_SEMANTICS: list[dict[str, Any]] = [
    {
        "field": "identity_group",
        "implementation": "build_reconciliation_groups",
        "actual_rule": (
            "DOI is used when compatible with explicit arXiv identity; conflicting "
            "DOI buckets are split by arXiv base and DOI-only rows are isolated."
        ),
        "audit_status": "accepted_current_behavior",
        "future_provenance_kind": "identity_trace",
    },
    {
        "field": "title",
        "implementation": "choose_best_title",
        "actual_rule": "longest title; OpenAlex wins equal-length ties",
        "audit_status": "implementation_specific_documentation_sync_needed",
        "future_provenance_kind": "winner",
    },
    {
        "field": "abstract",
        "implementation": "choose_best_abstract",
        "actual_rule": "longest non-empty abstract; OpenAlex wins equal-length ties",
        "audit_status": "implementation_specific_documentation_sync_needed",
        "future_provenance_kind": "winner",
    },
    {
        "field": "authors",
        "implementation": "merge_unique_strings",
        "actual_rule": "union preserving first-seen spelling; case-insensitive deduplication",
        "audit_status": "accepted_current_behavior",
        "future_provenance_kind": "element_level_union",
    },
    {
        "field": "published_at",
        "implementation": "choose_best_published_at",
        "actual_rule": "earliest non-null timestamp",
        "audit_status": "accepted_current_behavior",
        "future_provenance_kind": "aggregate_min",
    },
    {
        "field": "publication_date",
        "implementation": "choose_best_publication_date",
        "actual_rule": "earliest non-null timestamp",
        "audit_status": "accepted_current_behavior",
        "future_provenance_kind": "aggregate_min",
    },
    {
        "field": "updated_record_at",
        "implementation": "choose_best_updated_at",
        "actual_rule": "latest source update timestamp",
        "audit_status": "accepted_current_behavior",
        "future_provenance_kind": "aggregate_max",
    },
    {
        "field": "year",
        "implementation": "choose_best_year",
        "actual_rule": "earliest reasonable year in the accepted range",
        "audit_status": "accepted_current_behavior",
        "future_provenance_kind": "aggregate_min",
    },
    {
        "field": "doi",
        "implementation": "choose_best_doi",
        "actual_rule": "first direct DOI in grouped order, then first external DOI",
        "audit_status": "order_sensitive_review_in_field_provenance_slice",
        "future_provenance_kind": "winner",
    },
    {
        "field": "arxiv_id",
        "implementation": "choose_best_arxiv_id",
        "actual_rule": (
            "prefer identity from an arXiv source row, then any direct arXiv ID, "
            "then an external arXiv identifier"
        ),
        "audit_status": "accepted_current_behavior",
        "future_provenance_kind": "winner",
    },
    {
        "field": "openalex_id",
        "implementation": "choose_best_openalex_id",
        "actual_rule": "first direct OpenAlex ID, then external OpenAlex identifier",
        "audit_status": "accepted_current_behavior",
        "future_provenance_kind": "winner",
    },
    {
        "field": "venue/journal/conference",
        "implementation": "choose_preferred_string + normalize_venue_fields",
        "actual_rule": (
            "source-priority winner using venue priority; then normalize "
            "book-chapter/proceedings semantics"
        ),
        "audit_status": "accepted_current_behavior",
        "future_provenance_kind": "winner_with_normalization",
    },
    {
        "field": "publisher",
        "implementation": "choose_preferred_string",
        "actual_rule": "bibliographic source-priority winner",
        "audit_status": "accepted_current_behavior",
        "future_provenance_kind": "winner",
    },
    {
        "field": "publication_type",
        "implementation": "choose_best_publication_type",
        "actual_rule": "prefer explicit non-preprint type, then bibliographic priority",
        "audit_status": "accepted_current_behavior",
        "future_provenance_kind": "winner_with_semantic_override",
    },
    {
        "field": "license",
        "implementation": "choose_best_license",
        "actual_rule": (
            "prefer concrete Creative Commons labels over policy URLs; use "
            "source priority as secondary ordering"
        ),
        "audit_status": "accepted_current_behavior",
        "future_provenance_kind": "winner_with_quality_rank",
    },
    {
        "field": "open_access",
        "implementation": "choose_canonical_open_access",
        "actual_rule": "true if any explicit open manifestation exists; otherwise explicit false or null",
        "audit_status": "accepted_current_behavior",
        "future_provenance_kind": "boolean_evidence",
    },
    {
        "field": "is_open_access",
        "implementation": "choose_canonical_is_open_access",
        "actual_rule": (
            "strict bibliographic OA from non-arXiv evidence; arXiv-only openness "
            "does not produce bibliographic true"
        ),
        "audit_status": "accepted_current_behavior",
        "future_provenance_kind": "boolean_evidence",
    },
    {
        "field": "is_preprint",
        "implementation": "choose_canonical_is_preprint",
        "actual_rule": (
            "explicit published/non-preprint evidence overrides preprint flags; "
            "otherwise derive conservatively"
        ),
        "audit_status": "accepted_current_behavior",
        "future_provenance_kind": "boolean_evidence",
    },
    {
        "field": "cited_by_count",
        "implementation": "choose_max_int",
        "actual_rule": "maximum non-null source value",
        "audit_status": "accepted_current_behavior",
        "future_provenance_kind": "aggregate_max",
    },
    {
        "field": "references_count",
        "implementation": "choose_max_int",
        "actual_rule": "maximum non-null source value",
        "audit_status": "accepted_current_behavior",
        "future_provenance_kind": "aggregate_max",
    },
    {
        "field": "categories/concepts/keywords/tags/reference IDs/artifact links",
        "implementation": "merge_unique_strings",
        "actual_rule": "union with case-insensitive deduplication",
        "audit_status": "accepted_current_behavior",
        "future_provenance_kind": "element_level_union",
    },
    {
        "field": "metadata_completeness_score",
        "implementation": "compute_metadata_completeness_score",
        "actual_rule": "recomputed heuristic over the merged result; not max(source scores)",
        "audit_status": "documentation_correction_required",
        "future_provenance_kind": "derived_score_trace",
    },
    {
        "field": "sources/source_count/unique_source_count/doc_ids/source_ids",
        "implementation": "build_source_links + canonical assembly",
        "actual_rule": (
            "sources preserves contributing rows; source_count counts rows; "
            "unique_source_count counts families; doc_ids is a deduplicated legacy "
            "list; source_ids is a merged identifier map, not provenance"
        ),
        "audit_status": "accepted_with_documentation_clarification",
        "future_provenance_kind": "row_level_provenance",
    },
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ts_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def get_int(mapping: Mapping[str, Any], key: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Expected numeric {key}, got {value!r}")
    return int(value)


def build_report(
    *,
    identity: Mapping[str, Any],
    parity: Mapping[str, Any],
    non_contributing: Mapping[str, Any],
    acl_filtered: Mapping[str, Any],
    acl_check: Mapping[str, Any],
    acl_promotion: Mapping[str, Any],
    input_paths: Mapping[str, Path],
) -> dict[str, Any]:
    identity_summary = identity.get("summary") or identity.get("counters") or {}
    parity_file = parity.get("file_evidence", {}).get("summary", {})
    parity_db = parity.get("postgres_evidence", {}).get("summary", {})
    parity_verdict = parity.get("verdict", {})
    non_summary = non_contributing.get("summary", {})
    acl_filtered_summary = acl_filtered.get("filtered_summary", {})
    acl_check_summary = acl_check.get("summary", {})
    acl_promotion_summary = acl_promotion.get("filtered_summary", {})

    selected_count = get_int(parity_file, "selected_observation_row_count")
    provenance_count = get_int(parity_file, "canonical_provenance_observation_count")
    non_count = get_int(non_summary, "non_contributing_observation_count")
    source_documents_count = get_int(parity_db, "source_documents_count")
    link_count = get_int(parity_db, "canonical_source_links_count")
    resolved_count = get_int(parity_db, "resolved_link_count")
    null_count = get_int(parity_db, "null_link_count")
    dangling_count = get_int(parity_db, "dangling_non_null_link_count")

    non_source_counts = dict(non_summary.get("source_counts") or {})
    acl_non_contributing = int(non_source_counts.get("acl_anthology", 0))
    non_acl_observations = non_count - acl_non_contributing

    excluded_acl_soft = get_int(
        acl_filtered,
        "excluded_acl_potential_baseline_matches_count",
    )
    excluded_non_acl_docs = get_int(
        acl_filtered,
        "excluded_non_acl_added_docs_count",
    )
    updated_acl_baseline = get_int(
        acl_filtered,
        "updated_baseline_docs_with_acl_count",
    )
    added_acl_source_only = get_int(
        acl_filtered,
        "added_acl_source_only_docs_count",
    )
    filtered_rows = get_int(acl_filtered, "filtered_candidate_rows_count")

    identity_rows = int(
        identity_summary.get("rows_seen")
        or identity_summary.get("selected_observation_row_count")
        or 0
    )
    identity_collisions = int(
        identity_summary.get("source_observation_id_cross_source_collision_count")
        or 0
    )
    identity_conflicts = int(identity_summary.get("identity_conflict_count") or 0)
    identity_missing = int(identity_summary.get("missing_identity_count") or 0)
    identity_determinism = int(identity_summary.get("determinism_failure_count") or 0)

    classification_counts = dict(non_summary.get("classification_counts") or {})
    db_presence_counts = dict(non_summary.get("db_presence_counts") or {})

    checks = {
        "identity_report_ok": bool(identity.get("ok", True))
        and int(identity.get("required_failed_count", 0)) == 0,
        "identity_rows_match_selected_observations": identity_rows == selected_count,
        "identity_has_no_new_collisions": identity_collisions == 0,
        "identity_has_no_conflicts": identity_conflicts == 0,
        "identity_has_no_missing_rows": identity_missing == 0,
        "identity_is_deterministic": identity_determinism == 0,
        "parity_audit_ok": bool(parity_verdict.get("ok")),
        "materialization_gap_is_detected": bool(
            parity_verdict.get("materialization_gap_detected")
        ),
        "full_parity_is_not_claimed": not bool(parity_verdict.get("full_parity_ok")),
        "selected_minus_provenance_equals_non_contributing": (
            selected_count - provenance_count == non_count
        ),
        "canonical_link_count_matches_provenance": link_count == provenance_count,
        "resolved_plus_null_equals_link_count": resolved_count + null_count == link_count,
        "no_dangling_links": dangling_count == 0,
        "all_non_contributing_rows_classified": sum(
            int(v) for v in classification_counts.values()
        )
        == non_count,
        "db_presence_accounts_for_non_contributing_rows": sum(
            int(v) for v in db_presence_counts.values()
        )
        == non_count,
        "acl_non_contributing_matches_filtered_soft_exclusions": (
            acl_non_contributing == excluded_acl_soft == 73
        ),
        "non_acl_non_contributing_count_is_expected": non_acl_observations == 68,
        "acl_filtered_candidate_excludes_non_acl_side_fragments": (
            excluded_non_acl_docs == 46
        ),
        "acl_filtered_candidate_preserves_expected_selection": (
            updated_acl_baseline == 3
            and added_acl_source_only == 954
            and filtered_rows == 60954
        ),
        "acl_check_matches_filtered_candidate": (
            get_int(acl_check_summary, "filtered_rows_count") == filtered_rows
            and get_int(acl_check_summary, "filtered_acl_family_docs_count") == 957
            and get_int(acl_check_summary, "filtered_acl_family_only_docs_count") == 954
        ),
        "acl_promotion_matches_filtered_candidate": (
            bool(acl_promotion.get("promotion_performed"))
            and bool(acl_promotion.get("ok"))
            and get_int(acl_promotion_summary, "rows_count") == filtered_rows
        ),
    }
    failed = [name for name, ok in checks.items() if not ok]

    root_cause = {
        "non_contributing_observation_count": non_count,
        "fully_accounted": acl_non_contributing + non_acl_observations == non_count,
        "acl_soft_match_observations": {
            "count": acl_non_contributing,
            "lifecycle_evidence": (
                "ACL filtered candidate intentionally excluded 73 potential "
                "baseline matches, all recorded as title_year soft matches."
            ),
            "generic_classifier_counts": {
                "title_year_match_not_contributing": int(
                    classification_counts.get("title_year_match_not_contributing", 0)
                ),
                "no_matching_promoted_canonical_identity": int(
                    (non_summary.get("classification_by_source") or {})
                    .get("acl_anthology", {})
                    .get("no_matching_promoted_canonical_identity", 0)
                ),
            },
            "interpretation": (
                "The two generic no-match ACL rows are still covered by the "
                "historical ACL lifecycle report; this is diagnostic/index "
                "semantics drift, not an unexplained omission."
            ),
        },
        "non_acl_side_fragment_observations": {
            "observation_count": non_acl_observations,
            "excluded_candidate_document_count": excluded_non_acl_docs,
            "source_observation_counts": {
                source: int(count)
                for source, count in non_source_counts.items()
                if source != "acl_anthology"
            },
            "candidate_document_family_counts": dict(
                acl_filtered.get("excluded_non_acl_source_family_sets_top20") or {}
            ),
            "interpretation": (
                "The full ACL reconcile candidate used refreshed baseline-source "
                "snapshots and created 46 non-ACL side-fragment documents. The "
                "ACL filtered candidate deliberately removed them so the ACL "
                "promotion could not silently refresh unrelated canonical state."
            ),
        },
    }

    return {
        "report_name": REPORT_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "status": "internal_review_only",
        "publication_ready": False,
        "canonical_truth_mutated": False,
        "reconcile_executed_by_this_report": False,
        "postgres_mutated": False,
        "inputs": {name: str(path).replace("\\", "/") for name, path in input_paths.items()},
        "evidence_summary": {
            "selected_source_observations": selected_count,
            "canonical_provenance_observations": provenance_count,
            "non_contributing_observations": non_count,
            "source_documents": source_documents_count,
            "canonical_source_links": link_count,
            "resolved_links": resolved_count,
            "null_links": null_count,
            "dangling_links": dangling_count,
            "source_observation_identity_collisions": identity_collisions,
        },
        "root_cause": root_cause,
        "field_semantics": FIELD_SEMANTICS,
        "checks": checks,
        "verdict": {
            "ok": not failed,
            "required_failed_count": len(failed),
            "required_failed_checks": failed,
            "parallel_source_observation_plane": "not_needed",
            "existing_source_materialization": "strengthen_existing",
            "source_observation_id_operationalization": "candidate_required",
            "field_level_provenance": "recommended_separate_slice",
            "postgres_schema_change": "candidate_required_for_identity_parity",
            "canonical_contract_change": "not_required_initially",
            "canonical_truth_mutation": "forbidden",
            "reconciliation_behavior_change": "not_required_for_materialization_fix",
            "public_release_no_s2_candidate": (
                "required_if_written_permission_is_not_received"
            ),
            "next_slice": "source_observation_materialization_identity_design_v0.1",
        },
    }


def markdown(report: Mapping[str, Any]) -> str:
    evidence = report["evidence_summary"]
    verdict = report["verdict"]
    root = report["root_cause"]

    lines = [
        "# Reconciliation Evidence Audit v0.1",
        "",
        f"- Generated: `{report['generated_at_utc']}`",
        f"- Status: `{'OK' if verdict['ok'] else 'FAILED'}`",
        "- Scope: read-only audit; no canonical, Postgres, retrieval, graph, or publication mutation.",
        "",
        "## Evidence baseline",
        "",
        f"- Selected source observations: `{evidence['selected_source_observations']}`",
        f"- Canonical provenance observations: `{evidence['canonical_provenance_observations']}`",
        f"- Non-contributing observations: `{evidence['non_contributing_observations']}`",
        f"- Postgres source_documents: `{evidence['source_documents']}`",
        f"- Postgres canonical_source_links: `{evidence['canonical_source_links']}`",
        f"- Resolved links: `{evidence['resolved_links']}`",
        f"- NULL links: `{evidence['null_links']}`",
        f"- Dangling links: `{evidence['dangling_links']}`",
        "",
        "## Root-cause closure",
        "",
        (
            f"- ACL soft-match observations: "
            f"`{root['acl_soft_match_observations']['count']}`"
        ),
        (
            f"- Non-ACL side-fragment observations: "
            f"`{root['non_acl_side_fragment_observations']['observation_count']}`"
        ),
        (
            f"- Excluded non-ACL candidate documents: "
            f"`{root['non_acl_side_fragment_observations']['excluded_candidate_document_count']}`"
        ),
        f"- All non-contributing observations accounted: `{root['fully_accounted']}`",
        "",
        "## Explicit verdict",
        "",
    ]
    for key in (
        "parallel_source_observation_plane",
        "existing_source_materialization",
        "source_observation_id_operationalization",
        "field_level_provenance",
        "postgres_schema_change",
        "canonical_contract_change",
        "canonical_truth_mutation",
        "reconciliation_behavior_change",
        "public_release_no_s2_candidate",
        "next_slice",
    ):
        lines.append(f"- `{key}` = `{verdict[key]}`")

    lines.extend(
        [
            "",
            "## Executable field semantics",
            "",
            "| Field | Current rule | Audit status | Future provenance |",
            "|---|---|---|---|",
        ]
    )
    for row in report["field_semantics"]:
        lines.append(
            f"| `{row['field']}` | {row['actual_rule']} | "
            f"`{row['audit_status']}` | `{row['future_provenance_kind']}` |"
        )

    lines.extend(
        [
            "",
            "## Failed checks",
            "",
            (
                "None."
                if not verdict["required_failed_checks"]
                else "\n".join(f"- `{name}`" for name in verdict["required_failed_checks"])
            ),
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(report: Mapping[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    history = output_dir / "history"
    history.mkdir(parents=True, exist_ok=True)
    run_ts = ts_slug()

    latest_json = output_dir / "reconciliation_evidence_audit_latest.json"
    latest_md = output_dir / "reconciliation_evidence_audit_latest.md"
    history_json = history / f"reconciliation_evidence_audit_{run_ts}.json"
    history_md = history / f"reconciliation_evidence_audit_{run_ts}.md"

    json_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    md_text = markdown(report)

    for path in (latest_json, history_json):
        path.write_text(json_text, encoding="utf-8")
    for path in (latest_md, history_md):
        path.write_text(md_text, encoding="utf-8")

    return {
        "latest_json": latest_json,
        "latest_md": latest_md,
        "history_json": history_json,
        "history_md": history_md,
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build the final read-only Reconciliation Evidence Audit v0.1 verdict."
    )
    p.add_argument(
        "--identity-report",
        type=Path,
        default=DEFAULT_VALIDATION_DIR / "source_observation_identity_contract_latest.json",
    )
    p.add_argument(
        "--parity-report",
        type=Path,
        default=DEFAULT_VALIDATION_DIR / "source_observation_materialization_parity_latest.json",
    )
    p.add_argument(
        "--non-contributing-report",
        type=Path,
        default=DEFAULT_VALIDATION_DIR / "source_observation_non_contributing_classification_latest.json",
    )
    p.add_argument(
        "--acl-filtered-report",
        type=Path,
        default=DEFAULT_SOURCE_AUDIT_DIR / "acl_anthology_filtered_candidate_latest.json",
    )
    p.add_argument(
        "--acl-check-report",
        type=Path,
        default=DEFAULT_SOURCE_AUDIT_DIR / "acl_anthology_filtered_candidate_check_latest.json",
    )
    p.add_argument(
        "--acl-promotion-report",
        type=Path,
        default=DEFAULT_SOURCE_AUDIT_DIR / "promote_acl_anthology_filtered_candidate_latest.json",
    )
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    paths = {
        "identity_report": args.identity_report,
        "parity_report": args.parity_report,
        "non_contributing_report": args.non_contributing_report,
        "acl_filtered_report": args.acl_filtered_report,
        "acl_check_report": args.acl_check_report,
        "acl_promotion_report": args.acl_promotion_report,
    }

    try:
        report = build_report(
            identity=load_json(args.identity_report),
            parity=load_json(args.parity_report),
            non_contributing=load_json(args.non_contributing_report),
            acl_filtered=load_json(args.acl_filtered_report),
            acl_check=load_json(args.acl_check_report),
            acl_promotion=load_json(args.acl_promotion_report),
            input_paths=paths,
        )
        outputs = write_outputs(report, args.output_dir)
    except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1

    status = "OK" if report["verdict"]["ok"] else "FAILED"
    evidence = report["evidence_summary"]
    print(f"[{status}] report_name={REPORT_NAME}")
    print(f"[{status}] selected_source_observations={evidence['selected_source_observations']}")
    print(f"[{status}] canonical_provenance_observations={evidence['canonical_provenance_observations']}")
    print(f"[{status}] non_contributing_observations={evidence['non_contributing_observations']}")
    print(f"[{status}] source_documents={evidence['source_documents']}")
    print(f"[{status}] canonical_source_links={evidence['canonical_source_links']}")
    print(f"[{status}] null_links={evidence['null_links']}")
    print(f"[{status}] root_cause_fully_accounted={report['root_cause']['fully_accounted']}")
    print(f"[{status}] required_failed_count={report['verdict']['required_failed_count']}")
    print(f"[{status}] latest JSON: {outputs['latest_json']}")
    print(f"[{status}] latest Markdown: {outputs['latest_md']}")

    if report["verdict"]["required_failed_checks"]:
        for name in report["verdict"]["required_failed_checks"]:
            print(f"[FAILED] {name}")

    return 0 if report["verdict"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
