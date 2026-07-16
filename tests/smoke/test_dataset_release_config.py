from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.validation.check_dataset_release_config import (
    build_report,
    validate_config,
)


def make_valid_config() -> dict:
    return {
        "schema_version": "dataset_release_config_v2",
        "release": {
            "dataset_name": "ml_research_radar_metadata",
            "version": "v0.1",
            "release_family": "clean_research_metadata",
            "status": "candidate_contract",
            "publication_targets": ["huggingface_datasets", "kaggle"],
        },
        "source_checkpoint": {
            "canonical_corpus_path": "data/analytics/reconciled/canonical_documents.jsonl",
            "expected_canonical_doc_count": 60954,
            "retrieval_manifest_path": "artifacts/retrieval/manifests/latest.json",
            "retrieval_build_id": "20260504T164021Z",
            "retrieval_corpus_doc_count": 60954,
        },
        "export": {
            "output_root": "data/datasets_release",
            "format": "parquet",
            "include_embeddings": False,
            "include_raw_provider_payloads": False,
            "include_source_records": False,
            "include_full_text": False,
            "include_pdfs": False,
            "include_private_notes": False,
            "deterministic_order_by": ["canonical_id"],
        },
        "columns": {
            "required": [
                "canonical_id",
                "title",
                "abstract",
                "authors",
                "year",
                "doi",
                "source_count",
                "unique_source_count",
            ],
            "optional": ["keywords"],
            "forbidden": [
                "raw_provider_payload",
                "raw_source_record",
                "full_text",
                "pdf_binary",
                "embedding_vector",
                "private_notes",
            ],
        },
        "validation": {
            "require_unique_canonical_id": True,
            "require_expected_row_count": True,
            "require_non_empty_title": True,
            "require_manifest_json": True,
            "require_schema_json": True,
            "require_checksums_txt": True,
            "require_readme_md": True,
            "require_data_file": True,
            "require_data_quality_summary_json": True,
            "require_deterministic_order": True,
            "require_no_forbidden_columns": True,
            "require_build_metadata": True,
        },
        "license_review": {
            "status": "required_before_publication",
            "publication_allowed_before_review": False,
        },
        "safety": {
            "canonical_truth_impact": "none",
            "may_overwrite_operational_latest": False,
            "may_be_used_as_reconcile_input": False,
            "may_include_full_text": False,
            "may_include_pdfs": False,
            "may_include_embeddings_without_review": False,
            "publish_without_manual_review": False,
        },
        "public_release_policy": {
            "path": "configs/public_metadata_release_policy_v0.1.yaml",
            "required": True,
            "expected_schema_version": "public_metadata_release_policy_v1",
            "require_policy_validation_before_review": True,
        },
        "packaging": {
            "dataset_card_file": "DATASET_CARD.md",
            "attribution_file": "ATTRIBUTION.md",
            "field_policy_file": "field_release_policy.json",
            "source_attribution_file": "source_attribution.json",
            "kaggle_metadata_template_file": "kaggle_metadata.template.json",
            "kaggle_owner_slug": None,
            "kaggle_dataset_slug": "ml-research-radar-metadata",
            "kaggle_license_name": "other",
            "kaggle_metadata_is_template_only": True,
            "include_publication_command": False,
        },
        "outputs": {
            "expected_release_layout": [
                "data.parquet",
                "schema.json",
                "manifest.json",
                "README.md",
                "data_quality_summary.json",
                "checksums.txt",
                "DATASET_CARD.md",
                "ATTRIBUTION.md",
                "field_release_policy.json",
                "source_attribution.json",
                "kaggle_metadata.template.json",
            ]
        },
    }


def failed_names(config: dict) -> set[str]:
    checks = validate_config(
        config,
        config_path=Path("configs/dataset_release.yaml"),
        check_paths=False,
    )
    return {check.name for check in checks if check.severity == "required" and not check.ok}


