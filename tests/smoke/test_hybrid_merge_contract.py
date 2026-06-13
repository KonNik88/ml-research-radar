from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from radar_core.retrieval.hybrid_merge import (
    merge_hybrid_candidate_scores,
    minmax_normalize_scores,
)

from scripts.evaluation.run_search_quality_controlled_experiments import (
    build_hybrid_candidates_from_cache,
    minmax_normalize as controlled_minmax_normalize,
)
from services.api.search_service import (
    _candidate_pool_size,
    _hybrid_search_with_model,
    _minmax_normalize as api_minmax_normalize,
)


class FakeLexicalIndex:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = list(rows)
        self.calls: list[dict[str, Any]] = []

    def search(
        self,
        query: str,
        top_k: int,
    ) -> list[Any]:
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
            }
        )
        return self.rows[:top_k]


class FakeEmbeddingModel:
    def __init__(
        self,
        query_vector: np.ndarray,
    ) -> None:
        self.query_vector = np.asarray(
            query_vector,
            dtype=np.float32,
        )
        self.calls: list[dict[str, Any]] = []

    def encode(
        self,
        texts: list[str],
        *,
        convert_to_numpy: bool,
        normalize_embeddings: bool,
    ) -> np.ndarray:
        self.calls.append(
            {
                "texts": list(texts),
                "convert_to_numpy": convert_to_numpy,
                "normalize_embeddings": normalize_embeddings,
            }
        )

        return np.asarray(
            [self.query_vector],
            dtype=np.float32,
        )


def make_document(
    canonical_id: str,
    *,
    title: str | None = None,
    year: int = 2026,
    source_count: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        canonical_id=canonical_id,
        title=title or f"Paper {canonical_id}",
        year=year,
        doi=f"10.0000/{canonical_id}",
        source_count=source_count,
    )


def make_lexical_result(
    canonical_id: str,
    score: float,
) -> SimpleNamespace:
    return SimpleNamespace(
        canonical_id=canonical_id,
        score=float(score),
    )


def candidate_ids(
    rows: list[dict[str, Any]],
) -> list[str]:
    return [
        str(row["canonical_id"])
        for row in rows
    ]


def assert_candidate_rows_equal(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
) -> None:
    assert candidate_ids(left) == candidate_ids(right)
    assert len(left) == len(right)

    for left_row, right_row in zip(left, right):
        assert left_row["canonical_id"] == right_row["canonical_id"]

        for field in (
            "lexical_score",
            "dense_score",
            "hybrid_score",
        ):
            assert left_row[field] == pytest.approx(
                right_row[field],
                abs=1e-7,
            )

        assert left_row["title"] == right_row["title"]
        assert left_row["year"] == right_row["year"]
        assert left_row["doi"] == right_row["doi"]
        assert left_row["source_count"] == right_row["source_count"]
        assert left_row["document"] is right_row["document"]


@pytest.mark.parametrize(
    ("score_map", "expected"),
    [
        ({}, {}),
        ({"a": 7.0}, {"a": 1.0}),
        (
            {"a": 5.0, "b": 5.0},
            {"a": 1.0, "b": 1.0},
        ),
        (
            {"a": 1.0, "b": 2.0, "c": 3.0},
            {"a": 0.0, "b": 0.5, "c": 1.0},
        ),
        (
            {"a": -2.0, "b": 0.0, "c": 2.0},
            {"a": 0.0, "b": 0.5, "c": 1.0},
        ),
    ],
)
def test_existing_minmax_implementations_are_equivalent(
    score_map: dict[str, float],
    expected: dict[str, float],
) -> None:
    api_result = api_minmax_normalize(score_map)
    controlled_result = controlled_minmax_normalize(score_map)

    assert api_result == pytest.approx(expected)
    assert controlled_result == pytest.approx(expected)
    assert api_result == pytest.approx(controlled_result)

    shared_result = minmax_normalize_scores(
        score_map
    )

    assert shared_result == pytest.approx(expected)
    assert api_result == pytest.approx(
        shared_result
    )
    assert controlled_result == pytest.approx(
        shared_result
    )


@pytest.mark.parametrize(
    (
        "requested_top_k",
        "offset",
        "corpus_size",
        "expected",
    ),
    [
        (5, 0, 1_000, 50),
        (10, 0, 1_000, 50),
        (20, 0, 1_000, 100),
        (10, 80, 1_000, 90),
        (20, 0, 75, 75),
        (10, 0, 30, 30),
    ],
)
def test_public_candidate_pool_policy(
    requested_top_k: int,
    offset: int,
    corpus_size: int,
    expected: int,
) -> None:
    assert (
        _candidate_pool_size(
            requested_top_k=requested_top_k,
            offset=offset,
            corpus_size=corpus_size,
        )
        == expected
    )


