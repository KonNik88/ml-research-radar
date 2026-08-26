from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import (
    BUILD_ID_PATTERN,
    EVIDENCE_ID_PATTERN,
    MENTION_ID_PATTERN,
    SHA256_PATTERN,
)
from radar_core.contracts.scientific_entity_gliner_calibration import (
    ScientificEntityCalibrationProfileName,
    ScientificEntityCalibrationTrialStage,
    ScientificEntityThresholdPolicy,
    TRIAL_ID_PATTERN,
)


DERIVATION_MANIFEST_SCHEMA_VERSION = (
    "scientific_entity_gliner_frozen_policy_derivation_manifest_v0.1"
)
EVIDENCE_LINEAGE_SCHEMA_VERSION = (
    "scientific_entity_gliner_frozen_policy_evidence_lineage_v0.1"
)


class ScientificEntityFrozenPolicyEvidenceLineage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[EVIDENCE_LINEAGE_SCHEMA_VERSION]
    build_id: str = Field(pattern=BUILD_ID_PATTERN)
    parent_build_id: str = Field(pattern=BUILD_ID_PATTERN)
    mention_id: str = Field(pattern=MENTION_ID_PATTERN)
    parent_evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    candidate_evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)

    @model_validator(mode="after")
    def validate_identity_change(self) -> "ScientificEntityFrozenPolicyEvidenceLineage":
        if self.parent_evidence_id == self.candidate_evidence_id:
            raise ValueError("candidate evidence_id must differ from parent evidence_id")
        return self


class ScientificEntityGLiNERFrozenPolicyDerivationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[DERIVATION_MANIFEST_SCHEMA_VERSION]
    build_id: str = Field(pattern=BUILD_ID_PATTERN)
    generated_at_utc: datetime

    parent_build_id: str = Field(pattern=BUILD_ID_PATTERN)
    parent_manifest_path: str = Field(min_length=1)
    parent_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    parent_mentions_path: str = Field(min_length=1)
    parent_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    parent_extractor_fingerprint: str = Field(pattern=SHA256_PATTERN)

    calibration_id: str = Field(pattern=BUILD_ID_PATTERN)
    calibration_manifest_path: str = Field(min_length=1)
    calibration_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    calibration_trials_path: str = Field(min_length=1)
    calibration_trials_sha256: str = Field(pattern=SHA256_PATTERN)
    calibration_profiles_path: str = Field(min_length=1)
    calibration_profiles_sha256: str = Field(pattern=SHA256_PATTERN)
    selected_profile: Literal[ScientificEntityCalibrationProfileName.BALANCED]
    selected_trial_id: str = Field(pattern=TRIAL_ID_PATTERN)
    selected_trial_stage: Literal[ScientificEntityCalibrationTrialStage.SOURCE_PAIR]

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
    calibration_id_written_to_mentions: Literal[False]

    model_inference_executed: Literal[False]
    model_downloaded: Literal[False]
    provider_api_called: Literal[False]
    canonical_truth_mutated: Literal[False]
    may_be_used_as_reconcile_input: Literal[False]
    current_dev_set_becomes_held_out: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]
    publication_ready: Literal[False]

    @model_validator(mode="after")
    def validate_manifest(self) -> "ScientificEntityGLiNERFrozenPolicyDerivationManifest":
        if (
            self.generated_at_utc.tzinfo is None
            or self.generated_at_utc.utcoffset() != timedelta(0)
        ):
            raise ValueError("generated_at_utc must use UTC offset +00:00")
        if self.input_prediction_count != (
            self.selected_prediction_count + self.rejected_prediction_count
        ):
            raise ValueError("selected + rejected counts must equal input count")
        if self.lineage_count != self.selected_prediction_count:
            raise ValueError("lineage_count must equal selected_prediction_count")
        return self
