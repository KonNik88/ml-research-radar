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

from radar_core.retrieval.qdrant_store import QdrantSearchResult


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


class QdrantStore(Protocol):
    """Read-only Qdrant store boundary required by QdrantDenseBackend."""

    collection_name: str

    def collection_exists(self) -> bool:
        ...

    def count_points(self, *, exact: bool = True) -> int:
        ...

    def get_collection_info(self) -> dict[str, Any]:
        ...

    def search_vector(
        self,
        vector: Sequence[float],
        *,
        top_k: int = 20,
        with_payload: bool = True,
        with_vectors: bool = False,
        exact: bool = False,
        hnsw_ef: int | None = None,
    ) -> list[QdrantSearchResult]:
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


@dataclass(frozen=True)
class QdrantSearchProfile:
    """Explicit Qdrant vector-search profile."""

    name: str
    exact: bool = False
    hnsw_ef: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise DenseBackendRequestError(
                "Qdrant search profile name must be non-empty"
            )

        if not isinstance(self.exact, bool):
            raise DenseBackendRequestError(
                f"profile exact must be a boolean, got {self.exact!r}"
            )

        if self.hnsw_ef is not None:
            if (
                not isinstance(self.hnsw_ef, int)
                or isinstance(self.hnsw_ef, bool)
                or self.hnsw_ef <= 0
            ):
                raise DenseBackendRequestError(
                    "profile hnsw_ef must be a positive integer or None, "
                    f"got {self.hnsw_ef!r}"
                )

        if self.exact and self.hnsw_ef is not None:
            raise DenseBackendRequestError(
                "exact Qdrant profile must not define hnsw_ef"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "exact": self.exact,
            "hnsw_ef": self.hnsw_ef,
        }


def _normalize_enum_token(value: Any) -> str:
    if value is None:
        return ""
    return str(value).split(".")[-1].strip().lower()


def _point_id_as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _validate_dense_ids(
    dense_ids: Sequence[str] | None,
    *,
    expected_corpus_count: int,
) -> tuple[str, ...] | None:
    if dense_ids is None:
        return None

    if len(dense_ids) != expected_corpus_count:
        raise DenseBackendCompatibilityError(
            f"dense ids count {len(dense_ids)} "
            f"!= expected corpus count {expected_corpus_count}"
        )

    normalized: list[str] = []
    seen: set[str] = set()

    for dense_index, raw_id in enumerate(dense_ids):
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

        if canonical_id in seen:
            raise DenseBackendCompatibilityError(
                f"duplicate dense canonical_id: {canonical_id}"
            )

        seen.add(canonical_id)
        normalized.append(canonical_id)

    return tuple(normalized)


