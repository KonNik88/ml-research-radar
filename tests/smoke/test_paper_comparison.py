from __future__ import annotations

from pathlib import Path

import numpy as np

from radar_core.details.paper_comparison import build_paper_comparison
from radar_core.retrieval.similar import DenseBundle
from services.api.discovery_service import (
    DiscoveryService,
    PaperComparisonPaperNotFoundError,
)


def _capabilities() -> dict:
    return {
        "semantic_similarity": {
            "available": True,
            "retrieval_build_id": "retrieval-test",
        },
        "topic_clusters": {
            "available": True,
            "cluster_build_id": "cluster-test",
            "retrieval_build_id": "retrieval-test",
        },
        "citation_graph": {
            "available": True,
            "graph": {
                "name": "citation_reference_graph",
                "version": "v0.1",
            },
        },
        "artifact_details": {
            "available": True,
        },
    }


def test_comparison_preserves_order_and_builds_pairwise_evidence() -> None:
    canonical_by_id = {
        "paper:a": {
            "canonical_id": "paper:a",
            "title": "Paper A",
            "abstract": "A deterministic comparison fixture.",
            "authors": ["Ada", "Bob"],
            "year": 2024,
            "doi": "10.1000/a",
            "categories": ["Machine Learning", "Vision"],
            "concepts": [{"display_name": "Transformers"}],
            "keywords": ["attention", "benchmark"],
            "source_count": 3,
            "unique_source_count": 3,
            "metadata_completeness_score": 0.9,
            "cited_by_count": 12,
            "references_count": 20,
        },
        "paper:b": {
            "canonical_id": "paper:b",
            "title": "Paper B",
            "authors": ["Carol"],
            "year": 2025,
            "arxiv_id": "2501.00001",
            "categories": ["machine learning", "NLP"],
            "concepts": ["Transformers", "Language Models"],
            "keywords": ["attention", "generation"],
            "source_count": 2,
            "unique_source_count": 2,
            "metadata_completeness_score": 0.8,
            "cited_by_count": 5,
            "references_count": 15,
        },
    }
    features_by_id = {
        "paper:a": {
            "canonical_id": "paper:a",
            "source_count": 3,
            "source_family_count": 2,
            "source_families": ["arxiv", "openalex"],
            "radar_score": 0.7,
            "implementation_readiness_score": 0.8,
            "source_confidence_score": 0.9,
            "citation_signal_score": 0.6,
            "recency_score": 0.5,
            "citation_count": 12,
            "trusted_artifact_links_count": 1,
            "trusted_code_links_count": 1,
            "trusted_dataset_links_count": 0,
            "trusted_model_links_count": 0,
            "trusted_demo_links_count": 0,
            "artifact_type_counts": {"github_repository": 1},
            "artifact_provider_counts": {"github": 1},
            "github_found_repo_count": 1,
            "github_stars_max": 100,
        },
        "paper:b": {
            "canonical_id": "paper:b",
            "source_count": 2,
            "source_family_count": 2,
            "source_families": ["openalex", "semantic_scholar"],
            "radar_score": 0.8,
            "implementation_readiness_score": 0.6,
            "source_confidence_score": 0.7,
            "citation_signal_score": 0.4,
            "recency_score": 0.9,
            "citation_count": 5,
            "trusted_artifact_links_count": 1,
            "trusted_code_links_count": 0,
            "trusted_dataset_links_count": 0,
            "trusted_model_links_count": 1,
            "trusted_demo_links_count": 0,
            "artifact_type_counts": {"huggingface_model": 1},
            "artifact_provider_counts": {"huggingface": 1},
            "hf_found_count": 1,
            "hf_model_count": 1,
        },
    }
    artifacts_by_id = {
        "paper:a": [
            {
                "artifact_id": "github:a",
                "artifact_type": "github_repository",
                "provider": "github",
                "relation_type": "code",
            }
        ],
        "paper:b": [
            {
                "artifact_id": "hf:b",
                "artifact_type": "huggingface_model",
                "provider": "huggingface",
                "relation_type": "model",
            }
        ],
    }
    clusters_by_id = {
        "paper:a": {
            "found": True,
            "cluster_id": 7,
            "rank_within_cluster": 2,
            "similarity_to_centroid": 0.91,
            "label_candidates": ["transformers"],
        },
        "paper:b": {
            "found": True,
            "cluster_id": 7,
            "rank_within_cluster": 4,
            "similarity_to_centroid": 0.85,
            "label_candidates": ["transformers"],
        },
    }
    citation_by_id = {
        "paper:a": {
            "found": True,
            "outgoing_reference_count": 2,
            "outgoing_resolved_reference_count": 1,
            "outgoing_external_reference_count": 1,
            "incoming_citation_count": 0,
            "source_families": ["openalex"],
            "references_selected_canonical_ids": ["paper:b"],
            "referenced_by_selected_canonical_ids": [],
        },
        "paper:b": {
            "found": True,
            "outgoing_reference_count": 0,
            "outgoing_resolved_reference_count": 0,
            "outgoing_external_reference_count": 0,
            "incoming_citation_count": 1,
            "source_families": ["openalex"],
            "references_selected_canonical_ids": [],
            "referenced_by_selected_canonical_ids": ["paper:a"],
        },
    }

    payload = build_paper_comparison(
        canonical_ids=["paper:b", "paper:a"],
        canonical_by_id=canonical_by_id,
        features_by_id=features_by_id,
        artifacts_by_canonical_id=artifacts_by_id,
        clusters_by_canonical_id=clusters_by_id,
        citation_graph_by_canonical_id=citation_by_id,
        normalized_embeddings=np.asarray(
            [[1.0, 0.0], [0.8, 0.6]],
            dtype=np.float32,
        ),
        dense_id_to_index={"paper:a": 0, "paper:b": 1},
        capabilities=_capabilities(),
    )

    assert payload["schema_version"] == "paper_comparison_v0.1"
    assert payload["mode"] == "paper_comparison"
    assert payload["canonical_ids"] == ["paper:b", "paper:a"]
    assert [paper["canonical_id"] for paper in payload["papers"]] == [
        "paper:b",
        "paper:a",
    ]
    assert payload["paper_count"] == 2
    assert payload["input_order_preserved"] is True

    pair = payload["pairwise"][0]
    assert pair["left_canonical_id"] == "paper:b"
    assert pair["right_canonical_id"] == "paper:a"
    assert pair["semantic"] == {
        "available": True,
        "similarity": 0.8,
        "reason": None,
    }
    assert pair["same_cluster"] is True
    assert pair["left_references_right"] is False
    assert pair["right_references_left"] is True
    assert pair["dimensions"]["categories"]["shared"] == [
        "machine learning"
    ]
    assert pair["dimensions"]["keywords"]["shared"] == ["attention"]
    assert pair["dimensions"]["source_families"]["shared"] == ["openalex"]

    assert payload["summary"]["shared_by_all"]["concepts"] == [
        "Transformers"
    ]
    assert payload["summary"]["year_range"] == {"min": 2024, "max": 2025}
    assert payload["summary"]["all_same_cluster"] is True


