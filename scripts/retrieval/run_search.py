from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from radar_core.ranking.scoring import rank_results
from radar_core.retrieval.artifacts import (
    load_dense_artifacts,
    load_lexical_artifacts,
    read_latest_manifest,
)
from radar_core.retrieval.builders import load_canonical_documents


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--query",
        required=True,
        help="Поисковый запрос",
    )
    parser.add_argument(
        "--mode",
        choices=["lexical", "dense", "hybrid"],
        default="lexical",
        help="Режим поиска",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Сколько результатов показать",
    )
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=Path("artifacts/retrieval"),
        help="Корневая папка retrieval artifacts",
    )
    parser.add_argument(
        "--rank",
        action="store_true",
        help="Применить ranking поверх результатов hybrid",
    )
    return parser


def print_lexical_results(query: str, results) -> None:
    print(f"[OK] lexical results for query='{query}'")
    for i, r in enumerate(results, start=1):
        print(f"{i:02d}. score={r.score:.4f} | year={r.year} | sources={r.source_count}")
        print(f"    title: {r.title}")
        print(f"    doi: {r.doi}")
        print(f"    categories: {', '.join(r.document.categories[:5]) if r.document.categories else '-'}")


def print_dense_results(query: str, results: list[dict]) -> None:
    print(f"[OK] dense results for query='{query}'")
    for i, r in enumerate(results, start=1):
        print(f"{i:02d}. score={r['score']:.4f} | year={r['year']} | sources={r['source_count']}")
        print(f"    title: {r['title']}")
        print(f"    doi: {r['doi']}")
        print(f"    categories: {', '.join(r['document'].categories[:5]) if r['document'].categories else '-'}")


def print_hybrid_results(query: str, results: list[dict]) -> None:
    print(f"[OK] hybrid results for query='{query}'")
    for i, r in enumerate(results, start=1):
        print(
            f"{i:02d}. hybrid={r['hybrid_score']:.4f} | lexical={r['lexical_score']:.4f} "
            f"| dense={r['dense_score']:.4f} | year={r['year']} | sources={r['source_count']}"
        )
        print(f"    title: {r['title']}")
        print(f"    doi: {r['doi']}")
        print(f"    categories: {', '.join(r['document'].categories[:5]) if r['document'].categories else '-'}")


def print_ranked_results(query: str, results) -> None:
    print(f"[OK] ranked hybrid results for query='{query}'")
    for i, r in enumerate(results, start=1):
        print(
            f"{i:02d}. final={r.final_score:.4f} | retrieval={r.retrieval_score:.4f} "
            f"| recency={r.recency_score:.4f} | source_support={r.source_support_score:.4f} "
            f"| metadata={r.metadata_quality_score:.4f} | year={r.year} | sources={r.source_count}"
        )
        print(f"    title: {r.title}")
        print(f"    doi: {r.doi}")
        print(
            f"    categories: "
            f"{', '.join(r.document.categories[:5]) if getattr(r.document, 'categories', None) else '-'}"
        )


