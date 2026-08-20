from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from scripts.entities.evaluate_scientific_entity_evidence import CHECKSUM_FILES, evaluate_evidence
from scripts.validation.check_scientific_entity_evaluation import (
    main as validation_main,
    validate_evaluation,
)


FIXED_TIME = datetime(2026, 8, 21, 11, 0, 0, tzinfo=timezone.utc)
EVALUATION_ID = "scientific-entity-evaluation-validation-v0.1"


def _json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _execute(tmp_path: Path) -> Path:
    output_root = tmp_path / "output"
    evaluate_evidence(
        output_root=output_root,
        evaluation_id=EVALUATION_ID,
        execute=True,
        generated_at_utc=FIXED_TIME,
    )
    return output_root / EVALUATION_ID


def _rehash_manifest_and_checksums(evaluation_dir: Path) -> None:
    manifest_path = evaluation_dir / "manifest.json"
    manifest = _json(manifest_path)
    for field, filename in (
        ("metrics_sha256", "metrics.json"),
        ("per_type_metrics_sha256", "per_type_metrics.json"),
        ("matches_sha256", "matches.jsonl"),
        ("errors_sha256", "errors.jsonl"),
    ):
        manifest[field] = hashlib.sha256((evaluation_dir / filename).read_bytes()).hexdigest()
    manifest["match_count"] = len(
        (evaluation_dir / "matches.jsonl").read_text(encoding="utf-8").splitlines()
    )
    manifest["error_count"] = len(
        (evaluation_dir / "errors.jsonl").read_text(encoding="utf-8").splitlines()
    )
    _write_json(manifest_path, manifest)
    checksum_lines = [
        f"{hashlib.sha256((evaluation_dir / filename).read_bytes()).hexdigest()}  {filename}"
        for filename in CHECKSUM_FILES
    ]
    (evaluation_dir / "checksums.txt").write_text(
        "\n".join(checksum_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _check_map(report: dict[str, Any]) -> dict[str, bool]:
    return {row["name"]: row["ok"] for row in report["checks"]}


def test_validator_accepts_generated_evaluation(tmp_path: Path) -> None:
    evaluation_dir = _execute(tmp_path)

    report = validate_evaluation(evaluation_dir=evaluation_dir, write_reports=False)

    assert report["summary"]["ok"] is True
    assert report["summary"]["required_failed_count"] == 0
    assert _check_map(report)["metrics_independently_recomputed"] is True
    assert _check_map(report)["matches_are_one_to_one"] is True


def test_validator_writes_latest_and_history_reports(tmp_path: Path) -> None:
    evaluation_dir = _execute(tmp_path)
    report_dir = tmp_path / "reports"

    report = validate_evaluation(
        evaluation_dir=evaluation_dir,
        write_reports=True,
        report_dir=report_dir,
    )

    assert report["summary"]["ok"] is True
    assert (report_dir / "scientific_entity_evaluation_latest.json").is_file()
    assert (report_dir / "scientific_entity_evaluation_latest.md").is_file()
    assert len(list((report_dir / "history").glob("*.json"))) == 1
    assert len(list((report_dir / "history").glob("*.md"))) == 1


def test_validator_recomputes_metrics_independently_after_valid_rehash(
    tmp_path: Path,
) -> None:
    evaluation_dir = _execute(tmp_path)
    metrics_path = evaluation_dir / "metrics.json"
    metrics = _json(metrics_path)
    metrics["micro"]["exact"].update(
        {
            "true_positive": 13,
            "false_positive": 4,
            "false_negative": 5,
        }
    )
    _write_json(metrics_path, metrics)
    _rehash_manifest_and_checksums(evaluation_dir)

    report = validate_evaluation(evaluation_dir=evaluation_dir, write_reports=False)

    checks = _check_map(report)
    assert report["summary"]["ok"] is False
    assert checks["checksum_matches:metrics.json"] is True
    assert checks["manifest_metrics_sha_matches"] is True
    assert checks["metrics_independently_recomputed"] is False


def test_validator_rejects_duplicate_match_even_after_valid_rehash(
    tmp_path: Path,
) -> None:
    evaluation_dir = _execute(tmp_path)
    matches_path = evaluation_dir / "matches.jsonl"
    rows = matches_path.read_text(encoding="utf-8").splitlines()
    matches_path.write_text(
        "\n".join([*rows, rows[0]]) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _rehash_manifest_and_checksums(evaluation_dir)

    report = validate_evaluation(evaluation_dir=evaluation_dir, write_reports=False)

    checks = _check_map(report)
    assert report["summary"]["ok"] is False
    assert checks["checksum_matches:matches.jsonl"] is True
    assert checks["matches_are_one_to_one"] is False
    assert checks["matches_independently_recomputed"] is False


def test_validator_rejects_missing_error_after_valid_rehash(tmp_path: Path) -> None:
    evaluation_dir = _execute(tmp_path)
    errors_path = evaluation_dir / "errors.jsonl"
    rows = errors_path.read_text(encoding="utf-8").splitlines()
    errors_path.write_text(
        "\n".join(rows[:-1]) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _rehash_manifest_and_checksums(evaluation_dir)

    report = validate_evaluation(evaluation_dir=evaluation_dir, write_reports=False)

    assert report["summary"]["ok"] is False
    assert _check_map(report)["errors_independently_recomputed"] is False


def test_validator_rejects_crlf_even_when_checksum_is_updated(tmp_path: Path) -> None:
    evaluation_dir = _execute(tmp_path)
    readme_path = evaluation_dir / "README.md"
    readme_path.write_bytes(readme_path.read_bytes().replace(b"\n", b"\r\n"))
    _rehash_manifest_and_checksums(evaluation_dir)

    report = validate_evaluation(evaluation_dir=evaluation_dir, write_reports=False)

    checks = _check_map(report)
    assert report["summary"]["ok"] is False
    assert checks["output_utf8_lf:README.md"] is False
    assert checks["checksum_matches:README.md"] is True


def test_validator_rejects_directory_identity_mismatch(tmp_path: Path) -> None:
    evaluation_dir = _execute(tmp_path)
    renamed = evaluation_dir.with_name("renamed-evaluation")
    evaluation_dir.rename(renamed)

    report = validate_evaluation(evaluation_dir=renamed, write_reports=False)

    assert report["summary"]["ok"] is False
    assert _check_map(report)["directory_matches_evaluation_id"] is False


def test_validator_rejects_extra_output_file(tmp_path: Path) -> None:
    evaluation_dir = _execute(tmp_path)
    (evaluation_dir / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")

    report = validate_evaluation(evaluation_dir=evaluation_dir, write_reports=False)

    assert report["summary"]["ok"] is False
    assert _check_map(report)["required_file_layout_exact"] is False


def test_validator_reports_missing_output_file_without_crashing(
    tmp_path: Path,
) -> None:
    evaluation_dir = _execute(tmp_path)
    (evaluation_dir / "metrics.json").unlink()

    report = validate_evaluation(evaluation_dir=evaluation_dir, write_reports=False)

    checks = _check_map(report)
    assert report["summary"]["ok"] is False
    assert checks["required_file_layout_exact"] is False
    assert checks["metrics_schema_valid"] is False
    assert checks["manifest_metrics_sha_matches"] is False


def test_validator_rejects_manifest_input_hash_tampering(tmp_path: Path) -> None:
    evaluation_dir = _execute(tmp_path)
    manifest_path = evaluation_dir / "manifest.json"
    manifest = _json(manifest_path)
    manifest["review"]["manifest_sha256"] = "0" * 64
    _write_json(manifest_path, manifest)
    _rehash_manifest_and_checksums(evaluation_dir)

    report = validate_evaluation(evaluation_dir=evaluation_dir, write_reports=False)

    assert report["summary"]["ok"] is False
    assert _check_map(report)["review_manifest_sha_matches"] is False


def test_validator_rejects_descriptor_drift_after_valid_rehash(
    tmp_path: Path,
) -> None:
    evaluation_dir = _execute(tmp_path)
    manifest_path = evaluation_dir / "manifest.json"
    manifest = _json(manifest_path)
    manifest["review"]["reference_mention_count"] -= 1
    _write_json(manifest_path, manifest)
    _rehash_manifest_and_checksums(evaluation_dir)

    report = validate_evaluation(evaluation_dir=evaluation_dir, write_reports=False)

    checks = _check_map(report)
    assert report["summary"]["ok"] is False
    assert checks["checksum_matches:manifest.json"] is True
    assert checks["review_descriptor_matches_manifest"] is False


def test_strict_cli_returns_nonzero_for_corrupt_evaluation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    evaluation_dir = _execute(tmp_path)
    (evaluation_dir / "metrics.json").write_text("{}\n", encoding="utf-8")

    exit_code = validation_main(
        [
            "--evaluation-dir",
            str(evaluation_dir),
            "--strict",
            "--no-write-reports",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "[FAILED]" in output
