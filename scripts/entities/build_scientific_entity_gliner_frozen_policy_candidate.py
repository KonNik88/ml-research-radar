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

from pydantic import ValidationError

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
    ScientificEntityGLiNERCalibrationManifest,
)
from radar_core.contracts.scientific_entity_gliner_frozen_policy import (
    DERIVATION_MANIFEST_SCHEMA_VERSION,
    EVIDENCE_LINEAGE_SCHEMA_VERSION,
    ScientificEntityGLiNERFrozenPolicyDerivationManifest,
)
from radar_core.entities.scientific_entity_gliner_frozen_policy import (
    ScientificEntityGLiNERFrozenPolicyConfig,
    ScientificEntityGLiNERFrozenPolicyError,
    build_frozen_policy_extractor_descriptor,
    gliner_frozen_policy_config_sha256,
    load_gliner_frozen_policy_config,
    materialize_frozen_policy_mentions,
    validate_frozen_trial,
)


REPORT_NAME = "scientific_entity_gliner_frozen_policy_candidate_v01"
OUTPUT_SCHEMA_VERSION = "scientific_entity_gliner_frozen_policy_output_schema_v0.1"
QUALITY_SCHEMA_VERSION = "scientific_entity_gliner_frozen_policy_quality_v0.1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = (
    PROJECT_ROOT / "configs" / "scientific_entity_gliner_frozen_policy_candidate_v0.1.yaml"
)
CHECKSUM_FILES = (
    "mentions.jsonl",
    "manifest.json",
    "schema.json",
    "data_quality_summary.json",
    "README.md",
    "derivation_manifest.json",
    "evidence_lineage.jsonl",
)
REQUIRED_FILES = (*CHECKSUM_FILES, "checksums.txt")


class ScientificEntityGLiNERFrozenPolicyBuildError(RuntimeError):
    """Raised when a frozen-policy candidate cannot be materialized safely."""


