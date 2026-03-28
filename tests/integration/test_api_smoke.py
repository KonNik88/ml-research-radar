"""
Integration tests for file backend only.
Run with ML_RADAR_SEARCH_BACKEND=file
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from services.api.app import app


def test_health_smoke():
    with TestClient(app) as client:
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


def test_info_smoke():
    with TestClient(app) as client:
        response = client.get("/info")
        assert response.status_code == 200

        payload = response.json()
        assert payload["backend_mode"] == "file"
        assert "api_title" in payload
        assert "api_version" in payload
        assert "build_id" in payload
        assert "loaded_components" in payload


def test_runtime_smoke():
    with TestClient(app) as client:
        response = client.get("/runtime")
        assert response.status_code == 200

        payload = response.json()
        assert payload["ready"] is True
        assert payload["backend_mode"] == "file"
        assert payload["loaded_components"]["manifest"] is True
        assert payload["loaded_components"]["embedding_model"] is True
        assert payload["db_connected"] is False
        assert "model_reused" in payload
        assert "current_model_name" in payload


def test_search_lexical_smoke():
    with TestClient(app) as client:
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


def test_search_dense_smoke():
    with TestClient(app) as client:
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


def test_search_hybrid_ranked_smoke():
    with TestClient(app) as client:
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