from __future__ import annotations

from types import SimpleNamespace

import pytest

from radar_core.ranking.scoring import (
    compute_metadata_quality_score,
    compute_recency_score,
    compute_source_support_score,
    minmax_normalize,
    rank_results,
)


def _doc(**overrides):
    values = {
        "title": None,
        "abstract": None,
        "authors": [],
        "year": None,
        "doi": None,
        "primary_category": None,
        "categories": [],
        "tags": [],
        "venue": None,
        "journal": None,
        "publisher": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _candidate(
    canonical_id: str,
    score: float,
    *,
    year: int | None,
    source_count: int,
    document,
) -> dict:
    return {
        "canonical_id": canonical_id,
        "hybrid_score": score,
        "title": document.title,
        "year": year,
        "doi": document.doi,
        "source_count": source_count,
        "document": document,
    }


def test_minmax_normalize_scales_range() -> None:
    result = minmax_normalize({"a": 0.1, "b": 0.5, "c": 0.9})

    assert result == pytest.approx({"a": 0.0, "b": 0.5, "c": 1.0})


def test_minmax_normalize_constant_scores_become_one() -> None:
    result = minmax_normalize({"a": 0.5, "b": 0.5})

    assert result == {"a": 1.0, "b": 1.0}


@pytest.mark.parametrize(
    ("year", "min_year", "max_year", "expected"),
    [
        (None, 2020, 2024, 0.0),
        (2018, 2020, 2024, 0.0),
        (2020, 2020, 2024, 0.0),
        (2022, 2020, 2024, 0.5),
        (2024, 2020, 2024, 1.0),
        (2028, 2020, 2024, 1.0),
        (2022, 2022, 2022, 1.0),
    ],
)
def test_compute_recency_score_characterizes_current_bounds(
    year: int | None,
    min_year: int,
    max_year: int,
    expected: float,
) -> None:
    assert compute_recency_score(year, min_year, max_year) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("source_count", "max_source_count", "expected"),
    [
        (None, 3, 0.0),
        (0, 3, 0.0),
        (1, 3, 0.0),
        (2, 3, 0.5),
        (3, 3, 1.0),
        (5, 3, 1.0),
        (1, 1, 1.0),
    ],
)
def test_compute_source_support_score_characterizes_current_bounds(
    source_count: int | None,
    max_source_count: int,
    expected: float,
) -> None:
    assert compute_source_support_score(source_count, max_source_count) == pytest.approx(expected)


def test_metadata_quality_empty_and_complete_documents() -> None:
    empty = _doc()
    complete = _doc(
        title="Paper",
        abstract="Abstract",
        authors=["Author"],
        year=2024,
        doi="10.1000/example",
        primary_category="cs.LG",
        categories=["cs.LG"],
        tags=["ranking"],
        venue="Venue",
        journal="Journal",
        publisher="Publisher",
    )

    assert compute_metadata_quality_score(empty) == pytest.approx(0.0)
    assert compute_metadata_quality_score(complete) == pytest.approx(1.0)


def test_retrieval_only_profile_preserves_retrieval_order() -> None:
    candidates = [
        _candidate("a", 0.90, year=2020, source_count=1, document=_doc(title="A")),
        _candidate("b", 0.50, year=2024, source_count=4, document=_doc(title="B")),
        _candidate("c", 0.10, year=2022, source_count=2, document=_doc(title="C")),
    ]

    ranked = rank_results(
        candidates,
        retrieval_score_field="hybrid_score",
        retrieval_weight=1.0,
        recency_weight=0.0,
        source_support_weight=0.0,
        metadata_quality_weight=0.0,
    )

    assert [item.canonical_id for item in ranked] == ["a", "b", "c"]
    assert [item.final_score for item in ranked] == pytest.approx([1.0, 0.5, 0.0])


def test_current_weighted_formula_exposes_component_scores() -> None:
    complete = _doc(
        title="Complete",
        abstract="Abstract",
        authors=["Author"],
        year=2020,
        doi="10.1000/complete",
        primary_category="cs.LG",
        categories=["cs.LG"],
        tags=["ranking"],
        venue="Venue",
        journal="Journal",
        publisher="Publisher",
    )
    sparse = _doc(title=None)

    candidates = [
        _candidate("complete", 0.20, year=2020, source_count=1, document=complete),
        _candidate("sparse", 0.80, year=2024, source_count=3, document=sparse),
    ]

    ranked = rank_results(candidates, retrieval_score_field="hybrid_score")
    by_id = {item.canonical_id: item for item in ranked}

    assert by_id["complete"].retrieval_score == pytest.approx(0.0)
    assert by_id["complete"].recency_score == pytest.approx(0.0)
    assert by_id["complete"].source_support_score == pytest.approx(0.0)
    assert by_id["complete"].metadata_quality_score == pytest.approx(1.0)
    assert by_id["complete"].final_score == pytest.approx(0.10)

    assert by_id["sparse"].retrieval_score == pytest.approx(1.0)
    assert by_id["sparse"].recency_score == pytest.approx(1.0)
    assert by_id["sparse"].source_support_score == pytest.approx(1.0)
    assert by_id["sparse"].metadata_quality_score == pytest.approx(0.0)
    assert by_id["sparse"].final_score == pytest.approx(0.90)


def test_exact_final_score_ties_preserve_input_order() -> None:
    candidates = [
        _candidate("first", 0.5, year=2024, source_count=1, document=_doc()),
        _candidate("second", 0.5, year=2024, source_count=1, document=_doc()),
    ]

    ranked = rank_results(candidates, retrieval_score_field="hybrid_score")

    assert [item.canonical_id for item in ranked] == ["first", "second"]
    assert ranked[0].final_score == pytest.approx(ranked[1].final_score)


def test_candidate_pool_changes_relative_recency_and_source_support() -> None:
    target = _candidate(
        "target",
        0.5,
        year=2020,
        source_count=3,
        document=_doc(title="Target"),
    )

    small_pool = [
        target,
        _candidate("newer", 0.9, year=2024, source_count=1, document=_doc(title="Newer")),
    ]
    larger_pool = [
        target,
        _candidate("older", 0.1, year=2018, source_count=5, document=_doc(title="Older")),
        _candidate("newer", 0.9, year=2024, source_count=1, document=_doc(title="Newer")),
    ]

    small_target = {
        item.canonical_id: item
        for item in rank_results(small_pool, retrieval_score_field="hybrid_score")
    }["target"]
    larger_target = {
        item.canonical_id: item
        for item in rank_results(larger_pool, retrieval_score_field="hybrid_score")
    }["target"]

    assert small_target.recency_score == pytest.approx(0.0)
    assert larger_target.recency_score == pytest.approx(1.0 / 3.0)

    assert small_target.source_support_score == pytest.approx(1.0)
    assert larger_target.source_support_score == pytest.approx(0.5)
