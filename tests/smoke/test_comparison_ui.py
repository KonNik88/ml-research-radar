from __future__ import annotations

import pandas as pd
import pytest

from services.ui.comparison_ui import (
    COMPARISON_BASKET_KEY,
    COMPARISON_PAYLOAD_IDS_KEY,
    COMPARISON_PAYLOAD_KEY,
    MAX_COMPARISON_PAPERS,
    add_to_comparison_basket,
    artifact_rows,
    citation_rows,
    clear_comparison_basket,
    cluster_rows,
    comparison_basket,
    metadata_score_rows,
    pairwise_rows,
    remove_from_comparison_basket,
)


def _payload() -> dict:
    return {
        "schema_version": "paper_comparison_v0.1",
        "paper_count": 2,
        "papers": [
            {
                "canonical_id": "paper-a",
                "title": "Paper A",
                "authors": ["Ada", "Grace"],
                "year": 2025,
                "venue": None,
                "scores": {
                    "radar_score": 0.75,
                    "implementation_readiness_score": 0.0,
                    "source_confidence_score": None,
                    "citation_signal_score": 0.5,
                    "recency_score": 1.0,
                },
                "provenance": {"source_count": 0},
                "artifact_evidence": {
                    "has_code_artifact": False,
                    "has_dataset_artifact": True,
                    "has_model_artifact": None,
                    "has_demo_artifact": False,
                    "trusted_artifact_links_count": 0,
                    "artifact_types": ["code", "dataset"],
                    "github": {
                        "github_repo_count": 0,
                        "github_stars_max": 0,
                    },
                    "huggingface": {
                        "hf_model_count": None,
                        "hf_dataset_count": 1,
                    },
                },
                "citation_evidence": {
                    "canonical_cited_by_count": 0,
                    "canonical_references_count": None,
                    "feature_citation_count": 0,
                    "graph": {
                        "status": "available",
                        "outgoing_reference_count": 0,
                        "outgoing_resolved_reference_count": 0,
                        "outgoing_external_reference_count": 0,
                        "incoming_citation_count": 0,
                    },
                },
                "cluster": {
                    "status": "available",
                    "cluster_id": 0,
                    "rank_within_cluster": 1,
                    "similarity_to_centroid": 0.5,
                    "label_candidates": [],
                },
            },
            {
                "canonical_id": "paper-b",
                "title": "Paper B",
                "authors": [],
                "year": None,
                "scores": {},
                "provenance": {},
                "artifact_evidence": {},
                "citation_evidence": {"graph": {"status": "unavailable"}},
                "cluster": {"status": "paper_not_in_build"},
            },
        ],
        "pairwise": [
            {
                "left_canonical_id": "paper-a",
                "right_canonical_id": "paper-b",
                "semantic": {
                    "available": False,
                    "similarity": None,
                    "reason": "canonical_id_missing_from_dense_build",
                },
                "same_cluster": None,
                "left_references_right": False,
                "right_references_left": None,
                "dimensions": {},
            }
        ],
    }


def test_comparison_basket_is_ordered_unique_and_bounded() -> None:
    state: dict = {}

    assert add_to_comparison_basket(" paper-b ", state=state) == "added"
    assert add_to_comparison_basket("paper-a", state=state) == "added"
    assert add_to_comparison_basket("paper-b", state=state) == "already_selected"
    assert add_to_comparison_basket(" ", state=state) == "invalid"
    assert comparison_basket(state) == ["paper-b", "paper-a"]

    for index in range(3):
        assert add_to_comparison_basket(f"paper-{index}", state=state) == "added"

    assert len(comparison_basket(state)) == MAX_COMPARISON_PAPERS
    state[COMPARISON_PAYLOAD_KEY] = {"paper_count": 5}
    state[COMPARISON_PAYLOAD_IDS_KEY] = list(comparison_basket(state))
    assert add_to_comparison_basket("paper-six", state=state) == "full"
    assert state[COMPARISON_PAYLOAD_KEY] == {"paper_count": 5}


