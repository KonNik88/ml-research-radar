from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import (
    MANIFEST_SCHEMA_VERSION,
    MENTION_SCHEMA_VERSION,
    EntityEvidenceBuildStatus,
    ScientificEntityEvidenceManifest,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    ScientificEntityType,
    build_evidence_id,
    build_extractor_fingerprint,
    sha256_text,
)
from radar_core.contracts.scientific_entity_gliner_frozen_policy import (
    EVIDENCE_LINEAGE_SCHEMA_VERSION,
    ScientificEntityFrozenPolicyEvidenceLineage,
)
from radar_core.contracts.scientific_entity_fresh_heldout_frozen_policy import (
    ScientificEntityFreshHeldoutFrozenPolicyConfig,
    ScientificEntityFreshHeldoutFrozenPolicyError,
    load_scientific_entity_fresh_heldout_frozen_policy_config,
)
from radar_core.contracts.scientific_entity_semantic_prompt_raw_floor_policy import (
    load_raw_floor_policy_config,
)
from radar_core.entities.scientific_entity_gliner_calibration import filter_predictions
from radar_core.entities.scientific_entity_gliner_frozen_policy import (
    build_policy_filtered_extractor_descriptor,
)

REPORT_NAME = "scientific_entity_fresh_heldout_frozen_policy_v02"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_fresh_heldout_frozen_policy_v0.2.yaml"
DEFAULT_CANONICAL = PROJECT_ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
DERIVATION_SCHEMA_VERSION = "scientific_entity_fresh_heldout_frozen_policy_derivation_v0.2"
QUALITY_SCHEMA_VERSION = "scientific_entity_fresh_heldout_frozen_policy_quality_v0.2"
OUTPUT_SCHEMA_VERSION = "scientific_entity_fresh_heldout_frozen_policy_output_v0.2"
CHECKSUM_FILES = (
    "mentions.jsonl",
    "manifest.json",
    "derivation_manifest.json",
    "evidence_lineage.jsonl",
    "data_quality_summary.json",
    "schema.json",
    "README.md",
)


class FreshHeldoutPolicyBuildError(RuntimeError):
    """Raised when fresh-heldout frozen policy application cannot be reproduced safely."""


class FreshHeldoutPolicyDerivationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = Field(pattern=r"^scientific_entity_fresh_heldout_frozen_policy_derivation_v0\.2$")
    build_id: str = Field(min_length=1)
    generated_at_utc: datetime
    candidate_id: str = Field(min_length=1)
    sample_id: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    selected_canonical_ids_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_mention_count: int = Field(ge=1)
    parent_build_id: str = Field(min_length=1)
    parent_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_mentions_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_extractor_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    development_policy_config_path: str = Field(min_length=1)
    development_policy_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    calibration_id: str = Field(min_length=1)
    selected_trial_id: str = Field(min_length=1)
    input_threshold: float
    title_threshold: float
    abstract_threshold: float
    entity_type_overrides: dict[str, float]
    input_prediction_count: int = Field(ge=1)
    selected_prediction_count: int = Field(ge=0)
    rejected_prediction_count: int = Field(ge=0)
    candidate_extractor_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    lineage_file: str
    lineage_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    lineage_count: int = Field(ge=0)
    mention_id_preserved: bool
    evidence_id_recomputed: bool
    confidence_preserved: bool
    parent_model_inference_already_executed: bool
    new_model_inference_executed: bool
    threshold_tuning_executed: bool
    reference_comparison_executed: bool
    evaluation_executed: bool
    acceptance_decision_made: bool
    canonical_truth_mutated: bool
    production_extractor_selected: bool
    full_corpus_build_authorized: bool

    @model_validator(mode="after")
    def validate_counts(self):
        if self.selected_prediction_count + self.rejected_prediction_count != self.input_prediction_count:
            raise ValueError("selected + rejected must equal input")
        if self.lineage_count != self.selected_prediction_count:
            raise ValueError("lineage count must equal selected prediction count")
        if self.entity_type_overrides:
            raise ValueError("entity-type overrides must remain empty")
        return self


