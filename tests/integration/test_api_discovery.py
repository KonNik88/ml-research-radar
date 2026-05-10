from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.api.app import app


KNOWN_DISCOVERY_CANONICAL_ID = "bd3c9332f17370fa801e6ac9542f125a"


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_discovery_profiles_smoke(client: TestClient) -> None:
    response = client.get("/discovery/profiles")

    assert response.status_code == 200
    payload = response.json()

    assert payload["schema_version"] == "ranking_profiles_v1"
    assert payload["profile_count"] > 0
    assert payload["default_profile"] == "recent_artifact_ready"

    names = {profile["name"] for profile in payload["profiles"]}
    assert "huggingface_ready" in names
    assert "recent_artifact_ready" in names
    assert "acl_radar" in names


def test_discovery_ranking_profile_smoke(client: TestClient) -> None:
    response = client.get(
        "/discovery/ranking/huggingface_ready",
        params={"top_k": 5},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["mode"] == "ranking"
    assert payload["profile"]["name"] == "huggingface_ready"
    assert payload["top_k"] == 5
    assert payload["input_rows_count"] > 0
    assert payload["filtered_rows_count"] > 0
    assert 1 <= payload["returned_rows_count"] <= 5
    assert payload["results"]

    first = payload["results"][0]
    assert "canonical_id" in first
    assert "title" in first
    assert "implementation_readiness_score" in first


def test_discovery_unknown_profile_returns_404(client: TestClient) -> None:
    response = client.get("/discovery/ranking/not_a_real_profile")

    assert response.status_code == 404


def test_discovery_paper_detail_smoke(client: TestClient) -> None:
    response = client.get(f"/discovery/papers/{KNOWN_DISCOVERY_CANONICAL_ID}")

    assert response.status_code == 200
    payload = response.json()

    assert payload["canonical_id"] == KNOWN_DISCOVERY_CANONICAL_ID
    assert payload["found"] is True

    detail = payload["detail"]
    assert detail["canonical_id"] == KNOWN_DISCOVERY_CANONICAL_ID
    assert detail["found"] is True
    assert detail["canonical_found"] is True
    assert detail["features_found"] is True
    assert "title" in detail
    assert "scores" in detail
    assert "artifacts" in detail


def test_discovery_paper_detail_missing_returns_404(client: TestClient) -> None:
    response = client.get("/discovery/papers/not-a-real-canonical-id")

    assert response.status_code == 404


def test_discovery_similar_smoke(client: TestClient) -> None:
    response = client.get(
        f"/discovery/papers/{KNOWN_DISCOVERY_CANONICAL_ID}/similar",
        params={"top_k": 5},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["mode"] == "similar_papers"
    assert payload["target_canonical_id"] == KNOWN_DISCOVERY_CANONICAL_ID
    assert payload["target_found"] is True
    assert payload["rank_by"] == "semantic"
    assert payload["input_rows_count"] > 0
    assert 1 <= payload["returned_rows_count"] <= 5
    assert payload["results"]

    result_ids = [row["canonical_id"] for row in payload["results"]]
    assert KNOWN_DISCOVERY_CANONICAL_ID not in result_ids


def test_discovery_similar_radar_adjusted_smoke(client: TestClient) -> None:
    response = client.get(
        f"/discovery/papers/{KNOWN_DISCOVERY_CANONICAL_ID}/similar",
        params={"top_k": 5, "rank_by": "radar_adjusted"},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["rank_by"] == "radar_adjusted"
    assert payload["results"]

    scores = [row["radar_adjusted_similarity"] for row in payload["results"]]
    assert scores == sorted(scores, reverse=True)

def test_discovery_ranking_combined_overrides(client: TestClient) -> None:
    response = client.get(
        "/discovery/ranking/recent_artifact_ready",
        params={
            "top_k": 5,
            "min_year": 2025,
            "has_code": "true",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["mode"] == "ranking"
    assert payload["profile"]["name"] == "recent_artifact_ready"
    assert payload["top_k"] == 5
    assert payload["filters"]["min_year"] == 2025
    assert payload["filters"]["has_code"] is True
    assert payload["results"]
    assert 1 <= payload["returned_rows_count"] <= 5

    for row in payload["results"]:
        assert row["year"] is not None
        assert row["year"] >= 2025
        assert row["has_code_artifact"] is True


def test_discovery_ranking_false_boolean_override(client: TestClient) -> None:
    response = client.get(
        "/discovery/ranking/huggingface_ready",
        params={
            "top_k": 5,
            "has_hf": "false",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["profile"]["name"] == "huggingface_ready"
    assert payload["profile"]["filters"]["has_hf"] is True
    assert payload["filters"]["has_hf"] is False
    assert payload["results"]


def test_discovery_ranking_sort_by_override(client: TestClient) -> None:
    response = client.get(
        "/discovery/ranking/recent_artifact_ready",
        params={
            "top_k": 5,
            "has_github": "true",
            "sort_by": "github_stars_max",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["sort_by"] == "github_stars_max"
    assert payload["filters"]["has_github"] is True
    assert payload["results"]

    stars = [int(row.get("github_stars_max") or 0) for row in payload["results"]]
    assert stars == sorted(stars, reverse=True)


def test_discovery_ranking_invalid_year_range_returns_400(client: TestClient) -> None:
    response = client.get(
        "/discovery/ranking/recent_artifact_ready",
        params={
            "min_year": 2026,
            "max_year": 2025,
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "bad_request"
    assert "min_year" in payload["message"]


def test_discovery_ranking_invalid_sort_by_returns_422(client: TestClient) -> None:
    response = client.get(
        "/discovery/ranking/recent_artifact_ready",
        params={
            "sort_by": "not_a_sort_field",
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error_code"] == "validation_error"


def test_discovery_ranking_top_k_too_large_returns_422(client: TestClient) -> None:
    response = client.get(
        "/discovery/ranking/recent_artifact_ready",
        params={
            "top_k": 101,
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error_code"] == "validation_error"