from __future__ import annotations

from fastapi.testclient import TestClient

from services.api.app import app
from services.api.runtime import get_runtime


def test_reload_smoke():
    with TestClient(app) as client:
        response = client.post("/reload")
        assert response.status_code == 200

        payload = response.json()
        assert payload["status"] == "reloaded"
        assert payload["backend_mode"] in {"file", "db"}
        assert "message" in payload
        assert "build_id" in payload
        assert "corpus_doc_count" in payload
        assert "embedding_model_name" in payload
        assert "model_reused" in payload
        assert "last_reload_at" in payload


def test_health_after_reload_smoke():
    with TestClient(app) as client:
        reload_response = client.post("/reload")
        assert reload_response.status_code == 200

        health_response = client.get("/health")
        assert health_response.status_code == 200

        payload = health_response.json()
        assert payload["status"] == "ok"
        assert payload["ready"] is True
        assert payload["backend_mode"] in {"file", "db"}


def test_runtime_contains_reload_state():
    with TestClient(app) as client:
        client.post("/reload")

        response = client.get("/runtime")
        assert response.status_code == 200

        payload = response.json()
        assert "last_loaded_at" in payload
        assert "last_reload_at" in payload
        assert "model_reused" in payload
        assert "current_model_name" in payload
        assert "backend_mode" in payload

def test_reload_recreates_cached_qdrant_backend():
    with TestClient(app) as client:
        runtime = get_runtime()

        assert runtime.backend_mode == "file"

        first_backend = runtime.get_qdrant_dense_backend()
        assert runtime.qdrant_dense_backend is first_backend

        response = client.post("/reload")
        assert response.status_code == 200

        assert runtime.qdrant_dense_backend is None

        second_backend = runtime.get_qdrant_dense_backend()

        assert second_backend is runtime.qdrant_dense_backend
        assert second_backend is not first_backend