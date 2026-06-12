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
        qdrant_grpc_port=6334,
        qdrant_prefer_grpc=True,
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
        "grpc_port": 6334,
        "prefer_grpc": True,
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

        self.request_started_count = 0
        self.success_records: list[dict[str, Any]] = []
        self.failure_records: list[dict[str, Any]] = []

    def get_qdrant_dense_backend(self):
        return self.backend

    def record_qdrant_request_started(self) -> None:
        self.request_started_count += 1

    def record_qdrant_success(
        self,
        *,
        result_count: int,
        timing_ms: dict[str, float],
    ) -> None:
        self.success_records.append(
            {
                "result_count": result_count,
                "timing_ms": dict(timing_ms),
            }
        )

    def record_qdrant_failure(
        self,
        *,
        category: str,
        stage: str,
        message: str,
        timing_ms: dict[str, float],
    ) -> None:
        self.failure_records.append(
            {
                "category": category,
                "stage": stage,
                "message": message,
                "timing_ms": dict(timing_ms),
            }
        )


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
    assert runtime.request_started_count == 1
    assert len(runtime.success_records) == 1
    assert runtime.failure_records == []

    success_record = runtime.success_records[0]
    assert success_record["result_count"] == 1
    assert success_record["timing_ms"]["qdrant_search_ms"] == 1.25
    assert "encode_ms" in success_record["timing_ms"]
    assert "hydrate_ms" in success_record["timing_ms"]
    assert "total_ms" in success_record["timing_ms"]

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
    assert runtime.request_started_count == 1
    assert runtime.success_records == []
    assert len(runtime.failure_records) == 1

    failure_record = runtime.failure_records[0]
    assert failure_record["category"] == "dense_backend_unavailable"
    assert failure_record["stage"] == "backend_search"
    assert failure_record["message"] == "Qdrant is unavailable"
    assert "encode_ms" in failure_record["timing_ms"]
    assert "total_ms" in failure_record["timing_ms"]


def test_experimental_service_rejects_candidate_missing_during_hydration() -> None:
    runtime = FakeRuntime()
    runtime.backend = FakeDenseBackend(
        canonical_id="missing-canonical-id"
    )

    with pytest.raises(
        DenseBackendResultError,
        match="during hydration",
    ):
        run_qdrant_experimental_search(
            runtime=runtime,
            query="dense retrieval",
            top_k=5,
        )

    assert runtime.request_started_count == 1
    assert runtime.success_records == []
    assert len(runtime.failure_records) == 1

    failure_record = runtime.failure_records[0]
    assert failure_record["category"] == "dense_backend_invalid_result"
    assert failure_record["stage"] == "hydration"
    assert "missing-canonical-id" in failure_record["message"]
    assert "qdrant_search_ms" in failure_record["timing_ms"]
    assert "total_ms" in failure_record["timing_ms"]

def test_runtime_records_bounded_qdrant_operational_state() -> None:
    runtime = ApiRuntime()

    runtime.record_qdrant_request_started()
    runtime.record_qdrant_failure(
        category="dense_backend_unavailable",
        stage="backend_search",
        message="x" * 1000,
        timing_ms={
            "encode_ms": 1.0,
            "total_ms": 3.0,
        },
    )

    state = runtime.qdrant_operational_state

    assert state.request_count == 1
    assert state.success_count == 0
    assert state.failure_count == 1
    assert state.last_status == "error"
    assert state.last_request_at is not None
    assert state.last_failure_at is not None
    assert state.last_failure_category == "dense_backend_unavailable"
    assert state.last_failure_stage == "backend_search"
    assert state.last_failure_message is not None
    assert len(state.last_failure_message) == 500
    assert state.last_failure_message.endswith("...")
    assert state.last_result_count is None
    assert state.last_timing_ms == {
        "encode_ms": 1.0,
        "total_ms": 3.0,
    }
    assert state.requested_vector_backend == "qdrant"
    assert state.effective_vector_backend is None
    assert state.fallback_applied is False

    previous_failure_at = state.last_failure_at
    previous_failure_message = state.last_failure_message

    runtime.record_qdrant_request_started()
    runtime.record_qdrant_success(
        result_count=4,
        timing_ms={
            "encode_ms": 1.5,
            "qdrant_search_ms": 2.0,
            "hydrate_ms": 0.5,
            "total_ms": 4.0,
        },
    )

    state = runtime.qdrant_operational_state

    assert state.request_count == 2
    assert state.success_count == 1
    assert state.failure_count == 1
    assert state.last_status == "ok"
    assert state.last_success_at is not None
    assert state.last_result_count == 4
    assert state.effective_vector_backend == "qdrant"
    assert state.fallback_applied is False

    # Recovery does not erase bounded evidence about the last failure.
    assert state.last_failure_at == previous_failure_at
    assert state.last_failure_message == previous_failure_message

def test_runtime_qdrant_diagnostics_uses_ttl_cache_and_force_refresh(
    monkeypatch,
) -> None:
    settings = SimpleNamespace(
        qdrant_runtime_diagnostics_ttl_sec=30.0,
        qdrant_search_profile_name="ef_256",
        qdrant_search_exact=False,
        qdrant_search_hnsw_ef=256,
    )

    monkeypatch.setattr(
        runtime_module,
        "get_settings",
        lambda: settings,
    )

    runtime = ApiRuntime(
        manifest=_manifest(),
        backend_mode="file",
    )

    probe_calls: list[int | None] = []

    def fake_probe(
        *,
        expected_corpus_doc_count: int | None,
    ) -> dict[str, Any]:
        probe_calls.append(expected_corpus_doc_count)

        return {
            "configured": True,
            "ok": True,
            "host": "localhost",
            "port": 6333,
            "collection_name": "collection",
            "timeout_sec": 120.0,
            "check_compatibility": True,
            "collection_exists": True,
            "points_count": 2,
            "expected_corpus_doc_count": expected_corpus_doc_count,
            "points_match_corpus": True,
            "vector_size": 2,
            "distance": "Cosine",
            "status": "green",
            "optimizer_status": "ok",
            "error": None,
        }

    monkeypatch.setattr(
        runtime,
        "_probe_qdrant_diagnostics",
        fake_probe,
    )

    first = runtime._qdrant_diagnostics(
        expected_corpus_doc_count=2,
    )
    second = runtime._qdrant_diagnostics(
        expected_corpus_doc_count=2,
    )
    forced = runtime._qdrant_diagnostics(
        expected_corpus_doc_count=2,
        force_refresh=True,
    )

    assert probe_calls == [2, 2]

    assert first["probe_cached"] is False
    assert first["probe_checked_at"] is not None
    assert first["probe_cache_age_sec"] == 0.0
    assert first["probe_ttl_sec"] == 30.0

    assert second["probe_cached"] is True
    assert second["probe_checked_at"] == first["probe_checked_at"]
    assert second["probe_cache_age_sec"] is not None
    assert 0.0 <= second["probe_cache_age_sec"] <= 30.0

    assert forced["probe_cached"] is False
    assert forced["probe_checked_at"] is not None
    assert forced["probe_cache_age_sec"] == 0.0

    assert forced["profile_name"] == "ef_256"
    assert forced["exact"] is False
    assert forced["hnsw_ef"] == 256
    assert forced["build_id"] == "build-1"
    assert forced["backend_created"] is False
    assert forced["compatibility_checked"] is False
    assert forced["compatibility_ok"] is None