def test_public_and_controlled_hybrid_merge_are_equivalent(
) -> None:
    documents = [
        make_document("a"),
        make_document("b"),
        make_document("c"),
    ]

    lexical_index = FakeLexicalIndex(
        [
            make_lexical_result("a", 4.0),
            make_lexical_result("b", 2.0),
        ]
    )

    embedding_model = FakeEmbeddingModel(
        np.asarray([1.0, 0.0], dtype=np.float32)
    )

    dense_embeddings = np.asarray(
        [
            [0.8, 0.0],
            [0.2, 0.0],
        ],
        dtype=np.float32,
    )
    dense_ids = ["b", "c"]

    shared_score_rows = (
        merge_hybrid_candidate_scores(
            lexical_candidates=[
                {
                    "canonical_id": "a",
                    "score": 4.0,
                },
                {
                    "canonical_id": "b",
                    "score": 2.0,
                },
            ],
            dense_candidates=[
                {
                    "canonical_id": "b",
                    "score": 0.8,
                },
                {
                    "canonical_id": "c",
                    "score": 0.2,
                },
            ],
            lexical_weight=0.55,
            dense_weight=0.45,
        )
    )

    assert candidate_ids(
        shared_score_rows
    ) == ["a", "b", "c"]

    assert shared_score_rows[0][
        "hybrid_score"
    ] == pytest.approx(0.55)

    assert shared_score_rows[1][
        "hybrid_score"
    ] == pytest.approx(0.45)

    assert shared_score_rows[2][
        "hybrid_score"
    ] == pytest.approx(0.0)

    public_rows, public_timings = _hybrid_search_with_model(
        query="hybrid retrieval",
        documents=documents,
        lexical_index=lexical_index,
        dense_embeddings=dense_embeddings,
        dense_ids=dense_ids,
        embedding_model=embedding_model,
        top_k=3,
        lexical_weight=0.55,
        dense_weight=0.45,
    )

    runtime = SimpleNamespace(
        documents=documents,
    )
    query_cache = {
        "lexical_candidates": [
            {
                "canonical_id": "a",
                "score": 4.0,
            },
            {
                "canonical_id": "b",
                "score": 2.0,
            },
        ],
        "dense_candidates": [
            {
                "canonical_id": "b",
                "score": 0.8,
            },
            {
                "canonical_id": "c",
                "score": 0.2,
            },
        ],
    }

    controlled_rows, controlled_timings = (
        build_hybrid_candidates_from_cache(
            runtime=runtime,
            query_cache=query_cache,
            candidate_k=3,
            lexical_weight=0.55,
            dense_weight=0.45,
        )
    )

    assert candidate_ids(public_rows) == ["a", "b", "c"]

    assert public_rows[0]["hybrid_score"] == pytest.approx(
        0.55
    )
    assert public_rows[1]["hybrid_score"] == pytest.approx(
        0.45
    )
    assert public_rows[2]["hybrid_score"] == pytest.approx(
        0.0
    )

    assert public_rows[0]["lexical_score"] == pytest.approx(
        4.0
    )
    assert public_rows[0]["dense_score"] == pytest.approx(
        0.0
    )

    assert public_rows[1]["lexical_score"] == pytest.approx(
        2.0
    )
    assert public_rows[1]["dense_score"] == pytest.approx(
        0.8,
        abs=1e-7,
    )

    assert_candidate_rows_equal(
        public_rows,
        controlled_rows,
    )

    assert set(public_timings) == {
        "lexical_ms",
        "dense_ms",
        "hybrid_merge_ms",
    }
    assert set(controlled_timings) == {
        "hybrid_merge_ms",
    }

    assert lexical_index.calls == [
        {
            "query": "hybrid retrieval",
            "top_k": 3,
        }
    ]

    assert embedding_model.calls == [
        {
            "texts": ["hybrid retrieval"],
            "convert_to_numpy": True,
            "normalize_embeddings": True,
        }
    ]


def test_current_public_merge_normalizes_before_missing_document_skip(
) -> None:
    documents = [
        make_document("a"),
        make_document("b"),
    ]

    lexical_index = FakeLexicalIndex(
        [
            make_lexical_result("missing", 10.0),
            make_lexical_result("a", 4.0),
        ]
    )

    embedding_model = FakeEmbeddingModel(
        np.asarray([1.0, 0.0], dtype=np.float32)
    )

    dense_embeddings = np.asarray(
        [
            [1.0, 0.0],
        ],
        dtype=np.float32,
    )

    rows, _ = _hybrid_search_with_model(
        query="legacy hydration behavior",
        documents=documents,
        lexical_index=lexical_index,
        dense_embeddings=dense_embeddings,
        dense_ids=["b"],
        embedding_model=embedding_model,
        top_k=3,
        lexical_weight=0.55,
        dense_weight=0.45,
    )

    # The missing lexical candidate participates in score
    # normalization and is skipped only during hydration.
    # This is characterization of the current public behavior,
    # not an endorsement of that behavior.
    assert candidate_ids(rows) == ["b", "a"]

    assert rows[0]["hybrid_score"] == pytest.approx(
        0.45
    )
    assert rows[1]["hybrid_score"] == pytest.approx(
        0.0
    )