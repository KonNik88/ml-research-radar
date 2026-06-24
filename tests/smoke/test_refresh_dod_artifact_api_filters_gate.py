from __future__ import annotations

from pathlib import Path

from scripts.update import check_refresh_definition_of_done as dod


def _sample_artifact_api_filters_report() -> dict[str, object]:
    return {
        "report_name": "artifact_api_filters_check",
        "summary": {
            "runtime_backend_mode": "db",
            "runtime_ready": True,
            "runtime_db_connected": True,
            "artifacts_provider_github_total": 5953,
            "artifacts_github_status_found_total": 5339,
            "language_filter_value": "Python",
            "language_total": 100,
            "min_stars_threshold": 10,
            "pushed_after_threshold": "2026-01-01T00:00:00Z",
            "updated_before_threshold": "2026-05-01T00:00:00Z",
            "artifact_id": "artifact_1",
            "canonical_id": "paper_1",
            "documents_has_trusted_artifact_total": 10,
            "documents_artifact_provider_github_total": 9,
        },
        "checks": {
            "runtime_endpoint_ok": True,
            "runtime_db_ready": True,
            "artifacts_provider_github_endpoint_ok": True,
            "artifacts_provider_github_results_non_empty": True,
            "artifacts_provider_github_rows_match": True,
            "artifacts_has_github_metadata_endpoint_ok": True,
            "artifacts_has_github_metadata_rows_match": True,
            "artifacts_github_status_found_endpoint_ok": True,
            "artifacts_github_status_found_rows_match": True,
            "artifacts_stars_desc_endpoint_ok": True,
            "artifacts_stars_desc_sorted": True,
            "artifacts_forks_desc_endpoint_ok": True,
            "artifacts_forks_desc_sorted": True,
            "artifacts_min_stars_endpoint_ok": True,
            "artifacts_min_stars_rows_match": True,
            "artifacts_min_stars_sorted": True,
            "artifacts_language_value_resolved": True,
            "artifacts_language_endpoint_ok": True,
            "artifacts_language_rows_match": True,
            "artifacts_archived_false_endpoint_ok": True,
            "artifacts_archived_false_rows_match": True,
            "artifacts_pushed_desc_endpoint_ok": True,
            "artifacts_pushed_desc_values_present": True,
            "artifacts_pushed_desc_sorted": True,
            "artifacts_pushed_after_threshold_resolved": True,
            "artifacts_pushed_after_endpoint_ok": True,
            "artifacts_pushed_after_rows_match": True,
            "artifacts_pushed_after_sorted": True,
            "artifacts_updated_desc_endpoint_ok": True,
            "artifacts_updated_desc_values_present": True,
            "artifacts_updated_desc_sorted": True,
            "artifacts_updated_before_threshold_resolved": True,
            "artifacts_updated_before_endpoint_ok": True,
            "artifacts_updated_before_rows_match": True,
            "artifacts_updated_before_sorted": True,
            "artifacts_pushed_invalid_range_returns_400": True,
            "artifacts_updated_invalid_range_returns_400": True,
            "artifact_detail_endpoint_ok": True,
            "artifact_detail_found": True,
            "artifact_linked_papers_endpoint_ok": True,
            "artifact_linked_papers_rows_match": True,
            "documents_has_trusted_artifact_endpoint_ok": True,
            "documents_has_trusted_artifact_results_non_empty": True,
            "documents_artifact_provider_github_endpoint_ok": True,
            "documents_artifact_provider_github_results_non_empty": True,
            "document_artifacts_endpoint_ok": True,
            "document_artifacts_results_non_empty": True,
            "document_artifacts_rows_match": True,
        },
        "verdict": {
            "ok": True,
            "required_failed_count": 0,
            "required_failed_checks": [],
        },
    }


def test_extract_artifact_api_filters_values() -> None:
    values = dod.extract_artifact_api_filters_values(
        _sample_artifact_api_filters_report()
    )

    assert values["artifact_api_filters_check_ok"] is True
    assert values["artifact_api_filters_required_failed_count"] == 0
    assert values["artifact_api_filters_runtime_backend_mode"] == "db"
    assert values["artifact_api_filters_provider_github_total"] == 5953
    assert values["artifact_api_filters_runtime_db_ready"] is True
    assert values["artifact_api_filters_pushed_desc_sorted"] is True
    assert values["artifact_api_filters_updated_before_rows_match"] is True
    assert values["artifact_api_filters_document_artifacts_rows_match"] is True


def test_parser_accepts_artifact_api_filters_gate() -> None:
    parser = dod.build_parser()
    args = parser.parse_args(
        [
            "--artifact-api-filters-check-path",
            "custom/artifact_api_filters.json",
            "--require-artifact-api-filters",
        ]
    )

    assert args.artifact_api_filters_check_path == Path(
        "custom/artifact_api_filters.json"
    )
    assert args.require_artifact_api_filters is True
