from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.retrieval.similarity import (
    DEFAULT_CANONICAL_PATH,
    load_canonical_map,
    load_similarity_artifacts,
    load_similarity_model,
    find_similar_by_canonical_id,
    search_by_text_query,
)


DEFAULT_SEED_ID = "703f82b2febc3d63de367180ac1a23e6"


def print_neighbors(title: str, rows: list[dict], limit: int = 10) -> None:
    print(f"\n=== {title} ===")
    for i, row in enumerate(rows[:limit], start=1):
        print(
            f"{i:02d}. score={row['score']:.4f} | year={row.get('year')} | "
            f"canonical_id={row.get('canonical_id')}"
        )
        print(f"    title: {row.get('title')}")
        if row.get("doi"):
            print(f"    doi: {row.get('doi')}")
        if row.get("arxiv_id"):
            print(f"    arxiv_id: {row.get('arxiv_id')}")
        if row.get("categories"):
            print(f"    categories: {row.get('categories')}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a small manual demo for abstract embedding similarity."
    )
    parser.add_argument(
        "--seed-id",
        default=DEFAULT_SEED_ID,
        help="Canonical document id to inspect for nearest neighbors.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="How many results to show per demo block.",
    )
    parser.add_argument(
        "--canonical-path",
        type=Path,
        default=DEFAULT_CANONICAL_PATH,
        help="Path to canonical JSONL.",
    )
    parser.add_argument(
        "--query",
        action="append",
        default=None,
        help="Optional text query to run. Can be passed multiple times.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    artifacts = load_similarity_artifacts()
    canonical_map = load_canonical_map(args.canonical_path)

    print("[INFO] similarity artifacts loaded")
    print(f"[INFO] model_name={artifacts.model_name}")
    print(f"[INFO] text_builder={artifacts.text_builder}")
    print(f"[INFO] normalize_embeddings={artifacts.normalize_embeddings}")
    print(f"[INFO] count={artifacts.count}")
    print(f"[INFO] embedding_dim={artifacts.embedding_dim}")

    if args.seed_id not in canonical_map:
        raise KeyError(f"Seed canonical_id not found in canonical corpus: {args.seed_id}")

    seed_row = canonical_map[args.seed_id]
    print("\n[INFO] seed document")
    print(f"[INFO] canonical_id={args.seed_id}")
    print(f"[INFO] title={seed_row.get('title')}")
    print(f"[INFO] year={seed_row.get('year')}")

    neighbors = find_similar_by_canonical_id(
        args.seed_id,
        artifacts=artifacts,
        canonical_map=canonical_map,
        top_k=args.top_k,
        include_query_doc=False,
    )
    print_neighbors("Nearest neighbors by canonical_id", neighbors, limit=args.top_k)

    queries = args.query or [
        "graph neural networks for molecules",
        "time series forecasting with recurrent autoencoders",
        "video interaction and media retrieval",
    ]

    model = load_similarity_model(artifacts.model_name)

    for query_text in queries:
        results = search_by_text_query(
            query_text,
            model=model,
            artifacts=artifacts,
            canonical_map=canonical_map,
            top_k=args.top_k,
        )
        print_neighbors(f'Text query: "{query_text}"', results, limit=args.top_k)


if __name__ == "__main__":
    main()