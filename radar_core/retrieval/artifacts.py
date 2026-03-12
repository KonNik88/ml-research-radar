from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class DenseArtifacts:
    embeddings: np.ndarray
    ids: list[str]
    meta: dict[str, Any]


@dataclass
class LexicalArtifacts:
    index: Any
    ids: list[str]


@dataclass
class RetrievalBuildManifest:
    build_id: str
    created_at: str
    corpus_path: str
    corpus_doc_count: int
    corpus_fingerprint: str
    lexical_index_path: str
    lexical_ids_path: str
    dense_embeddings_path: str
    dense_ids_path: str
    dense_meta_path: str
    embedding_model_name: str
    text_fields: list[str]


DEFAULT_TEXT_FIELDS = [
    "title",
    "abstract",
    "authors",
    "categories",
    "concepts",
    "keywords",
    "tags",
    "primary_category",
    "venue",
    "journal",
    "conference",
    "publisher",
    "publication_type",
    "comment",
    "journal_ref",
    "language",
]


def make_build_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ensure_retrieval_dirs(root_dir: str | Path = "artifacts/retrieval") -> dict[str, Path]:
    root = Path(root_dir)
    dirs = {
        "root": root,
        "manifests": root / "manifests",
        "lexical": root / "lexical",
        "dense": root / "dense",
        "corpus": root / "corpus",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def _json_default(obj):
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def save_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=_json_default)


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def file_sha256(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with Path(path).open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def save_dense_artifacts(
    embeddings: np.ndarray,
    ids: list[str],
    meta: dict[str, Any],
    build_id: str,
    root_dir: str | Path = "artifacts/retrieval",
) -> tuple[Path, Path, Path]:
    dirs = ensure_retrieval_dirs(root_dir)
    embeddings_path = dirs["dense"] / f"embeddings_{build_id}.npy"
    ids_path = dirs["dense"] / f"ids_{build_id}.json"
    meta_path = dirs["dense"] / f"meta_{build_id}.json"

    np.save(embeddings_path, embeddings)
    save_json(ids_path, ids)
    save_json(meta_path, meta)
    return embeddings_path, ids_path, meta_path


def load_dense_artifacts(
    embeddings_path: str | Path,
    ids_path: str | Path,
    meta_path: str | Path,
) -> DenseArtifacts:
    embeddings = np.load(embeddings_path)
    ids = load_json(ids_path)
    meta = load_json(meta_path)
    return DenseArtifacts(embeddings=embeddings, ids=ids, meta=meta)


def save_lexical_artifacts(
    index: Any,
    ids: list[str],
    build_id: str,
    root_dir: str | Path = "artifacts/retrieval",
) -> tuple[Path, Path]:
    dirs = ensure_retrieval_dirs(root_dir)
    index_path = dirs["lexical"] / f"bm25_{build_id}.pkl"
    ids_path = dirs["lexical"] / f"ids_{build_id}.json"

    with index_path.open("wb") as f:
        pickle.dump(index, f)

    save_json(ids_path, ids)
    return index_path, ids_path


def load_lexical_artifacts(
    index_path: str | Path,
    ids_path: str | Path,
) -> LexicalArtifacts:
    with Path(index_path).open("rb") as f:
        index = pickle.load(f)

    ids = load_json(ids_path)
    return LexicalArtifacts(index=index, ids=ids)


def save_corpus_snapshot(
    corpus_info: dict[str, Any],
    build_id: str,
    root_dir: str | Path = "artifacts/retrieval",
) -> Path:
    dirs = ensure_retrieval_dirs(root_dir)
    path = dirs["corpus"] / f"corpus_{build_id}.json"
    save_json(path, corpus_info)
    return path


def write_manifest(
    manifest: RetrievalBuildManifest,
    root_dir: str | Path = "artifacts/retrieval",
    write_latest: bool = True,
) -> Path:
    dirs = ensure_retrieval_dirs(root_dir)
    manifest_path = dirs["manifests"] / f"{manifest.build_id}.json"
    save_json(manifest_path, asdict(manifest))

    if write_latest:
        latest_path = dirs["manifests"] / "latest.json"
        save_json(latest_path, asdict(manifest))

    return manifest_path


def read_manifest(path: str | Path) -> RetrievalBuildManifest:
    payload = load_json(path)
    return RetrievalBuildManifest(**payload)


def read_latest_manifest(root_dir: str | Path = "artifacts/retrieval") -> RetrievalBuildManifest:
    latest_path = Path(root_dir) / "manifests" / "latest.json"
    if not latest_path.exists():
        raise FileNotFoundError(
            f"Manifest not found: {latest_path}. "
            f"Сначала запусти: python -m scripts.retrieval.build_indexes"
        )
    return read_manifest(latest_path)