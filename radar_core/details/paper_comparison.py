from __future__ import annotations

from itertools import combinations
from typing import Any, Iterable

import numpy as np

from radar_core.details.paper_detail import (
    build_identifier_block,
    build_link_block,
    source_families_from_canonical_and_features,
)


PAPER_COMPARISON_SCHEMA_VERSION = "paper_comparison_v0.1"
PAPER_COMPARISON_MODE = "paper_comparison"

COMPARISON_DIMENSIONS = (
    "categories",
    "concepts",
    "keywords",
    "source_families",
    "artifact_types",
)

SCORE_FIELDS = (
    "radar_score",
    "implementation_readiness_score",
    "source_confidence_score",
    "citation_signal_score",
    "recency_score",
)

TRUSTED_ARTIFACT_COUNT_FIELDS = (
    "trusted_artifact_links_count",
    "trusted_code_links_count",
    "trusted_dataset_links_count",
    "trusted_model_links_count",
    "trusted_demo_links_count",
)

GITHUB_FIELDS = (
    "github_repo_count",
    "github_found_repo_count",
    "github_not_found_repo_count",
    "github_stars_max",
    "github_stars_sum",
    "github_forks_max",
    "github_forks_sum",
    "github_language_top",
    "github_license_any",
    "github_archived_any",
)

