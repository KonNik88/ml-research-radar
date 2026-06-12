from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from sentence_transformers import SentenceTransformer

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.retrieval.artifacts import (
    DenseArtifacts,
    LexicalArtifacts,
    RetrievalBuildManifest,
    load_dense_artifacts,
    load_lexical_artifacts,
    read_latest_manifest,
)
from radar_core.retrieval.builders import load_canonical_documents
from radar_core.retrieval.dense_backend import (
    QdrantDenseBackend,
    QdrantSearchProfile,
)
from radar_core.retrieval.qdrant_store import QdrantRetrievalStore
from services.api.db import PostgresConfig, PostgresDocumentStore
from services.api.logging import get_logger
from services.api.settings import get_settings


logger = get_logger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _bounded_message(value: object, *, max_length: int = 500) -> str:
    text = str(value).strip()

    if len(text) <= max_length:
        return text

    return text[: max_length - 3] + "..."

@dataclass
class QdrantOperationalState:
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0

    last_status: str = "never"
    last_request_at: str | None = None
    last_success_at: str | None = None
    last_failure_at: str | None = None

    last_failure_category: str | None = None
    last_failure_stage: str | None = None
    last_failure_message: str | None = None

    last_result_count: int | None = None
    last_timing_ms: dict[str, float] = field(default_factory=dict)

    requested_vector_backend: str | None = None
    effective_vector_backend: str | None = None
    fallback_applied: bool = False

