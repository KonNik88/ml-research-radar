from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "citation_graph_api_regression_v1"

DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")

DEFAULT_APP_PATH = Path("services/api/app.py")
DEFAULT_STORE_PATH = Path("services/api/citation_graph_store.py")
DEFAULT_SERVICE_PATH = Path("services/api/citation_graph_service.py")
DEFAULT_SCHEMAS_PATH = Path("services/api/schemas.py")

DEFAULT_API_REFERENCE_PATH = Path("docs/api_reference.md")
DEFAULT_ARCHITECTURE_PATH = Path("docs/architecture.md")
DEFAULT_PROJECT_STATE_PATH = Path("docs/project_state_current_v0.1.md")
DEFAULT_ROADMAP_PATH = Path("docs/roadmap.md")
DEFAULT_REFRESH_CONTRACT_PATH = Path("docs/refresh_contract_v1.md")

DEFAULT_STATUS_TEST_PATH = Path("tests/integration/test_api_citation_graph_status.py")
DEFAULT_TRAVERSAL_TEST_PATH = Path("tests/integration/test_api_citation_graph_references.py")
DEFAULT_STORE_TEST_PATH = Path("tests/smoke/test_citation_graph_fixture_store.py")
DEFAULT_RELOAD_TEST_PATH = Path("tests/integration/test_api_reload.py")
DEFAULT_GRAPH_RELOAD_TEST_PATH = Path(
    "tests/integration/test_api_citation_graph_reload.py"
)
DEFAULT_FAILURE_ISOLATION_TEST_PATH = Path(
    "tests/integration/test_api_citation_graph_failure_isolation.py"
)
DEFAULT_LIVE_SMOKE_VALIDATOR_PATH = Path(
    "scripts/validation/check_citation_graph_live_smoke.py"
)
DEFAULT_LIVE_SMOKE_TEST_PATH = Path(
    "tests/smoke/test_citation_graph_live_smoke.py"
)
DEFAULT_KNOWN_ISSUES_PATH = Path(
    "docs/citation_graph_known_issues_v0.1.md"
)

ROUTES = {
    "status": "/citation-graph/status",
    "references": "/citation-graph/papers/{canonical_id}/references",
    "citations": "/citation-graph/papers/{canonical_id}/citations",
    "external_reference_papers": (
        "/citation-graph/external-references/{reference_id:path}/papers"
    ),
    "source_families": "/citation-graph/source-families",
    "top_referenced_papers": "/citation-graph/top-referenced-papers",
    "top_external_references": "/citation-graph/top-external-references",
}

TRAVERSAL_ROUTES = {
    key: value
    for key, value in ROUTES.items()
    if key != "status"
}

STORE_METHODS = [
    "outgoing_references",
    "incoming_citations",
    "external_reference_papers",
    "source_family_diagnostics",
    "top_referenced_papers",
    "top_external_references",
]

REQUIRED_TOP_REFERENCED_CAVEATS = [
    "resolved_internal_reference_count_only",
    "not_global_citation_metric",
    "not_publication_grade_ranking",
]

REQUIRED_TOP_EXTERNAL_CAVEATS = [
    "external_reference_is_unresolved",
    "not_publication_grade_reference_entity",
    "not_global_citation_metric",
    "not_publication_grade_ranking",
]

COMMON_GRAPH_CAVEATS = [
    "metadata_reference_fields_only",
    "not_a_complete_citation_index",
    "manual_review_required",
    "publication_ready_false",
]

