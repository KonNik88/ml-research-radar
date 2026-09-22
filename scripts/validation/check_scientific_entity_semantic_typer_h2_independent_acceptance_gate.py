from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from radar_core.contracts.scientific_entity_fresh_heldout_gate import (
    load_scientific_entity_fresh_heldout_gate_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_candidate import (
    load_semantic_typer_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_fresh_heldout_sample import (
    H2FreshHeldoutSampleManifest,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_frozen_candidate import (
    FrozenH2CandidateDefinition,
    load_h2_frozen_candidate_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_acceptance_gate import (
    canonical_config_sha256,
    load_h2_independent_acceptance_gate_config,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = (
    ROOT
    / "configs"
    / "scientific_entity_semantic_typer_h2_independent_acceptance_gate_v0.3.yaml"
)
OLD_GATE_CONFIG = ROOT / "configs" / "scientific_entity_fresh_heldout_gate_v0.2.yaml"
H1_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_candidate_v0.3.yaml"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ids_sha256(ids: list[str]) -> str:
    payload = ("\n".join(sorted(ids)) + "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the frozen Scientific Entity v0.3 H2 independent acceptance "
            "gate preregistration without running inference or reading human references."
        )
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    config_path = args.config.resolve()
    config = load_h2_independent_acceptance_gate_config(config_path)
    old_gate = load_scientific_entity_fresh_heldout_gate_config(OLD_GATE_CONFIG)
    h1 = load_semantic_typer_config(H1_CONFIG)

    candidate_config_path = ROOT / config.candidate_lineage.frozen_candidate_config_path
    candidate_config = load_h2_frozen_candidate_config(candidate_config_path)
    frozen_dir = ROOT / config.candidate_lineage.frozen_candidate_dir
    frozen_manifest_path = frozen_dir / "manifest.json"
    frozen_candidate_path = frozen_dir / "frozen_candidate.json"
    frozen_manifest = _read_json(frozen_manifest_path)
    frozen_candidate = FrozenH2CandidateDefinition.model_validate(
        _read_json(frozen_candidate_path)
    )

    sample_dir = ROOT / config.fresh_heldout_lineage.sample_dir
    sample_manifest_path = sample_dir / "manifest.json"
    sample_manifest = H2FreshHeldoutSampleManifest.model_validate(
        _read_json(sample_manifest_path)
    )

    a = config.comparative_acceptance
    d = config.historical_diagnostics
    r = config.reference_adequacy
    s = config.safety

    checks: dict[str, bool] = {
        "gate_config_exists": config_path.is_file(),
        "frozen_candidate_config_exists": candidate_config_path.is_file(),
        "frozen_candidate_manifest_exists": frozen_manifest_path.is_file(),
        "frozen_candidate_definition_exists": frozen_candidate_path.is_file(),
        "fresh_sample_manifest_exists": sample_manifest_path.is_file(),
        "candidate_id_matches_frozen_config": (
            candidate_config.candidate.candidate_id == config.candidate_lineage.candidate_id
        ),
        "candidate_policy_matches_frozen_config": (
            candidate_config.selected_policy.baseline_type.value
            == config.candidate_lineage.baseline_type
            and candidate_config.selected_policy.semantic_typer_type.value
            == config.candidate_lineage.semantic_typer_type
            and candidate_config.selected_policy.score_field
            == config.candidate_lineage.score_field
            and candidate_config.selected_policy.operator == config.candidate_lineage.operator
            and candidate_config.selected_policy.threshold == config.candidate_lineage.threshold
            and candidate_config.selected_policy.preserve_baseline_otherwise
            == config.candidate_lineage.preserve_baseline_otherwise
        ),
        "freeze_manifest_hash_matches": (
            _sha256_file(frozen_manifest_path)
            == config.candidate_lineage.expected_freeze_manifest_sha256
        ),
        "frozen_candidate_hash_matches": (
            _sha256_file(frozen_candidate_path)
            == config.candidate_lineage.expected_frozen_candidate_sha256
        ),
        "frozen_candidate_identity_matches": (
            frozen_manifest.get("freeze_id") == config.candidate_lineage.freeze_id
            and frozen_manifest.get("candidate_id") == config.candidate_lineage.candidate_id
            and frozen_manifest.get("candidate_fingerprint_sha256")
            == config.candidate_lineage.candidate_fingerprint_sha256
            and frozen_candidate.candidate_id == config.candidate_lineage.candidate_id
            and frozen_candidate.candidate_fingerprint_sha256
            == config.candidate_lineage.candidate_fingerprint_sha256
        ),
        "frozen_h2_threshold_is_010": (
            frozen_candidate.baseline_type.value == "method"
            and frozen_candidate.semantic_typer_type.value == "model"
            and frozen_candidate.score_field == "score_margin"
            and frozen_candidate.operator == ">="
            and frozen_candidate.threshold == 0.1
            and frozen_candidate.preserve_baseline_otherwise
        ),
        "sample_manifest_hash_matches": (
            _sha256_file(sample_manifest_path)
            == config.fresh_heldout_lineage.expected_sample_manifest_sha256
        ),
        "sample_identity_matches": (
            sample_manifest.sample_id == config.fresh_heldout_lineage.sample_id
            and sample_manifest.review_id == config.fresh_heldout_lineage.review_id
            and sample_manifest.candidate_id == config.candidate_lineage.candidate_id
            and sample_manifest.candidate_fingerprint_sha256
            == config.candidate_lineage.candidate_fingerprint_sha256
            and sample_manifest.freeze_id == config.candidate_lineage.freeze_id
        ),
        "sample_selected_ids_hash_matches": (
            _ids_sha256(sample_manifest.selected_canonical_ids)
            == config.fresh_heldout_lineage.expected_selected_canonical_ids_sha256
        ),
        "sample_shape_is_48_docs_96_rows": (
            sample_manifest.selected_document_count
            == config.fresh_heldout_lineage.expected_document_count
            and sample_manifest.annotation_row_count
            == config.fresh_heldout_lineage.expected_annotation_row_count
        ),
        "sample_is_disjoint_from_all_120_consumed_docs": (
            sample_manifest.excluded_consumed_union_document_count
            == config.fresh_heldout_lineage.expected_consumed_union_document_count
            and sample_manifest.sample_consumed_union_overlap_count == 0
            and config.fresh_heldout_lineage.require_zero_consumed_overlap
        ),
        "sample_was_prediction_blind": (
            sample_manifest.prediction_blind
            and not sample_manifest.candidate_predictions_read_during_sampling
            and not sample_manifest.h1_predictions_read_during_sampling
            and config.fresh_heldout_lineage.require_prediction_blind
        ),
        "sample_unspent_at_gate_freeze": (
            not sample_manifest.reference_frozen
            and not sample_manifest.h2_model_inference_executed
            and not sample_manifest.evaluation_executed
            and not sample_manifest.threshold_tuning_executed
            and not sample_manifest.policy_revision_executed
        ),
        "reference_adequacy_reuses_v02_semantics": (
            r.require_all_annotation_rows_complete
            == old_gate.reference_freeze.require_all_annotation_rows_complete
            and r.require_zero_unresolved_uncertain_mentions
            == old_gate.reference_freeze.require_zero_unresolved_uncertain_mentions
            and r.minimum_reference_mentions_per_type
            == old_gate.reference_freeze.minimum_reference_mentions_per_type
            and r.required_entity_types
            == old_gate.reference_freeze.required_entity_types
            and r.candidate_inference_only_after_reference_freeze
            == old_gate.reference_freeze.candidate_inference_only_after_reference_freeze
        ),
        "comparative_gates_reuse_h1_preregistered_thresholds": (
            a.minimum_typer_coverage == h1.development_gate.minimum_typer_coverage
            and a.minimum_same_span_accuracy_delta
            == h1.development_gate.minimum_same_span_accuracy_delta
            and a.minimum_net_corrected_cases
            == h1.development_gate.minimum_net_corrected_cases
            and a.maximum_regression_rate == h1.development_gate.maximum_regression_rate
            and a.minimum_model_to_method_reduction_fraction
            == h1.development_gate.minimum_model_to_method_reduction_fraction
            and a.minimum_macro_f1_delta == -h1.development_gate.maximum_macro_f1_drop
        ),
        "exact_and_relaxed_floors_preserve_v02_continuity": (
            a.minimum_exact_f1 == old_gate.acceptance.minimum_exact_f1
            and a.exact_f1_floor_origin == old_gate.acceptance.exact_f1_floor_origin
            and a.desirable_minimum_relaxed_f1
            == old_gate.acceptance.desirable_minimum_relaxed_f1
            and not a.require_relaxed_f1_as_hard_gate
        ),
        "historical_raw_caps_are_diagnostics_not_hard_h2_gates": (
            d.historical_maximum_model_to_method_count
            == old_gate.acceptance.maximum_model_to_method_count
            and d.historical_maximum_method_to_task_count
            == old_gate.acceptance.maximum_method_to_task_count
            and d.historical_maximum_total_type_mismatch_count
            == old_gate.acceptance.maximum_total_type_mismatch_count
            and d.historical_maximum_method_semantic_sink_count
            == old_gate.acceptance.maximum_method_semantic_sink_count
            and d.historical_maximum_any_predicted_type_mismatch_sink_count
            == old_gate.acceptance.maximum_any_predicted_type_mismatch_sink_count
            and not d.historical_raw_count_caps_are_hard_h2_gates
        ),
        "comparative_error_materialization_required": (
            d.require_corrected_errors
            and d.require_introduced_regressions
            and d.require_model_to_method_direct_corrections
            and d.require_model_to_method_wrong_to_wrong
        ),
        "missing_required_denominator_fails_closed": (
            a.required_metric_missing_denominator_policy
            == "fail_closed_evidence_insufficient"
        ),
        "decision_requires_all_hard_gates": (
            a.require_reference_adequacy
            and a.require_candidate_fingerprint_match
            and a.require_all_comparative_gates
            and a.require_exact_f1_hard_gate
            and a.all_hard_gates_required_for_acceptance
            and a.no_post_heldout_tuning
        ),
        "pass_is_bounded_not_production": (
            config.decision_semantics.pass_does_not_select_production_extractor
            and config.decision_semantics.pass_does_not_authorize_full_corpus_build
            and not s.production_extractor_selection_allowed
            and not s.full_corpus_build_authorized
        ),
        "failure_consumes_heldout_for_future_design": (
            config.decision_semantics.failed_heldout_becomes_consumed_evidence
            and config.decision_semantics.future_candidate_after_failure_requires_new_independent_heldout
            and config.decision_semantics.heldout_may_not_be_reused_for_retuning_and_reacceptance
        ),
        "contract_slice_does_not_spend_heldout": (
            not s.contract_slice_reads_human_reference_results
            and not s.contract_slice_runs_baseline_inference
            and not s.contract_slice_runs_h2_inference
            and not s.contract_slice_runs_evaluation
            and not s.contract_slice_makes_acceptance_decision
            and not s.contract_slice_consumes_fresh_heldout
        ),
        "candidate_remains_frozen": (
            not s.model_inference_allowed_before_reference_freeze
            and not s.threshold_tuning_allowed
            and not s.policy_revision_allowed
            and not s.span_mutation_allowed
            and not s.taxonomy_changes_allowed
            and not s.canonical_truth_mutation_allowed
        ),
    }

    failed = [name for name, passed in checks.items() if not passed]

    print("[OK] report=scientific_entity_semantic_typer_h2_independent_acceptance_gate_v03_contract")
    print(f"[OK] status={config.layer.status}")
    print(f"[OK] candidate_id={config.candidate_lineage.candidate_id}")
    print(f"[OK] candidate_fingerprint={config.candidate_lineage.candidate_fingerprint_sha256}")
    print(f"[OK] sample_id={config.fresh_heldout_lineage.sample_id}")
    print(f"[OK] gate_config_sha256={canonical_config_sha256(config)}")
    print(f"[OK] hard_minimum_typer_coverage={a.minimum_typer_coverage}")
    print(f"[OK] hard_minimum_same_span_accuracy_delta={a.minimum_same_span_accuracy_delta}")
    print(f"[OK] hard_minimum_net_corrected_cases={a.minimum_net_corrected_cases}")
    print(f"[OK] hard_maximum_regression_rate={a.maximum_regression_rate}")
    print(f"[OK] hard_minimum_model_to_method_reduction_fraction={a.minimum_model_to_method_reduction_fraction}")
    print(f"[OK] hard_minimum_macro_f1_delta={a.minimum_macro_f1_delta}")
    print(f"[OK] hard_minimum_exact_f1={a.minimum_exact_f1}")
    print(f"[OK] desirable_minimum_relaxed_f1={a.desirable_minimum_relaxed_f1}")
    print(f"[OK] required_check_count={len(checks)}")
    print(f"[OK] required_failed_count={len(failed)}")
    for name in failed:
        print(f"[FAIL] {name}")

    if args.strict and failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
