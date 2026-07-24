from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from radar_core.contracts.document import NormalizedDocument
from radar_core.normalize.reconcile import reconcile_documents
from scripts.validation.build_field_level_canonical_provenance_evidence import (
    EvidenceBuildError,
    SCHEMA_VERSION,
    build_package,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _docs() -> list[NormalizedDocument]:
    return [
        NormalizedDocument(
            doc_id="shared-doc",
            canonical_url="https://arxiv.org/abs/2401.00001v1",
            content_hash="a",
            source="arxiv",
            source_id="2401.00001v1",
            source_record_id="2401.00001v1",
            source_record_url="https://arxiv.org/abs/2401.00001v1",
            doi="10.1234/example",
            arxiv_id="2401.00001v1",
            title="Equal length title A",
            abstract="short",
            authors=["Alice", "Bob"],
            year=2024,
            publication_date="2024-01-02T00:00:00Z",
            published_at="2024-01-02T00:00:00Z",
            updated_source_at="2024-02-01T00:00:00Z",
            categories=["cs.LG"],
            tags=["ML"],
            venue="Proceedings Example",
            journal="Lecture Notes in AI",
            publication_type="preprint",
            license="http://arxiv.org/licenses/nonexclusive-distrib/1.0/",
            open_access=True,
            is_open_access=True,
            is_preprint=True,
            cited_by_count=2,
            references_count=3,
            code_links=["https://github.com/example/repo"],
            has_code_link=True,
            pipeline_version="test",
        ),
        NormalizedDocument(
            doc_id="shared-doc",
            canonical_url="https://openalex.org/W1",
            content_hash="b",
            source="openalex",
            source_id="https://openalex.org/W1",
            source_record_id="https://openalex.org/W1",
            source_record_url="https://openalex.org/W1",
            doi="10.1234/example",
            arxiv_id="2401.00001",
            openalex_id="https://openalex.org/W1",
            title="Equal length title B",
            abstract="a substantially longer abstract",
            authors=["alice", "Carol"],
            year=2023,
            publication_date="2023-12-31T00:00:00Z",
            published_at="2024-01-01T00:00:00Z",
            updated_source_at="2024-03-01T00:00:00Z",
            categories=["Machine Learning"],
            tags=["ml"],
            venue="Proceedings Example",
            journal="Lecture Notes in Artificial Intelligence",
            publication_type="book-chapter",
            license="CC-BY-4.0",
            open_access=False,
            is_open_access=False,
            is_preprint=False,
            cited_by_count=8,
            references_count=7,
            dataset_links=["https://example.test/dataset"],
            has_dataset_link=True,
            pipeline_version="test",
        ),
    ]


def _make_audit_package(tmp_path: Path, *, unmatched: bool = False) -> Path:
    root = tmp_path / "audit"
    docs = _docs()
    canonical = reconcile_documents(docs)[0]
    canonical_id = canonical.canonical_id
    source_rows: list[dict] = []
    links: list[dict] = []
    for doc in docs:
        row = doc.model_dump(mode="json")
        row["_audit_canonical_ids"] = [canonical_id]
        source_rows.append(row)
        links.append(
            {
                "canonical_id": canonical_id,
                "source_family": doc.source,
                "source_link": next(
                    source.model_dump(mode="json")
                    for source in canonical.sources
                    if source.source == doc.source
                ),
                "matched": True,
                "resolved_doc_id": doc.doc_id,
                "match_basis": "source_record_id",
                "match_score": 90,
                "candidate_match_count": 1,
            }
        )

    _write_json(root / "manifest.json", {"package_name": "synthetic-audit"})
    _write_jsonl(
        root / "data_slice" / "canonical_documents.sample.jsonl",
        [canonical.model_dump(mode="json")],
    )
    _write_jsonl(root / "data_slice" / "source_documents.sample.jsonl", source_rows)
    _write_jsonl(root / "data_slice" / "canonical_source_links.sample.jsonl", links)
    _write_jsonl(
        root / "data_slice" / "unmatched_canonical_source_links.jsonl",
        [{"canonical_id": canonical_id}] if unmatched else [],
    )
    return root


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_builder_creates_complete_green_package(tmp_path: Path) -> None:
    audit = _make_audit_package(tmp_path)
    result = build_package(
        audit_path=audit,
        output_root=tmp_path / "output",
        run_ts="20260724T120000Z",
        strict=True,
    )

    assert result["ok"] is True
    assert result["counts"]["canonical_paper_count"] == 1
    assert result["counts"]["canonical_field_count"] == 61
    assert result["counts"]["field_evidence_record_count"] == 61
    assert result["counts"]["comparison_mismatch_count"] == 0
    assert Path(result["zip_path"]).is_file()


def test_builder_records_winner_union_and_normalization_trace(tmp_path: Path) -> None:
    audit = _make_audit_package(tmp_path)
    result = build_package(
        audit_path=audit,
        output_root=tmp_path / "output",
        run_ts="20260724T120001Z",
        strict=True,
    )
    rows = _read_jsonl(Path(result["run_dir"]) / "field_evidence.jsonl")
    by_field = {row["field_name"]: row for row in rows}

    assert by_field["abstract"]["canonical_value"] == "a substantially longer abstract"
    assert len(by_field["abstract"]["selected_source_observation_ids"]) == 1
    assert [item["value"] for item in by_field["authors"]["elements"]] == [
        "Alice",
        "Bob",
        "Carol",
    ]
    assert by_field["journal"]["canonical_value"] is None
    assert len(by_field["journal"]["selected_source_observation_ids"]) == 1
    assert by_field["journal"]["transformations"][0]["name"] == "normalize_venue_fields"
    assert by_field["license"]["canonical_value"] == "cc-by"
    assert by_field["is_preprint"]["canonical_value"] is False
    assert by_field["has_code_link"]["canonical_value"] is True


def test_builder_content_is_deterministic_across_run_timestamps(tmp_path: Path) -> None:
    audit = _make_audit_package(tmp_path)
    first = build_package(
        audit_path=audit,
        output_root=tmp_path / "first",
        run_ts="20260724T120002Z",
        strict=True,
    )
    second = build_package(
        audit_path=audit,
        output_root=tmp_path / "second",
        run_ts="20260724T120003Z",
        strict=True,
    )

    first_bytes = (Path(first["run_dir"]) / "field_evidence.jsonl").read_bytes()
    second_bytes = (Path(second["run_dir"]) / "field_evidence.jsonl").read_bytes()
    assert first_bytes == second_bytes


def test_builder_accepts_audit_zip(tmp_path: Path) -> None:
    audit = _make_audit_package(tmp_path)
    zip_path = tmp_path / "audit.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in audit.rglob("*"):
            if path.is_file():
                archive.write(path, arcname=f"synthetic-audit/{path.relative_to(audit)}")

    result = build_package(
        audit_path=zip_path,
        output_root=tmp_path / "output",
        run_ts="20260724T120004Z",
        strict=True,
    )
    assert result["ok"] is True
    assert result["counts"]["field_evidence_record_count"] == 61


def test_builder_fails_closed_on_unmatched_source_link(tmp_path: Path) -> None:
    audit = _make_audit_package(tmp_path, unmatched=True)
    with pytest.raises(EvidenceBuildError, match="unmatched canonical source links"):
        build_package(
            audit_path=audit,
            output_root=tmp_path / "output",
            run_ts="20260724T120005Z",
            strict=True,
        )


def test_builder_fails_closed_when_contributing_source_row_is_missing(tmp_path: Path) -> None:
    audit = _make_audit_package(tmp_path)
    source_path = audit / "data_slice" / "source_documents.sample.jsonl"
    rows = _read_jsonl(source_path)
    _write_jsonl(source_path, rows[:1])

    with pytest.raises(EvidenceBuildError, match="not found in audit data slice"):
        build_package(
            audit_path=audit,
            output_root=tmp_path / "output",
            run_ts="20260724T120006Z",
            strict=True,
        )


def test_runtime_defaults_are_explicitly_not_source_reconstructable(tmp_path: Path) -> None:
    audit = _make_audit_package(tmp_path)
    result = build_package(
        audit_path=audit,
        output_root=tmp_path / "output",
        run_ts="20260724T120007Z",
        strict=True,
    )
    rows = _read_jsonl(Path(result["run_dir"]) / "field_evidence.jsonl")
    runtime = [row for row in rows if row["field_name"] in {"created_at", "updated_record_at"}]

    assert len(runtime) == 2
    assert all(row["schema_version"] == SCHEMA_VERSION for row in runtime)
    assert all(row["comparison_status"] == "not_applicable" for row in runtime)
    assert all(row["reconstructability"] == "not_source_reconstructable" for row in runtime)
    assert all(not row["selected_source_observation_ids"] for row in runtime)