@dataclass
class ApiRuntime:
    manifest: RetrievalBuildManifest | None = None
    documents: list[CanonicalDocument] = field(default_factory=list)
    lexical_artifacts: LexicalArtifacts | None = None
    dense_artifacts: DenseArtifacts | None = None
    embedding_model: SentenceTransformer | None = None
    db_store: PostgresDocumentStore | None = None
    qdrant_dense_backend: QdrantDenseBackend | None = None
    qdrant_operational_state: QdrantOperationalState = field(
        default_factory=QdrantOperationalState,
        init=False,
    )

    _qdrant_state_lock: Any = field(
        default_factory=Lock,
        init=False,
        repr=False,
    )
    _qdrant_diagnostics_cache: dict[str, Any] | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _qdrant_diagnostics_cached_at_monotonic: float | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _qdrant_diagnostics_checked_at: str | None = field(
        default=None,
        init=False,
        repr=False,
    )

    last_load_error: str | None = None

    current_model_name: str | None = None
    last_loaded_at: str | None = None
    last_reload_at: str | None = None
    last_model_reused: bool = False
    backend_mode: str = "file"

    def load(self) -> None:
        settings = get_settings()
        self.backend_mode = settings.search_backend

        logger.info("Loading API runtime with backend=%s", self.backend_mode)

        try:
            if self.backend_mode == "db":
                self._load_db_runtime()
            else:
                self._load_file_runtime()

            self._reset_qdrant_runtime_state()

            self.last_load_error = None
            self.last_loaded_at = _utc_now_iso()

        except Exception as exc:
            self.last_load_error = str(exc)
            logger.exception("Failed to load API runtime")
            raise

    def _load_db_runtime(self) -> None:
        settings = get_settings()

        db_store = PostgresDocumentStore(
            PostgresConfig(
                host=settings.postgres_host,
                port=settings.postgres_port,
                dbname=settings.postgres_dbname,
                user=settings.postgres_user,
                password=settings.postgres_password,
            )
        )

        if not db_store.ping():
            raise RuntimeError("Postgres DB store is not available")

        total_docs = db_store.count_documents()

        self.db_store = db_store
        self.qdrant_dense_backend = None
        self.manifest = None
        self.documents = []
        self.lexical_artifacts = None
        self.dense_artifacts = None
        self.embedding_model = None
        self.current_model_name = None
        self.last_model_reused = False

        logger.info(
            "DB runtime loaded successfully: canonical_documents=%s",
            total_docs,
        )

    def _load_file_runtime(self) -> None:
        settings = get_settings()
        artifacts_root = settings.artifacts_root

        logger.info("Loading file-based API runtime from artifacts_root=%s", artifacts_root)

        manifest = read_latest_manifest(root_dir=artifacts_root)

        documents = load_canonical_documents(manifest.corpus_path)

        lexical_artifacts = load_lexical_artifacts(
            index_path=manifest.lexical_index_path,
            ids_path=manifest.lexical_ids_path,
        )

        dense_artifacts = load_dense_artifacts(
            embeddings_path=manifest.dense_embeddings_path,
            ids_path=manifest.dense_ids_path,
            meta_path=manifest.dense_meta_path,
        )

        requested_model_name = dense_artifacts.meta["model_name"]

        reuse_existing_model = (
            self.embedding_model is not None
            and self.current_model_name == requested_model_name
        )

        if reuse_existing_model:
            embedding_model = self.embedding_model
            self.last_model_reused = True
            logger.info(
                "Reusing already loaded embedding model: %s",
                requested_model_name,
            )
        else:
            logger.info(
                "Loading embedding model from scratch: %s",
                requested_model_name,
            )
            embedding_model = SentenceTransformer(requested_model_name)
            self.last_model_reused = False

        self.manifest = manifest
        self.documents = documents
        self.lexical_artifacts = lexical_artifacts
        self.dense_artifacts = dense_artifacts
        self.embedding_model = embedding_model
        self.qdrant_dense_backend = None
        self.current_model_name = requested_model_name
        self.db_store = None

        logger.info(
            "File runtime loaded: build_id=%s corpus_doc_count=%s embedding_model=%s model_reused=%s",
            manifest.build_id,
            len(documents),
            requested_model_name,
            self.last_model_reused,
        )

    def reload(self) -> None:
        logger.info("Reloading API runtime for backend=%s", self.backend_mode)
        self.load()
        self.last_reload_at = _utc_now_iso()

    def _reset_qdrant_runtime_state(self) -> None:
        with self._qdrant_state_lock:
            self.qdrant_operational_state = QdrantOperationalState()
            self._qdrant_diagnostics_cache = None
            self._qdrant_diagnostics_cached_at_monotonic = None
            self._qdrant_diagnostics_checked_at = None

    def record_qdrant_request_started(self) -> None:
        with self._qdrant_state_lock:
            state = self.qdrant_operational_state
            state.request_count += 1
            state.last_request_at = _utc_now_iso()
            state.requested_vector_backend = "qdrant"
            state.effective_vector_backend = None
            state.fallback_applied = False

    def record_qdrant_success(
        self,
        *,
        result_count: int,
        timing_ms: dict[str, float],
    ) -> None:
        with self._qdrant_state_lock:
            state = self.qdrant_operational_state
            state.success_count += 1
            state.last_status = "ok"
            state.last_success_at = _utc_now_iso()
            state.last_result_count = int(result_count)
            state.last_timing_ms = {
                str(name): float(value)
                for name, value in timing_ms.items()
            }
            state.requested_vector_backend = "qdrant"
            state.effective_vector_backend = "qdrant"
            state.fallback_applied = False

    def record_qdrant_failure(
        self,
        *,
        category: str,
        stage: str,
        message: str,
        timing_ms: dict[str, float],
    ) -> None:
        with self._qdrant_state_lock:
            state = self.qdrant_operational_state
            state.failure_count += 1
            state.last_status = "error"
            state.last_failure_at = _utc_now_iso()
            state.last_failure_category = str(category)
            state.last_failure_stage = str(stage)
            state.last_failure_message = _bounded_message(message)
            state.last_result_count = None
            state.last_timing_ms = {
                str(name): float(value)
                for name, value in timing_ms.items()
            }
            state.requested_vector_backend = "qdrant"
            state.effective_vector_backend = None
            state.fallback_applied = False

    def get_qdrant_dense_backend(self) -> QdrantDenseBackend:
        """Return the cached experimental Qdrant dense backend.

        The backend is created lazily so Qdrant remains optional for normal
        file-runtime readiness. Runtime reload invalidates the cached backend.
        """

        if self.backend_mode != "file":
            raise RuntimeError(
                "Experimental Qdrant search requires file backend runtime"
            )

        if self.qdrant_dense_backend is not None:
            return self.qdrant_dense_backend

        if self.manifest is None:
            raise RuntimeError("Retrieval manifest is not loaded")

        if self.dense_artifacts is None:
            raise RuntimeError("Dense retrieval artifacts are not loaded")

        embeddings = self.dense_artifacts.embeddings
        dense_ids = self.dense_artifacts.ids
        dense_meta = self.dense_artifacts.meta

        if embeddings.ndim != 2:
            raise RuntimeError(
                "Dense embeddings must be two-dimensional: "
                f"shape={embeddings.shape}"
            )

        if dense_meta.get("normalized") is not True:
            raise RuntimeError(
                "Experimental Qdrant search requires normalized dense artifacts"
            )

        settings = get_settings()

        store = QdrantRetrievalStore(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            grpc_port=settings.qdrant_grpc_port,
            prefer_grpc=settings.qdrant_prefer_grpc,
            collection_name=settings.qdrant_collection_name,
            timeout_sec=settings.qdrant_timeout_sec,
            check_compatibility=settings.qdrant_check_compatibility,
        )

        profile = QdrantSearchProfile(
            name=settings.qdrant_search_profile_name,
            exact=settings.qdrant_search_exact,
            hnsw_ef=settings.qdrant_search_hnsw_ef,
        )

        backend = QdrantDenseBackend(
            store=store,
            profile=profile,
            expected_build_id=self.manifest.build_id,
            expected_corpus_count=self.manifest.corpus_doc_count,
            expected_vector_size=int(embeddings.shape[1]),
            expected_distance="Cosine",
            dense_ids=dense_ids,
            require_point_id_equals_dense_index=True,
        )

        self.qdrant_dense_backend = backend

        logger.info(
            "Created experimental Qdrant dense backend: "
            "collection=%s transport=%s grpc_port=%s "
            "profile=%s exact=%s hnsw_ef=%s build_id=%s",
            settings.qdrant_collection_name,
            (
                "grpc"
                if settings.qdrant_prefer_grpc
                else "rest"
            ),
            settings.qdrant_grpc_port,
            profile.name,
            profile.exact,
            profile.hnsw_ef,
            self.manifest.build_id,
        )

        return backend

    def _db_connected(self) -> bool:
        if self.db_store is None:
            return False
        try:
            return self.db_store.ping()
        except Exception:
            logger.exception("Failed to ping DB store during runtime snapshot")
            return False

    def _loaded_components(self) -> dict[str, bool]:
        return {
            "manifest": self.manifest is not None,
            "documents": len(self.documents) > 0,
            "lexical_artifacts": self.lexical_artifacts is not None,
            "dense_artifacts": self.dense_artifacts is not None,
            "embedding_model": self.embedding_model is not None,
            "db_store": self.db_store is not None,
        }

    def _probe_qdrant_diagnostics(
            self,
            *,
            expected_corpus_doc_count: int | None,
    ) -> dict[str, Any]:
        settings = get_settings()

        diagnostics: dict[str, Any] = {
            "configured": True,
            "ok": False,
                        "host": settings.qdrant_host,
            "port": settings.qdrant_port,
            "grpc_port": settings.qdrant_grpc_port,
            "prefer_grpc": settings.qdrant_prefer_grpc,
            "transport": (
                "grpc"
                if settings.qdrant_prefer_grpc
                else "rest"
            ),
            "collection_name": settings.qdrant_collection_name,
            "timeout_sec": settings.qdrant_timeout_sec,
            "check_compatibility": settings.qdrant_check_compatibility,
            "collection_exists": False,
            "points_count": None,
            "expected_corpus_doc_count": expected_corpus_doc_count,
            "points_match_corpus": None,
            "vector_size": None,
            "distance": None,
            "status": None,
            "optimizer_status": None,
            "error": None,
        }

        try:
            store = QdrantRetrievalStore(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                grpc_port=settings.qdrant_grpc_port,
                prefer_grpc=settings.qdrant_prefer_grpc,
                collection_name=settings.qdrant_collection_name,
                timeout_sec=settings.qdrant_timeout_sec,
                check_compatibility=settings.qdrant_check_compatibility,
            )

            collection_exists = store.collection_exists()
            diagnostics["collection_exists"] = collection_exists

            if not collection_exists:
                diagnostics["points_match_corpus"] = False
                return diagnostics

            points_count = store.count_points()
            info = store.get_collection_info()

            diagnostics.update(
                {
                    "points_count": points_count,
                    "points_match_corpus": (
                        points_count == expected_corpus_doc_count
                        if expected_corpus_doc_count is not None
                        else None
                    ),
                    "vector_size": info.get("vector_size"),
                    "distance": info.get("distance"),
                    "status": info.get("status"),
                    "optimizer_status": info.get("optimizer_status"),
                }
            )
            diagnostics["ok"] = bool(
                diagnostics["collection_exists"]
                and points_count > 0
                and diagnostics["points_match_corpus"] is not False
            )

        except Exception as exc:  # noqa: BLE001 - optional diagnostics must not break /runtime
            logger.warning("Qdrant runtime diagnostics failed: %s", exc)
            diagnostics["error"] = _bounded_message(
                f"{type(exc).__name__}: {exc}"
            )

        return diagnostics

    def _qdrant_diagnostics(
        self,
        *,
        expected_corpus_doc_count: int | None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        settings = get_settings()

        ttl_sec = float(settings.qdrant_runtime_diagnostics_ttl_sec)
        now_monotonic = time.monotonic()

        with self._qdrant_state_lock:
            cached_payload = (
                dict(self._qdrant_diagnostics_cache)
                if self._qdrant_diagnostics_cache is not None
                else None
            )
            cached_at_monotonic = self._qdrant_diagnostics_cached_at_monotonic
            checked_at = self._qdrant_diagnostics_checked_at

        cache_age_sec: float | None = None
        if cached_at_monotonic is not None:
            cache_age_sec = max(
                0.0,
                now_monotonic - cached_at_monotonic,
            )

        use_cache = bool(
            not force_refresh
            and cached_payload is not None
            and cache_age_sec is not None
            and cache_age_sec <= ttl_sec
        )

        if use_cache:
            diagnostics = cached_payload
            probe_cached = True
        else:
            diagnostics = self._probe_qdrant_diagnostics(
                expected_corpus_doc_count=expected_corpus_doc_count,
            )
            checked_at = _utc_now_iso()
            cache_age_sec = 0.0
            probe_cached = False

            with self._qdrant_state_lock:
                self._qdrant_diagnostics_cache = dict(diagnostics)
                self._qdrant_diagnostics_cached_at_monotonic = now_monotonic
                self._qdrant_diagnostics_checked_at = checked_at

        with self._qdrant_state_lock:
            operational_state = asdict(self.qdrant_operational_state)

        backend_created = self.qdrant_dense_backend is not None
        compatibility_checked = False
        compatibility_ok: bool | None = None

        if self.qdrant_dense_backend is not None:
            backend_info = self.qdrant_dense_backend.info()
            backend_diagnostics = backend_info.diagnostics
            compatibility_checked = bool(
                backend_diagnostics.get("compatibility_checked")
            )
            compatibility_ok = (
                bool(backend_info.ready)
                if compatibility_checked
                else None
            )

        build_id = self.manifest.build_id if self.manifest else None

        return {
            **diagnostics,
            "probe_cached": probe_cached,
            "probe_checked_at": checked_at,
            "probe_cache_age_sec": (
                round(cache_age_sec, 3)
                if cache_age_sec is not None
                else None
            ),
            "probe_ttl_sec": ttl_sec,
            "profile_name": settings.qdrant_search_profile_name,
            "exact": settings.qdrant_search_exact,
            "hnsw_ef": settings.qdrant_search_hnsw_ef,
            "build_id": build_id,
            "backend_created": backend_created,
            "compatibility_checked": compatibility_checked,
            "compatibility_ok": compatibility_ok,
            **operational_state,
        }

    def is_ready(self) -> bool:
        if self.backend_mode == "db":
            return self._db_connected()

        return (
            self.manifest is not None
            and len(self.documents) > 0
            and self.lexical_artifacts is not None
            and self.dense_artifacts is not None
            and self.embedding_model is not None
        )

    def runtime_snapshot(
            self,
            *,
            include_qdrant: bool = False,
            refresh_qdrant: bool = False,
    ) -> dict:
        settings = get_settings()
        loaded_components = self._loaded_components()

        db_connected = self._db_connected()
        if self.backend_mode == "db":
            build_id = "db-runtime"
            embedding_model_name = None
            current_model_name = None
            model_reused = False
            if db_connected and self.db_store is not None:
                try:
                    corpus_doc_count = self.db_store.count_documents()
                except Exception:
                    corpus_doc_count = 0
            else:
                corpus_doc_count = 0
        else:
            build_id = self.manifest.build_id if self.manifest else None
            embedding_model_name = self.current_model_name
            current_model_name = self.current_model_name
            model_reused = self.last_model_reused
            corpus_doc_count = len(self.documents)

        snapshot = {
            "ready": self.is_ready(),
            "backend_mode": self.backend_mode,
            "build_id": build_id,
            "corpus_doc_count": corpus_doc_count,
            "embedding_model_name": embedding_model_name,
            "artifacts_root": str(settings.artifacts_root),
            "loaded_components": loaded_components,
            "db_connected": db_connected,
            "last_load_error": self.last_load_error,
            "last_loaded_at": self.last_loaded_at,
            "last_reload_at": self.last_reload_at,
            "model_reused": model_reused,
            "current_model_name": current_model_name,
        }

        if include_qdrant:
            snapshot["qdrant"] = self._qdrant_diagnostics(
                expected_corpus_doc_count=corpus_doc_count,
                force_refresh=refresh_qdrant,
            )

        return snapshot


_runtime = ApiRuntime()


def get_runtime() -> ApiRuntime:
    return _runtime