def test_unavailable_derived_layers_degrade_to_null_not_false_zero() -> None:
    capabilities = {
        "semantic_similarity": {
            "available": False,
            "reason": "dense artifacts missing",
        },
        "topic_clusters": {
            "available": False,
            "reason": "cluster artifacts missing",
        },
        "citation_graph": {
            "available": False,
            "reason": "citation_graph_api_disabled",
        },
        "artifact_details": {
            "available": False,
        },
    }

    payload = build_paper_comparison(
        canonical_ids=["paper:a", "paper:b"],
        canonical_by_id={
            "paper:a": {
                "canonical_id": "paper:a",
                "title": "Paper A",
                "source_count": 0,
            },
            "paper:b": {
                "canonical_id": "paper:b",
                "title": "Paper B",
            },
        },
        features_by_id={
            "paper:a": {
                "canonical_id": "paper:a",
                "source_count": 0,
                "citation_count": 0,
                "trusted_artifact_links_count": 0,
            }
        },
        capabilities=capabilities,
        warnings=["optional layers unavailable", "optional layers unavailable"],
    )

    paper_a, paper_b = payload["papers"]
    assert paper_a["provenance"]["source_count"] == 0
    assert paper_a["citation_evidence"]["feature_citation_count"] == 0
    assert (
        paper_a["artifact_evidence"]["trusted_artifact_links_count"]
        == 0
    )
    assert paper_b["provenance"]["source_count"] is None
    assert paper_b["provenance"]["unique_source_count"] is None
    assert paper_b["citation_evidence"]["feature_citation_count"] is None
    assert (
        paper_b["artifact_evidence"]["trusted_artifact_links_count"]
        is None
    )

    pair = payload["pairwise"][0]
    assert pair["semantic"]["available"] is False
    assert pair["semantic"]["similarity"] is None
    assert pair["same_cluster"] is None
    assert pair["left_references_right"] is None
    assert pair["right_references_left"] is None
    assert payload["summary"]["all_same_cluster"] is None
    assert payload["warnings"] == ["optional layers unavailable"]


