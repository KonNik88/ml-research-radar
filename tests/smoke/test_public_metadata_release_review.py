from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.validation.check_public_metadata_release_review import (
    CATEGORY_IDS,
    build_report,
    validate_review,
)


SOURCE_FAMILIES = ["acl_anthology", "arxiv", "crossref", "openalex", "semantic_scholar"]
COLUMNS = [
    "canonical_id", "title", "abstract", "authors", "year", "doi", "arxiv_id", "openalex_id",
    "primary_category", "categories", "concepts", "venue", "journal", "conference", "publisher",
    "publication_type", "language", "landing_page_url", "pdf_url", "open_access", "source_count",
    "unique_source_count", "source_families", "metadata_completeness_score", "is_preprint", "is_review",
    "is_survey", "is_withdrawn", "keywords", "tags", "cited_by_count", "references_count",
    "provenance_summary", "external_ids_summary",
]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def required_failures(checks) -> set[str]:
    return {check.name for check in checks if check.severity == "required" and not check.ok}


def build_base_release_fixture(tmp_path: Path) -> dict[str, Path]:
    dataset_config = yaml.safe_load(Path("configs/dataset_release.yaml").read_text(encoding="utf-8"))
    dataset_config["source_checkpoint"]["expected_canonical_doc_count"] = 3
    dataset_config["source_checkpoint"]["retrieval_corpus_doc_count"] = 3
    dataset_config_path = tmp_path / "configs/dataset_release.yaml"
    write_yaml(dataset_config_path, dataset_config)

    policy = yaml.safe_load(Path("configs/public_metadata_release_policy_v0.1.yaml").read_text(encoding="utf-8"))
    policy_path = tmp_path / "configs/public_metadata_release_policy_v0.1.yaml"
    write_yaml(policy_path, policy)

    release_dir = tmp_path / "data/datasets_release/ml_research_radar_metadata/v0.1"
    manifest = {
        "schema_version": "dataset_release_manifest_v2",
        "status": "candidate_local_export",
        "publication_status": "not_published",
        "manual_review_required_before_publication": True,
        "release": {
            "dataset_name": "ml_research_radar_metadata",
            "version": "v0.1",
            "release_family": "clean_research_metadata",
            "publication_targets": ["huggingface_datasets", "kaggle"],
        },
        "source_checkpoint": {
            "expected_canonical_doc_count": 3,
            "actual_exported_row_count": 3,
            "retrieval_build_id": "20260504T164021Z",
        },
        "public_release_policy": {
            "schema_version": "public_metadata_release_policy_v1",
            "policy_id": "ml_research_radar_public_metadata_release_v0.1",
            "policy_version": "v0.1",
            "publication_action_in_scope": False,
        },
        "compilation_license": {
            "status": "pending_explicit_release_decision",
            "single_cc0_claim_allowed": False,
            "kaggle_template_license_name": "other",
        },
        "safety": {
            "canonical_truth_impact": "none",
            "may_be_used_as_reconcile_input": False,
            "publish_without_manual_review": False,
        },
        "files": {
            "data": "data.parquet",
            "schema": "schema.json",
            "manifest": "manifest.json",
            "readme": "README.md",
            "dataset_card": "DATASET_CARD.md",
            "attribution": "ATTRIBUTION.md",
            "field_release_policy": "field_release_policy.json",
            "source_attribution": "source_attribution.json",
            "kaggle_metadata_template": "kaggle_metadata.template.json",
            "data_quality_summary": "data_quality_summary.json",
            "checksums": "checksums.txt",
        },
    }
    write_json(release_dir / "manifest.json", manifest)
    write_json(
        release_dir / "data_quality_summary.json",
        {
            "schema_version": "dataset_release_data_quality_summary_v1",
            "row_count": 3,
            "column_count": 34,
            "canonical_id": {"duplicate_count": 0, "unique_count": 3, "non_empty_count": 3},
            "public_release_policy": {
                "schema_version": "public_metadata_release_policy_v1",
                "policy_id": "ml_research_radar_public_metadata_release_v0.1",
                "policy_version": "v0.1",
                "field_transformations": {"abstract_excluded_by_policy_count": 0},
            },
        },
    )
    write_text(
        release_dir / "DATASET_CARD.md",
        "publication_status: not_published\nfinal_compilation_license: pending_explicit_release_decision\n"
        "article PDF binaries\narticle full text\nrelease owner must review\n",
    )
    write_text(
        release_dir / "ATTRIBUTION.md",
        "ACL Anthology\narXiv\nCrossref\nOpenAlex\nSemantic Scholar\n"
        "does not contain PDF binaries\n",
    )
    write_json(
        release_dir / "kaggle_metadata.template.json",
        {
            "template_only": True,
            "publication_action": "not_performed",
            "id": "__KAGGLE_OWNER__/ml-research-radar-metadata",
            "licenses": [{"name": "other"}],
        },
    )

    reports = tmp_path / "artifacts/reports/validation"
    write_json(
        reports / "dataset_release_review_readiness_latest.json",
        {
            "schema_version": "dataset_release_review_readiness_v2",
            "ok": True,
            "technical_candidate_ready": True,
            "public_policy_ready": True,
            "manual_release_decision_required": True,
            "manual_review_required": True,
            "publication_ready": False,
            "publication_block_reason": "public_release_decision_not_completed",
            "required_failed_count": 0,
            "release_dir": "data/datasets_release/ml_research_radar_metadata/v0.1",
        },
    )
    write_json(
        reports / "public_metadata_release_policy_latest.json",
        {
            "schema_version": "public_metadata_release_policy_quality_v1",
            "ok": True,
            "required_failed_count": 0,
            "publication_action_in_scope": False,
            "policy_path": "configs/public_metadata_release_policy_v0.1.yaml",
        },
    )
    write_json(
        reports / "dataset_release_output_latest.json",
        {
            "schema_version": "dataset_release_output_quality_v2",
            "ok": True,
            "required_failed_count": 0,
            "required_failed_checks": [],
            "release_dir": "data/datasets_release/ml_research_radar_metadata/v0.1",
        },
    )
    write_json(
        reports / "dataset_release_config_latest.json",
        {
            "schema_version": "dataset_release_config_quality_v2",
            "ok": True,
            "required_failed_count": 0,
        },
    )

    return {
        "dataset_config": dataset_config_path,
        "policy": policy_path,
        "release_dir": release_dir,
        "reports": reports,
    }


