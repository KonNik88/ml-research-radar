from __future__ import annotations

import argparse
import json
from pathlib import Path

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.evaluation.datasets import build_qrels_map, load_eval_queries, load_qrels
from radar_core.evaluation.metrics import (
    mean_ndcg_at_k,
    mean_precision_at_k,
    mean_recall_at_k,
    mean_reciprocal_rank,
)
from radar_core.retrieval.lexical import build_bm25_index
from radar_core.retrieval.embeddings import DenseRetriever
from radar_core.retrieval.hybrid import HybridRetriever


def load_canonical_documents(path: Path) -> list[CanonicalDocument]:
    documents: list[CanonicalDocument] = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            documents.append(CanonicalDocument(**row))

    return documents


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["lexical", "dense", "hybrid"],
        required=True,
        help="Какой retrieval-режим оценивать",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Сколько документов учитывать в выдаче",
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
        help="Путь к eval queries",
    )
    parser.add_argument(
        "--qrels-path",
        type=Path,
        default=Path("data/eval/qrels.jsonl"),
        help="Путь к qrels",
    )
    return parser


def build_retriever(mode: str, documents: list[CanonicalDocument]):
    if mode == "lexical":
        return build_bm25_index(documents)

    if mode == "dense":
        retriever = DenseRetriever()
        retriever.build(documents)
        return retriever

    if mode == "hybrid":
        retriever = HybridRetriever()
        retriever.build(documents)
        return retriever

    raise ValueError(f"Unsupported mode: {mode}")


def _extract_canonical_id(result) -> str:
    if hasattr(result, "canonical_id"):
        return result.canonical_id

    if hasattr(result, "document") and hasattr(result.document, "canonical_id"):
        return result.document.canonical_id

    if isinstance(result, dict):
        if "canonical_id" in result:
            return result["canonical_id"]

        doc = result.get("document")
        if isinstance(doc, dict) and "canonical_id" in doc:
            return doc["canonical_id"]

        doc = result.get("doc")
        if isinstance(doc, dict):
            if "canonical_id" in doc:
                return doc["canonical_id"]
            nested = doc.get("document")
            if isinstance(nested, dict) and "canonical_id" in nested:
                return nested["canonical_id"]

    raise ValueError(f"Не удалось извлечь canonical_id из результата: {result!r}")


def search_ids(retriever, query: str, top_k: int) -> list[str]:
    results = retriever.search(query=query, top_k=top_k)
    return [_extract_canonical_id(r) for r in results]


def main() -> None:
    args = build_parser().parse_args()

    documents = load_canonical_documents(args.canonical_path)
    queries = load_eval_queries(args.queries_path)
    qrels = load_qrels(args.qrels_path)
    qrels_map = build_qrels_map(qrels)

    retriever = build_retriever(args.mode, documents)

    ranked_ids_by_query: dict[str, list[str]] = {}

    for query in queries:
        ranked_ids = search_ids(
            retriever=retriever,
            query=query.text,
            top_k=args.top_k,
        )
        ranked_ids_by_query[query.query_id] = ranked_ids

    p_at_k = mean_precision_at_k(ranked_ids_by_query, qrels_map, k=args.top_k)
    r_at_k = mean_recall_at_k(ranked_ids_by_query, qrels_map, k=args.top_k)
    mrr = mean_reciprocal_rank(ranked_ids_by_query, qrels_map)
    ndcg_at_k = mean_ndcg_at_k(ranked_ids_by_query, qrels_map, k=args.top_k)

    print(f"[OK] mode={args.mode}")
    print(f"[OK] queries={len(queries)}")
    print(f"[OK] top_k={args.top_k}")
    print(f"P@{args.top_k}:   {p_at_k:.4f}")
    print(f"R@{args.top_k}:   {r_at_k:.4f}")
    print(f"MRR:      {mrr:.4f}")
    print(f"nDCG@{args.top_k}: {ndcg_at_k:.4f}")


if __name__ == "__main__":
    main()