def embed_query(query: str, model_name: str) -> np.ndarray:
    model = SentenceTransformer(model_name)
    vec = model.encode(
        [query],
        batch_size=1,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return vec[0].astype(np.float32)


def dense_search(
    query: str,
    documents,
    embeddings: np.ndarray,
    ids: list[str],
    model_name: str,
    top_k: int = 5,
) -> list[dict]:
    query_vec = embed_query(query, model_name=model_name)
    scores = embeddings @ query_vec

    id_to_doc = {doc.canonical_id: doc for doc in documents}
    ranked_idx = np.argsort(scores)[::-1][:top_k]

    results: list[dict] = []
    for idx in ranked_idx:
        canonical_id = ids[idx]
        doc = id_to_doc.get(canonical_id)
        if doc is None:
            continue

        results.append(
            {
                "canonical_id": canonical_id,
                "score": float(scores[idx]),
                "title": doc.title,
                "year": doc.year,
                "doi": doc.doi,
                "source_count": doc.source_count,
                "document": doc,
            }
        )

    return results


def _minmax_normalize(score_map: dict[str, float]) -> dict[str, float]:
    if not score_map:
        return {}

    values = list(score_map.values())
    min_v = min(values)
    max_v = max(values)

    if abs(max_v - min_v) < 1e-12:
        return {k: 1.0 for k in score_map}

    return {k: (v - min_v) / (max_v - min_v) for k, v in score_map.items()}


def hybrid_search(
    query: str,
    documents,
    lexical_index,
    dense_embeddings: np.ndarray,
    dense_ids: list[str],
    model_name: str,
    top_k: int = 5,
    lexical_weight: float = 0.55,
    dense_weight: float = 0.45,
) -> list[dict]:
    lexical_results = lexical_index.search(query=query, top_k=top_k)
    dense_results = dense_search(
        query=query,
        documents=documents,
        embeddings=dense_embeddings,
        ids=dense_ids,
        model_name=model_name,
        top_k=top_k,
    )

    lexical_score_map = {r.canonical_id: float(r.score) for r in lexical_results}
    dense_score_map = {r["canonical_id"]: float(r["score"]) for r in dense_results}

    lexical_norm = _minmax_normalize(lexical_score_map)
    dense_norm = _minmax_normalize(dense_score_map)

    all_ids = set(lexical_norm) | set(dense_norm)
    id_to_doc = {doc.canonical_id: doc for doc in documents}

    combined: list[dict] = []
    for canonical_id in all_ids:
        doc = id_to_doc.get(canonical_id)
        if doc is None:
            continue

        lexical_score = lexical_score_map.get(canonical_id, 0.0)
        dense_score = dense_score_map.get(canonical_id, 0.0)

        hybrid_score = (
            lexical_weight * lexical_norm.get(canonical_id, 0.0)
            + dense_weight * dense_norm.get(canonical_id, 0.0)
        )

        combined.append(
            {
                "canonical_id": canonical_id,
                "hybrid_score": float(hybrid_score),
                "lexical_score": float(lexical_score),
                "dense_score": float(dense_score),
                "title": doc.title,
                "year": doc.year,
                "doi": doc.doi,
                "source_count": doc.source_count,
                "document": doc,
            }
        )

    combined.sort(key=lambda x: x["hybrid_score"], reverse=True)
    return combined[:top_k]


def main() -> None:
    args = build_parser().parse_args()

    manifest = read_latest_manifest(root_dir=args.artifacts_root)

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

    if args.mode == "lexical":
        results = lexical_artifacts.index.search(query=args.query, top_k=args.top_k)
        print_lexical_results(args.query, results)
        return

    model_name = dense_artifacts.meta["model_name"]

    if args.mode == "dense":
        results = dense_search(
            query=args.query,
            documents=documents,
            embeddings=dense_artifacts.embeddings,
            ids=dense_artifacts.ids,
            model_name=model_name,
            top_k=args.top_k,
        )
        print_dense_results(args.query, results)
        return

    if args.mode == "hybrid":
        hybrid_results = hybrid_search(
            query=args.query,
            documents=documents,
            lexical_index=lexical_artifacts.index,
            dense_embeddings=dense_artifacts.embeddings,
            dense_ids=dense_artifacts.ids,
            model_name=model_name,
            top_k=args.top_k,
        )

        if args.rank:
            ranked_results = rank_results(
                hybrid_results,
                retrieval_score_field="hybrid_score",
                retrieval_weight=0.60,
                recency_weight=0.20,
                source_support_weight=0.10,
                metadata_quality_weight=0.10,
            )
            print_ranked_results(args.query, ranked_results)
            return

        print_hybrid_results(args.query, hybrid_results)
        return

    raise ValueError(f"Unsupported mode: {args.mode}")


if __name__ == "__main__":
    main()