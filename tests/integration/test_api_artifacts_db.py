"""
Integration tests for artifact API in DB backend only.

Run with:
    ML_RADAR_SEARCH_BACKEND=db
    python -m pytest tests/integration/test_api_artifacts_db.py -q
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

def _get_canonical_with_dataset_artifact(client: TestClient) -> str:
    response = client.get(
        "/documents",
        params={
            "has_trusted_dataset_artifact": "true",
            "limit": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    if payload["total"] <= 0 or not payload["results"]:
        pytest.skip("No documents with trusted dataset artifacts in current DB snapshot")

    return payload["results"][0]["canonical_id"]

@pytest.fixture
def client() -> TestClient:
    os.environ["ML_RADAR_SEARCH_BACKEND"] = "db"
    get_settings.cache_clear()

    with TestClient(app) as test_client:
        yield test_client


def test_runtime_db_backend_for_artifact_tests(client: TestClient) -> None:
    response = client.get("/runtime")

    assert response.status_code == 200
    payload = response.json()

    assert payload["ready"] is True
    assert payload["backend_mode"] == "db"
    assert payload["db_connected"] is True
    assert payload["loaded_components"]["db_store"] is True


def test_artifacts_list_db_smoke(client: TestClient) -> None:
    response = client.get("/artifacts", params={"limit": 3})

    assert response.status_code == 200
    payload = response.json()

    assert payload["total"] > 0
    assert payload["offset"] == 0
    assert payload["limit"] == 3
    assert payload["sort_by"] == "linked_papers_desc"
    assert "results" in payload
    assert 1 <= len(payload["results"]) <= 3

    first = payload["results"][0]
    assert "artifact_id" in first
    assert "artifact_type" in first
    assert "provider" in first
    assert "normalized_url" in first
    assert "canonical_url" in first
    assert "linked_papers_count" in first
    assert "relation_types" in first


def test_artifacts_provider_filter_github(client: TestClient) -> None:
    response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["total"] > 0
    assert 1 <= len(payload["results"]) <= 5

    for item in payload["results"]:
        assert item["provider"] == "github"
        assert item["artifact_type"] == "github_repository"
        assert item["normalized_url"].startswith("https://github.com/")


def test_artifacts_relation_type_filter_code(client: TestClient) -> None:
    response = client.get(
        "/artifacts",
        params={
            "relation_type": "code",
            "limit": 10,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["total"] > 0
    assert 1 <= len(payload["results"]) <= 10

    for item in payload["results"]:
        assert "code" in item["relation_types"]


def test_artifacts_has_paper_links_filter(client: TestClient) -> None:
    response = client.get(
        "/artifacts",
        params={
            "has_paper_links": "true",
            "limit": 10,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["total"] > 0
    assert 1 <= len(payload["results"]) <= 10

    for item in payload["results"]:
        assert item["linked_papers_count"] is not None
        assert item["linked_papers_count"] > 0


def test_document_artifacts_known_paper(client: TestClient) -> None:
    canonical_id = _get_canonical_with_dataset_artifact(client)

    response = client.get(f"/documents/{canonical_id}/artifacts")

    assert response.status_code == 200
    payload = response.json()

    assert payload["canonical_id"] == canonical_id
    assert payload["total"] > 0
    assert len(payload["results"]) > 0

    first = payload["results"][0]
    assert first["canonical_id"] == canonical_id
    assert first["relation_type"] in {"code", "dataset", "model", "demo"}
    assert first["confidence"] >= 0.0

    artifact = first["artifact"]
    assert artifact["artifact_id"] == first["artifact_id"]
    assert "provider" in artifact
    assert "artifact_type" in artifact
    assert "normalized_url" in artifact

    metadata = first["metadata"]
    assert isinstance(metadata, dict)
    assert "evidence" in metadata
    assert isinstance(metadata["evidence"], list)
    assert len(metadata["evidence"]) > 0


def test_document_artifacts_relation_filter_dataset(client: TestClient) -> None:
    canonical_id = _get_canonical_with_dataset_artifact(client)

    response = client.get(
        f"/documents/{canonical_id}/artifacts",
        params={"relation_type": "dataset"},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["canonical_id"] == canonical_id
    assert payload["total"] > 0

    for item in payload["results"]:
        assert item["relation_type"] == "dataset"


def test_document_artifacts_missing_document_returns_404(client: TestClient) -> None:
    response = client.get("/documents/not-a-real-canonical-id/artifacts")

    assert response.status_code == 404
    payload = response.json()

    assert payload["detail"] == "Document not found: not-a-real-canonical-id"