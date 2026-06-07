from __future__ import annotations

import numpy as np
import pytest

from radar_core.retrieval.dense_backend import (
    DenseBackendCompatibilityError,
    DenseBackendRequestError,
    DenseBackendResultError,
    DenseSearchRequest,
    FileDenseBackend,
    exact_file_dense_candidates,
)
from radar_core.retrieval.parity import exact_file_dense_search


def _embeddings() -> np.ndarray:
    return np.asarray(
        [
            [1.0, 0.0],
            [0.0, 1.0],
            [0.8, 0.2],
        ],
        dtype=np.float32,
    )


def _query() -> np.ndarray:
    return np.asarray([1.0, 0.0], dtype=np.float32)


def test_exact_file_dense_candidates_preserve_reference_order() -> None:
    candidates = exact_file_dense_candidates(
        embeddings=_embeddings(),
        ids=["a", "b", "c"],
        query_vector=_query(),
        top_k=3,
    )

    assert [row.canonical_id for row in candidates] == ["a", "c", "b"]
    assert [row.rank for row in candidates] == [1, 2, 3]
    assert [row.dense_index for row in candidates] == [0, 2, 1]
    assert candidates[0].score == pytest.approx(1.0)


def test_exact_file_dense_candidates_clip_top_k_to_corpus_size() -> None:
    candidates = exact_file_dense_candidates(
        embeddings=_embeddings(),
        ids=["a", "b", "c"],
        query_vector=_query(),
        top_k=100,
    )

    assert len(candidates) == 3
    assert [row.rank for row in candidates] == [1, 2, 3]


@pytest.mark.parametrize("top_k", [0, -1, True])
def test_exact_file_dense_candidates_reject_invalid_top_k(top_k) -> None:
    with pytest.raises(
        DenseBackendRequestError,
        match="top_k must be a positive integer",
    ):
        exact_file_dense_candidates(
            embeddings=_embeddings(),
            ids=["a", "b", "c"],
            query_vector=_query(),
            top_k=top_k,
        )


def test_exact_file_dense_candidates_reject_non_2d_embeddings() -> None:
    with pytest.raises(
        DenseBackendRequestError,
        match="embeddings must be two-dimensional",
    ):
        exact_file_dense_candidates(
            embeddings=np.asarray([1.0, 0.0], dtype=np.float32),
            ids=["a"],
            query_vector=_query(),
            top_k=1,
        )


def test_exact_file_dense_candidates_reject_non_1d_query() -> None:
    with pytest.raises(
        DenseBackendRequestError,
        match="query_vector must be one-dimensional",
    ):
        exact_file_dense_candidates(
            embeddings=_embeddings(),
            ids=["a", "b", "c"],
            query_vector=np.asarray([[1.0, 0.0]], dtype=np.float32),
            top_k=1,
        )


def test_exact_file_dense_candidates_reject_dimension_mismatch() -> None:
    with pytest.raises(
        DenseBackendRequestError,
        match="query dimension",
    ):
        exact_file_dense_candidates(
            embeddings=_embeddings(),
            ids=["a", "b", "c"],
            query_vector=np.asarray([1.0, 0.0, 0.0], dtype=np.float32),
            top_k=1,
        )


def test_exact_file_dense_candidates_reject_ids_count_mismatch() -> None:
    with pytest.raises(
        DenseBackendCompatibilityError,
        match="dense ids count",
    ):
        exact_file_dense_candidates(
            embeddings=_embeddings(),
            ids=["a", "b"],
            query_vector=_query(),
            top_k=1,
        )


@pytest.mark.parametrize(
    "query",
    [
        np.asarray([np.nan, 0.0], dtype=np.float32),
        np.asarray([np.inf, 0.0], dtype=np.float32),
    ],
)
def test_exact_file_dense_candidates_reject_non_finite_query(
    query: np.ndarray,
) -> None:
    with pytest.raises(
        DenseBackendRequestError,
        match="query_vector contains non-finite values",
    ):
        exact_file_dense_candidates(
            embeddings=_embeddings(),
            ids=["a", "b", "c"],
            query_vector=query,
            top_k=1,
        )


