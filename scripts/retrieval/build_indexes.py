from __future__ import annotations

import argparse

from radar_core.retrieval.builders import build_retrieval_artifacts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and persist retrieval artifacts for ML Research Radar.")
    parser.add_argument(
        "--corpus-path",
        default="data/analytics/reconciled/canonical_documents.jsonl",
        help="Path to canonical corpus jsonl.",
    )
    parser.add_argument(
        "--artifacts-root",
        default="artifacts/retrieval",
        help="Root directory for retrieval artifacts.",
    )
    parser.add_argument(
        "--model-name",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="SentenceTransformer model name for dense embeddings.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Embedding batch size.",
    )
    parser.add_argument(
        "--no-write-latest",
        action="store_true",
        help="Do not overwrite artifacts/retrieval/manifests/latest.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    manifest = build_retrieval_artifacts(
        corpus_path=args.corpus_path,
        root_dir=args.artifacts_root,
        model_name=args.model_name,
        batch_size=args.batch_size,
        write_latest=not args.no_write_latest,
    )

    print("[OK] Retrieval artifacts built successfully")
    print(f"build_id:              {manifest.build_id}")
    print(f"created_at:            {manifest.created_at}")
    print(f"corpus_path:           {manifest.corpus_path}")
    print(f"corpus_doc_count:      {manifest.corpus_doc_count}")
    print(f"corpus_fingerprint:    {manifest.corpus_fingerprint}")
    print(f"lexical_index_path:    {manifest.lexical_index_path}")
    print(f"lexical_ids_path:      {manifest.lexical_ids_path}")
    print(f"dense_embeddings_path: {manifest.dense_embeddings_path}")
    print(f"dense_ids_path:        {manifest.dense_ids_path}")
    print(f"dense_meta_path:       {manifest.dense_meta_path}")
    print(f"embedding_model_name:  {manifest.embedding_model_name}")


if __name__ == "__main__":
    main()
