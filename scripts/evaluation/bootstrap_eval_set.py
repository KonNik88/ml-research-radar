from __future__ import annotations

import argparse
import json
from pathlib import Path

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.retrieval.embeddings import DenseRetriever
from radar_core.retrieval.hybrid import HybridRetriever
from radar_core.retrieval.lexical import build_bm25_index


DEFAULT_QUERIES = [
    "graph neural networks",
    "diffusion models",
    "self supervised learning",
    "transformer language models",
    "reinforcement learning",
]


def load_canonical_documents(path: Path) -> list[CanonicalDocument]:
    documents: list[CanonicalDocument] = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            documents.append(CanonicalDocument(**row))

    return documents


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Сколько top результатов брать из каждого retriever",
    )
    parser.add_argument(
        "--relevance",
        type=int,
        default=1,
        choices=[1, 2],
        help="Какую релевантность автоматически ставить найденным документам",
    )
    parser.add_argument(
        "--canonical-path",
        type=Path,
        default=Path("data/analytics/reconciled/canonical_documents.jsonl"),
        help="Путь к canonical documents",
    )
    parser.add_argument(
        "--queries-path",
        type=Path,
        default=Path("data/eval/queries.jsonl"),
        help="Куда сохранять queries.jsonl",
    )
    parser.add_argument(
        "--qrels-path",
        type=Path,
        default=Path("data/eval/qrels.jsonl"),
        help="Куда сохранять qrels.jsonl",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    documents = load_canonical_documents(args.canonical_path)

    lexical_index = build_bm25_index(documents)

    dense_retriever = DenseRetriever()
    dense_retriever.build(documents)

    hybrid_retriever = HybridRetriever()
    hybrid_retriever.build(documents)

    query_rows: list[dict] = []
    qrels_rows: list[dict] = []

    for i, query_text in enumerate(DEFAULT_QUERIES, start=1):
        query_id = f"q{i}"

        query_rows.append(
            {
                "query_id": query_id,
                "text": query_text,
            }
        )

        pooled_ids: list[str] = []
        seen_ids: set[str] = set()

        lexical_results = lexical_index.search(query=query_text, top_k=args.top_k)
        dense_results = dense_retriever.search(query=query_text, top_k=args.top_k)
        hybrid_results = hybrid_retriever.search(query=query_text, top_k=args.top_k)

        for result in lexical_results:
            if result.canonical_id not in seen_ids:
                seen_ids.add(result.canonical_id)
                pooled_ids.append(result.canonical_id)

        for result in dense_results:
            if result.canonical_id not in seen_ids:
                seen_ids.add(result.canonical_id)
                pooled_ids.append(result.canonical_id)

        for result in hybrid_results:
            if result.canonical_id not in seen_ids:
                seen_ids.add(result.canonical_id)
                pooled_ids.append(result.canonical_id)

        for canonical_id in pooled_ids:
            qrels_rows.append(
                {
                    "query_id": query_id,
                    "canonical_id": canonical_id,
                    "relevance": args.relevance,
                }
            )

    write_jsonl(args.queries_path, query_rows)
    write_jsonl(args.qrels_path, qrels_rows)

    print(f"[OK] queries saved to: {args.queries_path}")
    print(f"[OK] qrels saved to: {args.qrels_path}")
    print(f"[OK] queries count: {len(query_rows)}")
    print(f"[OK] qrels count: {len(qrels_rows)}")


if __name__ == "__main__":
    main()