from __future__ import annotations

from pathlib import Path

from scripts.validation.build_reconciliation_evidence_audit_verdict import (
    FIELD_SEMANTICS,
    build_report,
)


def _identity() -> dict:
    return {
        "ok": True,
        "required_failed_count": 0,
        "summary": {
            "rows_seen": 88178,
            "source_observation_id_cross_source_collision_count": 0,
            "identity_conflict_count": 0,
            "missing_identity_count": 0,
            "determinism_failure_count": 0,
        },
    }


def _parity() -> dict:
    return {
        "file_evidence": {
            "summary": {
                "selected_observation_row_count": 88178,
                "canonical_provenance_observation_count": 88037,
            }
        },
        "postgres_evidence": {
            "summary": {
                "source_documents_count": 70244,
                "canonical_source_links_count": 88037,
                "resolved_link_count": 70145,
                "null_link_count": 17892,
                "dangling_non_null_link_count": 0,
            }
        },
        "verdict": {
            "ok": True,
            "materialization_gap_detected": True,
            "full_parity_ok": False,
        },
    }


def _non_contributing() -> dict:
    return {
        "summary": {
            "non_contributing_observation_count": 141,
            "source_counts": {
                "acl_anthology": 73,
                "crossref": 24,
                "openalex": 24,
                "semantic_scholar": 20,
            },
            "classification_counts": {
                "ambiguous_strong_identity_match": 8,
                "no_matching_promoted_canonical_identity": 4,
                "strong_identity_match_not_contributing": 58,
                "title_year_match_not_contributing": 71,
            },
            "classification_by_source": {
                "acl_anthology": {
                    "no_matching_promoted_canonical_identity": 2,
                    "title_year_match_not_contributing": 71,
                }
            },
            "db_presence_counts": {"materialized": 99, "missing": 42},
        }
    }


def _acl_filtered() -> dict:
    return {
        "excluded_acl_potential_baseline_matches_count": 73,
        "excluded_non_acl_added_docs_count": 46,
        "excluded_non_acl_source_family_sets_top20": {
            "arxiv+semantic_scholar": 20,
            "crossref+openalex": 22,
            "crossref": 2,
            "openalex": 2,
        },
        "updated_baseline_docs_with_acl_count": 3,
        "added_acl_source_only_docs_count": 954,
        "filtered_candidate_rows_count": 60954,
        "filtered_summary": {
            "rows_count": 60954,
            "acl_family_docs_count": 957,
            "acl_family_only_docs_count": 954,
        },
    }


def _acl_check() -> dict:
    return {
        "summary": {
            "filtered_rows_count": 60954,
            "filtered_acl_family_docs_count": 957,
            "filtered_acl_family_only_docs_count": 954,
        }
    }


def _acl_promotion() -> dict:
    return {
        "ok": True,
        "promotion_performed": True,
        "filtered_summary": {"rows_count": 60954},
    }


def _paths() -> dict[str, Path]:
    return {
        "identity_report": Path("identity.json"),
        "parity_report": Path("parity.json"),
        "non_contributing_report": Path("non.json"),
        "acl_filtered_report": Path("acl_filtered.json"),
        "acl_check_report": Path("acl_check.json"),
        "acl_promotion_report": Path("acl_promotion.json"),
    }


def test_build_report_closes_all_root_causes() -> None:
    report = build_report(
        identity=_identity(),
        parity=_parity(),
        non_contributing=_non_contributing(),
        acl_filtered=_acl_filtered(),
        acl_check=_acl_check(),
        acl_promotion=_acl_promotion(),
        input_paths=_paths(),
    )

    assert report["verdict"]["ok"] is True
    assert report["root_cause"]["fully_accounted"] is True
    assert (
        report["verdict"]["existing_source_materialization"]
        == "strengthen_existing"
    )
    assert report["verdict"]["parallel_source_observation_plane"] == "not_needed"
    assert report["verdict"]["next_slice"] == (
        "source_observation_materialization_identity_design_v0.1"
    )


def test_report_detects_count_mismatch() -> None:
    bad = _non_contributing()
    bad["summary"]["non_contributing_observation_count"] = 140

    report = build_report(
        identity=_identity(),
        parity=_parity(),
        non_contributing=bad,
        acl_filtered=_acl_filtered(),
        acl_check=_acl_check(),
        acl_promotion=_acl_promotion(),
        input_paths=_paths(),
    )

    assert report["verdict"]["ok"] is False
    assert (
        "selected_minus_provenance_equals_non_contributing"
        in report["verdict"]["required_failed_checks"]
    )


def test_field_semantics_records_current_executable_rules() -> None:
    by_field = {row["field"]: row for row in FIELD_SEMANTICS}

    assert by_field["title"]["actual_rule"] == (
        "longest title; OpenAlex wins equal-length ties"
    )
    assert "recomputed heuristic" in by_field["metadata_completeness_score"][
        "actual_rule"
    ]
    assert by_field["authors"]["future_provenance_kind"] == "element_level_union"


def test_report_preserves_canonical_and_reconcile_boundaries() -> None:
    report = build_report(
        identity=_identity(),
        parity=_parity(),
        non_contributing=_non_contributing(),
        acl_filtered=_acl_filtered(),
        acl_check=_acl_check(),
        acl_promotion=_acl_promotion(),
        input_paths=_paths(),
    )

    assert report["canonical_truth_mutated"] is False
    assert report["reconcile_executed_by_this_report"] is False
    assert report["postgres_mutated"] is False
    assert report["verdict"]["canonical_truth_mutation"] == "forbidden"
