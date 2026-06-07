from __future__ import annotations

import numpy as np
import pytest

from radar_core.retrieval.parity import (
    audit_qdrant_mapping,
    build_mismatch_details,
    check_repeat_determinism,
    classify_profile_difference,
    compare_ranked_results,
    exact_file_dense_search,
    query_vector_metadata,
    file_backend_result_to_rows,
    qdrant_backend_result_to_rows,
)
from radar_core.retrieval.dense_backend import (
    DenseSearchBackendInfo,
    DenseSearchBackendResult,
    DenseSearchCandidate,
)

def _row(
    canonical_id: str,
    rank: int,
    score: float,
    *,
    dense_index: int | None = None,
    build_id: str = "build-1",
) -> dict:
    index = rank - 1 if dense_index is None else dense_index
    return {
        "rank": rank,
        "point_id": index,
        "canonical_id": canonical_id,
        "dense_index": index,
        "score": score,
        "build_id": build_id,
        "payload": {
            "canonical_id": canonical_id,
            "dense_index": index,
            "build_id": build_id,
        },
    }


def test_exact_file_dense_search_uses_full_descending_order() -> None:
    embeddings = np.asarray(
        [
            [1.0, 0.0],
            [0.0, 1.0],
            [0.8, 0.2],
        ],
        dtype=np.float32,
    )
    query = np.asarray([1.0, 0.0], dtype=np.float32)

    rows = exact_file_dense_search(
        embeddings=embeddings,
        ids=["a", "b", "c"],
        query_vector=query,
        limit=3,
    )

    assert [row["canonical_id"] for row in rows] == ["a", "c", "b"]
    assert [row["rank"] for row in rows] == [1, 2, 3]
    assert rows[0]["score"] == 1.0


def test_exact_file_dense_search_rejects_dimension_mismatch() -> None:
    embeddings = np.zeros((3, 2), dtype=np.float32)
    query = np.zeros(3, dtype=np.float32)

    try:
        exact_file_dense_search(
            embeddings=embeddings,
            ids=["a", "b", "c"],
            query_vector=query,
            limit=2,
        )
    except ValueError as exc:
        assert "query dimension" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_compare_ranked_results_exact_match() -> None:
    reference = [_row("a", 1, 0.9), _row("b", 2, 0.8)]
    candidate = [_row("a", 1, 0.9), _row("b", 2, 0.8)]

    result = compare_ranked_results(
        reference_rows=reference,
        candidate_rows=candidate,
        top_k=2,
    )

    assert result["overlap_count"] == 2
    assert result["overlap_ratio"] == 1.0
    assert result["exact_same_order"] is True
    assert result["same_set"] is True
    assert result["reference_only"] == []
    assert result["candidate_only"] == []


def test_compare_ranked_results_same_set_different_order() -> None:
    reference = [_row("a", 1, 0.9), _row("b", 2, 0.8)]
    candidate = [_row("b", 1, 0.8), _row("a", 2, 0.9)]

    result = compare_ranked_results(
        reference_rows=reference,
        candidate_rows=candidate,
        top_k=2,
    )

    assert result["overlap_ratio"] == 1.0
    assert result["same_set"] is True
    assert result["exact_same_order"] is False


def test_mismatch_detection_is_automatic_and_preserves_reference_rank() -> None:
    reference = [
        _row("arbitrary-a", 1, 0.9),
        _row("arbitrary-b", 2, 0.8),
        _row("arbitrary-c", 3, 0.7),
    ]
    candidate = [
        _row("arbitrary-a", 1, 0.9),
        _row("arbitrary-c", 2, 0.7),
        _row("arbitrary-d", 3, 0.6),
    ]

    comparison = compare_ranked_results(
        reference_rows=reference,
        candidate_rows=candidate,
        top_k=3,
    )
    details = build_mismatch_details(
        comparison=comparison,
        reference_rows=reference,
        candidate_rows=candidate,
    )

    assert comparison["reference_only"] == ["arbitrary-b"]
    assert comparison["candidate_only"] == ["arbitrary-d"]
    assert details["best_missed_reference_rank"] == 2
    assert details["reference_only"][0]["reference_score"] == 0.8
    assert details["candidate_only"][0]["reference_rank"] is None


def test_mismatch_details_find_candidate_reference_rank_in_internal_window() -> None:
    reference = [
        _row("a", 1, 0.9),
        _row("b", 2, 0.8),
        _row("c", 3, 0.7),
        _row("replacement", 4, 0.6),
    ]
    candidate = [
        _row("a", 1, 0.9),
        _row("c", 2, 0.7),
        _row("replacement", 3, 0.6),
    ]

    comparison = compare_ranked_results(
        reference_rows=reference,
        candidate_rows=candidate,
        top_k=3,
    )
    details = build_mismatch_details(
        comparison=comparison,
        reference_rows=reference,
        candidate_rows=candidate,
    )

    assert details["candidate_only"][0]["reference_rank"] == 4
    assert details["pairwise_reference_score_gaps"][0]["reference_score_gap"] == pytest.approx(0.2)


