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
    last_load_error: str | None = None

    current_model_name: str | None = None
    last_loaded_at: str | None = None
    last_reload_at: str | None = None
    last_model_reused: bool = False

    def load(self) -> None:
        settings = get_settings()
        artifacts_root = settings.artifacts_root

        logger.info("Loading API runtime from artifacts_root=%s", artifacts_root)

        try:
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
            self.last_load_error = None
            self.last_loaded_at = _utc_now_iso()

            logger.info(
                "API runtime loaded: build_id=%s corpus_doc_count=%s embedding_model=%s model_reused=%s",
                manifest.build_id,
                len(documents),
                requested_model_name,
                self.last_model_reused,
            )
        except Exception as exc:
            self.last_load_error = str(exc)
            logger.exception("Failed to load API runtime")
            raise

    def reload(self) -> None:
        logger.info("Reloading API runtime")
        self.load()
        self.last_reload_at = _utc_now_iso()

    def is_ready(self) -> bool:
        return (
            self.manifest is not None
            and len(self.documents) > 0
            and self.lexical_artifacts is not None
            and self.dense_artifacts is not None
            and self.embedding_model is not None
        )

    def runtime_snapshot(self) -> dict:
        settings = get_settings()

        return {
            "ready": self.is_ready(),
            "build_id": self.manifest.build_id if self.manifest else None,
            "corpus_doc_count": len(self.documents),
            "embedding_model_name": self.current_model_name,
            "artifacts_root": str(settings.artifacts_root),
            "loaded_components": {
                "manifest": self.manifest is not None,
                "documents": len(self.documents) > 0,
                "lexical_artifacts": self.lexical_artifacts is not None,
                "dense_artifacts": self.dense_artifacts is not None,
                "embedding_model": self.embedding_model is not None,
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