def build_manual_review_fixture(tmp_path: Path) -> tuple[dict, Path]:
    build_base_release_fixture(tmp_path)
    review_config = yaml.safe_load(Path("configs/public_metadata_release_review.yaml").read_text(encoding="utf-8"))
    review_config_path = tmp_path / "configs/public_metadata_release_review.yaml"
    write_yaml(review_config_path, review_config)
    decision_source = Path("docs/public_metadata_release_review_decision_v0.1.md")
    write_text(
        tmp_path / review_config["inputs"]["decision_record"],
        decision_source.read_text(encoding="utf-8"),
    )
    return review_config, review_config_path


def test_rejected_review_gate_is_green_and_blocks_publication(tmp_path: Path) -> None:
    config, config_path = build_manual_review_fixture(tmp_path)
    checks = validate_review(config, config_path=config_path, check_paths=True)
    report = build_report(
        config_path=config_path,
        output_dir=tmp_path / "artifacts/reports/validation",
        config=config,
        checks=checks,
        strict=True,
        check_paths=True,
    )

    assert report["ok"] is True
    assert report["review"]["approval_state"] == "rejected"
    assert report["review"]["required_category_count"] == 20
    assert report["review"]["category_status_counts"] == {"failed": 5, "passed": 15}
    assert report["manual_review_complete"] is True
    assert report["publication_ready"] is False
    assert report["publication_block_reason"] == "manual_release_rejected"
    assert report["review"]["compilation_license_decision"] == "not_selected_due_semantic_scholar_redistribution_blocker"
    assert report["review"]["primary_publication_target"] == "kaggle_dataset_after_remediation"
    assert report["required_failed_count"] == 0


