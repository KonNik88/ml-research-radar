from __future__ import annotations

from pathlib import Path

import scripts.validation.check_streamlit_discovery_ui as ui_validator


APP_PATH = Path("services/ui/app.py")
COLLECTIONS_UI_PATH = Path("services/ui/collections_ui.py")


def _build_static_report(monkeypatch, app_path: Path) -> dict:
    monkeypatch.setattr(ui_validator, "module_import_available", lambda _: True)
    return ui_validator.build_report(
        app_path=app_path,
        check_api=False,
        api_base_url="http://127.0.0.1:8000",
        timeout_seconds=1,
    )


def test_streamlit_discovery_ui_current_repo_is_green(monkeypatch):
    report = _build_static_report(monkeypatch, APP_PATH)

    assert report["ok"] is True
    assert report["required_failed_count"] == 0
    assert report["checks"]["citation_graph_status_ui_snippets_present"] is True
    assert report["checks"]["collections_ui_snippets_present"] is True
    assert report["checks"]["collections_ui_module_snippets_present"] is True
    assert report["checks"]["workspace_client_module_snippets_present"] is True
    assert report["checks"]["collections_ui_uses_api_only"] is True
    assert report["extracted_values"][
        "missing_citation_graph_status_ui_snippets"
    ] == []
    assert report["extracted_values"]["missing_collections_ui_snippets"] == []
    assert report["extracted_values"]["missing_collections_module_snippets"] == []
    assert report["extracted_values"][
        "missing_workspace_client_module_snippets"
    ] == []


def test_streamlit_discovery_ui_detects_missing_lifecycle_marker(
    tmp_path,
    monkeypatch,
):
    app_text = APP_PATH.read_text(encoding="utf-8")
    mutated_text = app_text.replace(
        '"file_backed_store_loader_implemented"',
        '"file_backed_store_loader_removed"',
        1,
    )
    assert mutated_text != app_text

    mutated_app_path = tmp_path / "app.py"
    mutated_app_path.write_text(mutated_text, encoding="utf-8")

    report = _build_static_report(monkeypatch, mutated_app_path)

    assert report["ok"] is False
    assert report["checks"]["citation_graph_status_ui_snippets_present"] is False
    assert "file_backed_store_loader_implemented" in report["extracted_values"][
        "missing_citation_graph_status_ui_snippets"
    ]


def test_streamlit_discovery_ui_detects_missing_collections_marker(
    tmp_path,
    monkeypatch,
):
    app_text = APP_PATH.read_text(encoding="utf-8")
    mutated_text = app_text.replace(
        "from services.ui.collections_ui import",
        "from services.ui.collections_removed import",
        1,
    )
    assert mutated_text != app_text

    mutated_app_path = tmp_path / "app.py"
    mutated_app_path.write_text(mutated_text, encoding="utf-8")

    report = _build_static_report(monkeypatch, mutated_app_path)

    assert report["ok"] is False
    assert report["checks"]["collections_ui_snippets_present"] is False
    assert "from services.ui.collections_ui import" in report["extracted_values"][
        "missing_collections_ui_snippets"
    ]


def test_streamlit_collections_ui_is_thin_and_reuses_membership_control():
    app_text = APP_PATH.read_text(encoding="utf-8")
    collections_text = COLLECTIONS_UI_PATH.read_text(encoding="utf-8")
    compile(collections_text, str(COLLECTIONS_UI_PATH), "exec")

    assert "from services.ui.collections_ui import" in app_text
    assert "from services.ui.workspace_client import" in collections_text
    assert "from services.api.workspace" not in app_text
    assert "from services.api.workspace" not in collections_text
    assert "WorkspaceStore" not in app_text + collections_text
    assert "WorkspaceService" not in app_text + collections_text
    assert '"Collections"' in app_text
    assert "with collections_tab:" in app_text
    assert app_text.count("render_collection_membership_controls(") == 3
    for marker in [
        "Saved research collections",
        "READING_STATUS_OPTIONS",
        '"to_read"',
        '"reading"',
        '"read"',
        "Create collection",
        "Save / update",
        "Remove from collection",
        "Open saved paper in Paper workspace",
        "workspace_unavailable",
        "collections_pending_selected_id",
        "disabled=not confirm_remove",
    ]:
        assert marker in collections_text


def test_citation_graph_status_live_contract_checks():
    checks: dict[str, bool] = {}
    extracted_values: dict = {}
    errors: dict = {}

    ui_validator.record_citation_graph_status_checks(
        endpoint_ok=True,
        payload={
            "availability": {
                "runtime_enabled": True,
                "available": True,
                "status_probe_implemented": True,
                "file_backed_store_loader_implemented": True,
                "runtime_loader_implemented": False,
                "traversal_endpoints_implemented": True,
                "implemented_traversal_endpoint_count": 6,
                "full_graph_runtime_subsystem_implemented": False,
            },
            "caveats": [
                "file_backed_read_only_traversal_runtime",
                "not_promoted_full_graph_runtime",
            ],
        },
        endpoint_error=None,
        checks=checks,
        extracted_values=extracted_values,
        errors=errors,
    )

    assert checks == {
        "api_citation_graph_status_endpoint_ok": True,
        "api_citation_graph_status_capabilities_match": True,
        "api_citation_graph_status_legacy_caveat_absent": True,
        "api_citation_graph_status_available_caveats_match": True,
    }
    assert extracted_values["api_citation_graph_status_capabilities"] == {
        "status_probe_implemented": True,
        "file_backed_store_loader_implemented": True,
        "runtime_loader_implemented": False,
        "traversal_endpoints_implemented": True,
        "implemented_traversal_endpoint_count": 6,
        "full_graph_runtime_subsystem_implemented": False,
    }
    assert errors == {}


def test_citation_graph_status_disabled_capability_contract_checks():
    checks: dict[str, bool] = {}
    extracted_values: dict = {}
    errors: dict = {}

    ui_validator.record_citation_graph_status_checks(
        endpoint_ok=True,
        payload={
            "availability": {
                "runtime_enabled": False,
                "available": False,
                "status_probe_implemented": True,
                "file_backed_store_loader_implemented": True,
                "runtime_loader_implemented": False,
                "traversal_endpoints_implemented": True,
                "implemented_traversal_endpoint_count": 6,
                "full_graph_runtime_subsystem_implemented": False,
            },
            "caveats": ["metadata_reference_fields_only"],
        },
        endpoint_error=None,
        checks=checks,
        extracted_values=extracted_values,
        errors=errors,
    )

    assert all(checks.values())
    assert errors == {}
