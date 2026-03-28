from fastapi.testclient import TestClient

from services.api.app import app


def test_runtime_db_smoke():
    with TestClient(app) as client:
        response = client.get("/runtime")
        assert response.status_code == 200
        body = response.json()
        assert body["backend_mode"] == "db"


def test_documents_db_smoke():
    with TestClient(app) as client:
        response = client.get("/documents", params={"limit": 3})
        assert response.status_code == 200
        body = response.json()
        assert "results" in body
        assert len(body["results"]) <= 3


def test_search_db_lexical_smoke():
    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={
                "query": "graph neural networks",
                "mode": "lexical",
                "top_k": 5,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "graph neural networks"
        assert body["mode"] == "lexical"
        assert "results" in body
        assert len(body["results"]) <= 5


def test_search_db_lexical_with_filters():
    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={
                "query": "learning",
                "mode": "lexical",
                "year_from": 2023,
                "year_to": 2026,
                "top_k": 5,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "lexical"
        assert "results" in body


def test_search_db_dense_rejected():
    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={
                "query": "graph representation learning",
                "mode": "dense",
                "top_k": 3,
            },
        )
        assert response.status_code == 400
        body = response.json()
        assert body["error_code"] == "bad_request"
        assert "not supported for db backend v1" in body["message"].lower()


def test_search_db_hybrid_rejected():
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
        assert response.status_code == 400
        body = response.json()
        assert body["error_code"] == "bad_request"
        assert "not supported for db backend v1" in body["message"].lower()