from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from scripts.export.export_public_dataset import export_public_dataset
from scripts.validation.check_dataset_release_output import (
    build_report,
    validate_release_output,
)
from tests.smoke.test_public_dataset_export_contract import make_config


def required_failures(checks) -> set[str]:
    return {check.name for check in checks if check.severity == "required" and not check.ok}


def build_valid_release(tmp_path: Path) -> tuple[dict, Path, Path]:
    config, config_path = make_config(tmp_path)
    summary = export_public_dataset(config_path=config_path)
    return config, config_path, Path(summary["release_dir"])


def test_valid_release_output_passes_required_checks(tmp_path: Path) -> None:
    config, config_path, release_dir = build_valid_release(tmp_path)

    checks = validate_release_output(config, config_path=config_path, release_dir=release_dir)
    report = build_report(
        config_path=config_path,
        release_dir=release_dir,
        output_dir=tmp_path / "artifacts" / "reports" / "validation",
        checks=checks,
        strict=True,
    )

    assert report["ok"] is True
    assert report["required_failed_count"] == 0


def test_validator_fails_when_required_file_is_missing(tmp_path: Path) -> None:
    config, config_path, release_dir = build_valid_release(tmp_path)
    (release_dir / "data.parquet").unlink()

    failures = required_failures(
        validate_release_output(config, config_path=config_path, release_dir=release_dir)
    )

    assert "required_output_files" in failures


def test_validator_fails_on_duplicate_canonical_id(tmp_path: Path) -> None:
    config, config_path, release_dir = build_valid_release(tmp_path)
    data_path = release_dir / "data.parquet"
    frame = pd.read_parquet(data_path)
    frame.loc[1, "canonical_id"] = frame.loc[0, "canonical_id"]
    frame.to_parquet(data_path, index=False, compression="zstd")

    failures = required_failures(
        validate_release_output(config, config_path=config_path, release_dir=release_dir)
    )

    assert "unique_canonical_id" in failures


def test_validator_fails_on_forbidden_column(tmp_path: Path) -> None:
    config, config_path, release_dir = build_valid_release(tmp_path)
    data_path = release_dir / "data.parquet"
    frame = pd.read_parquet(data_path)
    frame["embedding_vector"] = ["[]"] * len(frame)
    frame.to_parquet(data_path, index=False, compression="zstd")

    failures = required_failures(
        validate_release_output(config, config_path=config_path, release_dir=release_dir)
    )

    assert "no_forbidden_columns" in failures
    assert "data_columns_match_config" in failures


def test_validator_fails_on_checksum_mismatch(tmp_path: Path) -> None:
    config, config_path, release_dir = build_valid_release(tmp_path)
    readme_path = release_dir / "README.md"
    readme_path.write_text(readme_path.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")

    failures = required_failures(
        validate_release_output(config, config_path=config_path, release_dir=release_dir)
    )

    assert "checksums_match_files" in failures


def test_validator_fails_when_manifest_claims_publication(tmp_path: Path) -> None:
    config, config_path, release_dir = build_valid_release(tmp_path)
    manifest_path = release_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["publication_status"] = "published"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    failures = required_failures(
        validate_release_output(config, config_path=config_path, release_dir=release_dir)
    )

    assert "manifest_not_published" in failures


def test_release_dir_must_be_under_configured_output_root(tmp_path: Path) -> None:
    config, config_path, release_dir = build_valid_release(tmp_path)
    outside_dir = tmp_path / "outside_release"
    outside_dir.mkdir()
    for item in release_dir.iterdir():
        (outside_dir / item.name).write_bytes(item.read_bytes())

    failures = required_failures(
        validate_release_output(config, config_path=config_path, release_dir=outside_dir)
    )

    assert "release_dir_under_output_root" in failures


def test_validator_fails_when_data_quality_summary_row_count_is_stale(tmp_path: Path) -> None:
    config, config_path, release_dir = build_valid_release(tmp_path)
    summary_path = release_dir / "data_quality_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["row_count"] = 999
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    failures = required_failures(
        validate_release_output(config, config_path=config_path, release_dir=release_dir)
    )

    assert "data_quality_summary_row_count_matches_data" in failures


def test_validator_fails_when_manifest_omits_data_quality_summary_file(tmp_path: Path) -> None:
    config, config_path, release_dir = build_valid_release(tmp_path)
    manifest_path = release_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"].pop("data_quality_summary")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    failures = required_failures(
        validate_release_output(config, config_path=config_path, release_dir=release_dir)
    )

    assert "manifest_lists_data_quality_summary_file" in failures


def test_validator_fails_when_attribution_file_is_missing(tmp_path: Path) -> None:
    config, config_path, release_dir = build_valid_release(tmp_path)
    (release_dir / "ATTRIBUTION.md").unlink()
    failures = required_failures(
        validate_release_output(config, config_path=config_path, release_dir=release_dir)
    )
    assert "required_output_files" in failures


def test_validator_fails_when_kaggle_template_claims_publication(tmp_path: Path) -> None:
    config, config_path, release_dir = build_valid_release(tmp_path)
    path = release_dir / "kaggle_metadata.template.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["template_only"] = False
    payload["publication_action"] = "performed"
    payload["id"] = "owner/ml-research-radar-metadata"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    failures = required_failures(
        validate_release_output(config, config_path=config_path, release_dir=release_dir)
    )
    assert "kaggle_template_not_publication" in failures
