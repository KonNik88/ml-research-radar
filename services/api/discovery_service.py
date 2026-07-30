from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from radar_core.details.paper_detail import (
    DEFAULT_PAPER_FEATURES_CONFIG_PATH,
    build_artifact_detail_rows,
    build_paper_detail_from_config,
    load_jsonl_by_key,
    load_paper_features_config_paths,
)
from radar_core.details.paper_comparison import build_paper_comparison
from radar_core.ranking.feature_ranking import (
    DEFAULT_FEATURES_PATH,
    RankingFilters,
    load_feature_rows,
    rank_feature_rows,
)
from radar_core.ranking.profiles import (
    DEFAULT_RANKING_PROFILES_PATH,
    get_ranking_profile,
    load_ranking_profiles,
)
from radar_core.retrieval.similar import (
    DEFAULT_CANONICAL_PATH,
    DEFAULT_DENSE_DIR,
    DEFAULT_RETRIEVAL_MANIFEST_PATH,
    DenseBundle,
    find_similar_papers_from_loaded,
    load_dense_bundle,
    load_latest_retrieval_manifest,
    load_jsonl_by_canonical_id,
    normalize_embeddings,
    normalize_path,
)

DEFAULT_TOPIC_CLUSTERS_LATEST_PATH = Path("artifacts/clusters/topic/latest.json")


class PaperComparisonPaperNotFoundError(ValueError):
    def __init__(self, missing_canonical_ids: list[str]) -> None:
        self.missing_canonical_ids = missing_canonical_ids
        joined = ", ".join(missing_canonical_ids)
        super().__init__(f"Paper(s) not found: {joined}")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Bad JSONL row in {path}:{line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"Expected JSON object in {path}:{line_no}")
            rows.append(row)
    return rows


def _as_path(value: Any, *, base_dir: Path | None = None) -> Path | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    path = Path(text)
    if path.is_absolute():
        return path

    if base_dir is not None:
        candidate = base_dir / path
        if candidate.exists():
            return candidate

    return path


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _cluster_id_of(row: dict[str, Any]) -> int:
    return _safe_int(row.get("cluster_id"))

def _projection_point_type(row: dict[str, Any]) -> str:
    value = (
        row.get("point_type")
        or row.get("type")
        or row.get("kind")
        or row.get("role")
    )

    text = str(value or "").strip().lower()
    if text:
        return text

    canonical_id = str(row.get("canonical_id") or "").strip()
    return "paper" if canonical_id else "centroid"


