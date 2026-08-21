from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.entities.build_scientific_entity_manual_review_evidence import (
    finalize_manual_review_evidence,
    prepare_manual_review_evidence,
)
from scripts.validation.check_scientific_entity_manual_review_evidence import (
    COMPLETED_CHECKSUM_FILES,
    PREPARED_CHECKSUM_FILES,
    main,
    validate_manual_review_evidence,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = (
    PROJECT_ROOT / "tests" / "fixtures" / "scientific_entity_manual_review_evidence_v0_1"
)
ANNOTATIONS_PATH = FIXTURE_DIR / "completed_annotations.jsonl"
REVIEW_ID = "scientific-entity-manual-review-fixture-v0.1"
GENERATED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)


def _build(tmp_path: Path) -> tuple[Path, Path]:
    prepared_root = tmp_path / "prepared"
    completed_root = tmp_path / "completed"
    prepare_manual_review_evidence(
        output_root=prepared_root,
        execute=True,
        generated_at_utc=GENERATED_AT,
    )
    prepared_dir = prepared_root / REVIEW_ID
    finalize_manual_review_evidence(
        prepared_dir=prepared_dir,
        annotations_path=ANNOTATIONS_PATH,
        annotator_ids=["synthetic-fixture-reviewer"],
        output_root=completed_root,
        execute=True,
        generated_at_utc=GENERATED_AT,
    )
    return prepared_dir, completed_root / REVIEW_ID


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )


def _rehash_checksums(directory: Path, filenames: set[str]) -> None:
    lines = [
        f"{hashlib.sha256((directory / filename).read_bytes()).hexdigest()}  {filename}"
        for filename in sorted(filenames)
    ]
    (directory / "checksums.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )


def _check_map(report: dict[str, object]) -> dict[str, bool]:
    return {
        row["name"]: row["ok"]  # type: ignore[index]
        for row in report["checks"]  # type: ignore[union-attr]
    }


def test_independent_validator_accepts_prepared_evidence(tmp_path: Path) -> None:
    prepared_dir, _ = _build(tmp_path)

    report = validate_manual_review_evidence(
        prepared_dir=prepared_dir,
        write_reports=False,
    )

    assert report["summary"]["ok"] is True
    assert report["summary"]["required_failed_count"] == 0
    assert report["summary"]["sample_document_count"] == 8
    assert report["summary"]["completed_review_present"] is False
    assert report["verdict"]["next_slice"] == (
        "complete_prediction_blind_manual_annotation_v0.1"
    )
    assert report["summary"]["total_checks"] >= 50


def test_independent_validator_accepts_completed_evidence(tmp_path: Path) -> None:
    prepared_dir, completed_dir = _build(tmp_path)

    report = validate_manual_review_evidence(
        prepared_dir=prepared_dir,
        completed_dir=completed_dir,
        write_reports=False,
    )

    assert report["summary"]["ok"] is True
    assert report["summary"]["required_failed_count"] == 0
    assert report["summary"]["reference_mention_count"] == 6
    assert report["summary"]["total_checks"] >= 100
    assert report["verdict"]["completed_review_valid"] is True
    assert report["verdict"]["automatic_review_approval"] is False
    assert report["verdict"]["next_slice"] == (
        "run_existing_scientific_entity_evaluation_harness_v0.1"
    )


def test_validator_writes_latest_and_history_reports(tmp_path: Path) -> None:
    prepared_dir, completed_dir = _build(tmp_path)
    report_dir = tmp_path / "reports"

    report = validate_manual_review_evidence(
        prepared_dir=prepared_dir,
        completed_dir=completed_dir,
        report_dir=report_dir,
        write_reports=True,
    )

    assert report["summary"]["ok"] is True
    assert (report_dir / "scientific_entity_manual_review_evidence_latest.json").is_file()
    assert (report_dir / "scientific_entity_manual_review_evidence_latest.md").is_file()
    assert len(list((report_dir / "history").glob("*.json"))) == 1
    assert len(list((report_dir / "history").glob("*.md"))) == 1


def test_validator_rejects_missing_prepared_file(tmp_path: Path) -> None:
    prepared_dir, _ = _build(tmp_path)
    (prepared_dir / "annotation_template.jsonl").unlink()

    report = validate_manual_review_evidence(
        prepared_dir=prepared_dir,
        write_reports=False,
    )

    assert report["summary"]["ok"] is False
    assert _check_map(report)["prepared_exact_file_layout"] is False


def test_validator_rejects_crlf_even_when_content_is_readable(tmp_path: Path) -> None:
    prepared_dir, _ = _build(tmp_path)
    readme = prepared_dir / "README.md"
    readme.write_bytes(readme.read_bytes().replace(b"\n", b"\r\n"))
    _rehash_checksums(prepared_dir, PREPARED_CHECKSUM_FILES)

    report = validate_manual_review_evidence(
        prepared_dir=prepared_dir,
        write_reports=False,
    )

    assert report["summary"]["ok"] is False
    assert _check_map(report)["prepared_lf_README_md"] is False


def test_validator_recomputes_sampling_after_consistent_rehash(tmp_path: Path) -> None:
    prepared_dir, _ = _build(tmp_path)
    assignments_path = prepared_dir / "sample_assignments.jsonl"
    rows = [json.loads(line) for line in assignments_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["selection_score"] = "0" * 64
    _write_jsonl(assignments_path, rows)
    manifest_path = prepared_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sample_assignments_sha256"] = hashlib.sha256(
        assignments_path.read_bytes()
    ).hexdigest()
    _write_json(manifest_path, manifest)
    _rehash_checksums(prepared_dir, PREPARED_CHECKSUM_FILES)

    report = validate_manual_review_evidence(
        prepared_dir=prepared_dir,
        write_reports=False,
    )
    checks = _check_map(report)

    assert report["summary"]["ok"] is False
    assert checks["prepared_assignments_sha256_matches"] is True
    assert checks["prepared_assignment_scores_recomputed"] is False
    assert checks["prepared_sampling_independently_recomputed"] is False


def test_validator_rejects_sampling_policy_drift_after_rehash(tmp_path: Path) -> None:
    prepared_dir, _ = _build(tmp_path)
    manifest_path = prepared_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sampling_policy"]["seed"] = "unaccepted-review-seed"
    _write_json(manifest_path, manifest)
    _rehash_checksums(prepared_dir, PREPARED_CHECKSUM_FILES)

    report = validate_manual_review_evidence(
        prepared_dir=prepared_dir,
        write_reports=False,
    )

    assert report["summary"]["ok"] is False
    assert _check_map(report)["prepared_sampling_policy_matches_config"] is False


def test_validator_rejects_source_path_boundary_drift_after_rehash(
    tmp_path: Path,
) -> None:
    prepared_dir, _ = _build(tmp_path)
    sample_path = prepared_dir / "canonical_documents.sample.jsonl"
    manifest_path = prepared_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_canonical_input"]["path"] = str(sample_path.resolve())
    manifest["source_canonical_input"]["sha256"] = hashlib.sha256(
        sample_path.read_bytes()
    ).hexdigest()
    _write_json(manifest_path, manifest)
    _rehash_checksums(prepared_dir, PREPARED_CHECKSUM_FILES)

    report = validate_manual_review_evidence(
        prepared_dir=prepared_dir,
        write_reports=False,
    )

    assert report["summary"]["ok"] is False
    assert (
        _check_map(report)["prepared_source_path_matches_status_boundary"] is False
    )


def test_validator_rejects_prediction_leakage_after_consistent_rehash(tmp_path: Path) -> None:
    prepared_dir, _ = _build(tmp_path)
    template_path = prepared_dir / "annotation_template.jsonl"
    rows = [json.loads(line) for line in template_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["evidence_id"] = "leaked-prediction"
    _write_jsonl(template_path, rows)
    manifest_path = prepared_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["annotation_template_sha256"] = hashlib.sha256(
        template_path.read_bytes()
    ).hexdigest()
    _write_json(manifest_path, manifest)
    _rehash_checksums(prepared_dir, PREPARED_CHECKSUM_FILES)

    report = validate_manual_review_evidence(
        prepared_dir=prepared_dir,
        write_reports=False,
    )

    assert report["summary"]["ok"] is False
    assert any(
        row["name"] == "prepared_template_contract" and row["ok"] is False
        for row in report["checks"]
    )


def test_validator_recomputes_preparation_quality_summary(tmp_path: Path) -> None:
    prepared_dir, _ = _build(tmp_path)
    quality_path = prepared_dir / "data_quality_summary.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    quality["eligible_document_count"] += 1
    _write_json(quality_path, quality)
    _rehash_checksums(prepared_dir, PREPARED_CHECKSUM_FILES)

    report = validate_manual_review_evidence(
        prepared_dir=prepared_dir,
        write_reports=False,
    )

    assert report["summary"]["ok"] is False
    assert _check_map(report)["prepared_quality_eligible_count_matches"] is False


def test_validator_recomputes_reference_mentions_after_rehash(tmp_path: Path) -> None:
    prepared_dir, completed_dir = _build(tmp_path)
    references_path = completed_dir / "reference_mentions.jsonl"
    rows = [json.loads(line) for line in references_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["surface_text"] = "lass"
    _write_jsonl(references_path, rows)
    reference_sha = hashlib.sha256(references_path.read_bytes()).hexdigest()

    review_path = completed_dir / "review_manifest.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["reference_mentions_sha256"] = reference_sha
    _write_json(review_path, review)

    completion_path = completed_dir / "completion_manifest.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    completion["reference_mentions_sha256"] = reference_sha
    completion["review_manifest_sha256"] = hashlib.sha256(review_path.read_bytes()).hexdigest()
    _write_json(completion_path, completion)
    _rehash_checksums(completed_dir, COMPLETED_CHECKSUM_FILES)

    report = validate_manual_review_evidence(
        prepared_dir=prepared_dir,
        completed_dir=completed_dir,
        write_reports=False,
    )

    assert report["summary"]["ok"] is False
    assert _check_map(report)["completed_reference_mentions_independently_recomputed"] is False


def test_validator_recomputes_annotation_audit_after_consistent_rehash(
    tmp_path: Path,
) -> None:
    prepared_dir, completed_dir = _build(tmp_path)
    audit_path = completed_dir / "annotation_audit_summary.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["zero_mention_annotation_row_count"] += 1
    _write_json(audit_path, audit)

    completion_path = completed_dir / "completion_manifest.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    completion["annotation_audit_sha256"] = hashlib.sha256(
        audit_path.read_bytes()
    ).hexdigest()
    _write_json(completion_path, completion)
    _rehash_checksums(completed_dir, COMPLETED_CHECKSUM_FILES)

    report = validate_manual_review_evidence(
        prepared_dir=prepared_dir,
        completed_dir=completed_dir,
        write_reports=False,
    )

    assert report["summary"]["ok"] is False
    assert _check_map(report)["completed_audit_counts_match"] is False


def test_strict_cli_returns_zero_for_valid_evidence(tmp_path: Path) -> None:
    prepared_dir, completed_dir = _build(tmp_path)

    exit_code = main(
        [
            "--prepared-dir",
            str(prepared_dir),
            "--completed-dir",
            str(completed_dir),
            "--strict",
            "--no-write-reports",
        ]
    )

    assert exit_code == 0


def test_strict_cli_returns_one_for_invalid_evidence(tmp_path: Path) -> None:
    prepared_dir, _ = _build(tmp_path)
    (prepared_dir / "README.md").unlink()

    exit_code = main(
        [
            "--prepared-dir",
            str(prepared_dir),
            "--strict",
            "--no-write-reports",
        ]
    )

    assert exit_code == 1