def test_discovery_service_composes_cached_batch_without_n_plus_one() -> None:
    service = DiscoveryService(
        canonical_path=Path("unused-canonical.jsonl"),
        features_path=Path("unused-features.jsonl"),
        retrieval_manifest_path=Path("unused-retrieval-manifest.json"),
    )
    service._canonical_by_id = {
        "paper:a": {
            "canonical_id": "paper:a",
            "title": "Paper A",
            "categories": ["ML"],
        },
        "paper:b": {
            "canonical_id": "paper:b",
            "title": "Paper B",
            "categories": ["ML"],
        },
    }
    service._features_by_id = {
        "paper:a": {
            "canonical_id": "paper:a",
            "radar_score": 0.6,
        },
        "paper:b": {
            "canonical_id": "paper:b",
            "radar_score": 0.7,
        },
    }
    service._paper_detail_paths = {
        "canonical_path": Path("unused-canonical.jsonl"),
        "features_path": Path("unused-features.jsonl"),
        "artifact_entities_path": Path("unused-artifact-entities.jsonl"),
        "artifact_links_path": Path("unused-artifact-links.jsonl"),
        "github_metadata_path": Path("unused-github.jsonl"),
        "huggingface_metadata_path": Path("unused-huggingface.jsonl"),
    }
    service._artifact_links_by_canonical_id = {}
    service._artifact_entities_by_id = {}
    service._github_metadata_by_artifact_id = {}
    service._huggingface_metadata_by_artifact_id = {}

    embeddings = np.asarray(
        [[1.0, 0.0], [0.0, 1.0]],
        dtype=np.float32,
    )
    service._dense_bundle = DenseBundle(
        embeddings=embeddings,
        ids=["paper:a", "paper:b"],
        meta_rows=[],
        embedding_path=Path("dense.npy"),
        ids_path=Path("ids.json"),
        meta_path=None,
    )
    service._normalized_embeddings = embeddings
    service._dense_id_to_index = {"paper:a": 0, "paper:b": 1}

    service._topic_clusters_payload = {
        "cluster_build_id": "cluster-test",
        "retrieval_build_id": "retrieval-test",
        "cluster_config_hash": "hash-test",
        "clusters_by_id": {
            1: {
                "cluster_id": 1,
                "label_candidates": ["machine learning"],
            }
        },
    }
    service._topic_assignments_by_id = {
        "paper:a": {
            "canonical_id": "paper:a",
            "cluster_id": 1,
        },
        "paper:b": {
            "canonical_id": "paper:b",
            "cluster_id": 1,
        },
    }

    payload = service.compare_papers(
        canonical_ids=["paper:b", "paper:a"],
        citation_graph_capability={
            "available": False,
            "reason": "disabled in fixture",
        },
    )

    assert payload["canonical_ids"] == ["paper:b", "paper:a"]
    assert payload["pairwise"][0]["semantic"]["similarity"] == 0.0
    assert payload["pairwise"][0]["same_cluster"] is True
    assert payload["capabilities"]["artifact_details"]["available"] is False

    try:
        service.compare_papers(
            canonical_ids=["paper:a", "paper:missing"],
        )
    except PaperComparisonPaperNotFoundError as exc:
        assert exc.missing_canonical_ids == ["paper:missing"]
    else:
        raise AssertionError("Expected PaperComparisonPaperNotFoundError")

    service.reload()
    assert service._canonical_by_id is None
    assert service._features_by_id is None
    assert service._paper_detail_paths is None
    assert service._artifact_links_by_canonical_id is None
    assert service._artifact_entities_by_id is None
    assert service._github_metadata_by_artifact_id is None
    assert service._huggingface_metadata_by_artifact_id is None
    assert service._dense_bundle is None
    assert service._topic_clusters_payload is None
