from __future__ import annotations

import json
from pathlib import Path

from scripts.export.export_public_dataset import export_public_dataset
from scripts.validation.check_dataset_release_output import (
    build_report as build_output_report,
    validate_release_output,
    write_reports as write_output_reports,
)
from scripts.validation.check_dataset_release_review_readiness import (
    build_report,
    validate_review_readiness,
)
from tests.smoke.test_public_dataset_export_contract import make_config


def required_failures(checks) -> set[str]:
    return {check.name for check in checks if check.severity == "required" and not check.ok}


def build_review_candidate(tmp_path: Path) -> tuple[dict, Path, Path, Path]:
    config, config_path = make_config(tmp_path)
    summary = export_public_dataset(config_path=config_path)
    release_dir = Path(summary["release_dir"])
    output_dir = tmp_path / "artifacts" / "reports" / "validation"
    output_checks = validate_release_output(config, config_path=config_path, release_dir=release_dir)
    output_report = build_output_report(
        config_path=config_path,
        release_dir=release_dir,
        output_dir=output_dir,
        checks=output_checks,
        strict=True,
    )
    latest_json, _latest_md, _history_json, _history_md = write_output_reports(output_report, output_dir)
    return config, config_path, release_dir, latest_json


def test_valid_candidate_is_ready_for_manual_review_but_not_publication(tmp_path: Path) -> None:
    config, config_path, release_dir, output_report_path = build_review_candidate(tmp_path)

    checks = validate_review_readiness(
        config,
        config_path=config_path,
        release_dir=release_dir,
        output_validation_report_path=output_report_path,
    )
    report = build_report(
        config_path=config_path,
        release_dir=release_dir,
        output_validation_report_path=output_report_path,
        output_dir=tmp_path / "artifacts" / "reports" / "validation",
        checks=checks,
        strict=True,
    )

    assert report["ok"] is True
    assert report["technical_candidate_ready"] is True
    assert report["manual_review_required"] is True
    assert report["publication_ready"] is False
    assert report["publication_block_reason"] == "manual_review_not_completed"
    assert report["required_failed_count"] == 0


def test_review_readiness_fails_when_output_validation_report_is_missing(tmp_path: Path) -> None:
    config, config_path, release_dir, output_report_path = build_review_candidate(tmp_path)
    output_report_path.unlink()

    failures = required_failures(
        validate_review_readiness(
            config,
            config_path=config_path,
            release_dir=release_dir,
            output_validation_report_path=output_report_path,
        )
    )

    assert "output_validation_report_readable" in failures


def test_review_readiness_fails_when_output_validation_report_is_not_green(tmp_path: Path) -> None:
    config, config_path, release_dir, output_report_path = build_review_candidate(tmp_path)
    output_report = json.loads(output_report_path.read_text(encoding="utf-8"))
    output_report["ok"] = False
    output_report["required_failed_count"] = 1
    output_report["required_failed_checks"] = ["synthetic_failure"]
    output_report_path.write_text(json.dumps(output_report, ensure_ascii=False, indent=2), encoding="utf-8")

    failures = required_failures(
        validate_review_readiness(
            config,
            config_path=config_path,
            release_dir=release_dir,
            output_validation_report_path=output_report_path,
        )
    )

    assert "output_validation_report_ok" in failures
    assert "output_validation_report_required_failed_count_zero" in failures


def test_review_readiness_fails_when_manifest_claims_publication(tmp_path: Path) -> None:
    config, config_path, release_dir, output_report_path = build_review_candidate(tmp_path)
    manifest_path = release_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["publication_status"] = "published"
    manifest["manual_review_required_before_publication"] = False
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    failures = required_failures(
        validate_review_readiness(
            config,
            config_path=config_path,
            release_dir=release_dir,
            output_validation_report_path=output_report_path,
        )
    )

    assert "manifest_not_published" in failures
    assert "manifest_manual_review_required" in failures


def test_review_readiness_fails_when_data_quality_summary_has_duplicates(tmp_path: Path) -> None:
    config, config_path, release_dir, output_report_path = build_review_candidate(tmp_path)
    summary_path = release_dir / "data_quality_summary.json"
    quality_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    quality_summary["canonical_id"]["duplicate_count"] = 1
    summary_path.write_text(json.dumps(quality_summary, ensure_ascii=False, indent=2), encoding="utf-8")

    failures = required_failures(
        validate_review_readiness(
            config,
            config_path=config_path,
            release_dir=release_dir,
            output_validation_report_path=output_report_path,
        )
    )

    assert "data_quality_summary_no_duplicate_canonical_ids" in failures


def test_review_readiness_fails_when_publication_before_review_is_allowed(tmp_path: Path) -> None:
    config, config_path, release_dir, output_report_path = build_review_candidate(tmp_path)
    config["license_review"]["publication_allowed_before_review"] = True

    failures = required_failures(
        validate_review_readiness(
            config,
            config_path=config_path,
            release_dir=release_dir,
            output_validation_report_path=output_report_path,
        )
    )

    assert "config_publication_allowed_before_review_false" in failures


def test_review_readiness_fails_when_output_report_points_to_other_release_dir(tmp_path: Path) -> None:
    config, config_path, release_dir, output_report_path = build_review_candidate(tmp_path)
    output_report = json.loads(output_report_path.read_text(encoding="utf-8"))
    output_report["release_dir"] = "data/datasets_release/other/v0.1"
    output_report_path.write_text(json.dumps(output_report, ensure_ascii=False, indent=2), encoding="utf-8")

    failures = required_failures(
        validate_review_readiness(
            config,
            config_path=config_path,
            release_dir=release_dir,
            output_validation_report_path=output_report_path,
        )
    )

    assert "output_validation_report_release_dir_matches" in failures
