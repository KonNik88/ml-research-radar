from __future__ import annotations

from scripts.update import check_refresh_definition_of_done as dod


def test_citation_graph_api_regression_values_green_report():
    report = {
        "schema_version": "citation_graph_api_regression_v1",
        "summary": {
            "ok": True,
            "required_failed_count": 0,
            "routes_count": 7,
            "traversal_routes_count": 6,
            "checks_count": 42,
        },
        "verdict": {
            "ok": True,
            "required_failed_count": 0,
            "required_failed_checks": [],
            "citation_graph_api_regression_ready": True,
            "current_graph_routes_checkpointed": True,
            "runtime_loader_implemented": False,
            "publication_ready": False,
            "manual_review_required": True,
        },
    }

    values = dod.extract_citation_graph_api_regression_values(report)

    assert values["citation_graph_api_regression_check_ok"] is True
    assert values["citation_graph_api_regression_schema_version"] == (
        "citation_graph_api_regression_v1"
    )
    assert values["citation_graph_api_regression_required_failed_count"] == 0
    assert values["citation_graph_api_regression_routes_count"] == 7
    assert values["citation_graph_api_regression_traversal_routes_count"] == 6
    assert (
        values["citation_graph_api_regression_current_graph_routes_checkpointed"]
        is True
    )
    assert (
        values["citation_graph_api_regression_runtime_loader_implemented"]
        is False
    )
    assert values["citation_graph_api_regression_publication_ready"] is False
    assert values["citation_graph_api_regression_manual_review_required"] is True


def test_citation_graph_api_regression_values_missing_report_are_not_green():
    values = dod.extract_citation_graph_api_regression_values(None)

    assert values["citation_graph_api_regression_check_ok"] is False
    assert values["citation_graph_api_regression_required_failed_count"] is None
    assert values["citation_graph_api_regression_routes_count"] is None


def test_citation_graph_api_regression_dod_parser_flag_and_path():
    args = dod.build_parser().parse_args(
        [
            "--require-citation-graph-api-regression",
            "--citation-graph-api-regression-path",
            "custom/report.json",
        ]
    )

    assert args.require_citation_graph_api_regression is True
    assert str(args.citation_graph_api_regression_path).replace("\\", "/") == (
        "custom/report.json"
    )