def _resolve(project_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _policy_config_sha256(config) -> str:
    return sha256_text(_canonical_json(config.model_dump(mode="json")))


def fresh_policy_config_sha256(config: ScientificEntityFreshHeldoutFrozenPolicyConfig) -> str:
    return sha256_text(_canonical_json(config.model_dump(mode="json")))


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FreshHeldoutPolicyBuildError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise FreshHeldoutPolicyBuildError(f"Blank JSONL line: {path}:{line_number}")
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise FreshHeldoutPolicyBuildError(f"Expected JSON object: {path}:{line_number}")
            rows.append(payload)
    return rows


def _jsonl_bytes(rows: Sequence[Any]) -> bytes:
    chunks = []
    for row in rows:
        payload = row.model_dump(mode="json") if hasattr(row, "model_dump") else row
        chunks.append(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return (("\n".join(chunks) + "\n") if chunks else "").encode("utf-8")


def _json_bytes(payload: Any) -> bytes:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _validate_policy_origin(project_root: Path, contract: ScientificEntityFreshHeldoutFrozenPolicyConfig) -> dict[str, Any]:
    policy_path = _resolve(project_root, contract.policy_origin.development_policy_config_path)
    if not policy_path.is_file():
        raise FileNotFoundError(policy_path)
    development = load_raw_floor_policy_config(policy_path)
    semantic_sha = _policy_config_sha256(development)
    expected = contract.policy_origin
    if semantic_sha != expected.development_policy_config_sha256:
        raise ScientificEntityFreshHeldoutFrozenPolicyError("development v0.2c policy config SHA drifted")
    if development.candidate.candidate_id != contract.candidate.candidate_id:
        raise ScientificEntityFreshHeldoutFrozenPolicyError("development policy candidate_id drifted")
    if development.candidate.calibration_id != expected.calibration_id:
        raise ScientificEntityFreshHeldoutFrozenPolicyError("development policy calibration_id drifted")
    if development.candidate.selected_trial_id != expected.selected_trial_id:
        raise ScientificEntityFreshHeldoutFrozenPolicyError("development policy selected_trial_id drifted")
    if float(development.policy.input_threshold) != expected.input_threshold:
        raise ScientificEntityFreshHeldoutFrozenPolicyError("development policy input threshold drifted")
    if development.policy.source_field_thresholds != expected.source_field_thresholds:
        raise ScientificEntityFreshHeldoutFrozenPolicyError("development source-field thresholds drifted")
    if development.policy.entity_type_thresholds:
        raise ScientificEntityFreshHeldoutFrozenPolicyError("development policy unexpectedly has type overrides")
    return {
        "policy_path": policy_path,
        "semantic_sha256": semantic_sha,
        "calibration_id": development.candidate.calibration_id,
        "selected_trial_id": development.candidate.selected_trial_id,
    }


def _validate_raw_parent(
    *,
    project_root: Path,
    contract: ScientificEntityFreshHeldoutFrozenPolicyConfig,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    canonical_path: Path,
) -> tuple[ScientificEntityEvidenceManifest, tuple[ScientificEntityMentionEvidence, ...], dict[str, Any]]:
    from radar_core.entities.scientific_entity_fresh_heldout_frozen_inference import validate_frozen_inference

    checks, summary = validate_frozen_inference(
        project_root=project_root,
        config_path=project_root / "configs" / "scientific_entity_fresh_heldout_frozen_inference_v0.2.yaml",
        sample_dir=sample_dir,
        reference_dir=reference_dir,
        development_package_dir=development_package_dir,
        canonical_path=canonical_path,
    )
    failed = [name for name, ok, _ in checks if not ok]
    if failed or summary.get("required_failed_count") != 0:
        raise FreshHeldoutPolicyBuildError("raw inference validation failed: " + ", ".join(failed))
    if summary.get("build_id") != contract.candidate.raw_build_id:
        raise FreshHeldoutPolicyBuildError("raw build_id drifted")
    if summary.get("raw_mention_count") != contract.candidate.expected_raw_mention_count:
        raise FreshHeldoutPolicyBuildError("raw mention count drifted")
    if summary.get("input_document_count") != contract.candidate.expected_document_count:
        raise FreshHeldoutPolicyBuildError("raw document count drifted")
    if summary.get("reference_mention_count") != contract.fresh_heldout.expected_reference_mention_count:
        raise FreshHeldoutPolicyBuildError("reference lineage drifted")

    parent_dir = _resolve(project_root, contract.candidate.raw_build_root) / contract.candidate.raw_build_id
    manifest_path = parent_dir / "manifest.json"
    mentions_path = parent_dir / "mentions.jsonl"
    manifest = ScientificEntityEvidenceManifest.model_validate(_read_json(manifest_path))
    rows = tuple(ScientificEntityMentionEvidence.model_validate(x) for x in _read_jsonl(mentions_path))
    if manifest.extractor_fingerprint != contract.candidate.expected_raw_extractor_fingerprint:
        raise FreshHeldoutPolicyBuildError("raw extractor fingerprint drifted")
    if manifest.mentions_sha256 != _sha256_file(mentions_path):
        raise FreshHeldoutPolicyBuildError("raw mentions checksum mismatch")
    if len(rows) != contract.candidate.expected_raw_mention_count:
        raise FreshHeldoutPolicyBuildError("raw mention row count drifted")
    return manifest, rows, summary


def _materialize(
    *,
    parents: Sequence[ScientificEntityMentionEvidence],
    contract: ScientificEntityFreshHeldoutFrozenPolicyConfig,
    build_id: str,
    fingerprint: str,
):
    selected = filter_predictions(
        parents,
        policy=contract.policy_origin.threshold_policy(),
        input_threshold=contract.policy_origin.input_threshold,
    )
    rows = []
    lineage = []
    for parent in selected:
        payload = parent.model_dump(mode="json")
        payload.update({
            "build_id": build_id,
            "extractor_fingerprint": fingerprint,
            "evidence_id": build_evidence_id(
                mention_id=parent.mention_id,
                extractor_fingerprint=fingerprint,
            ),
        })
        candidate = ScientificEntityMentionEvidence.model_validate(payload)
        if candidate.mention_id != parent.mention_id:
            raise FreshHeldoutPolicyBuildError("mention_id changed during policy materialization")
        if candidate.confidence_score != parent.confidence_score:
            raise FreshHeldoutPolicyBuildError("confidence score changed during policy materialization")
        rows.append(candidate)
        lineage.append(ScientificEntityFrozenPolicyEvidenceLineage(
            schema_version=EVIDENCE_LINEAGE_SCHEMA_VERSION,
            build_id=build_id,
            parent_build_id=parent.build_id,
            mention_id=parent.mention_id,
            parent_evidence_id=parent.evidence_id,
            candidate_evidence_id=candidate.evidence_id,
        ))
    if len({row.mention_id for row in rows}) != len(rows):
        raise FreshHeldoutPolicyBuildError("selected mention_ids must remain unique")
    return tuple(rows), tuple(lineage)


def _quality(build_id: str, parent_count: int, rows: Sequence[ScientificEntityMentionEvidence]) -> dict[str, Any]:
    by_field = Counter(row.source_field.value for row in rows)
    by_type = Counter(row.entity_type.value for row in rows)
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "build_id": build_id,
        "input_prediction_count": parent_count,
        "selected_prediction_count": len(rows),
        "rejected_prediction_count": parent_count - len(rows),
        "selected_by_source_field": dict(sorted(by_field.items())),
        "selected_by_entity_type": dict(sorted(by_type.items())),
        "input_threshold": 0.4,
        "title_threshold": 0.45,
        "abstract_threshold": 0.625,
        "entity_type_overrides": {},
        "new_model_inference_executed": False,
        "threshold_tuning_executed": False,
        "reference_comparison_executed": False,
        "evaluation_executed": False,
        "acceptance_decision_made": False,
    }


def _schema() -> dict[str, Any]:
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "mention_schema_version": MENTION_SCHEMA_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "derivation_schema_version": DERIVATION_SCHEMA_VERSION,
        "evidence_lineage_schema_version": EVIDENCE_LINEAGE_SCHEMA_VERSION,
        "quality_schema_version": QUALITY_SCHEMA_VERSION,
        "serialization": {"encoding": "utf-8", "line_ending": "lf"},
        "mentions_json_schema": ScientificEntityMentionEvidence.model_json_schema(),
        "manifest_json_schema": ScientificEntityEvidenceManifest.model_json_schema(),
        "derivation_json_schema": FreshHeldoutPolicyDerivationManifest.model_json_schema(),
    }