def _normalize_path(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def _resolve_project_path(path: Path | str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _project_relative_or_absolute(path: Path) -> str:
    try:
        return _normalize_path(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return _normalize_path(path.resolve())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _jsonl_bytes(rows: Sequence[Any]) -> bytes:
    chunks = [
        json.dumps(row.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
        for row in rows
    ]
    return (("\n".join(chunks) + "\n") if chunks else "").encode("utf-8")


def _write_text_lf(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ScientificEntityGLiNERFrozenPolicyBuildError(
            f"Expected JSON object: {path}"
        )
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise ScientificEntityGLiNERFrozenPolicyBuildError(
                f"Blank JSONL line: {path}:{line_number}"
            )
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ScientificEntityGLiNERFrozenPolicyBuildError(
                f"Expected JSON object: {path}:{line_number}"
            )
        rows.append(payload)
    return rows


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_build_id(generated_at_utc: datetime) -> str:
    timestamp = generated_at_utc.strftime("%Y%m%dT%H%M%S%fZ")
    return f"scientific-entity-gliner-small-v2.5-frozen-policy-v0.1-{timestamp}"


def _load_parent_build(
    *,
    parent_dir: Path,
    config: ScientificEntityGLiNERFrozenPolicyConfig,
) -> tuple[ScientificEntityEvidenceManifest, tuple[ScientificEntityMentionEvidence, ...]]:
    if not parent_dir.is_dir():
        raise FileNotFoundError(parent_dir)
    manifest_path = parent_dir / "manifest.json"
    mentions_path = parent_dir / "mentions.jsonl"
    quality_path = parent_dir / "data_quality_summary.json"
    for path in (manifest_path, mentions_path, quality_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    manifest = ScientificEntityEvidenceManifest.model_validate(_read_json(manifest_path))
    if manifest.build_id != config.frozen.parent_build_id:
        raise ScientificEntityGLiNERFrozenPolicyBuildError("parent build_id mismatch")
    if manifest.mentions_sha256 != _sha256_file(mentions_path):
        raise ScientificEntityGLiNERFrozenPolicyBuildError("parent mentions checksum mismatch")
    if manifest.mention_count != config.frozen.expected_input_prediction_count:
        raise ScientificEntityGLiNERFrozenPolicyBuildError("parent mention_count mismatch")
    rows = tuple(
        ScientificEntityMentionEvidence.model_validate(row)
        for row in _read_jsonl(mentions_path)
    )
    if len(rows) != manifest.mention_count:
        raise ScientificEntityGLiNERFrozenPolicyBuildError("parent rows/count mismatch")
    if any(row.build_id != manifest.build_id for row in rows):
        raise ScientificEntityGLiNERFrozenPolicyBuildError("parent row build_id mismatch")
    if any(row.extractor_fingerprint != manifest.extractor_fingerprint for row in rows):
        raise ScientificEntityGLiNERFrozenPolicyBuildError(
            "parent row extractor_fingerprint mismatch"
        )
    if len({row.mention_id for row in rows}) != len(rows):
        raise ScientificEntityGLiNERFrozenPolicyBuildError("parent mention_ids are not unique")
    if len({row.evidence_id for row in rows}) != len(rows):
        raise ScientificEntityGLiNERFrozenPolicyBuildError("parent evidence_ids are not unique")
    return manifest, rows


def _load_calibration(
    *,
    calibration_dir: Path,
    config: ScientificEntityGLiNERFrozenPolicyConfig,
) -> tuple[
    ScientificEntityGLiNERCalibrationManifest,
    ScientificEntityCalibrationTrial,
    ScientificEntityCalibrationProfiles,
]:
    if not calibration_dir.is_dir():
        raise FileNotFoundError(calibration_dir)
    manifest_path = calibration_dir / "manifest.json"
    trials_path = calibration_dir / "trials.jsonl"
    profiles_path = calibration_dir / "recommended_profiles.json"
    for path in (manifest_path, trials_path, profiles_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    manifest = ScientificEntityGLiNERCalibrationManifest.model_validate(
        _read_json(manifest_path)
    )
    if manifest.calibration_id != config.frozen.calibration_id:
        raise ScientificEntityGLiNERFrozenPolicyBuildError("calibration_id mismatch")
    if manifest.inputs.prediction_build_id != config.frozen.parent_build_id:
        raise ScientificEntityGLiNERFrozenPolicyBuildError(
            "calibration parent prediction_build_id mismatch"
        )
    if manifest.inputs.prediction_mention_count != config.frozen.expected_input_prediction_count:
        raise ScientificEntityGLiNERFrozenPolicyBuildError(
            "calibration input prediction count mismatch"
        )
    if manifest.inputs.input_threshold != config.frozen.input_threshold:
        raise ScientificEntityGLiNERFrozenPolicyBuildError(
            "calibration input threshold mismatch"
        )
    if manifest.trials_sha256 != _sha256_file(trials_path):
        raise ScientificEntityGLiNERFrozenPolicyBuildError("calibration trials checksum mismatch")
    if manifest.profiles_sha256 != _sha256_file(profiles_path):
        raise ScientificEntityGLiNERFrozenPolicyBuildError("calibration profiles checksum mismatch")

    trials = [
        ScientificEntityCalibrationTrial.model_validate(row)
        for row in _read_jsonl(trials_path)
    ]
    selected = [row for row in trials if row.trial_id == config.frozen.selected_trial_id]
    if len(selected) != 1:
        raise ScientificEntityGLiNERFrozenPolicyBuildError(
            "frozen selected trial must exist exactly once"
        )
    trial = selected[0]
    validate_frozen_trial(config=config, trial=trial)

    profiles = ScientificEntityCalibrationProfiles.model_validate(_read_json(profiles_path))
    balanced = [
        row
        for row in profiles.selections
        if row.profile_name == ScientificEntityCalibrationProfileName.BALANCED
    ]
    if len(balanced) != 1 or balanced[0].trial_id != config.frozen.selected_trial_id:
        raise ScientificEntityGLiNERFrozenPolicyBuildError(
            "balanced profile does not reference the frozen selected trial"
        )
    if balanced[0].policy != config.frozen.policy:
        raise ScientificEntityGLiNERFrozenPolicyBuildError(
            "balanced profile policy does not match frozen policy"
        )
    return manifest, trial, profiles


def _quality_summary(
    *,
    build_id: str,
    status: EntityEvidenceBuildStatus,
    parent_count: int,
    rows: Sequence[ScientificEntityMentionEvidence],
) -> dict[str, Any]:
    source_counts = Counter(row.source_field.value for row in rows)
    type_counts = Counter(row.entity_type.value for row in rows)
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "build_id": build_id,
        "status": status.value,
        "input_prediction_count": parent_count,
        "selected_prediction_count": len(rows),
        "rejected_prediction_count": parent_count - len(rows),
        "selected_prediction_count_by_source_field": {
            field.value: source_counts[field.value] for field in ScientificEntitySourceField
        },
        "selected_prediction_count_by_entity_type": {
            entity_type.value: type_counts[entity_type.value]
            for entity_type in ScientificEntityType
        },
        "confidence_kind": "model_score",
        "scores_reinterpreted_as_probabilities": False,
        "model_inference_executed": False,
        "model_downloaded": False,
        "provider_api_called": False,
        "canonical_truth_mutated": False,
        "may_be_used_as_reconcile_input": False,
        "current_dev_set_becomes_held_out": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "publication_ready": False,
    }


def _schema_payload() -> dict[str, Any]:
    from radar_core.contracts.scientific_entity_gliner_frozen_policy import (
        ScientificEntityFrozenPolicyEvidenceLineage,
    )

    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "mentions_schema_version": MENTION_SCHEMA_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "derivation_manifest_schema_version": DERIVATION_MANIFEST_SCHEMA_VERSION,
        "evidence_lineage_schema_version": EVIDENCE_LINEAGE_SCHEMA_VERSION,
        "data_quality_schema_version": QUALITY_SCHEMA_VERSION,
        "serialization": {
            "encoding": "utf-8",
            "line_ending": "lf",
            "offset_unit": "unicode_codepoint",
            "offset_interval": "half_open",
        },
        "mentions_json_schema": ScientificEntityMentionEvidence.model_json_schema(),
        "manifest_json_schema": ScientificEntityEvidenceManifest.model_json_schema(),
        "derivation_manifest_json_schema": (
            ScientificEntityGLiNERFrozenPolicyDerivationManifest.model_json_schema()
        ),
        "evidence_lineage_json_schema": (
            ScientificEntityFrozenPolicyEvidenceLineage.model_json_schema()
        ),
    }


def _readme(
    *,
    build_id: str,
    parent_build_id: str,
    calibration_id: str,
    selected_trial_id: str,
    input_count: int,
    selected_count: int,
) -> str:
    return "\n".join(
        [
            "# Frozen-Policy GLiNER Scientific Entity Candidate v0.1",
            "",
            "This immutable directory contains derived and rebuildable scientific entity",
            "evidence materialized from an existing immutable GLiNER prediction build.",
            "It is not canonical paper truth, not a reconcile input, not a production-selected",
            "extractor, not a full-corpus build, and not publication ready.",
            "",
            "No GLiNER inference, model/tokenizer download, provider API call, or canonical",
            "mutation occurs during this materialization.",
            "",
            "## Identity and lineage",
            "",
            f"- build_id: `{build_id}`",
            f"- parent_build_id: `{parent_build_id}`",
            f"- calibration_id: `{calibration_id}`",
            f"- selected_trial_id: `{selected_trial_id}`",
            f"- input_prediction_count: `{input_count}`",
            f"- selected_prediction_count: `{selected_count}`",
            f"- rejected_prediction_count: `{input_count - selected_count}`",
            "",
            "The frozen v0.1 policy is inclusive: title score >= 0.55 and abstract",
            "score >= 0.65, with no entity-type overrides. mention_id is preserved;",
            "a policy-aware extractor fingerprint causes evidence_id to be recomputed.",
            "Per-row parent evidence lineage is stored in evidence_lineage.jsonl.",
            "",
        ]
    )


def _write_output(
    *,
    output_dir: Path,
    mentions_bytes: bytes,
    manifest: ScientificEntityEvidenceManifest,
    schema: Mapping[str, Any],
    quality: Mapping[str, Any],
    readme: str,
    derivation_manifest: ScientificEntityGLiNERFrozenPolicyDerivationManifest,
    lineage_bytes: bytes,
) -> list[str]:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        raise FileExistsError(
            f"Immutable build directory already exists; overwrite is forbidden: {output_dir}"
        )
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_dir.parent))
    try:
        (staging / "mentions.jsonl").write_bytes(mentions_bytes)
        _write_text_lf(staging / "manifest.json", _json_text(manifest.model_dump(mode="json")))
        _write_text_lf(staging / "schema.json", _json_text(dict(schema)))
        _write_text_lf(staging / "data_quality_summary.json", _json_text(dict(quality)))
        _write_text_lf(staging / "README.md", readme)
        _write_text_lf(
            staging / "derivation_manifest.json",
            _json_text(derivation_manifest.model_dump(mode="json")),
        )
        (staging / "evidence_lineage.jsonl").write_bytes(lineage_bytes)
        checksums = [f"{_sha256_file(staging / name)}  {name}" for name in CHECKSUM_FILES]
        _write_text_lf(staging / "checksums.txt", "\n".join(checksums) + "\n")
        staging.rename(output_dir)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return list(REQUIRED_FILES)


def build_frozen_policy_candidate(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    parent_build_dir: Path | None = None,
    calibration_dir: Path | None = None,
    output_root: Path | None = None,
    build_id: str | None = None,
    status: EntityEvidenceBuildStatus | str = EntityEvidenceBuildStatus.CANDIDATE,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = load_gliner_frozen_policy_config(config_path)
    selected_status = EntityEvidenceBuildStatus(status)
    if selected_status.value not in config.safety.allowed_build_statuses:
        raise ScientificEntityGLiNERFrozenPolicyBuildError(
            f"Disallowed build status: {selected_status.value}"
        )
    if selected_status == EntityEvidenceBuildStatus.ACCEPTED:
        raise ScientificEntityGLiNERFrozenPolicyBuildError("accepted status is forbidden")

    parent_root = _resolve_project_path(config.inputs.parent_build_root)
    calibration_root = _resolve_project_path(config.inputs.calibration_root)
    selected_parent_dir = (
        parent_build_dir.resolve()
        if parent_build_dir is not None
        else parent_root / config.frozen.parent_build_id
    )
    selected_calibration_dir = (
        calibration_dir.resolve()
        if calibration_dir is not None
        else calibration_root / config.frozen.calibration_id
    )
    selected_output_root = _resolve_project_path(output_root or config.outputs.root)
    generated_at = generated_at_utc or _utc_now()
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ScientificEntityGLiNERFrozenPolicyBuildError("generated_at_utc must be timezone-aware")
    generated_at = generated_at.astimezone(timezone.utc)
    selected_build_id = build_id or _default_build_id(generated_at)
    output_dir = selected_output_root / selected_build_id
    if execute and output_dir.exists():
        raise FileExistsError(
            f"Immutable build directory already exists; overwrite is forbidden: {output_dir}"
        )

    parent_manifest, parent_mentions = _load_parent_build(
        parent_dir=selected_parent_dir,
        config=config,
    )
    calibration_manifest, selected_trial, _profiles = _load_calibration(
        calibration_dir=selected_calibration_dir,
        config=config,
    )
    if calibration_manifest.inputs.prediction_extractor_fingerprint != parent_manifest.extractor_fingerprint:
        raise ScientificEntityGLiNERFrozenPolicyBuildError(
            "calibration parent extractor fingerprint mismatch"
        )

    descriptor = build_frozen_policy_extractor_descriptor(
        config=config,
        parent_manifest=parent_manifest,
        project_root=PROJECT_ROOT,
    )
    candidate_fingerprint = build_extractor_fingerprint(descriptor)
    if candidate_fingerprint == parent_manifest.extractor_fingerprint:
        raise ScientificEntityGLiNERFrozenPolicyBuildError(
            "policy-aware extractor fingerprint must differ from parent"
        )

    candidate_rows, lineage_rows = materialize_frozen_policy_mentions(
        parent_mentions=parent_mentions,
        config=config,
        build_id=selected_build_id,
        candidate_extractor_fingerprint=candidate_fingerprint,
    )
    mentions_bytes = _jsonl_bytes(candidate_rows)
    lineage_bytes = _jsonl_bytes(lineage_rows)
    manifest = ScientificEntityEvidenceManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        build_id=selected_build_id,
        status=selected_status,
        generated_at_utc=generated_at,
        canonical_input=parent_manifest.canonical_input,
        extractor=descriptor,
        extractor_fingerprint=candidate_fingerprint,
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
    derivation_manifest = ScientificEntityGLiNERFrozenPolicyDerivationManifest(
        schema_version=DERIVATION_MANIFEST_SCHEMA_VERSION,
        build_id=selected_build_id,
        generated_at_utc=generated_at,
        parent_build_id=parent_manifest.build_id,
        parent_manifest_path=_project_relative_or_absolute(selected_parent_dir / "manifest.json"),
        parent_manifest_sha256=_sha256_file(selected_parent_dir / "manifest.json"),
        parent_mentions_path=_project_relative_or_absolute(selected_parent_dir / "mentions.jsonl"),
        parent_mentions_sha256=_sha256_file(selected_parent_dir / "mentions.jsonl"),
        parent_extractor_fingerprint=parent_manifest.extractor_fingerprint,
        calibration_id=calibration_manifest.calibration_id,
        calibration_manifest_path=_project_relative_or_absolute(selected_calibration_dir / "manifest.json"),
        calibration_manifest_sha256=_sha256_file(selected_calibration_dir / "manifest.json"),
        calibration_trials_path=_project_relative_or_absolute(selected_calibration_dir / "trials.jsonl"),
        calibration_trials_sha256=_sha256_file(selected_calibration_dir / "trials.jsonl"),
        calibration_profiles_path=_project_relative_or_absolute(selected_calibration_dir / "recommended_profiles.json"),
        calibration_profiles_sha256=_sha256_file(selected_calibration_dir / "recommended_profiles.json"),
        selected_profile=ScientificEntityCalibrationProfileName.BALANCED,
        selected_trial_id=selected_trial.trial_id,
        selected_trial_stage=selected_trial.stage,
        input_threshold=config.frozen.input_threshold,
        threshold_is_inclusive=True,
        policy=config.frozen.policy,
        input_prediction_count=len(parent_mentions),
        selected_prediction_count=len(candidate_rows),
        rejected_prediction_count=len(parent_mentions) - len(candidate_rows),
        candidate_extractor_fingerprint=candidate_fingerprint,
        lineage_file="evidence_lineage.jsonl",
        lineage_sha256=hashlib.sha256(lineage_bytes).hexdigest(),
        lineage_count=len(lineage_rows),
        mention_id_preserved=True,
        evidence_id_recomputed=True,
        confidence_kind_preserved=True,
        confidence_score_preserved=True,
        calibration_id_written_to_mentions=False,
        model_inference_executed=False,
        model_downloaded=False,
        provider_api_called=False,
        canonical_truth_mutated=False,
        may_be_used_as_reconcile_input=False,
        current_dev_set_becomes_held_out=False,
        production_extractor_selected=False,
        full_corpus_build_authorized=False,
        publication_ready=False,
    )
    quality = _quality_summary(
        build_id=selected_build_id,
        status=selected_status,
        parent_count=len(parent_mentions),
        rows=candidate_rows,
    )
    readme = _readme(
        build_id=selected_build_id,
        parent_build_id=parent_manifest.build_id,
        calibration_id=calibration_manifest.calibration_id,
        selected_trial_id=selected_trial.trial_id,
        input_count=len(parent_mentions),
        selected_count=len(candidate_rows),
    )
    written_files: list[str] = []
    if execute:
        written_files = _write_output(
            output_dir=output_dir,
            mentions_bytes=mentions_bytes,
            manifest=manifest,
            schema=_schema_payload(),
            quality=quality,
            readme=readme,
            derivation_manifest=derivation_manifest,
            lineage_bytes=lineage_bytes,
        )

    return {
        "schema_version": "scientific_entity_gliner_frozen_policy_candidate_report_v0.1",
        "report": REPORT_NAME,
        "ok": True,
        "mode": "execute" if execute else "plan",
        "phase_complete": execute,
        "build_id": selected_build_id,
        "status": selected_status.value,
        "config_path": _normalize_path(config_path),
        "config_sha256": gliner_frozen_policy_config_sha256(config),
        "parent_build_dir": _normalize_path(selected_parent_dir),
        "parent_build_id": parent_manifest.build_id,
        "parent_extractor_fingerprint": parent_manifest.extractor_fingerprint,
        "calibration_dir": _normalize_path(selected_calibration_dir),
        "calibration_id": calibration_manifest.calibration_id,
        "selected_profile": config.frozen.selected_profile.value,
        "selected_trial_id": selected_trial.trial_id,
        "policy": config.frozen.policy.model_dump(mode="json"),
        "input_prediction_count": len(parent_mentions),
        "selected_prediction_count": len(candidate_rows),
        "rejected_prediction_count": len(parent_mentions) - len(candidate_rows),
        "candidate_extractor_fingerprint": candidate_fingerprint,
        "output_dir": _normalize_path(output_dir),
        "written_files": written_files,
        "model_inference_executed": False,
        "model_downloaded": False,
        "provider_api_called": False,
        "canonical_truth_mutated": False,
        "current_dev_set_becomes_held_out": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "publication_ready": False,
        "next_slice": (
            "validate_and_reproduce_frozen_policy_candidate_dev_evaluation_v0.1"
            if execute
            else "execute_frozen_policy_candidate_materialization_v0.1"
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute the read-only frozen GLiNER dev-policy candidate "
            "materialization. No threshold overrides, model inference, downloads, "
            "provider APIs, or canonical writes are supported."
        )
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--parent-build-dir", type=Path, default=None)
    parser.add_argument("--calibration-dir", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--build-id", default=None)
    parser.add_argument("--status", choices=("fixture", "candidate"), default="candidate")
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_frozen_policy_candidate(
            config_path=args.config,
            parent_build_dir=args.parent_build_dir,
            calibration_dir=args.calibration_dir,
            output_root=args.output_root,
            build_id=args.build_id,
            status=args.status,
            execute=args.execute,
        )
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        ValidationError,
        ScientificEntityGLiNERFrozenPolicyError,
        ScientificEntityGLiNERFrozenPolicyBuildError,
    ) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1

    prefix = "OK"
    print(f"[{prefix}] report={REPORT_NAME}")
    print(f"[{prefix}] mode={report['mode']}")
    print(f"[{prefix}] phase_complete={report['phase_complete']}")
    print(f"[{prefix}] build_id={report['build_id']}")
    print(f"[{prefix}] status={report['status']}")
    print(f"[{prefix}] parent_build_id={report['parent_build_id']}")
    print(f"[{prefix}] calibration_id={report['calibration_id']}")
    print(f"[{prefix}] selected_trial_id={report['selected_trial_id']}")
    print(f"[{prefix}] input_prediction_count={report['input_prediction_count']}")
    print(f"[{prefix}] selected_prediction_count={report['selected_prediction_count']}")
    print(f"[{prefix}] rejected_prediction_count={report['rejected_prediction_count']}")
    print(f"[{prefix}] model_inference_executed={report['model_inference_executed']}")
    print(f"[{prefix}] output_dir={report['output_dir']}")
    print(f"[{prefix}] next_slice={report['next_slice']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