def test_mapping_audit_passes_valid_rows() -> None:
    rows = [
        _row("a", 1, 0.9, dense_index=0),
        _row("b", 2, 0.8, dense_index=1),
    ]

    audit = audit_qdrant_mapping(
        rows=rows,
        ids=["a", "b"],
        expected_build_id="build-1",
    )

    assert audit["failure_count"] == 0
    assert audit["failures"] == []


def test_mapping_audit_detects_wrong_index_build_duplicate_and_non_finite_score() -> None:
    first = _row("a", 1, 0.9, dense_index=1, build_id="wrong-build")
    second = _row("a", 2, float("nan"), dense_index=0)
    second["point_id"] = 99

    audit = audit_qdrant_mapping(
        rows=[first, second],
        ids=["a", "b"],
        expected_build_id="build-1",
    )

    reasons = audit["reason_counts"]
    assert audit["failure_count"] == 2
    assert reasons["ids_dense_index_mismatch"] == 1
    assert reasons["build_id_mismatch"] == 1
    assert reasons["duplicate_canonical_id"] == 1
    assert reasons["point_id_dense_index_mismatch"] == 1
    assert reasons["non_finite_or_invalid_score"] == 1


def test_repeat_determinism_stable() -> None:
    run = [_row("a", 1, 0.9), _row("b", 2, 0.8)]

    result = check_repeat_determinism(
        repeated_runs=[run, [dict(row) for row in run], [dict(row) for row in run]],
        top_k=2,
    )

    assert result["stable_order"] is True
    assert result["stable_scores"] is True
    assert result["max_score_delta"] == 0.0


def test_repeat_determinism_detects_unstable_order() -> None:
    first = [_row("a", 1, 0.9), _row("b", 2, 0.8)]
    second = [_row("b", 1, 0.8), _row("a", 2, 0.9)]

    result = check_repeat_determinism(
        repeated_runs=[first, second],
        top_k=2,
    )

    assert result["stable_order"] is False


def test_classify_approximate_recall_difference() -> None:
    comparison = {"exact_same_order": False}
    exact_comparison = {"exact_same_order": True}
    mapping = {"failure_count": 0}
    determinism = {"stable_order": True}

    result = classify_profile_difference(
        comparison=comparison,
        exact_comparison=exact_comparison,
        mapping_audit=mapping,
        determinism=determinism,
        is_exact_profile=False,
    )

    assert result["classification"] == "approximate_search_recall_difference"
    assert result["severity"] == "warning"


def test_classify_blocks_when_exact_qdrant_differs() -> None:
    result = classify_profile_difference(
        comparison={"exact_same_order": False},
        exact_comparison={"exact_same_order": False},
        mapping_audit={"failure_count": 0},
        determinism={"stable_order": True},
        is_exact_profile=False,
    )

    assert result["classification"] == "exact_parity_failure"
    assert result["severity"] == "blocking"


def test_classify_blocks_mapping_defect_before_search_classification() -> None:
    result = classify_profile_difference(
        comparison={"exact_same_order": False},
        exact_comparison={"exact_same_order": True},
        mapping_audit={"failure_count": 1},
        determinism={"stable_order": True},
        is_exact_profile=False,
    )

    assert result["classification"] == "mapping_or_payload_defect"
    assert result["severity"] == "blocking"


def test_query_vector_metadata_is_reproducible() -> None:
    vector = np.asarray([0.6, 0.8], dtype=np.float32)

    first = query_vector_metadata(vector)
    second = query_vector_metadata(vector.copy())

    assert first == second
    assert first["dimension"] == 2
    assert first["dtype"] == "float32"
    assert first["norm"] == 1.0
    assert first["all_finite"] is True
    assert len(first["sha256"]) == 64

def test_file_backend_result_adapter_preserves_legacy_shape() -> None:
    result = DenseSearchBackendResult(
        candidates=(
            DenseSearchCandidate(
                canonical_id="a",
                score=0.9,
                rank=1,
                dense_index=4,
            ),
        ),
        backend=DenseSearchBackendInfo(
            backend_name="file",
            implementation="FileDenseBackend",
            build_id="build-1",
            ready=True,
        ),
    )

    rows = file_backend_result_to_rows(result)

    assert rows == [
        {
            "rank": 1,
            "canonical_id": "a",
            "dense_index": 4,
            "score": 0.9,
        }
    ]


def test_qdrant_backend_result_adapter_preserves_audit_fields() -> None:
    payload = {
        "canonical_id": "a",
        "dense_index": 4,
        "build_id": "build-1",
    }
    result = DenseSearchBackendResult(
        candidates=(
            DenseSearchCandidate(
                canonical_id="a",
                score=0.9,
                rank=1,
                dense_index=4,
                backend_point_id=4,
                backend_metadata={
                    "build_id": "build-1",
                    "payload": payload,
                },
            ),
        ),
        backend=DenseSearchBackendInfo(
            backend_name="qdrant",
            implementation="QdrantDenseBackend",
            build_id="build-1",
            ready=True,
        ),
    )

    rows = qdrant_backend_result_to_rows(result)

    assert rows == [
        {
            "rank": 1,
            "point_id": 4,
            "canonical_id": "a",
            "dense_index": 4,
            "build_id": "build-1",
            "score": 0.9,
            "payload": payload,
        }
    ]