def _readme(build_id: str, parent_build_id: str, selected: int, rejected: int) -> str:
    return "\n".join([
        "# Scientific Entity Fresh Held-Out Frozen v0.2c Policy Evidence",
        "",
        "Immutable policy-filtered candidate evidence for the fresh 48-paper independent held-out.",
        "The policy was frozen on development evidence before this held-out was sampled.",
        "No model inference, threshold tuning, reference comparison, evaluation, or acceptance decision occurs here.",
        "",
        f"- build_id: `{build_id}`",
        f"- parent_build_id: `{parent_build_id}`",
        f"- selected_prediction_count: `{selected}`",
        f"- rejected_prediction_count: `{rejected}`",
        "- title threshold: `0.45`",
        "- abstract threshold: `0.625`",
        "",
    ])


def _write_output(output_dir: Path, payloads: dict[str, bytes]) -> None:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        raise FileExistsError(f"Immutable policy build already exists: {output_dir}")
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_dir.parent))
    try:
        for name, content in payloads.items():
            (staging / name).write_bytes(content)
        checksums = [f"{_sha256_file(staging / name)}  {name}" for name in CHECKSUM_FILES]
        (staging / "checksums.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8", newline="\n")
        staging.replace(output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def plan_or_execute_frozen_policy(
    *,
    project_root: Path,
    config_path: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    canonical_path: Path,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    contract = load_scientific_entity_fresh_heldout_frozen_policy_config(config_path.resolve())
    contract_sha = fresh_policy_config_sha256(contract)
    policy_origin = _validate_policy_origin(project_root, contract)
    parent_manifest, parent_mentions, raw_summary = _validate_raw_parent(
        project_root=project_root,
        contract=contract,
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        development_package_dir=development_package_dir.resolve(),
        canonical_path=canonical_path.resolve(),
    )
    output_dir = _resolve(project_root, contract.execution.output_root) / contract.execution.build_id
    already_applied = output_dir.exists()
    if execute and already_applied:
        raise FileExistsError(f"Frozen v0.2c fresh-heldout policy is one-shot and already exists: {output_dir}")

    descriptor = build_policy_filtered_extractor_descriptor(
        extractor_name=contract.extractor.name,
        extractor_version=contract.extractor.version,
        environment_lock_path=contract.extractor.environment_lock_path,
        config_sha256=contract_sha,
        parent_manifest=parent_manifest,
        project_root=project_root,
    )
    fingerprint = build_extractor_fingerprint(descriptor)
    if fingerprint == parent_manifest.extractor_fingerprint:
        raise FreshHeldoutPolicyBuildError("policy-aware extractor fingerprint must differ from raw parent")
    rows, lineage = _materialize(
        parents=parent_mentions,
        contract=contract,
        build_id=contract.execution.build_id,
        fingerprint=fingerprint,
    )
    rejected = len(parent_mentions) - len(rows)

    report = {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "candidate_id": contract.candidate.candidate_id,
        "sample_id": contract.fresh_heldout.sample_id,
        "review_id": contract.fresh_heldout.review_id,
        "parent_build_id": parent_manifest.build_id,
        "parent_raw_mention_count": len(parent_mentions),
        "parent_raw_extractor_fingerprint": parent_manifest.extractor_fingerprint,
        "reference_mention_count": raw_summary["reference_mention_count"],
        "raw_inference_validation_required_failed_count": raw_summary["required_failed_count"],
        "fresh_policy_config_sha256": contract_sha,
        "development_policy_config_sha256": policy_origin["semantic_sha256"],
        "calibration_id": contract.policy_origin.calibration_id,
        "selected_trial_id": contract.policy_origin.selected_trial_id,
        "title_threshold": contract.policy_origin.source_field_thresholds[ScientificEntitySourceField.TITLE],
        "abstract_threshold": contract.policy_origin.source_field_thresholds[ScientificEntitySourceField.ABSTRACT],
        "entity_type_overrides": {},
        "selected_prediction_count": len(rows),
        "rejected_prediction_count": rejected,
        "build_id": contract.execution.build_id,
        "policy_already_applied": already_applied,
        "plan_runs_model_inference": False,
        "new_model_inference_executed": False,
        "threshold_tuning_executed": False,
        "reference_comparison_executed": False,
        "evaluation_executed": False,
        "acceptance_decision_made": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "output_dir": str(output_dir).replace("\\", "/"),
        "next_slice": contract.next_steps.after_plan if not execute else contract.next_steps.after_execute,
    }
    if not execute:
        return report

    now = (generated_at_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    mentions_bytes = _jsonl_bytes(rows)
    lineage_bytes = _jsonl_bytes(lineage)
    manifest = ScientificEntityEvidenceManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        build_id=contract.execution.build_id,
        status=EntityEvidenceBuildStatus.CANDIDATE,
        generated_at_utc=now,
        canonical_input=parent_manifest.canonical_input,
        extractor=descriptor,
        extractor_fingerprint=fingerprint,
        offset_unit=parent_manifest.offset_unit,
        offset_interval=parent_manifest.offset_interval,
        source_fields=parent_manifest.source_fields,
        entity_types=parent_manifest.entity_types,
        mentions_file="mentions.jsonl",
        mention_count=len(rows),
        mentions_sha256=hashlib.sha256(mentions_bytes).hexdigest(),
        canonical_truth_mutated=False,
        may_be_used_as_reconcile_input=False,
        publication_ready=False,
    )
    derivation = FreshHeldoutPolicyDerivationManifest(
        schema_version=DERIVATION_SCHEMA_VERSION,
        build_id=contract.execution.build_id,
        generated_at_utc=now,
        candidate_id=contract.candidate.candidate_id,
        sample_id=contract.fresh_heldout.sample_id,
        review_id=contract.fresh_heldout.review_id,
        selected_canonical_ids_sha256=contract.fresh_heldout.selected_canonical_ids_sha256,
        reference_mention_count=contract.fresh_heldout.expected_reference_mention_count,
        parent_build_id=parent_manifest.build_id,
        parent_manifest_sha256=_sha256_file(_resolve(project_root, contract.candidate.raw_build_root) / contract.candidate.raw_build_id / "manifest.json"),
        parent_mentions_sha256=_sha256_file(_resolve(project_root, contract.candidate.raw_build_root) / contract.candidate.raw_build_id / "mentions.jsonl"),
        parent_extractor_fingerprint=parent_manifest.extractor_fingerprint,
        development_policy_config_path=contract.policy_origin.development_policy_config_path,
        development_policy_config_sha256=policy_origin["semantic_sha256"],
        calibration_id=contract.policy_origin.calibration_id,
        selected_trial_id=contract.policy_origin.selected_trial_id,
        input_threshold=contract.policy_origin.input_threshold,
        title_threshold=contract.policy_origin.source_field_thresholds[ScientificEntitySourceField.TITLE],
        abstract_threshold=contract.policy_origin.source_field_thresholds[ScientificEntitySourceField.ABSTRACT],
        entity_type_overrides={},
        input_prediction_count=len(parent_mentions),
        selected_prediction_count=len(rows),
        rejected_prediction_count=rejected,
        candidate_extractor_fingerprint=fingerprint,
        lineage_file="evidence_lineage.jsonl",
        lineage_sha256=hashlib.sha256(lineage_bytes).hexdigest(),
        lineage_count=len(lineage),
        mention_id_preserved=True,
        evidence_id_recomputed=True,
        confidence_preserved=True,
        parent_model_inference_already_executed=True,
        new_model_inference_executed=False,
        threshold_tuning_executed=False,
        reference_comparison_executed=False,
        evaluation_executed=False,
        acceptance_decision_made=False,
        canonical_truth_mutated=False,
        production_extractor_selected=False,
        full_corpus_build_authorized=False,
    )
    quality = _quality(contract.execution.build_id, len(parent_mentions), rows)
    payloads = {
        "mentions.jsonl": mentions_bytes,
        "manifest.json": _json_bytes(manifest),
        "derivation_manifest.json": _json_bytes(derivation),
        "evidence_lineage.jsonl": lineage_bytes,
        "data_quality_summary.json": _json_bytes(quality),
        "schema.json": _json_bytes(_schema()),
        "README.md": _readme(contract.execution.build_id, parent_manifest.build_id, len(rows), rejected).encode("utf-8"),
    }
    _write_output(output_dir, payloads)
    report["phase_complete"] = True
    report["policy_already_applied"] = True
    return report


def validate_frozen_policy_application(
    *,
    project_root: Path,
    config_path: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    canonical_path: Path,
):
    contract = load_scientific_entity_fresh_heldout_frozen_policy_config(config_path.resolve())
    contract_sha = fresh_policy_config_sha256(contract)
    policy_origin = _validate_policy_origin(project_root, contract)
    parent_manifest, parent_mentions, raw_summary = _validate_raw_parent(
        project_root=project_root,
        contract=contract,
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        development_package_dir=development_package_dir.resolve(),
        canonical_path=canonical_path.resolve(),
    )
    output_dir = _resolve(project_root, contract.execution.output_root) / contract.execution.build_id
    checks = []
    def add(name, ok, detail=""):
        checks.append((name, bool(ok), str(detail)))

    add("raw_inference_validation_passed", raw_summary["required_failed_count"] == 0, raw_summary["required_failed_count"])
    add("output_directory_exists", output_dir.is_dir(), output_dir)
    required = (*CHECKSUM_FILES, "checksums.txt")
    add("required_files_present", output_dir.is_dir() and all((output_dir / x).is_file() for x in required), required)
    if not output_dir.is_dir():
        failed = [name for name, ok, _ in checks if not ok]
        return checks, {
            "report": REPORT_NAME,
            "build_id": contract.execution.build_id,
            "parent_build_id": contract.candidate.raw_build_id,
            "input_prediction_count": None,
            "selected_prediction_count": None,
            "rejected_prediction_count": None,
            "total_checks": len(checks),
            "required_failed_count": len(failed),
            "next_slice": contract.next_steps.after_validation,
        }

    checksum_lines = (output_dir / "checksums.txt").read_text(encoding="utf-8").splitlines()
    checksum_map = {}
    for line in checksum_lines:
        if "  " in line:
            digest, name = line.split("  ", 1)
            checksum_map[name] = digest
    add("checksums_cover_required_files", set(checksum_map) == set(CHECKSUM_FILES), sorted(checksum_map))
    add("checksums_match", all(checksum_map.get(name) == _sha256_file(output_dir / name) for name in CHECKSUM_FILES), "")

    manifest = ScientificEntityEvidenceManifest.model_validate(_read_json(output_dir / "manifest.json"))
    derivation = FreshHeldoutPolicyDerivationManifest.model_validate(_read_json(output_dir / "derivation_manifest.json"))
    quality = _read_json(output_dir / "data_quality_summary.json")
    rows = tuple(ScientificEntityMentionEvidence.model_validate(x) for x in _read_jsonl(output_dir / "mentions.jsonl"))
    lineage = _read_jsonl(output_dir / "evidence_lineage.jsonl")

    descriptor = build_policy_filtered_extractor_descriptor(
        extractor_name=contract.extractor.name,
        extractor_version=contract.extractor.version,
        environment_lock_path=contract.extractor.environment_lock_path,
        config_sha256=contract_sha,
        parent_manifest=parent_manifest,
        project_root=project_root,
    )
    fingerprint = build_extractor_fingerprint(descriptor)
    expected_rows, expected_lineage = _materialize(
        parents=parent_mentions,
        contract=contract,
        build_id=contract.execution.build_id,
        fingerprint=fingerprint,
    )
    expected_mentions_bytes = _jsonl_bytes(expected_rows)
    expected_lineage_bytes = _jsonl_bytes(expected_lineage)

    add("build_id_exact", manifest.build_id == contract.execution.build_id, manifest.build_id)
    add("candidate_status", manifest.status.value == contract.execution.build_status, manifest.status.value)
    add("parent_build_id_exact", derivation.parent_build_id == contract.candidate.raw_build_id, derivation.parent_build_id)
    add("sample_id_exact", derivation.sample_id == contract.fresh_heldout.sample_id, derivation.sample_id)
    add("review_id_exact", derivation.review_id == contract.fresh_heldout.review_id, derivation.review_id)
    add("reference_count_exact", derivation.reference_mention_count == 944, derivation.reference_mention_count)
    add("fresh_policy_extractor_config_sha_exact", manifest.extractor.config_sha256 == contract_sha, manifest.extractor.config_sha256)
    add("development_policy_sha_exact", derivation.development_policy_config_sha256 == policy_origin["semantic_sha256"], derivation.development_policy_config_sha256)
    add("calibration_id_exact", derivation.calibration_id == contract.policy_origin.calibration_id, derivation.calibration_id)
    add("selected_trial_id_exact", derivation.selected_trial_id == contract.policy_origin.selected_trial_id, derivation.selected_trial_id)
    add("title_threshold_exact", derivation.title_threshold == 0.45, derivation.title_threshold)
    add("abstract_threshold_exact", derivation.abstract_threshold == 0.625, derivation.abstract_threshold)
    add("no_type_overrides", derivation.entity_type_overrides == {}, derivation.entity_type_overrides)
    add("input_count_1257", derivation.input_prediction_count == 1257, derivation.input_prediction_count)
    add("counts_sum", derivation.selected_prediction_count + derivation.rejected_prediction_count == 1257, "")
    add("manifest_selected_count_exact", manifest.mention_count == derivation.selected_prediction_count == len(rows), (manifest.mention_count, derivation.selected_prediction_count, len(rows)))
    add("mentions_checksum_exact", manifest.mentions_sha256 == _sha256_file(output_dir / "mentions.jsonl"), manifest.mentions_sha256)
    add("materialization_reproduces_exact_mentions", (output_dir / "mentions.jsonl").read_bytes() == expected_mentions_bytes, "")
    add("lineage_reproduces_exact", (output_dir / "evidence_lineage.jsonl").read_bytes() == expected_lineage_bytes, "")
    add("lineage_count_exact", len(lineage) == len(rows), len(lineage))
    add("policy_extractor_fingerprint_exact", manifest.extractor_fingerprint == fingerprint == derivation.candidate_extractor_fingerprint, manifest.extractor_fingerprint)
    add("policy_extractor_differs_from_raw", fingerprint != parent_manifest.extractor_fingerprint, fingerprint)
    add("quality_selected_count_exact", quality.get("selected_prediction_count") == len(rows), quality.get("selected_prediction_count"))
    add("quality_rejected_count_exact", quality.get("rejected_prediction_count") == 1257 - len(rows), quality.get("rejected_prediction_count"))
    add("new_model_inference_false", derivation.new_model_inference_executed is False, derivation.new_model_inference_executed)
    add("threshold_tuning_false", derivation.threshold_tuning_executed is False, derivation.threshold_tuning_executed)
    add("reference_comparison_false", derivation.reference_comparison_executed is False, derivation.reference_comparison_executed)
    add("evaluation_false", derivation.evaluation_executed is False, derivation.evaluation_executed)
    add("acceptance_decision_false", derivation.acceptance_decision_made is False, derivation.acceptance_decision_made)
    add("canonical_truth_not_mutated", manifest.canonical_truth_mutated is False and derivation.canonical_truth_mutated is False, "")
    add("production_not_selected", derivation.production_extractor_selected is False, "")
    add("full_corpus_not_authorized", derivation.full_corpus_build_authorized is False, "")

    failed = [name for name, ok, _ in checks if not ok]
    summary = {
        "report": REPORT_NAME,
        "candidate_id": contract.candidate.candidate_id,
        "sample_id": contract.fresh_heldout.sample_id,
        "review_id": contract.fresh_heldout.review_id,
        "build_id": contract.execution.build_id,
        "parent_build_id": contract.candidate.raw_build_id,
        "input_prediction_count": derivation.input_prediction_count,
        "selected_prediction_count": derivation.selected_prediction_count,
        "rejected_prediction_count": derivation.rejected_prediction_count,
        "reference_mention_count": derivation.reference_mention_count,
        "raw_inference_validation_required_failed_count": raw_summary["required_failed_count"],
        "new_model_inference_executed": False,
        "threshold_tuning_executed": False,
        "reference_comparison_executed": False,
        "evaluation_executed": False,
        "acceptance_decision_made": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "next_slice": contract.next_steps.after_validation,
    }
    return checks, summary
