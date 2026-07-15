from __future__ import annotations

import argparse
from pathlib import Path

from scripts.validation.check_citation_graph_api_regression import (
    DEFAULT_API_REFERENCE_PATH,
    DEFAULT_APP_PATH,
    DEFAULT_ARCHITECTURE_PATH,
    DEFAULT_PROJECT_STATE_PATH,
    DEFAULT_REFRESH_CONTRACT_PATH,
    DEFAULT_RELOAD_TEST_PATH,
    DEFAULT_GRAPH_RELOAD_TEST_PATH,
    DEFAULT_FAILURE_ISOLATION_TEST_PATH,
    DEFAULT_ROADMAP_PATH,
    DEFAULT_SCHEMAS_PATH,
    DEFAULT_SERVICE_PATH,
    DEFAULT_STATUS_TEST_PATH,
    DEFAULT_STORE_PATH,
    DEFAULT_STORE_TEST_PATH,
    DEFAULT_TRAVERSAL_TEST_PATH,
    build_report,
    missing_snippets,
    present_forbidden_snippets,
)


def _args(tmp_path: Path, *, skip_docs: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        app_path=DEFAULT_APP_PATH,
        store_path=DEFAULT_STORE_PATH,
        service_path=DEFAULT_SERVICE_PATH,
        schemas_path=DEFAULT_SCHEMAS_PATH,
        api_reference_path=DEFAULT_API_REFERENCE_PATH,
        architecture_path=DEFAULT_ARCHITECTURE_PATH,
        project_state_path=DEFAULT_PROJECT_STATE_PATH,
        roadmap_path=DEFAULT_ROADMAP_PATH,
        refresh_contract_path=DEFAULT_REFRESH_CONTRACT_PATH,
        status_test_path=DEFAULT_STATUS_TEST_PATH,
        traversal_test_path=DEFAULT_TRAVERSAL_TEST_PATH,
        store_test_path=DEFAULT_STORE_TEST_PATH,
        reload_test_path=DEFAULT_RELOAD_TEST_PATH,
        graph_reload_test_path=DEFAULT_GRAPH_RELOAD_TEST_PATH,
        failure_isolation_test_path=DEFAULT_FAILURE_ISOLATION_TEST_PATH,
        output_dir=tmp_path,
        skip_docs=skip_docs,
        strict=True,
    )


def test_citation_graph_api_regression_current_repo_is_green(tmp_path):
    report = build_report(_args(tmp_path))

    assert report["schema_version"] == "citation_graph_api_regression_v1"
    assert report["summary"]["routes_count"] == 7
    assert report["summary"]["traversal_routes_count"] == 6
    assert report["verdict"]["ok"] is True
    assert report["verdict"]["required_failed_count"] == 0
    assert report["verdict"]["runtime_loader_implemented"] is False
    assert report["verdict"]["publication_ready"] is False
    assert report["verdict"]["manual_review_required"] is True
    assert report["verdict"]["cache_reload_regression_ready"] is True
    assert report["verdict"]["failure_isolation_regression_ready"] is True
    assert report["checks"]["graph_store_cache_bounded_by_graph_root"] is True
    assert report["checks"]["graph_store_cache_clear_on_reload"] is True
    assert report["checks"]["graph_store_cache_clear_precedes_runtime_reload"] is True
    assert report["checks"][
        "graph_reload_tests_cover_cache_and_no_mutation_contract"
    ] is True
    assert report["checks"][
        "graph_store_oserror_is_graph_scoped_for_all_traversal_routes"
    ] is True
    assert report["checks"][
        "failure_isolation_tests_cover_errors_health_and_recovery"
    ] is True
    assert report["checks"][
        "docs_failure_isolation_checkpoint_synced"
    ] is True
    assert report["checks"][
        "docs_failure_isolation_contract_markers_present"
    ] is True


def test_citation_graph_api_regression_can_skip_docs(tmp_path):
    report = build_report(_args(tmp_path, skip_docs=True))

    assert report["verdict"]["ok"] is True
    assert report["checks"]["docs_checks_skipped"] is True


def test_snippet_helpers_detect_missing_and_forbidden_text():
    text = "alpha beta gamma"

    assert missing_snippets(text, ["alpha", "delta"]) == ["delta"]
    assert present_forbidden_snippets(text, ["beta", "omega"]) == ["beta"]
