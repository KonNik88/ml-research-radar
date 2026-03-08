from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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


@dataclass
class ApiRuntime:
    artifacts_root: Path = Path("artifacts/retrieval")
    manifest: RetrievalBuildManifest | None = None
    documents: list[CanonicalDocument] = field(default_factory=list)
    lexical_artifacts: LexicalArtifacts | None = None
    dense_artifacts: DenseArtifacts | None = None
    embedding_model: SentenceTransformer | None = None

    def load(self) -> None:
        self.manifest = read_latest_manifest(root_dir=self.artifacts_root)

        self.documents = load_canonical_documents(self.manifest.corpus_path)

        self.lexical_artifacts = load_lexical_artifacts(
            index_path=self.manifest.lexical_index_path,
            ids_path=self.manifest.lexical_ids_path,
        )

        self.dense_artifacts = load_dense_artifacts(
            embeddings_path=self.manifest.dense_embeddings_path,
            ids_path=self.manifest.dense_ids_path,
            meta_path=self.manifest.dense_meta_path,
        )

        model_name = self.dense_artifacts.meta["model_name"]
        self.embedding_model = SentenceTransformer(model_name)

    def reload(self) -> None:
        self.load()

    def is_ready(self) -> bool:
        return (
            self.manifest is not None
            and len(self.documents) > 0
            and self.lexical_artifacts is not None
            and self.dense_artifacts is not None
            and self.embedding_model is not None
        )


_runtime = ApiRuntime()


def get_runtime() -> ApiRuntime:
    return _runtime