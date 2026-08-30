from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

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
from radar_core.contracts.scientific_entity_semantic_prompt_raw_floor_calibration import (
    RawFloorCalibrationDiagnostics,
    RawFloorCalibrationTrial,
    RawFloorSelectedPolicy,
)
from radar_core.contracts.scientific_entity_semantic_prompt_raw_floor_policy import (
    POLICY_DERIVATION_SCHEMA_VERSION,
    POLICY_LINEAGE_SCHEMA_VERSION,
    RawFloorPolicyConfig,
    RawFloorPolicyDerivationManifest,
    RawFloorPolicyLineage,
    load_raw_floor_policy_config,
)
from radar_core.contracts.scientific_entity_semantic_prompt_raw_floor_extension import (
    canonical_config_sha256,
    load_semantic_prompt_raw_floor_extension_config,
)
from radar_core.entities.scientific_entity_gliner import (
    gliner_config_sha256,
    load_gliner_config,
    normalized_source_bundle_revision,
)
from radar_core.entities.scientific_entity_gliner_calibration import filter_predictions


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "scientific_entity_semantic_prompt_raw_floor_policy_v0.2c.yaml"
REPORT_NAME = "scientific_entity_semantic_prompt_raw_floor_policy_v02c"
OUTPUT_SCHEMA_VERSION = "scientific_entity_semantic_prompt_raw_floor_policy_output_v0.2c"
QUALITY_SCHEMA_VERSION = "scientific_entity_semantic_prompt_raw_floor_policy_quality_v0.2c"
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


