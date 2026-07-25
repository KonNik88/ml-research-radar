"""Validate the Field-Level Canonical Provenance Evidence line checkpoint.

This validator is intentionally read-only and fail-closed. It aggregates the
accepted static contract report, bounded evidence-package validation report,
and semantic review/hardening report into one final checkpoint verdict.

It does not rebuild evidence, execute reconciliation, mutate canonical truth,
materialize Postgres, touch retrieval/Qdrant/ranking/graph/API/UI, call provider
APIs, or publish anything.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


REPORT_NAME = "field_level_canonical_provenance_evidence_checkpoint_v01"
SCHEMA_VERSION = "field_level_canonical_provenance_evidence_checkpoint_v0.1"
STATUS = "read_only_line_checkpoint"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DIR = PROJECT_ROOT / "artifacts" / "reports" / "validation"
DEFAULT_CONTRACT_REPORT = (
    DEFAULT_REPORT_DIR / "field_level_canonical_provenance_contract_v01_latest.json"
)
DEFAULT_EVIDENCE_REPORT = (
    DEFAULT_REPORT_DIR / "field_level_canonical_provenance_evidence_v01_latest.json"
)
DEFAULT_REVIEW_REPORT = (
    DEFAULT_REPORT_DIR
    / "field_level_canonical_provenance_evidence_review_v01_latest.json"
)

EXPECTED_REPORT_IDENTITY = {
    "contract": {
        "report_name": "field_level_canonical_provenance_contract_v01",
        "schema_version": "field_level_canonical_provenance_contract_v0.1",
        "status": "read_only_static_contract_validation",
    },
    "evidence": {
        "report_name": "field_level_canonical_provenance_evidence_check_v01",
        "schema_version": "field_level_canonical_provenance_evidence_v0.1",
        "status": "read_only_package_validation",
    },
    "review": {
        "report_name": "field_level_canonical_provenance_evidence_review_v01",
        "schema_version": "field_level_canonical_provenance_evidence_review_v0.1",
        "status": "read_only_determinism_and_regression_review",
    },
}

EXPECTED_CONTRACT_SUMMARY = {
    "assembly_field_count": 59,
    "canonical_field_count": 61,
    "checks_count": 99,
    "classified_field_count": 61,
    "failed_checks_count": 0,
    "passed_checks_count": 99,
    "strategy_kind_count": 14,
}
EXPECTED_EVIDENCE_SUMMARY = {
    "candidate_count_mismatch_count": 0,
    "canonical_field_count": 61,
    "checks_count": 34,
    "checksum_mismatch_count": 0,
    "duplicate_record_id_count": 0,
    "duplicate_record_key_count": 0,
    "field_coverage_failure_count": 0,
    "field_record_count": 732,
    "foreign_observation_id_count": 0,
    "paper_count": 12,
    "passed_checks_count": 34,
    "required_failed_count": 0,
    "selected_not_field_contributing_count": 0,
    "value_mismatch_count": 0,
}
EXPECTED_REVIEW_SUMMARY = {
    "canonical_field_count": 61,
    "checks_count": 58,
    "comparison_match_count": 708,
    "contributing_source_observation_count": 33,
    "field_record_count": 732,
    "paper_count": 12,
    "passed_checks_count": 58,
    "record_content_difference_count": 0,
    "record_key_difference_count": 0,
    "required_failed_count": 0,
    "runtime_default_record_count": 24,
    "semantic_file_difference_count": 0,
    "semantic_files_compared_count": 3,
    "strategy_family_count": 14,
    "unmatched_source_link_count": 0,
    "value_mismatch_count": 0,
}
EXPECTED_SEMANTIC_SHA256 = {
    "field_evidence.jsonl": (
        "d3a42644e51854226343e98f048856a16b2f9cd52289bb3dd6e5676f751077b0"
    ),
    "paper_summary.jsonl": (
        "dc3d3ab43d4bc3bf82c14593f0b274f8989efbd7bd79694c5a397f7b58d7356d"
    ),
    "data_quality_summary.json": (
        "825d49a0f5b1b95be39a6bff77a000adc03842c8290c758716a202b04bb52236"
    ),
}
EXPECTED_STRATEGY_COUNTS = {
    "aggregate_max": 36,
    "aggregate_min": 36,
    "boolean_evidence": 84,
    "derived_flag": 36,
    "derived_score": 12,
    "identity_derived": 24,
    "merged_identifier_map": 24,
    "ordered_first": 120,
    "ordered_union": 144,
    "row_level_provenance": 36,
    "runtime_default": 24,
    "winner": 96,
    "winner_with_normalization": 48,
    "winner_with_quality_rank": 12,
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str
    details: dict[str, Any] | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ts_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _check(
    checks: list[CheckResult],
    name: str,
    ok: bool,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    checks.append(CheckResult(name=name, ok=bool(ok), message=message, details=details))


def _mapping_mismatches(
    actual: Mapping[str, Any], expected: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    return {
        key: {"expected": expected_value, "actual": actual.get(key)}
        for key, expected_value in expected.items()
        if actual.get(key) != expected_value
    }


def _all_checks_true(report: Mapping[str, Any], expected_count: int) -> bool:
    checks = report.get("checks")
    return (
        isinstance(checks, Mapping)
        and len(checks) == expected_count
        and all(value is True for value in checks.values())
    )


def _safe_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _product_equals(left: Any, right: Any, expected: Any) -> bool:
    left_int = _safe_int(left)
    right_int = _safe_int(right)
    expected_int = _safe_int(expected)
    return (
        left_int is not None
        and right_int is not None
        and expected_int is not None
        and left_int * right_int == expected_int
    )


def _sum_equals(left: Any, right: Any, expected: Any) -> bool:
    left_int = _safe_int(left)
    right_int = _safe_int(right)
    expected_int = _safe_int(expected)
    return (
        left_int is not None
        and right_int is not None
        and expected_int is not None
        and left_int + right_int == expected_int
    )


def _required_failed_count(report: Mapping[str, Any]) -> int | None:
    summary = _as_dict(report.get("summary"))
    verdict = _as_dict(report.get("verdict"))
    for value in (
        summary.get("required_failed_count"),
        verdict.get("required_failed_count"),
        report.get("required_failed_count"),
    ):
        if isinstance(value, int):
            return value
    return None


def _identity_checks(
    checks: list[CheckResult], name: str, report: Mapping[str, Any]
) -> None:
    expected = EXPECTED_REPORT_IDENTITY[name]
    actual = {
        "report_name": report.get("report_name"),
        "schema_version": report.get("schema_version"),
        "status": report.get("status"),
    }
    mismatches = _mapping_mismatches(actual, expected)
    _check(
        checks,
        f"{name}_report_identity_exact",
        not mismatches,
        f"{name.title()} report identity is exact",
        {"mismatches": mismatches, "actual": actual},
    )


def build_checkpoint_report(
    *,
    contract_report: Mapping[str, Any],
    evidence_report: Mapping[str, Any],
    review_report: Mapping[str, Any],
    input_paths: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the final checkpoint report from three already-generated reports."""

    contract = dict(contract_report)
    evidence = dict(evidence_report)
    review = dict(review_report)
    checks: list[CheckResult] = []

    _identity_checks(checks, "contract", contract)
    _identity_checks(checks, "evidence", evidence)
    _identity_checks(checks, "review", review)

    contract_summary = _as_dict(contract.get("summary"))
    evidence_summary = _as_dict(evidence.get("summary"))
    review_summary = _as_dict(review.get("summary"))
    contract_verdict = _as_dict(contract.get("verdict"))
    evidence_verdict = _as_dict(evidence.get("verdict"))
    review_verdict = _as_dict(review.get("verdict"))

    contract_summary_mismatches = _mapping_mismatches(
        contract_summary, EXPECTED_CONTRACT_SUMMARY
    )
    _check(
        checks,
        "contract_summary_exact",
        not contract_summary_mismatches,
        "Contract summary matches the accepted 99/99 baseline",
        {"mismatches": contract_summary_mismatches},
    )
    _check(
        checks,
        "contract_checks_all_true",
        _all_checks_true(contract, 99),
        "All 99 contract checks are present and true",
    )
    _check(
        checks,
        "contract_required_failed_count_zero",
        _required_failed_count(contract) == 0,
        "Contract required failure count is zero",
        {"actual": _required_failed_count(contract)},
    )
    _check(
        checks,
        "contract_verdict_green",
        contract_verdict.get("ok") is True
        and contract_verdict.get("contract_matches_current_reconciliation") is True,
        "Contract matches current reconciliation",
        {"verdict": contract_verdict},
    )
    contract_change_flags = {
        key: contract_verdict.get(key)
        for key in (
            "canonical_contract_change_required",
            "postgres_change_required",
            "reconciliation_behavior_change_required",
            "runtime_change_required",
        )
    }
    _check(
        checks,
        "contract_no_change_required",
        all(value is False for value in contract_change_flags.values()),
        "Contract requires no canonical, reconcile, Postgres, or runtime change",
        contract_change_flags,
    )
    contract_safety = {
        "canonical_truth_mutated": contract.get("canonical_truth_mutated"),
        "postgres_mutated": contract.get("postgres_mutated"),
        "provider_api_called": contract.get("provider_api_called"),
        "reconcile_executed": contract.get("reconcile_executed"),
    }
    _check(
        checks,
        "contract_read_only_boundaries",
        all(value is False for value in contract_safety.values()),
        "Contract validation preserved read-only boundaries",
        contract_safety,
    )

    evidence_summary_mismatches = _mapping_mismatches(
        evidence_summary, EXPECTED_EVIDENCE_SUMMARY
    )
    _check(
        checks,
        "evidence_summary_exact",
        not evidence_summary_mismatches,
        "Evidence package summary matches the accepted 34/34 baseline",
        {"mismatches": evidence_summary_mismatches},
    )
    _check(
        checks,
        "evidence_checks_all_true",
        _all_checks_true(evidence, 34),
        "All 34 evidence validation checks are present and true",
    )
    _check(
        checks,
        "evidence_required_failed_count_zero",
        _required_failed_count(evidence) == 0,
        "Evidence package required failure count is zero",
        {"actual": _required_failed_count(evidence)},
    )
    _check(
        checks,
        "evidence_verdict_green",
        evidence_verdict.get("ok") is True
        and evidence_verdict.get("evidence_package_valid") is True,
        "Evidence package is valid",
        {"verdict": evidence_verdict},
    )
    evidence_safety = {
        "canonical_truth_mutated": evidence_verdict.get("canonical_truth_mutated"),
        "postgres_mutated": evidence_verdict.get("postgres_mutated"),
        "provider_api_called": evidence_verdict.get("provider_api_called"),
    }
    _check(
        checks,
        "evidence_read_only_boundaries",
        all(value is False for value in evidence_safety.values()),
        "Evidence validation preserved read-only boundaries",
        evidence_safety,
    )
    _check(
        checks,
        "evidence_field_count_arithmetic",
        _product_equals(
            evidence_summary.get("paper_count"),
            evidence_summary.get("canonical_field_count"),
            evidence_summary.get("field_record_count"),
        ),
        "Evidence field-record arithmetic is 12 × 61 = 732",
        {
            "paper_count": evidence_summary.get("paper_count"),
            "canonical_field_count": evidence_summary.get("canonical_field_count"),
            "field_record_count": evidence_summary.get("field_record_count"),
        },
    )
    _check(
        checks,
        "evidence_integrity_counters_zero",
        all(
            evidence_summary.get(key) == 0
            for key in (
                "candidate_count_mismatch_count",
                "checksum_mismatch_count",
                "duplicate_record_id_count",
                "duplicate_record_key_count",
                "field_coverage_failure_count",
                "foreign_observation_id_count",
                "selected_not_field_contributing_count",
                "value_mismatch_count",
            )
        ),
        "Evidence package integrity counters are zero",
    )

    review_summary_mismatches = _mapping_mismatches(
        review_summary, EXPECTED_REVIEW_SUMMARY
    )
    _check(
        checks,
        "review_summary_exact",
        not review_summary_mismatches,
        "Review summary matches the accepted 58/58 baseline",
        {"mismatches": review_summary_mismatches},
    )
    _check(
        checks,
        "review_checks_all_true",
        _all_checks_true(review, 58),
        "All 58 semantic review checks are present and true",
    )
    _check(
        checks,
        "review_required_failed_count_zero",
        _required_failed_count(review) == 0,
        "Review required failure count is zero",
        {"actual": _required_failed_count(review)},
    )
    _check(
        checks,
        "review_verdict_green",
        review_verdict.get("ok") is True,
        "Semantic review verdict is green",
        {"verdict": review_verdict},
    )
    review_acceptance = {
        "accepted_bounded_baseline_confirmed": review_verdict.get(
            "accepted_bounded_baseline_confirmed"
        ),
        "directory_zip_input_parity_confirmed": review_verdict.get(
            "directory_zip_input_parity_confirmed"
        ),
        "semantic_determinism_confirmed": review_verdict.get(
            "semantic_determinism_confirmed"
        ),
    }
    _check(
        checks,
        "review_acceptance_flags_true",
        all(value is True for value in review_acceptance.values()),
        "Accepted bounded baseline, input parity, and semantic determinism are confirmed",
        review_acceptance,
    )
    review_safety = {
        key: review_verdict.get(key)
        for key in (
            "api_mutated",
            "canonical_truth_mutated",
            "graph_mutated",
            "postgres_mutated",
            "publication_performed",
            "qdrant_mutated",
            "reconcile_executed_by_review",
            "retrieval_mutated",
            "ui_mutated",
        )
    }
    _check(
        checks,
        "review_read_only_boundaries",
        all(value is False for value in review_safety.values()),
        "Review preserved all read-only architecture boundaries",
        review_safety,
    )

    semantic_sha = _as_dict(review.get("semantic_sha256"))
    left_sha = _as_dict(semantic_sha.get("left"))
    right_sha = _as_dict(semantic_sha.get("right"))
    left_sha_mismatches = _mapping_mismatches(left_sha, EXPECTED_SEMANTIC_SHA256)
    right_sha_mismatches = _mapping_mismatches(right_sha, EXPECTED_SEMANTIC_SHA256)
    _check(
        checks,
        "review_semantic_sha256_exact",
        not left_sha_mismatches and not right_sha_mismatches,
        "Both reviewed runs match the accepted semantic SHA-256 baseline",
        {
            "left_mismatches": left_sha_mismatches,
            "right_mismatches": right_sha_mismatches,
        },
    )

    strategy_counts = _as_dict(review.get("strategy_counts"))
    left_strategy = _as_dict(strategy_counts.get("left"))
    right_strategy = _as_dict(strategy_counts.get("right"))
    left_strategy_mismatches = _mapping_mismatches(
        left_strategy, EXPECTED_STRATEGY_COUNTS
    )
    right_strategy_mismatches = _mapping_mismatches(
        right_strategy, EXPECTED_STRATEGY_COUNTS
    )
    _check(
        checks,
        "review_strategy_counts_exact",
        not left_strategy_mismatches and not right_strategy_mismatches,
        "Both reviewed runs match all 14 accepted strategy-family counts",
        {
            "left_mismatches": left_strategy_mismatches,
            "right_mismatches": right_strategy_mismatches,
        },
    )
    _check(
        checks,
        "review_semantic_differences_zero",
        review_summary.get("semantic_files_compared_count") == 3
        and review_summary.get("semantic_file_difference_count") == 0,
        "Three semantic files were compared with zero differences",
    )
    _check(
        checks,
        "review_record_differences_zero",
        review_summary.get("record_key_difference_count") == 0
        and review_summary.get("record_content_difference_count") == 0,
        "Record keys and record content have zero differences",
    )
    _check(
        checks,
        "review_link_and_value_failures_zero",
        review_summary.get("unmatched_source_link_count") == 0
        and review_summary.get("value_mismatch_count") == 0,
        "Review has zero unmatched source links and value mismatches",
    )
    _check(
        checks,
        "review_comparison_partition_arithmetic",
        _sum_equals(
            review_summary.get("comparison_match_count"),
            review_summary.get("runtime_default_record_count"),
            review_summary.get("field_record_count"),
        ),
        "Review comparison partition is 708 + 24 = 732",
    )

    _check(
        checks,
        "canonical_field_count_consistent",
        contract_summary.get("canonical_field_count")
        == evidence_summary.get("canonical_field_count")
        == review_summary.get("canonical_field_count")
        == 61,
        "Canonical field count is consistently 61 across the full line",
    )
    _check(
        checks,
        "paper_count_consistent",
        evidence_summary.get("paper_count") == review_summary.get("paper_count") == 12,
        "Bounded paper count is consistently 12",
    )
    _check(
        checks,
        "field_record_count_consistent",
        evidence_summary.get("field_record_count")
        == review_summary.get("field_record_count")
        == 732,
        "Field evidence record count is consistently 732",
    )
    _check(
        checks,
        "strategy_family_count_consistent",
        contract_summary.get("strategy_kind_count")
        == review_summary.get("strategy_family_count")
        == len(EXPECTED_STRATEGY_COUNTS)
        == 14,
        "Strategy taxonomy is consistently 14 families",
    )
    _check(
        checks,
        "value_mismatch_count_consistent_zero",
        evidence_summary.get("value_mismatch_count")
        == review_summary.get("value_mismatch_count")
        == 0,
        "Value mismatch count is consistently zero",
    )
    _check(
        checks,
        "source_reconstructable_partition_exact",
        review_summary.get("comparison_match_count") == 708
        and review_summary.get("runtime_default_record_count") == 24,
        "Accepted partition is 708 source-reconstructable plus 24 runtime-default records",
    )
    _check(
        checks,
        "accepted_report_chain_green",
        contract_verdict.get("ok") is True
        and evidence_verdict.get("ok") is True
        and review_verdict.get("ok") is True,
        "Contract, evidence validation, and semantic review are all green",
    )

    failed = [check.name for check in checks if not check.ok]
    result_checks = {check.name: check.ok for check in checks}
    details = {
        check.name: check.details
        for check in checks
        if check.details is not None and (not check.ok or check.details)
    }
    summary = {
        "checks_count": len(checks),
        "passed_checks_count": len(checks) - len(failed),
        "required_failed_count": len(failed),
        "contract_checks_count": contract_summary.get("checks_count"),
        "evidence_checks_count": evidence_summary.get("checks_count"),
        "review_checks_count": review_summary.get("checks_count"),
        "canonical_field_count": review_summary.get("canonical_field_count"),
        "paper_count": review_summary.get("paper_count"),
        "contributing_source_observation_count": review_summary.get(
            "contributing_source_observation_count"
        ),
        "field_record_count": review_summary.get("field_record_count"),
        "comparison_match_count": review_summary.get("comparison_match_count"),
        "runtime_default_record_count": review_summary.get(
            "runtime_default_record_count"
        ),
        "strategy_family_count": review_summary.get("strategy_family_count"),
        "semantic_files_compared_count": review_summary.get(
            "semantic_files_compared_count"
        ),
        "semantic_file_difference_count": review_summary.get(
            "semantic_file_difference_count"
        ),
        "record_key_difference_count": review_summary.get(
            "record_key_difference_count"
        ),
        "record_content_difference_count": review_summary.get(
            "record_content_difference_count"
        ),
        "value_mismatch_count": review_summary.get("value_mismatch_count"),
        "unmatched_source_link_count": review_summary.get(
            "unmatched_source_link_count"
        ),
    }
    ok = not failed
    return {
        "report_name": REPORT_NAME,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "generated_at_utc": utc_now_iso(),
        "inputs": {
            key: normalize_path(Path(str(value)))
            for key, value in (input_paths or {}).items()
        },
        "accepted_baseline": {
            "contract_summary": EXPECTED_CONTRACT_SUMMARY,
            "evidence_summary": EXPECTED_EVIDENCE_SUMMARY,
            "review_summary": EXPECTED_REVIEW_SUMMARY,
            "semantic_sha256": EXPECTED_SEMANTIC_SHA256,
            "strategy_counts": EXPECTED_STRATEGY_COUNTS,
        },
        "checks": result_checks,
        "check_details": details,
        "summary": summary,
        "verdict": {
            "ok": ok,
            "field_level_provenance_line_complete": ok,
            "bounded_evidence_checkpoint_ready": ok,
            "required_failed_checks": failed,
            "required_failed_count": len(failed),
            "canonical_truth_mutated": False,
            "reconcile_executed_by_checkpoint": False,
            "postgres_mutated": False,
            "retrieval_mutated": False,
            "qdrant_mutated": False,
            "ranking_mutated": False,
            "graph_mutated": False,
            "api_mutated": False,
            "ui_mutated": False,
            "provider_api_called": False,
            "publication_performed": False,
            "full_corpus_materialization_performed": False,
            "may_be_used_as_reconcile_input": False,
            "next_slice": "separate_post_checkpoint_architectural_decision",
        },
    }


