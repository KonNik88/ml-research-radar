from __future__ import annotations

from fastapi.testclient import TestClient

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