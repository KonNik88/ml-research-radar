from __future__ import annotations

import json
from pathlib import Path

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.ranking.scoring import rank_results


def _make_docs() -> list[CanonicalDocument]:
    corpus_path = Path("data/analytics/reconciled/canonical_documents.jsonl")
    assert corpus_path.exists(), f"Canonical corpus not found: {corpus_path}"

    docs: list[CanonicalDocument] = []
    with corpus_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            docs.append(CanonicalDocument.model_validate(payload))
            if len(docs) >= 3:
                break

    assert len(docs) == 3, "Need at least 3 canonical documents for ranking smoke test"
    return docs


def test_rank_results_smoke() -> None:
    docs = _make_docs()

    candidates = [
        {
            "canonical_id": docs[0].canonical_id,
            "hybrid_score": 0.90,
            "title": docs[0].title,
            "year": docs[0].year,
            "doi": docs[0].doi,
            "source_count": docs[0].source_count,
            "document": docs[0],
        },
        {
            "canonical_id": docs[1].canonical_id,
            "hybrid_score": 0.50,
            "title": docs[1].title,
            "year": docs[1].year,
            "doi": docs[1].doi,
            "source_count": docs[1].source_count,
            "document": docs[1],
        },
        {
            "canonical_id": docs[2].canonical_id,
            "hybrid_score": 0.10,
            "title": docs[2].title,
            "year": docs[2].year,
            "doi": docs[2].doi,
            "source_count": docs[2].source_count,
            "document": docs[2],
        },
    ]

    ranked = rank_results(candidates, retrieval_score_field="hybrid_score")

    assert len(ranked) == 3
    assert ranked[0].final_score >= ranked[1].final_score >= ranked[2].final_score
    assert ranked[0].canonical_id in {d.canonical_id for d in docs}
    assert 0.0 <= ranked[0].retrieval_score <= 1.0
    assert 0.0 <= ranked[0].metadata_quality_score <= 1.0