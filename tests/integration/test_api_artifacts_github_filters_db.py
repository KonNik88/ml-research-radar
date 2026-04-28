"""
Integration tests for enriched GitHub artifact filters in the DB backend.

Run with:
    ML_RADAR_SEARCH_BACKEND=db
    python -m pytest tests/integration/test_api_artifacts_github_filters_db.py -q
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# This file is DB-backend only. Set env before importing the app.
os.environ["ML_RADAR_SEARCH_BACKEND"] = "db"

from services.api.settings import get_settings  # noqa: E402

get_settings.cache_clear()

from services.api.app import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    os.environ["ML_RADAR_SEARCH_BACKEND"] = "db"
    get_settings.cache_clear()

    with TestClient(app) as test_client:
        yield test_client


def _github_meta(item: dict) -> dict:
    return (item.get("metadata") or {}).get("github") or {}


def _non_null_values(items: list[dict], field: str) -> list[int]:
    return [int(item[field]) for item in items if item.get(field) is not None]


def test_artifacts_filter_min_stars(client: TestClient) -> None:
    response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "min_stars": 100,
            "limit": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 0
    assert payload["results"]

    for item in payload["results"]:
        assert item["provider"] == "github"
        assert item["stars"] is not None
        assert item["stars"] >= 100


def test_artifacts_filter_max_stars(client: TestClient) -> None:
    response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "max_stars": 100,
            "limit": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    for item in payload["results"]:
        assert item["provider"] == "github"
        assert item["stars"] is not None
        assert item["stars"] <= 100


def test_artifacts_filter_language_case_insensitive(client: TestClient) -> None:
    response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "language": "python",
            "limit": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 0
    assert payload["results"]

    for item in payload["results"]:
        assert item["provider"] == "github"
        assert _github_meta(item).get("language", "").lower() == "python"


def test_artifacts_filter_license_case_insensitive(client: TestClient) -> None:
    response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "license": "MIT",
            "limit": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 0
    assert payload["results"]

    for item in payload["results"]:
        assert item["provider"] == "github"
        assert item["license"] is not None
        assert item["license"].lower() == "mit"


def test_artifacts_filter_github_status_found(client: TestClient) -> None:
    response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "github_status": "found",
            "limit": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 0
    assert payload["results"]

    for item in payload["results"]:
        assert item["provider"] == "github"
        assert _github_meta(item).get("status") == "found"


def test_artifacts_filter_github_status_not_found(client: TestClient) -> None:
    response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "github_status": "not_found",
            "limit": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 0

    for item in payload["results"]:
        assert item["provider"] == "github"
        assert _github_meta(item).get("status") == "not_found"


def test_artifacts_filter_archived_false_only_explicit_github_metadata(client: TestClient) -> None:
    response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "archived": "false",
            "limit": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 0
    assert payload["results"]

    for item in payload["results"]:
        assert item["provider"] == "github"
        assert _github_meta(item).get("archived") is False


def test_artifacts_filter_has_github_metadata_true(client: TestClient) -> None:
    response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "has_github_metadata": "true",
            "limit": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 0
    assert payload["results"]

    for item in payload["results"]:
        assert item["provider"] == "github"
        assert "github" in (item.get("metadata") or {})


def test_artifacts_filter_has_github_metadata_false_diagnostic(client: TestClient) -> None:
    response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "has_github_metadata": "false",
            "limit": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    for item in payload["results"]:
        assert item["provider"] == "github"
        assert "github" not in (item.get("metadata") or {})


def test_artifacts_sort_stars_desc(client: TestClient) -> None:
    response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "has_github_metadata": "true",
            "sort_by": "stars_desc",
            "limit": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sort_by"] == "stars_desc"
    assert payload["results"]

    stars = _non_null_values(payload["results"], "stars")
    assert stars == sorted(stars, reverse=True)

    seen_null = False
    for item in payload["results"]:
        if item.get("stars") is None:
            seen_null = True
        if seen_null:
            assert item.get("stars") is None


def test_artifacts_sort_forks_desc(client: TestClient) -> None:
    response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "has_github_metadata": "true",
            "sort_by": "forks_desc",
            "limit": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sort_by"] == "forks_desc"
    assert payload["results"]

    forks = _non_null_values(payload["results"], "forks")
    assert forks == sorted(forks, reverse=True)

    seen_null = False
    for item in payload["results"]:
        if item.get("forks") is None:
            seen_null = True
        if seen_null:
            assert item.get("forks") is None


def test_artifacts_min_stars_greater_than_max_stars_returns_400(client: TestClient) -> None:
    response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "min_stars": 100,
            "max_stars": 10,
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "bad_request"
    assert "min_stars" in payload["message"]


def test_artifacts_invalid_sort_by_returns_validation_error(client: TestClient) -> None:
    response = client.get(
        "/artifacts",
        params={
            "sort_by": "bad_sort",
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error_code"] == "validation_error"
