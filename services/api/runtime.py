from __future__ import annotations

from dataclasses import dataclass, field

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


@dataclass
class ApiRuntime:
    manifest: RetrievalBuildManifest | None = None
    documents: list[CanonicalDocument] = field(default_factory=list)
    lexical_artifacts: LexicalArtifacts | None = None
    dense_artifacts: DenseArtifacts | None = None
    embedding_model: SentenceTransformer | None = None
    last_load_error: str | None = None

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

            model_name = dense_artifacts.meta["model_name"]
            embedding_model = SentenceTransformer(model_name)

            self.manifest = manifest
            self.documents = documents
            self.lexical_artifacts = lexical_artifacts
            self.dense_artifacts = dense_artifacts
            self.embedding_model = embedding_model
            self.last_load_error = None

            logger.info(
                "API runtime loaded: build_id=%s corpus_doc_count=%s embedding_model=%s",
                manifest.build_id,
                len(documents),
                model_name,
            )
        except Exception as exc:
            self.last_load_error = str(exc)
            logger.exception("Failed to load API runtime")
            raise

    def reload(self) -> None:
        logger.info("Reloading API runtime")
        self.load()

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
            "embedding_model_name": (
                self.manifest.embedding_model_name if self.manifest else None
            ),
            "artifacts_root": str(settings.artifacts_root),
            "loaded_components": {
                "manifest": self.manifest is not None,
                "documents": len(self.documents) > 0,
                "lexical_artifacts": self.lexical_artifacts is not None,
                "dense_artifacts": self.dense_artifacts is not None,
                "embedding_model": self.embedding_model is not None,
            },
            "last_load_error": self.last_load_error,
        }


_runtime = ApiRuntime()


def get_runtime() -> ApiRuntime:
    return _runtime