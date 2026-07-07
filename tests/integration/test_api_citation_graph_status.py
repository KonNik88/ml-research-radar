from __future__ import annotations

from fastapi.testclient import TestClient

from services.api.app import app
import services.api.app as app_module


def test_citation_graph_status_disabled_by_default(monkeypatch):
    monkeypatch.setattr(app_module.settings, "citation_graph_api_enabled", False)

    with TestClient(app) as client:
        response = client.get("/citation-graph/status")

    assert response.status_code == 200
    payload = response.json()

    assert payload["graph"]["name"] == "citation_reference_graph"
    assert payload["graph"]["version"] == "v0.1"
    assert payload["graph"]["runtime_enabled"] is False
    assert payload["graph"]["available"] is False
    assert payload["graph"]["exposure_mode"] == "local_inspection"

    assert payload["graph"]["metadata_reference_fields_only"] is True
    assert payload["graph"]["full_text_parsed"] is False
    assert payload["graph"]["pdfs_parsed"] is False
    assert payload["graph"]["bibliography_sections_parsed"] is False
    assert payload["graph"]["manual_review_required"] is True
    assert payload["graph"]["manual_review_complete"] is False
    assert payload["graph"]["publication_ready"] is False
    assert payload["graph"]["may_be_used_as_reconcile_input"] is False
    assert payload["graph"]["not_a_complete_citation_index"] is True

    assert payload["query"] == {"endpoint": "/citation-graph/status"}
    assert payload["items"] == []
    assert payload["page"] == {
        "limit": 0,
        "offset": 0,
        "returned": 0,
        "total_estimate": None,
    }
    assert payload["availability"]["configured"] is False
    assert payload["availability"]["available"] is False
    assert payload["availability"]["runtime_enabled"] is False
    assert payload["availability"]["safe_to_serve_locally"] is False
    assert payload["availability"]["runtime_loader_implemented"] is False
    assert payload["availability"]["traversal_endpoints_implemented"] is False
    assert payload["error_code"] == "graph_runtime_not_enabled"

    assert "metadata_reference_fields_only" in payload["caveats"]
    assert "not_a_complete_citation_index" in payload["caveats"]
    assert "manual_review_required" in payload["caveats"]
    assert "publication_ready_false" in payload["caveats"]


def test_citation_graph_status_does_not_affect_health(monkeypatch):
    monkeypatch.setattr(app_module.settings, "citation_graph_api_enabled", False)

    with TestClient(app) as client:
        status_response = client.get("/citation-graph/status")
        health_response = client.get("/health")

    assert status_response.status_code == 200
    assert health_response.status_code == 200

    health_payload = health_response.json()
    assert health_payload["status"] == "ok"
    assert health_payload["ready"] is True


def test_citation_graph_traversal_endpoints_not_implemented(monkeypatch):
    monkeypatch.setattr(app_module.settings, "citation_graph_api_enabled", False)

    with TestClient(app) as client:
        response = client.get("/citation-graph/papers/paper:example/references")

    assert response.status_code == 404
