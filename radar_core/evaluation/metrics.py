from __future__ import annotations

import math
from typing import Mapping, Set


RelevanceInput = Mapping[str, int] | Set[str]


def _to_relevance_map(relevant: RelevanceInput) -> dict[str, int]:
    if isinstance(relevant, set):
        return {doc_id: 1 for doc_id in relevant}
    return dict(relevant)


def precision_at_k(ranked_ids: list[str], relevant: RelevanceInput, k: int) -> float:
    relevant_map = _to_relevance_map(relevant)

    if k <= 0:
        return 0.0

    top_k = ranked_ids[:k]
    if not top_k:
        return 0.0

    hits = sum(1 for doc_id in top_k if relevant_map.get(doc_id, 0) > 0)
    return hits / k


def recall_at_k(ranked_ids: list[str], relevant: RelevanceInput, k: int) -> float:
    relevant_map = _to_relevance_map(relevant)

    total_relevant = sum(1 for _, rel in relevant_map.items() if rel > 0)
    if total_relevant == 0:
        return 0.0

    top_k = ranked_ids[:k]
    hits = sum(1 for doc_id in top_k if relevant_map.get(doc_id, 0) > 0)
    return hits / total_relevant


def reciprocal_rank(ranked_ids: list[str], relevant: RelevanceInput) -> float:
    relevant_map = _to_relevance_map(relevant)

    for rank, doc_id in enumerate(ranked_ids, start=1):
        if relevant_map.get(doc_id, 0) > 0:
            return 1.0 / rank
    return 0.0


def dcg_at_k(ranked_ids: list[str], relevant: RelevanceInput, k: int) -> float:
    relevant_map = _to_relevance_map(relevant)

    dcg = 0.0
    for rank, doc_id in enumerate(ranked_ids[:k], start=1):
        rel = relevant_map.get(doc_id, 0)
        if rel <= 0:
            continue
        dcg += (2**rel - 1) / math.log2(rank + 1)

    return dcg


def idcg_at_k(relevant: RelevanceInput, k: int) -> float:
    relevant_map = _to_relevance_map(relevant)

    ideal_rels = sorted((rel for rel in relevant_map.values() if rel > 0), reverse=True)[:k]

    idcg = 0.0
    for rank, rel in enumerate(ideal_rels, start=1):
        idcg += (2**rel - 1) / math.log2(rank + 1)

    return idcg


def ndcg_at_k(ranked_ids: list[str], relevant: RelevanceInput, k: int) -> float:
    ideal = idcg_at_k(relevant, k)
    if ideal == 0.0:
        return 0.0

    actual = dcg_at_k(ranked_ids, relevant, k)
    return actual / ideal


def mean_precision_at_k(
    ranked_ids_by_query: dict[str, list[str]],
    qrels_map: dict[str, dict[str, int]],
    k: int,
) -> float:
    if not ranked_ids_by_query:
        return 0.0

    scores: list[float] = []
    for query_id, ranked_ids in ranked_ids_by_query.items():
        relevant_map = qrels_map.get(query_id, {})
        scores.append(precision_at_k(ranked_ids, relevant_map, k))

    return sum(scores) / len(scores) if scores else 0.0


def mean_recall_at_k(
    ranked_ids_by_query: dict[str, list[str]],
    qrels_map: dict[str, dict[str, int]],
    k: int,
) -> float:
    if not ranked_ids_by_query:
        return 0.0

    scores: list[float] = []
    for query_id, ranked_ids in ranked_ids_by_query.items():
        relevant_map = qrels_map.get(query_id, {})
        scores.append(recall_at_k(ranked_ids, relevant_map, k))

    return sum(scores) / len(scores) if scores else 0.0


def mean_reciprocal_rank(
    ranked_ids_by_query: dict[str, list[str]],
    qrels_map: dict[str, dict[str, int]],
) -> float:
    if not ranked_ids_by_query:
        return 0.0

    scores: list[float] = []
    for query_id, ranked_ids in ranked_ids_by_query.items():
        relevant_map = qrels_map.get(query_id, {})
        scores.append(reciprocal_rank(ranked_ids, relevant_map))

    return sum(scores) / len(scores) if scores else 0.0


def mean_ndcg_at_k(
    ranked_ids_by_query: dict[str, list[str]],
    qrels_map: dict[str, dict[str, int]],
    k: int,
) -> float:
    if not ranked_ids_by_query:
        return 0.0

    scores: list[float] = []
    for query_id, ranked_ids in ranked_ids_by_query.items():
        relevant_map = qrels_map.get(query_id, {})
        scores.append(ndcg_at_k(ranked_ids, relevant_map, k))

    return sum(scores) / len(scores) if scores else 0.0