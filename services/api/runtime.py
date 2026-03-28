from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

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
            if settings.search_backend == "db":
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

        # optional snapshot count
        total_docs = db_store.count_documents()

        self.db_store = db_store
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
        logger.info("Reloading API runtime")
        self.load()
        self.last_reload_at = _utc_now_iso()

    def is_ready(self) -> bool:
        if self.backend_mode == "db":
            return self.db_store is not None

        return (
            self.manifest is not None
            and len(self.documents) > 0
            and self.lexical_artifacts is not None
            and self.dense_artifacts is not None
            and self.embedding_model is not None
        )

    def runtime_snapshot(self) -> dict:
        settings = get_settings()

        corpus_doc_count = 0
        if self.backend_mode == "file":
            corpus_doc_count = len(self.documents)
        elif self.db_store is not None:
            try:
                corpus_doc_count = self.db_store.count_documents()
            except Exception:
                corpus_doc_count = 0

        return {
            "ready": self.is_ready(),
            "backend_mode": self.backend_mode,
            "build_id": self.manifest.build_id if self.manifest else None,
            "corpus_doc_count": corpus_doc_count,
            "embedding_model_name": self.current_model_name,
            "artifacts_root": str(settings.artifacts_root),
            "loaded_components": {
                "manifest": self.manifest is not None,
                "documents": len(self.documents) > 0,
                "lexical_artifacts": self.lexical_artifacts is not None,
                "dense_artifacts": self.dense_artifacts is not None,
                "embedding_model": self.embedding_model is not None,
                "db_store": self.db_store is not None,
            },
            "last_load_error": self.last_load_error,
            "last_loaded_at": self.last_loaded_at,
            "last_reload_at": self.last_reload_at,
            "model_reused": self.last_model_reused,
            "current_model_name": self.current_model_name,
        }


_runtime = ApiRuntime()


def get_runtime() -> ApiRuntime:
    return _runtime