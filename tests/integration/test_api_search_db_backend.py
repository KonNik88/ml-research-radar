from __future__ import annotations

from services.api.search_service import run_search


class DummyDbStore:
    def count_search_documents(self, **kwargs):
        return 2

    def search_search_documents(self, **kwargs):
        return [
            {
                "canonical_id": "c1",
                "title": "Graph Neural Networks for Molecules",
                "abstract": "A graph neural network method",
                "authors": ["Alice"],
                "year": 2024,
                "categories": ["cs.LG"],
                "tags": ["cs.LG"],
                "source_count": 2,
                "unique_source_count": 2,
                "metadata_completeness_score": 0.8,
                "score": 35.0,
            },
            {
                "canonical_id": "c2",
                "title": "Older GNN Paper",
                "abstract": "Graph models",
                "authors": ["Bob"],
                "year": 2022,
                "categories": ["cs.LG"],
                "tags": ["cs.LG"],
                "source_count": 1,
                "unique_source_count": 1,
                "metadata_completeness_score": 0.5,
                "score": 20.0,
            },
        ]


class DummyRuntime:
    backend_mode = "db"
    db_store = DummyDbStore()


def test_run_search_db_lexical_supported() -> None:
    response = run_search(
        runtime=DummyRuntime(),
        query="graph neural",
        mode="lexical",
        top_k=2,
        rank=False,
        category="cs.LG",
    )

    assert response.mode == "lexical"
    assert response.build_id == "db-runtime"
    assert len(response.results) == 2


def test_run_search_db_dense_not_supported() -> None:
    try:
        run_search(
            runtime=DummyRuntime(),
            query="graph neural",
            mode="dense",
            top_k=2,
            rank=False,
        )
    except ValueError as exc:
        assert "not supported" in str(exc)
    else:
        raise AssertionError("Expected ValueError for dense mode in db backend")
