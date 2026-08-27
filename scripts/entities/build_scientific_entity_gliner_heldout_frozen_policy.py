from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from radar_core.contracts.scientific_entity_evidence import (
    MANIFEST_SCHEMA_VERSION,
    MENTION_SCHEMA_VERSION,
    EntityEvidenceBuildStatus,
    ScientificEntityEvidenceManifest,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    ScientificEntityType,
    build_extractor_fingerprint,
)
from radar_core.contracts.scientific_entity_gliner_calibration import (
    ScientificEntityCalibrationProfileName,
    ScientificEntityCalibrationProfiles,
    ScientificEntityCalibrationTrial,
    ScientificEntityCalibrationTrialStage,
    ScientificEntityGLiNERCalibrationManifest,
)
from radar_core.contracts.scientific_entity_gliner_frozen_policy import (
    EVIDENCE_LINEAGE_SCHEMA_VERSION,
    ScientificEntityFrozenPolicyEvidenceLineage,
)
from radar_core.contracts.scientific_entity_gliner_heldout_policy import (
    DERIVATION_MANIFEST_SCHEMA_VERSION,
    ScientificEntityGLiNERHeldoutPolicyDerivationManifest,
)
from radar_core.entities.scientific_entity_gliner_heldout_policy import (
    ScientificEntityGLiNERHeldoutPolicyConfig,
    build_descriptor,
    config_sha256,
    load_config,
    materialize,
)

REPORT_NAME = "scientific_entity_gliner_heldout_frozen_policy_v01"
OUTPUT_SCHEMA_VERSION = "scientific_entity_gliner_heldout_frozen_policy_output_schema_v0.1"
QUALITY_SCHEMA_VERSION = "scientific_entity_gliner_heldout_frozen_policy_quality_v0.1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "scientific_entity_gliner_heldout_frozen_policy_v0.1.yaml"
CHECKSUM_FILES = (
    "mentions.jsonl",
    "manifest.json",
    "schema.json",
    "data_quality_summary.json",
    "README.md",
    "derivation_manifest.json",
    "evidence_lineage.jsonl",
)


class HeldoutPolicyBuildError(RuntimeError):
    pass


