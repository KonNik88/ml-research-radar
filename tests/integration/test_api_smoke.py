"""
Integration tests for file backend only.
Run with ML_RADAR_SEARCH_BACKEND=file
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from radar_core.retrieval.dense_backend import (
    DenseBackendUnavailableError,
)
from services.api.runtime import get_runtime

from services.api.app import app


class FailingQdrantBackend:
    def search(self, request):
        raise DenseBackendUnavailableError(
            "Simulated Qdrant unavailability"
        )

@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_health_smoke(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["backend_mode"] == "file"
    assert payload["ready"] is True
    assert "build_id" in payload
    assert "corpus_doc_count" in payload
    assert "checks" in payload
    assert payload["checks"]["manifest_loaded"] is True
    assert payload["checks"]["db_connected"] is False


def test_info_smoke(client: TestClient):
    response = client.get("/info")
    assert response.status_code == 200

    payload = response.json()
    assert payload["backend_mode"] == "file"
    assert "api_title" in payload
    assert "api_version" in payload
    assert "build_id" in payload
    assert "loaded_components" in payload


def test_runtime_smoke(client: TestClient):
    response = client.get(
        "/runtime",
        params={"refresh_qdrant": True},
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["ready"] is True
    assert payload["backend_mode"] == "file"
    assert payload["loaded_components"]["manifest"] is True
    assert payload["loaded_components"]["embedding_model"] is True
    assert payload["db_connected"] is False
    assert "model_reused" in payload
    assert "current_model_name" in payload
    assert isinstance(payload["qdrant"], dict)

    qdrant = payload["qdrant"]

    assert qdrant["configured"] is True
    assert qdrant["collection_name"] == "ml_radar_dense_benchmark_v1"
    assert qdrant["expected_corpus_doc_count"] == payload["corpus_doc_count"]

    assert "ok" in qdrant
    assert "collection_exists" in qdrant
    assert "points_count" in qdrant
    assert "points_match_corpus" in qdrant
    assert "error" in qdrant

    assert qdrant["probe_cached"] is False
    assert qdrant["probe_checked_at"] is not None
    assert qdrant["probe_cache_age_sec"] == 0.0
    assert qdrant["probe_ttl_sec"] == 30.0

    assert qdrant["profile_name"] == "ef_256"
    assert qdrant["exact"] is False
    assert qdrant["hnsw_ef"] == 256
    assert qdrant["build_id"] == payload["build_id"]

    assert qdrant["backend_created"] is False
    assert qdrant["compatibility_checked"] is False
    assert qdrant["compatibility_ok"] is None

    assert qdrant["request_count"] == 0
    assert qdrant["success_count"] == 0
    assert qdrant["failure_count"] == 0
    assert qdrant["last_status"] == "never"
    assert qdrant["last_request_at"] is None
    assert qdrant["last_success_at"] is None
    assert qdrant["last_failure_at"] is None
    assert qdrant["last_timing_ms"] == {}
    assert qdrant["fallback_applied"] is False

    cached_response = client.get("/runtime")
    assert cached_response.status_code == 200

    cached_qdrant = cached_response.json()["qdrant"]

    assert cached_qdrant["probe_cached"] is True
    assert (
        cached_qdrant["probe_checked_at"]
        == qdrant["probe_checked_at"]
    )
    assert cached_qdrant["probe_cache_age_sec"] is not None
    assert (
        0.0
        <= cached_qdrant["probe_cache_age_sec"]
        <= cached_qdrant["probe_ttl_sec"]
    )


def test_search_lexical_smoke(client: TestClient):
    response = client.get(
        "/search",
        params={
            "query": "machine learning",
            "mode": "lexical",
            "top_k": 3,
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["mode"] == "lexical"
    assert payload["top_k"] == 3
    assert "meta" in payload
    assert isinstance(payload["results"], list)


def test_search_dense_smoke(client: TestClient):
    response = client.get(
        "/search",
        params={
            "query": "graph representation learning",
            "mode": "dense",
            "top_k": 3,
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["mode"] == "dense"
    assert "meta" in payload
    assert isinstance(payload["results"], list)


def test_search_hybrid_ranked_smoke(client: TestClient):
    response = client.get(
        "/search",
        params={
            "query": "graph neural networks",
            "mode": "hybrid",
            "top_k": 5,
            "rank": True,
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["mode"] == "hybrid"
    assert payload["rank_applied"] is True
    assert "meta" in payload
    assert "timing_ms" in payload["meta"]
    assert isinstance(payload["results"], list)

    if payload["results"]:
        first = payload["results"][0]
        assert "document" in first
        assert "retrieval" in first

def test_qdrant_failure_is_visible_in_runtime_state(
    client: TestClient,
    monkeypatch,
):
    runtime = get_runtime()

    initial_request_count = (
        runtime.qdrant_operational_state.request_count
    )
    initial_failure_count = (
        runtime.qdrant_operational_state.failure_count
    )

    failing_backend = FailingQdrantBackend()

    monkeypatch.setattr(
        runtime,
        "get_qdrant_dense_backend",
        lambda: failing_backend,
    )

    response = client.get(
        "/experimental/search/qdrant",
        params={
            "query": "protein language models",
            "top_k": 3,
        },
    )

    assert response.status_code == 503
    assert response.json()["error_code"] == "dense_backend_unavailable"

    runtime_response = client.get("/runtime")
    assert runtime_response.status_code == 200

    qdrant = runtime_response.json()["qdrant"]

    assert qdrant["request_count"] == initial_request_count + 1
    assert qdrant["failure_count"] == initial_failure_count + 1
    assert qdrant["last_status"] == "error"
    assert qdrant["last_request_at"] is not None
    assert qdrant["last_failure_at"] is not None
    assert (
        qdrant["last_failure_category"]
        == "dense_backend_unavailable"
    )
    assert qdrant["last_failure_stage"] == "backend_search"
    assert (
        qdrant["last_failure_message"]
        == "Simulated Qdrant unavailability"
    )
    assert "encode_ms" in qdrant["last_timing_ms"]
    assert "total_ms" in qdrant["last_timing_ms"]

    assert qdrant["requested_vector_backend"] == "qdrant"
    assert qdrant["effective_vector_backend"] is None
    assert qdrant["fallback_applied"] is False

    # Optional Qdrant failure still does not affect file-runtime readiness.
    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["ready"] is True