def test_completed_rejected_categories_do_not_authorize_publication(tmp_path: Path) -> None:
    config, config_path = build_manual_review_fixture(tmp_path)
    checks = validate_review(config, config_path=config_path, check_paths=True)
    assert not required_failures(checks)
    statuses = [category["status"] for category in config["manual_review"]["categories"]]
    assert statuses.count("passed") == 15
    assert statuses.count("failed") == 5
    assert "pending" not in statuses
    assert config["review"]["publication_ready"] is False
    assert config["review"]["publication_action_in_scope"] is False


def test_review_rejects_missing_required_category(tmp_path: Path) -> None:
    config, config_path = build_manual_review_fixture(tmp_path)
    config["manual_review"]["categories"].pop()
    failures = required_failures(validate_review(config, config_path=config_path, check_paths=False))
    assert "category_count" in failures
    assert "categories_cover_required_ids" in failures


def test_review_rejects_approval_state_regression(tmp_path: Path) -> None:
    config, config_path = build_manual_review_fixture(tmp_path)
    config["review"]["approval_state"] = "not_reviewed"
    config["review"]["manual_review_complete"] = False
    config["review"]["publication_block_reason"] = "public_release_decision_not_completed"
    for category in config["manual_review"]["categories"]:
        category["status"] = "pending"
    failures = required_failures(validate_review(config, config_path=config_path, check_paths=False))
    assert "review_approval_state" in failures
    assert "review_manual_review_complete" in failures
    assert "review_publication_block_reason" in failures
    assert "review_state_consistency" not in failures


def test_review_rejects_published_manifest(tmp_path: Path) -> None:
    config, config_path = build_manual_review_fixture(tmp_path)
    manifest_path = tmp_path / config["inputs"]["release_manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["publication_status"] = "published"
    write_json(manifest_path, manifest)
    failures = required_failures(validate_review(config, config_path=config_path, check_paths=True))
    assert "release_manifest_safe_candidate" in failures


def test_review_rejects_missing_readiness_report(tmp_path: Path) -> None:
    config, config_path = build_manual_review_fixture(tmp_path)
    (tmp_path / config["inputs"]["review_readiness_report"]).unlink()
    failures = required_failures(validate_review(config, config_path=config_path, check_paths=True))
    assert "input_review_readiness_report_exists" in failures
    assert "review_readiness_report_readable" in failures


def test_review_rejects_kaggle_publication_claim(tmp_path: Path) -> None:
    config, config_path = build_manual_review_fixture(tmp_path)
    kaggle_path = tmp_path / config["inputs"]["kaggle_metadata_template"]
    kaggle = json.loads(kaggle_path.read_text(encoding="utf-8"))
    kaggle["template_only"] = False
    kaggle["publication_action"] = "performed"
    kaggle["id"] = "owner/ml-research-radar-metadata"
    write_json(kaggle_path, kaggle)
    failures = required_failures(validate_review(config, config_path=config_path, check_paths=True))
    assert "kaggle_template_non_publishing" in failures



def test_review_rejects_missing_decision_record(tmp_path: Path) -> None:
    config, config_path = build_manual_review_fixture(tmp_path)
    (tmp_path / config["inputs"]["decision_record"]).unlink()
    failures = required_failures(validate_review(config, config_path=config_path, check_paths=True))
    assert "input_decision_record_exists" in failures
    assert "decision_record_readable" in failures


def test_review_rejects_incomplete_decision_record(tmp_path: Path) -> None:
    config, config_path = build_manual_review_fixture(tmp_path)
    write_text(tmp_path / config["inputs"]["decision_record"], "approval_state: approved\n")
    failures = required_failures(validate_review(config, config_path=config_path, check_paths=True))
    assert "decision_record_markers" in failures

def test_review_category_contract_is_stable() -> None:
    assert len(CATEGORY_IDS) == 20
    assert len(set(CATEGORY_IDS)) == 20
    assert CATEGORY_IDS[-1] == "manual_release_approval_state"
