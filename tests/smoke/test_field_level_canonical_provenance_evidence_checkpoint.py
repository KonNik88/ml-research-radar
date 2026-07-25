from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.validation.check_field_level_canonical_provenance_evidence_checkpoint import (
    EXPECTED_CONTRACT_SUMMARY,
    EXPECTED_EVIDENCE_SUMMARY,
    EXPECTED_REVIEW_SUMMARY,
    EXPECTED_SEMANTIC_SHA256,
    EXPECTED_STRATEGY_COUNTS,
    build_checkpoint_report,
    main,
    validate_checkpoint,
)


def _true_checks(count: int, prefix: str) -> dict[str, bool]:
    return {f"{prefix}_{index:03d}": True for index in range(count)}


def _accepted_reports() -> tuple[dict, dict, dict]:
    contract = {
        "report_name": "field_level_canonical_provenance_contract_v01",
        "schema_version": "field_level_canonical_provenance_contract_v0.1",
        "status": "read_only_static_contract_validation",
        "canonical_truth_mutated": False,
        "postgres_mutated": False,
        "provider_api_called": False,
        "reconcile_executed": False,
        "checks": _true_checks(99, "contract"),
        "summary": copy.deepcopy(EXPECTED_CONTRACT_SUMMARY),
        "verdict": {
            "ok": True,
            "required_failed_count": 0,
            "required_failed_checks": [],
            "contract_matches_current_reconciliation": True,
            "canonical_contract_change_required": False,
            "postgres_change_required": False,
            "reconciliation_behavior_change_required": False,
            "runtime_change_required": False,
        },
    }
    evidence = {
        "report_name": "field_level_canonical_provenance_evidence_check_v01",
        "schema_version": "field_level_canonical_provenance_evidence_v0.1",
        "status": "read_only_package_validation",
        "checks": _true_checks(34, "evidence"),
        "summary": copy.deepcopy(EXPECTED_EVIDENCE_SUMMARY),
        "verdict": {
            "ok": True,
            "required_failed_count": 0,
            "required_failed_checks": [],
            "evidence_package_valid": True,
            "canonical_truth_mutated": False,
            "postgres_mutated": False,
            "provider_api_called": False,
        },
    }
    review = {
        "report_name": "field_level_canonical_provenance_evidence_review_v01",
        "schema_version": "field_level_canonical_provenance_evidence_review_v0.1",
        "status": "read_only_determinism_and_regression_review",
        "checks": _true_checks(58, "review"),
        "summary": copy.deepcopy(EXPECTED_REVIEW_SUMMARY),
        "semantic_sha256": {
            "left": copy.deepcopy(EXPECTED_SEMANTIC_SHA256),
            "right": copy.deepcopy(EXPECTED_SEMANTIC_SHA256),
        },
        "strategy_counts": {
            "left": copy.deepcopy(EXPECTED_STRATEGY_COUNTS),
            "right": copy.deepcopy(EXPECTED_STRATEGY_COUNTS),
        },
        "verdict": {
            "ok": True,
            "required_failed_count": 0,
            "required_failed_checks": [],
            "accepted_bounded_baseline_confirmed": True,
            "directory_zip_input_parity_confirmed": True,
            "semantic_determinism_confirmed": True,
            "api_mutated": False,
            "canonical_truth_mutated": False,
            "graph_mutated": False,
            "postgres_mutated": False,
            "publication_performed": False,
            "qdrant_mutated": False,
            "reconcile_executed_by_review": False,
            "retrieval_mutated": False,
            "ui_mutated": False,
        },
    }
    return contract, evidence, review


def _build(contract: dict, evidence: dict, review: dict) -> dict:
    return build_checkpoint_report(
        contract_report=contract,
        evidence_report=evidence,
        review_report=review,
    )


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_checkpoint_passes_complete_accepted_fixture() -> None:
    report = _build(*_accepted_reports())

    assert report["verdict"]["ok"] is True
    assert report["verdict"]["field_level_provenance_line_complete"] is True
    assert report["verdict"]["bounded_evidence_checkpoint_ready"] is True
    assert report["summary"]["required_failed_count"] == 0
    assert report["summary"]["checks_count"] == 35


