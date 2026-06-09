from __future__ import annotations

from fastapi.testclient import TestClient

import services.api.app as app_module
from radar_core.retrieval.dense_backend import (
    DenseBackendCompatibilityError,
    DenseBackendRequestError,
    DenseBackendResultError,
    DenseBackendUnavailableError,
)
from services.api.app import app


def test_search_invalid_top_k_returns_400():
    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={
                "query": "machine learning",
                "mode": "lexical",
                "top_k": 1000,
            },
        )
        assert response.status_code == 400

        payload = response.json()
        assert payload["error_code"] == "bad_request"


def test_search_whitespace_query_returns_400():
    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={
                "query": "   ",
                "mode": "lexical",
            },
        )
        assert response.status_code == 400

        payload = response.json()
        assert payload["error_code"] == "bad_request"


def test_search_invalid_mode_returns_422():
    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={
                "query": "machine learning",
                "mode": "unknown_mode",
            },
        )
        assert response.status_code == 422

        payload = response.json()
        assert payload["error_code"] == "validation_error"

def test_qdrant_backend_errors_have_stable_api_contract(monkeypatch):
    cases = {
        "request": (
            DenseBackendRequestError,
            400,
            "dense_backend_bad_request",
        ),
        "unavailable": (
            DenseBackendUnavailableError,
            503,
            "dense_backend_unavailable",
        ),
        "compatibility": (
            DenseBackendCompatibilityError,
            503,
            "dense_backend_incompatible",
        ),
        "result": (
            DenseBackendResultError,
            503,
            "dense_backend_invalid_result",
        ),
    }

    def fail_qdrant_search(*, runtime, query: str, top_k: int):
        error_type, _, _ = cases[query]
        raise error_type(f"{query} failure")

    monkeypatch.setattr(
        app_module,
        "run_qdrant_experimental_search",
        fail_qdrant_search,
    )

    with TestClient(app) as client:
        for query, (_, expected_status, expected_error_code) in cases.items():
            response = client.get(
                "/experimental/search/qdrant",
                params={
                    "query": query,
                    "top_k": 3,
                },
            )

            assert response.status_code == expected_status

            payload = response.json()
            assert payload["error_code"] == expected_error_code
            assert payload["message"] == f"{query} failure"
            assert payload["details"] is None
            assert "results" not in payload

        health_response = client.get("/health")
        assert health_response.status_code == 200

        health_payload = health_response.json()
        assert health_payload["status"] == "ok"
        assert health_payload["ready"] is True
        assert health_payload["backend_mode"] == "file"

        dense_response = client.get(
            "/search",
            params={
                "query": "graph representation learning",
                "mode": "dense",
                "top_k": 3,
            },
        )
        assert dense_response.status_code == 200

        dense_payload = dense_response.json()
        assert dense_payload["mode"] == "dense"
        assert isinstance(dense_payload["results"], list)