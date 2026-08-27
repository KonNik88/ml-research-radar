from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import BUILD_ID_PATTERN, SHA256_PATTERN
from radar_core.contracts.scientific_entity_gliner_calibration import (
    ScientificEntityCalibrationProfileName,
    ScientificEntityCalibrationTrialStage,
    ScientificEntityThresholdPolicy,
    TRIAL_ID_PATTERN,
)

DERIVATION_MANIFEST_SCHEMA_VERSION = (
    "scientific_entity_gliner_heldout_frozen_policy_derivation_manifest_v0.1"
)


class ScientificEntityGLiNERHeldoutPolicyDerivationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[DERIVATION_MANIFEST_SCHEMA_VERSION]
    build_id: str = Field(pattern=BUILD_ID_PATTERN)
    generated_at_utc: datetime

    heldout_review_id: str = Field(pattern=BUILD_ID_PATTERN)
    heldout_document_count: int = Field(ge=1)
    heldout_sample_path: str = Field(min_length=1)
    heldout_sample_sha256: str = Field(pattern=SHA256_PATTERN)
    preparation_manifest_path: str = Field(min_length=1)
    preparation_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    prediction_blind_reference_preparation: Literal[True]
    heldout_dev_overlap_count: Literal[0]

    parent_build_id: str = Field(pattern=BUILD_ID_PATTERN)
    parent_manifest_path: str = Field(min_length=1)
    parent_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    parent_mentions_path: str = Field(min_length=1)
    parent_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    parent_extractor_fingerprint: str = Field(pattern=SHA256_PATTERN)

    calibration_id: str = Field(pattern=BUILD_ID_PATTERN)
    selected_profile: Literal[ScientificEntityCalibrationProfileName.BALANCED]
    selected_trial_id: str = Field(pattern=TRIAL_ID_PATTERN)
    selected_trial_stage: Literal[ScientificEntityCalibrationTrialStage.SOURCE_PAIR]
    policy_origin_is_dev_only: Literal[True]
    heldout_used_for_policy_selection: Literal[False]
    input_threshold: Literal[0.5]
    threshold_is_inclusive: Literal[True]
    policy: ScientificEntityThresholdPolicy

    input_prediction_count: int = Field(ge=1)
    selected_prediction_count: int = Field(ge=1)
    rejected_prediction_count: int = Field(ge=0)

    candidate_extractor_fingerprint: str = Field(pattern=SHA256_PATTERN)
    lineage_file: Literal["evidence_lineage.jsonl"]
    lineage_sha256: str = Field(pattern=SHA256_PATTERN)
    lineage_count: int = Field(ge=1)

    mention_id_preserved: Literal[True]
    evidence_id_recomputed: Literal[True]
    confidence_kind_preserved: Literal[True]
    confidence_score_preserved: Literal[True]
    model_inference_executed: Literal[False]
    model_downloaded: Literal[False]
    threshold_tuning_executed: Literal[False]
    canonical_truth_mutated: Literal[False]
    heldout_references_mutated: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]
    publication_ready: Literal[False]

    @model_validator(mode="after")
    def validate_manifest(self) -> "ScientificEntityGLiNERHeldoutPolicyDerivationManifest":
        if self.generated_at_utc.tzinfo is None or self.generated_at_utc.utcoffset() != timedelta(0):
            raise ValueError("generated_at_utc must use UTC offset +00:00")
        if self.input_prediction_count != self.selected_prediction_count + self.rejected_prediction_count:
            raise ValueError("selected + rejected counts must equal input count")
        if self.lineage_count != self.selected_prediction_count:
            raise ValueError("lineage_count must equal selected_prediction_count")
        return self
