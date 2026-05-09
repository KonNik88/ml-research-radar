from __future__ import annotations

import json
import math
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


DEFAULT_DENSE_DIR = Path("artifacts/retrieval/dense")
DEFAULT_RETRIEVAL_MANIFEST_PATH = Path("artifacts/retrieval/manifests/latest.json")
DEFAULT_FEATURES_PATH = Path("data/features/paper_features_latest.jsonl")
DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")


@dataclass(frozen=True)
class DenseBundle:
    embeddings: np.ndarray
    ids: list[str]
    meta_rows: list[dict[str, Any]]
    embedding_path: Path
    ids_path: Path | None
    meta_path: Path | None


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def iter_jsonl(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line), line_no
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL: {path} line={line_no}: {exc}") from exc


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

def resolve_manifest_path_value(value: Any) -> Path | None:
    if not value:
        return None
    return Path(str(value))


def load_latest_retrieval_manifest(
    manifest_path: Path = DEFAULT_RETRIEVAL_MANIFEST_PATH,
) -> dict[str, Any]:
    if not manifest_path.exists():
        return {}

    payload = load_json(manifest_path)

    if not isinstance(payload, dict):
        raise ValueError(f"Retrieval manifest must be a JSON object: {manifest_path}")

    return payload


def dense_paths_from_manifest(
    manifest_path: Path = DEFAULT_RETRIEVAL_MANIFEST_PATH,
) -> dict[str, Path | None]:
    manifest = load_latest_retrieval_manifest(manifest_path)

    if not manifest:
        return {
            "embedding_path": None,
            "ids_path": None,
            "meta_path": None,
        }

    return {
        "embedding_path": resolve_manifest_path_value(manifest.get("dense_embeddings_path")),
        "ids_path": resolve_manifest_path_value(manifest.get("dense_ids_path")),
        "meta_path": resolve_manifest_path_value(manifest.get("dense_meta_path")),
    }

