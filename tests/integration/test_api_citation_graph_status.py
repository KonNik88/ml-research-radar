from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from services.api.app import app
import services.api.app as app_module
from services.api.citation_graph_service import (
    EXPECTED_COUNTS,
    REQUIRED_GRAPH_FILES,
    REQUIRED_REPORTS,
    build_citation_graph_status,
)
from services.api.settings import ApiSettings


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_compatible_graph_fixture(tmp_path: Path) -> tuple[Path, Path]:
    graph_root = tmp_path / "data" / "graphs" / "citation_reference_graph" / "v0.1"
    reports_root = tmp_path / "artifacts" / "reports" / "validation"

    graph_root.mkdir(parents=True, exist_ok=True)
    reports_root.mkdir(parents=True, exist_ok=True)

    for file_name in REQUIRED_GRAPH_FILES:
        path = graph_root / file_name
        if file_name == "manifest.json":
            _write_json(
                path,
                {
                    "graph_name": "citation_reference_graph",
                    "graph_version": "v0.1",
                    "counts": dict(EXPECTED_COUNTS),
                    "safety": {
                        "mutate_canonical_documents": False,
                        "mutate_retrieval_artifacts": False,
                        "mutate_qdrant": False,
                        "mutate_postgres": False,
                        "mutate_api": False,
                        "mutate_ui": False,
                        "mutate_ranking": False,
                        "publish_graph": False,
                        "may_be_used_as_reconcile_input": False,
                    },
                },
            )
        elif file_name == "data_quality_summary.json":
            _write_json(
                path,
                {
                    "ok": True,
                    "required_failed_count": 0,
                    "counts": dict(EXPECTED_COUNTS),
                },
            )
        elif file_name == "schema.json":
            _write_json(
                path,
                {
                    "schema_version": "citation_reference_graph_schema_v1",
                    "graph_name": "citation_reference_graph",
                    "graph_version": "v0.1",
                },
            )
        else:
            path.write_text("test fixture\n", encoding="utf-8")

    for report_name, file_name in REQUIRED_REPORTS.items():
        _write_json(
            reports_root / file_name,
            {
                "summary": {
                    "ok": True,
                    "required_failed_count": 0,
                },
                "report_name": report_name,
                "counts": dict(EXPECTED_COUNTS),
                "manual_review_required": True,
                "manual_review_complete": False,
                "publication_ready": False,
                "publication_block_reason": "manual_review_not_completed",
            },
        )

    return graph_root, reports_root


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
    assert payload["availability"]["file_backed_store_loader_implemented"] is True
    assert payload["availability"]["runtime_loader_implemented"] is False
    assert payload["availability"]["traversal_endpoints_implemented"] is True
    assert payload["availability"]["implemented_traversal_endpoint_count"] == 6
    assert payload["availability"]["full_graph_runtime_subsystem_implemented"] is False
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


def test_citation_graph_references_endpoint_disabled_fails_closed(monkeypatch):
    monkeypatch.setattr(app_module.settings, "citation_graph_api_enabled", False)

    with TestClient(app) as client:
        response = client.get("/citation-graph/papers/paper:example/references")

    assert response.status_code == 503
    payload = response.json()
    assert payload["error_code"] == "graph_runtime_not_enabled"
    assert "results" not in payload


def test_citation_graph_status_enabled_missing_artifacts(tmp_path):
    settings = ApiSettings(
        citation_graph_api_enabled=True,
        citation_graph_root=tmp_path / "missing_graph",
        citation_graph_reports_root=tmp_path / "missing_reports",
    )

    payload = build_citation_graph_status(settings=settings).model_dump()

    assert payload["graph"]["runtime_enabled"] is True
    assert payload["graph"]["available"] is False
    assert payload["availability"]["configured"] is True
    assert payload["availability"]["available"] is False
    assert payload["availability"]["file_backed_store_loader_implemented"] is True
    assert payload["availability"]["runtime_loader_implemented"] is False
    assert payload["availability"]["traversal_endpoints_implemented"] is True
    assert payload["availability"]["implemented_traversal_endpoint_count"] == 6
    assert payload["availability"]["full_graph_runtime_subsystem_implemented"] is False
    assert payload["error_code"] == "graph_artifacts_not_found"
    assert payload["compatibility"]["ok"] is False
    assert payload["compatibility"]["missing_graph_files"]
    assert payload["compatibility"]["missing_reports"]


def test_citation_graph_status_enabled_compatible_local_probe(tmp_path):
    graph_root, reports_root = _write_compatible_graph_fixture(tmp_path)

    settings = ApiSettings(
        citation_graph_api_enabled=True,
        citation_graph_root=graph_root,
        citation_graph_reports_root=reports_root,
    )

    payload = build_citation_graph_status(settings=settings).model_dump()

    assert payload["graph"]["runtime_enabled"] is True
    assert payload["graph"]["available"] is True
    assert payload["graph"]["manual_review_required"] is True
    assert payload["graph"]["manual_review_complete"] is False
    assert payload["graph"]["publication_ready"] is False

    assert payload["availability"]["configured"] is True
    assert payload["availability"]["available"] is True
    assert payload["availability"]["safe_to_serve_locally"] is True
    assert payload["availability"]["file_backed_store_loader_implemented"] is True
    assert payload["availability"]["runtime_loader_implemented"] is False
    assert payload["availability"]["traversal_endpoints_implemented"] is True
    assert payload["availability"]["implemented_traversal_endpoint_count"] == 6
    assert payload["availability"]["full_graph_runtime_subsystem_implemented"] is False

    assert payload["error_code"] is None
    assert payload["compatibility"]["ok"] is True
    assert payload["compatibility"]["count_mismatches"] == {}
    assert payload["counts"]["nodes_count"] == 529295
    assert payload["counts"]["edges_count"] == 745516
    assert payload["counts"]["reference_resolution_ratio"] == 0.00869

    assert "manual_review_incomplete" in payload["caveats"]
    assert "publication_not_ready" in payload["caveats"]
    assert "file_backed_read_only_traversal_runtime" in payload["caveats"]
    assert "not_promoted_full_graph_runtime" in payload["caveats"]
    assert "status_probe_only_no_traversal_runtime" not in payload["caveats"]


def test_citation_graph_status_enabled_count_mismatch_blocks_availability(tmp_path):
    graph_root, reports_root = _write_compatible_graph_fixture(tmp_path)

    manifest_path = graph_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["counts"]["nodes_count"] = 1
    _write_json(manifest_path, manifest)

    settings = ApiSettings(
        citation_graph_api_enabled=True,
        citation_graph_root=graph_root,
        citation_graph_reports_root=reports_root,
    )

    payload = build_citation_graph_status(settings=settings).model_dump()

    assert payload["graph"]["runtime_enabled"] is True
    assert payload["graph"]["available"] is False
    assert payload["availability"]["available"] is False
    assert payload["error_code"] == "graph_artifacts_incompatible"
    assert payload["compatibility"]["ok"] is False
    assert payload["compatibility"]["count_mismatches"]["nodes_count"]["expected"] == 529295
    assert payload["compatibility"]["count_mismatches"]["nodes_count"]["actual"] == 1
