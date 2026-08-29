from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

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
from radar_core.contracts.scientific_entity_semantic_prompt_policy import (
    POLICY_CONFIG_SCHEMA_VERSION,
    POLICY_DERIVATION_SCHEMA_VERSION,
    POLICY_LINEAGE_SCHEMA_VERSION,
    SemanticPromptPolicyConfig,
    SemanticPromptPolicyDerivationManifest,
    SemanticPromptPolicyLineage,
)
from radar_core.contracts.scientific_entity_semantic_prompt_candidate import (
    load_semantic_prompt_candidate_config,
    validate_candidate_contract,
)
from radar_core.entities.scientific_entity_gliner import (
    gliner_config_sha256,
    load_gliner_config,
    normalized_source_bundle_revision,
)
from radar_core.entities.scientific_entity_gliner_calibration import filter_predictions


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "scientific_entity_semantic_prompt_policy_v0.2a.yaml"
REPORT_NAME = "scientific_entity_semantic_prompt_policy_v02a"
OUTPUT_SCHEMA_VERSION = "scientific_entity_semantic_prompt_policy_output_v0.2a"
QUALITY_SCHEMA_VERSION = "scientific_entity_semantic_prompt_policy_quality_v0.2a"
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


class SemanticPromptPolicyError(RuntimeError):
    """Raised when v0.2a policy materialization cannot be reproduced safely."""


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(rows: Sequence[Any]) -> bytes:
    chunks = []
    for row in rows:
        payload = row.model_dump(mode="json") if hasattr(row, "model_dump") else row
        chunks.append(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return (("\n".join(chunks) + "\n") if chunks else "").encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SemanticPromptPolicyError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise SemanticPromptPolicyError(f"Blank JSONL line: {path}:{line_number}")
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise SemanticPromptPolicyError(f"Expected JSON object: {path}:{line_number}")
            rows.append(payload)
    return rows


def _resolve(path: Path | str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _project_relative_or_absolute(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(resolved).replace("\\", "/")


def load_policy_config(path: Path = DEFAULT_CONFIG_PATH) -> SemanticPromptPolicyConfig:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SemanticPromptPolicyError("policy config must be a YAML mapping")
    return SemanticPromptPolicyConfig.model_validate(payload)


def policy_config_sha256(config: SemanticPromptPolicyConfig) -> str:
    return sha256_text(_canonical_json(config.model_dump(mode="json")))


def _design_file_sha256(path: Path) -> str:
    return _sha256_file(path)


def _threshold_policy(config: SemanticPromptPolicyConfig) -> ScientificEntityThresholdPolicy:
    return ScientificEntityThresholdPolicy(
        default_threshold=config.policy.default_threshold,
        source_field_thresholds=config.policy.source_field_thresholds,
        entity_type_thresholds={},
    )


def _default_build_id(now: datetime) -> str:
    return f"scientific-entity-semantic-prompt-policy-v0.2a-{now.strftime('%Y%m%dT%H%M%S%fZ')}"


def _load_parent(parent_build_dir: Path) -> tuple[ScientificEntityEvidenceManifest, tuple[ScientificEntityMentionEvidence, ...]]:
    manifest_path = parent_build_dir / "manifest.json"
    mentions_path = parent_build_dir / "mentions.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    if not mentions_path.is_file():
        raise FileNotFoundError(mentions_path)
    manifest = ScientificEntityEvidenceManifest.model_validate(_read_json(manifest_path))
    if manifest.status != EntityEvidenceBuildStatus.CANDIDATE:
        raise SemanticPromptPolicyError("v0.2a policy requires candidate raw parent build")
    if manifest.mentions_sha256 != _sha256_file(mentions_path):
        raise SemanticPromptPolicyError("raw parent mentions checksum mismatch")
    rows = tuple(ScientificEntityMentionEvidence.model_validate(x) for x in _read_jsonl(mentions_path))
    if len(rows) != manifest.mention_count:
        raise SemanticPromptPolicyError("raw parent mention count mismatch")
    if any(row.build_id != manifest.build_id for row in rows):
        raise SemanticPromptPolicyError("raw parent mention build_id mismatch")
    if any(row.extractor_fingerprint != manifest.extractor_fingerprint for row in rows):
        raise SemanticPromptPolicyError("raw parent extractor fingerprint mismatch")
    return manifest, rows


def _validate_development_package(
    *, development_package_dir: Path, parent_manifest: ScientificEntityEvidenceManifest, config: SemanticPromptPolicyConfig
) -> dict[str, Any]:
    manifest_path = development_package_dir / "manifest.json"
    canonical_path = development_package_dir / "canonical_documents.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    if not canonical_path.is_file():
        raise FileNotFoundError(canonical_path)
    package = _read_json(manifest_path)
    if package.get("candidate_id") != config.candidate.candidate_id:
        raise SemanticPromptPolicyError("development package candidate_id mismatch")
    if package.get("combined_document_count") != config.candidate.expected_document_count:
        raise SemanticPromptPolicyError("development package document count mismatch")
    canonical_sha = _sha256_file(canonical_path)
    if package.get("canonical_documents_sha256") != canonical_sha:
        raise SemanticPromptPolicyError("development package canonical checksum mismatch")
    if parent_manifest.canonical_input.document_count != config.candidate.expected_document_count:
        raise SemanticPromptPolicyError("raw parent canonical document count mismatch")
    if parent_manifest.canonical_input.sha256 != canonical_sha:
        raise SemanticPromptPolicyError("raw parent was not built from frozen 72-paper package")
    required_false = (
        "canonical_truth_mutated",
        "may_be_used_as_reconcile_input",
        "production_extractor_selected",
        "full_corpus_build_authorized",
        "publication_ready",
    )
    for key in required_false:
        if package.get(key) is not False:
            raise SemanticPromptPolicyError(f"development package safety flag drifted: {key}")
    if package.get("future_v02_acceptance_requires_new_disjoint_heldout") is not True:
        raise SemanticPromptPolicyError("fresh v0.2 held-out requirement must be preserved")
    return package


def _validate_candidate_runtime(
    *, config: SemanticPromptPolicyConfig, parent_manifest: ScientificEntityEvidenceManifest
) -> tuple[str, str]:
    design_path = _resolve(config.candidate.design_config_path)
    runtime_path = _resolve(config.candidate.runtime_config_path)
    contract = validate_candidate_contract(project_root=PROJECT_ROOT, design_config_path=design_path)
    if contract["candidate_id"] != config.candidate.candidate_id:
        raise SemanticPromptPolicyError("candidate contract id mismatch")
    design = load_semantic_prompt_candidate_config(design_path)
    if design.controlled_comparison.raw_candidate_inference_threshold != config.policy.input_threshold:
        raise SemanticPromptPolicyError("raw candidate threshold drifted from design")
    if design.controlled_comparison.frozen_source_field_policy.title_threshold != 0.55:
        raise SemanticPromptPolicyError("title threshold drifted from frozen design")
    if design.controlled_comparison.frozen_source_field_policy.abstract_threshold != 0.65:
        raise SemanticPromptPolicyError("abstract threshold drifted from frozen design")
    runtime = load_gliner_config(runtime_path)
    runtime_sha = gliner_config_sha256(runtime)
    if parent_manifest.extractor.config_sha256 != runtime_sha:
        raise SemanticPromptPolicyError("raw parent runtime config SHA mismatch")
    if parent_manifest.extractor.model_name != runtime.model.repository:
        raise SemanticPromptPolicyError("raw parent model repository mismatch")
    if parent_manifest.extractor.model_revision != runtime.model.revision:
        raise SemanticPromptPolicyError("raw parent model revision mismatch")
    return _design_file_sha256(design_path), runtime_sha


def _build_descriptor(
    *, config: SemanticPromptPolicyConfig, parent_manifest: ScientificEntityEvidenceManifest, design_sha: str, runtime_sha: str
) -> ScientificEntityExtractorDescriptor:
    parent = parent_manifest.extractor
    semantic_payload = {
        "schema_version": POLICY_CONFIG_SCHEMA_VERSION,
        "policy_config": config.model_dump(mode="json"),
        "candidate_design_file_sha256": design_sha,
        "candidate_runtime_config_sha256": runtime_sha,
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


def _materialize_mentions(
    *, parent_mentions: Sequence[ScientificEntityMentionEvidence], config: SemanticPromptPolicyConfig, build_id: str, extractor_fingerprint: str, parent_build_id: str
) -> tuple[tuple[ScientificEntityMentionEvidence, ...], tuple[SemanticPromptPolicyLineage, ...]]:
    selected = filter_predictions(
        parent_mentions,
        policy=_threshold_policy(config),
        input_threshold=config.policy.input_threshold,
    )
    rows: list[ScientificEntityMentionEvidence] = []
    lineage: list[SemanticPromptPolicyLineage] = []
    for parent in selected:
        payload = parent.model_dump(mode="json")
        payload.update(
            build_id=build_id,
            extractor_fingerprint=extractor_fingerprint,
            evidence_id=build_evidence_id(
                mention_id=parent.mention_id,
                extractor_fingerprint=extractor_fingerprint,
            ),
        )
        candidate = ScientificEntityMentionEvidence.model_validate(payload)
        if candidate.mention_id != parent.mention_id:
            raise SemanticPromptPolicyError("mention_id changed during policy filtering")
        if candidate.evidence_id == parent.evidence_id:
            raise SemanticPromptPolicyError("policy-aware evidence_id must differ from raw parent")
        if candidate.confidence_kind != parent.confidence_kind or candidate.confidence_score != parent.confidence_score:
            raise SemanticPromptPolicyError("confidence changed during policy filtering")
        rows.append(candidate)
        lineage.append(
            SemanticPromptPolicyLineage(
                schema_version=POLICY_LINEAGE_SCHEMA_VERSION,
                build_id=build_id,
                parent_build_id=parent_build_id,
                mention_id=parent.mention_id,
                parent_evidence_id=parent.evidence_id,
                candidate_evidence_id=candidate.evidence_id,
            )
        )
    if len({row.mention_id for row in rows}) != len(rows):
        raise SemanticPromptPolicyError("selected mention_ids must be unique")
    if len({row.evidence_id for row in rows}) != len(rows):
        raise SemanticPromptPolicyError("selected evidence_ids must be unique")
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
        "selected_prediction_count_by_source_field": {x.value: by_field[x.value] for x in ScientificEntitySourceField},
        "selected_prediction_count_by_entity_type": {x.value: by_type[x.value] for x in ScientificEntityType},
        "input_threshold": 0.5,
        "title_threshold": 0.55,
        "abstract_threshold": 0.65,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
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
        "derivation_manifest_schema_version": POLICY_DERIVATION_SCHEMA_VERSION,
        "lineage_schema_version": POLICY_LINEAGE_SCHEMA_VERSION,
        "quality_schema_version": QUALITY_SCHEMA_VERSION,
        "serialization": {"encoding": "utf-8", "line_ending": "lf"},
        "mentions_json_schema": ScientificEntityMentionEvidence.model_json_schema(),
        "manifest_json_schema": ScientificEntityEvidenceManifest.model_json_schema(),
        "derivation_manifest_json_schema": SemanticPromptPolicyDerivationManifest.model_json_schema(),
        "lineage_json_schema": SemanticPromptPolicyLineage.model_json_schema(),
    }


def _readme(build_id: str, parent_build_id: str, selected_count: int) -> str:
    return "\n".join([
        "# Scientific Entity Semantic Prompt Policy v0.2a", "",
        "Immutable policy-filtered development evidence for Semantic Prompt Candidate v0.2a.",
        "The source-field thresholds are inherited unchanged from frozen v0.1 development policy.", "",
        f"- build_id: `{build_id}`",
        f"- parent_raw_build_id: `{parent_build_id}`",
        f"- development_documents: `72`",
        f"- selected_prediction_count: `{selected_count}`", "",
        "No model inference or threshold tuning occurs in this materialization.",
        "This evidence is development-only and does not authorize production or full-corpus extraction.", "",
    ])


def build_semantic_prompt_policy(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    parent_build_dir: Path,
    development_package_dir: Path,
    output_root: Path | None = None,
    build_id: str | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = load_policy_config(config_path)
    parent_dir = parent_build_dir.resolve()
    package_dir = development_package_dir.resolve()
    parent_manifest, parent_mentions = _load_parent(parent_dir)
    package = _validate_development_package(
        development_package_dir=package_dir,
        parent_manifest=parent_manifest,
        config=config,
    )
    design_sha, runtime_sha = _validate_candidate_runtime(config=config, parent_manifest=parent_manifest)

    descriptor = _build_descriptor(
        config=config,
        parent_manifest=parent_manifest,
        design_sha=design_sha,
        runtime_sha=runtime_sha,
    )
    candidate_fingerprint = build_extractor_fingerprint(descriptor)
    if candidate_fingerprint == parent_manifest.extractor_fingerprint:
        raise SemanticPromptPolicyError("policy-aware fingerprint must differ from raw candidate")

    now = generated_at_utc or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(now):
        raise SemanticPromptPolicyError("generated_at_utc must be timezone-aware UTC")
    selected_build_id = build_id or _default_build_id(now)
    selected_output_root = _resolve(output_root or config.outputs.root)
    output_dir = selected_output_root / selected_build_id
    if execute and output_dir.exists():
        raise FileExistsError(f"Immutable policy build already exists: {output_dir}")

    rows, lineage = _materialize_mentions(
        parent_mentions=parent_mentions,
        config=config,
        build_id=selected_build_id,
        extractor_fingerprint=candidate_fingerprint,
        parent_build_id=parent_manifest.build_id,
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
        extractor_fingerprint=candidate_fingerprint,
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
    derivation = SemanticPromptPolicyDerivationManifest(
        schema_version=POLICY_DERIVATION_SCHEMA_VERSION,
        build_id=selected_build_id,
        parent_build_id=parent_manifest.build_id,
        development_package_id=str(package["package_id"]),
        candidate_id=config.candidate.candidate_id,
        design_config_sha256=design_sha,
        runtime_config_sha256=runtime_sha,
        parent_extractor_fingerprint=parent_manifest.extractor_fingerprint,
        candidate_extractor_fingerprint=candidate_fingerprint,
        input_threshold=0.5,
        title_threshold=0.55,
        abstract_threshold=0.65,
        entity_type_overrides={},
        input_prediction_count=len(parent_mentions),
        selected_prediction_count=len(rows),
        rejected_prediction_count=len(parent_mentions) - len(rows),
        mention_id_preserved=True,
        evidence_id_recomputed=True,
        confidence_preserved=True,
        model_inference_executed=False,
        threshold_tuning_executed=False,
        canonical_truth_mutated=False,
        may_be_used_as_reconcile_input=False,
        production_extractor_selected=False,
        full_corpus_build_authorized=False,
        publication_ready=False,
    )
    quality = _quality(selected_build_id, len(parent_mentions), rows)
    schema = _schema()
    readme = _readme(selected_build_id, parent_manifest.build_id, len(rows))

    written_files: list[str] = []
    if execute:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{selected_build_id}.tmp-", dir=output_dir.parent))
        try:
            (staging / "mentions.jsonl").write_bytes(mentions_bytes)
            (staging / "evidence_lineage.jsonl").write_bytes(lineage_bytes)
            (staging / "manifest.json").write_bytes(_json_bytes(manifest.model_dump(mode="json")))
            (staging / "derivation_manifest.json").write_bytes(_json_bytes(derivation.model_dump(mode="json")))
            (staging / "data_quality_summary.json").write_bytes(_json_bytes(quality))
            (staging / "schema.json").write_bytes(_json_bytes(schema))
            (staging / "README.md").write_text(readme, encoding="utf-8", newline="\n")
            checksum_lines = []
            for filename in REQUIRED_FILES[:-1]:
                checksum_lines.append(f"{_sha256_file(staging / filename)}  {filename}")
            (staging / "checksums.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8", newline="\n")
            staging.rename(output_dir)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
        written_files = list(REQUIRED_FILES)

    return {
        "report": REPORT_NAME,
        "ok": True,
        "mode": "execute" if execute else "plan",
        "phase_complete": execute,
        "build_id": selected_build_id,
        "parent_build_id": parent_manifest.build_id,
        "development_package_id": package["package_id"],
        "candidate_id": config.candidate.candidate_id,
        "input_document_count": parent_manifest.canonical_input.document_count,
        "input_prediction_count": len(parent_mentions),
        "selected_prediction_count": len(rows),
        "rejected_prediction_count": len(parent_mentions) - len(rows),
        "parent_extractor_fingerprint": parent_manifest.extractor_fingerprint,
        "candidate_extractor_fingerprint": candidate_fingerprint,
        "extractor_fingerprint_changed": candidate_fingerprint != parent_manifest.extractor_fingerprint,
        "title_threshold": 0.55,
        "abstract_threshold": 0.65,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "canonical_truth_mutated": False,
        "full_corpus_build_authorized": False,
        "production_extractor_selected": False,
        "output_dir": str(output_dir).replace("\\", "/"),
        "written_files": written_files,
        "next_slice": "controlled_semantic_prompt_comparison_on_24_48_72_development_splits" if execute else "execute_semantic_prompt_policy_materialization_v02a",
    }


def validate_semantic_prompt_policy_build(
    *,
    build_dir: Path,
    parent_build_dir: Path,
    development_package_dir: Path,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    build_dir = build_dir.resolve()
    for filename in REQUIRED_FILES:
        if not (build_dir / filename).is_file():
            raise FileNotFoundError(build_dir / filename)

    checksums: dict[str, str] = {}
    for line in (build_dir / "checksums.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        sha, filename = line.split("  ", 1)
        checksums[filename] = sha
    if set(checksums) != set(REQUIRED_FILES[:-1]):
        raise SemanticPromptPolicyError("checksums.txt coverage mismatch")
    for filename, expected in checksums.items():
        if _sha256_file(build_dir / filename) != expected:
            raise SemanticPromptPolicyError(f"checksum mismatch: {filename}")

    manifest = ScientificEntityEvidenceManifest.model_validate(_read_json(build_dir / "manifest.json"))
    derivation = SemanticPromptPolicyDerivationManifest.model_validate(_read_json(build_dir / "derivation_manifest.json"))
    rows = tuple(ScientificEntityMentionEvidence.model_validate(x) for x in _read_jsonl(build_dir / "mentions.jsonl"))
    lineage = tuple(SemanticPromptPolicyLineage.model_validate(x) for x in _read_jsonl(build_dir / "evidence_lineage.jsonl"))
    if manifest.mention_count != len(rows) or manifest.mentions_sha256 != _sha256_file(build_dir / "mentions.jsonl"):
        raise SemanticPromptPolicyError("materialized mention manifest mismatch")
    if len(lineage) != len(rows):
        raise SemanticPromptPolicyError("lineage count mismatch")
    if manifest.build_id != derivation.build_id:
        raise SemanticPromptPolicyError("build_id mismatch across manifest/derivation")
    if manifest.extractor_fingerprint != derivation.candidate_extractor_fingerprint:
        raise SemanticPromptPolicyError("candidate fingerprint mismatch")

    plan = build_semantic_prompt_policy(
        config_path=config_path,
        parent_build_dir=parent_build_dir,
        development_package_dir=development_package_dir,
        output_root=build_dir.parent,
        build_id=manifest.build_id,
        execute=False,
        generated_at_utc=manifest.generated_at_utc,
    )
    if plan["selected_prediction_count"] != manifest.mention_count:
        raise SemanticPromptPolicyError("recomputed selected count mismatch")
    if plan["candidate_extractor_fingerprint"] != manifest.extractor_fingerprint:
        raise SemanticPromptPolicyError("recomputed extractor fingerprint mismatch")

    parent_manifest, parent_mentions = _load_parent(parent_build_dir.resolve())
    parent_by_id = {row.mention_id: row for row in parent_mentions}
    for row, line in zip(rows, lineage, strict=True):
        parent = parent_by_id.get(row.mention_id)
        if parent is None:
            raise SemanticPromptPolicyError("selected mention missing from raw parent")
        if line.mention_id != row.mention_id or line.parent_evidence_id != parent.evidence_id or line.candidate_evidence_id != row.evidence_id:
            raise SemanticPromptPolicyError("lineage row mismatch")
        if row.evidence_id != build_evidence_id(mention_id=row.mention_id, extractor_fingerprint=manifest.extractor_fingerprint):
            raise SemanticPromptPolicyError("candidate evidence_id does not reproduce")
        if row.confidence_score != parent.confidence_score or row.confidence_kind != parent.confidence_kind:
            raise SemanticPromptPolicyError("confidence did not remain unchanged")

    quality = _read_json(build_dir / "data_quality_summary.json")
    if quality.get("input_prediction_count") != len(parent_mentions):
        raise SemanticPromptPolicyError("quality input count mismatch")
    if quality.get("selected_prediction_count") != len(rows):
        raise SemanticPromptPolicyError("quality selected count mismatch")
    if quality.get("rejected_prediction_count") != len(parent_mentions) - len(rows):
        raise SemanticPromptPolicyError("quality rejected count mismatch")

    return {
        "report": REPORT_NAME,
        "ok": True,
        "build_id": manifest.build_id,
        "parent_build_id": parent_manifest.build_id,
        "input_document_count": manifest.canonical_input.document_count,
        "input_prediction_count": len(parent_mentions),
        "selected_prediction_count": len(rows),
        "rejected_prediction_count": len(parent_mentions) - len(rows),
        "extractor_fingerprint_changed": manifest.extractor_fingerprint != parent_manifest.extractor_fingerprint,
        "model_inference_executed": derivation.model_inference_executed,
        "threshold_tuning_executed": derivation.threshold_tuning_executed,
        "canonical_truth_mutated": derivation.canonical_truth_mutated,
        "full_corpus_build_authorized": derivation.full_corpus_build_authorized,
        "required_failed_count": 0,
        "next_slice": "controlled_semantic_prompt_comparison_on_24_48_72_development_splits",
    }
