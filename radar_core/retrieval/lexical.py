from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from radar_core.contracts.canonical_document import CanonicalDocument

TOKEN_RE = re.compile(r"\b\w+\b", re.UNICODE)


@dataclass
class LexicalSearchResult:
    canonical_id: str
    score: float
    title: str
    year: int | None
    doi: str | None
    source_count: int
    document: CanonicalDocument


class SimpleTokenizer:
    def tokenize(self, text: str) -> list[str]:
        return [t.lower() for t in TOKEN_RE.findall(text or "") if t.strip()]


class BM25Index:
    """
    Compact in-memory BM25 index for canonical documents.
    Good enough for the first retrieval slice without extra dependencies.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75, tokenizer: SimpleTokenizer | None = None):
        self.k1 = k1
        self.b = b
        self.tokenizer = tokenizer or SimpleTokenizer()
        self.documents: list[CanonicalDocument] = []
        self.doc_tokens: list[list[str]] = []
        self.doc_lengths: list[int] = []
        self.term_doc_freq: dict[str, int] = {}
        self.avg_doc_len: float = 0.0

    def build(self, documents: Sequence[CanonicalDocument]) -> None:
        self.documents = list(documents)
        self.doc_tokens = []
        self.doc_lengths = []
        self.term_doc_freq = {}

        for doc in self.documents:
            text = self._document_text(doc)
            tokens = self.tokenizer.tokenize(text)
            self.doc_tokens.append(tokens)
            self.doc_lengths.append(len(tokens))

            seen = set(tokens)
            for token in seen:
                self.term_doc_freq[token] = self.term_doc_freq.get(token, 0) + 1

        self.avg_doc_len = sum(self.doc_lengths) / len(self.doc_lengths) if self.doc_lengths else 0.0

    def search(self, query: str, top_k: int = 10) -> list[LexicalSearchResult]:
        if not self.documents:
            return []

        query_tokens = self.tokenizer.tokenize(query)
        if not query_tokens:
            return []

        scores: list[tuple[int, float]] = []
        n_docs = len(self.documents)

        for doc_idx, tokens in enumerate(self.doc_tokens):
            if not tokens:
                scores.append((doc_idx, 0.0))
                continue

            tf_map: dict[str, int] = {}
            for token in tokens:
                tf_map[token] = tf_map.get(token, 0) + 1

            doc_len = self.doc_lengths[doc_idx]
            score = 0.0

            for token in query_tokens:
                tf = tf_map.get(token, 0)
                if tf == 0:
                    continue

                df = self.term_doc_freq.get(token, 0)
                idf = math.log(1 + ((n_docs - df + 0.5) / (df + 0.5)))
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * (doc_len / max(self.avg_doc_len, 1e-9)))
                score += idf * (numerator / denominator)

            scores.append((doc_idx, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        results: list[LexicalSearchResult] = []

        for doc_idx, score in scores[:top_k]:
            doc = self.documents[doc_idx]
            results.append(
                LexicalSearchResult(
                    canonical_id=doc.canonical_id,
                    score=score,
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
            " ".join(doc.authors or []),
            " ".join(doc.categories or []),
            " ".join(doc.tags or []),
            doc.primary_category or "",
        ]
        return "\n".join(part for part in parts if part)


def build_bm25_index(documents: Sequence[CanonicalDocument]) -> BM25Index:
    index = BM25Index()
    index.build(documents)
    return index
