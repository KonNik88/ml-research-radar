from __future__ import annotations

from scripts.validation.check_qdrant_collection import (
    audit_payload_records,
    build_sample_indices,
    iter_batches,
)


def make_record(point_id: int, canonical_id: str, build_id: str = "build-1") -> dict:
    return {
        "id": point_id,
        "payload": {
            "canonical_id": canonical_id,
            "dense_index": point_id,
            "build_id": build_id,
        },
    }


def test_build_sample_indices_is_deterministic_unique_and_anchored():
    first = build_sample_indices(total_count=100, build_id="build-1", sample_size=12)
    second = build_sample_indices(total_count=100, build_id="build-1", sample_size=12)

    assert first == second
    assert len(first) == 12
    assert len(set(first)) == 12
    assert {0, 25, 50, 75, 99}.issubset(first)


def test_build_sample_indices_caps_at_total_count():
    assert build_sample_indices(total_count=3, build_id="x", sample_size=12) == [0, 1, 2]


def test_iter_batches_preserves_values():
    batches = list(iter_batches([0, 1, 2, 3, 4], batch_size=2))
    assert batches == [[0, 1], [2, 3], [4]]


def test_payload_audit_accepts_consistent_records():
    dense_ids = ["a", "b", "c"]
    records = [make_record(0, "a"), make_record(2, "c")]

    audit = audit_payload_records(
        expected_indices=[0, 2],
        records=records,
        dense_ids=dense_ids,
        expected_build_id="build-1",
    )

    assert audit["checked_count"] == 2
    assert audit["failure_count"] == 0
    assert audit["failures"] == []


def test_payload_audit_reports_missing_point_and_mapping_defects():
    dense_ids = ["a", "b", "c"]
    records = [
        {
            "id": 0,
            "payload": {
                "canonical_id": "wrong",
                "dense_index": 1,
                "build_id": "stale-build",
            },
        }
    ]

    audit = audit_payload_records(
        expected_indices=[0, 2],
        records=records,
        dense_ids=dense_ids,
        expected_build_id="build-1",
    )

    reasons = audit["reason_counts"]
    assert audit["failure_count"] == 2
    assert reasons["ids_dense_index_mismatch"] == 1
    assert reasons["expected_index_dense_index_mismatch"] == 1
    assert reasons["point_id_dense_index_mismatch"] == 1
    assert reasons["build_id_mismatch"] == 1
    assert reasons["missing_point"] == 1
