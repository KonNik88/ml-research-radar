from __future__ import annotations

from radar_core.contracts.scientific_entity_evidence import (
    ConfidenceKind,
    MENTION_SCHEMA_VERSION,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    ScientificEntityType,
    build_evidence_id,
    build_mention_id,
    sha256_text,
)
from radar_core.contracts.scientific_entity_semantic_prompt_raw_floor_policy import (
    RawFloorPolicyDerivationManifest,
    load_raw_floor_policy_config,
)
from radar_core.entities.scientific_entity_semantic_prompt_raw_floor_policy import (
    DEFAULT_CONFIG_PATH,
    _materialize,
    _threshold_policy,
)


def _mention(field: ScientificEntitySourceField, text: str, start: int, end: int, kind: ScientificEntityType, score: float) -> ScientificEntityMentionEvidence:
    source_sha = sha256_text(text)
    mention_id = build_mention_id(
        canonical_id="fixture-doc",
        source_field=field,
        source_text_sha256=source_sha,
        char_start=start,
        char_end=end,
        entity_type=kind,
    )
    fingerprint = "a" * 64
    return ScientificEntityMentionEvidence(
        schema_version=MENTION_SCHEMA_VERSION,
        evidence_id=build_evidence_id(mention_id=mention_id, extractor_fingerprint=fingerprint),
        mention_id=mention_id,
        build_id="raw-build",
        canonical_id="fixture-doc",
        entity_type=kind,
        source_field=field,
        source_text_sha256=source_sha,
        char_start=start,
        char_end=end,
        surface_text=text[start:end],
        extractor_fingerprint=fingerprint,
        confidence_kind=ConfidenceKind.MODEL_SCORE,
        confidence_score=score,
        calibration_id=None,
    )


def test_config_freezes_selected_v02c_policy() -> None:
    config = load_raw_floor_policy_config(DEFAULT_CONFIG_PATH)
    assert config.candidate.calibration_id == "scientific-entity-semantic-prompt-raw-floor-calibration-v0.2c-20260830T104242195583Z"
    assert config.candidate.selected_trial_id == "calibration-trial:adcd020d8bce5af1ff157f4303e0b171"
    assert config.candidate.expected_raw_prediction_count == 1762
    assert config.policy.input_threshold == 0.4
    assert config.policy.source_field_thresholds[ScientificEntitySourceField.TITLE] == 0.45
    assert config.policy.source_field_thresholds[ScientificEntitySourceField.ABSTRACT] == 0.625
    assert config.safety.fresh_heldout_consumption_allowed is False


def test_threshold_policy_matches_frozen_values() -> None:
    config = load_raw_floor_policy_config(DEFAULT_CONFIG_PATH)
    policy = _threshold_policy(config)
    assert policy.default_threshold == 0.4
    assert policy.source_field_thresholds[ScientificEntitySourceField.TITLE] == 0.45
    assert policy.source_field_thresholds[ScientificEntitySourceField.ABSTRACT] == 0.625


def test_materialization_filters_without_changing_mentions_or_scores() -> None:
    config = load_raw_floor_policy_config(DEFAULT_CONFIG_PATH)
    parents = [
        _mention(ScientificEntitySourceField.TITLE, "Alpha Beta", 0, 5, ScientificEntityType.MODEL, 0.46),
        _mention(ScientificEntitySourceField.TITLE, "Alpha Beta", 6, 10, ScientificEntityType.METHOD, 0.44),
        _mention(ScientificEntitySourceField.ABSTRACT, "Gamma Delta", 0, 5, ScientificEntityType.TASK, 0.70),
        _mention(ScientificEntitySourceField.ABSTRACT, "Gamma Delta", 6, 11, ScientificEntityType.METRIC, 0.62),
    ]
    rows, lineage = _materialize(
        parents,
        config,
        build_id="policy-build",
        fingerprint="b" * 64,
        parent_build_id="raw-build",
    )
    assert len(rows) == 2
    assert len(lineage) == 2
    parent_by_id = {row.mention_id: row for row in parents}
    assert all(row.mention_id in parent_by_id for row in rows)
    assert all(row.confidence_score == parent_by_id[row.mention_id].confidence_score for row in rows)
    assert all(row.evidence_id != parent_by_id[row.mention_id].evidence_id for row in rows)


def test_derivation_manifest_requires_selected_count_to_match_calibration() -> None:
    payload = dict(
        build_id="policy-build",
        parent_build_id="raw-build",
        development_package_id="dev-package",
        candidate_id="scientific-entity-semantic-prompt-raw-floor-extension-v0.2c",
        calibration_id="calibration",
        selected_trial_id="trial",
        design_config_sha256="a"*64,
        runtime_config_sha256="b"*64,
        calibration_manifest_sha256="c"*64,
        calibration_selected_policy_sha256="d"*64,
        parent_extractor_fingerprint="e"*64,
        candidate_extractor_fingerprint="f"*64,
        input_threshold=0.4,
        title_threshold=0.45,
        abstract_threshold=0.625,
        entity_type_overrides={},
        input_prediction_count=1762,
        selected_prediction_count=1000,
        rejected_prediction_count=762,
        calibration_trial_selected_prediction_count=1000,
        calibration_hard_gates_passed=True,
        calibration_candidate_promising=True,
        selected_title_at_candidate_raw_floor=False,
        mention_id_preserved=True,
        evidence_id_recomputed=True,
        confidence_preserved=True,
        model_inference_executed=False,
        threshold_tuning_executed=False,
        fresh_heldout_consumed=False,
        canonical_truth_mutated=False,
        may_be_used_as_reconcile_input=False,
        production_extractor_selected=False,
        full_corpus_build_authorized=False,
        publication_ready=False,
        future_v02_acceptance_requires_new_disjoint_heldout=True,
    )
    row = RawFloorPolicyDerivationManifest(**payload)
    assert row.selected_prediction_count == row.calibration_trial_selected_prediction_count
