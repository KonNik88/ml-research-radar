from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.api.app import app


KNOWN_DISCOVERY_CANONICAL_ID = "bd3c9332f17370fa801e6ac9542f125a"


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _first_cluster_id(client: TestClient) -> int:
    response = client.get("/discovery/clusters", params={"limit": 1})
    assert response.status_code == 200
    payload = response.json()
    assert payload["results"]
    cluster_id = payload["results"][0]["cluster_id"]
    assert isinstance(cluster_id, int)
    return cluster_id


def _comparison_ids(client: TestClient, count: int) -> list[str]:
    response = client.get(
        "/discovery/ranking/recent_artifact_ready",
        params={"top_k": count},
    )
    assert response.status_code == 200
    ids = [
        str(row["canonical_id"])
        for row in response.json()["results"]
        if row.get("canonical_id")
    ]
    if len(ids) < count:
        pytest.skip(f"Comparison smoke requires {count} ranking papers")
    return ids[:count]


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


def test_discovery_paper_comparison_two_papers_preserves_order(
    client: TestClient,
) -> None:
    canonical_ids = _comparison_ids(client, 2)

    response = client.post(
        "/discovery/papers/compare",
        json={"canonical_ids": canonical_ids},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "paper_comparison_v0.1"
    assert payload["mode"] == "paper_comparison"
    assert payload["canonical_ids"] == canonical_ids
    assert payload["paper_count"] == 2
    assert payload["input_order_preserved"] is True
    assert [row["canonical_id"] for row in payload["papers"]] == canonical_ids
    assert len(payload["pairwise"]) == 1
    assert payload["pairwise"][0]["left_canonical_id"] == canonical_ids[0]
    assert payload["pairwise"][0]["right_canonical_id"] == canonical_ids[1]
    assert set(payload["capabilities"]) == {
        "artifact_details",
        "citation_graph",
        "semantic_similarity",
        "topic_clusters",
    }
    assert payload["capabilities"]["semantic_similarity"]["available"] is True
    assert payload["pairwise"][0]["semantic"]["available"] is True
    assert isinstance(
        payload["pairwise"][0]["semantic"]["similarity"],
        float,
    )


def test_discovery_paper_comparison_five_papers_has_all_pairs(
    client: TestClient,
) -> None:
    canonical_ids = _comparison_ids(client, 5)

    response = client.post(
        "/discovery/papers/compare",
        json={"canonical_ids": canonical_ids},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["canonical_ids"] == canonical_ids
    assert payload["paper_count"] == 5
    assert len(payload["pairwise"]) == 10
    assert set(payload["summary"]["shared_by_all"]) == {
        "categories",
        "concepts",
        "keywords",
        "source_families",
        "artifact_types",
    }


@pytest.mark.parametrize(
    "canonical_ids",
    [
        ["paper:a"],
        ["paper:a", "paper:a"],
        ["paper:a", "paper:b", "paper:c", "paper:d", "paper:e", "paper:f"],
        ["paper:a", " "],
    ],
)
def test_discovery_paper_comparison_rejects_invalid_id_sets(
    client: TestClient,
    canonical_ids: list[str],
) -> None:
    response = client.post(
        "/discovery/papers/compare",
        json={"canonical_ids": canonical_ids},
    )

    assert response.status_code == 422


def test_discovery_paper_comparison_unknown_paper_returns_404(
    client: TestClient,
) -> None:
    known_id = _comparison_ids(client, 1)[0]
    missing_id = "not-a-real-comparison-canonical-id"

    response = client.post(
        "/discovery/papers/compare",
        json={"canonical_ids": [known_id, missing_id]},
    )

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["missing_canonical_ids"] == [missing_id]


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


def test_discovery_topic_clusters_smoke(client: TestClient) -> None:
    response = client.get("/discovery/clusters", params={"limit": 3})

    assert response.status_code == 200
    payload = response.json()

    assert payload["mode"] == "topic_clusters"
    cluster_count = payload.get("cluster_count") or payload.get("total_cluster_count")
    assert cluster_count > 0
    assert payload["returned_count"] == 3
    assert len(payload["results"]) == 3

    first = payload["results"][0]
    assert isinstance(first["cluster_id"], int)
    assert first["size"] > 0
    assert first["label_candidates"]
    assert "mean_radar_score" in first
    assert "artifact_ready_count" in first
    assert "code_artifact_count" in first


def test_discovery_topic_clusters_limit_smoke(client: TestClient) -> None:
    response = client.get(
        "/discovery/clusters",
        params={"limit": 5},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["mode"] == "topic_clusters"
    assert payload["returned_count"] == 5
    assert len(payload["results"]) == 5

    sizes = [cluster["size"] for cluster in payload["results"]]
    assert all(size > 0 for size in sizes)

def test_discovery_topic_cluster_map_centroids_smoke(client: TestClient) -> None:
    response = client.get("/discovery/clusters/map")

    assert response.status_code == 200
    payload = response.json()

    assert payload["mode"] == "topic_cluster_map"
    assert payload["projection_build_id"]
    assert payload["cluster_build_id"]
    assert payload["retrieval_build_id"]

    assert payload["include_papers"] is False
    assert payload["centroid_count"] > 0
    assert payload["returned_points_count"] > 0
    assert payload["returned_points_count"] <= payload["max_points"]
    assert payload["returned_points_count"] == payload["centroid_count"]

    assert payload["points"]

    first = payload["points"][0]
    assert first["point_type"] == "centroid"
    assert isinstance(first["cluster_id"], int)
    assert isinstance(first["x"], float)
    assert isinstance(first["y"], float)
    assert first["label_candidates"]


def test_discovery_topic_cluster_map_include_papers_smoke(client: TestClient) -> None:
    response = client.get(
        "/discovery/clusters/map",
        params={"include_papers": "true", "max_points": 500},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["mode"] == "topic_cluster_map"
    assert payload["include_papers"] is True
    assert payload["returned_points_count"] > 0
    assert payload["returned_points_count"] <= 500
    assert payload["total_points_count"] >= payload["returned_points_count"]
    assert payload["total_points_count"] >= payload["centroid_count"]

    point_types = {point["point_type"] for point in payload["points"]}
    assert "centroid" in point_types

    first = payload["points"][0]
    assert isinstance(first["cluster_id"], int)
    assert isinstance(first["x"], float)
    assert isinstance(first["y"], float)

def test_discovery_topic_cluster_detail_smoke(client: TestClient) -> None:
    cluster_id = _first_cluster_id(client)

    response = client.get(
        f"/discovery/clusters/{cluster_id}",
        params={"top_k": 5},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["mode"] == "topic_cluster_detail"
    assert payload["found"] is True
    assert payload["cluster_id"] == cluster_id
    assert payload["total_papers"] > 0
    assert 1 <= payload["returned_papers_count"] <= 5
    assert payload["summary"]["label_candidates"]
    assert payload["papers"]

    first_paper = payload["papers"][0]
    assert first_paper["cluster_id"] == cluster_id
    assert first_paper["canonical_id"]
    assert first_paper["title"]
    assert first_paper["rank_within_cluster"] >= 1
    assert "filtered_papers_count" in payload
    assert "filters" in payload
    assert isinstance(payload["filters"], dict)
    assert payload["filtered_papers_count"] == payload["total_papers"]


@pytest.mark.parametrize(
    ("sort_by", "score_field"),
    [
        ("similarity_desc", "similarity_to_centroid"),
        ("radar_score", "radar_score"),
        ("implementation_readiness_score", "implementation_readiness_score"),
        ("citation_signal_score", "citation_signal_score"),
        ("year_desc", "year"),
    ],
)
def test_discovery_topic_cluster_detail_sort_modes_smoke(
    client: TestClient,
    sort_by: str,
    score_field: str,
) -> None:
    cluster_id = _first_cluster_id(client)

    response = client.get(
        f"/discovery/clusters/{cluster_id}",
        params={"top_k": 10, "sort_by": sort_by},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["sort_by"] == sort_by
    assert payload["papers"]
    assert 1 <= payload["returned_papers_count"] <= 10

    values = [
        float(row.get(score_field) or 0.0)
        for row in payload["papers"]
    ]
    assert values == sorted(values, reverse=True)

def test_discovery_topic_cluster_detail_invalid_sort_by_returns_422(
    client: TestClient,
) -> None:
    cluster_id = _first_cluster_id(client)

    response = client.get(
        f"/discovery/clusters/{cluster_id}",
        params={"sort_by": "not_a_sort_field"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error_code"] == "validation_error"

def test_discovery_topic_cluster_detail_missing_returns_404(client: TestClient) -> None:
    response = client.get("/discovery/clusters/999999")

    assert response.status_code == 404


def test_discovery_paper_topic_cluster_smoke(client: TestClient) -> None:
    response = client.get(
        f"/discovery/papers/{KNOWN_DISCOVERY_CANONICAL_ID}/cluster"
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["mode"] == "paper_topic_cluster"
    assert payload["canonical_id"] == KNOWN_DISCOVERY_CANONICAL_ID
    assert payload["found"] is True
    assert payload["assignment"]
    assert payload["cluster"]

    assignment = payload["assignment"]
    cluster = payload["cluster"]
    assert assignment["canonical_id"] == KNOWN_DISCOVERY_CANONICAL_ID
    assert isinstance(assignment["cluster_id"], int)
    assert assignment["cluster_id"] == cluster["cluster_id"]
    assert cluster["label_candidates"]


def test_discovery_paper_topic_cluster_missing_returns_404(client: TestClient) -> None:
    response = client.get("/discovery/papers/not-a-real-canonical-id/cluster")

    assert response.status_code == 404


def test_discovery_topic_clusters_invalid_sort_by_returns_422(client: TestClient) -> None:
    response = client.get(
        "/discovery/clusters",
        params={"sort_by": "not_a_sort_field"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error_code"] == "validation_error"

def test_discovery_topic_cluster_detail_filters_echoed_and_counts_valid(client: TestClient) -> None:
    cluster_id = _first_cluster_id(client)

    response = client.get(
        f"/discovery/clusters/{cluster_id}",
        params={
            "top_k": 5,
            "min_year": 2020,
            "min_radar_score": 0.0,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["filters"]["min_year"] == 2020
    assert payload["filters"]["min_radar_score"] == 0.0
    assert payload["total_papers"] >= payload["filtered_papers_count"]
    assert payload["filtered_papers_count"] >= payload["returned_papers_count"]
    assert payload["returned_papers_count"] == len(payload["papers"])

def test_discovery_topic_cluster_detail_min_year_filter(client: TestClient) -> None:
    cluster_id = _first_cluster_id(client)

    response = client.get(
        f"/discovery/clusters/{cluster_id}",
        params={"top_k": 10, "min_year": 2024, "sort_by": "year_desc"},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["filters"]["min_year"] == 2024
    assert payload["total_papers"] >= payload["filtered_papers_count"]
    assert payload["filtered_papers_count"] >= payload["returned_papers_count"]
    assert payload["returned_papers_count"] == len(payload["papers"])

    for row in payload["papers"]:
        assert row["year"] is not None
        assert row["year"] >= 2024

def _artifact_ready_cluster_id(client: TestClient) -> int:
    response = client.get(
        "/discovery/clusters",
        params={"limit": 1, "sort_by": "artifact_ready_desc"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["results"]
    return int(payload["results"][0]["cluster_id"])

def test_discovery_topic_cluster_detail_has_code_filter(client: TestClient) -> None:
    cluster_id = _artifact_ready_cluster_id(client)

    response = client.get(
        f"/discovery/clusters/{cluster_id}",
        params={"top_k": 10, "has_code": "true", "sort_by": "radar_score"},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["filters"]["has_code"] is True
    assert payload["papers"]

    for row in payload["papers"]:
        assert row["has_code_artifact"] is True

def test_discovery_topic_cluster_detail_min_score_filters(client: TestClient) -> None:
    cluster_id = _artifact_ready_cluster_id(client)

    response = client.get(
        f"/discovery/clusters/{cluster_id}",
        params={
            "top_k": 10,
            "min_radar_score": 0.2,
            "min_citation_signal_score": 0.0,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    for row in payload["papers"]:
        assert float(row.get("radar_score") or 0.0) >= 0.2
        assert float(row.get("citation_signal_score") or 0.0) >= 0.0

def test_discovery_topic_cluster_detail_invalid_year_range_returns_400(client: TestClient) -> None:
    cluster_id = _first_cluster_id(client)

    response = client.get(
        f"/discovery/clusters/{cluster_id}",
        params={"min_year": 2026, "max_year": 2025},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "bad_request"
    assert "min_year" in payload["message"]

def test_discovery_topic_cluster_detail_has_github_filter(client: TestClient) -> None:
    cluster_id = _artifact_ready_cluster_id(client)

    response = client.get(
        f"/discovery/clusters/{cluster_id}",
        params={"top_k": 10, "has_github": "true", "sort_by": "radar_score"},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["filters"]["has_github"] is True
    assert payload["total_papers"] >= payload["filtered_papers_count"]
    assert payload["filtered_papers_count"] >= payload["returned_papers_count"]

    for row in payload["papers"]:
        assert int(row.get("github_found_repo_count") or 0) > 0

def _first_linked_artifact_id_or_skip(client: TestClient) -> str:
    response = client.get(
        "/artifacts",
        params={
            "limit": 1,
            "provider": "github",
            "has_paper_links": "true",
            "has_github_metadata": "true",
            "sort_by": "stars_desc",
        },
    )

    if response.status_code == 503:
        pytest.skip("DB backend is not enabled for artifact API tests")

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"]

    artifact_id = payload["results"][0]["artifact_id"]
    assert artifact_id
    return str(artifact_id)

def test_artifact_detail_smoke(client: TestClient) -> None:
    artifact_id = _first_linked_artifact_id_or_skip(client)

    response = client.get(f"/artifacts/{artifact_id}")

    assert response.status_code == 200
    payload = response.json()

    assert payload["artifact_id"] == artifact_id
    assert payload["found"] is True
    assert payload["artifact"]["artifact_id"] == artifact_id
    assert payload["artifact"]["provider"]
    assert payload["artifact"]["normalized_url"]

def test_artifact_linked_papers_smoke(client: TestClient) -> None:
    artifact_id = _first_linked_artifact_id_or_skip(client)

    response = client.get(
        f"/artifacts/{artifact_id}/papers",
        params={"limit": 5},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["artifact_id"] == artifact_id
    assert payload["total"] > 0
    assert 1 <= len(payload["results"]) <= 5

    first = payload["results"][0]
    assert first["artifact_id"] == artifact_id
    assert first["canonical_id"]
    assert first["relation_type"]
    assert 0.0 <= float(first["confidence"]) <= 1.0
    assert first["paper"]["canonical_id"] == first["canonical_id"]
    assert first["paper"]["title"]

def test_artifact_linked_papers_sort_year_desc_smoke(client: TestClient) -> None:
    artifact_id = _first_linked_artifact_id_or_skip(client)

    response = client.get(
        f"/artifacts/{artifact_id}/papers",
        params={"limit": 5, "sort_by": "year_desc"},
    )

    assert response.status_code == 200
    payload = response.json()

    years = [
        int(row["paper"]["year"])
        for row in payload["results"]
        if row["paper"].get("year") is not None
    ]
    assert years == sorted(years, reverse=True)

def test_artifact_detail_missing_returns_404(client: TestClient) -> None:
    response = client.get("/artifacts/not-a-real-artifact-id")

    if response.status_code == 503:
        pytest.skip("DB backend is not enabled for artifact API tests")

    assert response.status_code == 404
