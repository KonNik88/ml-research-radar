from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.validation.check_public_metadata_release_review import (
    build_report as build_manual_report,
    validate_review,
    write_reports as write_manual_reports,
)
from scripts.validation.check_public_metadata_release_review_evidence import (
    build_report,
    validate_evidence,
)
from tests.smoke.test_public_metadata_release_review import (
    COLUMNS,
    SOURCE_FAMILIES,
    build_manual_review_fixture,
    required_failures,
    write_json,
    write_text,
    write_yaml,
)


def build_evidence_fixture(tmp_path: Path) -> tuple[dict, Path]:
    manual_config, manual_config_path = build_manual_review_fixture(tmp_path)
    output_dir = tmp_path / "artifacts/reports/validation"
    manual_checks = validate_review(manual_config, config_path=manual_config_path, check_paths=True)
    manual_report = build_manual_report(
        config_path=manual_config_path,
        output_dir=output_dir,
        config=manual_config,
        checks=manual_checks,
        strict=True,
        check_paths=True,
    )
    write_manual_reports(manual_report, output_dir)

    release_dir = tmp_path / "data/datasets_release/ml_research_radar_metadata/v0.1"
    write_json(
        release_dir / "schema.json",
        {
            "schema_version": "dataset_release_schema_v1",
            "primary_key": ["canonical_id"],
            "columns": [{"name": name, "dtype": "string|null", "nullable": True} for name in COLUMNS],
        },
    )
    fields = []
    for name in COLUMNS:
        field = {"name": name, "classification": "metadata", "action": "include"}
        if name == "abstract":
            field.update({"action": "source_aware_include_or_null", "fallback_action": "null", "acl_min_year": 2016})
        if name == "pdf_url":
            field["action"] = "include_link_only_no_binary"
        fields.append(field)
    write_json(
        release_dir / "field_release_policy.json",
        {
            "schema_version": "dataset_field_release_policy_v1",
            "policy_id": "ml_research_radar_public_metadata_release_v0.1",
            "fields": fields,
        },
    )

    source_policy = yaml.safe_load((tmp_path / "configs/public_metadata_release_policy_v0.1.yaml").read_text(encoding="utf-8"))["source_policies"]
    source_rows = []
    for name in SOURCE_FAMILIES:
        row = {"source_family": name, **source_policy[name]}
        source_rows.append(row)
    write_json(
        release_dir / "source_attribution.json",
        {
            "schema_version": "dataset_source_attribution_v1",
            "policy_id": "ml_research_radar_public_metadata_release_v0.1",
            "policy_version": "v0.1",
            "attribution_required_for_all_sources": True,
            "sources": source_rows,
        },
    )
    write_text(
        release_dir / "README.md",
        "not published\nmanual_release_decision_required\ncanonical_truth_impact\nmay_be_used_as_reconcile_input\n",
    )
    checksum_names = [
        "data.parquet", "schema.json", "manifest.json", "README.md", "DATASET_CARD.md", "ATTRIBUTION.md",
        "field_release_policy.json", "source_attribution.json", "kaggle_metadata.template.json", "data_quality_summary.json",
    ]
    write_text(release_dir / "checksums.txt", "".join(f"{'a'*64}  {name}\n" for name in checksum_names))

    docs = {
        "docs/public_metadata_release_policy_v0.1.md": "source-aware public metadata projection\nexplicit human release decision\nnever download or package the PDF binary\n",
        "docs/dataset-release-v0.1.md": "publication_ready = false\npublic upload is not performed\n",
        "docs/dataset_strategy.md": "derived public artifact candidate\nmanual license/provenance review\n",
        "docs/source_matrix.md": "arxiv openalex_alignment semantic_scholar_alignment crossref_alignment acl_anthology\n",
        "docs/provenance_semantics.md": "sources is the provenance rows list\nsource_count\nunique_source_count\n",
        "docs/merge_policy.md": "field-dependent\nartifact sources are not paper truth sources\n",
    }
    for relative, text in docs.items():
        write_text(tmp_path / relative, text)

    evidence_config = yaml.safe_load(Path("configs/public_metadata_release_review_evidence.yaml").read_text(encoding="utf-8"))
    evidence_config["expected"]["canonical_doc_count"] = 3
    evidence_config_path = tmp_path / "configs/public_metadata_release_review_evidence.yaml"
    write_yaml(evidence_config_path, evidence_config)
    return evidence_config, evidence_config_path


def test_valid_evidence_supports_completed_rejected_review_without_publication(tmp_path: Path) -> None:
    config, config_path = build_evidence_fixture(tmp_path)
    checks, categories = validate_evidence(config, config_path=config_path, check_paths=True)
    report = build_report(
        config_path=config_path,
        output_dir=tmp_path / "artifacts/reports/validation",
        config=config,
        checks=checks,
        categories=categories,
        strict=True,
        check_paths=True,
    )
    assert report["ok"] is True
    assert report["manual_review_evidence_ready"] is True
    assert report["evidence"]["evidence_ready_category_count"] == 20
    assert report["evidence"]["automated_support_category_count"] == 15
    assert report["evidence"]["human_decision_category_count"] == 5
    assert report["evidence"]["category_status_counts"] == {"failed": 5, "passed": 15}
    assert report["manual_review_complete"] is True
    assert report["publication_ready"] is False