class RawFloorPolicyBuildError(RuntimeError):
    """Raised when selected v0.2c policy materialization cannot be reproduced safely."""


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(payload: Any) -> bytes:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(rows: Sequence[Any]) -> bytes:
    chunks: list[str] = []
    for row in rows:
        payload = row.model_dump(mode="json") if hasattr(row, "model_dump") else row
        chunks.append(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return (("\n".join(chunks) + "\n") if chunks else "").encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RawFloorPolicyBuildError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise RawFloorPolicyBuildError(f"Blank JSONL line: {path}:{line_number}")
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise RawFloorPolicyBuildError(f"Expected JSON object: {path}:{line_number}")
            rows.append(payload)
    return rows


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def policy_config_sha256(config: RawFloorPolicyConfig) -> str:
    return sha256_text(_canonical_json(config.model_dump(mode="json")))


def _threshold_policy(config: RawFloorPolicyConfig) -> ScientificEntityThresholdPolicy:
    return ScientificEntityThresholdPolicy(
        default_threshold=config.policy.default_threshold,
        source_field_thresholds=config.policy.source_field_thresholds,
        entity_type_thresholds={},
    )


def _default_build_id(now: datetime) -> str:
    return f"scientific-entity-semantic-prompt-raw-floor-policy-v0.2c-{now.strftime('%Y%m%dT%H%M%S%fZ')}"


def _load_parent(parent_build_dir: Path, config: RawFloorPolicyConfig) -> tuple[ScientificEntityEvidenceManifest, tuple[ScientificEntityMentionEvidence, ...]]:
    manifest_path = parent_build_dir / "manifest.json"
    manifest = ScientificEntityEvidenceManifest.model_validate(_read_json(manifest_path))
    if manifest.build_id != config.candidate.raw_build_id:
        raise RawFloorPolicyBuildError("raw parent build_id drifted from frozen v0.2c lineage")
    if manifest.status != EntityEvidenceBuildStatus.CANDIDATE:
        raise RawFloorPolicyBuildError("v0.2c policy requires candidate raw parent build")
    mentions_path = parent_build_dir / manifest.mentions_file
    if manifest.mentions_sha256 != _sha256_file(mentions_path):
        raise RawFloorPolicyBuildError("raw parent mentions checksum mismatch")
    rows = tuple(ScientificEntityMentionEvidence.model_validate(row) for row in _read_jsonl(mentions_path))
    if len(rows) != config.candidate.expected_raw_prediction_count or len(rows) != manifest.mention_count:
        raise RawFloorPolicyBuildError("raw parent prediction count drifted")
    if any(row.build_id != manifest.build_id for row in rows):
        raise RawFloorPolicyBuildError("raw parent mention build_id mismatch")
    if any(row.extractor_fingerprint != manifest.extractor_fingerprint for row in rows):
        raise RawFloorPolicyBuildError("raw parent extractor fingerprint mismatch")
    return manifest, rows


def _load_calibration(calibration_dir: Path, config: RawFloorPolicyConfig, parent_manifest: ScientificEntityEvidenceManifest) -> tuple[dict[str, Any], RawFloorSelectedPolicy, RawFloorCalibrationTrial, RawFloorCalibrationDiagnostics]:
    manifest_path = calibration_dir / "manifest.json"
    selected_path = calibration_dir / "selected_policy.json"
    trials_path = calibration_dir / "trials.jsonl"
    diagnostics_path = calibration_dir / "diagnostics.json"
    manifest = _read_json(manifest_path)
    selected = RawFloorSelectedPolicy.model_validate(_read_json(selected_path))
    diagnostics = RawFloorCalibrationDiagnostics.model_validate(_read_json(diagnostics_path))
    trials = tuple(RawFloorCalibrationTrial.model_validate(row) for row in _read_jsonl(trials_path))
    if manifest.get("calibration_id") != config.candidate.calibration_id or selected.calibration_id != config.candidate.calibration_id:
        raise RawFloorPolicyBuildError("calibration_id drifted")
    if calibration_dir.name != config.candidate.calibration_id:
        raise RawFloorPolicyBuildError("calibration directory name drifted")
    if manifest.get("raw_build_id") != parent_manifest.build_id:
        raise RawFloorPolicyBuildError("calibration raw_build_id does not match parent")
    # Parent raw-build manifest SHA is checked by the builder against the explicit parent path.
    if manifest.get("raw_prediction_count") != config.candidate.expected_raw_prediction_count:
        raise RawFloorPolicyBuildError("calibration raw_prediction_count drifted")
    if selected.selected_trial_id != config.candidate.selected_trial_id:
        raise RawFloorPolicyBuildError("selected trial_id drifted")
    if abs(float(selected.title_threshold) - 0.45) > 1e-12 or abs(float(selected.abstract_threshold) - 0.625) > 1e-12:
        raise RawFloorPolicyBuildError("selected thresholds drifted")
    if selected.all_hard_gates_passed is not True or selected.candidate_promising_for_future_freeze is not True:
        raise RawFloorPolicyBuildError("v0.2c selected policy must pass frozen development gates")
    if diagnostics.selected_trial_id != selected.selected_trial_id:
        raise RawFloorPolicyBuildError("calibration diagnostics selected trial drifted")
    if diagnostics.selected_title_at_candidate_raw_floor is not False or diagnostics.raw_input_floor_may_still_be_binding is not False:
        raise RawFloorPolicyBuildError("selected title must remain above candidate raw floor")
    selected_trial = next((row for row in trials if row.trial_id == selected.selected_trial_id), None)
    if selected_trial is None:
        raise RawFloorPolicyBuildError("selected calibration trial missing")
    if not selected_trial.eligible_for_selection or not selected_trial.semantic_guardrails_passed:
        raise RawFloorPolicyBuildError("selected calibration trial is not semantic-safe")
    if selected_trial.combined_exact_f1 != 0.403677 or selected_trial.consumed_heldout_exact_f1 != 0.4:
        raise RawFloorPolicyBuildError("selected calibration trial metrics drifted")
    return manifest, selected, selected_trial, diagnostics


def _validate_development_package(package_dir: Path, config: RawFloorPolicyConfig, parent_manifest: ScientificEntityEvidenceManifest) -> dict[str, Any]:
    package = _read_json(package_dir / "manifest.json")
    canonical_path = package_dir / "canonical_documents.jsonl"
    if package.get("package_id") != config.candidate.development_package_id:
        raise RawFloorPolicyBuildError("development package_id drifted")
    if package.get("combined_document_count") != config.candidate.expected_document_count:
        raise RawFloorPolicyBuildError("development document count drifted")
    canonical_sha = _sha256_file(canonical_path)
    if package.get("canonical_documents_sha256") != canonical_sha:
        raise RawFloorPolicyBuildError("development canonical checksum mismatch")
    if parent_manifest.canonical_input.document_count != config.candidate.expected_document_count or parent_manifest.canonical_input.sha256 != canonical_sha:
        raise RawFloorPolicyBuildError("raw parent canonical input does not match frozen package")
    return package


def _validate_design_runtime(config: RawFloorPolicyConfig, parent_manifest: ScientificEntityEvidenceManifest) -> tuple[str, str]:
    design_path = _resolve(config.candidate.design_config_path)
    runtime_path = _resolve(config.candidate.runtime_config_path)
    design = load_semantic_prompt_raw_floor_extension_config(design_path)
    if design.lineage.candidate_id != config.candidate.candidate_id:
        raise RawFloorPolicyBuildError("v0.2c design candidate_id drifted")
    if design.raw_inference.candidate_floor != config.policy.input_threshold:
        raise RawFloorPolicyBuildError("policy input threshold drifted from raw floor")
    if design.bounded_policy_search.fixed_abstract_threshold != 0.625 or 0.45 not in design.bounded_policy_search.title_thresholds:
        raise RawFloorPolicyBuildError("selected thresholds are not part of frozen v0.2c search")
    runtime = load_gliner_config(runtime_path)
    runtime_sha = gliner_config_sha256(runtime)
    if parent_manifest.extractor.config_sha256 != runtime_sha:
        raise RawFloorPolicyBuildError("raw parent runtime config SHA mismatch")
    return canonical_config_sha256(design), runtime_sha


def _build_descriptor(config: RawFloorPolicyConfig, parent_manifest: ScientificEntityEvidenceManifest, design_sha: str, runtime_sha: str, calibration_manifest_sha: str, selected_policy_sha: str) -> ScientificEntityExtractorDescriptor:
    parent = parent_manifest.extractor
    semantic_payload = {
        "policy_config": config.model_dump(mode="json"),
        "design_config_sha256": design_sha,
        "runtime_config_sha256": runtime_sha,
        "calibration_manifest_sha256": calibration_manifest_sha,
        "calibration_selected_policy_sha256": selected_policy_sha,
        "selected_trial_id": config.candidate.selected_trial_id,
        "parent_raw_extractor_fingerprint": parent_manifest.extractor_fingerprint,
    }
    return ScientificEntityExtractorDescriptor(
        schema_version=EXTRACTOR_SCHEMA_VERSION,
        name=config.extractor.name,
        version=config.extractor.version,
        kind=parent.kind,
        code_revision=normalized_source_bundle_revision(PROJECT_ROOT),
        config_sha256=sha256_text(_canonical_json(semantic_payload)),
        environment_sha256=parent.environment_sha256,
        model_name=parent.model_name,
        model_revision=parent.model_revision,
        model_artifact_sha256=parent.model_artifact_sha256,
        model_license=parent.model_license,
    )


def _materialize(parent_mentions: Sequence[ScientificEntityMentionEvidence], config: RawFloorPolicyConfig, build_id: str, fingerprint: str, parent_build_id: str) -> tuple[tuple[ScientificEntityMentionEvidence, ...], tuple[RawFloorPolicyLineage, ...]]:
    selected = filter_predictions(parent_mentions, policy=_threshold_policy(config), input_threshold=config.policy.input_threshold)
    rows: list[ScientificEntityMentionEvidence] = []
    lineage: list[RawFloorPolicyLineage] = []
    for parent in selected:
        payload = parent.model_dump(mode="json")
        payload.update(
            build_id=build_id,
            extractor_fingerprint=fingerprint,
            evidence_id=build_evidence_id(mention_id=parent.mention_id, extractor_fingerprint=fingerprint),
        )
        candidate = ScientificEntityMentionEvidence.model_validate(payload)
        if candidate.mention_id != parent.mention_id:
            raise RawFloorPolicyBuildError("mention_id changed during policy filtering")
        if candidate.evidence_id == parent.evidence_id:
            raise RawFloorPolicyBuildError("policy-aware evidence_id must differ from raw parent")
        if candidate.confidence_score != parent.confidence_score or candidate.confidence_kind != parent.confidence_kind:
            raise RawFloorPolicyBuildError("confidence changed during policy filtering")
        rows.append(candidate)
        lineage.append(RawFloorPolicyLineage(
            build_id=build_id,
            parent_build_id=parent_build_id,
            calibration_id=config.candidate.calibration_id,
            selected_trial_id=config.candidate.selected_trial_id,
            mention_id=parent.mention_id,
            parent_evidence_id=parent.evidence_id,
            candidate_evidence_id=candidate.evidence_id,
        ))
    if len({row.mention_id for row in rows}) != len(rows) or len({row.evidence_id for row in rows}) != len(rows):
        raise RawFloorPolicyBuildError("selected identities must be unique")
    return tuple(rows), tuple(lineage)


def _quality(build_id: str, parent_count: int, rows: Sequence[ScientificEntityMentionEvidence]) -> dict[str, Any]:
    by_field = Counter(row.source_field.value for row in rows)
    by_type = Counter(row.entity_type.value for row in rows)
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "build_id": build_id,
        "development_document_count": 72,
        "input_prediction_count": parent_count,
        "selected_prediction_count": len(rows),
        "rejected_prediction_count": parent_count - len(rows),
        "selected_prediction_count_by_source_field": {field.value: by_field[field.value] for field in ScientificEntitySourceField},
        "selected_prediction_count_by_entity_type": {kind.value: by_type[kind.value] for kind in ScientificEntityType},
        "input_threshold": 0.4,
        "title_threshold": 0.45,
        "abstract_threshold": 0.625,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "fresh_heldout_consumed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
    }


