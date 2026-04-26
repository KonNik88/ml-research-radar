"""
Integration tests for GitHub artifact enrichment exposure in the DB backend.

Run after:
    python -m scripts.enrich.enrich_github_artifacts --limit 5
    python -m scripts.export.export_artifacts_postgres_v1 --replace

Then:
    ML_RADAR_SEARCH_BACKEND=db
    python -m pytest tests/integration/test_api_github_enrichment_db.py -q
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# This file is DB-backend only. Set env before importing the app.
os.environ["ML_RADAR_SEARCH_BACKEND"] = "db"

from services.api.settings import get_settings  # noqa: E402

get_settings.cache_clear()

from services.api.app import app  # noqa: E402


GITHUB_ENRICHMENT_REPORT = Path(
    "artifacts/reports/validation/github_artifact_enrichment_latest.json"
)


@pytest.fixture
def client() -> TestClient:
    os.environ["ML_RADAR_SEARCH_BACKEND"] = "db"
    get_settings.cache_clear()

    with TestClient(app) as test_client:
        yield test_client


def _load_enrichment_report() -> dict:
    if not GITHUB_ENRICHMENT_REPORT.exists():
        pytest.skip("GitHub enrichment report does not exist yet")

    with GITHUB_ENRICHMENT_REPORT.open("r", encoding="utf-8") as f:
        return json.load(f)


def test_github_enrichment_report_sane() -> None:
    report = _load_enrichment_report()

    assert report["report_name"] == "github_artifact_enrichment"
    assert report["requested_count"] >= 0
    assert "status_distribution" in report
    assert "token_present" in report


def test_github_enrichment_visible_in_artifacts_api(client: TestClient) -> None:
    report = _load_enrichment_report()

    if int(report.get("found_count") or 0) <= 0:
        pytest.skip("No found GitHub repositories in latest enrichment report")

    response = client.get(
        "/artifacts",
        params={
            "provider": "github",
            "limit": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 0
    assert payload["results"]

    enriched_items = []
    for item in payload["results"]:
        metadata = item.get("metadata") or {}
        github_meta = metadata.get("github") or {}
        if github_meta.get("status") == "found" or item.get("fetched_at"):
            enriched_items.append(item)

    assert enriched_items, (
        "Latest enrichment report has found_count > 0, but /artifacts?provider=github "
        "does not expose any enriched GitHub metadata. Re-run artifact export with GitHub metadata."
    )

    first = enriched_items[0]
    assert first["provider"] == "github"
    assert first["artifact_type"] == "github_repository"

    github_meta = (first.get("metadata") or {}).get("github") or {}
    assert github_meta.get("status") == "found" or first.get("fetched_at") is not None
    assert "github_api_url" in github_meta or first.get("normalized_url", "").startswith("https://github.com/")
