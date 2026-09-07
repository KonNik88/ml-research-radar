from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from radar_core.contracts.scientific_entity_evidence import (
    EXTRACTOR_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    MENTION_SCHEMA_VERSION,
    EntityEvidenceBuildStatus,
    ScientificEntityEvidenceManifest,
    ScientificEntityExtractorDescriptor,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    ScientificEntityType,
    build_evidence_id,
    build_extractor_fingerprint,
    sha256_text,
)
from radar_core.contracts.scientific_entity_gliner_calibration import ScientificEntityThresholdPolicy
from radar_core.contracts.scientific_entity_fresh_heldout_frozen_policy import (
    FrozenPolicyDerivationManifest,
    FrozenPolicyLineage,
    ScientificEntityFreshHeldoutFrozenPolicyConfig,
    ScientificEntityFreshHeldoutFrozenPolicyError,
    load_scientific_entity_fresh_heldout_frozen_policy_config,
)
from radar_core.entities.scientific_entity_gliner_calibration import filter_predictions
from radar_core.entities.scientific_entity_semantic_prompt_raw_floor_policy import (
    load_raw_floor_policy_config,
    policy_config_sha256,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_fresh_heldout_frozen_policy_v0.2.yaml"
DEFAULT_CANONICAL = PROJECT_ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
REPORT_NAME = "scientific_entity_fresh_heldout_frozen_policy_v02"
QUALITY_SCHEMA_VERSION = "scientific_entity_fresh_heldout_frozen_policy_quality_v0.2"
OUTPUT_SCHEMA_VERSION = "scientific_entity_fresh_heldout_frozen_policy_output_v0.2"
REQUIRED_FILES = (
    "mentions.jsonl",
    "manifest.json",
    "derivation_manifest.json",
    "evidence_lineage.jsonl",
    "data_quality_summary.json",
    "schema.json",
    "README.md",
    "checksums.txt",
)
CHECKSUM_FILES = REQUIRED_FILES[:-1]


class FrozenPolicyBuildError(RuntimeError):
    """Raised when fresh-heldout frozen policy materialization is unsafe or inconsistent."""


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _semantic_yaml_sha256(path: Path) -> str:
    import yaml
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return sha256_text(_canonical_json(payload))


def _json_bytes(payload: Any) -> bytes:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(rows: Sequence[Any]) -> bytes:
    lines = []
    for row in rows:
        payload = row.model_dump(mode="json") if hasattr(row, "model_dump") else row
        lines.append(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return (("\n".join(lines) + "\n") if lines else "").encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FrozenPolicyBuildError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise FrozenPolicyBuildError(f"Blank JSONL line: {path}:{line_number}")
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise FrozenPolicyBuildError(f"Expected JSON object: {path}:{line_number}")
            rows.append(payload)
    return rows


def _resolve(project_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def _validate_frozen_policy_config(*, project_root: Path, contract: ScientificEntityFreshHeldoutFrozenPolicyConfig) -> dict[str, Any]:
    policy_path = _resolve(project_root, contract.candidate.frozen_policy_config_path)
    if not policy_path.is_file():
        raise FileNotFoundError(policy_path)
    semantic_sha = _semantic_yaml_sha256(policy_path)
    if semantic_sha != contract.candidate.frozen_policy_config_sha256:
        raise ScientificEntityFreshHeldoutFrozenPolicyError("Frozen v0.2c policy config SHA-256 drifted")
    policy = load_raw_floor_policy_config(policy_path)
    model_sha = policy_config_sha256(policy)
    if model_sha != semantic_sha:
        raise ScientificEntityFreshHeldoutFrozenPolicyError("Frozen policy semantic SHA implementation drifted")
    checks = {
        "candidate_id": policy.candidate.candidate_id == contract.candidate.candidate_id,
        "calibration_id": policy.candidate.calibration_id == contract.candidate.calibration_id,
        "selected_trial_id": policy.candidate.selected_trial_id == contract.candidate.selected_trial_id,
        "input_threshold": policy.policy.input_threshold == contract.policy.input_threshold,
        "default_threshold": policy.policy.default_threshold == contract.policy.default_threshold,
        "title_threshold": float(policy.policy.source_field_thresholds[ScientificEntitySourceField.TITLE]) == contract.policy.title_threshold,
        "abstract_threshold": float(policy.policy.source_field_thresholds[ScientificEntitySourceField.ABSTRACT]) == contract.policy.abstract_threshold,
        "entity_type_overrides": not policy.policy.entity_type_thresholds and not contract.policy.entity_type_overrides,
        "source_development_policy_fresh_heldout_forbidden": policy.safety.fresh_heldout_consumption_allowed is False,
        "model_inference_forbidden": policy.safety.model_inference_allowed is False,
        "threshold_tuning_forbidden": policy.safety.threshold_tuning_allowed is False,
        "production_not_selected": policy.safety.production_extractor_selected is False,
        "full_corpus_not_authorized": policy.safety.full_corpus_build_authorized is False,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise ScientificEntityFreshHeldoutFrozenPolicyError("Frozen v0.2c policy semantics drifted: " + ", ".join(failed))
    return {"policy_path": policy_path, "policy_sha256": semantic_sha, "policy": policy}


def _validate_raw_inference(
    *,
    project_root: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    canonical_path: Path,
    model_cache_dir: Path | None,
) -> dict[str, Any]:
    from radar_core.entities.scientific_entity_fresh_heldout_frozen_inference import (
        DEFAULT_CONFIG as RAW_CONFIG,
        validate_frozen_inference,
    )
    checks, summary = validate_frozen_inference(
        project_root=project_root,
        config_path=RAW_CONFIG,
        sample_dir=sample_dir,
        reference_dir=reference_dir,
        development_package_dir=development_package_dir,
        canonical_path=canonical_path,
        model_cache_dir=model_cache_dir,
    )
    if summary.get("required_failed_count"):
        failed = [name for name, ok, _ in checks if not ok]
        raise FrozenPolicyBuildError("Frozen raw inference validation failed: " + ", ".join(failed))
    return summary


def _assert_raw_matches_contract(summary: dict[str, Any], contract: ScientificEntityFreshHeldoutFrozenPolicyConfig) -> None:
    expected = {
        "candidate_id": contract.candidate.candidate_id,
        "sample_id": contract.fresh_heldout.sample_id,
        "review_id": contract.fresh_heldout.review_id,
        "build_id": contract.candidate.raw_build_id,
        "input_document_count": contract.fresh_heldout.expected_document_count,
        "raw_mention_count": contract.candidate.expected_raw_prediction_count,
        "reference_mention_count": contract.fresh_heldout.expected_reference_mention_count,
        "model_inference_executed": True,
        "policy_applied": False,
        "evaluation_executed": False,
        "acceptance_decision_made": False,
        "required_failed_count": 0,
    }
    mismatched = [key for key, value in expected.items() if summary.get(key) != value]
    if mismatched:
        raise ScientificEntityFreshHeldoutFrozenPolicyError(
            "Frozen raw inference lineage drifted: " + ", ".join(mismatched)
        )


def _load_parent(*, project_root: Path, contract: ScientificEntityFreshHeldoutFrozenPolicyConfig) -> tuple[ScientificEntityEvidenceManifest, tuple[ScientificEntityMentionEvidence, ...], Path]:
    raw_contract_path = _resolve(project_root, contract.candidate.raw_inference_contract_path)
    if _semantic_yaml_sha256(raw_contract_path) != contract.candidate.raw_inference_contract_sha256:
        raise ScientificEntityFreshHeldoutFrozenPolicyError("Frozen raw-inference contract SHA-256 drifted")
    from radar_core.contracts.scientific_entity_fresh_heldout_frozen_inference import (
        load_scientific_entity_fresh_heldout_frozen_inference_config,
    )
    raw_contract = load_scientific_entity_fresh_heldout_frozen_inference_config(raw_contract_path)
    if raw_contract.execution.build_id != contract.candidate.raw_build_id:
        raise ScientificEntityFreshHeldoutFrozenPolicyError("Raw build ID drifted from frozen policy parent")
    raw_dir = _resolve(project_root, raw_contract.execution.raw_output_root) / raw_contract.execution.build_id
    manifest = ScientificEntityEvidenceManifest.model_validate(_read_json(raw_dir / "manifest.json"))
    if manifest.build_id != contract.candidate.raw_build_id:
        raise FrozenPolicyBuildError("Raw parent build_id mismatch")
    if manifest.status != EntityEvidenceBuildStatus.CANDIDATE:
        raise FrozenPolicyBuildError("Fresh policy parent must remain candidate raw evidence")
    if manifest.mention_count != contract.candidate.expected_raw_prediction_count:
        raise FrozenPolicyBuildError("Raw parent mention count drifted")
    if manifest.extractor_fingerprint != contract.candidate.expected_raw_extractor_fingerprint:
        raise FrozenPolicyBuildError("Raw parent extractor fingerprint drifted")
    mentions_path = raw_dir / manifest.mentions_file
    if _sha256_file(mentions_path) != manifest.mentions_sha256:
        raise FrozenPolicyBuildError("Raw parent mentions checksum mismatch")
    mentions = tuple(ScientificEntityMentionEvidence.model_validate(row) for row in _read_jsonl(mentions_path))
    if len(mentions) != contract.candidate.expected_raw_prediction_count:
        raise FrozenPolicyBuildError("Raw parent JSONL count drifted")
    if any(row.build_id != manifest.build_id for row in mentions):
        raise FrozenPolicyBuildError("Raw parent mention build_id mismatch")
    if any(row.extractor_fingerprint != manifest.extractor_fingerprint for row in mentions):
        raise FrozenPolicyBuildError("Raw parent mention extractor fingerprint mismatch")
    return manifest, mentions, raw_dir


def _threshold_policy(contract: ScientificEntityFreshHeldoutFrozenPolicyConfig) -> ScientificEntityThresholdPolicy:
    return ScientificEntityThresholdPolicy(
        default_threshold=contract.policy.default_threshold,
        source_field_thresholds={
            ScientificEntitySourceField.TITLE: contract.policy.title_threshold,
            ScientificEntitySourceField.ABSTRACT: contract.policy.abstract_threshold,
        },
        entity_type_thresholds={},
    )


def _code_revision(project_root: Path) -> str:
    relative_paths = (
        "radar_core/contracts/scientific_entity_fresh_heldout_frozen_policy.py",
        "radar_core/entities/scientific_entity_fresh_heldout_frozen_policy.py",
        "radar_core/entities/scientific_entity_semantic_prompt_raw_floor_policy.py",
        "radar_core/entities/scientific_entity_gliner_calibration.py",
    )
    digest = hashlib.sha256()
    for relative in relative_paths:
        path = project_root / relative
        if not path.is_file():
            raise FrozenPolicyBuildError(f"Policy code revision file is missing: {path}")
        normalized = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        digest.update(relative.encode("utf-8")); digest.update(b"\0")
        digest.update(normalized.encode("utf-8")); digest.update(b"\0")
    return "scientific-entity-fresh-policy-sha256:" + digest.hexdigest()


def _build_descriptor(
    *,
    project_root: Path,
    contract: ScientificEntityFreshHeldoutFrozenPolicyConfig,
    parent_manifest: ScientificEntityEvidenceManifest,
) -> ScientificEntityExtractorDescriptor:
    semantic_payload = {
        "fresh_policy_contract": contract.model_dump(mode="json"),
        "frozen_policy_config_sha256": contract.candidate.frozen_policy_config_sha256,
        "raw_inference_contract_sha256": contract.candidate.raw_inference_contract_sha256,
        "parent_raw_extractor_fingerprint": parent_manifest.extractor_fingerprint,
        "calibration_id": contract.candidate.calibration_id,
        "selected_trial_id": contract.candidate.selected_trial_id,
    }
    parent = parent_manifest.extractor
    return ScientificEntityExtractorDescriptor(
        schema_version=EXTRACTOR_SCHEMA_VERSION,
        name=contract.extractor.name,
        version=contract.extractor.version,
        kind=parent.kind,
        code_revision=_code_revision(project_root),
        config_sha256=sha256_text(_canonical_json(semantic_payload)),
        environment_sha256=parent.environment_sha256,
        model_name=parent.model_name,
        model_revision=parent.model_revision,
        model_artifact_sha256=parent.model_artifact_sha256,
        model_license=parent.model_license,
    )


def _materialize(
    parents: Sequence[ScientificEntityMentionEvidence],
    *,
    contract: ScientificEntityFreshHeldoutFrozenPolicyConfig,
    build_id: str,
    fingerprint: str,
    parent_build_id: str,
) -> tuple[tuple[ScientificEntityMentionEvidence, ...], tuple[FrozenPolicyLineage, ...]]:
    selected = filter_predictions(
        parents,
        policy=_threshold_policy(contract),
        input_threshold=contract.policy.input_threshold,
    )
    rows: list[ScientificEntityMentionEvidence] = []
    lineage: list[FrozenPolicyLineage] = []
    for parent in selected:
        payload = parent.model_dump(mode="json")
        payload.update(
            build_id=build_id,
            extractor_fingerprint=fingerprint,
            evidence_id=build_evidence_id(mention_id=parent.mention_id, extractor_fingerprint=fingerprint),
        )
        candidate = ScientificEntityMentionEvidence.model_validate(payload)
        if candidate.mention_id != parent.mention_id:
            raise FrozenPolicyBuildError("mention_id changed during frozen policy filtering")
        if candidate.evidence_id == parent.evidence_id:
            raise FrozenPolicyBuildError("policy-aware evidence_id must differ from raw parent")
        if candidate.confidence_score != parent.confidence_score or candidate.confidence_kind != parent.confidence_kind:
            raise FrozenPolicyBuildError("confidence changed during frozen policy filtering")
        rows.append(candidate)
        lineage.append(FrozenPolicyLineage(
            build_id=build_id,
            parent_build_id=parent_build_id,
            calibration_id=contract.candidate.calibration_id,
            selected_trial_id=contract.candidate.selected_trial_id,
            mention_id=parent.mention_id,
            parent_evidence_id=parent.evidence_id,
            candidate_evidence_id=candidate.evidence_id,
        ))
    if len({row.mention_id for row in rows}) != len(rows):
        raise FrozenPolicyBuildError("Selected mention IDs must remain unique")
    if len({row.evidence_id for row in rows}) != len(rows):
        raise FrozenPolicyBuildError("Selected evidence IDs must remain unique")
    return tuple(rows), tuple(lineage)


def _quality(build_id: str, parent_count: int, rows: Sequence[ScientificEntityMentionEvidence]) -> dict[str, Any]:
    by_field = Counter(row.source_field.value for row in rows)
    by_type = Counter(row.entity_type.value for row in rows)
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "build_id": build_id,
        "input_document_count": 48,
        "input_prediction_count": parent_count,
        "selected_prediction_count": len(rows),
        "rejected_prediction_count": parent_count - len(rows),
        "selected_prediction_count_by_source_field": {field.value: by_field[field.value] for field in ScientificEntitySourceField},
        "selected_prediction_count_by_entity_type": {kind.value: by_type[kind.value] for kind in ScientificEntityType},
        "input_threshold": 0.4,
        "title_threshold": 0.45,
        "abstract_threshold": 0.625,
        "entity_type_overrides": {},
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "reference_labels_used_for_filtering": False,
        "evaluation_executed": False,
        "acceptance_decision_made": False,
    }


def plan_or_execute_frozen_policy(
    *,
    project_root: Path,
    config_path: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    canonical_path: Path,
    model_cache_dir: Path | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    contract = load_scientific_entity_fresh_heldout_frozen_policy_config(config_path.resolve())
    policy_info = _validate_frozen_policy_config(project_root=project_root, contract=contract)
    raw_summary = _validate_raw_inference(
        project_root=project_root,
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        development_package_dir=development_package_dir.resolve(),
        canonical_path=canonical_path.resolve(),
        model_cache_dir=model_cache_dir,
    )
    _assert_raw_matches_contract(raw_summary, contract)

    output_root = _resolve(project_root, contract.execution.output_root)
    output_dir = output_root / contract.execution.build_id
    already_executed = output_dir.exists()
    if execute and already_executed:
        raise FileExistsError(f"Frozen v0.2c fresh-heldout policy is one-shot and already exists: {output_dir}")

    report: dict[str, Any] = {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "candidate_id": contract.candidate.candidate_id,
        "sample_id": contract.fresh_heldout.sample_id,
        "review_id": contract.fresh_heldout.review_id,
        "raw_build_id": contract.candidate.raw_build_id,
        "raw_mention_count": raw_summary["raw_mention_count"],
        "raw_extractor_fingerprint": contract.candidate.expected_raw_extractor_fingerprint,
        "raw_validation_required_failed_count": raw_summary["required_failed_count"],
        "frozen_policy_config_sha256": policy_info["policy_sha256"],
        "calibration_id": contract.candidate.calibration_id,
        "selected_trial_id": contract.candidate.selected_trial_id,
        "title_threshold": contract.policy.title_threshold,
        "abstract_threshold": contract.policy.abstract_threshold,
        "entity_type_overrides": {},
        "build_id": contract.execution.build_id,
        "output_dir": str(output_dir).replace("\\", "/"),
        "one_shot_already_executed": already_executed,
        "plan_runs_policy_filtering": False,
        "model_inference_executed": False,
        "policy_applied": False,
        "threshold_tuning_executed": False,
        "reference_labels_used_for_filtering": False,
        "evaluation_executed": False,
        "acceptance_decision_made": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "next_slice": contract.next_steps.after_plan,
    }
    if not execute:
        return report

    parent_manifest, parent_mentions, _ = _load_parent(project_root=project_root, contract=contract)
    descriptor = _build_descriptor(project_root=project_root, contract=contract, parent_manifest=parent_manifest)
    fingerprint = build_extractor_fingerprint(descriptor)
    rows, lineage = _materialize(
        parent_mentions,
        contract=contract,
        build_id=contract.execution.build_id,
        fingerprint=fingerprint,
        parent_build_id=parent_manifest.build_id,
    )
    now = generated_at_utc or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(now):
        raise FrozenPolicyBuildError("generated_at_utc must use UTC")
    mentions_bytes = _jsonl_bytes(rows)
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
    derivation = FrozenPolicyDerivationManifest(
        build_id=contract.execution.build_id,
        parent_build_id=parent_manifest.build_id,
        candidate_id=contract.candidate.candidate_id,
        sample_id=contract.fresh_heldout.sample_id,
        review_id=contract.fresh_heldout.review_id,
        runtime_config_sha256=contract.candidate.runtime_config_sha256,
        frozen_policy_config_sha256=contract.candidate.frozen_policy_config_sha256,
        calibration_id=contract.candidate.calibration_id,
        selected_trial_id=contract.candidate.selected_trial_id,
        development_policy_build_id=contract.candidate.development_policy_build_id,
        parent_extractor_fingerprint=parent_manifest.extractor_fingerprint,
        candidate_extractor_fingerprint=fingerprint,
        input_threshold=0.4,
        title_threshold=0.45,
        abstract_threshold=0.625,
        entity_type_overrides={},
        input_prediction_count=1257,
        selected_prediction_count=len(rows),
        rejected_prediction_count=1257-len(rows),
        mention_id_preserved=True,
        evidence_id_recomputed=True,
        confidence_preserved=True,
        model_inference_executed=False,
        threshold_tuning_executed=False,
        reference_labels_used_for_filtering=False,
        evaluation_executed=False,
        acceptance_decision_made=False,
        canonical_truth_mutated=False,
        may_be_used_as_reconcile_input=False,
        production_extractor_selected=False,
        full_corpus_build_authorized=False,
        publication_ready=False,
    )
    quality = _quality(contract.execution.build_id, len(parent_mentions), rows)
    schema = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "mentions_schema_version": MENTION_SCHEMA_VERSION,
        "derivation_schema_version": derivation.schema_version,
        "lineage_schema_version": FrozenPolicyLineage.model_fields["schema_version"].default,
        "identity_semantics": {
            "mention_id": "preserved from raw parent",
            "evidence_id": "recomputed from mention_id plus policy-aware extractor fingerprint",
            "confidence": "preserved model score; policy is selection only",
        },
    }
    readme = "\n".join([
        "# Scientific Entity Fresh Held-Out Frozen Policy v0.2", "",
        "This immutable build applies the already-frozen v0.2c source-field thresholds to the already-frozen fresh-heldout raw predictions.", "",
        f"- parent raw build: `{parent_manifest.build_id}`",
        f"- input predictions: `{len(parent_mentions)}`",
        f"- selected predictions: `{len(rows)}`",
        f"- rejected predictions: `{len(parent_mentions)-len(rows)}`",
        "- title threshold: `0.45`",
        "- abstract threshold: `0.625`",
        "- entity-type overrides: none",
        "- model inference executed: `false`",
        "- threshold tuning executed: `false`",
        "- reference labels used for filtering: `false`",
        "- evaluation executed: `false`",
        "- acceptance decision made: `false`", "",
        "This build is candidate evaluation input only. It is not production-selected and does not authorize a full-corpus build.", "",
    ])

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{contract.execution.build_id}.tmp-", dir=output_dir.parent))
    try:
        (staging / "mentions.jsonl").write_bytes(mentions_bytes)
        (staging / "manifest.json").write_bytes(_json_bytes(manifest))
        (staging / "derivation_manifest.json").write_bytes(_json_bytes(derivation))
        (staging / "evidence_lineage.jsonl").write_bytes(_jsonl_bytes(lineage))
        (staging / "data_quality_summary.json").write_bytes(_json_bytes(quality))
        (staging / "schema.json").write_bytes(_json_bytes(schema))
        (staging / "README.md").write_text(readme, encoding="utf-8", newline="\n")
        checksum_lines = [f"{_sha256_file(staging / filename)}  {filename}" for filename in CHECKSUM_FILES]
        (staging / "checksums.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8", newline="\n")
        staging.rename(output_dir)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    report.update({
        "phase_complete": True,
        "one_shot_already_executed": True,
        "policy_applied": True,
        "selected_prediction_count": len(rows),
        "rejected_prediction_count": len(parent_mentions)-len(rows),
        "policy_extractor_fingerprint": fingerprint,
        "next_slice": contract.next_steps.after_execute,
    })
    return report


def _text_is_utf8_lf(path: Path) -> tuple[bool, str | None]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return False, "UTF-8 BOM is forbidden"
    if b"\r" in raw:
        return False, "CR/CRLF is forbidden"
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"invalid UTF-8: {exc}"
    if raw and not raw.endswith(b"\n"):
        return False, "text file must end with LF"
    return True, None


def validate_frozen_policy_build(
    *,
    project_root: Path,
    config_path: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    canonical_path: Path,
    model_cache_dir: Path | None = None,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    project_root = project_root.resolve()
    contract = load_scientific_entity_fresh_heldout_frozen_policy_config(config_path.resolve())
    policy_info = _validate_frozen_policy_config(project_root=project_root, contract=contract)
    raw_summary = _validate_raw_inference(
        project_root=project_root,
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        development_package_dir=development_package_dir.resolve(),
        canonical_path=canonical_path.resolve(),
        model_cache_dir=model_cache_dir,
    )
    _assert_raw_matches_contract(raw_summary, contract)
    checks: list[tuple[str, bool, str]] = []
    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    output_dir = _resolve(project_root, contract.execution.output_root) / contract.execution.build_id
    add("raw_inference_validation_passed", raw_summary["required_failed_count"] == 0, raw_summary["required_failed_count"])
    add("build_directory_exists", output_dir.is_dir(), output_dir)
    if not output_dir.is_dir():
        return checks, _validation_summary(checks, contract, raw_summary, None)
    files = {p.name for p in output_dir.iterdir() if p.is_file()}
    dirs = {p.name for p in output_dir.iterdir() if p.is_dir()}
    add("required_files_exact", files == set(REQUIRED_FILES), sorted(files))
    add("nested_directories_absent", not dirs, sorted(dirs))
    if files != set(REQUIRED_FILES):
        return checks, _validation_summary(checks, contract, raw_summary, None)
    for filename in REQUIRED_FILES:
        ok, detail = _text_is_utf8_lf(output_dir / filename)
        add(f"utf8_lf::{filename}", ok, detail or "")
    checksum_rows: dict[str, str] = {}
    for line in (output_dir / "checksums.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) == 2:
            checksum_rows[parts[1]] = parts[0]
    add("checksums_cover_exact_files", set(checksum_rows) == set(CHECKSUM_FILES), sorted(checksum_rows))
    for filename in CHECKSUM_FILES:
        add(f"checksum::{filename}", checksum_rows.get(filename) == _sha256_file(output_dir / filename), filename)

    manifest = ScientificEntityEvidenceManifest.model_validate(_read_json(output_dir / "manifest.json"))
    derivation = FrozenPolicyDerivationManifest.model_validate(_read_json(output_dir / "derivation_manifest.json"))
    mentions = tuple(ScientificEntityMentionEvidence.model_validate(row) for row in _read_jsonl(output_dir / "mentions.jsonl"))
    lineage = tuple(FrozenPolicyLineage.model_validate(row) for row in _read_jsonl(output_dir / "evidence_lineage.jsonl"))
    quality = _read_json(output_dir / "data_quality_summary.json")
    parent_manifest, parent_mentions, _ = _load_parent(project_root=project_root, contract=contract)
    expected_descriptor = _build_descriptor(project_root=project_root, contract=contract, parent_manifest=parent_manifest)
    expected_fingerprint = build_extractor_fingerprint(expected_descriptor)
    expected_rows, expected_lineage = _materialize(
        parent_mentions,
        contract=contract,
        build_id=contract.execution.build_id,
        fingerprint=expected_fingerprint,
        parent_build_id=parent_manifest.build_id,
    )

    add("build_id_exact", manifest.build_id == contract.execution.build_id, manifest.build_id)
    add("candidate_status", manifest.status == EntityEvidenceBuildStatus.CANDIDATE, manifest.status)
    add("parent_build_id_exact", derivation.parent_build_id == contract.candidate.raw_build_id, derivation.parent_build_id)
    add("input_prediction_count_1257", derivation.input_prediction_count == 1257, derivation.input_prediction_count)
    add("selected_plus_rejected_equals_input", derivation.selected_prediction_count + derivation.rejected_prediction_count == 1257, "")
    add("manifest_selected_count_exact", manifest.mention_count == derivation.selected_prediction_count == len(mentions), manifest.mention_count)
    add("quality_counts_exact", quality.get("selected_prediction_count") == len(mentions) and quality.get("rejected_prediction_count") == 1257-len(mentions), quality)
    add("policy_config_sha_exact", derivation.frozen_policy_config_sha256 == policy_info["policy_sha256"] == contract.candidate.frozen_policy_config_sha256, derivation.frozen_policy_config_sha256)
    add("runtime_config_sha_exact", derivation.runtime_config_sha256 == contract.candidate.runtime_config_sha256, derivation.runtime_config_sha256)
    add("selected_trial_exact", derivation.selected_trial_id == contract.candidate.selected_trial_id, derivation.selected_trial_id)
    add("thresholds_exact", derivation.title_threshold == 0.45 and derivation.abstract_threshold == 0.625 and not derivation.entity_type_overrides, "")
    add("parent_fingerprint_exact", derivation.parent_extractor_fingerprint == contract.candidate.expected_raw_extractor_fingerprint, derivation.parent_extractor_fingerprint)
    add("candidate_fingerprint_exact", manifest.extractor_fingerprint == derivation.candidate_extractor_fingerprint == expected_fingerprint, manifest.extractor_fingerprint)
    add("extractor_fingerprint_changed", expected_fingerprint != parent_manifest.extractor_fingerprint, expected_fingerprint)
    add("mention_ids_exact_filtered_subset", [row.mention_id for row in mentions] == [row.mention_id for row in expected_rows], len(mentions))
    add("evidence_ids_exact", [row.evidence_id for row in mentions] == [row.evidence_id for row in expected_rows], len(mentions))
    add("lineage_exact", [row.model_dump(mode="json") for row in lineage] == [row.model_dump(mode="json") for row in expected_lineage], len(lineage))
    add("confidence_preserved", all(row.confidence_score == parent.confidence_score and row.confidence_kind == parent.confidence_kind for row, parent in [(row, {p.mention_id:p for p in parent_mentions}[row.mention_id]) for row in mentions]), "")
    add("model_inference_not_run_by_policy", derivation.model_inference_executed is False, "")
    add("threshold_tuning_not_run", derivation.threshold_tuning_executed is False, "")
    add("reference_labels_not_used_for_filtering", derivation.reference_labels_used_for_filtering is False, "")
    add("evaluation_not_run", derivation.evaluation_executed is False, "")
    add("acceptance_not_decided", derivation.acceptance_decision_made is False, "")
    add("canonical_truth_not_mutated", manifest.canonical_truth_mutated is False and derivation.canonical_truth_mutated is False, "")
    add("production_not_selected", derivation.production_extractor_selected is False, "")
    add("full_corpus_not_authorized", derivation.full_corpus_build_authorized is False, "")

    return checks, _validation_summary(checks, contract, raw_summary, derivation)


def _validation_summary(
    checks: list[tuple[str, bool, str]],
    contract: ScientificEntityFreshHeldoutFrozenPolicyConfig,
    raw_summary: dict[str, Any],
    derivation: FrozenPolicyDerivationManifest | None,
) -> dict[str, Any]:
    failed = [name for name, ok, _ in checks if not ok]
    return {
        "report": REPORT_NAME,
        "candidate_id": contract.candidate.candidate_id,
        "sample_id": contract.fresh_heldout.sample_id,
        "review_id": contract.fresh_heldout.review_id,
        "raw_build_id": contract.candidate.raw_build_id,
        "raw_mention_count": raw_summary.get("raw_mention_count"),
        "build_id": contract.execution.build_id,
        "selected_prediction_count": None if derivation is None else derivation.selected_prediction_count,
        "rejected_prediction_count": None if derivation is None else derivation.rejected_prediction_count,
        "title_threshold": 0.45,
        "abstract_threshold": 0.625,
        "model_inference_executed_by_policy": False,
        "policy_applied": derivation is not None,
        "threshold_tuning_executed": False,
        "reference_labels_used_for_filtering": False,
        "evaluation_executed": False,
        "acceptance_decision_made": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "next_slice": contract.next_steps.after_validation,
    }