def test_exact_file_dense_candidates_reject_non_finite_scores() -> None:
    embeddings = _embeddings()
    embeddings[1, 0] = np.nan

    with pytest.raises(
        DenseBackendResultError,
        match="non-finite scores",
    ):
        exact_file_dense_candidates(
            embeddings=embeddings,
            ids=["a", "b", "c"],
            query_vector=_query(),
            top_k=3,
        )


def test_file_dense_backend_returns_backend_neutral_result() -> None:
    backend = FileDenseBackend(
        embeddings=_embeddings(),
        ids=["a", "b", "c"],
        build_id="build-1",
        normalized=True,
    )

    result = backend.search(
        DenseSearchRequest(
            query_vector=_query(),
            top_k=2,
        )
    )

    assert [row.canonical_id for row in result.candidates] == ["a", "c"]
    assert [row.rank for row in result.candidates] == [1, 2]

    assert result.backend.backend_name == "file"
    assert result.backend.implementation == "FileDenseBackend"
    assert result.backend.build_id == "build-1"
    assert result.backend.ready is True

    assert result.backend.diagnostics["rows_count"] == 3
    assert result.backend.diagnostics["vector_size"] == 2
    assert result.backend.diagnostics["normalized"] is True

    assert result.timing_ms["backend_search_ms"] >= 0.0


def test_file_dense_backend_info_is_stable() -> None:
    backend = FileDenseBackend(
        embeddings=_embeddings(),
        ids=["a", "b", "c"],
        build_id="build-1",
        normalized=True,
    )

    assert backend.info() == backend.info()
    assert backend.info().backend_name == "file"


def test_file_dense_backend_rejects_non_normalized_artifacts() -> None:
    with pytest.raises(
        DenseBackendCompatibilityError,
        match="normalized=true",
    ):
        FileDenseBackend(
            embeddings=_embeddings(),
            ids=["a", "b", "c"],
            build_id="build-1",
            normalized=False,
        )


def test_file_dense_backend_rejects_duplicate_ids() -> None:
    with pytest.raises(
        DenseBackendCompatibilityError,
        match="duplicate dense canonical_id",
    ):
        FileDenseBackend(
            embeddings=_embeddings(),
            ids=["a", "a", "c"],
            build_id="build-1",
            normalized=True,
        )


def test_file_dense_backend_rejects_empty_id() -> None:
    with pytest.raises(
        DenseBackendCompatibilityError,
        match="empty canonical_id",
    ):
        FileDenseBackend(
            embeddings=_embeddings(),
            ids=["a", "", "c"],
            build_id="build-1",
            normalized=True,
        )


def test_file_dense_backend_does_not_mutate_inputs() -> None:
    embeddings = _embeddings()
    query = _query()

    embeddings_before = embeddings.copy()
    query_before = query.copy()

    backend = FileDenseBackend(
        embeddings=embeddings,
        ids=["a", "b", "c"],
        build_id="build-1",
        normalized=True,
    )

    backend.search(
        DenseSearchRequest(
            query_vector=query,
            top_k=3,
        )
    )

    np.testing.assert_array_equal(embeddings, embeddings_before)
    np.testing.assert_array_equal(query, query_before)


def test_parity_adapter_preserves_legacy_row_shape_and_order() -> None:
    rows = exact_file_dense_search(
        embeddings=_embeddings(),
        ids=["a", "b", "c"],
        query_vector=_query(),
        limit=3,
    )

    assert rows == [
        {
            "rank": 1,
            "canonical_id": "a",
            "dense_index": 0,
            "score": pytest.approx(1.0),
        },
        {
            "rank": 2,
            "canonical_id": "c",
            "dense_index": 2,
            "score": pytest.approx(0.8),
        },
        {
            "rank": 3,
            "canonical_id": "b",
            "dense_index": 1,
            "score": pytest.approx(0.0),
        },
    ]