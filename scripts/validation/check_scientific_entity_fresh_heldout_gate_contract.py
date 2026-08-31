from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from radar_core.contracts.scientific_entity_fresh_heldout_gate import (
    ENTITY_TYPES,
    canonical_config_sha256,
    load_scientific_entity_fresh_heldout_gate_config,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_fresh_heldout_gate_v0.2.yaml"


def _load_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected YAML mapping: {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the frozen Scientific Entity fresh v0.2 prediction-blind "
            "held-out acceptance-gate design."
        )
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    config_path = args.config.resolve()
    config = load_scientific_entity_fresh_heldout_gate_config(config_path)

    runtime_path = ROOT / config.candidate.raw_runtime_config_path
    policy_path = ROOT / config.candidate.policy_config_path
    comparison_path = ROOT / config.candidate.comparison_config_path

    runtime = _load_yaml(runtime_path)
    policy = _load_yaml(policy_path)
    comparison = _load_yaml(comparison_path)

    p = policy["policy"]["source_field_thresholds"]
    candidate = comparison["candidate"]

    checks = {
        "design_config_exists": config_path.exists(),
        "runtime_config_exists": runtime_path.exists(),
        "policy_config_exists": policy_path.exists(),
        "comparison_config_exists": comparison_path.exists(),
        "candidate_id_matches_v02c": (
            policy["candidate"]["candidate_id"] == config.candidate.candidate_id
            and candidate["candidate_id"] == config.candidate.candidate_id
        ),
        "raw_floor_matches_frozen_v02c": (
            float(runtime["inference"]["threshold"]) == config.candidate.raw_inference_floor
            and float(policy["policy"]["input_threshold"]) == config.candidate.raw_inference_floor
        ),
        "policy_thresholds_match_frozen_v02c": (
            float(p["title"]) == config.candidate.title_threshold
            and float(p["abstract"]) == config.candidate.abstract_threshold
            and policy["policy"]["entity_type_thresholds"] == {}
        ),
        "development_lineage_is_consumed_72": (
            config.development_exclusion.expected_consumed_document_count == 72
            and config.development_exclusion.expected_consumed_reference_mention_count == 1316
            and config.development_exclusion.previous_v01_heldout_is_consumed_development_for_v02
        ),
        "fresh_sample_is_48_with_96_rows": (
            config.sampling.expected_document_count == 48
            and config.sampling.expected_annotation_row_count == 96
            and config.sampling.uniform_document_count == 24
            and config.sampling.type_enriched_documents_per_type == 4
        ),
        "sampling_is_prediction_blind": (
            config.reference_freeze.prediction_blind
            and not config.reference_freeze.candidate_predictions_may_be_read_during_sampling
            and not config.reference_freeze.candidate_predictions_may_be_read_during_annotation
        ),
        "all_six_types_frozen": (
            config.reference_freeze.required_entity_types == list(ENTITY_TYPES)
            and set(config.sampling.enrichment_terms) == set(ENTITY_TYPES)
        ),
        "sample_adequacy_frozen": (
            config.reference_freeze.minimum_reference_mentions_per_type == 20
            and config.reference_freeze.require_zero_unresolved_uncertain_mentions
            and config.reference_freeze.require_all_annotation_rows_complete
        ),
        "exact_f1_floor_is_historical_independent_baseline": (
            config.acceptance.minimum_exact_f1 == 0.396882
            and config.acceptance.exact_f1_floor_origin
            == "independent_v01_heldout_exact_f1"
            and config.acceptance.require_exact_f1_hard_gate
        ),
        "relaxed_f1_remains_desirable_not_hard": (
            config.acceptance.desirable_minimum_relaxed_f1 == 0.414868
            and config.acceptance.relaxed_f1_floor_role == "desirable_not_hard"
            and not config.acceptance.require_relaxed_f1_as_hard_gate
        ),
        "semantic_guardrails_preserved": (
            config.acceptance.maximum_model_to_method_count == 43
            and config.acceptance.maximum_method_to_task_count == 25
            and config.acceptance.maximum_total_type_mismatch_count == 150
            and config.acceptance.maximum_method_semantic_sink_count == 74
            and config.acceptance.maximum_any_predicted_type_mismatch_sink_count == 74
        ),
        "no_post_heldout_tuning": config.acceptance.no_post_heldout_tuning,
        "pass_is_bounded_not_production": (
            config.decision_semantics.pass_does_not_select_production_extractor
            and config.decision_semantics.pass_does_not_authorize_full_corpus_build
            and not config.safety.production_extractor_selected
            and not config.safety.full_corpus_build_authorized
        ),
        "failure_consumes_heldout_for_future_design": (
            config.decision_semantics.failed_heldout_becomes_consumed_development_evidence
            and config.decision_semantics.future_candidate_after_failure_requires_new_independent_heldout
            and config.decision_semantics.heldout_may_not_be_reused_for_retuning_and_reacceptance
        ),
        "contract_does_not_spend_heldout": (
            not config.safety.contract_slice_selects_sample
            and not config.safety.contract_slice_runs_model_inference
            and not config.safety.contract_slice_runs_evaluation
            and not config.safety.contract_slice_consumes_fresh_heldout
        ),
        "candidate_inference_forbidden_before_reference_freeze": (
            not config.safety.model_inference_allowed_before_reference_freeze
            and config.reference_freeze.candidate_inference_only_after_reference_freeze
        ),
        "candidate_is_frozen": (
            config.candidate.prompts_frozen
            and config.candidate.model_revision_artifact_frozen
            and config.candidate.adapter_windowing_frozen
            and not config.candidate.entity_type_overrides_allowed
            and not config.safety.threshold_tuning_allowed
            and not config.safety.prompt_changes_allowed
            and not config.safety.model_changes_allowed
            and not config.safety.entity_type_changes_allowed
        ),
    }

    failed = [name for name, passed in checks.items() if not passed]

    print("[OK] report=scientific_entity_fresh_heldout_gate_v02_contract")
    print(f"[OK] status={config.layer.status}")
    print(f"[OK] candidate_id={config.candidate.candidate_id}")
    print(f"[OK] development_comparison_id={config.candidate.development_comparison_id}")
    print(f"[OK] consumed_development_document_count={config.development_exclusion.expected_consumed_document_count}")
    print(f"[OK] heldout_document_count={config.sampling.expected_document_count}")
    print(f"[OK] annotation_row_count={config.sampling.expected_annotation_row_count}")
    print(f"[OK] uniform_document_count={config.sampling.uniform_document_count}")
    print(f"[OK] type_enriched_document_count={config.sampling.type_enriched_documents_per_type * len(ENTITY_TYPES)}")
    print(f"[OK] minimum_reference_mentions_per_type={config.reference_freeze.minimum_reference_mentions_per_type}")
    print(f"[OK] raw_inference_floor={config.candidate.raw_inference_floor}")
    print(f"[OK] title_threshold={config.candidate.title_threshold}")
    print(f"[OK] abstract_threshold={config.candidate.abstract_threshold}")
    print(f"[OK] minimum_exact_f1={config.acceptance.minimum_exact_f1}")
    print(f"[OK] desirable_minimum_relaxed_f1={config.acceptance.desirable_minimum_relaxed_f1}")
    print(f"[OK] maximum_model_to_method_count={config.acceptance.maximum_model_to_method_count}")
    print(f"[OK] maximum_method_to_task_count={config.acceptance.maximum_method_to_task_count}")
    print(f"[OK] design_config_sha256={canonical_config_sha256(config)}")
    print("[OK] sample_selected=False")
    print("[OK] model_inference_executed=False")
    print("[OK] evaluation_executed=False")
    print("[OK] fresh_heldout_consumed=False")
    print("[OK] canonical_truth_mutated=False")
    print("[OK] production_extractor_selected=False")
    print("[OK] full_corpus_build_authorized=False")
    print(f"[OK] next_slice={config.next_steps.after_contract_freeze}")

    if failed:
        print(f"[FAILED] required_failed_count={len(failed)}")
        for name in failed:
            print(f"[FAILED] {name}")
        return 1 if args.strict else 0

    print(f"[OK] total_checks={len(checks)}")
    print("[OK] required_failed_count=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
