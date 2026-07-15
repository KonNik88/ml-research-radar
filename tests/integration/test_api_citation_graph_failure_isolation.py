from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import services.api.app as app_module
from services.api.app import app
from services.api.citation_graph_service import (
    EXPECTED_COUNTS,
    REQUIRED_GRAPH_FILES,
    REQUIRED_REPORTS,
)


TRAVERSAL_ENDPOINTS = (
    "/citation-graph/papers/paper:a/references",
    "/citation-graph/papers/paper:b/citations",
    "/citation-graph/external-references/doi:10.9999/external-one/papers",
    "/citation-graph/source-families",
    "/citation-graph/top-referenced-papers",
    "/citation-graph/top-external-references",
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _fixture_nodes() -> list[dict[str, Any]]:
    return [
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


def _fixture_edges() -> list[dict[str, Any]]:
    return [
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


def _write_compatible_graph_fixture(tmp_path: Path) -> tuple[Path, Path]:
    graph_root = (
        tmp_path / "data" / "graphs" / "citation_reference_graph" / "v0.1"
    )
    reports_root = tmp_path / "artifacts" / "reports" / "validation"

    graph_root.mkdir(parents=True, exist_ok=True)
    reports_root.mkdir(parents=True, exist_ok=True)

    nodes = _fixture_nodes()
    edges = _fixture_edges()

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
            path.write_text("failure-isolation fixture\n", encoding="utf-8")

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


def _enable_citation_graph(
    monkeypatch: pytest.MonkeyPatch,
    graph_root: Path,
    reports_root: Path,
) -> None:
    monkeypatch.setattr(app_module.settings, "citation_graph_api_enabled", True)
    monkeypatch.setattr(app_module.settings, "citation_graph_root", graph_root)
    monkeypatch.setattr(
        app_module.settings,
        "citation_graph_reports_root",
        reports_root,
    )
    monkeypatch.setattr(
        app_module.settings,
        "citation_graph_exposure_mode",
        "local_inspection",
    )
    monkeypatch.setattr(app_module.settings, "citation_graph_default_limit", 50)
    monkeypatch.setattr(app_module.settings, "citation_graph_max_limit", 100)


@dataclass
class _FakeRuntime:
    load_calls: int = 0
    reload_calls: int = 0
    last_reload_at: str | None = None

    def load(self) -> None:
        self.load_calls += 1

    def reload(self) -> None:
        self.reload_calls += 1
        self.last_reload_at = "2026-07-15T12:00:00+00:00"

    def runtime_snapshot(self, **_: Any) -> dict[str, Any]:
        return {
            "ready": True,
            "backend_mode": "file",
            "build_id": "failure-isolation-test-build",
            "corpus_doc_count": 2,
            "embedding_model_name": "test-model",
            "artifacts_root": "artifacts/retrieval",
            "loaded_components": {
                "manifest": True,
                "documents": True,
                "lexical_artifacts": True,
                "dense_artifacts": True,
                "embedding_model": True,
                "db_store": False,
            },
            "db_connected": False,
            "qdrant": None,
            "last_load_error": None,
            "last_loaded_at": "2026-07-15T11:59:00+00:00",
            "last_reload_at": self.last_reload_at,
            "model_reused": True,
            "current_model_name": "test-model",
        }


@dataclass
class _FakeDiscoveryService:
    reload_calls: int = 0

    def reload(self) -> None:
        self.reload_calls += 1


@pytest.fixture(autouse=True)
def _clear_graph_store_cache():
    app_module._load_citation_graph_store_cached.cache_clear()
    yield
    app_module._load_citation_graph_store_cached.cache_clear()


def _install_fake_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[_FakeRuntime, _FakeDiscoveryService]:
    runtime = _FakeRuntime()
    discovery = _FakeDiscoveryService()
    monkeypatch.setattr(app_module, "get_runtime", lambda: runtime)
    monkeypatch.setattr(app_module, "get_discovery_service", lambda: discovery)
    return runtime, discovery


def _assert_general_runtime_healthy(client: TestClient) -> None:
    health = client.get("/health")
    info = client.get("/info")
    runtime = client.get("/runtime")

    assert health.status_code == 200
    assert health.json()["ready"] is True
    assert info.status_code == 200
    assert runtime.status_code == 200
    assert runtime.json()["ready"] is True


def test_missing_graph_artifact_fails_closed_without_affecting_general_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    graph_root, reports_root = _write_compatible_graph_fixture(tmp_path)
    _enable_citation_graph(monkeypatch, graph_root, reports_root)
    _install_fake_runtime(monkeypatch)
    (graph_root / "edges.jsonl").unlink()

    with TestClient(app) as client:
        status_response = client.get("/citation-graph/status")
        traversal_response = client.get(
            "/citation-graph/papers/paper:a/references"
        )
        _assert_general_runtime_healthy(client)

    assert status_response.status_code == 200
    assert status_response.json()["error_code"] == "graph_artifacts_not_found"
    assert traversal_response.status_code == 503
    assert traversal_response.json()["error_code"] == "graph_artifacts_not_found"


def test_invalid_status_artifact_fails_closed_without_affecting_general_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    graph_root, reports_root = _write_compatible_graph_fixture(tmp_path)
    _enable_citation_graph(monkeypatch, graph_root, reports_root)
    _install_fake_runtime(monkeypatch)
    (graph_root / "manifest.json").write_text("{not-json\n", encoding="utf-8")

    with TestClient(app) as client:
        status_response = client.get("/citation-graph/status")
        traversal_response = client.get(
            "/citation-graph/papers/paper:a/references"
        )
        _assert_general_runtime_healthy(client)

    assert status_response.status_code == 200
    assert status_response.json()["error_code"] == "graph_artifacts_invalid"
    assert traversal_response.status_code == 503
    assert traversal_response.json()["error_code"] == "graph_artifacts_invalid"


def test_graph_store_oserror_maps_to_graph_artifacts_invalid_for_all_routes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    graph_root, reports_root = _write_compatible_graph_fixture(tmp_path)
    _enable_citation_graph(monkeypatch, graph_root, reports_root)
    _install_fake_runtime(monkeypatch)

    def _raise_oserror():
        raise OSError("simulated citation graph file access failure")

    monkeypatch.setattr(app_module, "_load_citation_graph_store", _raise_oserror)

    with TestClient(app) as client:
        for endpoint in TRAVERSAL_ENDPOINTS:
            response = client.get(endpoint)
            assert response.status_code == 503, endpoint
            assert response.json()["error_code"] == "graph_artifacts_invalid"
        _assert_general_runtime_healthy(client)


def test_failed_store_load_is_not_cached_and_recovers_without_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    graph_root, reports_root = _write_compatible_graph_fixture(tmp_path)
    _enable_citation_graph(monkeypatch, graph_root, reports_root)
    _install_fake_runtime(monkeypatch)
    nodes_path = graph_root / "nodes.jsonl"
    nodes_path.write_text("{not-json\n", encoding="utf-8")

    with TestClient(app) as client:
        failed_response = client.get(
            "/citation-graph/papers/paper:a/references"
        )
        assert failed_response.status_code == 503
        assert failed_response.json()["error_code"] == "graph_artifacts_invalid"
        assert app_module._load_citation_graph_store_cached.cache_info().currsize == 0

        _write_jsonl(nodes_path, _fixture_nodes())

        recovered_response = client.get(
            "/citation-graph/papers/paper:a/references"
        )
        assert recovered_response.status_code == 200
        assert app_module._load_citation_graph_store_cached.cache_info().currsize == 1
        _assert_general_runtime_healthy(client)


def test_cached_store_survives_file_corruption_until_reload_then_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    graph_root, reports_root = _write_compatible_graph_fixture(tmp_path)
    _enable_citation_graph(monkeypatch, graph_root, reports_root)
    runtime, discovery = _install_fake_runtime(monkeypatch)
    nodes_path = graph_root / "nodes.jsonl"

    with TestClient(app) as client:
        initial_response = client.get(
            "/citation-graph/papers/paper:a/references"
        )
        assert initial_response.status_code == 200
        assert app_module._load_citation_graph_store_cached.cache_info().currsize == 1

        nodes_path.write_text("{not-json\n", encoding="utf-8")

        cached_response = client.get(
            "/citation-graph/papers/paper:a/references"
        )
        assert cached_response.status_code == 200

        reload_response = client.post("/reload")
        assert reload_response.status_code == 200
        assert runtime.reload_calls == 1
        assert discovery.reload_calls == 1
        assert app_module._load_citation_graph_store_cached.cache_info().currsize == 0

        failed_response = client.get(
            "/citation-graph/papers/paper:a/references"
        )
        assert failed_response.status_code == 503
        assert failed_response.json()["error_code"] == "graph_artifacts_invalid"
        assert app_module._load_citation_graph_store_cached.cache_info().currsize == 0
        _assert_general_runtime_healthy(client)

        _write_jsonl(nodes_path, _fixture_nodes())

        recovered_response = client.get(
            "/citation-graph/papers/paper:a/references"
        )
        assert recovered_response.status_code == 200
        assert app_module._load_citation_graph_store_cached.cache_info().currsize == 1
