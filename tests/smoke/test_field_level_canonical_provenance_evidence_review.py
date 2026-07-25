from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from radar_core.contracts.document import NormalizedDocument
from radar_core.normalize.reconcile import reconcile_documents
from scripts.validation.build_field_level_canonical_provenance_evidence import (
    build_package,
)
from scripts.validation.check_field_level_canonical_provenance_evidence_review import (
    build_review_report,
    validate_review,
)


LEFT_TS = "20260724T140000Z"
RIGHT_TS = "20260724T140001Z"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_docs() -> list[NormalizedDocument]:
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


def _refresh_audit_manifest(root: Path) -> None:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = (
        "data_slice/canonical_documents.sample.jsonl",
        "data_slice/source_documents.sample.jsonl",
        "data_slice/canonical_source_links.sample.jsonl",
        "data_slice/unmatched_canonical_source_links.jsonl",
    )
    manifest["package_files_before_manifest_and_checksums"] = [
        {
            "path": relative,
            "sha256": _sha256(root / relative),
            "size_bytes": (root / relative).stat().st_size,
        }
        for relative in paths
    ]
    manifest["selection"]["selected_paper_count"] = len(
        _read_jsonl(root / "data_slice/canonical_documents.sample.jsonl")
    )
    manifest["source_evidence"]["matched_source_document_count"] = len(
        _read_jsonl(root / "data_slice/source_documents.sample.jsonl")
    )
    manifest["source_evidence"]["wanted_canonical_source_link_count"] = len(
        _read_jsonl(root / "data_slice/canonical_source_links.sample.jsonl")
    )
    manifest["source_evidence"]["matched_canonical_source_link_count"] = len(
        _read_jsonl(root / "data_slice/canonical_source_links.sample.jsonl")
    )
    unmatched_path = root / "data_slice/unmatched_canonical_source_links.jsonl"
    unmatched = _read_jsonl(unmatched_path) if unmatched_path.stat().st_size else []
    manifest["source_evidence"]["unmatched_canonical_source_link_count"] = len(unmatched)
    _write_json(manifest_path, manifest)


