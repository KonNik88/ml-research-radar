"""
Integration tests for file backend only.
Run with ML_RADAR_SEARCH_BACKEND=file
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.api.app import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _extract_years(payload: dict) -> list[int]:
    years: list[int] = []
    for item in payload.get("results", []):
        year = item.get("document", {}).get("year")
        if year is not None:
            years.append(year)
    return years


def test_search_with_year_from_filter(client: TestClient) -> None:
    response = client.get(
        "/search",
        params={
            "query": "graph neural networks",
            "mode": "hybrid",
            "top_k": 5,
            "rank": "true",
            "year_from": 2024,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["query"] == "graph neural networks"
    assert payload["mode"] == "hybrid"
    assert payload["rank_applied"] is True
    assert payload["meta"]["applied_filters"]["year_from"] == 2024

    for item in payload["results"]:
        year = item["document"]["year"]
        assert year is not None
        assert year >= 2024


def test_search_with_category_filter(client: TestClient) -> None:
    response = client.get(
        "/search",
        params={
            "query": "graph neural networks",
            "mode": "hybrid",
            "top_k": 5,
            "rank": "true",
            "category": "cs.LG",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["meta"]["applied_filters"]["category"] == "cs.LG"
    assert (
        payload["meta"]["retrieved_candidates_after_filters"]
        <= payload["meta"]["retrieved_candidates_before_filters"]
    )

    for item in payload["results"]:
        doc = item["document"]
        primary = doc.get("primary_category")
        categories = doc.get("categories", [])
        tags = doc.get("tags", [])

        assert (
            primary == "cs.LG"
            or "cs.LG" in categories
            or "cs.LG" in tags
        )


def test_search_with_source_filter(client: TestClient) -> None:
    response = client.get(
        "/search",
        params={
            "query": "graph neural networks",
            "mode": "hybrid",
            "top_k": 5,
            "rank": "true",
            "source": "arxiv",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["meta"]["applied_filters"]["source"] == "arxiv"
    assert payload["meta"]["returned_count"] == len(payload["results"])
    assert (
        payload["meta"]["retrieved_candidates_after_filters"]
        <= payload["meta"]["retrieved_candidates_before_filters"]
    )


def test_search_with_offset_changes_results(client: TestClient) -> None:
    response_0 = client.get(
        "/search",
        params={
            "query": "graph neural networks",
            "mode": "hybrid",
            "top_k": 5,
            "rank": "true",
            "offset": 0,
        },
    )
    response_2 = client.get(
        "/search",
        params={
            "query": "graph neural networks",
            "mode": "hybrid",
            "top_k": 5,
            "rank": "true",
            "offset": 2,
        },
    )

    assert response_0.status_code == 200
    assert response_2.status_code == 200

    payload_0 = response_0.json()
    payload_2 = response_2.json()

    ids_0 = [item["document"]["canonical_id"] for item in payload_0["results"]]
    ids_2 = [item["document"]["canonical_id"] for item in payload_2["results"]]

    assert payload_0["meta"]["offset"] == 0
    assert payload_2["meta"]["offset"] == 2
    assert ids_0 != ids_2


def test_search_with_sort_by_year_desc(client: TestClient) -> None:
    response = client.get(
        "/search",
        params={
            "query": "graph neural networks",
            "mode": "hybrid",
            "top_k": 10,
            "rank": "true",
            "sort_by": "year_desc",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["meta"]["sort_by"] == "year_desc"

    years = _extract_years(payload)
    assert years == sorted(years, reverse=True)


def test_search_invalid_year_range(client: TestClient) -> None:
    response = client.get(
        "/search",
        params={
            "query": "graph neural networks",
            "mode": "hybrid",
            "top_k": 5,
            "rank": "true",
            "year_from": 2026,
            "year_to": 2024,
        },
    )

    assert response.status_code == 400
    payload = response.json()

    assert payload["error_code"] == "bad_request"
    assert "year_from" in payload["message"]


def test_search_invalid_sort_by(client: TestClient) -> None:
    response = client.get(
        "/search",
        params={
            "query": "graph neural networks",
            "mode": "hybrid",
            "top_k": 5,
            "rank": "true",
            "sort_by": "wrong_sort",
        },
    )

    assert response.status_code == 422
    payload = response.json()

    assert payload["error_code"] == "validation_error"