def test_evidence_mirrors_human_pass_fail_statuses_without_automated_approval(tmp_path: Path) -> None:
    config, config_path = build_evidence_fixture(tmp_path)
    _checks, categories = validate_evidence(config, config_path=config_path, check_paths=True)
    assert sum(category["category_status"] == "passed" for category in categories) == 15
    assert sum(category["category_status"] == "failed" for category in categories) == 5
    assert all(category["automated_decision"] is None for category in categories)
    assert sum(category["human_decision_required"] for category in categories) == 5


def test_evidence_fails_when_attribution_source_is_missing(tmp_path: Path) -> None:
    config, config_path = build_evidence_fixture(tmp_path)
    path = tmp_path / config["inputs"]["source_attribution"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["sources"] = [row for row in payload["sources"] if row["source_family"] != "semantic_scholar"]
    write_json(path, payload)
    checks, _ = validate_evidence(config, config_path=config_path, check_paths=True)
    failures = required_failures(checks)
    assert "source_attribution_coverage" in failures
    assert "source_policy_evidence" in failures
    assert "all_categories_evidence_ready" in failures


def test_evidence_fails_when_kaggle_template_claims_publication(tmp_path: Path) -> None:
    config, config_path = build_evidence_fixture(tmp_path)
    path = tmp_path / config["inputs"]["kaggle_metadata_template"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update({"template_only": False, "publication_action": "performed", "id": "owner/ml-research-radar-metadata"})
    write_json(path, payload)
    checks, _ = validate_evidence(config, config_path=config_path, check_paths=True)
    failures = required_failures(checks)
    assert "package_manifest_checksums_kaggle_template" in failures
    assert "publication_action_separation" in failures


def test_evidence_fails_on_stale_row_count(tmp_path: Path) -> None:
    config, config_path = build_evidence_fixture(tmp_path)
    path = tmp_path / config["inputs"]["data_quality_summary"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["row_count"] = 999
    write_json(path, payload)
    checks, _ = validate_evidence(config, config_path=config_path, check_paths=True)
    failures = required_failures(checks)
    assert "data_quality_checkpoint" in failures
    assert "all_categories_evidence_ready" in failures


def test_evidence_fails_when_checksum_entry_is_missing(tmp_path: Path) -> None:
    config, config_path = build_evidence_fixture(tmp_path)
    path = tmp_path / config["inputs"]["checksums"]
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if not line.endswith("  DATASET_CARD.md")]
    write_text(path, "\n".join(lines) + "\n")
    checks, _ = validate_evidence(config, config_path=config_path, check_paths=True)
    assert "package_manifest_checksums_kaggle_template" in required_failures(checks)


def test_evidence_fails_if_manual_review_regresses_to_pending(tmp_path: Path) -> None:
    config, config_path = build_evidence_fixture(tmp_path)
    manual_path = tmp_path / config["inputs"]["manual_review_config"]
    manual = yaml.safe_load(manual_path.read_text(encoding="utf-8"))
    manual["review"].update({
        "approval_state": "not_reviewed",
        "manual_review_complete": False,
        "publication_block_reason": "public_release_decision_not_completed",
    })
    for category in manual["manual_review"]["categories"]:
        category["status"] = "pending"
    write_yaml(manual_path, manual)
    checks, _ = validate_evidence(config, config_path=config_path, check_paths=True)
    assert "manual_review_gate_rejected_and_green" in required_failures(checks)



def test_evidence_fails_when_decision_record_marker_is_missing(tmp_path: Path) -> None:
    config, config_path = build_evidence_fixture(tmp_path)
    path = tmp_path / config["inputs"]["decision_record_doc"]
    write_text(path, "approval_state: approved\ncategory_status_counts: passed = 20\n")
    checks, _ = validate_evidence(config, config_path=config_path, check_paths=True)
    failures = required_failures(checks)
    assert "decision_record_doc_markers" in failures
    assert "human_decision_material_ready" in failures
    assert "all_categories_evidence_ready" in failures

def test_evidence_fails_when_manifest_claims_publication(tmp_path: Path) -> None:
    config, config_path = build_evidence_fixture(tmp_path)
    path = tmp_path / config["inputs"]["release_manifest"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["publication_status"] = "published"
    write_json(path, payload)
    checks, _ = validate_evidence(config, config_path=config_path, check_paths=True)
    failures = required_failures(checks)
    assert "publication_action_separation" in failures
    assert "all_categories_evidence_ready" in failures
