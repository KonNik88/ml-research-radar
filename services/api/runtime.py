from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
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


@dataclass
class ApiRuntime:
    manifest: RetrievalBuildManifest | None = None
    documents: list[CanonicalDocument] = field(default_factory=list)
    lexical_artifacts: LexicalArtifacts | None = None
    dense_artifacts: DenseArtifacts | None = None
    embedding_model: SentenceTransformer | None = None
    db_store: PostgresDocumentStore | None = None
    qdrant_dense_backend: QdrantDenseBackend | None = None

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
            "collection=%s profile=%s exact=%s hnsw_ef=%s build_id=%s",
            settings.qdrant_collection_name,
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

    def _qdrant_diagnostics(self, *, expected_corpus_doc_count: int | None) -> dict[str, Any]:
        settings = get_settings()

        diagnostics: dict[str, Any] = {
            "configured": True,
            "ok": False,
            "host": settings.qdrant_host,
            "port": settings.qdrant_port,
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
            diagnostics["error"] = repr(exc)

        return diagnostics

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

    def runtime_snapshot(self, *, include_qdrant: bool = False) -> dict:
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
            )

        return snapshot


_runtime = ApiRuntime()


def get_runtime() -> ApiRuntime:
    return _runtime