def build_markdown(report: Mapping[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    verdict = _as_dict(report.get("verdict"))
    lines = [
        "# Field-Level Canonical Provenance Evidence Checkpoint v0.1",
        "",
        f"- Generated at: `{report.get('generated_at_utc')}`",
        f"- Status: `{report.get('status')}`",
        f"- OK: `{verdict.get('ok')}`",
        f"- Line complete: `{verdict.get('field_level_provenance_line_complete')}`",
        f"- Checkpoint ready: `{verdict.get('bounded_evidence_checkpoint_ready')}`",
        "",
        "## Inputs",
    ]
    inputs = _as_dict(report.get("inputs"))
    if inputs:
        for key, value in inputs.items():
            lines.append(f"- {key}: `{value}`")
    else:
        lines.append("- none recorded")
    lines.extend(["", "## Summary"])
    for key, value in summary.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Required failures"])
    failures = verdict.get("required_failed_checks") or []
    if failures:
        lines.extend(f"- `{name}`" for name in failures)
    else:
        lines.append("- none")
    lines.extend(["", "## Safety boundaries"])
    for key in (
        "canonical_truth_mutated",
        "reconcile_executed_by_checkpoint",
        "postgres_mutated",
        "retrieval_mutated",
        "qdrant_mutated",
        "ranking_mutated",
        "graph_mutated",
        "api_mutated",
        "ui_mutated",
        "provider_api_called",
        "publication_performed",
        "full_corpus_materialization_performed",
        "may_be_used_as_reconcile_input",
    ):
        lines.append(f"- {key}: `{verdict.get(key)}`")
    return "\n".join(lines) + "\n"


def write_reports(report: Mapping[str, Any], output_dir: Path) -> dict[str, str]:
    run_ts = ts_slug()
    latest_json = (
        output_dir
        / "field_level_canonical_provenance_evidence_checkpoint_v01_latest.json"
    )
    latest_md = latest_json.with_suffix(".md")
    history_json = (
        output_dir
        / "history"
        / f"field_level_canonical_provenance_evidence_checkpoint_v01_{run_ts}.json"
    )
    history_md = history_json.with_suffix(".md")
    write_json(latest_json, report)
    write_text(latest_md, build_markdown(report))
    write_json(history_json, report)
    write_text(history_md, build_markdown(report))
    return {
        "latest_json": normalize_path(latest_json),
        "latest_md": normalize_path(latest_md),
        "history_json": normalize_path(history_json),
        "history_md": normalize_path(history_md),
    }


def validate_checkpoint(
    *,
    contract_report_path: Path = DEFAULT_CONTRACT_REPORT,
    evidence_report_path: Path = DEFAULT_EVIDENCE_REPORT,
    review_report_path: Path = DEFAULT_REVIEW_REPORT,
) -> dict[str, Any]:
    paths = {
        "contract_report": contract_report_path,
        "evidence_report": evidence_report_path,
        "review_report": review_report_path,
    }
    payloads: dict[str, dict[str, Any]] = {}
    input_errors: dict[str, str] = {}
    for name, path in paths.items():
        try:
            payloads[name.removesuffix("_report")] = load_json(path)
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            payloads[name.removesuffix("_report")] = {}
            input_errors[name] = f"{type(exc).__name__}: {exc}"

    report = build_checkpoint_report(
        contract_report=payloads["contract"],
        evidence_report=payloads["evidence"],
        review_report=payloads["review"],
        input_paths=paths,
    )
    report["input_errors"] = input_errors
    if input_errors:
        checks = dict(report["checks"])
        for name in paths:
            check_name = f"input_{name}_present_and_readable"
            checks[check_name] = name not in input_errors
        failures = [name for name, ok in checks.items() if not ok]
        report["checks"] = checks
        report["summary"]["checks_count"] = len(checks)
        report["summary"]["passed_checks_count"] = len(checks) - len(failures)
        report["summary"]["required_failed_count"] = len(failures)
        report["verdict"]["ok"] = False
        report["verdict"]["field_level_provenance_line_complete"] = False
        report["verdict"]["bounded_evidence_checkpoint_ready"] = False
        report["verdict"]["required_failed_checks"] = failures
        report["verdict"]["required_failed_count"] = len(failures)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the final bounded Field-Level Canonical Provenance Evidence "
            "v0.1 checkpoint from existing contract, evidence, and review reports."
        )
    )
    parser.add_argument(
        "--contract-report", type=Path, default=DEFAULT_CONTRACT_REPORT
    )
    parser.add_argument(
        "--evidence-report", type=Path, default=DEFAULT_EVIDENCE_REPORT
    )
    parser.add_argument("--review-report", type=Path, default=DEFAULT_REVIEW_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_checkpoint(
        contract_report_path=args.contract_report,
        evidence_report_path=args.evidence_report,
        review_report_path=args.review_report,
    )
    if not args.no_write:
        report["report_paths"] = write_reports(report, args.output_dir)

    summary = report["summary"]
    verdict = report["verdict"]
    prefix = "OK" if verdict["ok"] else "FAIL"
    print(f"[{prefix}] report_name={REPORT_NAME}")
    print(f"[{prefix}] checks_count={summary['checks_count']}")
    print(f"[{prefix}] passed_checks_count={summary['passed_checks_count']}")
    print(f"[{prefix}] canonical_field_count={summary['canonical_field_count']}")
    print(f"[{prefix}] paper_count={summary['paper_count']}")
    print(f"[{prefix}] field_record_count={summary['field_record_count']}")
    print(f"[{prefix}] strategy_family_count={summary['strategy_family_count']}")
    print(
        f"[{prefix}] semantic_file_difference_count="
        f"{summary['semantic_file_difference_count']}"
    )
    print(f"[{prefix}] value_mismatch_count={summary['value_mismatch_count']}")
    print(f"[{prefix}] required_failed_count={summary['required_failed_count']}")
    print(
        f"[{prefix}] field_level_provenance_line_complete="
        f"{verdict['field_level_provenance_line_complete']}"
    )
    if verdict["required_failed_checks"]:
        print("[FAIL] Required checks:")
        for name in verdict["required_failed_checks"]:
            print(f"- {name}")
    if args.strict and not verdict["ok"]:
        return 1
    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
