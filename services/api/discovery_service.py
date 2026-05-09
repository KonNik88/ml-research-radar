from __future__ import annotations

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


@dataclass
class DiscoveryService:
    profiles_path: Path = DEFAULT_RANKING_PROFILES_PATH
    features_path: Path = DEFAULT_FEATURES_PATH
    paper_features_config_path: Path = DEFAULT_PAPER_FEATURES_CONFIG_PATH
    canonical_path: Path = DEFAULT_CANONICAL_PATH
    dense_dir: Path = DEFAULT_DENSE_DIR
    retrieval_manifest_path: Path = DEFAULT_RETRIEVAL_MANIFEST_PATH

    _profiles_payload: dict[str, Any] | None = field(default=None, init=False)
    _feature_rows: list[dict[str, Any]] | None = field(default=None, init=False)
    _features_by_id: dict[str, dict[str, Any]] | None = field(default=None, init=False)
    _canonical_by_id: dict[str, dict[str, Any]] | None = field(default=None, init=False)
    _dense_bundle: DenseBundle | None = field(default=None, init=False)
    _normalized_embeddings: Any | None = field(default=None, init=False)
    _dense_id_to_index: dict[str, int] | None = field(default=None, init=False)

    def reload(self) -> None:
        self._profiles_payload = None
        self._feature_rows = None
        self._features_by_id = None
        self._canonical_by_id = None
        self._dense_bundle = None
        self._normalized_embeddings = None
        self._dense_id_to_index = None

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
    ) -> dict[str, Any]:
        profiles_payload = self._load_profiles_payload()
        profile = get_ranking_profile(profiles_payload, profile_name)

        resolved_top_k = int(top_k or profile["top_k"])

        filters = RankingFilters(**(profile.get("filters") or {}))
        rows = self._load_feature_rows()

        report = rank_feature_rows(
            rows,
            filters=filters,
            sort_by=profile["sort_by"],
            top_k=resolved_top_k,
            descending=bool(profile.get("descending", True)),
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


_DISCOVERY_SERVICE = DiscoveryService()


def get_discovery_service() -> DiscoveryService:
    return _DISCOVERY_SERVICE