def _schema() -> dict[str, Any]:
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "mentions_schema_version": MENTION_SCHEMA_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "derivation_manifest_schema_version": POLICY_DERIVATION_SCHEMA_VERSION,
        "lineage_schema_version": POLICY_LINEAGE_SCHEMA_VERSION,
        "quality_schema_version": QUALITY_SCHEMA_VERSION,
        "serialization": {"encoding": "utf-8", "line_ending": "lf"},
        "mentions_json_schema": ScientificEntityMentionEvidence.model_json_schema(),
        "manifest_json_schema": ScientificEntityEvidenceManifest.model_json_schema(),
        "derivation_manifest_json_schema": RawFloorPolicyDerivationManifest.model_json_schema(),
        "lineage_json_schema": RawFloorPolicyLineage.model_json_schema(),
    }


def build_raw_floor_selected_policy(*, config_path: Path = DEFAULT_CONFIG_PATH, parent_build_dir: Path, development_package_dir: Path, calibration_dir: Path, output_root: Path | None = None, build_id: str | None = None, execute: bool = False, generated_at_utc: datetime | None = None) -> dict[str, Any]:
    config = load_raw_floor_policy_config(config_path.resolve())
    parent_dir = parent_build_dir.resolve()
    package_dir = development_package_dir.resolve()
    calibration_dir = calibration_dir.resolve()
    parent_manifest, parent_mentions = _load_parent(parent_dir, config)
    package = _validate_development_package(package_dir, config, parent_manifest)
    calibration_manifest, selected_policy, selected_trial, diagnostics = _load_calibration(calibration_dir, config, parent_manifest)
    if calibration_manifest.get("raw_build_manifest_sha256") != _sha256_file(parent_dir / "manifest.json"):
        raise RawFloorPolicyBuildError("calibration raw build manifest SHA mismatch")
    design_sha, runtime_sha = _validate_design_runtime(config, parent_manifest)
    calibration_manifest_sha = _sha256_file(calibration_dir / "manifest.json")
    selected_policy_sha = _sha256_file(calibration_dir / "selected_policy.json")
    descriptor = _build_descriptor(config, parent_manifest, design_sha, runtime_sha, calibration_manifest_sha, selected_policy_sha)
    fingerprint = build_extractor_fingerprint(descriptor)
    if fingerprint == parent_manifest.extractor_fingerprint:
        raise RawFloorPolicyBuildError("policy-aware fingerprint must differ from raw parent")

    now = generated_at_utc or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(now):
        raise RawFloorPolicyBuildError("generated_at_utc must be timezone-aware UTC")
    selected_build_id = build_id or _default_build_id(now)
    selected_output_root = _resolve(output_root or config.outputs.root)
    output_dir = selected_output_root / selected_build_id
    if execute and output_dir.exists():
        raise FileExistsError(f"Immutable selected-policy build already exists: {output_dir}")

    rows, lineage = _materialize(parent_mentions, config, selected_build_id, fingerprint, parent_manifest.build_id)
    if len(rows) != selected_trial.selected_prediction_count:
        raise RawFloorPolicyBuildError(
            f"materialized selected count {len(rows)} != calibration trial {selected_trial.selected_prediction_count}"
        )
    mentions_bytes = _jsonl_bytes(rows)
    lineage_bytes = _jsonl_bytes(lineage)
    manifest = ScientificEntityEvidenceManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        build_id=selected_build_id,
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
    derivation = RawFloorPolicyDerivationManifest(
        build_id=selected_build_id,
        parent_build_id=parent_manifest.build_id,
        development_package_id=str(package["package_id"]),
        candidate_id=config.candidate.candidate_id,
        calibration_id=config.candidate.calibration_id,
        selected_trial_id=config.candidate.selected_trial_id,
        design_config_sha256=design_sha,
        runtime_config_sha256=runtime_sha,
        calibration_manifest_sha256=calibration_manifest_sha,
        calibration_selected_policy_sha256=selected_policy_sha,
        parent_extractor_fingerprint=parent_manifest.extractor_fingerprint,
        candidate_extractor_fingerprint=fingerprint,
        input_threshold=0.4,
        title_threshold=0.45,
        abstract_threshold=0.625,
        entity_type_overrides={},
        input_prediction_count=1762,
        selected_prediction_count=len(rows),
        rejected_prediction_count=1762-len(rows),
        calibration_trial_selected_prediction_count=selected_trial.selected_prediction_count,
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
    quality = _quality(selected_build_id, len(parent_mentions), rows)
    schema = _schema()
    readme = "\n".join([
        "# Scientific Entity Semantic Prompt Raw-Floor Selected Policy v0.2c", "",
        f"- build_id: `{selected_build_id}`",
        f"- parent_raw_build_id: `{parent_manifest.build_id}`",
        f"- calibration_id: `{config.candidate.calibration_id}`",
        f"- selected_trial_id: `{config.candidate.selected_trial_id}`",
        "- policy: `title >= 0.45 / abstract >= 0.625`",
        f"- input_prediction_count: `{len(parent_mentions)}`",
        f"- selected_prediction_count: `{len(rows)}`", "",
        "No model inference or threshold tuning occurs in this materialization.",
        "This is development-only evidence; fresh independent held-out evidence is still required before acceptance.", "",
    ])

    if execute:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{selected_build_id}.tmp-", dir=output_dir.parent))
        try:
            (staging / "mentions.jsonl").write_bytes(mentions_bytes)
            (staging / "evidence_lineage.jsonl").write_bytes(lineage_bytes)
            (staging / "manifest.json").write_bytes(_json_bytes(manifest))
            (staging / "derivation_manifest.json").write_bytes(_json_bytes(derivation))
            (staging / "data_quality_summary.json").write_bytes(_json_bytes(quality))
            (staging / "schema.json").write_bytes(_json_bytes(schema))
            (staging / "README.md").write_text(readme, encoding="utf-8", newline="\n")
            checksum_lines = [f"{_sha256_file(staging / filename)}  {filename}" for filename in CHECKSUM_FILES]
            (staging / "checksums.txt").write_text("\n".join(checksum_lines)+"\n", encoding="utf-8", newline="\n")
            staging.rename(output_dir)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise

    return {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": execute,
        "build_id": selected_build_id,
        "parent_build_id": parent_manifest.build_id,
        "calibration_id": config.candidate.calibration_id,
        "selected_trial_id": config.candidate.selected_trial_id,
        "input_document_count": 72,
        "input_prediction_count": len(parent_mentions),
        "selected_prediction_count": len(rows),
        "rejected_prediction_count": len(parent_mentions)-len(rows),
        "extractor_fingerprint_changed": fingerprint != parent_manifest.extractor_fingerprint,
        "title_threshold": 0.45,
        "abstract_threshold": 0.625,
        "calibration_hard_gates_passed": selected_policy.all_hard_gates_passed,
        "calibration_candidate_promising": selected_policy.candidate_promising_for_future_freeze,
        "selected_title_at_candidate_raw_floor": diagnostics.selected_title_at_candidate_raw_floor,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "fresh_heldout_consumed": False,
        "canonical_truth_mutated": False,
        "full_corpus_build_authorized": False,
        "production_extractor_selected": False,
        "output_dir": str(output_dir).replace("\\", "/"),
        "next_slice": "controlled_v02c_24_48_72_comparison",
    }


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


def validate_raw_floor_selected_policy_build(*, build_dir: Path, parent_build_dir: Path, development_package_dir: Path, calibration_dir: Path, config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    config = load_raw_floor_policy_config(config_path.resolve())
    build_dir = build_dir.resolve()
    checks: list[dict[str, Any]] = []
    def add(name: str, ok: bool, details: str | None = None) -> None:
        checks.append({"name": name, "ok": bool(ok), "required": True, "details": details})

    add("build_directory_exists", build_dir.is_dir(), str(build_dir))
    if not build_dir.is_dir():
        return _validation_report(checks, None, None)
    files = {p.name for p in build_dir.iterdir() if p.is_file()}
    dirs = {p.name for p in build_dir.iterdir() if p.is_dir()}
    add("required_files_exact", files == set(REQUIRED_FILES))
    add("nested_directories_absent", not dirs)
    if files != set(REQUIRED_FILES):
        return _validation_report(checks, None, None)
    for filename in REQUIRED_FILES:
        ok, details = _text_is_utf8_lf(build_dir / filename)
        add(f"utf8_lf::{filename}", ok, details)
    checksum_rows: dict[str, str] = {}
    for line in (build_dir / "checksums.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, filename = line.split("  ", 1)
            checksum_rows[filename] = digest
    add("checksum_file_set_exact", set(checksum_rows) == set(CHECKSUM_FILES))
    for filename in CHECKSUM_FILES:
        add(f"checksum_matches::{filename}", checksum_rows.get(filename) == _sha256_file(build_dir / filename))
    try:
        manifest = ScientificEntityEvidenceManifest.model_validate(_read_json(build_dir / "manifest.json"))
        derivation = RawFloorPolicyDerivationManifest.model_validate(_read_json(build_dir / "derivation_manifest.json"))
        mentions = tuple(ScientificEntityMentionEvidence.model_validate(row) for row in _read_jsonl(build_dir / "mentions.jsonl"))
        lineage = tuple(RawFloorPolicyLineage.model_validate(row) for row in _read_jsonl(build_dir / "evidence_lineage.jsonl"))
        add("output_contracts_parse", True)
    except Exception as exc:
        add("output_contracts_parse", False, f"{type(exc).__name__}: {exc}")
        return _validation_report(checks, None, None)
    parent_manifest, parent_mentions = _load_parent(parent_build_dir.resolve(), config)
    package = _validate_development_package(development_package_dir.resolve(), config, parent_manifest)
    calibration_manifest, selected_policy, selected_trial, diagnostics = _load_calibration(calibration_dir.resolve(), config, parent_manifest)
    add("directory_matches_build_id", build_dir.name == manifest.build_id)
    add("status_candidate", manifest.status == EntityEvidenceBuildStatus.CANDIDATE)
    add("parent_build_id_matches", derivation.parent_build_id == parent_manifest.build_id)
    add("calibration_id_matches", derivation.calibration_id == config.candidate.calibration_id)
    add("selected_trial_matches", derivation.selected_trial_id == config.candidate.selected_trial_id)
    add("input_count_matches", derivation.input_prediction_count == len(parent_mentions) == 1762)
    add("selected_count_matches_calibration", len(mentions) == derivation.selected_prediction_count == selected_trial.selected_prediction_count)
    add("rejected_count_matches", derivation.rejected_prediction_count == len(parent_mentions)-len(mentions))
    add("manifest_mentions_count_matches", manifest.mention_count == len(mentions))
    add("manifest_mentions_sha_matches", manifest.mentions_sha256 == _sha256_file(build_dir / "mentions.jsonl"))
    add("fingerprint_changed", manifest.extractor_fingerprint != parent_manifest.extractor_fingerprint)
    add("derivation_fingerprint_matches", derivation.candidate_extractor_fingerprint == manifest.extractor_fingerprint)
    parent_by_id = {row.mention_id: row for row in parent_mentions}
    add("mention_ids_unique", len({row.mention_id for row in mentions}) == len(mentions))
    add("evidence_ids_unique", len({row.evidence_id for row in mentions}) == len(mentions))
    add("all_mentions_from_parent", all(row.mention_id in parent_by_id for row in mentions))
    add("confidence_preserved", all(row.confidence_score == parent_by_id[row.mention_id].confidence_score and row.confidence_kind == parent_by_id[row.mention_id].confidence_kind for row in mentions))
    add("lineage_count_matches", len(lineage) == len(mentions))
    lineage_by_mention = {row.mention_id: row for row in lineage}
    add("lineage_exact", all(row.mention_id in lineage_by_mention and lineage_by_mention[row.mention_id].candidate_evidence_id == row.evidence_id and lineage_by_mention[row.mention_id].parent_evidence_id == parent_by_id[row.mention_id].evidence_id for row in mentions))
    expected_selected = filter_predictions(parent_mentions, policy=_threshold_policy(config), input_threshold=config.policy.input_threshold)
    add("policy_recomputed_exactly", [row.mention_id for row in mentions] == [row.mention_id for row in expected_selected])
    add("calibration_manifest_sha_matches", derivation.calibration_manifest_sha256 == _sha256_file(calibration_dir / "manifest.json"))
    add("calibration_selected_policy_sha_matches", derivation.calibration_selected_policy_sha256 == _sha256_file(calibration_dir / "selected_policy.json"))
    add("calibration_hard_gates_passed", selected_policy.all_hard_gates_passed is True)
    add("calibration_candidate_promising", selected_policy.candidate_promising_for_future_freeze is True)
    add("selected_title_not_at_floor", diagnostics.selected_title_at_candidate_raw_floor is False)
    add("fresh_heldout_preserved", derivation.future_v02_acceptance_requires_new_disjoint_heldout is True and derivation.fresh_heldout_consumed is False)
    add("canonical_truth_not_mutated", manifest.canonical_truth_mutated is False and derivation.canonical_truth_mutated is False)
    add("full_corpus_not_authorized", derivation.full_corpus_build_authorized is False)
    add("production_not_selected", derivation.production_extractor_selected is False)

    return _validation_report(checks, manifest, derivation)


def _validation_report(checks: Sequence[Mapping[str, Any]], manifest: ScientificEntityEvidenceManifest | None, derivation: RawFloorPolicyDerivationManifest | None) -> dict[str, Any]:
    failed = [row for row in checks if row["required"] and not row["ok"]]
    return {
        "report": REPORT_NAME,
        "build_id": None if manifest is None else manifest.build_id,
        "parent_build_id": None if derivation is None else derivation.parent_build_id,
        "calibration_id": None if derivation is None else derivation.calibration_id,
        "input_document_count": None if manifest is None else manifest.canonical_input.document_count,
        "input_prediction_count": None if derivation is None else derivation.input_prediction_count,
        "selected_prediction_count": None if derivation is None else derivation.selected_prediction_count,
        "rejected_prediction_count": None if derivation is None else derivation.rejected_prediction_count,
        "extractor_fingerprint_changed": None if manifest is None or derivation is None else manifest.extractor_fingerprint != derivation.parent_extractor_fingerprint,
        "calibration_hard_gates_passed": None if derivation is None else derivation.calibration_hard_gates_passed,
        "calibration_candidate_promising": None if derivation is None else derivation.calibration_candidate_promising,
        "model_inference_executed": False if derivation is None else derivation.model_inference_executed,
        "threshold_tuning_executed": False if derivation is None else derivation.threshold_tuning_executed,
        "fresh_heldout_consumed": False if derivation is None else derivation.fresh_heldout_consumed,
        "canonical_truth_mutated": False if derivation is None else derivation.canonical_truth_mutated,
        "full_corpus_build_authorized": False if derivation is None else derivation.full_corpus_build_authorized,
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "next_slice": "controlled_v02c_24_48_72_comparison",
        "checks": list(checks),
    }
