"""
Integration tests for /documents trusted artifact filters in DB backend.

Run with:
    ML_RADAR_SEARCH_BACKEND=db
    python -m pytest tests/integration/test_api_documents_artifact_filters_db.py -q
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


def _assert_document_list_payload(payload: dict) -> None:
    assert "total" in payload
    assert "offset" in payload
    assert "limit" in payload
    assert "sort_by" in payload
    assert "results" in payload
    assert isinstance(payload["results"], list)


def _assert_doc_has_artifact(
    client: TestClient,
    canonical_id: str,
    *,
    relation_type: str | None = None,
    provider: str | None = None,
    artifact_type: str | None = None,
) -> None:
    params: dict[str, str] = {}

    if relation_type:
        params["relation_type"] = relation_type

    if provider:
        params["provider"] = provider

    if artifact_type:
        params["artifact_type"] = artifact_type

    response = client.get(f"/documents/{canonical_id}/artifacts", params=params)

    assert response.status_code == 200
    payload = response.json()
    assert payload["canonical_id"] == canonical_id
    assert payload["total"] > 0
    assert len(payload["results"]) > 0

    for item in payload["results"]:
        if relation_type:
            assert item["relation_type"] == relation_type

        artifact = item["artifact"]

        if provider:
            assert artifact["provider"] == provider

        if artifact_type:
            assert artifact["artifact_type"] == artifact_type


def test_documents_has_trusted_artifact_filter(client: TestClient) -> None:
    response = client.get(
        "/documents",
        params={
            "has_trusted_artifact": "true",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    _assert_document_list_payload(payload)

    assert payload["total"] > 0
    assert 1 <= len(payload["results"]) <= 5

    for doc in payload["results"]:
        _assert_doc_has_artifact(client, doc["canonical_id"])


def test_documents_has_trusted_code_artifact_filter(client: TestClient) -> None:
    response = client.get(
        "/documents",
        params={
            "has_trusted_code_artifact": "true",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    _assert_document_list_payload(payload)

    assert payload["total"] > 0
    assert 1 <= len(payload["results"]) <= 5

    for doc in payload["results"]:
        _assert_doc_has_artifact(
            client,
            doc["canonical_id"],
            relation_type="code",
        )


def test_documents_has_trusted_dataset_artifact_filter(client: TestClient) -> None:
    response = client.get(
        "/documents",
        params={
            "has_trusted_dataset_artifact": "true",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    _assert_document_list_payload(payload)

    assert payload["total"] > 0
    assert 1 <= len(payload["results"]) <= 5

    for doc in payload["results"]:
        _assert_doc_has_artifact(
            client,
            doc["canonical_id"],
            relation_type="dataset",
        )


def test_documents_artifact_provider_filter_github(client: TestClient) -> None:
    response = client.get(
        "/documents",
        params={
            "artifact_provider": "github",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    _assert_document_list_payload(payload)

    assert payload["total"] > 0
    assert 1 <= len(payload["results"]) <= 5

    for doc in payload["results"]:
        _assert_doc_has_artifact(
            client,
            doc["canonical_id"],
            provider="github",
        )


def test_documents_artifact_type_filter_github_repository(client: TestClient) -> None:
    response = client.get(
        "/documents",
        params={
            "artifact_type": "github_repository",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    _assert_document_list_payload(payload)

    assert payload["total"] > 0
    assert 1 <= len(payload["results"]) <= 5

    for doc in payload["results"]:
        _assert_doc_has_artifact(
            client,
            doc["canonical_id"],
            artifact_type="github_repository",
        )


def test_documents_combined_code_and_github_filter(client: TestClient) -> None:
    response = client.get(
        "/documents",
        params={
            "has_trusted_code_artifact": "true",
            "artifact_provider": "github",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    _assert_document_list_payload(payload)

    assert payload["total"] > 0
    assert 1 <= len(payload["results"]) <= 5

    for doc in payload["results"]:
        _assert_doc_has_artifact(
            client,
            doc["canonical_id"],
            relation_type="code",
            provider="github",
        )


def test_documents_no_trusted_artifact_filter(client: TestClient) -> None:
    response = client.get(
        "/documents",
        params={
            "has_trusted_artifact": "false",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    _assert_document_list_payload(payload)

    assert payload["total"] > 0
    assert 1 <= len(payload["results"]) <= 5

    for doc in payload["results"]:
        response_artifacts = client.get(f"/documents/{doc['canonical_id']}/artifacts")
        assert response_artifacts.status_code == 200
        assert response_artifacts.json()["total"] == 0


def test_documents_legacy_has_code_link_filter_still_works(client: TestClient) -> None:
    response = client.get(
        "/documents",
        params={
            "has_code_link": "true",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    _assert_document_list_payload(payload)

    # This is the legacy canonical/source-layer flag. It is intentionally
    # separate from trusted artifact filters. We only assert the endpoint and
    # schema still work, because its count depends on canonical source fields.
    assert payload["total"] >= 0
    assert len(payload["results"]) <= 5