from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import services.api.app as app_module
from services.api.app import app
from services.api.citation_graph_service import EXPECTED_COUNTS, REQUIRED_GRAPH_FILES, REQUIRED_REPORTS


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_reference_endpoint_fixture(tmp_path: Path) -> tuple[Path, Path]:
    graph_root = tmp_path / "data" / "graphs" / "citation_reference_graph" / "v0.1"
    reports_root = tmp_path / "artifacts" / "reports" / "validation"

    graph_root.mkdir(parents=True, exist_ok=True)
    reports_root.mkdir(parents=True, exist_ok=True)

    nodes = [
        {
            "node_id": "paper:a",
            "node_type": "paper",
            "canonical_id": "paper:a",
            "title": "Example Source Paper",
            "year": 2025,
        },
        {
            "node_id": "paper:b",
            "node_type": "paper",
            "canonical_id": "paper:b",
            "title": "Example Target Paper",
            "year": 2024,
        },
        {
            "node_id": "external_reference:doi:10.9999/external-one",
            "node_type": "external_reference",
            "reference_key": "doi:10.9999/external-one",
            "reference_type": "doi",
            "normalized_value": "10.9999/external-one",
        },
        {
            "node_id": "source_family:openalex",
            "node_type": "source_family",
            "source_family": "openalex",
        },
    ]
    edges = [
        {
            "edge_id": "edge:001",
            "edge_type": "paper_references_paper",
            "source_node_id": "paper:a",
            "target_node_id": "paper:b",
            "reference_type": "doi",
            "normalized_reference": "10.0000/example-target",
            "source_families": ["openalex"],
            "evidence_count": 1,
        },
        {
            "edge_id": "edge:002",
            "edge_type": "paper_references_external",
            "source_node_id": "paper:a",
            "target_node_id": "external_reference:doi:10.9999/external-one",
            "reference_type": "doi",
            "normalized_reference": "10.9999/external-one",
            "source_families": ["openalex"],
            "evidence_count": 1,
        },
        {
            "edge_id": "edge:003",
            "edge_type": "paper_has_reference_source_family",
            "source_node_id": "paper:a",
            "target_node_id": "source_family:openalex",
            "source_family": "openalex",
            "evidence_count": 1,
        },
    ]

    for file_name in REQUIRED_GRAPH_FILES:
        path = graph_root / file_name
        if file_name == "nodes.jsonl":
            _write_jsonl(path, nodes)
        elif file_name == "edges.jsonl":
            _write_jsonl(path, edges)
        elif file_name == "manifest.json":
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


def _enable_citation_graph(monkeypatch, graph_root: Path, reports_root: Path) -> None:
    monkeypatch.setattr(app_module.settings, "citation_graph_api_enabled", True)
    monkeypatch.setattr(app_module.settings, "citation_graph_root", graph_root)
    monkeypatch.setattr(app_module.settings, "citation_graph_reports_root", reports_root)
    monkeypatch.setattr(app_module.settings, "citation_graph_exposure_mode", "local_inspection")
    monkeypatch.setattr(app_module.settings, "citation_graph_default_limit", 50)
    monkeypatch.setattr(app_module.settings, "citation_graph_max_limit", 100)


def test_citation_graph_references_disabled_fails_closed(monkeypatch):
    monkeypatch.setattr(app_module.settings, "citation_graph_api_enabled", False)

    with TestClient(app) as client:
        response = client.get("/citation-graph/papers/paper:a/references")

    assert response.status_code == 503
    payload = response.json()
    assert payload["error_code"] == "graph_runtime_not_enabled"
    assert "results" not in payload


def test_citation_graph_references_returns_resolved_and_external_items(tmp_path, monkeypatch):
    graph_root, reports_root = _write_reference_endpoint_fixture(tmp_path)
    _enable_citation_graph(monkeypatch, graph_root, reports_root)

    with TestClient(app) as client:
        response = client.get(
            "/citation-graph/papers/paper:a/references",
            params={"limit": 10, "offset": 0},
        )

    assert response.status_code == 200
    payload = response.json()

    assert payload["graph"]["name"] == "citation_reference_graph"
    assert payload["graph"]["version"] == "v0.1"
    assert payload["graph"]["metadata_reference_fields_only"] is True
    assert payload["graph"]["full_text_parsed"] is False
    assert payload["graph"]["manual_review_required"] is True
    assert payload["graph"]["manual_review_complete"] is False
    assert payload["graph"]["publication_ready"] is False

    assert payload["query"] == {
        "endpoint": "/citation-graph/papers/{canonical_id}/references",
        "canonical_id": "paper:a",
        "limit": 10,
        "offset": 0,
        "reference_type": None,
        "resolved": None,
        "source_family": None,
    }
    assert payload["page"] == {
        "limit": 10,
        "offset": 0,
        "returned": 2,
        "total_estimate": 2,
    }
    assert [item["edge_type"] for item in payload["items"]] == [
        "paper_references_paper",
        "paper_references_external",
    ]
    assert payload["items"][0]["resolved"] is True
    assert payload["items"][0]["target_canonical_id"] == "paper:b"
    assert payload["items"][1]["resolved"] is False
    assert payload["items"][1]["external_reference_id"] == (
        "external_reference:doi:10.9999/external-one"
    )
    assert "metadata_reference_fields_only" in payload["caveats"]
    assert "not_a_complete_citation_index" in payload["caveats"]
    assert "unresolved_references_preserved_as_external_reference_nodes" in payload["caveats"]


def test_citation_graph_references_unknown_canonical_id_returns_404(tmp_path, monkeypatch):
    graph_root, reports_root = _write_reference_endpoint_fixture(tmp_path)
    _enable_citation_graph(monkeypatch, graph_root, reports_root)

    with TestClient(app) as client:
        response = client.get("/citation-graph/papers/paper:missing/references")

    assert response.status_code == 404
    payload = response.json()
    assert payload["error_code"] == "canonical_id_not_found"
    assert payload["details"] == {"canonical_id": "paper:missing"}


def test_citation_graph_references_limit_above_max_returns_graph_error(tmp_path, monkeypatch):
    graph_root, reports_root = _write_reference_endpoint_fixture(tmp_path)
    _enable_citation_graph(monkeypatch, graph_root, reports_root)

    with TestClient(app) as client:
        response = client.get(
            "/citation-graph/papers/paper:a/references",
            params={"limit": 101},
        )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "graph_result_limit_exceeded"
    assert payload["details"] == {"limit": 101, "max_limit": 100}


def test_citation_graph_references_incompatible_graph_fails_closed(tmp_path, monkeypatch):
    missing_graph_root = tmp_path / "missing_graph"
    missing_reports_root = tmp_path / "missing_reports"
    _enable_citation_graph(monkeypatch, missing_graph_root, missing_reports_root)

    with TestClient(app) as client:
        response = client.get("/citation-graph/papers/paper:a/references")

    assert response.status_code == 503
    payload = response.json()
    assert payload["error_code"] == "graph_artifacts_not_found"
    assert payload["details"]["compatibility"]["ok"] is False
