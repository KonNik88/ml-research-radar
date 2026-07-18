from __future__ import annotations

import json
from pathlib import Path

import pytest

from radar_core.utils.source_observation_identity import (
    build_source_observation_identity,
    normalize_source_name,
)
from scripts.validation.check_source_observation_identity_contract import (
    select_latest_primary_snapshot,
    validate_snapshots,
)


def test_same_paper_legacy_doc_id_produces_distinct_source_observation_ids() -> None:
    legacy_doc_id = "same-paper-doc-id"

    crossref = build_source_observation_identity(
        source="crossref",
        source_record_id="10.1234/example",
        legacy_doc_id=legacy_doc_id,
    )
    openalex = build_source_observation_identity(
        source="openalex",
        source_record_id="https://openalex.org/W123",
        legacy_doc_id=legacy_doc_id,
    )
    semantic_scholar = build_source_observation_identity(
        source="semantic_scholar",
        source_record_id="ABCDEF1234",
        legacy_doc_id=legacy_doc_id,
    )

    assert len(
        {
            crossref.source_observation_id,
            openalex.source_observation_id,
            semantic_scholar.source_observation_id,
        }
    ) == 3
    assert crossref.identity_basis == "source_record_id"
    assert openalex.identity_basis == "source_record_id"
    assert semantic_scholar.identity_basis == "source_record_id"


def test_identity_is_deterministic() -> None:
    kwargs = {
        "source": "openalex_alignment",
        "source_record_id": "https://openalex.org/w123",
        "legacy_doc_id": "legacy",
    }

    first = build_source_observation_identity(**kwargs)
    second = build_source_observation_identity(**kwargs)

    assert first == second
    assert first.normalized_source == "openalex"
    assert first.normalized_identity_value == "https://openalex.org/W123"


def test_crossref_doi_forms_normalize_to_same_identity() -> None:
    direct = build_source_observation_identity(
        source="crossref",
        source_record_id="10.1234/Example",
    )
    url = build_source_observation_identity(
        source="crossref_alignment",
        source_record_id="https://doi.org/10.1234/example/",
    )

    assert direct == url


def test_arxiv_url_and_id_normalize_to_same_versioned_identity() -> None:
    direct = build_source_observation_identity(
        source="arxiv",
        source_record_id="2401.01234v2",
    )
    url = build_source_observation_identity(
        source="arxiv",
        source_record_id="https://arxiv.org/abs/2401.01234v2",
    )

    assert direct == url
    assert direct.normalized_identity_value == "2401.01234v2"


def test_acl_url_and_anthology_id_normalize_to_same_identity() -> None:
    direct = build_source_observation_identity(
        source="acl_anthology",
        source_record_id="2024.acl-long.123",
    )
    url = build_source_observation_identity(
        source="acl",
        source_record_id="https://aclanthology.org/2024.ACL-LONG.123/",
    )

    assert direct == url


def test_basis_precedence_prefers_source_record_id() -> None:
    identity = build_source_observation_identity(
        source="semantic_scholar",
        source_record_id="paper-id",
        source_id="different-source-id",
        source_record_url="https://example.test/record",
        legacy_doc_id="legacy",
    )

    assert identity.identity_basis == "source_record_id"
    assert identity.normalized_identity_value == "paper-id"


def test_fallback_canonical_url_still_includes_source_family() -> None:
    openalex = build_source_observation_identity(
        source="openalex",
        canonical_url="https://doi.org/10.1234/example",
    )
    semantic_scholar = build_source_observation_identity(
        source="semantic_scholar",
        canonical_url="https://doi.org/10.1234/example",
    )

    assert openalex.identity_basis == "canonical_url"
    assert semantic_scholar.identity_basis == "canonical_url"
    assert openalex.source_observation_id != semantic_scholar.source_observation_id


def test_missing_identity_fails_closed() -> None:
    with pytest.raises(ValueError):
        build_source_observation_identity(source="openalex")

    with pytest.raises(ValueError):
        build_source_observation_identity(
            source="",
            source_record_id="W123",
        )


def test_source_aliases_are_canonicalized() -> None:
    assert normalize_source_name("OpenAlex Alignment") == "openalex"
    assert normalize_source_name("semantic-scholar-alignment") == "semantic_scholar"
    assert normalize_source_name("crossref_alignment") == "crossref"
    assert normalize_source_name("ACL") == "acl_anthology"


def test_latest_primary_snapshot_selection_excludes_latest_and_delta_files(
    tmp_path: Path,
) -> None:
    (tmp_path / "documents.20260101T000000Z.jsonl").write_text("{}\n", encoding="utf-8")
    expected = tmp_path / "documents.20260102T000000Z.jsonl"
    expected.write_text("{}\n", encoding="utf-8")
    (tmp_path / "documents.20260103T000000Z.new.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "documents_latest.jsonl").write_text("{}\n", encoding="utf-8")

    assert select_latest_primary_snapshot(tmp_path) == expected


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")


def test_validator_detects_legacy_collision_without_new_identity_collision(
    tmp_path: Path,
) -> None:
    shared_doc_id = "legacy-shared"
    paths = {
        "arxiv": tmp_path / "arxiv.jsonl",
        "openalex": tmp_path / "openalex.jsonl",
        "semantic_scholar": tmp_path / "semantic_scholar.jsonl",
        "crossref": tmp_path / "crossref.jsonl",
        "acl_anthology": tmp_path / "acl.jsonl",
    }

    _write_jsonl(
        paths["arxiv"],
        [{"source": "arxiv", "source_record_id": "2401.00001v1", "doc_id": "a"}],
    )
    _write_jsonl(
        paths["openalex"],
        [{"source": "openalex", "source_record_id": "https://openalex.org/W1", "doc_id": shared_doc_id}],
    )
    _write_jsonl(
        paths["semantic_scholar"],
        [{"source": "semantic_scholar", "source_record_id": "paper-1", "doc_id": shared_doc_id}],
    )
    _write_jsonl(
        paths["crossref"],
        [{"source": "crossref", "source_record_id": "10.1234/example", "doc_id": shared_doc_id}],
    )
    _write_jsonl(
        paths["acl_anthology"],
        [{"source": "acl_anthology", "source_record_id": "2024.acl-long.1", "doc_id": "acl"}],
    )

    report = validate_snapshots(paths, strict=True, sample_limit=5)
    summary = report["summary"]

    assert report["verdict"]["ok"] is True
    assert summary["rows_seen"] == 5
    assert summary["legacy_doc_id_cross_source_collision_count"] == 1
    assert summary["source_observation_id_cross_source_collision_count"] == 0
    assert summary.get("identity_conflict_count", 0) == 0
    assert summary.get("missing_identity_count", 0) == 0