REQUIRED_DOC_SNIPPETS = [
    "Citation Graph Traversal API Checkpoint v0.3",
    "GET /citation-graph/status",
    "GET /citation-graph/papers/{canonical_id}/references",
    "GET /citation-graph/papers/{canonical_id}/citations",
    "GET /citation-graph/external-references/{reference_id}/papers",
    "GET /citation-graph/source-families",
    "GET /citation-graph/top-referenced-papers",
    "GET /citation-graph/top-external-references",
    "top_external_references_endpoint = implemented",
    "full_graph_runtime_loader = not implemented",
    "graph_db_materialization = not implemented",
    "Citation Graph UI Productization Checkpoint v0.1",
    "streamlit_graph_evidence_panels = implemented",
    "streamlit_graph_status_panel = implemented",
    "streamlit_graph_paper_workspace_panel = implemented",
    "streamlit_graph_diagnostics_ui = implemented",
    "streamlit_graph_external_reference_lookup_ui = implemented",
    "full_graph_visualization_ui = not implemented",
    "graphrag = not implemented",
    "Citation Graph Store Cache & Reload Regression v0.1",
    "citation_graph_store_cache = bounded_by_graph_root",
    "citation_graph_store_cache_clear_on_reload = implemented",
    "graph_reload_rebuilds_artifacts = false",
    "graph_reload_mutates_artifacts = false",
    "Citation Graph Failure Isolation & Error Recovery v0.1",
    "citation_graph_failure_isolation = implemented",
    "graph_store_oserror_maps_to_graph_artifacts_invalid = true",
    "graph_store_failed_load_cached = false",
    "graph_runtime_failure_affects_general_health = false",
    "graph_runtime_recovery_requires_process_restart = false",
    "Citation Graph Live Smoke & Known-Issues Hardening v0.1",
    "citation_graph_live_smoke = implemented_operator_facing_opt_in",
    "citation_graph_live_smoke_dod_gate = not_required",
    "citation_graph_live_smoke_auto_samples = graph_jsonl",
    "citation_graph_known_issues = documented_v0.1",
]

FORBIDDEN_STALE_DOC_SNIPPETS = [
    "top_external_references_endpoint = not implemented",
    "top-external-reference public route = not implemented",
    "top_external_references_endpoint = not_implemented",
    "GET /citation-graph/top-external-references = not implemented",
    "current active slice = Citation Graph Top External References Endpoint Docs Sync v0.1",
    "Citation Graph Top External References Endpoint Docs Sync v0.1 — 2026-07 active",
    "current active slice = Citation Graph External Reference Lookup UI v0.1",
    "Citation Graph External Reference Lookup UI v0.1 — 2026-07 active",
    "current active slice = Citation Graph UI Productization Checkpoint v0.1",
    "Citation Graph UI Productization Checkpoint v0.1 — 2026-07 active",
    "current active slice = Citation Graph Store Cache & Reload Regression v0.1",
    "Citation Graph Store Cache & Reload Regression v0.1 — 2026-07 active",
    "current active slice = Citation Graph Failure Isolation & Error Recovery v0.1",
    "Citation Graph Failure Isolation & Error Recovery v0.1 — 2026-07 active",
    "streamlit_graph_ui = not implemented",
]

FORBIDDEN_RUNTIME_IMPORT_SNIPPETS = [
    "import networkx",
    "from networkx",
    "import neo4j",
    "from neo4j",
    "GraphDatabase",
    "import graphrag",
    "from graphrag",
]


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def read_text(path: Path) -> tuple[bool, str, str | None]:
    try:
        return True, path.read_text(encoding="utf-8"), None
    except Exception as exc:  # noqa: BLE001 - report should keep diagnostics.
        return False, "", repr(exc)


def missing_snippets(text: str, snippets: list[str]) -> list[str]:
    return [snippet for snippet in snippets if snippet not in text]


def present_forbidden_snippets(text: str, snippets: list[str]) -> list[str]:
    return [snippet for snippet in snippets if snippet in text]


def check_python_syntax(path: Path) -> tuple[bool, str | None]:
    ok, text, error = read_text(path)
    if not ok:
        return False, error
    try:
        compile(text, str(path), "exec")
    except SyntaxError as exc:
        return False, f"{exc.__class__.__name__}: {exc}"
    return True, None


def count_occurrences(text: str, needle: str) -> int:
    return text.count(needle)


