from __future__ import annotations

from pathlib import Path

import yaml

from scripts.validation.check_public_metadata_release_policy import (
    build_report,
    validate_policy,
)


def load_inputs() -> tuple[dict, dict, Path, Path]:
    policy_path = Path("configs/public_metadata_release_policy_v0.1.yaml")
    config_path = Path("configs/dataset_release.yaml")
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return policy, config, policy_path, config_path


def required_failures(checks) -> set[str]:
    return {check.name for check in checks if check.severity == "required" and not check.ok}


def test_current_policy_passes_required_checks() -> None:
    policy, config, policy_path, config_path = load_inputs()
    checks = validate_policy(
        policy,
        policy_path=policy_path,
        dataset_config=config,
        dataset_config_path=config_path,
        check_paths=True,
    )
    report = build_report(
        policy_path=policy_path,
        dataset_config_path=config_path,
        output_dir=Path("artifacts/reports/validation"),
        policy=policy,
        checks=checks,
        strict=True,
        check_paths=True,
    )
    assert report["ok"] is True
    assert report["required_failed_count"] == 0
    assert report["publication_action_in_scope"] is False


def test_policy_rejects_publication_action() -> None:
    policy, config, policy_path, config_path = load_inputs()
    policy["policy"]["publication_action_in_scope"] = True
    failures = required_failures(
        validate_policy(
            policy,
            policy_path=policy_path,
            dataset_config=config,
            dataset_config_path=config_path,
        )
    )
    assert "publication_action_not_in_scope" in failures


def test_policy_rejects_missing_source_family() -> None:
    policy, config, policy_path, config_path = load_inputs()
    policy["source_policies"].pop("semantic_scholar")
    failures = required_failures(
        validate_policy(
            policy,
            policy_path=policy_path,
            dataset_config=config,
            dataset_config_path=config_path,
        )
    )
    assert "required_source_policies" in failures


def test_policy_rejects_uncovered_dataset_column() -> None:
    policy, config, policy_path, config_path = load_inputs()
    policy["field_policies"].pop("title")
    failures = required_failures(
        validate_policy(
            policy,
            policy_path=policy_path,
            dataset_config=config,
            dataset_config_path=config_path,
        )
    )
    assert "field_policy_covers_dataset_columns" in failures


def test_policy_rejects_non_fail_closed_abstract_rule() -> None:
    policy, config, policy_path, config_path = load_inputs()
    policy["field_policies"]["abstract"]["fallback_action"] = "include"
    failures = required_failures(
        validate_policy(
            policy,
            policy_path=policy_path,
            dataset_config=config,
            dataset_config_path=config_path,
        )
    )
    assert "abstract_source_aware_policy" in failures


def test_policy_rejects_blanket_cc0_claim() -> None:
    policy, config, policy_path, config_path = load_inputs()
    policy["compilation_license"]["single_cc0_claim_allowed"] = True
    failures = required_failures(
        validate_policy(
            policy,
            policy_path=policy_path,
            dataset_config=config,
            dataset_config_path=config_path,
        )
    )
    assert "single_cc0_claim_forbidden" in failures


def test_policy_rejects_kaggle_upload_scope() -> None:
    policy, config, policy_path, config_path = load_inputs()
    policy["packaging"]["kaggle_upload_command_in_scope"] = True
    failures = required_failures(
        validate_policy(
            policy,
            policy_path=policy_path,
            dataset_config=config,
            dataset_config_path=config_path,
        )
    )
    assert "kaggle_template_only" in failures
