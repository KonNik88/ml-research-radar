from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.contracts.scientific_entity_evidence import (
    ConfidenceKind,
    MENTION_SCHEMA_VERSION,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    ScientificEntityType,
    build_evidence_id,
    build_extractor_fingerprint,
    build_mention_id,
    sha256_text,
)
from radar_core.contracts.scientific_entity_semantic_typer_candidate import (
    SemanticTyperPrediction,
    load_semantic_typer_config,
    semantic_typer_config_sha256,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_frozen_candidate import (
    FrozenH2CandidateDefinition,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_acceptance_gate import (
    canonical_config_sha256 as acceptance_gate_sha256,
    load_h2_independent_acceptance_gate_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_inference import (
    H2IndependentInferenceCase,
    H2IndependentInferenceManifest,
    H2IndependentInferenceSummary,
    H2IndependentPrediction,
    ScientificEntityH2IndependentInferenceError,
    canonical_config_sha256 as inference_config_sha256,
    load_h2_independent_inference_config,
)
from radar_core.entities.scientific_entity_gliner import (
    GLiNERBackend,
    ScientificEntityGLiNERAdapter,
    build_gliner_extractor_descriptor,
    gliner_config_sha256,
    load_gliner_config,
    load_native_gliner_backend,
    normalized_source_bundle_revision,
    normalized_text_sha256,
)
from radar_core.entities.scientific_entity_gliner_calibration import filter_predictions
from radar_core.entities.scientific_entity_semantic_prompt_raw_floor_policy import (
    load_raw_floor_policy_config,
    policy_config_sha256,
)
from radar_core.entities.scientific_entity_semantic_typer import (
    semantic_typer_fingerprint,
    type_semantic_case,
)
from radar_core.entities.scientific_entity_semantic_typer_h2_reference import (
    validate_frozen_reference_evidence,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_semantic_typer_h2_independent_inference_v0.3.yaml"
DEFAULT_CANONICAL = PROJECT_ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
REPORT_NAME = "scientific_entity_semantic_typer_h2_independent_inference_v03"
REQUIRED_FILES = {
    "upstream_raw_mentions.jsonl",
    "baseline_mentions.jsonl",
    "semantic_typer_cases.jsonl",
    "semantic_typer_predictions.jsonl",
    "h2_predictions.jsonl",
    "manifest.json",
    "summary.json",
    "README.md",
    "checksums.txt",
}
CHECKSUM_FILES = REQUIRED_FILES - {"checksums.txt"}


SOURCE_FIELD_ORDER = {
    ScientificEntitySourceField.TITLE: 0,
    ScientificEntitySourceField.ABSTRACT: 1,
}


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_id(prefix: str, parts: Sequence[str]) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


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
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScientificEntityH2IndependentInferenceError(f"Invalid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ScientificEntityH2IndependentInferenceError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                raise ScientificEntityH2IndependentInferenceError(f"Blank JSONL line: {path}:{line_number}")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ScientificEntityH2IndependentInferenceError(f"Expected JSON object: {path}:{line_number}")
            rows.append(payload)
    return rows


def _write_atomic(output_dir: Path, payloads: Mapping[str, bytes]) -> None:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        for name, data in payloads.items():
            (temp / name).write_bytes(data)
        temp.rename(output_dir)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def _checksums(payloads: Mapping[str, bytes]) -> bytes:
    names = sorted(name for name in payloads if name != "checksums.txt")
    return "".join(
        f"{hashlib.sha256(payloads[name]).hexdigest()}  {name}\n" for name in names
    ).encode("utf-8")


def _parse_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        result[name] = digest
    return result


def _load_documents(path: Path, *, expected_count: int) -> tuple[CanonicalDocument, ...]:
    docs = tuple(CanonicalDocument.model_validate(row) for row in _read_jsonl(path))
    if len(docs) != expected_count:
        raise ScientificEntityH2IndependentInferenceError(
            f"Expected {expected_count} held-out documents, found {len(docs)}"
        )
    ids = [row.canonical_id for row in docs]
    if len(set(ids)) != len(ids):
        raise ScientificEntityH2IndependentInferenceError("Duplicate canonical_id in held-out sample")
    return docs


def _validate_parent_state(
    *,
    root: Path,
    config_path: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    previous_heldout_sample_dir: Path,
    frozen_candidate_dir: Path,
    canonical_path: Path,
) -> dict[str, Any]:
    config = load_h2_independent_inference_config(config_path)

    gate_path = _resolve(root, config.lineage.acceptance_gate_config_path)
    gate = load_h2_independent_acceptance_gate_config(gate_path)
    gate_sha = acceptance_gate_sha256(gate)
    if gate_sha != config.lineage.acceptance_gate_config_sha256:
        raise ScientificEntityH2IndependentInferenceError("Independent acceptance gate SHA-256 drifted")
    if gate.candidate_lineage.candidate_id != config.candidate.candidate_id:
        raise ScientificEntityH2IndependentInferenceError("Acceptance gate candidate_id drifted")
    if gate.candidate_lineage.candidate_fingerprint_sha256 != config.candidate.candidate_fingerprint_sha256:
        raise ScientificEntityH2IndependentInferenceError("Acceptance gate candidate fingerprint drifted")
    if gate.fresh_heldout_lineage.sample_id != config.lineage.sample_id:
        raise ScientificEntityH2IndependentInferenceError("Acceptance gate sample_id drifted")
    if gate.fresh_heldout_lineage.review_id != config.lineage.review_id:
        raise ScientificEntityH2IndependentInferenceError("Acceptance gate review_id drifted")

    reference_config_path = _resolve(root, config.lineage.reference_config_path)
    checks, reference_summary = validate_frozen_reference_evidence(
        project_root=root,
        config_path=reference_config_path,
        acceptance_gate_config_path=gate_path,
        sample_dir=sample_dir,
        canonical_path=canonical_path,
        development_package_dir=development_package_dir,
        previous_heldout_sample_dir=previous_heldout_sample_dir,
        frozen_candidate_dir=frozen_candidate_dir,
        reference_dir=reference_dir,
    )
    if any(not ok for _, ok, _ in checks) or reference_summary["required_failed_count"] != 0:
        raise ScientificEntityH2IndependentInferenceError(
            "Frozen H2 reference evidence failed strict pre-inference validation"
        )
    if reference_summary.get("reference_frozen") is not True:
        raise ScientificEntityH2IndependentInferenceError("Human reference is not frozen")
    if reference_summary.get("h2_model_inference_executed") is not False:
        raise ScientificEntityH2IndependentInferenceError("H2 inference was already marked executed in reference evidence")
    if reference_summary.get("evaluation_executed") is not False:
        raise ScientificEntityH2IndependentInferenceError("Evaluation was already marked executed in reference evidence")

    candidate_manifest_path = frozen_candidate_dir / "manifest.json"
    candidate_definition_path = frozen_candidate_dir / "frozen_candidate.json"
    candidate_manifest = _read_json(candidate_manifest_path)
    candidate = FrozenH2CandidateDefinition.model_validate(_read_json(candidate_definition_path))
    if candidate.candidate_id != config.candidate.candidate_id:
        raise ScientificEntityH2IndependentInferenceError("Frozen H2 candidate_id drifted")
    if candidate.candidate_fingerprint_sha256 != config.candidate.candidate_fingerprint_sha256:
        raise ScientificEntityH2IndependentInferenceError("Frozen H2 candidate fingerprint drifted")
    if candidate.parent_semantic_typer_candidate_id != config.candidate.parent_semantic_typer_candidate_id:
        raise ScientificEntityH2IndependentInferenceError("Frozen H2 parent semantic typer drifted")
    if candidate.parent_semantic_typer_config_sha256 != config.candidate.parent_semantic_typer_config_sha256:
        raise ScientificEntityH2IndependentInferenceError("Frozen H2 parent semantic typer config SHA drifted")
    if candidate.threshold != config.execution.h2_threshold:
        raise ScientificEntityH2IndependentInferenceError("Frozen H2 threshold drifted")
    if candidate.baseline_type != config.execution.h2_baseline_type:
        raise ScientificEntityH2IndependentInferenceError("Frozen H2 baseline type drifted")
    if candidate.semantic_typer_type != config.execution.h2_semantic_typer_type:
        raise ScientificEntityH2IndependentInferenceError("Frozen H2 semantic typer type drifted")

    semantic_config_path = _resolve(root, config.candidate.parent_semantic_typer_config_path)
    semantic_config = load_semantic_typer_config(semantic_config_path)
    semantic_sha = semantic_typer_config_sha256(semantic_config)
    if semantic_sha != config.candidate.parent_semantic_typer_config_sha256:
        raise ScientificEntityH2IndependentInferenceError("Parent semantic typer config SHA-256 drifted")
    if semantic_config.candidate.candidate_id != config.candidate.parent_semantic_typer_candidate_id:
        raise ScientificEntityH2IndependentInferenceError("Parent semantic typer candidate_id drifted")

    runtime_path = _resolve(root, config.candidate.upstream_runtime_config_path)
    runtime_config = load_gliner_config(runtime_path)
    runtime_sha = gliner_config_sha256(runtime_config)
    if runtime_sha != config.candidate.upstream_runtime_config_sha256:
        raise ScientificEntityH2IndependentInferenceError("Upstream v0.2c runtime config SHA-256 drifted")
    if runtime_config.inference.threshold != config.execution.raw_input_threshold:
        raise ScientificEntityH2IndependentInferenceError("Upstream raw input threshold drifted")

    policy_path = _resolve(root, config.candidate.upstream_policy_config_path)
    policy_config = load_raw_floor_policy_config(policy_path)
    policy_sha = policy_config_sha256(policy_config)
    if policy_sha != config.candidate.upstream_policy_config_sha256:
        raise ScientificEntityH2IndependentInferenceError("Upstream frozen baseline policy SHA-256 drifted")
    if policy_config.candidate.candidate_id != config.candidate.upstream_baseline_candidate_id:
        raise ScientificEntityH2IndependentInferenceError("Upstream baseline candidate_id drifted")
    title_threshold = float(policy_config.policy.source_field_thresholds[ScientificEntitySourceField.TITLE])
    abstract_threshold = float(policy_config.policy.source_field_thresholds[ScientificEntitySourceField.ABSTRACT])
    if title_threshold != config.execution.baseline_title_threshold:
        raise ScientificEntityH2IndependentInferenceError("Frozen title threshold drifted")
    if abstract_threshold != config.execution.baseline_abstract_threshold:
        raise ScientificEntityH2IndependentInferenceError("Frozen abstract threshold drifted")
    if policy_config.policy.entity_type_thresholds:
        raise ScientificEntityH2IndependentInferenceError("Unexpected frozen entity-type threshold overrides")

    sample_manifest_path = sample_dir / "manifest.json"
    sample_manifest = _read_json(sample_manifest_path)
    if sample_manifest.get("sample_id") != config.lineage.sample_id:
        raise ScientificEntityH2IndependentInferenceError("Held-out sample_id drifted")
    if sample_manifest.get("review_id") != config.lineage.review_id:
        raise ScientificEntityH2IndependentInferenceError("Held-out review_id drifted")
    if sample_manifest.get("candidate_fingerprint_sha256") != config.candidate.candidate_fingerprint_sha256:
        raise ScientificEntityH2IndependentInferenceError("Held-out sample candidate fingerprint drifted")

    reference_completion_path = reference_dir / "completion_manifest.json"
    reference_completion = _read_json(reference_completion_path)
    reference_mentions_path = reference_dir / "reference_mentions.jsonl"

    return {
        "config": config,
        "inference_config_sha": inference_config_sha256(config),
        "gate_sha": gate_sha,
        "reference_summary": reference_summary,
        "candidate": candidate,
        "candidate_manifest_sha": _sha256_file(candidate_manifest_path),
        "candidate_definition_sha": _sha256_file(candidate_definition_path),
        "semantic_config": semantic_config,
        "semantic_config_sha": semantic_sha,
        "semantic_typer_fingerprint": semantic_typer_fingerprint(semantic_config),
        "runtime_path": runtime_path,
        "runtime_config": runtime_config,
        "runtime_sha": runtime_sha,
        "policy_config": policy_config,
        "policy_sha": policy_sha,
        "sample_manifest_sha": _sha256_file(sample_manifest_path),
        "reference_completion_sha": _sha256_file(reference_completion_path),
        "reference_mentions_sha": _sha256_file(reference_mentions_path),
        "reference_completion": reference_completion,
    }


def _extract_raw_mentions(
    *,
    root: Path,
    documents: Sequence[CanonicalDocument],
    runtime_config,
    backend: GLiNERBackend,
    raw_build_id: str,
) -> tuple[ScientificEntityMentionEvidence, ...]:
    environment_lock = _resolve(root, runtime_config.extractor.environment_lock_path)
    descriptor = build_gliner_extractor_descriptor(
        config=runtime_config,
        config_sha256=gliner_config_sha256(runtime_config),
        environment_sha256=normalized_text_sha256(environment_lock),
        code_revision=normalized_source_bundle_revision(root),
    )
    fingerprint = build_extractor_fingerprint(descriptor)
    adapter = ScientificEntityGLiNERAdapter(
        config=runtime_config,
        descriptor=descriptor,
        backend=backend,
    )
    rows: list[ScientificEntityMentionEvidence] = []
    seen_evidence: set[str] = set()
    seen_mentions: set[str] = set()
    for document in documents:
        source_values = {
            ScientificEntitySourceField.TITLE: document.title,
            ScientificEntitySourceField.ABSTRACT: document.abstract,
        }
        for source_field in runtime_config.inference.source_fields:
            source_text = source_values[source_field]
            if source_text in (None, ""):
                continue
            result = adapter.extract(
                canonical_id=document.canonical_id,
                source_field=source_field,
                source_text=source_text,
            )
            source_sha = sha256_text(source_text)
            for candidate in result.candidates:
                mention_id = build_mention_id(
                    canonical_id=document.canonical_id,
                    source_field=source_field,
                    source_text_sha256=source_sha,
                    char_start=candidate.char_start,
                    char_end=candidate.char_end,
                    entity_type=candidate.entity_type,
                )
                evidence_id = build_evidence_id(
                    mention_id=mention_id,
                    extractor_fingerprint=fingerprint,
                )
                if mention_id in seen_mentions or evidence_id in seen_evidence:
                    raise ScientificEntityH2IndependentInferenceError("Duplicate raw mention/evidence identity")
                seen_mentions.add(mention_id)
                seen_evidence.add(evidence_id)
                rows.append(
                    ScientificEntityMentionEvidence(
                        schema_version=MENTION_SCHEMA_VERSION,
                        evidence_id=evidence_id,
                        mention_id=mention_id,
                        build_id=raw_build_id,
                        canonical_id=document.canonical_id,
                        entity_type=candidate.entity_type,
                        source_field=source_field,
                        source_text_sha256=source_sha,
                        char_start=candidate.char_start,
                        char_end=candidate.char_end,
                        surface_text=source_text[candidate.char_start:candidate.char_end],
                        extractor_fingerprint=fingerprint,
                        confidence_kind=ConfidenceKind.MODEL_SCORE,
                        confidence_score=round(candidate.score, 8),
                        calibration_id=None,
                    )
                )
    rows.sort(
        key=lambda row: (
            row.canonical_id,
            SOURCE_FIELD_ORDER[row.source_field],
            row.char_start,
            row.char_end,
            row.entity_type.value,
            row.evidence_id,
        )
    )
    return tuple(rows)


def _baseline_predictions(raw_rows: Sequence[ScientificEntityMentionEvidence], *, policy_config) -> tuple[ScientificEntityMentionEvidence, ...]:
    return filter_predictions(
        raw_rows,
        policy=_threshold_policy(policy_config),
        input_threshold=policy_config.policy.input_threshold,
    )


def _threshold_policy(policy_config):
    from radar_core.contracts.scientific_entity_gliner_calibration import ScientificEntityThresholdPolicy

    return ScientificEntityThresholdPolicy(
        default_threshold=policy_config.policy.default_threshold,
        source_field_thresholds=policy_config.policy.source_field_thresholds,
        entity_type_thresholds=policy_config.policy.entity_type_thresholds,
    )


def _source_map(documents: Sequence[CanonicalDocument]) -> dict[tuple[str, ScientificEntitySourceField], str]:
    result: dict[tuple[str, ScientificEntitySourceField], str] = {}
    for doc in documents:
        if doc.title not in (None, ""):
            result[(doc.canonical_id, ScientificEntitySourceField.TITLE)] = doc.title
        if doc.abstract not in (None, ""):
            result[(doc.canonical_id, ScientificEntitySourceField.ABSTRACT)] = doc.abstract
    return result


def _build_cases(
    *,
    sample_id: str,
    documents: Sequence[CanonicalDocument],
    baseline_rows: Sequence[ScientificEntityMentionEvidence],
    semantic_config,
) -> tuple[H2IndependentInferenceCase, ...]:
    sources = _source_map(documents)
    cases: list[H2IndependentInferenceCase] = []
    for row in baseline_rows:
        source_text = sources.get((row.canonical_id, row.source_field))
        if source_text is None:
            raise ScientificEntityH2IndependentInferenceError("Baseline mention source field missing from sample")
        if sha256_text(source_text) != row.source_text_sha256:
            raise ScientificEntityH2IndependentInferenceError("Baseline source-text SHA mismatch")
        surface = source_text[row.char_start:row.char_end]
        if surface != row.surface_text:
            raise ScientificEntityH2IndependentInferenceError("Baseline surface is not exact source slice")
        if row.confidence_score is None:
            raise ScientificEntityH2IndependentInferenceError("Baseline model score is missing")
        left_chars = semantic_config.semantic_typing.context_left_chars
        right_chars = semantic_config.semantic_typing.context_right_chars
        cases.append(
            H2IndependentInferenceCase(
                case_id=_stable_id("h2-independent-case", [sample_id, row.evidence_id]),
                canonical_id=row.canonical_id,
                source_field=row.source_field,
                source_text_sha256=row.source_text_sha256,
                baseline_prediction_evidence_id=row.evidence_id,
                char_start=row.char_start,
                char_end=row.char_end,
                surface_text=row.surface_text,
                baseline_entity_type=row.entity_type,
                baseline_confidence_score=row.confidence_score,
                left_context=source_text[max(0, row.char_start-left_chars):row.char_start],
                right_context=source_text[row.char_end:min(len(source_text), row.char_end+right_chars)],
            )
        )
    case_ids = [row.case_id for row in cases]
    if len(set(case_ids)) != len(case_ids):
        raise ScientificEntityH2IndependentInferenceError("Duplicate H2 inference case_id")
    return tuple(cases)


def _run_semantic_typer(*, cases: Sequence[H2IndependentInferenceCase], semantic_config, backend: GLiNERBackend) -> tuple[SemanticTyperPrediction, ...]:
    predictions = tuple(
        type_semantic_case(config=semantic_config, case=case, backend=backend)
        for case in cases
    )
    if [row.case_id for row in predictions] != [row.case_id for row in cases]:
        raise ScientificEntityH2IndependentInferenceError("Semantic typer prediction order drifted")
    return predictions


def _apply_h2_policy(
    *,
    inference_id: str,
    cases: Sequence[H2IndependentInferenceCase],
    semantic_predictions: Sequence[SemanticTyperPrediction],
    baseline_type: ScientificEntityType,
    semantic_typer_type: ScientificEntityType,
    threshold: float,
) -> tuple[H2IndependentPrediction, ...]:
    if len(cases) != len(semantic_predictions):
        raise ScientificEntityH2IndependentInferenceError("Case/prediction count mismatch")
    output: list[H2IndependentPrediction] = []
    for case, semantic in zip(cases, semantic_predictions):
        if case.case_id != semantic.case_id:
            raise ScientificEntityH2IndependentInferenceError("Case/prediction identity mismatch")
        override = (
            case.baseline_entity_type == baseline_type
            and not semantic.used_baseline_fallback
            and semantic.predicted_entity_type == semantic_typer_type
            and semantic.score_margin is not None
            and semantic.score_margin >= threshold
        )
        final_type = semantic_typer_type if override else case.baseline_entity_type
        output.append(
            H2IndependentPrediction(
                inference_id=inference_id,
                case_id=case.case_id,
                canonical_id=case.canonical_id,
                source_field=case.source_field,
                source_text_sha256=case.source_text_sha256,
                char_start=case.char_start,
                char_end=case.char_end,
                surface_text=case.surface_text,
                baseline_prediction_evidence_id=case.baseline_prediction_evidence_id,
                baseline_entity_type=case.baseline_entity_type,
                baseline_confidence_score=case.baseline_confidence_score,
                semantic_typer_candidate_id=semantic.candidate_id,
                semantic_typer_predicted_entity_type=semantic.predicted_entity_type,
                semantic_typer_used_baseline_fallback=semantic.used_baseline_fallback,
                semantic_typer_score_margin=semantic.score_margin,
                h2_override_applied=override,
                final_entity_type=final_type,
            )
        )
    return tuple(output)


def _summary(
    *,
    inference_id: str,
    raw_rows: Sequence[ScientificEntityMentionEvidence],
    baseline_rows: Sequence[ScientificEntityMentionEvidence],
    cases: Sequence[H2IndependentInferenceCase],
    semantic_rows: Sequence[SemanticTyperPrediction],
    h2_rows: Sequence[H2IndependentPrediction],
) -> H2IndependentInferenceSummary:
    scored = sum(not row.used_baseline_fallback for row in semantic_rows)
    fallback = len(semantic_rows) - scored
    baseline_counts = Counter(row.entity_type.value for row in baseline_rows)
    final_counts = Counter(row.final_entity_type.value for row in h2_rows)
    source_counts = Counter(row.source_field.value for row in baseline_rows)
    return H2IndependentInferenceSummary(
        inference_id=inference_id,
        input_document_count=48,
        upstream_raw_mention_count=len(raw_rows),
        baseline_prediction_count=len(baseline_rows),
        semantic_typer_case_count=len(cases),
        semantic_typer_scored_count=scored,
        semantic_typer_fallback_count=fallback,
        typer_coverage=round(scored / len(cases), 6) if cases else 0.0,
        h2_override_count=sum(row.h2_override_applied for row in h2_rows),
        baseline_count_by_type={kind.value: baseline_counts[kind.value] for kind in ScientificEntityType},
        final_count_by_type={kind.value: final_counts[kind.value] for kind in ScientificEntityType},
        source_field_counts={field.value: source_counts[field.value] for field in ScientificEntitySourceField},
    )


def _readme(*, inference_id: str, candidate_id: str, sample_id: str) -> bytes:
    text = (
        "# H2 v0.3 frozen independent inference\n\n"
        f"Inference ID: `{inference_id}`\n\n"
        f"Candidate ID: `{candidate_id}`\n\n"
        f"Fresh held-out sample: `{sample_id}`\n\n"
        "This immutable package was created only after prediction-blind human reference freeze.\n\n"
        "It contains frozen upstream v0.2c raw predictions, the frozen baseline-threshold subset, "
        "reference-free semantic-typer cases/scores, and the frozen H2 selective method-to-model decisions.\n\n"
        "Human reference labels are not present in inference cases or predictions. Evaluation and acceptance "
        "decision are separate later slices. No threshold tuning or policy revision is allowed on this held-out.\n"
    )
    return text.encode("utf-8")


def plan_or_execute_h2_independent_inference(
    *,
    project_root: Path,
    config_path: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    previous_heldout_sample_dir: Path,
    frozen_candidate_dir: Path,
    canonical_path: Path,
    inference_id: str | None = None,
    output_root: Path | None = None,
    execute: bool = False,
    allow_model_download: bool = False,
    model_cache_dir: Path | None = None,
    backend: GLiNERBackend | None = None,
    allow_test_backend: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    config_path = config_path.resolve()
    sample_dir = sample_dir.resolve()
    reference_dir = reference_dir.resolve()
    development_package_dir = development_package_dir.resolve()
    previous_heldout_sample_dir = previous_heldout_sample_dir.resolve()
    frozen_candidate_dir = frozen_candidate_dir.resolve()
    canonical_path = canonical_path.resolve()

    parent = _validate_parent_state(
        root=root,
        config_path=config_path,
        sample_dir=sample_dir,
        reference_dir=reference_dir,
        development_package_dir=development_package_dir,
        previous_heldout_sample_dir=previous_heldout_sample_dir,
        frozen_candidate_dir=frozen_candidate_dir,
        canonical_path=canonical_path,
    )
    config = parent["config"]
    generated_at = generated_at_utc or datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() != timezone.utc.utcoffset(generated_at):
        raise ScientificEntityH2IndependentInferenceError("generated_at_utc must be timezone-aware UTC")
    selected_id = inference_id or (
        config.execution.inference_id_prefix + "-" + generated_at.strftime("%Y%m%dT%H%M%S%fZ")
    )
    selected_root = output_root.resolve() if output_root is not None else _resolve(root, config.execution.output_root)
    output_dir = selected_root / selected_id
    already_executed = output_dir.exists()
    if execute and already_executed:
        raise FileExistsError(f"Immutable H2 independent inference already exists: {output_dir}")
    if backend is not None and not allow_test_backend:
        raise ScientificEntityH2IndependentInferenceError("Injected backend is test-only")

    report: dict[str, Any] = {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "candidate_id": config.candidate.candidate_id,
        "candidate_fingerprint_sha256": config.candidate.candidate_fingerprint_sha256,
        "sample_id": config.lineage.sample_id,
        "review_id": config.lineage.review_id,
        "reference_validation_required_failed_count": parent["reference_summary"]["required_failed_count"],
        "reference_frozen_before_inference": True,
        "input_document_count": config.lineage.expected_document_count,
        "inference_id": selected_id,
        "one_shot_already_executed": already_executed,
        "plan_runs_model_inference": False,
        "upstream_model_inference_executed": False,
        "semantic_typer_model_inference_executed": False,
        "frozen_h2_policy_applied": False,
        "reference_labels_used_for_case_construction": False,
        "reference_labels_used_as_model_features": False,
        "threshold_tuning_executed": False,
        "policy_revision_executed": False,
        "span_mutated": False,
        "evaluation_executed": False,
        "acceptance_decision_made": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "output_dir": str(output_dir).replace("\\", "/"),
        "next_slice": config.next_steps.after_plan,
    }
    if not execute:
        return report

    documents = _load_documents(
        sample_dir / "canonical_documents.sample.jsonl",
        expected_count=config.lineage.expected_document_count,
    )

    selected_backend = backend
    runtime_meta: dict[str, Any] = {"backend_injected_for_test": backend is not None}
    if selected_backend is None:
        loaded = load_native_gliner_backend(
            config=parent["runtime_config"],
            allow_model_download=allow_model_download,
            cache_dir=model_cache_dir,
        )
        selected_backend = loaded.backend
        runtime_meta.update(
            {
                "model_artifact_verified": loaded.model_artifact_verified,
                "backbone_config_verified": loaded.backbone_config_verified,
                "model_weights_downloaded": loaded.model_weights_downloaded,
                "backbone_config_downloaded": loaded.backbone_config_downloaded,
                "runtime_device_name": None,
            }
        )
        if parent["runtime_config"].inference.device == "cuda":
            import torch

            runtime_meta["runtime_device_name"] = torch.cuda.get_device_name(0)
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()

    started = time.perf_counter()
    raw_rows = _extract_raw_mentions(
        root=root,
        documents=documents,
        runtime_config=parent["runtime_config"],
        backend=selected_backend,
        raw_build_id=selected_id + "-upstream-raw-v02c",
    )
    baseline_rows = _baseline_predictions(raw_rows, policy_config=parent["policy_config"])
    cases = _build_cases(
        sample_id=config.lineage.sample_id,
        documents=documents,
        baseline_rows=baseline_rows,
        semantic_config=parent["semantic_config"],
    )
    semantic_rows = _run_semantic_typer(
        cases=cases,
        semantic_config=parent["semantic_config"],
        backend=selected_backend,
    )
    h2_rows = _apply_h2_policy(
        inference_id=selected_id,
        cases=cases,
        semantic_predictions=semantic_rows,
        baseline_type=config.execution.h2_baseline_type,
        semantic_typer_type=config.execution.h2_semantic_typer_type,
        threshold=config.execution.h2_threshold,
    )
    duration = time.perf_counter() - started
    peak_cuda_memory_bytes: int | None = None
    if backend is None and parent["runtime_config"].inference.device == "cuda":
        import torch

        torch.cuda.synchronize()
        peak_cuda_memory_bytes = int(torch.cuda.max_memory_allocated())

    summary = _summary(
        inference_id=selected_id,
        raw_rows=raw_rows,
        baseline_rows=baseline_rows,
        cases=cases,
        semantic_rows=semantic_rows,
        h2_rows=h2_rows,
    )

    payloads: dict[str, bytes] = {
        "upstream_raw_mentions.jsonl": _jsonl_bytes(raw_rows),
        "baseline_mentions.jsonl": _jsonl_bytes(baseline_rows),
        "semantic_typer_cases.jsonl": _jsonl_bytes(cases),
        "semantic_typer_predictions.jsonl": _jsonl_bytes(semantic_rows),
        "h2_predictions.jsonl": _jsonl_bytes(h2_rows),
        "summary.json": _json_bytes(summary),
        "README.md": _readme(
            inference_id=selected_id,
            candidate_id=config.candidate.candidate_id,
            sample_id=config.lineage.sample_id,
        ),
    }
    manifest_files = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
    manifest = H2IndependentInferenceManifest(
        inference_id=selected_id,
        candidate_id=config.candidate.candidate_id,
        candidate_fingerprint_sha256=config.candidate.candidate_fingerprint_sha256,
        sample_id=config.lineage.sample_id,
        review_id=config.lineage.review_id,
        inference_config_sha256=parent["inference_config_sha"],
        acceptance_gate_config_sha256=parent["gate_sha"],
        sample_manifest_sha256=parent["sample_manifest_sha"],
        frozen_candidate_manifest_sha256=parent["candidate_manifest_sha"],
        frozen_candidate_sha256=parent["candidate_definition_sha"],
        reference_completion_manifest_sha256=parent["reference_completion_sha"],
        reference_mentions_sha256=parent["reference_mentions_sha"],
        parent_semantic_typer_config_sha256=parent["semantic_config_sha"],
        upstream_runtime_config_sha256=parent["runtime_sha"],
        upstream_policy_config_sha256=parent["policy_sha"],
        input_document_count=48,
        upstream_raw_mention_count=len(raw_rows),
        baseline_prediction_count=len(baseline_rows),
        semantic_typer_case_count=len(cases),
        semantic_typer_scored_count=summary.semantic_typer_scored_count,
        semantic_typer_fallback_count=summary.semantic_typer_fallback_count,
        h2_override_count=summary.h2_override_count,
        files=manifest_files,
        next_slice=config.next_steps.after_execute,
    )
    payloads["manifest.json"] = _json_bytes(manifest)
    payloads["checksums.txt"] = _checksums(payloads)
    _write_atomic(output_dir, payloads)

    report.update(
        {
            "phase_complete": True,
            "one_shot_already_executed": True,
            "upstream_model_inference_executed": True,
            "semantic_typer_model_inference_executed": True,
            "frozen_h2_policy_applied": True,
            "upstream_raw_mention_count": len(raw_rows),
            "baseline_prediction_count": len(baseline_rows),
            "semantic_typer_case_count": len(cases),
            "semantic_typer_scored_count": summary.semantic_typer_scored_count,
            "semantic_typer_fallback_count": summary.semantic_typer_fallback_count,
            "typer_coverage": summary.typer_coverage,
            "h2_override_count": summary.h2_override_count,
            "inference_duration_seconds": round(duration, 6),
            "peak_cuda_memory_bytes": peak_cuda_memory_bytes,
            "runtime_device_name": runtime_meta.get("runtime_device_name"),
            "model_artifact_verified": runtime_meta.get("model_artifact_verified"),
            "backbone_config_verified": runtime_meta.get("backbone_config_verified"),
            "next_slice": config.next_steps.after_execute,
        }
    )
    return report


def _lf_ok(path: Path) -> bool:
    data = path.read_bytes()
    return bool(data) and not data.startswith(b"\xef\xbb\xbf") and b"\r" not in data and data.endswith(b"\n")


def validate_h2_independent_inference(
    *,
    project_root: Path,
    config_path: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    previous_heldout_sample_dir: Path,
    frozen_candidate_dir: Path,
    canonical_path: Path,
    inference_dir: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    root = project_root.resolve()
    parent = _validate_parent_state(
        root=root,
        config_path=config_path.resolve(),
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        development_package_dir=development_package_dir.resolve(),
        previous_heldout_sample_dir=previous_heldout_sample_dir.resolve(),
        frozen_candidate_dir=frozen_candidate_dir.resolve(),
        canonical_path=canonical_path.resolve(),
    )
    config = parent["config"]
    inference_dir = inference_dir.resolve()
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    actual_files = {path.name for path in inference_dir.iterdir() if path.is_file()}
    add("exact_file_layout", actual_files == REQUIRED_FILES, sorted(actual_files))
    if actual_files != REQUIRED_FILES:
        failed = sum(not ok for _, ok, _ in checks)
        return checks, {
            "report": REPORT_NAME,
            "validation_scope": "h2_independent_inference",
            "total_checks": len(checks),
            "required_failed_count": failed,
            "next_slice": "fix_h2_v03_independent_inference_evidence",
        }

    checksum_map = _parse_checksums(inference_dir / "checksums.txt")
    add("checksum_filename_set", set(checksum_map) == CHECKSUM_FILES, sorted(checksum_map))
    for name in sorted(CHECKSUM_FILES):
        add(f"checksum:{name}", checksum_map.get(name) == _sha256_file(inference_dir / name), name)
    for name in sorted(REQUIRED_FILES):
        add(f"lf:{name}", _lf_ok(inference_dir / name), name)

    manifest = H2IndependentInferenceManifest.model_validate(_read_json(inference_dir / "manifest.json"))
    summary = H2IndependentInferenceSummary.model_validate(_read_json(inference_dir / "summary.json"))
    raw_rows = tuple(ScientificEntityMentionEvidence.model_validate(row) for row in _read_jsonl(inference_dir / "upstream_raw_mentions.jsonl"))
    baseline_rows = tuple(ScientificEntityMentionEvidence.model_validate(row) for row in _read_jsonl(inference_dir / "baseline_mentions.jsonl"))
    cases = tuple(H2IndependentInferenceCase.model_validate(row) for row in _read_jsonl(inference_dir / "semantic_typer_cases.jsonl"))
    semantic_rows = tuple(SemanticTyperPrediction.model_validate(row) for row in _read_jsonl(inference_dir / "semantic_typer_predictions.jsonl"))
    h2_rows = tuple(H2IndependentPrediction.model_validate(row) for row in _read_jsonl(inference_dir / "h2_predictions.jsonl"))

    add("directory_matches_inference_id", inference_dir.name == manifest.inference_id, inference_dir.name)
    add("candidate_id_matches", manifest.candidate_id == config.candidate.candidate_id, manifest.candidate_id)
    add("candidate_fingerprint_matches", manifest.candidate_fingerprint_sha256 == config.candidate.candidate_fingerprint_sha256, manifest.candidate_fingerprint_sha256)
    add("sample_id_matches", manifest.sample_id == config.lineage.sample_id, manifest.sample_id)
    add("review_id_matches", manifest.review_id == config.lineage.review_id, manifest.review_id)
    add("inference_config_sha_matches", manifest.inference_config_sha256 == parent["inference_config_sha"], manifest.inference_config_sha256)
    add("acceptance_gate_sha_matches", manifest.acceptance_gate_config_sha256 == parent["gate_sha"], manifest.acceptance_gate_config_sha256)
    add("sample_manifest_sha_matches", manifest.sample_manifest_sha256 == parent["sample_manifest_sha"], manifest.sample_manifest_sha256)
    add("frozen_candidate_manifest_sha_matches", manifest.frozen_candidate_manifest_sha256 == parent["candidate_manifest_sha"], manifest.frozen_candidate_manifest_sha256)
    add("frozen_candidate_sha_matches", manifest.frozen_candidate_sha256 == parent["candidate_definition_sha"], manifest.frozen_candidate_sha256)
    add("reference_completion_sha_matches", manifest.reference_completion_manifest_sha256 == parent["reference_completion_sha"], manifest.reference_completion_manifest_sha256)
    add("reference_mentions_sha_matches", manifest.reference_mentions_sha256 == parent["reference_mentions_sha"], manifest.reference_mentions_sha256)
    add("semantic_config_sha_matches", manifest.parent_semantic_typer_config_sha256 == parent["semantic_config_sha"], manifest.parent_semantic_typer_config_sha256)
    add("runtime_config_sha_matches", manifest.upstream_runtime_config_sha256 == parent["runtime_sha"], manifest.upstream_runtime_config_sha256)
    add("baseline_policy_sha_matches", manifest.upstream_policy_config_sha256 == parent["policy_sha"], manifest.upstream_policy_config_sha256)

    payload_file_shas = {
        name: _sha256_file(inference_dir / name)
        for name in manifest.files
    }
    add("manifest_file_shas_match", payload_file_shas == manifest.files, len(payload_file_shas))

    add("raw_count_matches", len(raw_rows) == manifest.upstream_raw_mention_count == summary.upstream_raw_mention_count, len(raw_rows))
    add("baseline_count_matches", len(baseline_rows) == manifest.baseline_prediction_count == summary.baseline_prediction_count, len(baseline_rows))
    add("case_count_matches", len(cases) == manifest.semantic_typer_case_count == summary.semantic_typer_case_count, len(cases))
    add("semantic_prediction_count_matches", len(semantic_rows) == len(cases), len(semantic_rows))
    add("h2_prediction_count_matches", len(h2_rows) == len(cases), len(h2_rows))

    recomputed_baseline = _baseline_predictions(raw_rows, policy_config=parent["policy_config"])
    add(
        "baseline_recomputes_from_raw_with_frozen_policy",
        _jsonl_bytes(recomputed_baseline) == (inference_dir / "baseline_mentions.jsonl").read_bytes(),
        len(recomputed_baseline),
    )

    documents = _load_documents(sample_dir.resolve() / "canonical_documents.sample.jsonl", expected_count=48)
    recomputed_cases = _build_cases(
        sample_id=config.lineage.sample_id,
        documents=documents,
        baseline_rows=baseline_rows,
        semantic_config=parent["semantic_config"],
    )
    add("cases_recompute_without_reference", _jsonl_bytes(recomputed_cases) == (inference_dir / "semantic_typer_cases.jsonl").read_bytes(), len(recomputed_cases))
    forbidden_case_keys = {"reference_id", "reference_entity_type", "baseline_correct", "root_cause", "ambiguity_level", "reference_type_confirmed"}
    raw_case_payloads = _read_jsonl(inference_dir / "semantic_typer_cases.jsonl")
    add("case_schema_contains_no_reference_labels", all(not (forbidden_case_keys & set(row)) for row in raw_case_payloads), "")

    add("semantic_case_order_matches", [row.case_id for row in semantic_rows] == [row.case_id for row in cases], "")
    scored = sum(not row.used_baseline_fallback for row in semantic_rows)
    fallback = len(semantic_rows) - scored
    add("semantic_scored_count_matches", scored == manifest.semantic_typer_scored_count == summary.semantic_typer_scored_count, scored)
    add("semantic_fallback_count_matches", fallback == manifest.semantic_typer_fallback_count == summary.semantic_typer_fallback_count, fallback)
    expected_coverage = round(scored / len(cases), 6) if cases else 0.0
    add("typer_coverage_matches", summary.typer_coverage == expected_coverage, expected_coverage)

    recomputed_h2 = _apply_h2_policy(
        inference_id=manifest.inference_id,
        cases=cases,
        semantic_predictions=semantic_rows,
        baseline_type=config.execution.h2_baseline_type,
        semantic_typer_type=config.execution.h2_semantic_typer_type,
        threshold=config.execution.h2_threshold,
    )
    add("h2_predictions_recompute_from_frozen_policy", _jsonl_bytes(recomputed_h2) == (inference_dir / "h2_predictions.jsonl").read_bytes(), len(recomputed_h2))
    add("h2_override_count_matches", sum(row.h2_override_applied for row in h2_rows) == manifest.h2_override_count == summary.h2_override_count, manifest.h2_override_count)
    add("spans_are_frozen", all((case.canonical_id, case.source_field, case.source_text_sha256, case.char_start, case.char_end, case.surface_text) == (row.canonical_id, row.source_field, row.source_text_sha256, row.char_start, row.char_end, row.surface_text) for case, row in zip(cases, h2_rows)), "")

    recomputed_summary = _summary(
        inference_id=manifest.inference_id,
        raw_rows=raw_rows,
        baseline_rows=baseline_rows,
        cases=cases,
        semantic_rows=semantic_rows,
        h2_rows=h2_rows,
    )
    add("summary_recomputes_exactly", recomputed_summary == summary, "")

    safety_ok = (
        manifest.reference_frozen_before_inference is True
        and manifest.reference_labels_used_for_case_construction is False
        and manifest.reference_labels_used_as_model_features is False
        and manifest.upstream_model_inference_executed is True
        and manifest.semantic_typer_model_inference_executed is True
        and manifest.frozen_h2_policy_applied is True
        and manifest.threshold_tuning_executed is False
        and manifest.policy_revision_executed is False
        and manifest.span_mutated is False
        and manifest.evaluation_executed is False
        and manifest.acceptance_decision_made is False
        and manifest.canonical_truth_mutated is False
        and manifest.production_extractor_selected is False
        and manifest.full_corpus_build_authorized is False
        and manifest.publication_ready is False
    )
    add("safety_flags_fail_closed", safety_ok, "")
    add("next_slice_is_validation", manifest.next_slice == "validate_h2_v03_independent_inference_evidence", manifest.next_slice)

    failed = [name for name, ok, _ in checks if not ok]
    result = {
        "report": REPORT_NAME,
        "validation_scope": "h2_independent_inference",
        "inference_id": manifest.inference_id,
        "candidate_id": manifest.candidate_id,
        "candidate_fingerprint_sha256": manifest.candidate_fingerprint_sha256,
        "sample_id": manifest.sample_id,
        "review_id": manifest.review_id,
        "input_document_count": manifest.input_document_count,
        "upstream_raw_mention_count": manifest.upstream_raw_mention_count,
        "baseline_prediction_count": manifest.baseline_prediction_count,
        "semantic_typer_case_count": manifest.semantic_typer_case_count,
        "semantic_typer_scored_count": manifest.semantic_typer_scored_count,
        "semantic_typer_fallback_count": manifest.semantic_typer_fallback_count,
        "typer_coverage": summary.typer_coverage,
        "h2_override_count": manifest.h2_override_count,
        "evaluation_executed": manifest.evaluation_executed,
        "acceptance_decision_made": manifest.acceptance_decision_made,
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "next_slice": config.next_steps.after_validation if not failed else "fix_h2_v03_independent_inference_evidence",
    }
    return checks, result


__all__ = [
    "PROJECT_ROOT",
    "DEFAULT_CONFIG",
    "DEFAULT_CANONICAL",
    "REPORT_NAME",
    "REQUIRED_FILES",
    "plan_or_execute_h2_independent_inference",
    "validate_h2_independent_inference",
    "_apply_h2_policy",
    "_build_cases",
]