def load_pickle(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Pickle file not found: {path}")
    with path.open("rb") as f:
        return pickle.load(f)


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def discover_files(root: Path) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(f"Dense retrieval directory not found: {root}")

    return sorted(p for p in root.rglob("*") if p.is_file())


def score_embedding_candidate(path: Path) -> tuple[int, int]:
    name = path.name.lower()
    score = 0

    if path.suffix.lower() in {".npy", ".npz"}:
        score += 100
    else:
        score -= 1000

    if "embedding" in name or "embeddings" in name:
        score += 100
    if "dense" in name:
        score += 30
    if "vector" in name or "vectors" in name:
        score += 20
    if "id" in name or "meta" in name or "metadata" in name:
        score -= 200

    try:
        size = path.stat().st_size
    except OSError:
        size = 0

    return score, size


def discover_embedding_path(dense_dir: Path) -> Path:
    candidates = [
        p
        for p in discover_files(dense_dir)
        if p.suffix.lower() in {".npy", ".npz"}
    ]

    if not candidates:
        raise FileNotFoundError(
            f"No .npy/.npz embedding candidates found under {dense_dir}"
        )

    candidates.sort(key=score_embedding_candidate, reverse=True)
    return candidates[0]


def score_ids_candidate(path: Path) -> tuple[int, int]:
    name = path.name.lower()
    score = 0

    if path.suffix.lower() in {".json", ".jsonl", ".txt", ".pkl", ".pickle", ".npy"}:
        score += 50
    else:
        score -= 1000

    if "canonical" in name:
        score += 50
    if "ids" in name or name in {"ids.json", "ids.jsonl", "ids.txt"}:
        score += 100
    if "doc_ids" in name or "document_ids" in name:
        score += 80
    if "meta" in name or "metadata" in name:
        score -= 40
    if "embedding" in name or "vector" in name:
        score -= 200

    try:
        size = path.stat().st_size
    except OSError:
        size = 0

    return score, size


def discover_ids_path(dense_dir: Path) -> Path | None:
    candidates = [
        p
        for p in discover_files(dense_dir)
        if p.suffix.lower() in {".json", ".jsonl", ".txt", ".pkl", ".pickle", ".npy"}
        and ("id" in p.name.lower() or "ids" in p.name.lower())
        and "embedding" not in p.name.lower()
        and "vector" not in p.name.lower()
    ]

    if not candidates:
        return None

    candidates.sort(key=score_ids_candidate, reverse=True)
    return candidates[0]


def score_meta_candidate(path: Path) -> tuple[int, int]:
    name = path.name.lower()
    score = 0

    if path.suffix.lower() in {".json", ".jsonl", ".pkl", ".pickle"}:
        score += 50
    else:
        score -= 1000

    if "meta" in name or "metadata" in name:
        score += 100
    if "dense" in name:
        score += 20
    if "embedding" in name or "vector" in name:
        score -= 200

    try:
        size = path.stat().st_size
    except OSError:
        size = 0

    return score, size


def discover_meta_path(dense_dir: Path) -> Path | None:
    candidates = [
        p
        for p in discover_files(dense_dir)
        if p.suffix.lower() in {".json", ".jsonl", ".pkl", ".pickle"}
        and ("meta" in p.name.lower() or "metadata" in p.name.lower())
    ]

    if not candidates:
        return None

    candidates.sort(key=score_meta_candidate, reverse=True)
    return candidates[0]


def load_embeddings(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(f"Embedding file not found: {path}")

    if path.suffix.lower() == ".npy":
        arr = np.load(path, allow_pickle=False)
    elif path.suffix.lower() == ".npz":
        payload = np.load(path, allow_pickle=False)
        if "embeddings" in payload.files:
            arr = payload["embeddings"]
        elif "vectors" in payload.files:
            arr = payload["vectors"]
        else:
            arr = payload[payload.files[0]]
    else:
        raise ValueError(f"Unsupported embedding file type: {path}")

    arr = np.asarray(arr)

    if arr.ndim != 2:
        raise ValueError(f"Embeddings must be 2D, got shape={arr.shape} from {path}")

    return arr.astype(np.float32, copy=False)


def extract_id_from_row(row: Any) -> str | None:
    if isinstance(row, str):
        text = row.strip()
        return text or None

    if isinstance(row, dict):
        for key in (
            "canonical_id",
            "id",
            "doc_id",
            "document_id",
            "paper_id",
            "corpus_id",
        ):
            value = row.get(key)
            if value:
                return str(value)

    return None


def ids_from_json_payload(payload: Any) -> list[str]:
    if isinstance(payload, list):
        ids: list[str] = []
        for item in payload:
            item_id = extract_id_from_row(item)
            if item_id:
                ids.append(item_id)
        return ids

    if isinstance(payload, dict):
        for key in ("canonical_ids", "ids", "doc_ids", "document_ids", "paper_ids"):
            value = payload.get(key)
            if isinstance(value, list):
                ids = []
                for item in value:
                    item_id = extract_id_from_row(item)
                    if item_id:
                        ids.append(item_id)
                return ids

        if payload and all(isinstance(v, int) for v in payload.values()):
            return [str(k) for k, _ in sorted(payload.items(), key=lambda kv: kv[1])]

        if payload and all(isinstance(v, dict) for v in payload.values()):
            ids = []
            for item in payload.values():
                item_id = extract_id_from_row(item)
                if item_id:
                    ids.append(item_id)
            return ids

    return []


def load_ids(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"IDs file not found: {path}")

    suffix = path.suffix.lower()

    if suffix == ".json":
        return ids_from_json_payload(load_json(path))

    if suffix == ".jsonl":
        ids = []
        for row, _ in iter_jsonl(path):
            item_id = extract_id_from_row(row)
            if item_id:
                ids.append(item_id)
        return ids

    if suffix == ".txt":
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    if suffix in {".pkl", ".pickle"}:
        return ids_from_json_payload(load_pickle(path))

    if suffix == ".npy":
        payload = np.load(path, allow_pickle=True)
        return [str(x) for x in payload.tolist() if str(x).strip()]

    raise ValueError(f"Unsupported IDs file type: {path}")


def metadata_rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]

    if isinstance(payload, dict):
        for key in ("meta", "metadata", "rows", "documents", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]

        if payload and all(isinstance(v, dict) for v in payload.values()):
            return list(payload.values())

    return []


def load_meta_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Metadata file not found: {path}")

    suffix = path.suffix.lower()

    if suffix == ".jsonl":
        return [row for row, _ in iter_jsonl(path) if isinstance(row, dict)]

    if suffix == ".json":
        return metadata_rows_from_payload(load_json(path))

    if suffix in {".pkl", ".pickle"}:
        return metadata_rows_from_payload(load_pickle(path))

    raise ValueError(f"Unsupported metadata file type: {path}")


def extract_ids_from_meta_rows(meta_rows: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for row in meta_rows:
        item_id = extract_id_from_row(row)
        if item_id:
            ids.append(item_id)
        else:
            ids.append("")
    return ids


def load_dense_bundle(
    *,
    dense_dir: Path = DEFAULT_DENSE_DIR,
    embedding_path: Path | None = None,
    ids_path: Path | None = None,
    meta_path: Path | None = None,
    manifest_path: Path = DEFAULT_RETRIEVAL_MANIFEST_PATH,
) -> DenseBundle:
    manifest_paths = dense_paths_from_manifest(manifest_path)

    embedding_path = (
        embedding_path
        or manifest_paths.get("embedding_path")
        or discover_embedding_path(dense_dir)
    )
    ids_path = (
        ids_path
        if ids_path is not None
        else manifest_paths.get("ids_path")
        or discover_ids_path(dense_dir)
    )
    meta_path = (
        meta_path
        if meta_path is not None
        else manifest_paths.get("meta_path")
        or discover_meta_path(dense_dir)
    )

    embeddings = load_embeddings(embedding_path)
    n_rows = int(embeddings.shape[0])

    ids: list[str] = []
    meta_rows: list[dict[str, Any]] = []

    if ids_path is not None:
        ids = load_ids(ids_path)

    if meta_path is not None:
        meta_rows = load_meta_rows(meta_path)

    meta_ids = extract_ids_from_meta_rows(meta_rows) if meta_rows else []

    if len(ids) != n_rows and len(meta_ids) == n_rows and all(meta_ids):
        ids = meta_ids

    if len(ids) != n_rows:
        raise ValueError(
            "Dense artifact shape mismatch: "
            f"embeddings_rows={n_rows}, ids_count={len(ids)}, "
            f"meta_rows_count={len(meta_rows)}, "
            f"embedding_path={embedding_path}, ids_path={ids_path}, meta_path={meta_path}, "
            f"manifest_path={manifest_path}. "
            "Pass explicit --embedding-path/--ids-path/--meta-path if auto-discovery chose wrong files."
        )

    if meta_rows and len(meta_rows) != n_rows:
        # In this project dense_meta_path can be build-level metadata, not row-level metadata.
        # Row-level title/year enrichment comes from paper_features/canonical files.
        meta_rows = []

    return DenseBundle(
        embeddings=embeddings,
        ids=ids,
        meta_rows=meta_rows,
        embedding_path=embedding_path,
        ids_path=ids_path,
        meta_path=meta_path,
    )

def load_jsonl_by_canonical_id(path: Path, *, optional: bool = False) -> dict[str, dict[str, Any]]:
    if optional and not path.exists():
        return {}

    out: dict[str, dict[str, Any]] = {}

    for row, _ in iter_jsonl(path):
        canonical_id = row.get("canonical_id")
        if canonical_id:
            out[str(canonical_id)] = row

    return out


def normalize_embeddings(embeddings: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(embeddings, axis=1)
    safe_norms = np.where(norms > 0.0, norms, 1.0).astype(np.float32)
    return embeddings / safe_norms[:, None]


def semantic_to_unit_interval(value: float) -> float:
    return clamp01((float(value) + 1.0) / 2.0)


def radar_adjusted_score(
    *,
    semantic_similarity: float,
    radar_score: float,
    implementation_readiness_score: float,
) -> float:
    semantic_norm = semantic_to_unit_interval(semantic_similarity)

    return round(
        clamp01(
            0.85 * semantic_norm
            + 0.10 * clamp01(radar_score)
            + 0.05 * clamp01(implementation_readiness_score)
        ),
        6,
    )


def feature_or_default(features: dict[str, Any] | None, key: str, default: Any = None) -> Any:
    if not features:
        return default
    return features.get(key, default)


def canonical_or_default(canonical: dict[str, Any] | None, key: str, default: Any = None) -> Any:
    if not canonical:
        return default
    return canonical.get(key, default)


def build_target_summary(
    *,
    canonical_id: str,
    features_by_id: dict[str, dict[str, Any]],
    canonical_by_id: dict[str, dict[str, Any]],
    dense_index: int,
) -> dict[str, Any]:
    features = features_by_id.get(canonical_id)
    canonical = canonical_by_id.get(canonical_id)

    return {
        "canonical_id": canonical_id,
        "dense_index": dense_index,
        "title": feature_or_default(features, "title")
        or canonical_or_default(canonical, "title"),
        "year": feature_or_default(features, "year")
        or canonical_or_default(canonical, "year"),
        "radar_score": feature_or_default(features, "radar_score"),
        "implementation_readiness_score": feature_or_default(
            features,
            "implementation_readiness_score",
        ),
        "source_confidence_score": feature_or_default(features, "source_confidence_score"),
        "citation_signal_score": feature_or_default(features, "citation_signal_score"),
        "source_families": feature_or_default(features, "source_families", []),
    }


def build_result_row(
    *,
    canonical_id: str,
    dense_index: int,
    semantic_similarity: float,
    features_by_id: dict[str, dict[str, Any]],
    canonical_by_id: dict[str, dict[str, Any]],
    meta_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    features = features_by_id.get(canonical_id)
    canonical = canonical_by_id.get(canonical_id)
    meta = meta_rows[dense_index] if meta_rows and dense_index < len(meta_rows) else {}

    radar_score = safe_float(feature_or_default(features, "radar_score"), default=0.0)
    impl_score = safe_float(
        feature_or_default(features, "implementation_readiness_score"),
        default=0.0,
    )

    adjusted = radar_adjusted_score(
        semantic_similarity=semantic_similarity,
        radar_score=radar_score,
        implementation_readiness_score=impl_score,
    )

    return {
        "canonical_id": canonical_id,
        "dense_index": dense_index,
        "title": feature_or_default(features, "title")
        or canonical_or_default(canonical, "title")
        or meta.get("title"),
        "year": feature_or_default(features, "year")
        or canonical_or_default(canonical, "year")
        or meta.get("year"),
        "semantic_similarity": round(float(semantic_similarity), 6),
        "semantic_similarity_norm": round(semantic_to_unit_interval(float(semantic_similarity)), 6),
        "radar_adjusted_similarity": adjusted,
        "radar_score": radar_score,
        "implementation_readiness_score": impl_score,
        "source_confidence_score": safe_float(
            feature_or_default(features, "source_confidence_score"),
            default=0.0,
        ),
        "citation_signal_score": safe_float(
            feature_or_default(features, "citation_signal_score"),
            default=0.0,
        ),
        "recency_score": safe_float(feature_or_default(features, "recency_score"), default=0.0),
        "trusted_artifact_links_count": safe_int(
            feature_or_default(features, "trusted_artifact_links_count"),
            default=0,
        ),
        "trusted_code_links_count": safe_int(
            feature_or_default(features, "trusted_code_links_count"),
            default=0,
        ),
        "trusted_dataset_links_count": safe_int(
            feature_or_default(features, "trusted_dataset_links_count"),
            default=0,
        ),
        "trusted_model_links_count": safe_int(
            feature_or_default(features, "trusted_model_links_count"),
            default=0,
        ),
        "trusted_demo_links_count": safe_int(
            feature_or_default(features, "trusted_demo_links_count"),
            default=0,
        ),
        "has_code_artifact": bool(feature_or_default(features, "has_code_artifact", False)),
        "has_dataset_artifact": bool(
            feature_or_default(features, "has_dataset_artifact", False)
        ),
        "has_model_artifact": bool(feature_or_default(features, "has_model_artifact", False)),
        "has_demo_artifact": bool(feature_or_default(features, "has_demo_artifact", False)),
        "github_found_repo_count": safe_int(
            feature_or_default(features, "github_found_repo_count"),
            default=0,
        ),
        "github_stars_max": safe_int(
            feature_or_default(features, "github_stars_max"),
            default=0,
        ),
        "hf_found_count": safe_int(feature_or_default(features, "hf_found_count"), default=0),
        "hf_model_count": safe_int(feature_or_default(features, "hf_model_count"), default=0),
        "hf_dataset_count": safe_int(feature_or_default(features, "hf_dataset_count"), default=0),
        "hf_space_count": safe_int(feature_or_default(features, "hf_space_count"), default=0),
        "citation_count": safe_int(feature_or_default(features, "citation_count"), default=0),
        "source_families": feature_or_default(features, "source_families", []),
    }


def top_indices(scores: np.ndarray, *, top_k: int) -> list[int]:
    top_k = max(1, int(top_k))
    finite_mask = np.isfinite(scores)
    valid_indices = np.where(finite_mask)[0]

    if len(valid_indices) == 0:
        return []

    k = min(top_k, len(valid_indices))
    valid_scores = scores[valid_indices]

    if k == len(valid_indices):
        order = np.argsort(-valid_scores)
        return [int(valid_indices[i]) for i in order[:k]]

    candidate_local = np.argpartition(-valid_scores, kth=k - 1)[:k]
    candidate_local = candidate_local[np.argsort(-valid_scores[candidate_local])]

    return [int(valid_indices[i]) for i in candidate_local]

def resolve_ids_for_lookup(
    *,
    canonical_id: str,
    bundle: DenseBundle,
    id_to_index: dict[str, int] | None = None,
) -> tuple[list[str], dict[str, int], int]:
    if id_to_index is None:
        id_to_index = {doc_id: idx for idx, doc_id in enumerate(bundle.ids)}

    if canonical_id not in id_to_index:
        meta_ids = extract_ids_from_meta_rows(bundle.meta_rows)
        if len(meta_ids) == len(bundle.ids) and canonical_id in meta_ids:
            ids_for_lookup = meta_ids
            id_to_index = {doc_id: idx for idx, doc_id in enumerate(ids_for_lookup)}
        else:
            available_hint = bundle.ids[:5]
            raise ValueError(
                f"canonical_id={canonical_id!r} not found in dense ids. "
                f"First ids: {available_hint}. "
                "If dense ids use another field, pass explicit --ids-path/--meta-path."
            )
    else:
        ids_for_lookup = bundle.ids

    return ids_for_lookup, id_to_index, id_to_index[canonical_id]


def find_similar_papers_from_loaded(
    *,
    canonical_id: str,
    bundle: DenseBundle,
    normalized_embeddings: np.ndarray,
    id_to_index: dict[str, int],
    features_by_id: dict[str, dict[str, Any]],
    canonical_by_id: dict[str, dict[str, Any]],
    dense_dir: Path = DEFAULT_DENSE_DIR,
    manifest_path: Path = DEFAULT_RETRIEVAL_MANIFEST_PATH,
    features_path: Path = DEFAULT_FEATURES_PATH,
    canonical_path: Path = DEFAULT_CANONICAL_PATH,
    top_k: int = 20,
    rank_by: str = "semantic",
    min_similarity: float | None = None,
) -> dict[str, Any]:
    canonical_id = str(canonical_id).strip()
    if not canonical_id:
        raise ValueError("canonical_id must be non-empty")

    if rank_by not in {"semantic", "radar_adjusted"}:
        raise ValueError("rank_by must be one of: semantic, radar_adjusted")

    ids_for_lookup, id_to_index, target_index = resolve_ids_for_lookup(
        canonical_id=canonical_id,
        bundle=bundle,
        id_to_index=id_to_index,
    )

    if normalized_embeddings.shape[0] != len(ids_for_lookup):
        raise ValueError(
            "Normalized embedding shape mismatch: "
            f"rows={normalized_embeddings.shape[0]}, ids_count={len(ids_for_lookup)}"
        )

    target_vector = normalized_embeddings[target_index]

    if not np.isfinite(target_vector).all() or np.linalg.norm(target_vector) <= 0.0:
        raise ValueError(f"Target embedding is invalid for canonical_id={canonical_id}")

    semantic_scores = normalized_embeddings @ target_vector
    semantic_scores = np.asarray(semantic_scores, dtype=np.float32)
    semantic_scores[target_index] = -np.inf

    if min_similarity is not None:
        semantic_scores = np.where(
            semantic_scores >= float(min_similarity),
            semantic_scores,
            -np.inf,
        )

    if rank_by == "semantic":
        ranking_scores = semantic_scores
    else:
        adjusted_scores = np.full_like(
            semantic_scores,
            fill_value=-np.inf,
            dtype=np.float32,
        )

        for idx, semantic_similarity in enumerate(semantic_scores):
            if not np.isfinite(semantic_similarity):
                continue

            doc_id = ids_for_lookup[idx]
            features = features_by_id.get(doc_id)
            adjusted_scores[idx] = radar_adjusted_score(
                semantic_similarity=float(semantic_similarity),
                radar_score=safe_float(
                    feature_or_default(features, "radar_score"),
                    default=0.0,
                ),
                implementation_readiness_score=safe_float(
                    feature_or_default(features, "implementation_readiness_score"),
                    default=0.0,
                ),
            )

        ranking_scores = adjusted_scores

    neighbor_indices = top_indices(ranking_scores, top_k=top_k)

    results: list[dict[str, Any]] = []
    for idx in neighbor_indices:
        doc_id = ids_for_lookup[idx]
        row = build_result_row(
            canonical_id=doc_id,
            dense_index=idx,
            semantic_similarity=float(semantic_scores[idx]),
            features_by_id=features_by_id,
            canonical_by_id=canonical_by_id,
            meta_rows=bundle.meta_rows,
        )
        row["rank_score"] = round(float(ranking_scores[idx]), 6)
        results.append(row)

    target = build_target_summary(
        canonical_id=canonical_id,
        features_by_id=features_by_id,
        canonical_by_id=canonical_by_id,
        dense_index=target_index,
    )

    return {
        "mode": "similar_papers",
        "target_canonical_id": canonical_id,
        "target_found": True,
        "target": target,
        "rank_by": rank_by,
        "top_k": int(top_k),
        "min_similarity": min_similarity,
        "input_rows_count": int(bundle.embeddings.shape[0]),
        "returned_rows_count": len(results),
        "dense_artifacts": {
            "dense_dir": normalize_path(dense_dir),
            "manifest_path": normalize_path(manifest_path),
            "embedding_path": normalize_path(bundle.embedding_path),
            "ids_path": normalize_path(bundle.ids_path),
            "meta_path": normalize_path(bundle.meta_path),
            "embedding_shape": list(bundle.embeddings.shape),
            "ids_count": len(bundle.ids),
            "meta_rows_count": len(bundle.meta_rows),
        },
        "inputs": {
            "features_path": normalize_path(features_path),
            "canonical_path": normalize_path(canonical_path),
        },
        "results": results,
    }

def find_similar_papers(
    *,
    canonical_id: str,
    dense_dir: Path = DEFAULT_DENSE_DIR,
    manifest_path: Path = DEFAULT_RETRIEVAL_MANIFEST_PATH,
    embedding_path: Path | None = None,
    ids_path: Path | None = None,
    meta_path: Path | None = None,
    features_path: Path = DEFAULT_FEATURES_PATH,
    canonical_path: Path = DEFAULT_CANONICAL_PATH,
    top_k: int = 20,
    rank_by: str = "semantic",
    min_similarity: float | None = None,
) -> dict[str, Any]:
    canonical_id = str(canonical_id).strip()
    if not canonical_id:
        raise ValueError("canonical_id must be non-empty")

    if rank_by not in {"semantic", "radar_adjusted"}:
        raise ValueError("rank_by must be one of: semantic, radar_adjusted")

    bundle = load_dense_bundle(
        dense_dir=dense_dir,
        manifest_path=manifest_path,
        embedding_path=embedding_path,
        ids_path=ids_path,
        meta_path=meta_path,
    )

    id_to_index = {doc_id: idx for idx, doc_id in enumerate(bundle.ids)}
    normalized = normalize_embeddings(bundle.embeddings)

    features_by_id = load_jsonl_by_canonical_id(features_path, optional=True)
    canonical_by_id = load_jsonl_by_canonical_id(canonical_path, optional=True)

    return find_similar_papers_from_loaded(
        canonical_id=canonical_id,
        bundle=bundle,
        normalized_embeddings=normalized,
        id_to_index=id_to_index,
        features_by_id=features_by_id,
        canonical_by_id=canonical_by_id,
        dense_dir=dense_dir,
        manifest_path=manifest_path,
        features_path=features_path,
        canonical_path=canonical_path,
        top_k=top_k,
        rank_by=rank_by,
        min_similarity=min_similarity,
    )