def route_count_summary(app_text: str) -> dict[str, int]:
    return {
        name: count_occurrences(app_text, route)
        for name, route in ROUTES.items()
    }


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = [
        "# Citation Graph API regression check",
        "",
        f"- generated_at_utc: `{report.get('generated_at_utc')}`",
        f"- run_ts: `{report.get('run_ts')}`",
        f"- schema_version: `{report.get('schema_version')}`",
        f"- strict: `{report.get('strict')}`",
        "",
        "## Summary",
        "",
    ]

    for key, value in report["summary"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Inputs", ""])
    for key, value in report["inputs"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Checks", ""])
    for key, value in report["checks"].items():
        lines.append(f"- {key}: `{value}`")

    diagnostics = report.get("diagnostics") or {}
    if diagnostics:
        lines.extend(["", "## Diagnostics", ""])
        for key, value in diagnostics.items():
            if isinstance(value, (dict, list)):
                pretty = json.dumps(value, ensure_ascii=False, sort_keys=True)
                lines.append(f"- {key}: `{pretty}`")
            else:
                lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Verdict", ""])
    for key, value in report["verdict"].items():
        lines.append(f"- {key}: `{value}`")

    lines.append("")
    return "\n".join(lines)


def _paths_from_args(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "app_path": Path(args.app_path),
        "store_path": Path(args.store_path),
        "service_path": Path(args.service_path),
        "schemas_path": Path(args.schemas_path),
        "api_reference_path": Path(args.api_reference_path),
        "architecture_path": Path(args.architecture_path),
        "project_state_path": Path(args.project_state_path),
        "roadmap_path": Path(args.roadmap_path),
        "refresh_contract_path": Path(args.refresh_contract_path),
        "status_test_path": Path(args.status_test_path),
        "traversal_test_path": Path(args.traversal_test_path),
        "store_test_path": Path(args.store_test_path),
        "reload_test_path": Path(args.reload_test_path),
        "graph_reload_test_path": Path(args.graph_reload_test_path),
        "failure_isolation_test_path": Path(args.failure_isolation_test_path),
        "live_smoke_validator_path": Path(args.live_smoke_validator_path),
        "live_smoke_test_path": Path(args.live_smoke_test_path),
        "known_issues_path": Path(args.known_issues_path),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    run_ts = utc_now_ts()
    paths = _paths_from_args(args)

    checks: dict[str, bool] = {}
    diagnostics: dict[str, Any] = {}

    file_texts: dict[str, str] = {}
    read_errors: dict[str, str] = {}

    for key, path in paths.items():
        ok, text, error = read_text(path)
        checks[f"{key}_exists_and_readable"] = ok
        if ok:
            file_texts[key] = text
        else:
            read_errors[key] = error or "unreadable"

    diagnostics["read_errors"] = read_errors

    for key in (
        "app_path",
        "store_path",
        "service_path",
        "schemas_path",
        "live_smoke_validator_path",
        "live_smoke_test_path",
    ):
        path = paths[key]
        ok, error = check_python_syntax(path)
        checks[f"{key}_syntax_ok"] = ok
        if error:
            diagnostics[f"{key}_syntax_error"] = error

    app_text = file_texts.get("app_path", "")
    store_text = file_texts.get("store_path", "")
    service_text = file_texts.get("service_path", "")
    schemas_text = file_texts.get("schemas_path", "")
    traversal_test_text = file_texts.get("traversal_test_path", "")
    status_test_text = file_texts.get("status_test_path", "")
    store_test_text = file_texts.get("store_test_path", "")
    reload_test_text = file_texts.get("reload_test_path", "")
    graph_reload_test_text = file_texts.get("graph_reload_test_path", "")
    failure_isolation_test_text = file_texts.get(
        "failure_isolation_test_path",
        "",
    )
    live_smoke_validator_text = file_texts.get("live_smoke_validator_path", "")
    live_smoke_test_text = file_texts.get("live_smoke_test_path", "")
    known_issues_text = file_texts.get("known_issues_path", "")

    route_counts = route_count_summary(app_text)
    diagnostics["route_counts"] = route_counts
    checks["all_7_routes_present_in_app"] = all(
        route_counts[name] >= 1 for name in ROUTES
    )
    checks["no_unexpected_missing_route"] = not [
        name for name, count in route_counts.items() if count <= 0
    ]

    checks["status_route_uses_status_response"] = (
        "@app.get(\"/citation-graph/status\", response_model=CitationGraphStatusResponse)"
        in app_text
        or "response_model=CitationGraphStatusResponse" in app_text
    )
    checks["traversal_routes_use_traversal_response"] = (
        app_text.count("response_model=CitationGraphTraversalResponse")
        >= len(TRAVERSAL_ROUTES)
    )
    checks["traversal_routes_fail_closed_before_loading_store"] = (
        app_text.count("_citation_graph_unavailable_response()")
        >= len(TRAVERSAL_ROUTES)
    )
    checks["traversal_routes_have_limit_guard"] = (
        app_text.count("graph_result_limit_exceeded") >= len(TRAVERSAL_ROUTES)
    )
    checks["external_reference_route_uses_path_parameter"] = (
        "/citation-graph/external-references/{reference_id:path}/papers" in app_text
    )

    missing_top_referenced_caveats = missing_snippets(
        app_text,
        REQUIRED_TOP_REFERENCED_CAVEATS,
    )
    missing_top_external_caveats = missing_snippets(
        app_text,
        REQUIRED_TOP_EXTERNAL_CAVEATS,
    )
    missing_common_caveats = missing_snippets(
        service_text,
        COMMON_GRAPH_CAVEATS,
    )
    diagnostics["missing_top_referenced_caveats"] = missing_top_referenced_caveats
    diagnostics["missing_top_external_caveats"] = missing_top_external_caveats
    diagnostics["missing_common_caveats"] = missing_common_caveats

    checks["top_referenced_caveats_present"] = not missing_top_referenced_caveats
    checks["top_external_caveats_present"] = not missing_top_external_caveats
    checks["common_graph_caveats_present"] = not missing_common_caveats

    missing_store_methods = missing_snippets(
        store_text,
        [f"def {method}(" for method in STORE_METHODS],
    )
    diagnostics["missing_store_methods"] = missing_store_methods
    checks["store_methods_for_6_traversal_surfaces_present"] = not missing_store_methods
    checks["store_contract_remains_file_backed_read_only"] = all(
        snippet in store_text
        for snippet in [
            "file-backed",
            "side-effect free",
            "must not rebuild graph outputs",
            "NetworkX/Neo4j/GraphRAG",
        ]
    )

    checks["schemas_include_status_response"] = (
        "class CitationGraphStatusResponse" in schemas_text
    )
    checks["schemas_include_traversal_response"] = (
        "class CitationGraphTraversalResponse" in schemas_text
        and "items: list[dict[str, Any]]" in schemas_text
        and "caveats: list[str]" in schemas_text
    )

    checks["disabled_default_error_code_present"] = (
        "graph_runtime_not_enabled" in service_text
        and "graph_runtime_not_enabled" in status_test_text
        and "graph_runtime_not_enabled" in traversal_test_text
    )
    checks["status_runtime_loader_remains_not_implemented"] = (
        "runtime_loader_implemented=False" in service_text
        or '"runtime_loader_implemented": False' in service_text
    )
    checks["status_reports_file_backed_traversal_capability"] = all(
        snippet in service_text
        for snippet in [
            '"file_backed_store_loader_implemented": True',
            '"runtime_loader_implemented": False',
            '"traversal_endpoints_implemented": True',
            '"implemented_traversal_endpoint_count": 6',
            '"full_graph_runtime_subsystem_implemented": False',
        ]
    )

    checks["graph_store_cache_bounded_by_graph_root"] = all(
        snippet in app_text
        for snippet in [
            "@lru_cache(maxsize=2)",
            "def _load_citation_graph_store_cached(graph_root: str)",
            "return CitationGraphStore.load(graph_root)",
        ]
    )
    checks["graph_store_cache_clear_on_reload"] = all(
        snippet in app_text
        for snippet in [
            '@app.post("/reload", response_model=ReloadResponse)',
            "_load_citation_graph_store_cached.cache_clear()",
            "runtime.reload()",
            "discovery_service.reload()",
        ]
    )
    cache_clear_position = app_text.find(
        "_load_citation_graph_store_cached.cache_clear()"
    )
    runtime_reload_position = app_text.find("runtime.reload()")
    checks["graph_store_cache_clear_precedes_runtime_reload"] = (
        cache_clear_position >= 0
        and runtime_reload_position >= 0
        and cache_clear_position < runtime_reload_position
    )
    checks["general_reload_tests_preserve_runtime_invariants"] = all(
        snippet in reload_test_text
        for snippet in [
            "test_reload_smoke",
            "test_health_after_reload_smoke",
            "test_runtime_contains_reload_state",
            "test_reload_recreates_cached_qdrant_backend_and_resets_observability",
        ]
    )
    required_graph_reload_test_snippets = [
        "test_repeated_graph_store_load_reuses_cache",
        "test_reload_clears_graph_store_cache_and_reloads_replaced_files",
        "test_reload_does_not_mutate_graph_artifacts",
        "test_disabled_reload_does_not_clear_graph_store_cache",
        "_load_citation_graph_store_cached.cache_info()",
        "_artifact_hashes(graph_root)",
    ]
    missing_graph_reload_test_snippets = missing_snippets(
        graph_reload_test_text,
        required_graph_reload_test_snippets,
    )
    diagnostics["missing_graph_reload_test_snippets"] = (
        missing_graph_reload_test_snippets
    )
    checks["graph_reload_tests_cover_cache_and_no_mutation_contract"] = (
        not missing_graph_reload_test_snippets
    )

    checks["graph_store_oserror_is_graph_scoped_for_all_traversal_routes"] = (
        app_text.count("except (OSError, ValueError) as exc:")
        >= len(TRAVERSAL_ROUTES)
    )
    required_failure_isolation_test_snippets = [
        "test_missing_graph_artifact_fails_closed_without_affecting_general_runtime",
        "test_invalid_status_artifact_fails_closed_without_affecting_general_runtime",
        "test_graph_store_oserror_maps_to_graph_artifacts_invalid_for_all_routes",
        "test_failed_store_load_is_not_cached_and_recovers_without_reload",
        "test_cached_store_survives_file_corruption_until_reload_then_recovers",
        "TRAVERSAL_ENDPOINTS",
        "_assert_general_runtime_healthy",
        "_load_citation_graph_store_cached.cache_info().currsize == 0",
        "graph_artifacts_not_found",
        "graph_artifacts_invalid",
    ]
    missing_failure_isolation_test_snippets = missing_snippets(
        failure_isolation_test_text,
        required_failure_isolation_test_snippets,
    )
    diagnostics["missing_failure_isolation_test_snippets"] = (
        missing_failure_isolation_test_snippets
    )
    checks["failure_isolation_tests_cover_errors_health_and_recovery"] = (
        not missing_failure_isolation_test_snippets
    )

    required_live_smoke_validator_snippets = [
        'SCHEMA_VERSION = "citation_graph_live_smoke_v1"',
        "def resolve_smoke_samples(",
        "from urllib.request import Request, urlopen",
        '"/health"',
        '"/info"',
        '"/runtime"',
        '"/citation-graph/status"',
        '"/citation-graph/source-families"',
        '"/citation-graph/top-referenced-papers"',
        '"/citation-graph/top-external-references"',
        "canonical_id_not_found",
        "external_reference_not_found",
        "graph_result_limit_exceeded",
        '"dod_gate_required": False',
        "citation_graph_live_smoke_latest.json",
        "citation_graph_live_smoke_latest.md",
    ]
    missing_live_smoke_validator_snippets = missing_snippets(
        live_smoke_validator_text,
        required_live_smoke_validator_snippets,
    )
    diagnostics["missing_live_smoke_validator_snippets"] = (
        missing_live_smoke_validator_snippets
    )
    checks["live_smoke_validator_covers_live_routes_and_error_contract"] = (
        not missing_live_smoke_validator_snippets
    )

    required_live_smoke_test_snippets = [
        "test_live_smoke_report_green_with_fake_http",
        "test_live_smoke_detects_general_runtime_regression",
        "test_sample_resolution_and_path_encoding",
        "resolve_smoke_samples",
        "general_runtime_remains_healthy",
        "dod_gate_required",
    ]
    missing_live_smoke_test_snippets = missing_snippets(
        live_smoke_test_text,
        required_live_smoke_test_snippets,
    )
    diagnostics["missing_live_smoke_test_snippets"] = (
        missing_live_smoke_test_snippets
    )
    checks["live_smoke_tests_cover_report_failures_and_sample_resolution"] = (
        not missing_live_smoke_test_snippets
    )

    required_known_issues_snippets = [
        "# Citation Graph Known Issues v0.1",
        "metadata_reference_fields_only = true",
        "not_a_complete_citation_index = true",
        "reference_resolution_ratio = 0.00869",
        "not_global_citation_metric = true",
        "not_publication_grade_ranking = true",
        "full_graph_runtime_loader = not implemented",
        "graph_db_materialization = not implemented",
        "graphrag = not implemented",
        "citation_graph_live_smoke = operator_facing_opt_in",
        "citation_graph_live_smoke_dod_gate = not_required",
        "manual_review_complete = false",
        "publication_ready = false",
    ]
    missing_known_issues_snippets = missing_snippets(
        known_issues_text,
        required_known_issues_snippets,
    )
    diagnostics["missing_known_issues_snippets"] = missing_known_issues_snippets
    checks["known_issues_checkpoint_documents_current_limitations"] = (
        not missing_known_issues_snippets
    )

    required_test_snippets = [
        "test_citation_graph_references_disabled_fails_closed",
        "test_citation_graph_references_returns_resolved_and_external_items",
        "test_citation_graph_citations_disabled_fails_closed",
        "test_citation_graph_citations_returns_resolved_internal_items_only",
        "test_citation_graph_external_reference_papers_disabled_fails_closed",
        "test_citation_graph_external_reference_papers_returns_referencing_papers",
        "test_citation_graph_source_families_disabled_fails_closed",
        "test_citation_graph_source_families_returns_reference_evidence_summary",
        "test_citation_graph_top_referenced_papers_disabled_fails_closed",
        "test_citation_graph_top_referenced_papers_returns_resolved_internal_counts",
        "test_citation_graph_top_external_references_disabled_fails_closed",
        "test_citation_graph_top_external_references_returns_unresolved_reference_counts",
        "graph_result_limit_exceeded",
        "graph_artifacts_not_found",
    ]
    missing_test_snippets = missing_snippets(traversal_test_text, required_test_snippets)
    diagnostics["missing_traversal_test_snippets"] = missing_test_snippets
    checks["traversal_tests_cover_all_current_routes"] = not missing_test_snippets

    checks["status_tests_cover_disabled_and_compatible_probe"] = all(
        snippet in status_test_text
        for snippet in [
            "test_citation_graph_status_disabled_by_default",
            "test_citation_graph_status_enabled_compatible_local_probe",
            "test_citation_graph_status_enabled_missing_artifacts",
            "runtime_loader_implemented",
            "traversal_endpoints_implemented",
        ]
    )

    checks["fixture_store_tests_cover_top_queries"] = all(
        snippet in store_test_text
        for snippet in [
            "top_referenced_papers",
            "top_external_references",
            "source_family_diagnostics",
            "external_reference_papers",
        ]
    )

    runtime_import_text = "\n".join([app_text, store_text, service_text])
    forbidden_runtime_imports = present_forbidden_snippets(
        runtime_import_text,
        FORBIDDEN_RUNTIME_IMPORT_SNIPPETS,
    )
    diagnostics["forbidden_runtime_imports"] = forbidden_runtime_imports
    checks["no_graph_db_or_graphrag_runtime_imports"] = not forbidden_runtime_imports

    if args.skip_docs:
        checks["docs_checks_skipped"] = True
    else:
        doc_texts = {
            key: file_texts.get(key, "")
            for key in (
                "api_reference_path",
                "architecture_path",
                "project_state_path",
                "roadmap_path",
                "refresh_contract_path",
                "known_issues_path",
            )
        }
        combined_docs = "\n".join(doc_texts.values())
        missing_doc_snippets = missing_snippets(combined_docs, REQUIRED_DOC_SNIPPETS)
        stale_doc_snippets = present_forbidden_snippets(
            combined_docs,
            FORBIDDEN_STALE_DOC_SNIPPETS,
        )
        diagnostics["missing_doc_snippets"] = missing_doc_snippets
        diagnostics["stale_doc_snippets"] = stale_doc_snippets

        checks["docs_checkpoint_v03_synced"] = (
            "Citation Graph Traversal API Checkpoint v0.3" in combined_docs
        )
        checks["docs_all_7_routes_present"] = all(
            route.replace("{reference_id:path}", "{reference_id}") in combined_docs
            or route in combined_docs
            for route in ROUTES.values()
        )
        checks["docs_top_external_endpoint_implemented"] = (
            "top_external_references_endpoint = implemented" in combined_docs
        )
        checks["docs_no_stale_top_external_not_implemented_text"] = (
            not stale_doc_snippets
        )
        checks["docs_ui_productization_checkpoint_synced"] = (
            "Citation Graph UI Productization Checkpoint v0.1" in combined_docs
        )
        checks["docs_all_4_streamlit_consumers_implemented"] = all(
            snippet in combined_docs
            for snippet in [
                "streamlit_graph_evidence_panels = implemented",
                "streamlit_graph_status_panel = implemented",
                "streamlit_graph_paper_workspace_panel = implemented",
                "streamlit_graph_diagnostics_ui = implemented",
                "streamlit_graph_external_reference_lookup_ui = implemented",
            ]
        )
        checks["docs_no_ambiguous_streamlit_graph_ui_marker"] = (
            "streamlit_graph_ui = not implemented" not in combined_docs
        )
        checks["docs_cache_reload_checkpoint_synced"] = (
            "Citation Graph Store Cache & Reload Regression v0.1"
            in combined_docs
        )
        checks["docs_cache_reload_contract_markers_present"] = all(
            snippet in combined_docs
            for snippet in [
                "citation_graph_store_cache = bounded_by_graph_root",
                "citation_graph_store_cache_clear_on_reload = implemented",
                "graph_reload_rebuilds_artifacts = false",
                "graph_reload_mutates_artifacts = false",
            ]
        )
        checks["docs_failure_isolation_checkpoint_synced"] = (
            "Citation Graph Failure Isolation & Error Recovery v0.1"
            in combined_docs
        )
        checks["docs_failure_isolation_contract_markers_present"] = all(
            snippet in combined_docs
            for snippet in [
                "citation_graph_failure_isolation = implemented",
                "graph_store_oserror_maps_to_graph_artifacts_invalid = true",
                "graph_store_failed_load_cached = false",
                "graph_runtime_failure_affects_general_health = false",
                "graph_runtime_recovery_requires_process_restart = false",
            ]
        )
        checks["docs_live_smoke_known_issues_checkpoint_synced"] = (
            "Citation Graph Live Smoke & Known-Issues Hardening v0.1"
            in combined_docs
        )
        checks["docs_live_smoke_known_issues_markers_present"] = all(
            snippet in combined_docs
            for snippet in [
                "citation_graph_live_smoke = implemented_operator_facing_opt_in",
                "citation_graph_live_smoke_dod_gate = not_required",
                "citation_graph_live_smoke_auto_samples = graph_jsonl",
                "citation_graph_known_issues = documented_v0.1",
            ]
        )
        checks["docs_non_goals_preserved"] = all(
            snippet in combined_docs
            for snippet in [
                "full_graph_runtime_loader = not implemented",
                "graph_db_materialization = not implemented",
                "full_graph_visualization_ui = not implemented",
                "graphrag = not implemented",
            ]
        )

    failed_checks = [
        key for key, value in checks.items()
        if value is False and key != "docs_checks_skipped"
    ]

    summary = {
        "ok": not failed_checks,
        "required_failed_count": len(failed_checks),
        "checks_count": len(checks),
        "failed_checks": failed_checks,
        "routes_count": len(ROUTES),
        "traversal_routes_count": len(TRAVERSAL_ROUTES),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            key: normalize_path(value)
            for key, value in paths.items()
        } | {
            "skip_docs": bool(args.skip_docs),
            "output_dir": normalize_path(args.output_dir),
        },
        "summary": summary,
        "checks": checks,
        "diagnostics": diagnostics,
        "verdict": {
            "ok": not failed_checks,
            "required_failed_count": len(failed_checks),
            "required_failed_checks": failed_checks,
            "citation_graph_api_regression_ready": not failed_checks,
            "current_graph_routes_checkpointed": not failed_checks,
            "cache_reload_regression_ready": not failed_checks,
            "failure_isolation_regression_ready": not failed_checks,
            "live_smoke_known_issues_ready": not failed_checks,
            "file_backed_store_loader_implemented": True,
            "runtime_loader_implemented": False,
            "traversal_endpoints_implemented": True,
            "implemented_traversal_endpoint_count": 6,
            "full_graph_runtime_subsystem_implemented": False,
            "publication_ready": False,
            "manual_review_required": True,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Static regression check for the implemented Citation Graph API "
            "local-inspection block."
        )
    )
    parser.add_argument("--app-path", type=Path, default=DEFAULT_APP_PATH)
    parser.add_argument("--store-path", type=Path, default=DEFAULT_STORE_PATH)
    parser.add_argument("--service-path", type=Path, default=DEFAULT_SERVICE_PATH)
    parser.add_argument("--schemas-path", type=Path, default=DEFAULT_SCHEMAS_PATH)
    parser.add_argument(
        "--api-reference-path",
        type=Path,
        default=DEFAULT_API_REFERENCE_PATH,
    )
    parser.add_argument("--architecture-path", type=Path, default=DEFAULT_ARCHITECTURE_PATH)
    parser.add_argument("--project-state-path", type=Path, default=DEFAULT_PROJECT_STATE_PATH)
    parser.add_argument("--roadmap-path", type=Path, default=DEFAULT_ROADMAP_PATH)
    parser.add_argument(
        "--refresh-contract-path",
        type=Path,
        default=DEFAULT_REFRESH_CONTRACT_PATH,
    )
    parser.add_argument("--status-test-path", type=Path, default=DEFAULT_STATUS_TEST_PATH)
    parser.add_argument(
        "--traversal-test-path",
        type=Path,
        default=DEFAULT_TRAVERSAL_TEST_PATH,
    )
    parser.add_argument("--store-test-path", type=Path, default=DEFAULT_STORE_TEST_PATH)
    parser.add_argument("--reload-test-path", type=Path, default=DEFAULT_RELOAD_TEST_PATH)
    parser.add_argument(
        "--graph-reload-test-path",
        type=Path,
        default=DEFAULT_GRAPH_RELOAD_TEST_PATH,
    )
    parser.add_argument(
        "--failure-isolation-test-path",
        type=Path,
        default=DEFAULT_FAILURE_ISOLATION_TEST_PATH,
    )
    parser.add_argument(
        "--live-smoke-validator-path",
        type=Path,
        default=DEFAULT_LIVE_SMOKE_VALIDATOR_PATH,
    )
    parser.add_argument(
        "--live-smoke-test-path",
        type=Path,
        default=DEFAULT_LIVE_SMOKE_TEST_PATH,
    )
    parser.add_argument(
        "--known-issues-path",
        type=Path,
        default=DEFAULT_KNOWN_ISSUES_PATH,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--skip-docs", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_report(args)

    output_dir = Path(args.output_dir)
    run_ts = str(report["run_ts"])

    latest_json = output_dir / "citation_graph_api_regression_latest.json"
    latest_md = output_dir / "citation_graph_api_regression_latest.md"
    history_json = output_dir / "history" / f"citation_graph_api_regression_{run_ts}.json"
    history_md = output_dir / "history" / f"citation_graph_api_regression_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(history_json, report)
    dump_text(history_md, build_markdown(report))

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    print(f"[report] {normalize_path(latest_json)}")
    print(f"[report] {normalize_path(latest_md)}")

    if args.strict and not report["verdict"]["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
