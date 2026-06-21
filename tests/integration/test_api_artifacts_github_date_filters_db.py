"""
Integration tests for GitHub artifact date filters in DB backend only.

Run with:
    ML_RADAR_SEARCH_BACKEND=db
    python -m pytest tests/integration/test_api_artifacts_github_date_filters_db.py -q
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

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


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _github_metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") or {}
    github = metadata.get("github") or {}
    assert isinstance(github, dict)
    return github


def test_artifacts_github_pushed_after_filter_and_sort(client: TestClient) -> None:
    baseline_response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "github_status": "found",
            "sort_by": "pushed_desc",
            "limit": 5,
        },
    )

    assert baseline_response.status_code == 200
    baseline_payload = baseline_response.json()

    if baseline_payload["total"] <= 0 or not baseline_payload["results"]:
        pytest.skip("No found GitHub artifacts with pushed_at metadata in current DB snapshot")

    pushed_values = [
        _github_metadata(item).get("pushed_at")
        for item in baseline_payload["results"]
    ]
    pushed_values = [value for value in pushed_values if value]

    if not pushed_values:
        pytest.skip("No pushed_at values exposed in current DB snapshot")

    assert pushed_values == sorted(pushed_values, reverse=True)

    threshold = pushed_values[-1]
    filtered_response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "pushed_after": threshold,
            "sort_by": "pushed_desc",
            "limit": 5,
        },
    )

    assert filtered_response.status_code == 200
    filtered_payload = filtered_response.json()
    assert filtered_payload["total"] > 0
    assert 1 <= len(filtered_payload["results"]) <= 5

    threshold_dt = _parse_timestamp(threshold)
    returned_pushed_values: list[str] = []
    for item in filtered_payload["results"]:
        github = _github_metadata(item)
        pushed_at = github.get("pushed_at")
        assert pushed_at
        assert _parse_timestamp(pushed_at) >= threshold_dt
        returned_pushed_values.append(pushed_at)

    assert returned_pushed_values == sorted(returned_pushed_values, reverse=True)


def test_artifacts_github_updated_before_filter_and_sort(client: TestClient) -> None:
    baseline_response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "github_status": "found",
            "sort_by": "updated_desc",
            "limit": 5,
        },
    )

    assert baseline_response.status_code == 200
    baseline_payload = baseline_response.json()

    if baseline_payload["total"] <= 0 or not baseline_payload["results"]:
        pytest.skip("No found GitHub artifacts with updated_at metadata in current DB snapshot")

    updated_values = [item.get("updated_at") for item in baseline_payload["results"]]
    updated_values = [value for value in updated_values if value]

    if not updated_values:
        pytest.skip("No updated_at values exposed in current DB snapshot")

    assert updated_values == sorted(updated_values, reverse=True)

    threshold = updated_values[0]
    filtered_response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "updated_before": threshold,
            "sort_by": "updated_desc",
            "limit": 5,
        },
    )

    assert filtered_response.status_code == 200
    filtered_payload = filtered_response.json()
    assert filtered_payload["total"] > 0
    assert 1 <= len(filtered_payload["results"]) <= 5

    threshold_dt = _parse_timestamp(threshold)
    returned_updated_values: list[str] = []
    for item in filtered_payload["results"]:
        updated_at = item.get("updated_at")
        assert updated_at
        assert _parse_timestamp(updated_at) <= threshold_dt
        returned_updated_values.append(updated_at)

    assert returned_updated_values == sorted(returned_updated_values, reverse=True)


def test_artifacts_github_pushed_date_range_validation(client: TestClient) -> None:
    response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "pushed_after": "2030-01-01T00:00:00Z",
            "pushed_before": "2000-01-01T00:00:00Z",
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "bad_request"
    assert "pushed_after" in payload["message"]


def test_artifacts_github_updated_date_range_validation(client: TestClient) -> None:
    response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "updated_after": "2030-01-01T00:00:00Z",
            "updated_before": "2000-01-01T00:00:00Z",
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "bad_request"
    assert "updated_after" in payload["message"]
