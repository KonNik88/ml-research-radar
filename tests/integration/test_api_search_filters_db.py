from fastapi.testclient import TestClient

from services.api.app import app


def test_search_db_with_year_from_filter():
    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={
                "query": "learning",
                "mode": "lexical",
                "top_k": 5,
                "year_from": 2024,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "lexical"
        assert "results" in body


def test_search_db_with_category_filter():
    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={
                "query": "learning",
                "mode": "lexical",
                "top_k": 5,
                "category": "cs.LG",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert "results" in body


def test_search_db_with_source_filter():
    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={
                "query": "learning",
                "mode": "lexical",
                "top_k": 5,
                "source": "arxiv",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert "results" in body


def test_search_db_with_offset_changes_results():
    with TestClient(app) as client:
        response_0 = client.get(
            "/search",
            params={
                "query": "learning",
                "mode": "lexical",
                "top_k": 5,
                "offset": 0,
            },
        )
        response_2 = client.get(
            "/search",
            params={
                "query": "learning",
                "mode": "lexical",
                "top_k": 5,
                "offset": 2,
            },
        )

        assert response_0.status_code == 200
        assert response_2.status_code == 200

        body_0 = response_0.json()
        body_2 = response_2.json()

        assert "results" in body_0
        assert "results" in body_2


def test_search_db_with_sort_by_year_desc():
    with TestClient(app) as client:
        response = client.get(
            "/search",
            params={
                "query": "learning",
                "mode": "lexical",
                "top_k": 10,
                "sort_by": "year_desc",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert "results" in body