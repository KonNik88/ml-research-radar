from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Sequence

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import (
    EXTRACTOR_SCHEMA_VERSION,
    ExtractorKind,
    ScientificEntityEvidenceManifest,
    ScientificEntityExtractorDescriptor,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    build_evidence_id,
    build_extractor_fingerprint,
    sha256_text,
)
from radar_core.contracts.scientific_entity_gliner_calibration import (
    ScientificEntityCalibrationProfileName,
    ScientificEntityCalibrationTrial,
    ScientificEntityCalibrationTrialStage,
    ScientificEntityThresholdPolicy,
)
from radar_core.contracts.scientific_entity_gliner_frozen_policy import (
    EVIDENCE_LINEAGE_SCHEMA_VERSION,
    ScientificEntityFrozenPolicyEvidenceLineage,
)
from radar_core.entities.scientific_entity_gliner import (
    normalized_source_bundle_revision,
    normalized_text_sha256,
)
from radar_core.entities.scientific_entity_gliner_calibration import filter_predictions


FROZEN_CONFIG_SCHEMA_VERSION = (
    "scientific_entity_gliner_frozen_policy_candidate_config_v0.1"
)
FROZEN_DEFAULT_THRESHOLD = 0.50
FROZEN_TITLE_THRESHOLD = 0.55
FROZEN_ABSTRACT_THRESHOLD = 0.65


class ScientificEntityGLiNERFrozenPolicyError(ValueError):
    """Raised when frozen-policy semantics or lineage are inconsistent."""


class FrozenLayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["scientific_entity_gliner_frozen_policy_candidate"]
    version: Literal["v0.1"]
    status: Literal["dev_frozen_candidate"]
    layer_kind: Literal["derived_policy_filtered_mention_evidence"]
    description: str = Field(min_length=1)


class FrozenExtractorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["ml_radar_gliner_small_v2_5_frozen_policy_candidate"]
    version: Literal["0.1.0"]
    environment_lock_path: str = Field(min_length=1)
    code_revision_policy: Literal["normalized_source_bundle_sha256"]
    config_fingerprint_policy: Literal["sha256_of_canonical_semantic_json"]
    parent_model_provenance_policy: Literal["inherit_and_verify"]


class FrozenDecisionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_build_id: str = Field(min_length=1)
    calibration_id: str = Field(min_length=1)
    selected_profile: Literal[ScientificEntityCalibrationProfileName.BALANCED]
    selected_trial_id: str = Field(min_length=1)
    input_threshold: Literal[0.5]
    threshold_is_inclusive: Literal[True]
    policy: ScientificEntityThresholdPolicy
    expected_input_prediction_count: int = Field(ge=1)
    expected_selected_prediction_count: int = Field(ge=1)
    expected_rejected_prediction_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_frozen_policy(self) -> "FrozenDecisionConfig":
        expected = ScientificEntityThresholdPolicy(
            default_threshold=FROZEN_DEFAULT_THRESHOLD,
            source_field_thresholds={
                ScientificEntitySourceField.TITLE: FROZEN_TITLE_THRESHOLD,
                ScientificEntitySourceField.ABSTRACT: FROZEN_ABSTRACT_THRESHOLD,
            },
            entity_type_thresholds={},
        )
        if self.policy != expected:
            raise ValueError(
                "v0.1 policy is frozen at title>=0.55, abstract>=0.65, "
                "default=0.50, with no entity-type overrides"
            )
        if self.expected_input_prediction_count != (
            self.expected_selected_prediction_count
            + self.expected_rejected_prediction_count
        ):
            raise ValueError("expected selected + rejected counts must equal input count")
        return self


class FrozenInputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_build_root: str = Field(min_length=1)
    calibration_root: str = Field(min_length=1)


class FrozenSafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_build_statuses: list[Literal["fixture", "candidate"]] = Field(min_length=1)
    accepted_status_may_be_emitted: Literal[False]
    execute_required_for_writes: Literal[True]
    overwrite_allowed: Literal[False]
    arbitrary_threshold_override_allowed: Literal[False]
    model_inference_allowed: Literal[False]
    model_or_tokenizer_download_allowed: Literal[False]
    provider_api_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    full_corpus_build_authorized: Literal[False]
    current_dev_set_becomes_held_out: Literal[False]
    publication_allowed: Literal[False]


class FrozenOutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root: str = Field(min_length=1)
    immutable_build_directory: Literal[True]
    mutable_latest_pointer: Literal[False]
    encoding: Literal["utf-8"]
    line_ending: Literal["lf"]
    required_files: list[str] = Field(min_length=8, max_length=8)

    @model_validator(mode="after")
    def validate_required_files(self) -> "FrozenOutputsConfig":
        expected = {
            "mentions.jsonl",
            "manifest.json",
            "schema.json",
            "data_quality_summary.json",
            "README.md",
            "derivation_manifest.json",
            "evidence_lineage.jsonl",
            "checksums.txt",
        }
        if set(self.required_files) != expected or len(set(self.required_files)) != 8:
            raise ValueError("frozen-policy output file contract must match exactly")
        return self


class FrozenValidationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_dir: str = Field(min_length=1)
    require_independent_validator: Literal[True]
    require_parent_build_validation: Literal[True]
    require_calibration_validation: Literal[True]
    require_selected_trial_recomputation: Literal[True]
    require_identity_recomputation: Literal[True]
    require_parent_lineage: Literal[True]
    require_checksums: Literal[True]
    require_lf_outputs: Literal[True]
    require_fail_closed_policy: Literal[True]


class ScientificEntityGLiNERFrozenPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[FROZEN_CONFIG_SCHEMA_VERSION]
    layer: FrozenLayerConfig
    extractor: FrozenExtractorConfig
    frozen: FrozenDecisionConfig
    inputs: FrozenInputsConfig
    safety: FrozenSafetyConfig
    outputs: FrozenOutputsConfig
    validation: FrozenValidationConfig


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False):
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ScientificEntityGLiNERFrozenPolicyError(
                f"duplicate YAML key in frozen-policy config: {key!r}"
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def canonical_semantic_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_gliner_frozen_policy_config(
    path: Path,
) -> ScientificEntityGLiNERFrozenPolicyConfig:
    payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    if not isinstance(payload, dict):
        raise ScientificEntityGLiNERFrozenPolicyError("config must be a YAML mapping")
    return ScientificEntityGLiNERFrozenPolicyConfig.model_validate(payload)


def gliner_frozen_policy_config_sha256(
    config: ScientificEntityGLiNERFrozenPolicyConfig,
) -> str:
    return sha256_text(canonical_semantic_json(config.model_dump(mode="json")))


def build_frozen_policy_extractor_descriptor(
    *,
    config: ScientificEntityGLiNERFrozenPolicyConfig,
    parent_manifest: ScientificEntityEvidenceManifest,
    project_root: Path,
) -> ScientificEntityExtractorDescriptor:
    parent = parent_manifest.extractor
    if (
        parent.kind != ExtractorKind.STATISTICAL_MODEL
        and parent_manifest.status.value != "fixture"
    ):
        raise ScientificEntityGLiNERFrozenPolicyError(
            "non-fixture frozen-policy parent must be a statistical_model extractor"
        )
    if parent.kind == ExtractorKind.STATISTICAL_MODEL and not all(
        (
            parent.model_name,
            parent.model_revision,
            parent.model_artifact_sha256,
            parent.model_license,
        )
    ):
        raise ScientificEntityGLiNERFrozenPolicyError(
            "parent GLiNER extractor is missing model provenance"
        )
    environment_path = Path(config.extractor.environment_lock_path)
    if not environment_path.is_absolute():
        environment_path = project_root / environment_path
    if not environment_path.is_file():
        raise FileNotFoundError(environment_path)
    return ScientificEntityExtractorDescriptor(
        schema_version=EXTRACTOR_SCHEMA_VERSION,
        name=config.extractor.name,
        version=config.extractor.version,
        kind=parent.kind,
        code_revision=normalized_source_bundle_revision(project_root),
        config_sha256=gliner_frozen_policy_config_sha256(config),
        environment_sha256=normalized_text_sha256(environment_path),
        model_name=parent.model_name,
        model_revision=parent.model_revision,
        model_artifact_sha256=parent.model_artifact_sha256,
        model_license=parent.model_license,
    )


def validate_frozen_trial(
    *,
    config: ScientificEntityGLiNERFrozenPolicyConfig,
    trial: ScientificEntityCalibrationTrial,
) -> None:
    if trial.calibration_id != config.frozen.calibration_id:
        raise ScientificEntityGLiNERFrozenPolicyError("selected trial calibration_id mismatch")
    if trial.trial_id != config.frozen.selected_trial_id:
        raise ScientificEntityGLiNERFrozenPolicyError("selected trial_id mismatch")
    if trial.stage != ScientificEntityCalibrationTrialStage.SOURCE_PAIR:
        raise ScientificEntityGLiNERFrozenPolicyError("frozen trial must be source_pair")
    if trial.policy != config.frozen.policy:
        raise ScientificEntityGLiNERFrozenPolicyError("selected trial policy mismatch")
    if trial.selected_prediction_count != config.frozen.expected_selected_prediction_count:
        raise ScientificEntityGLiNERFrozenPolicyError("selected trial prediction count mismatch")
    if trial.rejected_prediction_count != config.frozen.expected_rejected_prediction_count:
        raise ScientificEntityGLiNERFrozenPolicyError("selected trial rejected count mismatch")


def materialize_frozen_policy_mentions(
    *,
    parent_mentions: Sequence[ScientificEntityMentionEvidence],
    config: ScientificEntityGLiNERFrozenPolicyConfig,
    build_id: str,
    candidate_extractor_fingerprint: str,
) -> tuple[
    tuple[ScientificEntityMentionEvidence, ...],
    tuple[ScientificEntityFrozenPolicyEvidenceLineage, ...],
]:
    if len(parent_mentions) != config.frozen.expected_input_prediction_count:
        raise ScientificEntityGLiNERFrozenPolicyError(
            "parent prediction count does not match frozen decision"
        )
    selected = filter_predictions(
        parent_mentions,
        policy=config.frozen.policy,
        input_threshold=config.frozen.input_threshold,
    )
    if len(selected) != config.frozen.expected_selected_prediction_count:
        raise ScientificEntityGLiNERFrozenPolicyError(
            "materialized selected prediction count does not match frozen decision"
        )
    if len(parent_mentions) - len(selected) != config.frozen.expected_rejected_prediction_count:
        raise ScientificEntityGLiNERFrozenPolicyError(
            "materialized rejected prediction count does not match frozen decision"
        )

    candidate_rows: list[ScientificEntityMentionEvidence] = []
    lineage_rows: list[ScientificEntityFrozenPolicyEvidenceLineage] = []
    for parent in selected:
        payload = parent.model_dump(mode="json")
        payload.update(
            {
                "build_id": build_id,
                "extractor_fingerprint": candidate_extractor_fingerprint,
                "evidence_id": build_evidence_id(
                    mention_id=parent.mention_id,
                    extractor_fingerprint=candidate_extractor_fingerprint,
                ),
            }
        )
        candidate = ScientificEntityMentionEvidence.model_validate(payload)
        if candidate.mention_id != parent.mention_id:
            raise ScientificEntityGLiNERFrozenPolicyError("mention_id changed during materialization")
        if candidate.evidence_id == parent.evidence_id:
            raise ScientificEntityGLiNERFrozenPolicyError("evidence_id did not change")
        candidate_rows.append(candidate)
        lineage_rows.append(
            ScientificEntityFrozenPolicyEvidenceLineage(
                schema_version=EVIDENCE_LINEAGE_SCHEMA_VERSION,
                build_id=build_id,
                parent_build_id=config.frozen.parent_build_id,
                mention_id=parent.mention_id,
                parent_evidence_id=parent.evidence_id,
                candidate_evidence_id=candidate.evidence_id,
            )
        )

    if len({row.mention_id for row in candidate_rows}) != len(candidate_rows):
        raise ScientificEntityGLiNERFrozenPolicyError("candidate mention_ids must be unique")
    if len({row.evidence_id for row in candidate_rows}) != len(candidate_rows):
        raise ScientificEntityGLiNERFrozenPolicyError("candidate evidence_ids must be unique")
    return tuple(candidate_rows), tuple(lineage_rows)
