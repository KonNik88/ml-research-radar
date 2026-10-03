"""Read-only validation for the preregistered H2 production-authorization gate."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_acceptance_decision import (
    H2IndependentDecisionRecord,
    canonical_config_sha256 as acceptance_decision_config_sha256,
    load_h2_independent_decision_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_acceptance_gate import (
    load_h2_independent_acceptance_gate_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_authorization_gate import (
    H2ProductionAuthorizationGateConfig,
    canonical_config_sha256,
    load_h2_production_authorization_gate_config,
)
from radar_core.entities.scientific_entity_semantic_typer_h2_independent_acceptance_decision import (
    DEFAULT_CANONICAL,
    validate_h2_independent_acceptance_decision,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_authorization_gate_v0.3.yaml"
REPORT_NAME = "scientific_entity_semantic_typer_h2_production_authorization_gate_v03"


def _read_json(path: Path) -> dict[str, Any]:
    import json
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def validate_h2_production_authorization_gate(
    *,
    project_root: Path,
    config_path: Path,
    decision_dir: Path,
    evaluation_dir: Path,
    inference_dir: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    previous_heldout_sample_dir: Path,
    frozen_candidate_dir: Path,
    canonical_path: Path = DEFAULT_CANONICAL,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    config: H2ProductionAuthorizationGateConfig = load_h2_production_authorization_gate_config(config_path)
    add("gate_config_schema_valid", True)
    add("gate_config_is_non_authorizing", not config.safety.gate_slice_authorizes_full_corpus_candidate_build)
    add("gate_config_does_not_promote_latest", not config.safety.gate_slice_authorizes_latest_promotion)
    add("gate_config_forbids_latest_overwrite", not config.safety.overwrite_latest_allowed)
    add("gate_config_forbids_canonical_mutation", not config.safety.canonical_truth_mutation_allowed)
    add("future_authorization_requires_exact_canonical_snapshot", config.future_authorization_boundary.authorization_must_bind_exact_canonical_snapshot)
    add("future_authorization_requires_separate_promotion", config.production_authorization_prerequisites.require_separate_promotion_decision)

    decision_config_path = project_root / config.acceptance_lineage.acceptance_decision_config_path
    decision_config = load_h2_independent_decision_config(decision_config_path)
    add(
        "acceptance_decision_config_sha_matches",
        acceptance_decision_config_sha256(decision_config)
        == config.acceptance_lineage.acceptance_decision_config_sha256,
    )
    add(
        "candidate_identity_matches_acceptance_decision_config",
        decision_config.candidate.candidate_id == config.acceptance_lineage.candidate_id
        and decision_config.candidate.candidate_fingerprint_sha256
        == config.acceptance_lineage.candidate_fingerprint_sha256,
    )

    acceptance_gate_path = project_root / decision_config.frozen_inputs.gate_config_path
    acceptance_gate = load_h2_independent_acceptance_gate_config(acceptance_gate_path)
    policy = config.bounded_intervention
    frozen = acceptance_gate.candidate_lineage
    add(
        "frozen_h2_policy_matches",
        frozen.baseline_type == policy.baseline_type
        and frozen.semantic_typer_type == policy.semantic_typer_type
        and frozen.score_field == policy.score_field
        and frozen.operator == policy.operator
        and frozen.threshold == policy.threshold
        and frozen.preserve_baseline_otherwise == policy.preserve_baseline_otherwise,
    )
    add(
        "bounded_policy_forbids_scope_expansion",
        not policy.span_mutation_allowed
        and not policy.span_split_merge_allowed
        and not policy.new_span_generation_allowed
        and not policy.taxonomy_changes_allowed
        and not policy.threshold_tuning_allowed
        and not policy.policy_revision_allowed,
    )

    upstream_checks, upstream_summary = validate_h2_independent_acceptance_decision(
        project_root=project_root,
        config_path=decision_config_path,
        decision_dir=decision_dir,
        evaluation_dir=evaluation_dir,
        inference_dir=inference_dir,
        sample_dir=sample_dir,
        reference_dir=reference_dir,
        development_package_dir=development_package_dir,
        previous_heldout_sample_dir=previous_heldout_sample_dir,
        frozen_candidate_dir=frozen_candidate_dir,
        canonical_path=canonical_path,
    )
    add(
        "acceptance_decision_strict_validation_passes",
        upstream_summary.get("required_failed_count")
        == config.acceptance_lineage.expected_decision_validation_required_failed_count,
        upstream_summary.get("required_failed_count"),
    )
    add(
        "acceptance_decision_validation_check_count_matches",
        upstream_summary.get("total_checks")
        == config.acceptance_lineage.expected_decision_validation_total_checks,
        upstream_summary.get("total_checks"),
    )
    add(
        "all_upstream_decision_checks_pass",
        all(ok for _, ok, _ in upstream_checks),
    )

    decision = H2IndependentDecisionRecord.model_validate(_read_json(decision_dir / "decision.json"))
    add(
        "accepted_decision_identity_matches",
        decision.decision_id == config.acceptance_lineage.acceptance_decision_id
        and decision.candidate_id == config.acceptance_lineage.candidate_id
        and decision.candidate_fingerprint_sha256
        == config.acceptance_lineage.candidate_fingerprint_sha256,
    )
    add(
        "accepted_decision_is_required_acceptance",
        decision.decision == config.acceptance_lineage.required_acceptance_decision
        and decision.all_hard_gates_passed,
    )
    add(
        "accepted_decision_did_not_authorize_production",
        not decision.production_extractor_selected
        and not decision.full_corpus_build_authorized
        and not decision.canonical_truth_mutated,
    )

    failed = sum(not ok for _, ok, _ in checks)
    summary = {
        "report": REPORT_NAME,
        "gate_config_sha256": canonical_config_sha256(config),
        "candidate_id": config.acceptance_lineage.candidate_id,
        "candidate_fingerprint_sha256": config.acceptance_lineage.candidate_fingerprint_sha256,
        "acceptance_decision_id": config.acceptance_lineage.acceptance_decision_id,
        "accepted_independent_decision_verified": failed == 0,
        "production_authorization_made": False,
        "full_corpus_candidate_build_authorized": False,
        "production_latest_promotion_authorized": False,
        "canonical_truth_mutated": False,
        "total_checks": len(checks),
        "required_failed_count": failed,
        "next_slice": config.next_steps.after_gate_validation if failed == 0 else None,
    }
    return checks, summary
