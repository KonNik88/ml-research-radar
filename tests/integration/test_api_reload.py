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
        qdrant = payload["qdrant"]

        assert qdrant["request_count"] == 0
        assert qdrant["success_count"] == 0
        assert qdrant["failure_count"] == 0
        assert qdrant["last_status"] == "never"
        assert qdrant["last_request_at"] is None
        assert qdrant["last_success_at"] is None
        assert qdrant["last_failure_at"] is None
        assert qdrant["last_failure_category"] is None
        assert qdrant["last_failure_stage"] is None
        assert qdrant["last_failure_message"] is None
        assert qdrant["last_timing_ms"] == {}
        assert qdrant["fallback_applied"] is False

def test_reload_recreates_cached_qdrant_backend_and_resets_observability():
    with TestClient(app) as client:
        runtime = get_runtime()

        assert runtime.backend_mode == "file"

        first_backend = runtime.get_qdrant_dense_backend()
        assert runtime.qdrant_dense_backend is first_backend

        runtime.record_qdrant_request_started()
        runtime.record_qdrant_failure(
            category="dense_backend_unavailable",
            stage="backend_search",
            message="Simulated failure before reload",
            timing_ms={
                "encode_ms": 1.0,
                "total_ms": 2.0,
            },
        )

        runtime._qdrant_diagnostics_cache = {
            "configured": True,
            "ok": False,
        }
        runtime._qdrant_diagnostics_cached_at_monotonic = 1.0
        runtime._qdrant_diagnostics_checked_at = (
            "2026-06-10T00:00:00+00:00"
        )

        assert runtime.qdrant_operational_state.request_count == 1
        assert runtime.qdrant_operational_state.failure_count == 1
        assert runtime._qdrant_diagnostics_cache is not None

        response = client.post("/reload")
        assert response.status_code == 200

        assert runtime.qdrant_dense_backend is None

        state = runtime.qdrant_operational_state

        assert state.request_count == 0
        assert state.success_count == 0
        assert state.failure_count == 0
        assert state.last_status == "never"
        assert state.last_request_at is None
        assert state.last_success_at is None
        assert state.last_failure_at is None
        assert state.last_failure_category is None
        assert state.last_failure_stage is None
        assert state.last_failure_message is None
        assert state.last_result_count is None
        assert state.last_timing_ms == {}
        assert state.requested_vector_backend is None
        assert state.effective_vector_backend is None
        assert state.fallback_applied is False

        assert runtime._qdrant_diagnostics_cache is None
        assert (
            runtime._qdrant_diagnostics_cached_at_monotonic
            is None
        )
        assert runtime._qdrant_diagnostics_checked_at is None

        second_backend = runtime.get_qdrant_dense_backend()

        assert second_backend is runtime.qdrant_dense_backend
        assert second_backend is not first_backend