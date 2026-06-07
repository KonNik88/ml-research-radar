"""Backend-neutral contracts for dense candidate retrieval.

This module owns the runtime semantics of dense candidate retrieval.

Important boundaries:

- callers prepare and normalize the query vector;
- backends return candidate IDs and scores only;
- query encoding, document hydration, hybrid merge, ranking, pagination,
  fallback policy, and API serialization remain outside this module.

The authoritative exact file-dense kernel intentionally preserves the current
production semantics:

    scores = stored_embeddings @ normalized_float32_query
    order = np.argsort(scores)[::-1]

Stored embeddings are used as persisted and are not silently normalized here.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

import numpy as np


class DenseBackendError(RuntimeError):
    """Base error for dense backend failures."""


class DenseBackendRequestError(DenseBackendError, ValueError):
    """The caller supplied an invalid dense-search request."""


class DenseBackendUnavailableError(DenseBackendError):
    """The selected dense backend is not available."""


class DenseBackendCompatibilityError(DenseBackendError):
    """Backend artifacts or serving state are incompatible."""


class DenseBackendResultError(DenseBackendError):
    """The backend returned an invalid candidate result."""


@dataclass(frozen=True)
class DenseSearchRequest:
    """Prepared dense candidate-retrieval request.

    ``query_vector`` must already be encoded, normalized, and compatible with
    the active retrieval build. Backends do not load or invoke embedding models.
    """

    query_vector: np.ndarray
    top_k: int


@dataclass(frozen=True)
class DenseSearchCandidate:
    """Backend-neutral dense retrieval candidate."""

    canonical_id: str
    score: float
    rank: int

    dense_index: int | None = None
    backend_point_id: int | str | None = None
    backend_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DenseSearchBackendInfo:
    """Stable identity and diagnostics for one backend instance."""

    backend_name: str
    implementation: str
    build_id: str | None
    ready: bool
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DenseSearchBackendResult:
    """Candidate result returned by a dense backend."""

    candidates: tuple[DenseSearchCandidate, ...]
    backend: DenseSearchBackendInfo
    timing_ms: Mapping[str, float] = field(default_factory=dict)


class DenseSearchBackend(Protocol):
    """Minimal contract shared by dense candidate-retrieval backends."""

    def search(self, request: DenseSearchRequest) -> DenseSearchBackendResult:
        ...

    def info(self) -> DenseSearchBackendInfo:
        ...


def _positive_int(value: int, *, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise DenseBackendRequestError(
            f"{name} must be a positive integer, got {value!r}"
        )
    return value


def exact_file_dense_candidates(
    *,
    embeddings: np.ndarray,
    ids: Sequence[str],
    query_vector: np.ndarray,
    top_k: int,
) -> tuple[DenseSearchCandidate, ...]:
    """Run exact file-dense candidate retrieval.

    The query is expected to be prepared and normalized by the caller. The
    stored embedding matrix is used as-is.

    Full ``np.argsort`` is deliberate because this is the exact reference
    implementation, not a scale-optimized ANN implementation.

    Artifact-level validation such as global ID uniqueness is performed once by
    :class:`FileDenseBackend`. This low-level kernel still validates all
    request-dependent conditions and every returned candidate.
    """

    top_k = _positive_int(top_k, name="top_k")

    matrix = np.asarray(embeddings)
    query = np.asarray(query_vector, dtype=np.float32)

    if matrix.ndim != 2:
        raise DenseBackendRequestError(
            f"embeddings must be two-dimensional, got shape={matrix.shape}"
        )

    if query.ndim != 1:
        raise DenseBackendRequestError(
            f"query_vector must be one-dimensional, got shape={query.shape}"
        )

    if matrix.shape[0] != len(ids):
        raise DenseBackendCompatibilityError(
            f"dense ids count {len(ids)} != embeddings rows {matrix.shape[0]}"
        )

    if matrix.shape[1] != query.shape[0]:
        raise DenseBackendRequestError(
            f"query dimension {query.shape[0]} "
            f"!= embedding dimension {matrix.shape[1]}"
        )

    if not np.isfinite(query).all():
        raise DenseBackendRequestError(
            "query_vector contains non-finite values"
        )

    scores = np.asarray(matrix @ query, dtype=np.float32)

    if scores.ndim != 1 or scores.shape[0] != matrix.shape[0]:
        raise DenseBackendResultError(
            "file dense kernel produced an invalid score vector: "
            f"shape={scores.shape}"
        )

    if not np.isfinite(scores).all():
        raise DenseBackendResultError(
            "file dense kernel produced non-finite scores"
        )

    order = np.argsort(scores)[::-1]
    effective_limit = min(top_k, int(order.shape[0]))

    candidates: list[DenseSearchCandidate] = []
    seen_ids: set[str] = set()

    for rank, raw_index in enumerate(order[:effective_limit], start=1):
        dense_index = int(raw_index)
        canonical_id = str(ids[dense_index]).strip()

        if not canonical_id:
            raise DenseBackendResultError(
                f"empty canonical_id at dense_index={dense_index}"
            )

        if canonical_id in seen_ids:
            raise DenseBackendResultError(
                f"duplicate canonical_id in dense results: {canonical_id}"
            )
        seen_ids.add(canonical_id)

        score = float(scores[dense_index])
        if not math.isfinite(score):
            raise DenseBackendResultError(
                f"non-finite score at dense_index={dense_index}"
            )

        candidates.append(
            DenseSearchCandidate(
                canonical_id=canonical_id,
                score=score,
                rank=rank,
                dense_index=dense_index,
            )
        )

    return tuple(candidates)


class FileDenseBackend:
    """Exact dense retrieval over persisted file artifacts.

    The backend validates build-level invariants once during construction.
    Query-dependent validation is performed for every search.
    """

    def __init__(
        self,
        *,
        embeddings: np.ndarray,
        ids: Sequence[str],
        build_id: str | None,
        normalized: bool,
    ) -> None:
        matrix = np.asarray(embeddings)

        if matrix.ndim != 2:
            raise DenseBackendCompatibilityError(
                f"embeddings must be two-dimensional, got shape={matrix.shape}"
            )

        if matrix.shape[0] <= 0:
            raise DenseBackendCompatibilityError(
                "embeddings matrix must contain at least one row"
            )

        if matrix.shape[1] <= 0:
            raise DenseBackendCompatibilityError(
                "embedding dimension must be positive"
            )

        if matrix.shape[0] != len(ids):
            raise DenseBackendCompatibilityError(
                f"dense ids count {len(ids)} "
                f"!= embeddings rows {matrix.shape[0]}"
            )

        if normalized is not True:
            raise DenseBackendCompatibilityError(
                "FileDenseBackend requires normalized=true dense artifacts"
            )

        normalized_ids: list[str] = []
        seen_ids: set[str] = set()

        for dense_index, raw_id in enumerate(ids):
            if not isinstance(raw_id, str):
                raise DenseBackendCompatibilityError(
                    "dense canonical IDs must be strings: "
                    f"index={dense_index}, value={raw_id!r}"
                )

            canonical_id = raw_id.strip()
            if not canonical_id:
                raise DenseBackendCompatibilityError(
                    f"empty canonical_id at dense_index={dense_index}"
                )

            if canonical_id != raw_id:
                raise DenseBackendCompatibilityError(
                    "dense canonical IDs must not contain surrounding whitespace: "
                    f"index={dense_index}"
                )

            if canonical_id in seen_ids:
                raise DenseBackendCompatibilityError(
                    f"duplicate dense canonical_id: {canonical_id}"
                )

            seen_ids.add(canonical_id)
            normalized_ids.append(canonical_id)

        if build_id is not None and not str(build_id).strip():
            raise DenseBackendCompatibilityError(
                "build_id must be non-empty when provided"
            )

        self._embeddings = matrix
        self._ids = tuple(normalized_ids)
        self._build_id = str(build_id) if build_id is not None else None

        self._info = DenseSearchBackendInfo(
            backend_name="file",
            implementation=type(self).__name__,
            build_id=self._build_id,
            ready=True,
            diagnostics={
                "rows_count": int(matrix.shape[0]),
                "vector_size": int(matrix.shape[1]),
                "normalized": True,
                "ordering": "np.argsort(scores)[::-1]",
                "score_function": "stored_embeddings @ query_vector",
            },
        )

    def info(self) -> DenseSearchBackendInfo:
        return self._info

    def search(self, request: DenseSearchRequest) -> DenseSearchBackendResult:
        if not isinstance(request, DenseSearchRequest):
            raise DenseBackendRequestError(
                "request must be a DenseSearchRequest instance"
            )

        started = time.perf_counter()
        candidates = exact_file_dense_candidates(
            embeddings=self._embeddings,
            ids=self._ids,
            query_vector=request.query_vector,
            top_k=request.top_k,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        return DenseSearchBackendResult(
            candidates=candidates,
            backend=self._info,
            timing_ms={
                "backend_search_ms": elapsed_ms,
            },
        )