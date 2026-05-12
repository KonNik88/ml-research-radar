from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from radar_core.details.paper_detail import (
    DEFAULT_PAPER_FEATURES_CONFIG_PATH,
    build_paper_detail_from_config,
)
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
    load_jsonl_by_canonical_id,
    normalize_embeddings,
    normalize_path,
)

DEFAULT_TOPIC_CLUSTERS_LATEST_PATH = Path("artifacts/clusters/topic/latest.json")


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

    _topic_clusters_payload: dict[str, Any] | None = field(default=None, init=False)
    _topic_assignments_by_id: dict[str, dict[str, Any]] | None = field(default=None, init=False)
    _topic_assignments_by_cluster: dict[int, list[dict[str, Any]]] | None = field(
        default=None,
        init=False,
    )

    def reload(self) -> None:
        self._profiles_payload = None
        self._feature_rows = None
        self._features_by_id = None
        self._canonical_by_id = None
        self._dense_bundle = None
        self._normalized_embeddings = None
        self._dense_id_to_index = None

        self._topic_clusters_payload = None
        self._topic_assignments_by_id = None
        self._topic_assignments_by_cluster = None

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

    def get_topic_clusters(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "size_desc",
        include_representatives: bool = True,
    ) -> dict[str, Any]:
        payload = self._load_topic_clusters_payload()
        clusters = list(payload["clusters"])

        clusters = _sort_clusters(clusters, sort_by=sort_by)
        total = len(clusters)
        returned = clusters[offset : offset + limit]

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

    def get_topic_cluster(
        self,
        *,
        cluster_id: int,
        top_k: int = 20,
        sort_by: str = "rank",
    ) -> dict[str, Any]:
        payload = self._load_topic_clusters_payload()
        clusters_by_id = payload["clusters_by_id"]
        summary = clusters_by_id.get(cluster_id)

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
                "returned_papers_count": 0,
                "top_k": top_k,
                "sort_by": sort_by,
                "inputs": payload["inputs"],
                "papers": [],
            }

        assignments_by_cluster = self._load_topic_assignments_by_cluster()
        papers = list(assignments_by_cluster.get(cluster_id, []))
        papers = _sort_cluster_papers(papers, sort_by=sort_by)
        returned_papers = papers[:top_k]

        return {
            "mode": "topic_cluster_detail",
            "cluster_id": cluster_id,
            "found": True,
            "cluster_build_id": payload.get("cluster_build_id"),
            "retrieval_build_id": payload.get("retrieval_build_id"),
            "cluster_config_hash": payload.get("cluster_config_hash"),
            "summary": summary,
            "total_papers": len(papers),
            "returned_papers_count": len(returned_papers),
            "top_k": top_k,
            "sort_by": sort_by,
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


_DISCOVERY_SERVICE = DiscoveryService()


def get_discovery_service() -> DiscoveryService:
    return _DISCOVERY_SERVICE