def _make_audit_package(tmp_path: Path) -> Path:
    root = tmp_path / "synthetic-audit-v0.1"
    docs = _source_docs()
    canonical = reconcile_documents(docs)[0]
    source_rows: list[dict] = []
    links: list[dict] = []
    for doc in docs:
        row = doc.model_dump(mode="json")
        row["_audit_canonical_ids"] = [canonical.canonical_id]
        source_rows.append(row)
        links.append(
            {
                "canonical_id": canonical.canonical_id,
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

    _write_jsonl(
        root / "data_slice/canonical_documents.sample.jsonl",
        [canonical.model_dump(mode="json")],
    )
    _write_jsonl(root / "data_slice/source_documents.sample.jsonl", source_rows)
    _write_jsonl(root / "data_slice/canonical_source_links.sample.jsonl", links)
    _write_jsonl(root / "data_slice/unmatched_canonical_source_links.jsonl", [])
    _write_json(
        root / "manifest.json",
        {
            "package_name": root.name,
            "status": "internal_review_only",
            "canonical_truth": False,
            "may_be_used_as_reconcile_input": False,
            "publication_ready": False,
            "selection": {"selected_paper_count": 1},
            "source_evidence": {
                "matched_source_document_count": 2,
                "wanted_canonical_source_link_count": 2,
                "matched_canonical_source_link_count": 2,
                "unmatched_canonical_source_link_count": 0,
            },
            "package_files_before_manifest_and_checksums": [],
        },
    )
    _refresh_audit_manifest(root)
    return root


def _zip_tree(root: Path, zip_path: Path) -> Path:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=f"{root.name}/{path.relative_to(root)}")
    return zip_path


def _make_pair(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    audit = _make_audit_package(tmp_path)
    audit_zip = _zip_tree(audit, tmp_path / "synthetic-audit.zip")
    left = build_package(
        audit_path=audit,
        output_root=tmp_path / "left-output",
        run_ts=LEFT_TS,
        strict=True,
    )
    right = build_package(
        audit_path=audit_zip,
        output_root=tmp_path / "right-output",
        run_ts=RIGHT_TS,
        strict=True,
    )
    return (
        audit,
        audit_zip,
        Path(left["run_dir"]),
        Path(left["zip_path"]),
        Path(right["run_dir"]),
    )


def _refresh_evidence_package(root: Path) -> None:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for filename in (
        "field_evidence.jsonl",
        "paper_summary.jsonl",
        "data_quality_summary.json",
        "README.md",
    ):
        manifest["content_files"][filename] = {
            "sha256": _sha256(root / filename),
            "size_bytes": (root / filename).stat().st_size,
        }
    _write_json(manifest_path, manifest)

    checksums = []
    for filename in (
        "field_evidence.jsonl",
        "paper_summary.jsonl",
        "data_quality_summary.json",
        "manifest.json",
        "README.md",
    ):
        checksums.append(f"{_sha256(root / filename)}  {filename}")
    (root / "checksums.txt").write_text(
        "\n".join(checksums) + "\n",
        encoding="utf-8",
    )


def test_review_accepts_directory_zip_semantic_parity(tmp_path: Path) -> None:
    audit, _, left, _, right = _make_pair(tmp_path)

    report = build_review_report(
        left_root=left,
        right_root=right,
        audit_root=audit,
    )

    assert report["verdict"]["ok"] is True
    assert report["verdict"]["semantic_determinism_confirmed"] is True
    assert report["verdict"]["directory_zip_input_parity_confirmed"] is True
    assert report["summary"]["paper_count"] == 1
    assert report["summary"]["field_record_count"] == 61
    assert report["summary"]["strategy_family_count"] == 14
    assert report["summary"]["semantic_file_difference_count"] == 0


def test_review_accepts_evidence_and_audit_zip_inputs(tmp_path: Path) -> None:
    _, audit_zip, _, left_zip, right = _make_pair(tmp_path)
    right_zip = _zip_tree(right, tmp_path / "right-evidence.zip")

    report = validate_review(
        left_package=left_zip,
        right_package=right_zip,
        audit_path=audit_zip,
        require_accepted_baseline=False,
        sample_limit=10,
    )

    assert report["verdict"]["ok"] is True
    assert report["summary"]["required_failed_count"] == 0


def test_review_detects_semantic_drift_even_when_package_is_valid(tmp_path: Path) -> None:
    audit, _, left, _, right = _make_pair(tmp_path)
    evidence_path = right / "field_evidence.jsonl"
    rows = _read_jsonl(evidence_path)
    target = next(row for row in rows if row["field_name"] == "title")
    target["selection_reason"] = "tampered but internally schema-valid"
    _write_jsonl(evidence_path, rows)
    _refresh_evidence_package(right)

    report = build_review_report(
        left_root=left,
        right_root=right,
        audit_root=audit,
    )

    assert report["base_validation"]["right"]["ok"] is True
    assert report["checks"]["semantic_file_hashes_match"] is False
    assert report["checks"]["record_rows_match_exactly"] is False
    assert report["verdict"]["ok"] is False


def test_review_detects_audit_package_identity_drift(tmp_path: Path) -> None:
    audit, _, left, _, right = _make_pair(tmp_path)
    manifest_path = right / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["inputs"]["audit_package_name"] = "different-audit-package"
    _write_json(manifest_path, manifest)
    _refresh_evidence_package(right)

    report = build_review_report(
        left_root=left,
        right_root=right,
        audit_root=audit,
    )

    assert report["base_validation"]["right"]["ok"] is True
    assert report["checks"]["both_runs_reference_same_audit_package"] is False
    assert report["checks"]["both_runs_reference_supplied_audit_package"] is False


def test_review_propagates_individual_package_failure(tmp_path: Path) -> None:
    audit, _, left, _, right = _make_pair(tmp_path)
    evidence_path = right / "field_evidence.jsonl"
    rows = _read_jsonl(evidence_path)
    rows[0]["strategy_kind"] = "runtime_default"
    _write_jsonl(evidence_path, rows)
    _refresh_evidence_package(right)

    report = build_review_report(
        left_root=left,
        right_root=right,
        audit_root=audit,
    )

    assert report["base_validation"]["right"]["ok"] is False
    assert report["checks"]["right_package_validator_ok"] is False
    assert report["verdict"]["ok"] is False


def test_review_detects_audit_observation_set_drift(tmp_path: Path) -> None:
    audit, _, left, _, right = _make_pair(tmp_path)
    changed_audit = tmp_path / "changed-audit"
    shutil.copytree(audit, changed_audit)
    source_path = changed_audit / "data_slice/source_documents.sample.jsonl"
    rows = _read_jsonl(source_path)
    _write_jsonl(source_path, rows[:1])
    _refresh_audit_manifest(changed_audit)

    report = build_review_report(
        left_root=left,
        right_root=right,
        audit_root=changed_audit,
    )

    assert report["checks"]["audit_observation_ids_match_both_runs"] is False
    assert report["checks"]["audit_counts_match_both_manifests"] is False
    assert report["verdict"]["ok"] is False


def test_accepted_baseline_mode_rejects_synthetic_counts(tmp_path: Path) -> None:
    audit, _, left, _, right = _make_pair(tmp_path)

    report = build_review_report(
        left_root=left,
        right_root=right,
        audit_root=audit,
        require_accepted_baseline=True,
    )

    assert report["verdict"]["ok"] is False
    assert report["checks"]["accepted_audit_package_name_exact"] is False
    assert report["checks"]["accepted_counts_exact_left"] is False
    assert report["checks"]["accepted_semantic_hashes_exact_left"] is False