def test_basket_changes_invalidate_previous_comparison() -> None:
    state = {
        COMPARISON_BASKET_KEY: ["paper-a", "paper-b"],
        COMPARISON_PAYLOAD_KEY: {"paper_count": 2},
        COMPARISON_PAYLOAD_IDS_KEY: ["paper-a", "paper-b"],
    }

    assert add_to_comparison_basket("paper-c", state=state) == "added"
    assert state[COMPARISON_PAYLOAD_KEY] is None
    assert state[COMPARISON_PAYLOAD_IDS_KEY] is None

    state[COMPARISON_PAYLOAD_KEY] = {"paper_count": 3}
    state[COMPARISON_PAYLOAD_IDS_KEY] = list(comparison_basket(state))
    assert remove_from_comparison_basket("paper-b", state=state) is True
    assert comparison_basket(state) == ["paper-a", "paper-c"]
    assert state[COMPARISON_PAYLOAD_KEY] is None

    state[COMPARISON_PAYLOAD_KEY] = {"paper_count": 2}
    assert clear_comparison_basket(state=state) is True
    assert comparison_basket(state) == []
    assert state[COMPARISON_PAYLOAD_KEY] is None


def test_duplicate_and_missing_removal_are_idempotent() -> None:
    state = {
        COMPARISON_BASKET_KEY: ["paper-a", "paper-a", "", "paper-b"],
        COMPARISON_PAYLOAD_KEY: {"paper_count": 2},
        COMPARISON_PAYLOAD_IDS_KEY: ["paper-a", "paper-b"],
    }

    assert comparison_basket(state) == ["paper-a", "paper-b"]
    assert add_to_comparison_basket("paper-a", state=state) == "already_selected"
    assert remove_from_comparison_basket("missing", state=state) is False
    assert state[COMPARISON_PAYLOAD_KEY] == {"paper_count": 2}


def test_comparison_table_rows_keep_zero_false_and_unknown_distinct() -> None:
    payload = _payload()

    metadata = metadata_score_rows(payload)
    assert metadata[0]["implementation"] == "0.000"
    assert metadata[0]["sources"] == "0"
    assert metadata[1]["year"] == "—"

    artifacts = artifact_rows(payload)
    assert artifacts[0]["code"] == "no"
    assert artifacts[0]["dataset"] == "yes"
    assert artifacts[0]["model"] == "unknown"
    assert artifacts[0]["trusted links"] == "0"
    assert artifacts[0]["GitHub repos"] == "0"

    citations = citation_rows(payload)
    assert citations[0]["canonical cited by"] == "0"
    assert citations[0]["canonical references"] == "—"
    assert citations[0]["outgoing"] == "0"

    clusters = cluster_rows(payload)
    assert clusters[0]["cluster"] == "0"
    assert clusters[1]["cluster"] == "—"


def test_citation_rows_keep_unknown_and_zero_arrow_safe() -> None:
    payload = _payload()
    rows = citation_rows(payload)

    assert rows[0]["canonical cited by"] == "0"
    assert rows[1]["canonical cited by"] == "—"
    assert all(isinstance(row["canonical cited by"], str) for row in rows)

    frame = pd.DataFrame(rows)
    assert frame["canonical cited by"].tolist() == ["0", "—"]

    pyarrow = pytest.importorskip("pyarrow")
    for display_rows in [
        metadata_score_rows(payload),
        artifact_rows(payload),
        citation_rows(payload),
        cluster_rows(payload),
    ]:
        pyarrow.Table.from_pandas(
            pd.DataFrame(display_rows),
            preserve_index=False,
        )


def test_pairwise_rows_label_unavailable_and_unknown_evidence() -> None:
    row = pairwise_rows(_payload())[0]

    assert row["left"] == "Paper A"
    assert row["right"] == "Paper B"
    assert row["semantic similarity"] == "unavailable"
    assert row["semantic caveat"] == "canonical_id_missing_from_dense_build"
    assert row["same cluster"] == "unknown"
    assert row["left references right"] == "no"
    assert row["right references left"] == "unknown"