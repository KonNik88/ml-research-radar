from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

import services.api.runtime as runtime_module
from radar_core.contracts.canonical_document import (
    CanonicalDocument,
    SourceLink,
)
from radar_core.retrieval.artifacts import (
    DenseArtifacts,
    RetrievalBuildManifest,
)
from radar_core.retrieval.dense_backend import (
    DenseBackendResultError,
    DenseBackendUnavailableError,
    DenseSearchBackendInfo,
    DenseSearchBackendResult,
    DenseSearchCandidate,
)
from services.api.runtime import ApiRuntime
from services.api.search_service import (
    run_qdrant_experimental_search,
)


class FakeQdrantStore:
    created_kwargs: dict[str, Any] | None = None

    def __init__(self, **kwargs: Any) -> None:
        type(self).created_kwargs = dict(kwargs)
        self.collection_name = str(kwargs["collection_name"])


def _manifest() -> RetrievalBuildManifest:
    return RetrievalBuildManifest(
        build_id="build-1",
        created_at="20260607T000000Z",
        corpus_path="canonical.jsonl",
        corpus_doc_count=2,
        corpus_fingerprint="fingerprint",
        lexical_index_path="lexical.pkl",
        lexical_ids_path="lexical_ids.json",
        dense_embeddings_path="embeddings.npy",
        dense_ids_path="dense_ids.json",
        dense_meta_path="dense_meta.json",
        embedding_model_name="model",
        text_fields=["title", "abstract"],
    )


def _document() -> CanonicalDocument:
    return CanonicalDocument(
        canonical_id="a",
        reconciliation_key="title_year::paper a::2026",
        doc_ids=["source-a"],
        title="Paper A",
        abstract="Dense retrieval test paper.",
        authors=["Author"],
        year=2026,
        categories=["Machine Learning"],
        tags=["retrieval"],
        sources=[SourceLink(source="arxiv")],
        source_count=1,
    )


def test_runtime_builds_and_caches_qdrant_dense_backend(
    monkeypatch,
) -> None:
    settings = SimpleNamespace(
        qdrant_host="localhost",
        qdrant_port=6333,
        qdrant_collection_name="collection",
        qdrant_timeout_sec=120.0,
        qdrant_check_compatibility=True,
        qdrant_search_profile_name="ef_256",
        qdrant_search_exact=False,
        qdrant_search_hnsw_ef=256,
    )

    monkeypatch.setattr(
        runtime_module,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        runtime_module,
        "QdrantRetrievalStore",
        FakeQdrantStore,
    )

    runtime = ApiRuntime(
        manifest=_manifest(),
        dense_artifacts=DenseArtifacts(
            embeddings=np.zeros((2, 2), dtype=np.float32),
            ids=["a", "b"],
            meta={
                "normalized": True,
                "embedding_dim": 2,
                "doc_count": 2,
            },
        ),
        backend_mode="file",
    )

    first = runtime.get_qdrant_dense_backend()
    second = runtime.get_qdrant_dense_backend()

    assert first is second
    assert runtime.qdrant_dense_backend is first

    info = first.info()
    assert info.backend_name == "qdrant"
    assert info.build_id == "build-1"
    assert info.ready is False
    assert info.diagnostics["collection_name"] == "collection"
    assert info.diagnostics["profile"] == {
        "name": "ef_256",
        "exact": False,
        "hnsw_ef": 256,
    }
    assert info.diagnostics["strict_dense_ids_mapping"] is True

    assert FakeQdrantStore.created_kwargs == {
        "host": "localhost",
        "port": 6333,
        "collection_name": "collection",
        "timeout_sec": 120.0,
        "check_compatibility": True,
    }


class FakeEmbeddingModel:
    def encode(self, *args, **kwargs):
        return np.asarray([[1.0, 0.0]], dtype=np.float32)


class FakeDenseBackend:
    def __init__(self, *, canonical_id: str = "a") -> None:
        self.request = None
        self.canonical_id = canonical_id

    def search(self, request):
        self.request = request

        return DenseSearchBackendResult(
            candidates=(
                DenseSearchCandidate(
                    canonical_id=self.canonical_id,
                    score=0.91,
                    rank=1,
                    dense_index=0,
                    backend_point_id=0,
                    backend_metadata={
                        "payload": {
                            "canonical_id": self.canonical_id,
                            "dense_index": 0,
                            "build_id": "build-1",
                        }
                    },
                ),
            ),
            backend=DenseSearchBackendInfo(
                backend_name="qdrant",
                implementation="FakeDenseBackend",
                build_id="build-1",
                ready=True,
                diagnostics={
                    "collection_name": "collection",
                    "profile": {
                        "name": "ef_256",
                        "exact": False,
                        "hnsw_ef": 256,
                    },
                },
            ),
            timing_ms={
                "backend_search_ms": 1.25,
            },
        )

class FailingDenseBackend:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.request = None

    def search(self, request):
        self.request = request
        raise self.error

class FakeRuntime:
    def __init__(self) -> None:
        self.backend_mode = "file"
        self.manifest = SimpleNamespace(build_id="build-1")
        self.documents = [_document()]
        self.embedding_model = FakeEmbeddingModel()
        self.backend = FakeDenseBackend()

    def get_qdrant_dense_backend(self):
        return self.backend


def test_experimental_service_uses_backend_neutral_candidates() -> None:
    runtime = FakeRuntime()

    response = run_qdrant_experimental_search(
        runtime=runtime,
        query="  dense retrieval  ",
        top_k=5,
    )

    assert response.query == "dense retrieval"
    assert response.mode == "dense_qdrant"
    assert response.top_k == 5
    assert response.build_id == "build-1"
    assert response.collection_name == "collection"

    assert response.meta.vector_backend == "qdrant"
    assert response.meta.source_backend == "file_runtime"
    assert response.meta.result_count == 1
    assert response.meta.timing_ms["qdrant_search_ms"] == 1.25

    assert len(response.results) == 1
    item = response.results[0]

    assert item.rank == 1
    assert item.document.canonical_id == "a"
    assert item.retrieval.score == 0.91
    assert item.retrieval.dense_score == 0.91
    assert item.point_id == 0
    assert item.dense_index == 0
    assert item.payload["build_id"] == "build-1"

    request = runtime.backend.request
    assert request is not None
    assert request.top_k == 5
    np.testing.assert_array_equal(
        request.query_vector,
        np.asarray([1.0, 0.0], dtype=np.float32),
    )

def test_experimental_service_propagates_backend_failure_without_fallback() -> None:
    runtime = FakeRuntime()
    runtime.backend = FailingDenseBackend(
        DenseBackendUnavailableError("Qdrant is unavailable")
    )

    with pytest.raises(
        DenseBackendUnavailableError,
        match="Qdrant is unavailable",
    ):
        run_qdrant_experimental_search(
            runtime=runtime,
            query="dense retrieval",
            top_k=5,
        )

    assert runtime.backend.request is not None


def test_experimental_service_rejects_candidate_missing_during_hydration() -> None:
    runtime = FakeRuntime()
    runtime.backend = FakeDenseBackend(canonical_id="missing-canonical-id")

    with pytest.raises(
        DenseBackendResultError,
        match="during hydration",
    ):
        run_qdrant_experimental_search(
            runtime=runtime,
            query="dense retrieval",
            top_k=5,
        )