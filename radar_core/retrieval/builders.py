from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from sentence_transformers import SentenceTransformer

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.retrieval.artifacts import (
    DEFAULT_TEXT_FIELDS,
    RetrievalBuildManifest,
    file_sha256,
    make_build_id,
    save_corpus_snapshot,
    save_dense_artifacts,
    save_lexical_artifacts,
    write_manifest,
)
from radar_core.retrieval.lexical import BM25Index, build_bm25_index


def _doc_to_text(doc: CanonicalDocument) -> str:
    parts = [
        getattr(doc, "title", "") or "",
        getattr(doc, "abstract", "") or "",
        " ".join(getattr(doc, "authors", []) or []),
        " ".join(getattr(doc, "categories", []) or []),
        " ".join(getattr(doc, "tags", []) or []),
        getattr(doc, "primary_category", "") or "",
    ]
    return "\n".join(part for part in parts if part)


def _doc_to_dict(doc: CanonicalDocument) -> dict[str, Any]:
    if hasattr(doc, "model_dump"):
        return doc.model_dump()
    if hasattr(doc, "dict"):
        return doc.dict()
    if is_dataclass(doc):
        return asdict(doc)
    if hasattr(doc, "__dict__"):
        return dict(doc.__dict__)
    raise TypeError(f"Cannot serialize CanonicalDocument of type {type(doc)!r}")


def _canonical_from_payload(payload: dict[str, Any]) -> CanonicalDocument:
    if hasattr(CanonicalDocument, "model_validate"):
        return CanonicalDocument.model_validate(payload)
    if hasattr(CanonicalDocument, "parse_obj"):
        return CanonicalDocument.parse_obj(payload)
    if hasattr(CanonicalDocument, "from_dict"):
        return CanonicalDocument.from_dict(payload)
    return CanonicalDocument(**payload)


def load_canonical_documents(corpus_path: str | Path) -> list[CanonicalDocument]:
    corpus_path = Path(corpus_path)
    documents: list[CanonicalDocument] = []

    with corpus_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                documents.append(_canonical_from_payload(payload))
            except Exception as exc:
                raise ValueError(
                    f"Failed to parse canonical document at line {line_no} in {corpus_path}: {exc}"
                ) from exc

    return documents


def build_lexical_index(documents: Sequence[CanonicalDocument]) -> BM25Index:
    return build_bm25_index(documents)


def build_dense_embeddings(
    documents: Sequence[CanonicalDocument],
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    batch_size: int = 64,
) -> tuple[np.ndarray, list[str], dict[str, Any]]:
    texts = [_doc_to_text(doc) for doc in documents]
    ids = [doc.canonical_id for doc in documents]

    model = SentenceTransformer(model_name)
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    ).astype(np.float32)

    meta = {
        "model_name": model_name,
        "embedding_dim": int(embeddings.shape[1]) if embeddings.ndim == 2 and embeddings.size else 0,
        "doc_count": len(ids),
        "normalized": True,
        "batch_size": batch_size,
    }
    return embeddings, ids, meta


def build_retrieval_artifacts(
    corpus_path: str | Path = "data/analytics/reconciled/canonical_documents.jsonl",
    root_dir: str | Path = "artifacts/retrieval",
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    batch_size: int = 64,
    write_latest: bool = True,
) -> RetrievalBuildManifest:
    corpus_path = Path(corpus_path)
    if not corpus_path.exists():
        raise FileNotFoundError(f"Canonical corpus not found: {corpus_path}")

    documents = load_canonical_documents(corpus_path)
    if not documents:
        raise ValueError(f"No canonical documents found in: {corpus_path}")

    build_id = make_build_id()
    corpus_fingerprint = file_sha256(corpus_path)

    lexical_index = build_lexical_index(documents)
    lexical_ids = [doc.canonical_id for doc in documents]
    lexical_index_path, lexical_ids_path = save_lexical_artifacts(
        index=lexical_index,
        ids=lexical_ids,
        build_id=build_id,
        root_dir=root_dir,
    )

    embeddings, dense_ids, dense_meta = build_dense_embeddings(
        documents=documents,
        model_name=model_name,
        batch_size=batch_size,
    )
    dense_embeddings_path, dense_ids_path, dense_meta_path = save_dense_artifacts(
        embeddings=embeddings,
        ids=dense_ids,
        meta=dense_meta,
        build_id=build_id,
        root_dir=root_dir,
    )

    corpus_snapshot = {
        "build_id": build_id,
        "corpus_path": str(corpus_path),
        "corpus_doc_count": len(documents),
        "corpus_fingerprint": corpus_fingerprint,
        "sample_ids": lexical_ids[:10],
        "text_fields": DEFAULT_TEXT_FIELDS,
        "sample_documents": [_doc_to_dict(doc) for doc in documents[:3]],
    }
    save_corpus_snapshot(corpus_snapshot, build_id=build_id, root_dir=root_dir)

    manifest = RetrievalBuildManifest(
        build_id=build_id,
        created_at=make_build_id(),
        corpus_path=str(corpus_path),
        corpus_doc_count=len(documents),
        corpus_fingerprint=corpus_fingerprint,
        lexical_index_path=str(lexical_index_path),
        lexical_ids_path=str(lexical_ids_path),
        dense_embeddings_path=str(dense_embeddings_path),
        dense_ids_path=str(dense_ids_path),
        dense_meta_path=str(dense_meta_path),
        embedding_model_name=model_name,
        text_fields=DEFAULT_TEXT_FIELDS,
    )
    write_manifest(manifest, root_dir=root_dir, write_latest=write_latest)
    return manifest
