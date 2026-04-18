from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer


DEFAULT_EMBEDDINGS_LATEST = Path("artifacts/embeddings/abstract/latest.json")
DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")


@dataclass
class SimilarityArtifacts:
    model_name: str
    text_builder: str
    normalize_embeddings: bool
    count: int
    embedding_dim: int
    embeddings: np.ndarray
    ids: list[str]
    id_to_index: dict[str, int]


def load_json(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def iter_jsonl(path: str | Path):
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_canonical_map(path: str | Path = DEFAULT_CANONICAL_PATH) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in iter_jsonl(path):
        cid = row.get("canonical_id")
        if cid:
            out[str(cid)] = row
    return out


def load_similarity_artifacts(
    latest_path: str | Path = DEFAULT_EMBEDDINGS_LATEST,
) -> SimilarityArtifacts:
    latest = load_json(latest_path)

    embeddings_path = Path(latest["embeddings_path"])
    ids_path = Path(latest["ids_path"])

    embeddings = np.load(embeddings_path)
    ids_payload = load_json(ids_path)
    ids = ids_payload["ids"]

    if len(ids) != embeddings.shape[0]:
        raise ValueError(
            f"IDs count ({len(ids)}) does not match embedding rows ({embeddings.shape[0]})"
        )

    id_to_index = {cid: idx for idx, cid in enumerate(ids)}

    return SimilarityArtifacts(
        model_name=str(latest["model_name"]),
        text_builder=str(latest["text_builder"]),
        normalize_embeddings=bool(latest["normalize_embeddings"]),
        count=int(latest["count"]),
        embedding_dim=int(latest["embedding_dim"]),
        embeddings=embeddings,
        ids=ids,
        id_to_index=id_to_index,
    )


def _normalize_vector(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm


def _cosine_scores(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    return matrix @ query_vec


def _top_k_indices(scores: np.ndarray, top_k: int) -> np.ndarray:
    top_k = min(max(1, top_k), len(scores))
    if top_k >= len(scores):
        return np.argsort(-scores)

    part = np.argpartition(-scores, top_k)[:top_k]
    return part[np.argsort(-scores[part])]


def _build_result_row(
    *,
    canonical_id: str,
    score: float,
    canonical_map: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    row = canonical_map.get(canonical_id, {}) if canonical_map else {}

    return {
        "canonical_id": canonical_id,
        "score": float(score),
        "title": row.get("title"),
        "year": row.get("year"),
        "doi": row.get("doi"),
        "arxiv_id": row.get("arxiv_id"),
        "categories": row.get("categories") or [],
        "source_count": row.get("source_count"),
        "unique_source_count": row.get("unique_source_count"),
    }


def find_similar_by_canonical_id(
    canonical_id: str,
    *,
    artifacts: SimilarityArtifacts,
    canonical_map: dict[str, dict[str, Any]] | None = None,
    top_k: int = 10,
    include_query_doc: bool = False,
) -> list[dict[str, Any]]:
    if canonical_id not in artifacts.id_to_index:
        raise KeyError(f"canonical_id not found in embedding artifacts: {canonical_id}")

    query_idx = artifacts.id_to_index[canonical_id]
    query_vec = artifacts.embeddings[query_idx]

    scores = _cosine_scores(query_vec, artifacts.embeddings)
    ranked_idx = _top_k_indices(scores, top_k + (0 if include_query_doc else 1))

    results: list[dict[str, Any]] = []
    for idx in ranked_idx.tolist():
        cid = artifacts.ids[idx]
        if not include_query_doc and cid == canonical_id:
            continue

        results.append(
            _build_result_row(
                canonical_id=cid,
                score=float(scores[idx]),
                canonical_map=canonical_map,
            )
        )

        if len(results) >= top_k:
            break

    return results


def search_by_text_query(
    query_text: str,
    *,
    model: SentenceTransformer,
    artifacts: SimilarityArtifacts,
    canonical_map: dict[str, dict[str, Any]] | None = None,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    if not query_text or not query_text.strip():
        raise ValueError("query_text must be non-empty")

    query_vec = model.encode(
        [query_text],
        convert_to_numpy=True,
        normalize_embeddings=artifacts.normalize_embeddings,
        show_progress_bar=False,
    )[0]

    if not artifacts.normalize_embeddings:
        query_vec = _normalize_vector(query_vec)
        matrix = np.asarray([_normalize_vector(v) for v in artifacts.embeddings])
    else:
        matrix = artifacts.embeddings

    scores = _cosine_scores(query_vec, matrix)
    ranked_idx = _top_k_indices(scores, top_k)

    results: list[dict[str, Any]] = []
    for idx in ranked_idx.tolist():
        cid = artifacts.ids[idx]
        results.append(
            _build_result_row(
                canonical_id=cid,
                score=float(scores[idx]),
                canonical_map=canonical_map,
            )
        )

    return results


def load_similarity_model(model_name: str) -> SentenceTransformer:
    return SentenceTransformer(model_name)