def test_valid_config_passes_required_checks() -> None:
    config = make_valid_config()
    checks = validate_config(
        config,
        config_path=Path("configs/dataset_release.yaml"),
        check_paths=False,
    )
    report = build_report(
        config_path=Path("configs/dataset_release.yaml"),
        output_dir=Path("artifacts/reports/validation"),
        config=config,
        checks=checks,
        strict=True,
        check_paths=False,
    )

    assert report["ok"] is True
    assert report["required_failed_count"] == 0


@pytest.mark.parametrize(
    ("field", "expected_failure"),
    [
        ("include_embeddings", "export_include_embeddings"),
        ("include_raw_provider_payloads", "export_include_raw_provider_payloads"),
        ("include_source_records", "export_include_source_records"),
        ("include_full_text", "export_include_full_text"),
        ("include_pdfs", "export_include_pdfs"),
        ("include_private_notes", "export_include_private_notes"),
    ],
)
def test_metadata_release_forbids_high_risk_export_flags(
    field: str,
    expected_failure: str,
) -> None:
    config = make_valid_config()
    config["export"][field] = True

    assert expected_failure in failed_names(config)


@pytest.mark.parametrize(
    ("field", "bad_value", "expected_failure"),
    [
        ("may_overwrite_operational_latest", True, "safety_may_overwrite_operational_latest"),
        ("may_be_used_as_reconcile_input", True, "safety_may_be_used_as_reconcile_input"),
        ("may_include_full_text", True, "safety_may_include_full_text"),
        ("may_include_pdfs", True, "safety_may_include_pdfs"),
        ("publish_without_manual_review", True, "safety_publish_without_manual_review"),
        ("canonical_truth_impact", "mutates_truth", "safety_canonical_truth_impact"),
    ],
)
def test_safety_flags_are_enforced(
    field: str,
    bad_value,
    expected_failure: str,
) -> None:
    config = make_valid_config()
    config["safety"][field] = bad_value

    assert expected_failure in failed_names(config)


def test_required_columns_include_minimum_contract() -> None:
    config = make_valid_config()
    config["columns"]["required"].remove("canonical_id")

    assert "required_columns" in failed_names(config)


def test_required_and_forbidden_columns_must_not_overlap() -> None:
    config = make_valid_config()
    config["columns"]["forbidden"].append("title")

    assert "required_forbidden_overlap" in failed_names(config)


def test_license_review_blocks_publication_before_review() -> None:
    config = make_valid_config()
    config["license_review"]["publication_allowed_before_review"] = True

    assert "publication_blocked_before_review" in failed_names(config)


def test_expected_layout_requires_data_quality_summary() -> None:
    config = make_valid_config()
    config["outputs"]["expected_release_layout"].remove("data_quality_summary.json")

    assert "expected_release_layout" in failed_names(config)


def test_validation_requires_data_quality_summary_flag() -> None:
    config = make_valid_config()
    config["validation"]["require_data_quality_summary_json"] = False

    assert "validation_required_flags" in failed_names(config)



def test_public_release_policy_is_required() -> None:
    config = make_valid_config()
    config["public_release_policy"]["required"] = False
    assert "public_release_policy_required" in failed_names(config)


def test_kaggle_metadata_must_remain_template_only() -> None:
    config = make_valid_config()
    config["packaging"]["include_publication_command"] = True
    assert "kaggle_metadata_template_only" in failed_names(config)


def test_kaggle_license_must_not_overclaim_cc0() -> None:
    config = make_valid_config()
    config["packaging"]["kaggle_license_name"] = "CC0-1.0"
    assert "kaggle_license_not_overclaimed" in failed_names(config)

def test_config_file_shape_matches_yaml_round_trip(tmp_path: Path) -> None:
    config = make_valid_config()
    config_path = tmp_path / "dataset_release.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    checks = validate_config(
        loaded,
        config_path=config_path,
        check_paths=False,
    )

    assert not [
        check.name
        for check in checks
        if check.severity == "required" and not check.ok
    ]