HUGGINGFACE_FIELDS = (
    "hf_found_count",
    "hf_model_count",
    "hf_dataset_count",
    "hf_space_count",
    "hf_downloads_max",
    "hf_likes_max",
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _known_value(mapping: dict[str, Any], key: str) -> Any:
    return mapping[key] if key in mapping else None


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _display_text(value: Any) -> str | None:
    if isinstance(value, dict):
        value = _first_nonempty(
            value.get("display_name"),
            value.get("name"),
            value.get("label"),
            value.get("title"),
            value.get("id"),
        )
    text = str(value or "").strip()
    return text or None


def _stable_strings(value: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in _as_list(value):
        text = _display_text(item)
        if not text:
            continue
        normalized = text.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(text)
    return out


def _select_fields(
    mapping: dict[str, Any],
    fields: Iterable[str],
) -> dict[str, Any]:
    return {field: _known_value(mapping, field) for field in fields}


def _identifier_payload(canonical: dict[str, Any]) -> dict[str, Any]:
    identifiers = build_identifier_block(canonical)
    return {
        "canonical_id": canonical.get("canonical_id"),
        "doi": identifiers.get("doi"),
        "arxiv_id": identifiers.get("arxiv_id"),
        "acl_anthology_id": identifiers.get("acl_anthology_id"),
        "acl_bibkey": identifiers.get("acl_bibkey"),
        "openalex_id": identifiers.get("openalex_id"),
        "semantic_scholar_id": identifiers.get("semantic_scholar_id"),
        "pmid": identifiers.get("pmid"),
        "pmcid": identifiers.get("pmcid"),
    }


def _link_payload(canonical: dict[str, Any]) -> dict[str, Any]:
    links = build_link_block(canonical)
    return {
        "pdf_url": links.get("pdf_url"),
        "landing_page_url": links.get("landing_page_url"),
        "doi_url": links.get("doi_url"),
        "repo_url": canonical.get("repo_url"),
        "code_links": _stable_strings(canonical.get("code_links")),
    }


def _taxonomy_payload(canonical: dict[str, Any]) -> dict[str, Any]:
    return {
        "primary_category": canonical.get("primary_category"),
        "categories": _stable_strings(canonical.get("categories")),
        "concepts": _stable_strings(canonical.get("concepts")),
        "keywords": _stable_strings(canonical.get("keywords")),
        "tags": _stable_strings(canonical.get("tags")),
    }


def _provenance_payload(
    *,
    canonical: dict[str, Any],
    features: dict[str, Any],
) -> dict[str, Any]:
    source_count = _first_nonempty(
        _known_value(features, "source_count"),
        _known_value(canonical, "source_count"),
    )
    unique_source_count = _first_nonempty(
        _known_value(canonical, "unique_source_count"),
        _known_value(features, "unique_source_count"),
    )
    source_family_count = _first_nonempty(
        _known_value(features, "source_family_count"),
        _known_value(canonical, "source_family_count"),
    )

    return {
        "source_count": _optional_int(source_count),
        "unique_source_count": _optional_int(unique_source_count),
        "source_family_count": _optional_int(source_family_count),
        "source_families": source_families_from_canonical_and_features(
            canonical=canonical,
            features=features,
        ),
        "metadata_completeness_score": _optional_float(
            _first_nonempty(
                _known_value(canonical, "metadata_completeness_score"),
                _known_value(features, "metadata_completeness_score"),
            )
        ),
        "source_ids": _as_dict(canonical.get("source_ids")),
        "external_ids": _as_dict(canonical.get("external_ids")),
    }


def _score_payload(features: dict[str, Any]) -> dict[str, Any]:
    scores = {
        field: _optional_float(_known_value(features, field))
        for field in SCORE_FIELDS
    }
    scores["score_components"] = _as_dict(features.get("score_components"))
    return scores


def _artifact_types(
    *,
    features: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> list[str]:
    values: list[Any] = []
    type_counts = _as_dict(features.get("artifact_type_counts"))
    values.extend(type_counts.keys())
    values.extend(row.get("artifact_type") for row in artifacts)
    return _stable_strings(values)


def _artifact_providers(
    *,
    features: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> list[str]:
    values: list[Any] = []
    provider_counts = _as_dict(features.get("artifact_provider_counts"))
    values.extend(provider_counts.keys())
    values.extend(row.get("provider") for row in artifacts)
    return _stable_strings(values)


def _artifact_evidence_payload(
    *,
    features: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    trusted_counts = {
        field: _optional_int(_known_value(features, field))
        for field in TRUSTED_ARTIFACT_COUNT_FIELDS
    }

    return {
        "has_code_artifact": _known_value(features, "has_code_artifact"),
        "has_dataset_artifact": _known_value(features, "has_dataset_artifact"),
        "has_model_artifact": _known_value(features, "has_model_artifact"),
        "has_demo_artifact": _known_value(features, "has_demo_artifact"),
        **trusted_counts,
        "artifact_provider_counts": _as_dict(
            features.get("artifact_provider_counts")
        ),
        "artifact_type_counts": _as_dict(features.get("artifact_type_counts")),
        "artifact_types": _artifact_types(
            features=features,
            artifacts=artifacts,
        ),
        "artifact_providers": _artifact_providers(
            features=features,
            artifacts=artifacts,
        ),
        "github": _select_fields(features, GITHUB_FIELDS),
        "huggingface": _select_fields(features, HUGGINGFACE_FIELDS),
        "details": artifacts,
    }


def _cluster_payload(
    *,
    cluster_context: dict[str, Any] | None,
    cluster_capability: dict[str, Any],
) -> dict[str, Any]:
    if cluster_capability.get("available") is not True:
        return {
            "status": "unavailable",
            "cluster_id": None,
            "rank_within_cluster": None,
            "similarity_to_centroid": None,
            "label_candidates": [],
            "cluster_build_id": cluster_capability.get("cluster_build_id"),
            "retrieval_build_id": cluster_capability.get("retrieval_build_id"),
        }

    context = _as_dict(cluster_context)
    if context.get("found") is not True:
        return {
            "status": "paper_not_in_build",
            "cluster_id": None,
            "rank_within_cluster": None,
            "similarity_to_centroid": None,
            "label_candidates": [],
            "cluster_build_id": cluster_capability.get("cluster_build_id"),
            "retrieval_build_id": cluster_capability.get("retrieval_build_id"),
        }

    return {
        "status": "available",
        "cluster_id": _optional_int(context.get("cluster_id")),
        "rank_within_cluster": _optional_int(context.get("rank_within_cluster")),
        "similarity_to_centroid": _optional_float(
            context.get("similarity_to_centroid")
        ),
        "label_candidates": _stable_strings(context.get("label_candidates")),
        "cluster_build_id": cluster_capability.get("cluster_build_id"),
        "retrieval_build_id": cluster_capability.get("retrieval_build_id"),
    }


def _citation_evidence_payload(
    *,
    canonical: dict[str, Any],
    features: dict[str, Any],
    graph_evidence: dict[str, Any] | None,
    graph_capability: dict[str, Any],
) -> dict[str, Any]:
    evidence = _as_dict(graph_evidence)

    if graph_capability.get("available") is not True:
        graph_status = "unavailable"
    elif evidence.get("found") is True:
        graph_status = "available"
    else:
        graph_status = "paper_not_in_graph"

    return {
        "canonical_cited_by_count": _optional_int(
            canonical.get("cited_by_count")
        ),
        "canonical_references_count": _optional_int(
            canonical.get("references_count")
        ),
        "feature_citation_count": _optional_int(features.get("citation_count")),
        "citation_signal_score": _optional_float(
            features.get("citation_signal_score")
        ),
        "graph": {
            "status": graph_status,
            "outgoing_reference_count": _optional_int(
                evidence.get("outgoing_reference_count")
            ),
            "outgoing_resolved_reference_count": _optional_int(
                evidence.get("outgoing_resolved_reference_count")
            ),
            "outgoing_external_reference_count": _optional_int(
                evidence.get("outgoing_external_reference_count")
            ),
            "incoming_citation_count": _optional_int(
                evidence.get("incoming_citation_count")
            ),
            "source_families": _stable_strings(
                evidence.get("source_families")
            ),
            "references_selected_canonical_ids": _stable_strings(
                evidence.get("references_selected_canonical_ids")
            ),
            "referenced_by_selected_canonical_ids": _stable_strings(
                evidence.get("referenced_by_selected_canonical_ids")
            ),
        },
    }


def build_comparison_paper(
    *,
    canonical_id: str,
    canonical: dict[str, Any],
    features: dict[str, Any] | None,
    artifacts: list[dict[str, Any]] | None,
    cluster_context: dict[str, Any] | None,
    citation_graph_evidence: dict[str, Any] | None,
    capabilities: dict[str, Any],
) -> dict[str, Any]:
    features = _as_dict(features)
    artifacts = [
        row for row in (artifacts or []) if isinstance(row, dict)
    ]

    return {
        "canonical_id": canonical_id,
        "title": _first_nonempty(
            canonical.get("title"),
            features.get("title"),
        ),
        "abstract": canonical.get("abstract"),
        "authors": _stable_strings(canonical.get("authors")),
        "year": _optional_int(
            _first_nonempty(canonical.get("year"), features.get("year"))
        ),
        "publication_date": _first_nonempty(
            canonical.get("publication_date"),
            features.get("publication_date"),
        ),
        "published_at": _first_nonempty(
            canonical.get("published_at"),
            features.get("published_at"),
        ),
        "venue": _first_nonempty(
            canonical.get("venue"),
            canonical.get("conference"),
            canonical.get("journal"),
        ),
        "journal": canonical.get("journal"),
        "conference": canonical.get("conference"),
        "publisher": canonical.get("publisher"),
        "publication_type": _first_nonempty(
            canonical.get("publication_type"),
            canonical.get("document_type"),
        ),
        "language": canonical.get("language"),
        "open_access": canonical.get("open_access"),
        "is_preprint": canonical.get("is_preprint"),
        "is_review": canonical.get("is_review"),
        "is_survey": canonical.get("is_survey"),
        "is_withdrawn": canonical.get("is_withdrawn"),
        "identifiers": _identifier_payload(canonical),
        "links": _link_payload(canonical),
        "taxonomy": _taxonomy_payload(canonical),
        "provenance": _provenance_payload(
            canonical=canonical,
            features=features,
        ),
        "scores": _score_payload(features),
        "artifact_evidence": _artifact_evidence_payload(
            features=features,
            artifacts=artifacts,
        ),
        "citation_evidence": _citation_evidence_payload(
            canonical=canonical,
            features=features,
            graph_evidence=citation_graph_evidence,
            graph_capability=_as_dict(capabilities.get("citation_graph")),
        ),
        "cluster": _cluster_payload(
            cluster_context=cluster_context,
            cluster_capability=_as_dict(capabilities.get("topic_clusters")),
        ),
    }


def _normalized_lookup(values: Iterable[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for value in values:
        text = str(value).strip()
        if text:
            out.setdefault(text.casefold(), text)
    return out


def _pair_dimension_diff(
    left_values: Iterable[str],
    right_values: Iterable[str],
) -> dict[str, list[str]]:
    left = _normalized_lookup(left_values)
    right = _normalized_lookup(right_values)

    return {
        "shared": [
            display for key, display in left.items() if key in right
        ],
        "left_only": [
            display for key, display in left.items() if key not in right
        ],
        "right_only": [
            display for key, display in right.items() if key not in left
        ],
    }


def _paper_dimension_values(
    paper: dict[str, Any],
    dimension: str,
) -> list[str]:
    if dimension in {"categories", "concepts", "keywords"}:
        return _stable_strings(
            _as_dict(paper.get("taxonomy")).get(dimension)
        )
    if dimension == "source_families":
        return _stable_strings(
            _as_dict(paper.get("provenance")).get("source_families")
        )
    if dimension == "artifact_types":
        return _stable_strings(
            _as_dict(paper.get("artifact_evidence")).get("artifact_types")
        )
    raise ValueError(f"Unsupported comparison dimension: {dimension}")


def _shared_by_all(
    papers: list[dict[str, Any]],
    dimension: str,
) -> list[str]:
    if not papers:
        return []

    first_values = _paper_dimension_values(papers[0], dimension)
    shared_keys = set(_normalized_lookup(first_values))

    for paper in papers[1:]:
        shared_keys &= set(
            _normalized_lookup(_paper_dimension_values(paper, dimension))
        )

    return [
        value for value in first_values if value.casefold() in shared_keys
    ]


def _semantic_similarity(
    *,
    left_id: str,
    right_id: str,
    normalized_embeddings: np.ndarray | None,
    dense_id_to_index: dict[str, int] | None,
    semantic_capability: dict[str, Any],
) -> dict[str, Any]:
    if semantic_capability.get("available") is not True:
        return {
            "available": False,
            "similarity": None,
            "reason": semantic_capability.get("reason")
            or "semantic_similarity_unavailable",
        }

    if normalized_embeddings is None or dense_id_to_index is None:
        return {
            "available": False,
            "similarity": None,
            "reason": "dense_runtime_not_loaded",
        }

    missing = [
        canonical_id
        for canonical_id in (left_id, right_id)
        if canonical_id not in dense_id_to_index
    ]
    if missing:
        return {
            "available": False,
            "similarity": None,
            "reason": "canonical_id_missing_from_dense_build",
            "missing_canonical_ids": missing,
        }

    left_vector = normalized_embeddings[dense_id_to_index[left_id]]
    right_vector = normalized_embeddings[dense_id_to_index[right_id]]

    if (
        not np.isfinite(left_vector).all()
        or not np.isfinite(right_vector).all()
        or np.linalg.norm(left_vector) <= 0.0
        or np.linalg.norm(right_vector) <= 0.0
    ):
        return {
            "available": False,
            "similarity": None,
            "reason": "invalid_embedding_vector",
        }

    similarity = float(left_vector @ right_vector)
    similarity = max(-1.0, min(1.0, similarity))
    return {
        "available": True,
        "similarity": round(similarity, 6),
        "reason": None,
    }


def _same_cluster(
    left: dict[str, Any],
    right: dict[str, Any],
) -> bool | None:
    left_cluster = _as_dict(left.get("cluster"))
    right_cluster = _as_dict(right.get("cluster"))
    if (
        left_cluster.get("status") != "available"
        or right_cluster.get("status") != "available"
    ):
        return None
    left_cluster_id = left_cluster.get("cluster_id")
    right_cluster_id = right_cluster.get("cluster_id")
    if left_cluster_id is None or right_cluster_id is None:
        return None
    return left_cluster_id == right_cluster_id


def _selected_reference_relationship(
    *,
    source: dict[str, Any],
    target_canonical_id: str,
) -> bool | None:
    graph = _as_dict(
        _as_dict(source.get("citation_evidence")).get("graph")
    )
    if graph.get("status") != "available":
        return None
    selected_ids = {
        value.casefold()
        for value in _stable_strings(
            graph.get("references_selected_canonical_ids")
        )
    }
    return target_canonical_id.casefold() in selected_ids


def _pairwise_payload(
    *,
    papers: list[dict[str, Any]],
    normalized_embeddings: np.ndarray | None,
    dense_id_to_index: dict[str, int] | None,
    semantic_capability: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for left, right in combinations(papers, 2):
        left_id = str(left["canonical_id"])
        right_id = str(right["canonical_id"])
        dimensions = {
            dimension: _pair_dimension_diff(
                _paper_dimension_values(left, dimension),
                _paper_dimension_values(right, dimension),
            )
            for dimension in COMPARISON_DIMENSIONS
        }

        rows.append(
            {
                "left_canonical_id": left_id,
                "right_canonical_id": right_id,
                "semantic": _semantic_similarity(
                    left_id=left_id,
                    right_id=right_id,
                    normalized_embeddings=normalized_embeddings,
                    dense_id_to_index=dense_id_to_index,
                    semantic_capability=semantic_capability,
                ),
                "same_cluster": _same_cluster(left, right),
                "left_references_right": _selected_reference_relationship(
                    source=left,
                    target_canonical_id=right_id,
                ),
                "right_references_left": _selected_reference_relationship(
                    source=right,
                    target_canonical_id=left_id,
                ),
                "dimensions": dimensions,
            }
        )

    return rows


def _numeric_range(values: Iterable[Any]) -> dict[str, float] | None:
    numeric = [
        value
        for value in (_optional_float(item) for item in values)
        if value is not None
    ]
    if not numeric:
        return None
    return {
        "min": min(numeric),
        "max": max(numeric),
    }


def _summary_payload(papers: list[dict[str, Any]]) -> dict[str, Any]:
    available_cluster_ids = [
        _as_dict(paper.get("cluster")).get("cluster_id")
        for paper in papers
        if _as_dict(paper.get("cluster")).get("status") == "available"
    ]

    all_same_cluster: bool | None
    if (
        len(available_cluster_ids) != len(papers)
        or any(cluster_id is None for cluster_id in available_cluster_ids)
    ):
        all_same_cluster = None
    else:
        all_same_cluster = len(set(available_cluster_ids)) == 1

    year_range = _numeric_range(paper.get("year") for paper in papers)
    if year_range is not None:
        year_range = {
            "min": int(year_range["min"]),
            "max": int(year_range["max"]),
        }

    return {
        "shared_by_all": {
            dimension: _shared_by_all(papers, dimension)
            for dimension in COMPARISON_DIMENSIONS
        },
        "year_range": year_range,
        "score_ranges": {
            score: _numeric_range(
                _as_dict(paper.get("scores")).get(score)
                for paper in papers
            )
            for score in SCORE_FIELDS
        },
        "all_same_cluster": all_same_cluster,
    }


def build_paper_comparison(
    *,
    canonical_ids: list[str],
    canonical_by_id: dict[str, dict[str, Any]],
    features_by_id: dict[str, dict[str, Any]] | None = None,
    artifacts_by_canonical_id: dict[str, list[dict[str, Any]]] | None = None,
    clusters_by_canonical_id: dict[str, dict[str, Any]] | None = None,
    citation_graph_by_canonical_id: dict[str, dict[str, Any]] | None = None,
    normalized_embeddings: np.ndarray | None = None,
    dense_id_to_index: dict[str, int] | None = None,
    capabilities: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build a deterministic comparison without mutating any source layer."""

    capabilities = _as_dict(capabilities)
    features_by_id = features_by_id or {}
    artifacts_by_canonical_id = artifacts_by_canonical_id or {}
    clusters_by_canonical_id = clusters_by_canonical_id or {}
    citation_graph_by_canonical_id = citation_graph_by_canonical_id or {}

    papers = [
        build_comparison_paper(
            canonical_id=canonical_id,
            canonical=canonical_by_id[canonical_id],
            features=features_by_id.get(canonical_id),
            artifacts=artifacts_by_canonical_id.get(canonical_id),
            cluster_context=clusters_by_canonical_id.get(canonical_id),
            citation_graph_evidence=citation_graph_by_canonical_id.get(
                canonical_id
            ),
            capabilities=capabilities,
        )
        for canonical_id in canonical_ids
    ]

    warning_rows = list(dict.fromkeys(str(item) for item in (warnings or []) if item))

    return {
        "schema_version": PAPER_COMPARISON_SCHEMA_VERSION,
        "mode": PAPER_COMPARISON_MODE,
        "canonical_ids": canonical_ids,
        "paper_count": len(papers),
        "input_order_preserved": True,
        "papers": papers,
        "pairwise": _pairwise_payload(
            papers=papers,
            normalized_embeddings=normalized_embeddings,
            dense_id_to_index=dense_id_to_index,
            semantic_capability=_as_dict(
                capabilities.get("semantic_similarity")
            ),
        ),
        "summary": _summary_payload(papers),
        "capabilities": capabilities,
        "warnings": warning_rows,
    }
