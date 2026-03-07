from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from sentence_transformers import SentenceTransformer

from radar_core.contracts.canonical_document import CanonicalDocument


@dataclass
class DenseSearchResult:
    canonical_id: str
    score: float
    title: str
    year: int | None
    doi: str | None
    source_count: int
    document: CanonicalDocument


class DenseRetriever:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model: SentenceTransformer | None = None
        self.documents: list[CanonicalDocument] = []
        self.embeddings: np.ndarray | None = None

    def load_model(self) -> None:
        if self.model is None:
            self.model = SentenceTransformer(self.model_name)

    def build(self, documents: Sequence[CanonicalDocument]) -> None:
        self.load_model()
        self.documents = list(documents)
        texts = [self._document_text(doc) for doc in self.documents]
        embeddings = self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        self.embeddings = embeddings.astype(np.float32)

    def search(self, query: str, top_k: int = 10) -> list[DenseSearchResult]:
        if not self.documents or self.embeddings is None:
            return []

        self.load_model()
        query_embedding = self.model.encode([query], convert_to_numpy=True, normalize_embeddings=True)[0].astype(np.float32)
        scores = self.embeddings @ query_embedding
        order = np.argsort(scores)[::-1][:top_k]

        results: list[DenseSearchResult] = []
        for idx in order:
            doc = self.documents[int(idx)]
            results.append(
                DenseSearchResult(
                    canonical_id=doc.canonical_id,
                    score=float(scores[int(idx)]),
                    title=doc.title,
                    year=doc.year,
                    doi=doc.doi,
                    source_count=doc.source_count,
                    document=doc,
                )
            )
        return results

    @staticmethod
    def _document_text(doc: CanonicalDocument) -> str:
        parts = [
            doc.title or "",
            doc.abstract or "",
            " ".join(doc.categories or []),
            " ".join(doc.tags or []),
        ]
        return "\n".join(part for part in parts if part)
