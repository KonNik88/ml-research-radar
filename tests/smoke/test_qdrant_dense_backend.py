from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from radar_core.retrieval.dense_backend import (
    DenseBackendCompatibilityError,
    DenseBackendRequestError,
    DenseBackendResultError,
    DenseBackendUnavailableError,
    DenseSearchRequest,
    QdrantDenseBackend,
    QdrantSearchProfile,
)
from radar_core.retrieval.qdrant_store import (
    QdrantRetrievalStore,
    QdrantSearchResult,
)


class CapturingClient:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] | None = None

    def query_points(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    id=0,
                    score=0.9,
                    payload={
                        "canonical_id": "a",
                        "dense_index": 0,
                        "build_id": "build-1",
                    },
                )
            ]
        )


class FakeStore:
    collection_name = "collection"

    def __init__(
        self,
        *,
        exists: bool = True,
        points_count: int = 2,
        vector_size: int = 2,
        distance: str = "Cosine",
        results: list[QdrantSearchResult] | None = None,
    ) -> None:
        self.exists = exists
        self.points_count = points_count
        self.vector_size = vector_size
        self.distance = distance
        self.results = list(results or [])

        self.collection_exists_calls = 0
        self.count_points_calls = 0
        self.get_collection_info_calls = 0
        self.search_calls: list[dict[str, Any]] = []

    def collection_exists(self) -> bool:
        self.collection_exists_calls += 1
        return self.exists

    def count_points(self, *, exact: bool = True) -> int:
        self.count_points_calls += 1
        return self.points_count

    def get_collection_info(self) -> dict[str, Any]:
        self.get_collection_info_calls += 1
        return {
            "collection_name": self.collection_name,
            "points_count": self.points_count,
            "vector_size": self.vector_size,
            "distance": self.distance,
            "status": "green",
            "optimizer_status": "ok",
        }

    def search_vector(
        self,
        vector,
        *,
        top_k: int = 20,
        with_payload: bool = True,
        with_vectors: bool = False,
        exact: bool = False,
        hnsw_ef: int | None = None,
    ) -> list[QdrantSearchResult]:
        self.search_calls.append(
            {
                "vector": list(vector),
                "top_k": top_k,
                "with_payload": with_payload,
                "with_vectors": with_vectors,
                "exact": exact,
                "hnsw_ef": hnsw_ef,
            }
        )
        return list(self.results)


def _result(
    *,
    point_id: int = 0,
    canonical_id: str = "a",
    score: float = 0.9,
    dense_index: int = 0,
    build_id: str = "build-1",
) -> QdrantSearchResult:
    return QdrantSearchResult(
        point_id=point_id,
        canonical_id=canonical_id,
        score=score,
        dense_index=dense_index,
        payload={
            "canonical_id": canonical_id,
            "dense_index": dense_index,
            "build_id": build_id,
        },
    )


def _backend(
    store: FakeStore,
    *,
    profile: QdrantSearchProfile | None = None,
    dense_ids: list[str] | None = None,
) -> QdrantDenseBackend:
    return QdrantDenseBackend(
        store=store,
        profile=profile
        or QdrantSearchProfile(
            name="ef_256",
            exact=False,
            hnsw_ef=256,
        ),
        expected_build_id="build-1",
        expected_corpus_count=2,
        expected_vector_size=2,
        expected_distance="Cosine",
        dense_ids=dense_ids,
        require_point_id_equals_dense_index=True,
    )

