"""Qdrant retrieval store adapter for ML Research Radar.

This module is intentionally small and runtime-safe:
- it does not build embeddings;
- it does not create or mutate collections;
- it does not read or modify canonical truth;
- it only provides health/count/info/search access to an existing Qdrant collection.

The collection is expected to be produced by:
    python -m scripts.evaluation.run_qdrant_retrieval_benchmark
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class QdrantSearchResult:
    """Normalized Qdrant search result."""

    point_id: int | str | None
    canonical_id: str | None
    score: float | None
    dense_index: int | None = None
    payload: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class QdrantRetrievalStore:
    """Thin read-only adapter over a Qdrant collection."""

    def __init__(
            self,
            *,
            host: str = "localhost",
            port: int = 6333,
            grpc_port: int = 6334,
            prefer_grpc: bool = False,
            collection_name: str,
            timeout_sec: float = 120.0,
            check_compatibility: bool = True,
    ) -> None:
        from qdrant_client import QdrantClient

        if (
                not isinstance(grpc_port, int)
                or isinstance(grpc_port, bool)
                or not 1 <= grpc_port <= 65535
        ):
            raise ValueError(
                "grpc_port must be an integer in range "
                f"1..65535, got {grpc_port!r}"
            )

        if not isinstance(prefer_grpc, bool):
            raise ValueError(
                "prefer_grpc must be a boolean, "
                f"got {prefer_grpc!r}"
            )

        self.host = host
        self.port = port
        self.grpc_port = grpc_port
        self.prefer_grpc = prefer_grpc
        self.transport = "grpc" if prefer_grpc else "rest"

        self.collection_name = collection_name
        self.timeout_sec = timeout_sec
        self.check_compatibility = check_compatibility

        self.client = QdrantClient(
            host=host,
            port=port,
            grpc_port=grpc_port,
            prefer_grpc=prefer_grpc,
            timeout=timeout_sec,
            check_compatibility=check_compatibility,
        )

    def collection_exists(self) -> bool:
        collections = self.client.get_collections()
        names: list[str] = []
        for collection in getattr(collections, "collections", []) or []:
            name = getattr(collection, "name", None)
            if name:
                names.append(str(name))
        return self.collection_name in names

    def count_points(self, *, exact: bool = True) -> int:
        count_result = self.client.count(
            collection_name=self.collection_name,
            exact=exact,
        )
        return int(getattr(count_result, "count", 0))

    def get_collection_info(self) -> dict[str, Any]:
        info = self.client.get_collection(collection_name=self.collection_name)
        return {
            "collection_name": self.collection_name,
            "points_count": _safe_get(info, "points_count"),
            "indexed_vectors_count": _safe_get(info, "indexed_vectors_count"),
            "vectors_count": _safe_get(info, "vectors_count"),
            "status": str(_safe_get(info, "status")),
            "optimizer_status": str(_safe_get(info, "optimizer_status")),
            "vector_size": extract_vector_size(info),
            "distance": extract_distance(info),
        }

    def search_vector(
            self,
            vector: Iterable[float],
            *,
            top_k: int = 20,
            with_payload: bool = True,
            with_vectors: bool = False,
            exact: bool = False,
            hnsw_ef: int | None = None,
    ) -> list[QdrantSearchResult]:
        """Search an existing Qdrant collection with an explicit profile.

        ``exact=False`` and ``hnsw_ef=None`` preserve the previous default
        Qdrant search behavior.

        Uses ``query_points`` on newer clients and falls back to ``search`` on
        older client/server combinations.
        """

        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k <= 0:
            raise ValueError(
                f"top_k must be a positive integer, got {top_k!r}"
            )

        if not isinstance(exact, bool):
            raise ValueError(
                f"exact must be a boolean, got {exact!r}"
            )

        if hnsw_ef is not None:
            if (
                    not isinstance(hnsw_ef, int)
                    or isinstance(hnsw_ef, bool)
                    or hnsw_ef <= 0
            ):
                raise ValueError(
                    f"hnsw_ef must be a positive integer or None, "
                    f"got {hnsw_ef!r}"
                )

        query_vector = [float(x) for x in vector]

        search_params = None
        if exact or hnsw_ef is not None:
            from qdrant_client.http import models as qmodels

            search_params = qmodels.SearchParams(
                exact=exact,
                hnsw_ef=hnsw_ef,
            )

        if hasattr(self.client, "query_points"):
            kwargs: dict[str, Any] = {
                "collection_name": self.collection_name,
                "query": query_vector,
                "limit": top_k,
                "with_payload": with_payload,
                "with_vectors": with_vectors,
            }
            if search_params is not None:
                kwargs["search_params"] = search_params

            response = self.client.query_points(**kwargs)
            raw_results = getattr(response, "points", response)
        else:
            kwargs = {
                "collection_name": self.collection_name,
                "query_vector": query_vector,
                "limit": top_k,
                "with_payload": with_payload,
                "with_vectors": with_vectors,
            }
            if search_params is not None:
                kwargs["search_params"] = search_params

            raw_results = self.client.search(**kwargs)

        return [normalize_search_result(point) for point in raw_results or []]


def normalize_search_result(point: Any) -> QdrantSearchResult:
    payload = getattr(point, "payload", None) or {}
    if not isinstance(payload, dict):
        payload = dict(payload)

    point_id = getattr(point, "id", None)
    if point_id is None:
        point_id = getattr(point, "point_id", None)

    canonical_id = payload.get("canonical_id")
    dense_index = payload.get("dense_index")

    if canonical_id is None and isinstance(point_id, str) and len(point_id) >= 16:
        canonical_id = point_id

    if dense_index is None:
        try:
            dense_index = int(point_id) if point_id is not None else None
        except (TypeError, ValueError):
            dense_index = None

    score = getattr(point, "score", None)
    if score is not None:
        score = float(score)

    return QdrantSearchResult(
        point_id=point_id,
        canonical_id=str(canonical_id) if canonical_id is not None else None,
        score=score,
        dense_index=int(dense_index) if dense_index is not None else None,
        payload=payload,
    )


def extract_vector_size(collection_info: Any) -> int | None:
    vectors = _safe_get(collection_info, "config.params.vectors")
    if vectors is None:
        vectors = _safe_get(collection_info, "config.params.vectors_config")

    size = _safe_get(vectors, "size")
    if size is not None:
        try:
            return int(size)
        except (TypeError, ValueError):
            return None

    if isinstance(vectors, Mapping):
        for value in vectors.values():
            size = _safe_get(value, "size")
            if size is not None:
                try:
                    return int(size)
                except (TypeError, ValueError):
                    return None

    return None


def extract_distance(collection_info: Any) -> str | None:
    vectors = _safe_get(collection_info, "config.params.vectors")
    if vectors is None:
        vectors = _safe_get(collection_info, "config.params.vectors_config")

    distance = _safe_get(vectors, "distance")
    if distance is not None:
        return str(distance)

    if isinstance(vectors, Mapping):
        for value in vectors.values():
            distance = _safe_get(value, "distance")
            if distance is not None:
                return str(distance)

    return None


def _safe_get(obj: Any, dotted_path: str, default: Any = None) -> Any:
    current = obj
    for part in dotted_path.split("."):
        if current is None:
            return default
        if isinstance(current, Mapping):
            current = current.get(part, default)
        else:
            current = getattr(current, part, default)
    return current