def test_checkpoint_rejects_report_identity_drift() -> None:
    contract, evidence, review = _accepted_reports()
    review["report_name"] = "wrong_review"

    report = _build(contract, evidence, review)

    assert report["checks"]["review_report_identity_exact"] is False
    assert report["verdict"]["ok"] is False


def test_checkpoint_rejects_required_check_failure() -> None:
    contract, evidence, review = _accepted_reports()
    evidence["checks"]["evidence_000"] = False
    evidence["summary"]["passed_checks_count"] = 33
    evidence["summary"]["required_failed_count"] = 1
    evidence["verdict"]["ok"] = False
    evidence["verdict"]["evidence_package_valid"] = False
    evidence["verdict"]["required_failed_count"] = 1

    report = _build(contract, evidence, review)

    assert report["checks"]["evidence_checks_all_true"] is False
    assert report["checks"]["evidence_required_failed_count_zero"] is False
    assert report["verdict"]["ok"] is False


def test_checkpoint_rejects_contract_field_count_drift() -> None:
    contract, evidence, review = _accepted_reports()
    contract["summary"]["canonical_field_count"] = 60
    contract["summary"]["classified_field_count"] = 60

    report = _build(contract, evidence, review)

    assert report["checks"]["contract_summary_exact"] is False
    assert report["checks"]["canonical_field_count_consistent"] is False
    assert report["verdict"]["ok"] is False


def test_checkpoint_rejects_evidence_counter_drift() -> None:
    contract, evidence, review = _accepted_reports()
    evidence["summary"]["field_record_count"] = 731

    report = _build(contract, evidence, review)

    assert report["checks"]["evidence_summary_exact"] is False
    assert report["checks"]["evidence_field_count_arithmetic"] is False
    assert report["checks"]["field_record_count_consistent"] is False
    assert report["verdict"]["ok"] is False


def test_checkpoint_rejects_semantic_drift() -> None:
    contract, evidence, review = _accepted_reports()
    review["summary"]["semantic_file_difference_count"] = 1
    review["semantic_sha256"]["right"]["field_evidence.jsonl"] = "0" * 64

    report = _build(contract, evidence, review)

    assert report["checks"]["review_summary_exact"] is False
    assert report["checks"]["review_semantic_sha256_exact"] is False
    assert report["checks"]["review_semantic_differences_zero"] is False
    assert report["verdict"]["ok"] is False


def test_checkpoint_rejects_safety_boundary_drift() -> None:
    contract, evidence, review = _accepted_reports()
    review["verdict"]["postgres_mutated"] = True

    report = _build(contract, evidence, review)

    assert report["checks"]["review_read_only_boundaries"] is False
    assert report["verdict"]["ok"] is False


def test_validate_checkpoint_rejects_missing_report(tmp_path: Path) -> None:
    contract, evidence, _ = _accepted_reports()
    contract_path = tmp_path / "contract.json"
    evidence_path = tmp_path / "evidence.json"
    missing_review_path = tmp_path / "missing_review.json"
    _write(contract_path, contract)
    _write(evidence_path, evidence)

    report = validate_checkpoint(
        contract_report_path=contract_path,
        evidence_report_path=evidence_path,
        review_report_path=missing_review_path,
    )

    assert report["checks"]["input_review_report_present_and_readable"] is False
    assert report["verdict"]["ok"] is False


def test_cli_no_write_passes_accepted_fixture(tmp_path: Path) -> None:
    contract, evidence, review = _accepted_reports()
    contract_path = tmp_path / "contract.json"
    evidence_path = tmp_path / "evidence.json"
    review_path = tmp_path / "review.json"
    output_dir = tmp_path / "reports"
    _write(contract_path, contract)
    _write(evidence_path, evidence)
    _write(review_path, review)

    exit_code = main(
        [
            "--contract-report",
            str(contract_path),
            "--evidence-report",
            str(evidence_path),
            "--review-report",
            str(review_path),
            "--output-dir",
            str(output_dir),
            "--strict",
            "--no-write",
        ]
    )

    assert exit_code == 0
    assert not output_dir.exists()
