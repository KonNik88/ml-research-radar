from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import services.api.app as app_module
from services.api.app import app


GRAPH_ARTIFACT_NAMES = (
    "nodes.jsonl",
    "edges.jsonl",
    "schema.json",
    "manifest.json",
    "data_quality_summary.json",
    "README.md",
    "checksums.txt",
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


def _write_graph_fixture(graph_root: Path, *, target_title: str) -> Path:
    graph_root.mkdir(parents=True, exist_ok=True)

    nodes = [
        {
            "node_id": "paper:a",
            "node_type": "paper",
            "canonical_id": "paper:a",
            "title": "Source Paper",
            "year": 2025,
        },
        {
            "node_id": "paper:b",
            "node_type": "paper",
            "canonical_id": "paper:b",
            "title": target_title,
            "year": 2024,
        },
    ]
    edges = [
        {
            "edge_id": "edge:001",
            "edge_type": "paper_references_paper",
            "source_node_id": "paper:a",
            "target_node_id": "paper:b",
            "reference_type": "doi",
            "normalized_reference": "10.0000/cache-reload-target",
            "source_families": ["openalex"],
            "evidence_count": 1,
        }
    ]

    _write_jsonl(graph_root / "nodes.jsonl", nodes)
    _write_jsonl(graph_root / "edges.jsonl", edges)
    _write_json(
        graph_root / "schema.json",
        {
            "schema_version": "citation_reference_graph_schema_v1",
            "graph": {
                "name": "citation_reference_graph",
                "version": "v0.1",
            },
        },
    )
    _write_json(
        graph_root / "manifest.json",
        {
            "schema_version": "citation_reference_graph_manifest_v1",
            "graph_name": "citation_reference_graph",
            "graph_version": "v0.1",
            "counts": {
                "nodes_count": len(nodes),
                "edges_count": len(edges),
                "paper_nodes_count": len(nodes),
                "external_reference_nodes_count": 0,
                "source_family_nodes_count": 0,
                "paper_references_paper_edges_count": len(edges),
                "paper_references_external_edges_count": 0,
                "paper_has_reference_source_family_edges_count": 0,
            },
        },
    )
    _write_json(
        graph_root / "data_quality_summary.json",
        {
            "schema_version": "citation_reference_graph_data_quality_summary_v1",
            "summary": {
                "ok": True,
                "required_failed_count": 0,
                "nodes_count": len(nodes),
                "edges_count": len(edges),
            },
        },
    )
    (graph_root / "README.md").write_text(
        "# Citation graph cache/reload fixture\n",
        encoding="utf-8",
    )
    (graph_root / "checksums.txt").write_text(
        "fixture-only; cache/reload tests verify byte stability directly\n",
        encoding="utf-8",
    )
    return graph_root


def _artifact_hashes(graph_root: Path) -> dict[str, str]:
    return {
        name: hashlib.sha256((graph_root / name).read_bytes()).hexdigest()
        for name in GRAPH_ARTIFACT_NAMES
    }


@dataclass
class _FakeRuntime:
    load_calls: int = 0
    reload_calls: int = 0
    last_reload_at: str | None = None

    def load(self) -> None:
        self.load_calls += 1

    def reload(self) -> None:
        self.reload_calls += 1
        self.last_reload_at = "2026-07-14T12:00:00+00:00"

    def runtime_snapshot(self, **_: Any) -> dict[str, Any]:
        return {
            "ready": True,
            "backend_mode": "file",
            "build_id": "test-build",
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
            "last_loaded_at": "2026-07-14T11:59:00+00:00",
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


def _install_fake_runtime(monkeypatch) -> tuple[_FakeRuntime, _FakeDiscoveryService]:
    runtime = _FakeRuntime()
    discovery = _FakeDiscoveryService()
    monkeypatch.setattr(app_module, "get_runtime", lambda: runtime)
    monkeypatch.setattr(app_module, "get_discovery_service", lambda: discovery)
    return runtime, discovery


def test_repeated_graph_store_load_reuses_cache(tmp_path):
    graph_root = _write_graph_fixture(
        tmp_path / "citation_reference_graph" / "v0.1",
        target_title="Target Paper v1",
    )

    first = app_module._load_citation_graph_store_cached(str(graph_root))
    cache_after_first = app_module._load_citation_graph_store_cached.cache_info()
    second = app_module._load_citation_graph_store_cached(str(graph_root))
    cache_after_second = app_module._load_citation_graph_store_cached.cache_info()

    assert second is first
    assert cache_after_first.misses == 1
    assert cache_after_second.misses == 1
    assert cache_after_second.hits == 1
    assert cache_after_second.currsize == 1


def test_reload_clears_graph_store_cache_and_reloads_replaced_files(
    tmp_path,
    monkeypatch,
):
    graph_root = _write_graph_fixture(
        tmp_path / "citation_reference_graph" / "v0.1",
        target_title="Target Paper v1",
    )

    first = app_module._load_citation_graph_store_cached(str(graph_root))
    assert first.nodes_by_id["paper:b"]["title"] == "Target Paper v1"

    _write_graph_fixture(graph_root, target_title="Target Paper v2")

    still_cached = app_module._load_citation_graph_store_cached(str(graph_root))
    assert still_cached is first
    assert still_cached.nodes_by_id["paper:b"]["title"] == "Target Paper v1"

    runtime, discovery = _install_fake_runtime(monkeypatch)
    monkeypatch.setattr(app_module.settings, "enable_reload_endpoint", True)

    with TestClient(app) as client:
        response = client.post("/reload")

    assert response.status_code == 200
    assert response.json()["status"] == "reloaded"
    assert runtime.load_calls == 1
    assert runtime.reload_calls == 1
    assert discovery.reload_calls == 1

    reloaded = app_module._load_citation_graph_store_cached(str(graph_root))
    assert reloaded is not first
    assert reloaded.nodes_by_id["paper:b"]["title"] == "Target Paper v2"


def test_reload_does_not_mutate_graph_artifacts(tmp_path, monkeypatch):
    graph_root = _write_graph_fixture(
        tmp_path / "citation_reference_graph" / "v0.1",
        target_title="Stable Target Paper",
    )
    before = _artifact_hashes(graph_root)

    app_module._load_citation_graph_store_cached(str(graph_root))
    runtime, discovery = _install_fake_runtime(monkeypatch)
    monkeypatch.setattr(app_module.settings, "enable_reload_endpoint", True)

    with TestClient(app) as client:
        response = client.post("/reload")

    assert response.status_code == 200
    assert runtime.reload_calls == 1
    assert discovery.reload_calls == 1
    assert _artifact_hashes(graph_root) == before


def test_disabled_reload_does_not_clear_graph_store_cache(tmp_path, monkeypatch):
    graph_root = _write_graph_fixture(
        tmp_path / "citation_reference_graph" / "v0.1",
        target_title="Target Paper v1",
    )
    first = app_module._load_citation_graph_store_cached(str(graph_root))

    _write_graph_fixture(graph_root, target_title="Target Paper v2")

    runtime, discovery = _install_fake_runtime(monkeypatch)
    monkeypatch.setattr(app_module.settings, "enable_reload_endpoint", False)

    with TestClient(app) as client:
        response = client.post("/reload")

    assert response.status_code == 404
    assert runtime.load_calls == 1
    assert runtime.reload_calls == 0
    assert discovery.reload_calls == 0

    still_cached = app_module._load_citation_graph_store_cached(str(graph_root))
    assert still_cached is first
    assert still_cached.nodes_by_id["paper:b"]["title"] == "Target Paper v1"