def _norm(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def _resolve(path: Path | str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p.resolve()


def _rel(path: Path) -> str:
    try:
        return _norm(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return _norm(path.resolve())


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise HeldoutPolicyBuildError(f"Expected JSON object: {path}")
    return payload


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise HeldoutPolicyBuildError(f"Blank JSONL line: {path}:{n}")
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise HeldoutPolicyBuildError(f"Expected object: {path}:{n}")
        rows.append(payload)
    return rows


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _jsonl_bytes(rows: Sequence[Any]) -> bytes:
    chunks = [json.dumps((row.model_dump(mode="json") if hasattr(row, "model_dump") else row), ensure_ascii=False, sort_keys=True, separators=(",", ":")) for row in rows]
    return (("\n".join(chunks) + "\n") if chunks else "").encode("utf-8")


def _write_lf(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _default_build_id(now: datetime) -> str:
    return f"scientific-entity-gliner-small-v2.5-heldout-frozen-policy-v0.1-{now.strftime('%Y%m%dT%H%M%S%fZ')}"


def _load_parent(parent_dir: Path, config: ScientificEntityGLiNERHeldoutPolicyConfig):
    manifest_path = parent_dir / "manifest.json"
    mentions_path = parent_dir / "mentions.jsonl"
    quality_path = parent_dir / "data_quality_summary.json"
    for p in (manifest_path, mentions_path, quality_path):
        if not p.is_file():
            raise FileNotFoundError(p)
    manifest = ScientificEntityEvidenceManifest.model_validate(_json(manifest_path))
    quality = _json(quality_path)
    if manifest.build_id != config.parent.build_id:
        raise HeldoutPolicyBuildError("parent build_id mismatch")
    if manifest.mention_count != config.parent.expected_input_prediction_count:
        raise HeldoutPolicyBuildError("parent mention_count mismatch")
    if manifest.mentions_sha256 != _sha(mentions_path):
        raise HeldoutPolicyBuildError("parent mentions checksum mismatch")
    if quality.get("input_document_count") != config.heldout.expected_document_count:
        raise HeldoutPolicyBuildError("parent input_document_count mismatch")
    if quality.get("mention_count") != manifest.mention_count:
        raise HeldoutPolicyBuildError("parent quality mention_count mismatch")
    if float(quality.get("threshold")) != config.parent.expected_raw_threshold:
        raise HeldoutPolicyBuildError("parent raw threshold mismatch")
    rows = tuple(ScientificEntityMentionEvidence.model_validate(x) for x in _jsonl(mentions_path))
    if len(rows) != manifest.mention_count:
        raise HeldoutPolicyBuildError("parent row count mismatch")
    if any(x.build_id != manifest.build_id for x in rows):
        raise HeldoutPolicyBuildError("parent row build_id mismatch")
    if any(x.extractor_fingerprint != manifest.extractor_fingerprint for x in rows):
        raise HeldoutPolicyBuildError("parent row extractor_fingerprint mismatch")
    return manifest, rows, quality


def _load_prepared(config: ScientificEntityGLiNERHeldoutPolicyConfig, parent_manifest: ScientificEntityEvidenceManifest):
    prepared_dir = _resolve(config.heldout.prepared_dir)
    sample = prepared_dir / config.heldout.canonical_sample_file
    prep_manifest_path = prepared_dir / config.heldout.preparation_manifest_file
    for p in (sample, prep_manifest_path):
        if not p.is_file():
            raise FileNotFoundError(p)
    prep = _json(prep_manifest_path)
    if prep.get("review_id") != config.heldout.review_id:
        raise HeldoutPolicyBuildError("prepared review_id mismatch")
    if prep.get("selected_document_count") != config.heldout.expected_document_count:
        raise HeldoutPolicyBuildError("prepared document count mismatch")
    if prep.get("prediction_blind") is not True:
        raise HeldoutPolicyBuildError("prepared sample is not prediction-blind")
    if prep.get("heldout_dev_overlap_count") != 0:
        raise HeldoutPolicyBuildError("prepared sample overlaps development evidence")
    files = prep.get("files") or {}
    if files.get(config.heldout.canonical_sample_file) != _sha(sample):
        raise HeldoutPolicyBuildError("prepared canonical sample checksum mismatch")
    sample_rows = _jsonl(sample)
    if len(sample_rows) != config.heldout.expected_document_count:
        raise HeldoutPolicyBuildError("held-out canonical sample row count mismatch")
    sample_ids = {str(row.get("canonical_id") or "") for row in sample_rows}
    if "" in sample_ids or len(sample_ids) != len(sample_rows):
        raise HeldoutPolicyBuildError("held-out canonical sample ids are missing or duplicated")
    if parent_manifest.canonical_input.document_count != config.heldout.expected_document_count:
        raise HeldoutPolicyBuildError("parent canonical_input document_count mismatch")
    if parent_manifest.canonical_input.sha256 != _sha(sample):
        raise HeldoutPolicyBuildError("raw parent was not built from frozen held-out sample")
    return prepared_dir, sample, prep_manifest_path, prep, sample_ids


def _load_policy_origin(config: ScientificEntityGLiNERHeldoutPolicyConfig):
    calibration_dir = _resolve(config.policy_origin.calibration_root) / config.policy_origin.calibration_id
    manifest_path = calibration_dir / "manifest.json"
    trials_path = calibration_dir / "trials.jsonl"
    profiles_path = calibration_dir / "recommended_profiles.json"
    for p in (manifest_path, trials_path, profiles_path):
        if not p.is_file():
            raise FileNotFoundError(p)
    manifest = ScientificEntityGLiNERCalibrationManifest.model_validate(_json(manifest_path))
    if manifest.calibration_id != config.policy_origin.calibration_id:
        raise HeldoutPolicyBuildError("calibration_id mismatch")
    trials = [ScientificEntityCalibrationTrial.model_validate(x) for x in _jsonl(trials_path)]
    selected = [x for x in trials if x.trial_id == config.policy_origin.selected_trial_id]
    if len(selected) != 1:
        raise HeldoutPolicyBuildError("selected frozen trial missing or duplicated")
    trial = selected[0]
    if trial.calibration_id != config.policy_origin.calibration_id:
        raise HeldoutPolicyBuildError("selected trial calibration mismatch")
    if trial.stage != ScientificEntityCalibrationTrialStage.SOURCE_PAIR:
        raise HeldoutPolicyBuildError("selected trial stage mismatch")
    if trial.policy != config.policy_origin.policy:
        raise HeldoutPolicyBuildError("selected trial policy mismatch")
    profiles = ScientificEntityCalibrationProfiles.model_validate(_json(profiles_path))
    balanced = [x for x in profiles.selections if x.profile_name == ScientificEntityCalibrationProfileName.BALANCED]
    if len(balanced) != 1 or balanced[0].trial_id != trial.trial_id or balanced[0].policy != trial.policy:
        raise HeldoutPolicyBuildError("balanced calibration profile mismatch")
    return calibration_dir, manifest, trial


def _quality(build_id: str, status: EntityEvidenceBuildStatus, parent_count: int, rows: Sequence[ScientificEntityMentionEvidence]) -> dict[str, Any]:
    by_field = Counter(x.source_field.value for x in rows)
    by_type = Counter(x.entity_type.value for x in rows)
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "build_id": build_id,
        "status": status.value,
        "heldout_document_count": 48,
        "input_prediction_count": parent_count,
        "selected_prediction_count": len(rows),
        "rejected_prediction_count": parent_count - len(rows),
        "selected_prediction_count_by_source_field": {x.value: by_field[x.value] for x in ScientificEntitySourceField},
        "selected_prediction_count_by_entity_type": {x.value: by_type[x.value] for x in ScientificEntityType},
        "confidence_kind": "model_score",
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "heldout_references_mutated": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "publication_ready": False,
    }


def _schema() -> dict[str, Any]:
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "mentions_schema_version": MENTION_SCHEMA_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "derivation_manifest_schema_version": DERIVATION_MANIFEST_SCHEMA_VERSION,
        "evidence_lineage_schema_version": EVIDENCE_LINEAGE_SCHEMA_VERSION,
        "data_quality_schema_version": QUALITY_SCHEMA_VERSION,
        "serialization": {"encoding": "utf-8", "line_ending": "lf", "offset_unit": "unicode_codepoint", "offset_interval": "half_open"},
        "mentions_json_schema": ScientificEntityMentionEvidence.model_json_schema(),
        "manifest_json_schema": ScientificEntityEvidenceManifest.model_json_schema(),
        "derivation_manifest_json_schema": ScientificEntityGLiNERHeldoutPolicyDerivationManifest.model_json_schema(),
        "evidence_lineage_json_schema": ScientificEntityFrozenPolicyEvidenceLineage.model_json_schema(),
    }


def _readme(build_id: str, parent_id: str, selected: int) -> str:
    return "\n".join([
        "# Held-Out Frozen-Policy GLiNER Evidence v0.1", "",
        "Immutable policy-filtered evidence for the 48-paper prediction-blind held-out sample.",
        "The thresholds were selected only on prior development evidence and are not tuned here.", "",
        f"- build_id: `{build_id}`", f"- parent_build_id: `{parent_id}`", f"- selected_prediction_count: `{selected}`", "",
        "No model inference, threshold tuning, held-out reference mutation, canonical mutation, or production promotion occurs in this materialization.", ""
    ])


def _write_output(output_dir: Path, mentions_bytes: bytes, lineage_bytes: bytes, manifest, derivation, quality, readme):
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        raise FileExistsError(f"Immutable build directory already exists: {output_dir}")
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_dir.parent))
    try:
        (staging / "mentions.jsonl").write_bytes(mentions_bytes)
        (staging / "evidence_lineage.jsonl").write_bytes(lineage_bytes)
        _write_lf(staging / "manifest.json", _json_text(manifest.model_dump(mode="json")))
        _write_lf(staging / "derivation_manifest.json", _json_text(derivation.model_dump(mode="json")))
        _write_lf(staging / "schema.json", _json_text(_schema()))
        _write_lf(staging / "data_quality_summary.json", _json_text(quality))
        _write_lf(staging / "README.md", readme)
        checksums = [f"{_sha(staging / name)}  {name}" for name in CHECKSUM_FILES]
        _write_lf(staging / "checksums.txt", "\n".join(checksums) + "\n")
        staging.replace(output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def build(*, config_path: Path = DEFAULT_CONFIG_PATH, build_id: str | None = None, status: str = "candidate", execute: bool = False, generated_at_utc: datetime | None = None) -> dict[str, Any]:
    config = load_config(config_path.resolve())
    selected_status = EntityEvidenceBuildStatus(status)
    if selected_status.value not in config.safety.allowed_build_statuses or selected_status == EntityEvidenceBuildStatus.ACCEPTED:
        raise HeldoutPolicyBuildError("disallowed build status")
    now = generated_at_utc or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc)
    selected_build_id = build_id or _default_build_id(now)
    output_dir = _resolve(config.outputs.root) / selected_build_id
    if execute and output_dir.exists():
        raise FileExistsError(output_dir)

    parent_dir = _resolve(config.parent.build_root) / config.parent.build_id
    parent_manifest, parent_mentions, _parent_quality = _load_parent(parent_dir, config)
    prepared_dir, sample_path, prep_manifest_path, _prep, sample_ids = _load_prepared(config, parent_manifest)
    calibration_dir, calibration_manifest, trial = _load_policy_origin(config)
    if not {row.canonical_id for row in parent_mentions}.issubset(sample_ids):
        raise HeldoutPolicyBuildError("raw parent mentions contain canonical ids outside held-out sample")

    descriptor = build_descriptor(config=config, parent_manifest=parent_manifest, project_root=PROJECT_ROOT)
    fingerprint = build_extractor_fingerprint(descriptor)
    if fingerprint == parent_manifest.extractor_fingerprint:
        raise HeldoutPolicyBuildError("policy-aware extractor fingerprint must differ from raw parent")
    candidate_rows, lineage_rows = materialize(parent_mentions=parent_mentions, config=config, build_id=selected_build_id, candidate_extractor_fingerprint=fingerprint)

    mentions_bytes = _jsonl_bytes(candidate_rows)
    lineage_bytes = _jsonl_bytes(lineage_rows)
    manifest = ScientificEntityEvidenceManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        build_id=selected_build_id,
        status=selected_status,
        generated_at_utc=now,
        canonical_input=parent_manifest.canonical_input,
        extractor=descriptor,
        extractor_fingerprint=fingerprint,
        offset_unit=parent_manifest.offset_unit,
        offset_interval=parent_manifest.offset_interval,
        source_fields=parent_manifest.source_fields,
        entity_types=parent_manifest.entity_types,
        mentions_file="mentions.jsonl",
        mention_count=len(candidate_rows),
        mentions_sha256=hashlib.sha256(mentions_bytes).hexdigest(),
        canonical_truth_mutated=False,
        may_be_used_as_reconcile_input=False,
        publication_ready=False,
    )
    derivation = ScientificEntityGLiNERHeldoutPolicyDerivationManifest(
        schema_version=DERIVATION_MANIFEST_SCHEMA_VERSION,
        build_id=selected_build_id,
        generated_at_utc=now,
        heldout_review_id=config.heldout.review_id,
        heldout_document_count=config.heldout.expected_document_count,
        heldout_sample_path=_rel(sample_path),
        heldout_sample_sha256=_sha(sample_path),
        preparation_manifest_path=_rel(prep_manifest_path),
        preparation_manifest_sha256=_sha(prep_manifest_path),
        prediction_blind_reference_preparation=True,
        heldout_dev_overlap_count=0,
        parent_build_id=parent_manifest.build_id,
        parent_manifest_path=_rel(parent_dir / "manifest.json"),
        parent_manifest_sha256=_sha(parent_dir / "manifest.json"),
        parent_mentions_path=_rel(parent_dir / "mentions.jsonl"),
        parent_mentions_sha256=_sha(parent_dir / "mentions.jsonl"),
        parent_extractor_fingerprint=parent_manifest.extractor_fingerprint,
        calibration_id=calibration_manifest.calibration_id,
        selected_profile=ScientificEntityCalibrationProfileName.BALANCED,
        selected_trial_id=trial.trial_id,
        selected_trial_stage=trial.stage,
        policy_origin_is_dev_only=True,
        heldout_used_for_policy_selection=False,
        input_threshold=config.policy_origin.input_threshold,
        threshold_is_inclusive=True,
        policy=config.policy_origin.policy,
        input_prediction_count=len(parent_mentions),
        selected_prediction_count=len(candidate_rows),
        rejected_prediction_count=len(parent_mentions) - len(candidate_rows),
        candidate_extractor_fingerprint=fingerprint,
        lineage_file="evidence_lineage.jsonl",
        lineage_sha256=hashlib.sha256(lineage_bytes).hexdigest(),
        lineage_count=len(lineage_rows),
        mention_id_preserved=True,
        evidence_id_recomputed=True,
        confidence_kind_preserved=True,
        confidence_score_preserved=True,
        model_inference_executed=False,
        model_downloaded=False,
        threshold_tuning_executed=False,
        canonical_truth_mutated=False,
        heldout_references_mutated=False,
        production_extractor_selected=False,
        full_corpus_build_authorized=False,
        publication_ready=False,
    )
    quality = _quality(selected_build_id, selected_status, len(parent_mentions), candidate_rows)
    if execute:
        _write_output(output_dir, mentions_bytes, lineage_bytes, manifest, derivation, quality, _readme(selected_build_id, parent_manifest.build_id, len(candidate_rows)))

    return {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": execute,
        "build_id": selected_build_id,
        "status": selected_status.value,
        "heldout_review_id": config.heldout.review_id,
        "heldout_document_count": config.heldout.expected_document_count,
        "parent_build_id": parent_manifest.build_id,
        "calibration_id": calibration_manifest.calibration_id,
        "selected_trial_id": trial.trial_id,
        "input_prediction_count": len(parent_mentions),
        "selected_prediction_count": len(candidate_rows),
        "rejected_prediction_count": len(parent_mentions) - len(candidate_rows),
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "heldout_references_mutated": False,
        "output_dir": _norm(output_dir),
        "next_slice": "validate_then_run_one_heldout_evaluation_v0.1" if execute else "execute_heldout_frozen_policy_materialization_v0.1",
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--config", dest="config_path", type=Path, default=DEFAULT_CONFIG_PATH)
    p.add_argument("--build-id")
    p.add_argument("--status", default="candidate", choices=("fixture", "candidate"))
    p.add_argument("--execute", action="store_true")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    report = build(**vars(parser().parse_args(argv)))
    for key in ("report", "mode", "phase_complete", "build_id", "status", "heldout_review_id", "heldout_document_count", "parent_build_id", "calibration_id", "selected_trial_id", "input_prediction_count", "selected_prediction_count", "rejected_prediction_count", "model_inference_executed", "threshold_tuning_executed", "heldout_references_mutated", "output_dir", "next_slice"):
        print(f"[OK] {key}={report[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