class QdrantDenseBackend:
    """Dense candidate retrieval over an existing Qdrant collection.

    Collection-level compatibility is checked once per backend lifecycle and
    cached. Payload/build/mapping invariants are checked for every returned
    result.

    The backend is read-only and never creates collections, uploads vectors,
    loads embedding models, hydrates documents, ranks results, or falls back to
    another backend.
    """

    def __init__(
        self,
        *,
        store: QdrantStore,
        profile: QdrantSearchProfile,
        expected_build_id: str,
        expected_corpus_count: int,
        expected_vector_size: int,
        expected_distance: str = "Cosine",
        dense_ids: Sequence[str] | None = None,
        require_point_id_equals_dense_index: bool = True,
    ) -> None:
        if not isinstance(profile, QdrantSearchProfile):
            raise DenseBackendRequestError(
                "profile must be a QdrantSearchProfile instance"
            )

        if not isinstance(expected_build_id, str) or not expected_build_id.strip():
            raise DenseBackendCompatibilityError(
                "expected_build_id must be non-empty"
            )

        expected_corpus_count = _positive_int(
            expected_corpus_count,
            name="expected_corpus_count",
        )
        expected_vector_size = _positive_int(
            expected_vector_size,
            name="expected_vector_size",
        )

        if (
            not isinstance(expected_distance, str)
            or not expected_distance.strip()
        ):
            raise DenseBackendCompatibilityError(
                "expected_distance must be non-empty"
            )

        if not isinstance(
            require_point_id_equals_dense_index,
            bool,
        ):
            raise DenseBackendRequestError(
                "require_point_id_equals_dense_index must be boolean"
            )

        collection_name = str(
            getattr(store, "collection_name", "") or ""
        ).strip()
        if not collection_name:
            raise DenseBackendCompatibilityError(
                "Qdrant store collection_name must be non-empty"
            )

        self._store = store
        self._profile = profile
        self._expected_build_id = expected_build_id
        self._expected_corpus_count = expected_corpus_count
        self._expected_vector_size = expected_vector_size
        self._expected_distance = expected_distance
        self._dense_ids = _validate_dense_ids(
            dense_ids,
            expected_corpus_count=expected_corpus_count,
        )
        self._require_point_id_equals_dense_index = (
            require_point_id_equals_dense_index
        )

        self._compatibility_checked = False
        self._compatibility_diagnostics: dict[str, Any] = {}

    def info(self) -> DenseSearchBackendInfo:
        diagnostics = {
            "collection_name": self._store.collection_name,
            "profile": self._profile.to_dict(),
            "expected_corpus_count": self._expected_corpus_count,
            "expected_vector_size": self._expected_vector_size,
            "expected_distance": self._expected_distance,
            "expected_build_id": self._expected_build_id,
            "strict_dense_ids_mapping": self._dense_ids is not None,
            "require_point_id_equals_dense_index": (
                self._require_point_id_equals_dense_index
            ),
            "compatibility_checked": self._compatibility_checked,
            **self._compatibility_diagnostics,
        }

        return DenseSearchBackendInfo(
            backend_name="qdrant",
            implementation=type(self).__name__,
            build_id=self._expected_build_id,
            ready=self._compatibility_checked,
            diagnostics=diagnostics,
        )

    def _ensure_compatible(self) -> None:
        if self._compatibility_checked:
            return

        try:
            collection_exists = self._store.collection_exists()
        except Exception as exc:
            raise DenseBackendUnavailableError(
                "Failed to check Qdrant collection availability"
            ) from exc

        if not collection_exists:
            raise DenseBackendUnavailableError(
                "Qdrant collection does not exist: "
                f"{self._store.collection_name}"
            )

        try:
            points_count = self._store.count_points()
            collection_info = self._store.get_collection_info()
        except Exception as exc:
            raise DenseBackendUnavailableError(
                "Failed to inspect Qdrant collection: "
                f"{self._store.collection_name}"
            ) from exc

        if points_count != self._expected_corpus_count:
            raise DenseBackendCompatibilityError(
                f"Qdrant points count {points_count} "
                f"!= expected corpus count {self._expected_corpus_count}"
            )

        vector_size = collection_info.get("vector_size")
        if vector_size != self._expected_vector_size:
            raise DenseBackendCompatibilityError(
                f"Qdrant vector size {vector_size} "
                f"!= expected vector size {self._expected_vector_size}"
            )

        actual_distance = collection_info.get("distance")
        if _normalize_enum_token(actual_distance) != _normalize_enum_token(
            self._expected_distance
        ):
            raise DenseBackendCompatibilityError(
                f"Qdrant distance {actual_distance!r} "
                f"!= expected distance {self._expected_distance!r}"
            )

        self._compatibility_diagnostics = {
            "points_count": points_count,
            "vector_size": vector_size,
            "distance": actual_distance,
            "status": collection_info.get("status"),
            "optimizer_status": collection_info.get("optimizer_status"),
        }
        self._compatibility_checked = True

    def search(
        self,
        request: DenseSearchRequest,
    ) -> DenseSearchBackendResult:
        if not isinstance(request, DenseSearchRequest):
            raise DenseBackendRequestError(
                "request must be a DenseSearchRequest instance"
            )

        top_k = _positive_int(request.top_k, name="top_k")

        try:
            query = np.asarray(request.query_vector, dtype=np.float32)
        except (TypeError, ValueError) as exc:
            raise DenseBackendRequestError(
                "query_vector cannot be converted to float32"
            ) from exc

        if query.ndim != 1:
            raise DenseBackendRequestError(
                f"query_vector must be one-dimensional, got shape={query.shape}"
            )

        if query.shape[0] != self._expected_vector_size:
            raise DenseBackendRequestError(
                f"query dimension {query.shape[0]} "
                f"!= expected vector size {self._expected_vector_size}"
            )

        if not np.isfinite(query).all():
            raise DenseBackendRequestError(
                "query_vector contains non-finite values"
            )

        self._ensure_compatible()

        started = time.perf_counter()
        try:
            raw_results = self._store.search_vector(
                vector=query.tolist(),
                top_k=top_k,
                with_payload=True,
                with_vectors=False,
                exact=self._profile.exact,
                hnsw_ef=self._profile.hnsw_ef,
            )
        except Exception as exc:
            raise DenseBackendUnavailableError(
                "Qdrant vector search failed: "
                f"collection={self._store.collection_name}, "
                f"profile={self._profile.name}"
            ) from exc

        elapsed_ms = (time.perf_counter() - started) * 1000.0

        if len(raw_results) > top_k:
            raise DenseBackendResultError(
                f"Qdrant returned {len(raw_results)} results "
                f"for top_k={top_k}"
            )

        candidates: list[DenseSearchCandidate] = []
        seen_ids: set[str] = set()

        for rank, result in enumerate(raw_results, start=1):
            if not isinstance(result, QdrantSearchResult):
                raise DenseBackendResultError(
                    "Qdrant store returned an unexpected result type: "
                    f"{type(result).__name__}"
                )

            canonical_id = (
                result.canonical_id.strip()
                if isinstance(result.canonical_id, str)
                else ""
            )
            if not canonical_id:
                raise DenseBackendResultError(
                    f"missing canonical_id at Qdrant rank={rank}"
                )

            if canonical_id in seen_ids:
                raise DenseBackendResultError(
                    "duplicate canonical_id in Qdrant results: "
                    f"{canonical_id}"
                )
            seen_ids.add(canonical_id)

            if isinstance(result.score, bool):
                raise DenseBackendResultError(
                    f"invalid score at Qdrant rank={rank}"
                )

            try:
                score = float(result.score)
            except (TypeError, ValueError) as exc:
                raise DenseBackendResultError(
                    f"invalid score at Qdrant rank={rank}"
                ) from exc

            if not math.isfinite(score):
                raise DenseBackendResultError(
                    f"non-finite score at Qdrant rank={rank}"
                )

            payload = result.payload
            if not isinstance(payload, Mapping):
                raise DenseBackendResultError(
                    f"missing or invalid payload at Qdrant rank={rank}"
                )

            payload_canonical_id = payload.get("canonical_id")
            if (
                not isinstance(payload_canonical_id, str)
                or payload_canonical_id.strip() != canonical_id
            ):
                raise DenseBackendResultError(
                    "payload canonical_id mismatch at Qdrant rank="
                    f"{rank}"
                )

            payload_dense_index = payload.get("dense_index")
            if (
                not isinstance(payload_dense_index, int)
                or isinstance(payload_dense_index, bool)
            ):
                raise DenseBackendResultError(
                    "missing or invalid payload dense_index at Qdrant rank="
                    f"{rank}"
                )

            if not 0 <= payload_dense_index < self._expected_corpus_count:
                raise DenseBackendResultError(
                    "payload dense_index out of range at Qdrant rank="
                    f"{rank}: {payload_dense_index}"
                )

            if result.dense_index != payload_dense_index:
                raise DenseBackendResultError(
                    "normalized dense_index does not match payload at "
                    f"Qdrant rank={rank}"
                )

            payload_build_id = payload.get("build_id")
            if str(payload_build_id or "") != self._expected_build_id:
                raise DenseBackendResultError(
                    "payload build_id mismatch at Qdrant rank="
                    f"{rank}: {payload_build_id!r}"
                )

            if self._dense_ids is not None:
                expected_canonical_id = self._dense_ids[payload_dense_index]
                if expected_canonical_id != canonical_id:
                    raise DenseBackendResultError(
                        "dense_ids mapping mismatch at Qdrant rank="
                        f"{rank}: expected={expected_canonical_id}, "
                        f"actual={canonical_id}"
                    )

            if self._require_point_id_equals_dense_index:
                normalized_point_id = _point_id_as_int(result.point_id)
                if normalized_point_id != payload_dense_index:
                    raise DenseBackendResultError(
                        "point_id does not match dense_index at Qdrant rank="
                        f"{rank}: point_id={result.point_id!r}, "
                        f"dense_index={payload_dense_index}"
                    )

            candidates.append(
                DenseSearchCandidate(
                    canonical_id=canonical_id,
                    score=score,
                    rank=rank,
                    dense_index=payload_dense_index,
                    backend_point_id=result.point_id,
                    backend_metadata={
                        "collection_name": self._store.collection_name,
                        "profile": self._profile.to_dict(),
                        "build_id": payload_build_id,
                        "payload": dict(payload),
                    },
                )
            )

        return DenseSearchBackendResult(
            candidates=tuple(candidates),
            backend=self.info(),
            timing_ms={
                "backend_search_ms": elapsed_ms,
            },
        )