def _projection_xy(row: dict[str, Any]) -> tuple[float, float]:
    x_value = row.get("x")
    y_value = row.get("y")

    if x_value is None:
        x_value = row.get("projection_x")
    if y_value is None:
        y_value = row.get("projection_y")

    if (x_value is None or y_value is None) and isinstance(row.get("coordinates"), list):
        coordinates = row["coordinates"]
        if len(coordinates) >= 2:
            x_value = coordinates[0]
            y_value = coordinates[1]

    try:
        x = float(x_value)
        y = float(y_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Bad topic projection point coordinates: {row}") from exc

    return x, y


def _normalize_projection_point(row: dict[str, Any]) -> dict[str, Any]:
    point_type = _projection_point_type(row)
    x, y = _projection_xy(row)

    cluster_id = _safe_int(row.get("cluster_id"))

    label_candidates = row.get("label_candidates") or []
    if not isinstance(label_candidates, list):
        label_candidates = []

    metadata = row.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    metadata = {
        **metadata,
        "cluster_size": row.get("cluster_size"),
        "mean_radar_score": row.get("mean_radar_score"),
        "mean_implementation_readiness_score": row.get(
            "mean_implementation_readiness_score"
        ),
        "is_representative": bool(row.get("is_representative")),
        "is_sampled": bool(row.get("is_sampled")),
        "rank_within_cluster": row.get("rank_within_cluster"),
    }

    return {
        "point_id": row.get("point_id"),
        "point_type": point_type,
        "cluster_id": cluster_id,
        "x": x,
        "y": y,
        "canonical_id": row.get("canonical_id"),
        "title": row.get("title"),
        "year": row.get("year"),
        "label_candidates": [str(x) for x in label_candidates if str(x).strip()],
        "size": row.get("size") or row.get("cluster_size"),
        "radar_score": row.get("radar_score") or row.get("mean_radar_score"),
        "implementation_readiness_score": (
                row.get("implementation_readiness_score")
                or row.get("mean_implementation_readiness_score")
        ),
        "artifact_ready_count": row.get("artifact_ready_count"),
        "metadata": metadata,
    }

def _merge_cluster_labels(
    *,
    summary_cluster: dict[str, Any],
    labels_by_cluster_id: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    cluster_id = _cluster_id_of(summary_cluster)
    label_payload = labels_by_cluster_id.get(cluster_id) or {}

    merged = dict(summary_cluster)
    label_candidates = label_payload.get("label_candidates") or merged.get("label_candidates") or []
    merged["label_candidates"] = [str(x) for x in label_candidates if str(x).strip()]

    for field_name in (
        "top_title_terms",
        "top_title_trigrams",
        "top_abstract_terms",
        "top_abstract_bigrams",
        "top_abstract_trigrams",
        "top_categories",
        "top_concepts",
        "top_keywords",
        "top_tags",
    ):
        if field_name not in merged and field_name in label_payload:
            merged[field_name] = label_payload[field_name]

    return merged


def _sort_clusters(
    clusters: list[dict[str, Any]],
    sort_by: str,
) -> list[dict[str, Any]]:
    if sort_by == "cluster_id_asc":
        return sorted(clusters, key=lambda x: _cluster_id_of(x))

    if sort_by == "mean_radar_desc":
        return sorted(
            clusters,
            key=lambda x: (
                _safe_float(x.get("mean_radar_score")),
                _safe_int(x.get("size")),
                -_cluster_id_of(x),
            ),
            reverse=True,
        )

    if sort_by == "artifact_ready_desc":
        return sorted(
            clusters,
            key=lambda x: (
                _safe_int(x.get("artifact_ready_count")),
                _safe_int(x.get("size")),
                -_cluster_id_of(x),
            ),
            reverse=True,
        )

    if sort_by == "size_desc":
        return sorted(
            clusters,
            key=lambda x: (
                _safe_int(x.get("size")),
                _safe_float(x.get("mean_radar_score")),
                -_cluster_id_of(x),
            ),
            reverse=True,
        )

    raise ValueError(f"Unsupported topic cluster sort_by: {sort_by}")

def _bool_filter_matches(actual: bool, expected: bool | None) -> bool:
    if expected is None:
        return True
    return actual is expected

def _row_has_github(row: dict[str, Any]) -> bool:
    return _safe_int(row.get("github_found_repo_count")) > 0

def _row_has_hf(row: dict[str, Any]) -> bool:
    return _safe_int(row.get("hf_found_count")) > 0

def _row_has_acl(row: dict[str, Any]) -> bool:
    if bool(row.get("has_acl")):
        return True

    source_families = row.get("source_families") or []
    if not isinstance(source_families, list):
        return False

    normalized = {str(x).strip().lower() for x in source_families}
    return bool({"acl", "acl_anthology", "acl-family"} & normalized)

def _row_has_doi(row: dict[str, Any]) -> bool:
    if "has_doi" in row:
        return bool(row.get("has_doi"))
    return bool(row.get("doi"))

def _score_at_least(
    row: dict[str, Any],
    field_name: str,
    threshold: float | None,
) -> bool:
    if threshold is None:
        return True
    return _safe_float(row.get(field_name), default=0.0) >= float(threshold)

def _apply_topic_cluster_paper_filters(
    papers: list[dict[str, Any]],
    *,
    min_year: int | None = None,
    max_year: int | None = None,
    has_code: bool | None = None,
    has_dataset: bool | None = None,
    has_model: bool | None = None,
    has_demo: bool | None = None,
    has_github: bool | None = None,
    has_hf: bool | None = None,
    has_acl: bool | None = None,
    has_doi: bool | None = None,
    min_radar_score: float | None = None,
    min_implementation_readiness_score: float | None = None,
    min_citation_signal_score: float | None = None,
) -> list[dict[str, Any]]:
    if min_year is not None and max_year is not None and min_year > max_year:
        raise ValueError("min_year must be less than or equal to max_year")

    filtered: list[dict[str, Any]] = []

    for row in papers:
        year = row.get("year")

        if min_year is not None:
            if year is None or _safe_int(year, default=-9999) < min_year:
                continue

        if max_year is not None:
            if year is None or _safe_int(year, default=999999) > max_year:
                continue

        if not _bool_filter_matches(bool(row.get("has_code_artifact")), has_code):
            continue
        if not _bool_filter_matches(bool(row.get("has_dataset_artifact")), has_dataset):
            continue
        if not _bool_filter_matches(bool(row.get("has_model_artifact")), has_model):
            continue
        if not _bool_filter_matches(bool(row.get("has_demo_artifact")), has_demo):
            continue

        if not _bool_filter_matches(_row_has_github(row), has_github):
            continue
        if not _bool_filter_matches(_row_has_hf(row), has_hf):
            continue
        if not _bool_filter_matches(_row_has_acl(row), has_acl):
            continue
        if not _bool_filter_matches(_row_has_doi(row), has_doi):
            continue

        if not _score_at_least(row, "radar_score", min_radar_score):
            continue
        if not _score_at_least(
            row,
            "implementation_readiness_score",
            min_implementation_readiness_score,
        ):
            continue
        if not _score_at_least(
            row,
            "citation_signal_score",
            min_citation_signal_score,
        ):
            continue

        filtered.append(row)

    return filtered

def _effective_topic_cluster_filters(
    *,
    min_year: int | None = None,
    max_year: int | None = None,
    has_code: bool | None = None,
    has_dataset: bool | None = None,
    has_model: bool | None = None,
    has_demo: bool | None = None,
    has_github: bool | None = None,
    has_hf: bool | None = None,
    has_acl: bool | None = None,
    has_doi: bool | None = None,
    min_radar_score: float | None = None,
    min_implementation_readiness_score: float | None = None,
    min_citation_signal_score: float | None = None,
) -> dict[str, Any]:
    raw = {
        "min_year": min_year,
        "max_year": max_year,
        "has_code": has_code,
        "has_dataset": has_dataset,
        "has_model": has_model,
        "has_demo": has_demo,
        "has_github": has_github,
        "has_hf": has_hf,
        "has_acl": has_acl,
        "has_doi": has_doi,
        "min_radar_score": min_radar_score,
        "min_implementation_readiness_score": min_implementation_readiness_score,
        "min_citation_signal_score": min_citation_signal_score,
    }
    return {key: value for key, value in raw.items() if value is not None}

def _sort_cluster_papers(
    papers: list[dict[str, Any]],
    sort_by: str,
) -> list[dict[str, Any]]:
    if sort_by == "rank":
        return sorted(
            papers,
            key=lambda x: (
                _safe_int(x.get("rank_within_cluster"), default=10**12),
                -_safe_float(x.get("similarity_to_centroid")),
                str(x.get("canonical_id") or ""),
            ),
        )

    if sort_by == "similarity_desc":
        return sorted(
            papers,
            key=lambda x: (
                _safe_float(x.get("similarity_to_centroid")),
                -_safe_int(x.get("rank_within_cluster"), default=10**12),
            ),
            reverse=True,
        )

    if sort_by == "radar_score":
        return sorted(
            papers,
            key=lambda x: (
                _safe_float(x.get("radar_score")),
                _safe_float(x.get("similarity_to_centroid")),
            ),
            reverse=True,
        )

    if sort_by == "implementation_readiness_score":
        return sorted(
            papers,
            key=lambda x: (
                _safe_float(x.get("implementation_readiness_score")),
                _safe_float(x.get("similarity_to_centroid")),
            ),
            reverse=True,
        )

    if sort_by == "citation_signal_score":
        return sorted(
            papers,
            key=lambda x: (
                _safe_float(x.get("citation_signal_score")),
                _safe_float(x.get("similarity_to_centroid")),
            ),
            reverse=True,
        )

    if sort_by == "year_desc":
        return sorted(
            papers,
            key=lambda x: (
                x.get("year") is not None,
                _safe_int(x.get("year"), default=-9999),
                _safe_float(x.get("similarity_to_centroid")),
            ),
            reverse=True,
        )

    raise ValueError(f"Unsupported topic cluster paper sort_by: {sort_by}")


@dataclass
class DiscoveryService:
    profiles_path: Path = DEFAULT_RANKING_PROFILES_PATH
    features_path: Path = DEFAULT_FEATURES_PATH
    paper_features_config_path: Path = DEFAULT_PAPER_FEATURES_CONFIG_PATH
    canonical_path: Path = DEFAULT_CANONICAL_PATH
    dense_dir: Path = DEFAULT_DENSE_DIR
    retrieval_manifest_path: Path = DEFAULT_RETRIEVAL_MANIFEST_PATH
    topic_clusters_latest_path: Path = DEFAULT_TOPIC_CLUSTERS_LATEST_PATH

    _profiles_payload: dict[str, Any] | None = field(default=None, init=False)
    _feature_rows: list[dict[str, Any]] | None = field(default=None, init=False)
    _features_by_id: dict[str, dict[str, Any]] | None = field(default=None, init=False)
    _canonical_by_id: dict[str, dict[str, Any]] | None = field(default=None, init=False)
    _dense_bundle: DenseBundle | None = field(default=None, init=False)
    _normalized_embeddings: Any | None = field(default=None, init=False)
    _dense_id_to_index: dict[str, int] | None = field(default=None, init=False)

    _paper_detail_paths: dict[str, Path] | None = field(default=None, init=False)
    _artifact_links_by_canonical_id: dict[str, list[dict[str, Any]]] | None = field(
        default=None,
        init=False,
    )
    _artifact_entities_by_id: dict[str, dict[str, Any]] | None = field(
        default=None,
        init=False,
    )
    _github_metadata_by_artifact_id: dict[str, dict[str, Any]] | None = field(
        default=None,
        init=False,
    )
    _huggingface_metadata_by_artifact_id: dict[str, dict[str, Any]] | None = field(
        default=None,
        init=False,
    )

    _topic_clusters_payload: dict[str, Any] | None = field(default=None, init=False)
    _topic_assignments_by_id: dict[str, dict[str, Any]] | None = field(default=None, init=False)
    _topic_assignments_by_cluster: dict[int, list[dict[str, Any]]] | None = field(
        default=None,
        init=False,
    )
    _topic_projection_summary: dict[str, Any] | None = field(default=None, init=False)
    _topic_projection_points: list[dict[str, Any]] | None = field(default=None, init=False)

    def reload(self) -> None:
        self._profiles_payload = None
        self._feature_rows = None
        self._features_by_id = None
        self._canonical_by_id = None
        self._dense_bundle = None
        self._normalized_embeddings = None
        self._dense_id_to_index = None

        self._paper_detail_paths = None
        self._artifact_links_by_canonical_id = None
        self._artifact_entities_by_id = None
        self._github_metadata_by_artifact_id = None
        self._huggingface_metadata_by_artifact_id = None

        self._topic_clusters_payload = None
        self._topic_assignments_by_id = None
        self._topic_assignments_by_cluster = None
        self._topic_projection_summary = None
        self._topic_projection_points = None

    def _load_profiles_payload(self) -> dict[str, Any]:
        if self._profiles_payload is None:
            self._profiles_payload = load_ranking_profiles(self.profiles_path)
        return self._profiles_payload

    def _load_feature_rows(self) -> list[dict[str, Any]]:
        if self._feature_rows is None:
            self._feature_rows = load_feature_rows(self.features_path)
        return self._feature_rows

    def list_profiles(self) -> dict[str, Any]:
        payload = self._load_profiles_payload()
        profiles_map = payload.get("profiles") or {}
        profiles = [profiles_map[name] for name in sorted(profiles_map.keys())]

        return {
            "schema_version": payload.get("schema_version"),
            "default_profile": payload.get("default_profile"),
            "profile_count": len(profiles),
            "profiles": profiles,
        }

    def get_ranking(
        self,
        *,
        profile_name: str,
        top_k: int | None = None,
        query_title: str | None = None,
        source_family: str | None = None,
        min_year: int | None = None,
        max_year: int | None = None,
        has_code: bool | None = None,
        has_dataset: bool | None = None,
        has_model: bool | None = None,
        has_demo: bool | None = None,
        has_github: bool | None = None,
        has_hf: bool | None = None,
        has_acl: bool | None = None,
        has_doi: bool | None = None,
        sort_by: str | None = None,
        descending: bool | None = None,
    ) -> dict[str, Any]:
        profiles_payload = self._load_profiles_payload()
        profile = get_ranking_profile(profiles_payload, profile_name)

        resolved_top_k = int(top_k if top_k is not None else profile["top_k"])
        resolved_sort_by = str(sort_by or profile["sort_by"])
        resolved_descending = (
            bool(profile.get("descending", True))
            if descending is None
            else bool(descending)
        )

        filter_values: dict[str, Any] = dict(profile.get("filters") or {})

        filter_overrides = {
            "query_title": query_title,
            "source_family": source_family,
            "min_year": min_year,
            "max_year": max_year,
            "has_code": has_code,
            "has_dataset": has_dataset,
            "has_model": has_model,
            "has_demo": has_demo,
            "has_github": has_github,
            "has_hf": has_hf,
            "has_acl": has_acl,
            "has_doi": has_doi,
        }

        for key, value in filter_overrides.items():
            if value is not None:
                filter_values[key] = value

        filters = RankingFilters(**filter_values)
        rows = self._load_feature_rows()

        report = rank_feature_rows(
            rows,
            filters=filters,
            sort_by=resolved_sort_by,
            top_k=resolved_top_k,
            descending=resolved_descending,
            include_explanations=False,
        )

        report["features_path"] = normalize_path(self.features_path)
        report["profile"] = {
            **profile,
            "loaded": True,
            "profiles_path": normalize_path(self.profiles_path),
        }

        return report

    def get_paper_detail(
        self,
        *,
        canonical_id: str,
        view: str = "full",
    ) -> dict[str, Any]:
        if view != "full":
            raise ValueError("Only view='full' is supported in Discovery API v1")

        detail, resolved_paths = build_paper_detail_from_config(
            canonical_id=canonical_id,
            config_path=self.paper_features_config_path,
        )

        return {
            "canonical_id": canonical_id,
            "found": bool(detail.get("found")),
            "inputs": resolved_paths,
            "detail": detail,
        }

    def get_similar_papers(
        self,
        *,
        canonical_id: str,
        top_k: int = 20,
        rank_by: str = "semantic",
        min_similarity: float | None = None,
    ) -> dict[str, Any]:
        bundle, normalized_embeddings, id_to_index = self._load_dense_runtime()

        return find_similar_papers_from_loaded(
            canonical_id=canonical_id,
            bundle=bundle,
            normalized_embeddings=normalized_embeddings,
            id_to_index=id_to_index,
            features_by_id=self._load_features_by_id(),
            canonical_by_id=self._load_canonical_by_id(),
            dense_dir=self.dense_dir,
            manifest_path=self.retrieval_manifest_path,
            features_path=self.features_path,
            canonical_path=self.canonical_path,
            top_k=top_k,
            rank_by=rank_by,
            min_similarity=min_similarity,
        )

    def compare_papers(
        self,
        *,
        canonical_ids: list[str],
        citation_graph_by_canonical_id: dict[str, dict[str, Any]] | None = None,
        citation_graph_capability: dict[str, Any] | None = None,
        initial_warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_ids = [
            str(canonical_id).strip()
            for canonical_id in canonical_ids
        ]
        if not 2 <= len(normalized_ids) <= 5:
            raise ValueError("Paper comparison requires 2 to 5 canonical_ids")
        if any(not canonical_id for canonical_id in normalized_ids):
            raise ValueError("canonical_ids must be non-empty")
        if len(set(normalized_ids)) != len(normalized_ids):
            raise ValueError("canonical_ids must be unique")

        canonical_by_id = self._load_canonical_by_id()
        missing_ids = [
            canonical_id
            for canonical_id in normalized_ids
            if canonical_id not in canonical_by_id
        ]
        if missing_ids:
            raise PaperComparisonPaperNotFoundError(missing_ids)

        features_by_id = self._load_features_by_id()
        warnings = list(initial_warnings or [])
        capabilities: dict[str, Any] = {
            "citation_graph": citation_graph_capability
            or {
                "available": False,
                "reason": "citation_graph_context_not_provided",
            },
        }

        artifacts_by_canonical_id: dict[str, list[dict[str, Any]]] = {}
        try:
            (
                detail_paths,
                artifact_links_by_canonical_id,
                entities_by_id,
                github_by_artifact_id,
                huggingface_by_artifact_id,
            ) = self._load_comparison_artifact_indexes()

            artifacts_by_canonical_id = {
                canonical_id: build_artifact_detail_rows(
                    artifact_links=artifact_links_by_canonical_id.get(
                        canonical_id,
                        [],
                    ),
                    entities_by_id=entities_by_id,
                    github_metadata_by_artifact_id=github_by_artifact_id,
                    huggingface_metadata_by_artifact_id=huggingface_by_artifact_id,
                )
                for canonical_id in normalized_ids
            }
            capabilities["artifact_details"] = {
                "available": detail_paths["artifact_links_path"].is_file(),
                "artifact_entities_available": detail_paths[
                    "artifact_entities_path"
                ].is_file(),
                "github_metadata_available": detail_paths[
                    "github_metadata_path"
                ].is_file(),
                "huggingface_metadata_available": detail_paths[
                    "huggingface_metadata_path"
                ].is_file(),
                "inputs": {
                    key: normalize_path(path)
                    for key, path in detail_paths.items()
                },
            }
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            capabilities["artifact_details"] = {
                "available": False,
                "reason": f"{type(exc).__name__}: {exc}",
            }
            warnings.append(
                "artifact_detail_rows_unavailable; feature-level artifact "
                "signals remain available"
            )

        normalized_embeddings = None
        dense_id_to_index = None
        try:
            bundle, normalized_embeddings, dense_id_to_index = (
                self._load_dense_runtime()
            )
            retrieval_manifest = load_latest_retrieval_manifest(
                self.retrieval_manifest_path
            )
            capabilities["semantic_similarity"] = {
                "available": True,
                "reason": None,
                "retrieval_build_id": (
                    retrieval_manifest.get("build_id")
                    or retrieval_manifest.get("retrieval_build_id")
                ),
                "embedding_model": (
                    retrieval_manifest.get("embedding_model_name")
                    or retrieval_manifest.get("model_name")
                ),
                "embedding_path": normalize_path(bundle.embedding_path),
                "embedding_shape": list(bundle.embeddings.shape),
                "ids_count": len(bundle.ids),
            }
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            capabilities["semantic_similarity"] = {
                "available": False,
                "reason": f"{type(exc).__name__}: {exc}",
                "retrieval_build_id": None,
            }
            warnings.append(
                "semantic_similarity_unavailable; metadata comparison remains valid"
            )

        clusters_by_canonical_id: dict[str, dict[str, Any]] = {}
        try:
            cluster_payload = self._load_topic_clusters_payload()
            assignments_by_id = self._load_topic_assignments_by_id()
            clusters_by_id = cluster_payload["clusters_by_id"]

            for canonical_id in normalized_ids:
                assignment = assignments_by_id.get(canonical_id)
                if assignment is None:
                    clusters_by_canonical_id[canonical_id] = {"found": False}
                    continue

                cluster_id = _cluster_id_of(assignment)
                cluster_summary = clusters_by_id.get(cluster_id) or {}
                clusters_by_canonical_id[canonical_id] = {
                    **assignment,
                    "found": True,
                    "cluster_id": cluster_id,
                    "label_candidates": cluster_summary.get(
                        "label_candidates"
                    )
                    or [],
                }

            capabilities["topic_clusters"] = {
                "available": True,
                "reason": None,
                "cluster_build_id": cluster_payload.get("cluster_build_id"),
                "retrieval_build_id": cluster_payload.get(
                    "retrieval_build_id"
                ),
                "cluster_config_hash": cluster_payload.get(
                    "cluster_config_hash"
                ),
            }
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            capabilities["topic_clusters"] = {
                "available": False,
                "reason": f"{type(exc).__name__}: {exc}",
                "cluster_build_id": None,
                "retrieval_build_id": None,
            }
            warnings.append(
                "topic_cluster_context_unavailable; comparison remains valid"
            )

        return build_paper_comparison(
            canonical_ids=normalized_ids,
            canonical_by_id=canonical_by_id,
            features_by_id=features_by_id,
            artifacts_by_canonical_id=artifacts_by_canonical_id,
            clusters_by_canonical_id=clusters_by_canonical_id,
            citation_graph_by_canonical_id=citation_graph_by_canonical_id,
            normalized_embeddings=normalized_embeddings,
            dense_id_to_index=dense_id_to_index,
            capabilities=capabilities,
            warnings=warnings,
        )

    def get_topic_clusters(
            self,
            *,
            limit: int = 20,
            offset: int = 0,
            sort_by: str = "size_desc",
            include_representatives: bool = True,
            min_size: int | None = None,
    ) -> dict[str, Any]:
        payload = self._load_topic_clusters_payload()
        clusters = list(payload["clusters"])

        if min_size is not None:
            clusters = [
                cluster
                for cluster in clusters
                if _safe_int(cluster.get("size")) >= min_size
            ]

        clusters = _sort_clusters(clusters, sort_by=sort_by)
        total = len(clusters)
        returned = clusters[offset: offset + limit]

        if not include_representatives:
            cleaned: list[dict[str, Any]] = []
            for cluster in returned:
                item = dict(cluster)
                item["representative_papers"] = []
                cleaned.append(item)
            returned = cleaned

        return {
            "mode": "topic_clusters",
            "cluster_build_id": payload["cluster_build_id"],
            "retrieval_build_id": payload["retrieval_build_id"],
            "cluster_config_hash": payload.get("cluster_config_hash"),
            "algorithm": payload.get("algorithm"),
            "params": payload.get("params") or {},
            "embedding_model": payload.get("embedding_model"),
            "embedding_shape": payload.get("embedding_shape") or [],
            "cluster_count": payload["cluster_count"],
            "total": total,
            "offset": offset,
            "limit": limit,
            "returned_count": len(returned),
            "sort_by": sort_by,
            "inputs": payload["inputs"],
            "results": returned,
        }

    def get_topic_cluster_map(
        self,
        *,
        include_papers: bool = False,
        max_points: int = 5000,
    ) -> dict[str, Any]:
        if max_points <= 0:
            raise ValueError("max_points must be positive")

        payload = self._load_topic_clusters_payload()
        projection_summary = self._load_topic_projection_summary()
        points = self._load_topic_projection_points()
        summary_counts = projection_summary.get("counts") or {}
        summary_method = projection_summary.get("method") or {}

        if include_papers:
            filtered_points = list(points)
        else:
            filtered_points = [
                point
                for point in points
                if str(point.get("point_type") or "").lower() == "centroid"
            ]

        returned_points = filtered_points[:max_points]

        return {
            "mode": "topic_cluster_map",
            "projection_build_id": str(projection_summary.get("projection_build_id") or ""),
            "cluster_build_id": payload["cluster_build_id"],
            "retrieval_build_id": payload["retrieval_build_id"],
            "cluster_config_hash": payload.get("cluster_config_hash"),
            "projection_algorithm": summary_method.get("algorithm"),
            "point_count": _safe_int(
                summary_counts.get("point_count"),
                default=len(points),
            ),
            "centroid_count": _safe_int(
                summary_counts.get("centroid_count"),
                default=sum(
                    1
                    for point in points
                    if str(point.get("point_type") or "").lower() == "centroid"
                ),
            ),
            "representative_count": _safe_int(
                summary_counts.get("representative_count"),
                default=sum(1 for point in points if point.get("is_representative")),
            ),
            "sampled_count": _safe_int(
                summary_counts.get("sampled_count"),
                default=sum(1 for point in points if point.get("is_sampled")),
            ),
            "total_points_count": len(filtered_points),
            "returned_points_count": len(returned_points),
            "include_papers": include_papers,
            "max_points": max_points,
            "inputs": {
                **payload["inputs"],
                "projection_path": payload["inputs"].get("projection_path"),
                "projection_summary_path": payload["inputs"].get("projection_summary_path"),
            },
            "points": returned_points,
        }

    def get_topic_cluster(
            self,
            *,
            cluster_id: int,
            top_k: int = 20,
            sort_by: str = "rank",
            min_year: int | None = None,
            max_year: int | None = None,
            has_code: bool | None = None,
            has_dataset: bool | None = None,
            has_model: bool | None = None,
            has_demo: bool | None = None,
            has_github: bool | None = None,
            has_hf: bool | None = None,
            has_acl: bool | None = None,
            has_doi: bool | None = None,
            min_radar_score: float | None = None,
            min_implementation_readiness_score: float | None = None,
            min_citation_signal_score: float | None = None,
    ) -> dict[str, Any]:
        payload = self._load_topic_clusters_payload()
        clusters_by_id = payload["clusters_by_id"]
        summary = clusters_by_id.get(cluster_id)

        filters = _effective_topic_cluster_filters(
            min_year=min_year,
            max_year=max_year,
            has_code=has_code,
            has_dataset=has_dataset,
            has_model=has_model,
            has_demo=has_demo,
            has_github=has_github,
            has_hf=has_hf,
            has_acl=has_acl,
            has_doi=has_doi,
            min_radar_score=min_radar_score,
            min_implementation_readiness_score=min_implementation_readiness_score,
            min_citation_signal_score=min_citation_signal_score,
        )

        if summary is None:
            return {
                "mode": "topic_cluster_detail",
                "cluster_id": cluster_id,
                "found": False,
                "cluster_build_id": payload.get("cluster_build_id"),
                "retrieval_build_id": payload.get("retrieval_build_id"),
                "cluster_config_hash": payload.get("cluster_config_hash"),
                "summary": {},
                "total_papers": 0,
                "filtered_papers_count": 0,
                "returned_papers_count": 0,
                "top_k": top_k,
                "sort_by": sort_by,
                "filters": filters,
                "inputs": payload["inputs"],
                "papers": [],
            }

        assignments_by_cluster = self._load_topic_assignments_by_cluster()

        papers = list(assignments_by_cluster.get(cluster_id, []))
        total_papers = len(papers)

        filtered_papers = _apply_topic_cluster_paper_filters(
            papers,
            min_year=min_year,
            max_year=max_year,
            has_code=has_code,
            has_dataset=has_dataset,
            has_model=has_model,
            has_demo=has_demo,
            has_github=has_github,
            has_hf=has_hf,
            has_acl=has_acl,
            has_doi=has_doi,
            min_radar_score=min_radar_score,
            min_implementation_readiness_score=min_implementation_readiness_score,
            min_citation_signal_score=min_citation_signal_score,
        )

        filtered_papers = _sort_cluster_papers(filtered_papers, sort_by=sort_by)
        returned_papers = filtered_papers[:top_k]

        return {
            "mode": "topic_cluster_detail",
            "cluster_id": cluster_id,
            "found": True,
            "cluster_build_id": payload.get("cluster_build_id"),
            "retrieval_build_id": payload.get("retrieval_build_id"),
            "cluster_config_hash": payload.get("cluster_config_hash"),
            "summary": summary,
            "total_papers": total_papers,
            "filtered_papers_count": len(filtered_papers),
            "returned_papers_count": len(returned_papers),
            "top_k": top_k,
            "sort_by": sort_by,
            "filters": filters,
            "inputs": payload["inputs"],
            "papers": returned_papers,
        }

    def get_paper_topic_cluster(
        self,
        *,
        canonical_id: str,
    ) -> dict[str, Any]:
        payload = self._load_topic_clusters_payload()
        assignments_by_id = self._load_topic_assignments_by_id()

        assignment = assignments_by_id.get(canonical_id)
        if assignment is None:
            return {
                "mode": "paper_topic_cluster",
                "canonical_id": canonical_id,
                "found": False,
                "cluster_build_id": payload.get("cluster_build_id"),
                "retrieval_build_id": payload.get("retrieval_build_id"),
                "cluster_config_hash": payload.get("cluster_config_hash"),
                "assignment": None,
                "cluster": None,
                "inputs": payload["inputs"],
            }

        cluster_id = _cluster_id_of(assignment)
        cluster = payload["clusters_by_id"].get(cluster_id)

        return {
            "mode": "paper_topic_cluster",
            "canonical_id": canonical_id,
            "found": True,
            "cluster_build_id": payload.get("cluster_build_id"),
            "retrieval_build_id": payload.get("retrieval_build_id"),
            "cluster_config_hash": payload.get("cluster_config_hash"),
            "assignment": assignment,
            "cluster": cluster,
            "inputs": payload["inputs"],
        }

    def _load_features_by_id(self) -> dict[str, dict[str, Any]]:
        if self._features_by_id is None:
            rows = self._load_feature_rows()
            self._features_by_id = {
                str(row["canonical_id"]): row
                for row in rows
                if row.get("canonical_id")
            }
        return self._features_by_id

    def _load_canonical_by_id(self) -> dict[str, dict[str, Any]]:
        if self._canonical_by_id is None:
            self._canonical_by_id = load_jsonl_by_canonical_id(
                self.canonical_path,
                optional=True,
            )
        return self._canonical_by_id

    def _load_comparison_artifact_indexes(
        self,
    ) -> tuple[
        dict[str, Path],
        dict[str, list[dict[str, Any]]],
        dict[str, dict[str, Any]],
        dict[str, dict[str, Any]],
        dict[str, dict[str, Any]],
    ]:
        if self._paper_detail_paths is None:
            self._paper_detail_paths = load_paper_features_config_paths(
                self.paper_features_config_path
            )

        paths = self._paper_detail_paths

        if self._artifact_links_by_canonical_id is None:
            by_canonical_id: dict[str, list[dict[str, Any]]] = {}
            artifact_links_path = paths["artifact_links_path"]
            if artifact_links_path.is_file():
                for row in _read_jsonl(artifact_links_path):
                    canonical_id = str(row.get("canonical_id") or "").strip()
                    if canonical_id:
                        by_canonical_id.setdefault(canonical_id, []).append(row)
            self._artifact_links_by_canonical_id = by_canonical_id

        if self._artifact_entities_by_id is None:
            path = paths["artifact_entities_path"]
            self._artifact_entities_by_id = (
                load_jsonl_by_key(path, key="artifact_id")
                if path.is_file()
                else {}
            )

        if self._github_metadata_by_artifact_id is None:
            path = paths["github_metadata_path"]
            self._github_metadata_by_artifact_id = (
                load_jsonl_by_key(path, key="artifact_id")
                if path.is_file()
                else {}
            )

        if self._huggingface_metadata_by_artifact_id is None:
            path = paths["huggingface_metadata_path"]
            self._huggingface_metadata_by_artifact_id = (
                load_jsonl_by_key(path, key="artifact_id")
                if path.is_file()
                else {}
            )

        return (
            paths,
            self._artifact_links_by_canonical_id,
            self._artifact_entities_by_id,
            self._github_metadata_by_artifact_id,
            self._huggingface_metadata_by_artifact_id,
        )

    def _load_dense_runtime(self) -> tuple[DenseBundle, Any, dict[str, int]]:
        if (
            self._dense_bundle is None
            or self._normalized_embeddings is None
            or self._dense_id_to_index is None
        ):
            bundle = load_dense_bundle(
                dense_dir=self.dense_dir,
                manifest_path=self.retrieval_manifest_path,
            )
            self._dense_bundle = bundle
            self._normalized_embeddings = normalize_embeddings(bundle.embeddings)
            self._dense_id_to_index = {
                doc_id: idx
                for idx, doc_id in enumerate(bundle.ids)
            }

        return (
            self._dense_bundle,
            self._normalized_embeddings,
            self._dense_id_to_index,
        )

    def _load_topic_clusters_payload(self) -> dict[str, Any]:
        if self._topic_clusters_payload is not None:
            return self._topic_clusters_payload

        latest_path = self.topic_clusters_latest_path
        if not latest_path.exists():
            raise FileNotFoundError(f"Topic clusters latest file not found: {latest_path}")

        latest = _read_json(latest_path)

        run_dir = _as_path(latest.get("run_dir"))
        if run_dir is None:
            cluster_build_id = latest.get("cluster_build_id")
            if not cluster_build_id:
                raise ValueError(
                    f"Topic clusters latest file has no run_dir or cluster_build_id: {latest_path}"
                )
            run_dir = latest_path.parent / "runs" / str(cluster_build_id)

        summary_path = _as_path(latest.get("summary_path"))
        if summary_path is None:
            summary_path = run_dir / "summary.json"

        label_candidates_path = _as_path(latest.get("label_candidates_path"))
        if label_candidates_path is None:
            label_candidates_path = run_dir / "label_candidates.json"

        assignments_path = _as_path(latest.get("assignments_path"))
        projection_payload = latest.get("projection") or {}
        if not isinstance(projection_payload, dict):
            projection_payload = {}

        projection_path = _as_path(
            projection_payload.get("projection_path")
            or latest.get("projection_path"),
            base_dir=run_dir,
        )
        if projection_path is None:
            projection_path = run_dir / "projection_2d.jsonl"

        projection_summary_path = _as_path(
            projection_payload.get("projection_summary_path")
            or latest.get("projection_summary_path"),
            base_dir=run_dir,
        )
        if projection_summary_path is None:
            projection_summary_path = run_dir / "projection_summary.json"
        if assignments_path is None:
            assignments_path = run_dir / "assignments.jsonl"

        if not summary_path.exists():
            raise FileNotFoundError(f"Topic clusters summary file not found: {summary_path}")

        if not label_candidates_path.exists():
            raise FileNotFoundError(
                f"Topic clusters label candidates file not found: {label_candidates_path}"
            )

        if not assignments_path.exists():
            raise FileNotFoundError(
                f"Topic clusters assignments file not found: {assignments_path}"
            )

        summary = _read_json(summary_path)
        label_payload = _read_json(label_candidates_path)

        labels_by_cluster_id = {
            _cluster_id_of(row): row
            for row in label_payload.get("clusters", [])
            if isinstance(row, dict)
        }

        raw_clusters = summary.get("clusters") or []
        if not isinstance(raw_clusters, list):
            raise ValueError(f"summary.clusters must be a list in {summary_path}")

        clusters: list[dict[str, Any]] = []
        for row in raw_clusters:
            if not isinstance(row, dict):
                continue
            clusters.append(
                _merge_cluster_labels(
                    summary_cluster=row,
                    labels_by_cluster_id=labels_by_cluster_id,
                )
            )

        clusters_by_id = {
            _cluster_id_of(cluster): cluster
            for cluster in clusters
        }

        cluster_build_id = str(
            latest.get("cluster_build_id")
            or summary.get("cluster_build_id")
            or label_payload.get("cluster_build_id")
            or ""
        )
        retrieval_build_id = str(
            latest.get("retrieval_build_id")
            or summary.get("retrieval_build_id")
            or label_payload.get("retrieval_build_id")
            or ""
        )

        if not cluster_build_id:
            raise ValueError("Topic clusters payload has no cluster_build_id")

        if not retrieval_build_id:
            raise ValueError("Topic clusters payload has no retrieval_build_id")

        self._topic_clusters_payload = {
            "cluster_build_id": cluster_build_id,
            "retrieval_build_id": retrieval_build_id,
            "cluster_config_hash": (
                latest.get("cluster_config_hash")
                or summary.get("cluster_config_hash")
                or label_payload.get("cluster_config_hash")
            ),
            "algorithm": latest.get("algorithm") or summary.get("algorithm"),
            "params": latest.get("params") or summary.get("params") or {},
            "embedding_model": latest.get("embedding_model") or summary.get("embedding_model"),
            "embedding_shape": latest.get("embedding_shape") or summary.get("embedding_shape") or [],
            "cluster_count": _safe_int(
                latest.get("cluster_count")
                or summary.get("cluster_count")
                or len(clusters)
            ),
            "clusters": clusters,
            "clusters_by_id": clusters_by_id,
            "inputs": {
                "latest_path": normalize_path(latest_path),
                "run_dir": normalize_path(run_dir),
                "summary_path": normalize_path(summary_path),
                "label_candidates_path": normalize_path(label_candidates_path),
                "assignments_path": normalize_path(assignments_path),
                "projection_path": normalize_path(projection_path),
                "projection_summary_path": normalize_path(projection_summary_path),
            },
        }

        return self._topic_clusters_payload

    def _load_topic_assignments_by_id(self) -> dict[str, dict[str, Any]]:
        if self._topic_assignments_by_id is None:
            self._load_topic_assignments()
        assert self._topic_assignments_by_id is not None
        return self._topic_assignments_by_id

    def _load_topic_assignments_by_cluster(self) -> dict[int, list[dict[str, Any]]]:
        if self._topic_assignments_by_cluster is None:
            self._load_topic_assignments()
        assert self._topic_assignments_by_cluster is not None
        return self._topic_assignments_by_cluster

    def _load_topic_assignments(self) -> None:
        payload = self._load_topic_clusters_payload()
        assignments_path = Path(payload["inputs"]["assignments_path"])

        rows = _read_jsonl(assignments_path)

        by_id: dict[str, dict[str, Any]] = {}
        by_cluster: dict[int, list[dict[str, Any]]] = {}

        for row in rows:
            canonical_id = str(row.get("canonical_id") or "").strip()
            if not canonical_id:
                continue

            cluster_id = _cluster_id_of(row)
            by_id[canonical_id] = row
            by_cluster.setdefault(cluster_id, []).append(row)

        self._topic_assignments_by_id = by_id
        self._topic_assignments_by_cluster = by_cluster

    def _load_topic_projection_summary(self) -> dict[str, Any]:
        if self._topic_projection_summary is not None:
            return self._topic_projection_summary

        payload = self._load_topic_clusters_payload()
        summary_path_raw = payload["inputs"].get("projection_summary_path")
        if not summary_path_raw:
            raise FileNotFoundError("Topic projection summary path is not configured")

        summary_path = Path(summary_path_raw)
        if not summary_path.exists():
            raise FileNotFoundError(f"Topic projection summary file not found: {summary_path}")

        summary = _read_json(summary_path)

        cluster_build_id = str(summary.get("cluster_build_id") or "")
        retrieval_build_id = str(summary.get("retrieval_build_id") or "")

        if cluster_build_id and cluster_build_id != payload["cluster_build_id"]:
            raise ValueError(
                "Topic projection cluster_build_id does not match topic clusters payload: "
                f"{cluster_build_id} != {payload['cluster_build_id']}"
            )

        if retrieval_build_id and retrieval_build_id != payload["retrieval_build_id"]:
            raise ValueError(
                "Topic projection retrieval_build_id does not match topic clusters payload: "
                f"{retrieval_build_id} != {payload['retrieval_build_id']}"
            )

        self._topic_projection_summary = summary
        return self._topic_projection_summary

    def _load_topic_projection_points(self) -> list[dict[str, Any]]:
        if self._topic_projection_points is not None:
            return self._topic_projection_points

        payload = self._load_topic_clusters_payload()
        projection_path_raw = payload["inputs"].get("projection_path")
        if not projection_path_raw:
            raise FileNotFoundError("Topic projection path is not configured")

        projection_path = Path(projection_path_raw)
        if not projection_path.exists():
            raise FileNotFoundError(f"Topic projection file not found: {projection_path}")

        rows = _read_jsonl(projection_path)
        points = [_normalize_projection_point(row) for row in rows]

        if not points:
            raise ValueError(f"Topic projection has no points: {projection_path}")

        self._topic_projection_points = points
        return self._topic_projection_points


_DISCOVERY_SERVICE = DiscoveryService()


def get_discovery_service() -> DiscoveryService:
    return _DISCOVERY_SERVICE
