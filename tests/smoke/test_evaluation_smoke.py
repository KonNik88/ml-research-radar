
from radar_core.evaluation.metrics import ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank


def test_retrieval_metrics_smoke():
    ranked_ids = ['d1', 'd2', 'd3', 'd4']
    relevant_ids = {'d2', 'd4'}
    relevance_map = {'d2': 2, 'd4': 1}

    assert precision_at_k(ranked_ids, relevant_ids, 2) == 0.5
    assert recall_at_k(ranked_ids, relevant_ids, 2) == 0.5
    assert reciprocal_rank(ranked_ids, relevant_ids) == 0.5
    score = ndcg_at_k(ranked_ids, relevance_map, 4)
    assert 0.0 < score <= 1.0
