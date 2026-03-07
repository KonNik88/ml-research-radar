from __future__ import annotations

import argparse
import json
from pathlib import Path

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.retrieval.embeddings import DenseRetriever
from radar_core.retrieval.hybrid import HybridRetriever
from radar_core.retrieval.lexical import build_bm25_index


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
        "--canonical-path",
        type=Path,
        default=Path("data/analytics/reconciled/canonical_documents.jsonl"),
        help="Путь к canonical documents",
    )
    return parser


def print_lexical_results(query: str, results) -> None:
    print(f"[OK] lexical results for query='{query}'")
    for i, r in enumerate(results, start=1):
        print(f"{i:02d}. score={r.score:.4f} | year={r.year} | sources={r.source_count}")
        print(f"    title: {r.title}")
        print(f"    doi: {r.doi}")
        print(f"    categories: {', '.join(r.document.categories[:5]) if r.document.categories else '-'}")


def print_dense_results(query: str, results) -> None:
    print(f"[OK] dense results for query='{query}'")
    for i, r in enumerate(results, start=1):
        print(f"{i:02d}. score={r.score:.4f} | year={r.year} | sources={r.source_count}")
        print(f"    title: {r.title}")
        print(f"    doi: {r.doi}")
        print(f"    categories: {', '.join(r.document.categories[:5]) if r.document.categories else '-'}")


def print_hybrid_results(query: str, results) -> None:
    print(f"[OK] hybrid results for query='{query}'")
    for i, r in enumerate(results, start=1):
        print(
            f"{i:02d}. hybrid={r.hybrid_score:.4f} | lexical={r.lexical_score:.4f} "
            f"| dense={r.dense_score:.4f} | year={r.year} | sources={r.source_count}"
        )
        print(f"    title: {r.title}")
        print(f"    doi: {r.doi}")
        print(f"    categories: {', '.join(r.document.categories[:5]) if r.document.categories else '-'}")


def main() -> None:
    args = build_parser().parse_args()

    documents = load_canonical_documents(args.canonical_path)

    if args.mode == "lexical":
        index = build_bm25_index(documents)
        results = index.search(query=args.query, top_k=args.top_k)
        print_lexical_results(args.query, results)
        return

    if args.mode == "dense":
        retriever = DenseRetriever()
        retriever.build(documents)
        results = retriever.search(query=args.query, top_k=args.top_k)
        print_dense_results(args.query, results)
        return

    if args.mode == "hybrid":
        retriever = HybridRetriever()
        retriever.build(documents)
        results = retriever.search(query=args.query, top_k=args.top_k)
        print_hybrid_results(args.query, results)
        return

    raise ValueError(f"Unsupported mode: {args.mode}")


if __name__ == "__main__":
    main()