def test_store_configures_explicit_grpc_transport(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeQdrantClient:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(
        "qdrant_client.QdrantClient",
        FakeQdrantClient,
    )

    store = QdrantRetrievalStore(
        host="localhost",
        port=6333,
        grpc_port=6334,
        prefer_grpc=True,
        collection_name="collection",
        timeout_sec=120.0,
        check_compatibility=False,
    )

    assert store.host == "localhost"
    assert store.port == 6333
    assert store.grpc_port == 6334
    assert store.prefer_grpc is True
    assert store.transport == "grpc"

    assert captured == {
        "host": "localhost",
        "port": 6333,
        "grpc_port": 6334,
        "prefer_grpc": True,
        "timeout": 120.0,
        "check_compatibility": False,
    }


def test_store_preserves_rest_transport_by_default(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeQdrantClient:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(
        "qdrant_client.QdrantClient",
        FakeQdrantClient,
    )

    store = QdrantRetrievalStore(
        collection_name="collection",
    )

    assert store.grpc_port == 6334
    assert store.prefer_grpc is False
    assert store.transport == "rest"

    assert captured["port"] == 6333
    assert captured["grpc_port"] == 6334
    assert captured["prefer_grpc"] is False

def test_store_passes_explicit_hnsw_search_params() -> None:
    client = CapturingClient()

    store = object.__new__(QdrantRetrievalStore)
    store.collection_name = "collection"
    store.client = client

    rows = store.search_vector(
        [1.0, 0.0],
        top_k=1,
        exact=False,
        hnsw_ef=256,
    )

    assert len(rows) == 1
    assert client.kwargs is not None

    search_params = client.kwargs["search_params"]
    assert search_params.exact is False
    assert search_params.hnsw_ef == 256


def test_store_passes_explicit_exact_search_params() -> None:
    client = CapturingClient()

    store = object.__new__(QdrantRetrievalStore)
    store.collection_name = "collection"
    store.client = client

    store.search_vector(
        [1.0, 0.0],
        top_k=1,
        exact=True,
    )

    assert client.kwargs is not None
    search_params = client.kwargs["search_params"]

    assert search_params.exact is True
    assert search_params.hnsw_ef is None


def test_store_preserves_default_search_without_search_params() -> None:
    client = CapturingClient()

    store = object.__new__(QdrantRetrievalStore)
    store.collection_name = "collection"
    store.client = client

    store.search_vector(
        [1.0, 0.0],
        top_k=1,
    )

    assert client.kwargs is not None
    assert "search_params" not in client.kwargs


def test_qdrant_profile_rejects_exact_with_hnsw_ef() -> None:
    with pytest.raises(
        DenseBackendRequestError,
        match="must not define hnsw_ef",
    ):
        QdrantSearchProfile(
            name="invalid",
            exact=True,
            hnsw_ef=256,
        )


def test_qdrant_backend_returns_backend_neutral_candidates() -> None:
    store = FakeStore(
        results=[
            _result(
                point_id=0,
                canonical_id="a",
                score=0.9,
                dense_index=0,
            ),
            _result(
                point_id=1,
                canonical_id="b",
                score=0.8,
                dense_index=1,
            ),
        ]
    )
    backend = _backend(store, dense_ids=["a", "b"])

    result = backend.search(
        DenseSearchRequest(
            query_vector=np.asarray([1.0, 0.0], dtype=np.float32),
            top_k=2,
        )
    )

    assert [row.canonical_id for row in result.candidates] == ["a", "b"]
    assert [row.rank for row in result.candidates] == [1, 2]
    assert [row.dense_index for row in result.candidates] == [0, 1]
    assert [row.backend_point_id for row in result.candidates] == [0, 1]

    assert result.backend.backend_name == "qdrant"
    assert result.backend.ready is True
    assert result.backend.build_id == "build-1"
    assert result.backend.diagnostics["compatibility_checked"] is True
    assert result.backend.diagnostics["profile"]["name"] == "ef_256"

    assert store.search_calls == [
        {
            "vector": [1.0, 0.0],
            "top_k": 2,
            "with_payload": True,
            "with_vectors": False,
            "exact": False,
            "hnsw_ef": 256,
        }
    ]


def test_qdrant_backend_uses_exact_profile() -> None:
    store = FakeStore(results=[_result()])
    backend = _backend(
        store,
        profile=QdrantSearchProfile(
            name="exact",
            exact=True,
            hnsw_ef=None,
        ),
        dense_ids=["a", "b"],
    )

    backend.search(
        DenseSearchRequest(
            query_vector=np.asarray([1.0, 0.0], dtype=np.float32),
            top_k=1,
        )
    )

    assert store.search_calls[0]["exact"] is True
    assert store.search_calls[0]["hnsw_ef"] is None


def test_qdrant_backend_caches_collection_compatibility() -> None:
    store = FakeStore(results=[_result()])
    backend = _backend(store, dense_ids=["a", "b"])
    request = DenseSearchRequest(
        query_vector=np.asarray([1.0, 0.0], dtype=np.float32),
        top_k=1,
    )

    backend.search(request)
    backend.search(request)

    assert store.collection_exists_calls == 1
    assert store.count_points_calls == 1
    assert store.get_collection_info_calls == 1
    assert len(store.search_calls) == 2


def test_qdrant_backend_rejects_missing_collection() -> None:
    backend = _backend(FakeStore(exists=False))

    with pytest.raises(
        DenseBackendUnavailableError,
        match="does not exist",
    ):
        backend.search(
            DenseSearchRequest(
                query_vector=np.asarray([1.0, 0.0], dtype=np.float32),
                top_k=1,
            )
        )


def test_qdrant_backend_rejects_points_count_mismatch() -> None:
    backend = _backend(FakeStore(points_count=3))

    with pytest.raises(
        DenseBackendCompatibilityError,
        match="points count",
    ):
        backend.search(
            DenseSearchRequest(
                query_vector=np.asarray([1.0, 0.0], dtype=np.float32),
                top_k=1,
            )
        )


def test_qdrant_backend_rejects_vector_size_mismatch() -> None:
    backend = _backend(FakeStore(vector_size=3))

    with pytest.raises(
        DenseBackendCompatibilityError,
        match="vector size",
    ):
        backend.search(
            DenseSearchRequest(
                query_vector=np.asarray([1.0, 0.0], dtype=np.float32),
                top_k=1,
            )
        )


def test_qdrant_backend_rejects_distance_mismatch() -> None:
    backend = _backend(FakeStore(distance="Dot"))

    with pytest.raises(
        DenseBackendCompatibilityError,
        match="distance",
    ):
        backend.search(
            DenseSearchRequest(
                query_vector=np.asarray([1.0, 0.0], dtype=np.float32),
                top_k=1,
            )
        )


def test_qdrant_backend_rejects_query_dimension_mismatch() -> None:
    backend = _backend(FakeStore())

    with pytest.raises(
        DenseBackendRequestError,
        match="query dimension",
    ):
        backend.search(
            DenseSearchRequest(
                query_vector=np.asarray([1.0, 0.0, 0.0], dtype=np.float32),
                top_k=1,
            )
        )


def test_qdrant_backend_rejects_payload_build_mismatch() -> None:
    store = FakeStore(
        results=[
            _result(build_id="stale-build"),
        ]
    )
    backend = _backend(store)

    with pytest.raises(
        DenseBackendResultError,
        match="build_id mismatch",
    ):
        backend.search(
            DenseSearchRequest(
                query_vector=np.asarray([1.0, 0.0], dtype=np.float32),
                top_k=1,
            )
        )


def test_qdrant_backend_rejects_mapping_mismatch() -> None:
    store = FakeStore(
        results=[
            _result(
                point_id=1,
                canonical_id="a",
                dense_index=1,
            ),
        ]
    )
    backend = _backend(store, dense_ids=["a", "b"])

    with pytest.raises(
        DenseBackendResultError,
        match="dense_ids mapping mismatch",
    ):
        backend.search(
            DenseSearchRequest(
                query_vector=np.asarray([1.0, 0.0], dtype=np.float32),
                top_k=1,
            )
        )


def test_qdrant_backend_rejects_point_id_mismatch() -> None:
    store = FakeStore(
        results=[
            _result(
                point_id=99,
                canonical_id="a",
                dense_index=0,
            ),
        ]
    )
    backend = _backend(store)

    with pytest.raises(
        DenseBackendResultError,
        match="point_id does not match dense_index",
    ):
        backend.search(
            DenseSearchRequest(
                query_vector=np.asarray([1.0, 0.0], dtype=np.float32),
                top_k=1,
            )
        )


def test_qdrant_backend_rejects_duplicate_ids() -> None:
    store = FakeStore(
        results=[
            _result(
                point_id=0,
                canonical_id="a",
                dense_index=0,
            ),
            _result(
                point_id=1,
                canonical_id="a",
                dense_index=1,
            ),
        ]
    )
    backend = _backend(store)

    with pytest.raises(
        DenseBackendResultError,
        match="duplicate canonical_id",
    ):
        backend.search(
            DenseSearchRequest(
                query_vector=np.asarray([1.0, 0.0], dtype=np.float32),
                top_k=2,
            )
        )


def test_qdrant_backend_rejects_non_finite_score() -> None:
    store = FakeStore(
        results=[
            _result(score=float("nan")),
        ]
    )
    backend = _backend(store)

    with pytest.raises(
        DenseBackendResultError,
        match="non-finite score",
    ):
        backend.search(
            DenseSearchRequest(
                query_vector=np.asarray([1.0, 0.0], dtype=np.float32),
                top_k=1,
            )
        )