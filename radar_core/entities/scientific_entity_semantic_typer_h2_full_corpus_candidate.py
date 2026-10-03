from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

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
from radar_core.contracts.scientific_entity_semantic_typer_h2_full_corpus_candidate import (
    H2FullCorpusCandidateConfig,
    H2FullCorpusCandidateError,
    H2FullCorpusCase,
    H2FullCorpusFinalMention,
    H2FullCorpusManifest,
    H2FullCorpusOverride,
    H2FullCorpusSummary,
    canonical_config_sha256,
    load_h2_full_corpus_candidate_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_authorization import (
    H2ProductionAuthorizationRecord,
    canonical_config_sha256 as authorization_config_sha256,
    load_h2_production_authorization_config,
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
from radar_core.entities.scientific_entity_semantic_typer_h2_production_authorization import (
    validate_h2_production_authorization,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_semantic_typer_h2_full_corpus_candidate_v0.3.yaml"
DEFAULT_CANONICAL = PROJECT_ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
REPORT_NAME = "scientific_entity_semantic_typer_h2_full_corpus_candidate_v03"
JSONL_FILES = (
    "upstream_raw_mentions.jsonl",
    "baseline_mentions.jsonl",
    "semantic_typer_cases.jsonl",
    "semantic_typer_predictions.jsonl",
    "h2_overrides.jsonl",
    "final_mentions.jsonl",
)
REQUIRED_FILES = (*JSONL_FILES, "summary.json", "manifest.json", "README.md", "checksums.txt")
CHECKSUM_FILES = tuple(name for name in REQUIRED_FILES if name != "checksums.txt")
SOURCE_FIELD_ORDER = {ScientificEntitySourceField.TITLE: 0, ScientificEntitySourceField.ABSTRACT: 1}


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _relative(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_id(prefix: str, parts: Sequence[str]) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _json_line(value: Any) -> str:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _json_bytes(value: Any) -> bytes:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _canonical_snapshot(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as handle:
        for raw in handle:
            digest.update(raw)
            if raw.strip():
                count += 1
    if count <= 0:
        raise H2FullCorpusCandidateError("Canonical snapshot is empty")
    return digest.hexdigest(), count


def _authorization_consumed(output_root: Path, authorization_id: str) -> tuple[bool, str | None]:
    if not output_root.is_dir():
        return False, None
    for child in sorted(output_root.iterdir()):
        manifest_path = child / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("authorization_id") == authorization_id:
            return True, child.name
    return False, None


def _threshold_policy(policy_config: Any):
    from radar_core.contracts.scientific_entity_gliner_calibration import ScientificEntityThresholdPolicy

    return ScientificEntityThresholdPolicy(
        default_threshold=policy_config.policy.default_threshold,
        source_field_thresholds=policy_config.policy.source_field_thresholds,
        entity_type_thresholds=policy_config.policy.entity_type_thresholds,
    )


def _validate_parent(
    *,
    root: Path,
    config_path: Path,
    authorization_dir: Path,
    decision_dir: Path,
    evaluation_dir: Path,
    inference_dir: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    previous_heldout_sample_dir: Path,
    frozen_candidate_dir: Path,
    canonical_path: Path,
) -> dict[str, Any]:
    config = load_h2_full_corpus_candidate_config(config_path)
    auth_config_path = _resolve(root, config.authorization.authorization_config_path)
    auth_config = load_h2_production_authorization_config(auth_config_path)
    auth_config_sha = authorization_config_sha256(auth_config)
    if auth_config_sha != config.authorization.authorization_config_sha256:
        raise H2FullCorpusCandidateError("Production authorization config SHA drifted")

    checks, auth_summary = validate_h2_production_authorization(
        project_root=root,
        config_path=auth_config_path,
        authorization_dir=authorization_dir,
        decision_dir=decision_dir,
        evaluation_dir=evaluation_dir,
        inference_dir=inference_dir,
        sample_dir=sample_dir,
        reference_dir=reference_dir,
        development_package_dir=development_package_dir,
        previous_heldout_sample_dir=previous_heldout_sample_dir,
        frozen_candidate_dir=frozen_candidate_dir,
        canonical_path=canonical_path,
    )
    if auth_summary.get("required_failed_count") != 0:
        raise H2FullCorpusCandidateError("Immutable production authorization validation failed")
    if auth_summary.get("total_checks") != config.authorization.expected_authorization_validation_total_checks:
        raise H2FullCorpusCandidateError("Production authorization validation check count drifted")
    if auth_summary.get("authorization_id") != config.authorization.authorization_id:
        raise H2FullCorpusCandidateError("Production authorization ID drifted")
    if auth_summary.get("full_corpus_candidate_build_authorized") is not True:
        raise H2FullCorpusCandidateError("Authorization does not permit candidate build")
    if auth_summary.get("production_latest_promotion_authorized") is not False:
        raise H2FullCorpusCandidateError("Authorization unexpectedly permits latest promotion")

    authorization = H2ProductionAuthorizationRecord.model_validate(
        json.loads((authorization_dir / "authorization.json").read_text(encoding="utf-8"))
    )
    if authorization.authorization_id != config.authorization.authorization_id:
        raise H2FullCorpusCandidateError("Authorization record ID drifted")
    if authorization.authorized_candidate_build_count != 1:
        raise H2FullCorpusCandidateError("Authorization is not exactly one candidate build")

    canonical_sha, canonical_count = _canonical_snapshot(canonical_path)
    if canonical_sha != config.canonical_snapshot.sha256 or canonical_sha != authorization.canonical_sha256:
        raise H2FullCorpusCandidateError("Canonical SHA-256 no longer matches immutable authorization")
    if canonical_count != config.canonical_snapshot.document_count or canonical_count != authorization.canonical_document_count:
        raise H2FullCorpusCandidateError("Canonical document count no longer matches immutable authorization")

    runtime_path = _resolve(root, config.frozen_runtime.runtime_config_path)
    runtime_config = load_gliner_config(runtime_path)
    runtime_sha = gliner_config_sha256(runtime_config)
    if runtime_sha != config.frozen_runtime.runtime_config_sha256:
        raise H2FullCorpusCandidateError("Frozen upstream runtime config SHA drifted")

    policy_path = _resolve(root, config.frozen_runtime.baseline_policy_config_path)
    policy_config = load_raw_floor_policy_config(policy_path)
    policy_sha = policy_config_sha256(policy_config)
    if policy_sha != config.frozen_runtime.baseline_policy_config_sha256:
        raise H2FullCorpusCandidateError("Frozen baseline policy config SHA drifted")

    semantic_path = _resolve(root, config.frozen_runtime.semantic_typer_config_path)
    semantic_config = load_semantic_typer_config(semantic_path)
    semantic_sha = semantic_typer_config_sha256(semantic_config)
    semantic_fp = semantic_typer_fingerprint(semantic_config)
    if semantic_sha != config.frozen_runtime.semantic_typer_config_sha256:
        raise H2FullCorpusCandidateError("Frozen semantic typer config SHA drifted")
    if semantic_fp != config.frozen_runtime.semantic_typer_fingerprint_sha256:
        raise H2FullCorpusCandidateError("Frozen semantic typer fingerprint drifted")

    return {
        "config": config,
        "authorization": authorization,
        "authorization_summary": auth_summary,
        "canonical_sha": canonical_sha,
        "canonical_count": canonical_count,
        "runtime_config": runtime_config,
        "runtime_sha": runtime_sha,
        "policy_config": policy_config,
        "policy_sha": policy_sha,
        "semantic_config": semantic_config,
        "semantic_sha": semantic_sha,
        "semantic_fp": semantic_fp,
    }


def _raw_extractor(root: Path, runtime_config: Any, backend: GLiNERBackend):
    environment_lock = _resolve(root, runtime_config.extractor.environment_lock_path)
    descriptor = build_gliner_extractor_descriptor(
        config=runtime_config,
        config_sha256=gliner_config_sha256(runtime_config),
        environment_sha256=normalized_text_sha256(environment_lock),
        code_revision=normalized_source_bundle_revision(root),
    )
    fingerprint = build_extractor_fingerprint(descriptor)
    adapter = ScientificEntityGLiNERAdapter(config=runtime_config, descriptor=descriptor, backend=backend)
    return descriptor, fingerprint, adapter


def _iter_raw_mentions_for_document(
    *,
    document: CanonicalDocument,
    adapter: ScientificEntityGLiNERAdapter,
    extractor_fingerprint: str,
    raw_build_id: str,
) -> tuple[ScientificEntityMentionEvidence, ...]:
    rows: list[ScientificEntityMentionEvidence] = []
    seen: set[str] = set()
    values = {
        ScientificEntitySourceField.TITLE: document.title,
        ScientificEntitySourceField.ABSTRACT: document.abstract,
    }
    for source_field in adapter.config.inference.source_fields:
        source_text = values[source_field]
        if source_text in (None, ""):
            continue
        result = adapter.extract(canonical_id=document.canonical_id, source_field=source_field, source_text=source_text)
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
            evidence_id = build_evidence_id(mention_id=mention_id, extractor_fingerprint=extractor_fingerprint)
            if evidence_id in seen:
                raise H2FullCorpusCandidateError("Duplicate raw evidence identity within document")
            seen.add(evidence_id)
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
                    extractor_fingerprint=extractor_fingerprint,
                    confidence_kind=ConfidenceKind.MODEL_SCORE,
                    confidence_score=round(candidate.score, 8),
                    calibration_id=None,
                )
            )
    rows.sort(key=lambda row: (SOURCE_FIELD_ORDER[row.source_field], row.char_start, row.char_end, row.entity_type.value, row.evidence_id))
    return tuple(rows)


def _case_for_method(*, authorization_id: str, row: ScientificEntityMentionEvidence, source_text: str, semantic_config: Any) -> H2FullCorpusCase:
    if row.entity_type != ScientificEntityType.METHOD or row.confidence_score is None:
        raise H2FullCorpusCandidateError("Semantic typer case requires scored baseline method mention")
    left = semantic_config.semantic_typing.context_left_chars
    right = semantic_config.semantic_typing.context_right_chars
    return H2FullCorpusCase(
        case_id=_stable_id("h2-prod-case", [authorization_id, row.evidence_id]),
        canonical_id=row.canonical_id,
        source_field=row.source_field,
        source_text_sha256=row.source_text_sha256,
        baseline_prediction_evidence_id=row.evidence_id,
        char_start=row.char_start,
        char_end=row.char_end,
        surface_text=row.surface_text,
        baseline_entity_type=ScientificEntityType.METHOD,
        baseline_confidence_score=row.confidence_score,
        left_context=source_text[max(0, row.char_start-left):row.char_start],
        right_context=source_text[row.char_end:min(len(source_text), row.char_end+right)],
    )


def _materialization_fingerprint(config: H2FullCorpusCandidateConfig, *, authorization_id: str, raw_extractor_fingerprint: str) -> str:
    payload = {
        "config_sha256": canonical_config_sha256(config),
        "authorization_id": authorization_id,
        "candidate_fingerprint_sha256": config.frozen_h2.candidate_fingerprint_sha256,
        "canonical_sha256": config.canonical_snapshot.sha256,
        "raw_extractor_fingerprint": raw_extractor_fingerprint,
        "semantic_typer_fingerprint_sha256": config.frozen_runtime.semantic_typer_fingerprint_sha256,
        "h2_threshold": config.frozen_h2.threshold,
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _final_row(
    *,
    build_id: str,
    baseline: ScientificEntityMentionEvidence,
    materialization_fingerprint: str,
    semantic_case: H2FullCorpusCase | None,
    semantic_prediction: SemanticTyperPrediction | None,
    override: bool,
) -> H2FullCorpusFinalMention:
    final_type = ScientificEntityType.MODEL if override else baseline.entity_type
    final_mention_id = build_mention_id(
        canonical_id=baseline.canonical_id,
        source_field=baseline.source_field,
        source_text_sha256=baseline.source_text_sha256,
        char_start=baseline.char_start,
        char_end=baseline.char_end,
        entity_type=final_type,
    )
    evidence_id = build_evidence_id(mention_id=final_mention_id, extractor_fingerprint=materialization_fingerprint)
    return H2FullCorpusFinalMention(
        build_id=build_id,
        candidate_evidence_id=evidence_id,
        final_mention_id=final_mention_id,
        canonical_id=baseline.canonical_id,
        source_field=baseline.source_field,
        source_text_sha256=baseline.source_text_sha256,
        char_start=baseline.char_start,
        char_end=baseline.char_end,
        surface_text=baseline.surface_text,
        baseline_prediction_evidence_id=baseline.evidence_id,
        baseline_entity_type=baseline.entity_type,
        baseline_confidence_score=baseline.confidence_score,
        semantic_typer_case_id=None if semantic_case is None else semantic_case.case_id,
        semantic_typer_predicted_entity_type=None if semantic_prediction is None else semantic_prediction.predicted_entity_type,
        semantic_typer_used_baseline_fallback=None if semantic_prediction is None else semantic_prediction.used_baseline_fallback,
        semantic_typer_score_margin=None if semantic_prediction is None else semantic_prediction.score_margin,
        h2_override_applied=override,
        final_entity_type=final_type,
        materialization_fingerprint_sha256=materialization_fingerprint,
    )


def _iter_canonical(path: Path) -> Iterator[CanonicalDocument]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                raise H2FullCorpusCandidateError(f"Blank canonical JSONL line at {line_number}")
            payload = json.loads(raw)
            yield CanonicalDocument.model_validate(payload)


def plan_or_execute_h2_full_corpus_candidate(
    *,
    project_root: Path,
    config_path: Path,
    authorization_dir: Path,
    decision_dir: Path,
    evaluation_dir: Path,
    inference_dir: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    previous_heldout_sample_dir: Path,
    frozen_candidate_dir: Path,
    canonical_path: Path,
    output_root: Path | None = None,
    build_id: str | None = None,
    execute: bool = False,
    allow_model_download: bool = False,
    model_cache_dir: Path | None = None,
    backend: GLiNERBackend | None = None,
    allow_test_backend: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    canonical_path = canonical_path.resolve()
    parent = _validate_parent(
        root=root,
        config_path=config_path.resolve(),
        authorization_dir=authorization_dir.resolve(),
        decision_dir=decision_dir.resolve(),
        evaluation_dir=evaluation_dir.resolve(),
        inference_dir=inference_dir.resolve(),
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        development_package_dir=development_package_dir.resolve(),
        previous_heldout_sample_dir=previous_heldout_sample_dir.resolve(),
        frozen_candidate_dir=frozen_candidate_dir.resolve(),
        canonical_path=canonical_path,
    )
    config: H2FullCorpusCandidateConfig = parent["config"]
    now = generated_at_utc or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(now):
        raise H2FullCorpusCandidateError("generated_at_utc must be timezone-aware UTC")
    selected_id = build_id or f"{config.execution.build_id_prefix}-{now.strftime('%Y%m%dT%H%M%S%fZ')}"
    selected_root = output_root.resolve() if output_root is not None else _resolve(root, config.execution.output_root)
    output_dir = selected_root / selected_id
    consumed, consumed_build = _authorization_consumed(selected_root, config.authorization.authorization_id)
    if execute and consumed:
        raise H2FullCorpusCandidateError(f"Authorization already consumed by successful build: {consumed_build}")
    if execute and output_dir.exists():
        raise FileExistsError(f"Immutable candidate output already exists: {output_dir}")
    if backend is not None and not allow_test_backend:
        raise H2FullCorpusCandidateError("Injected backend is test-only")

    report: dict[str, Any] = {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "authorization_id": config.authorization.authorization_id,
        "authorization_validation_required_failed_count": parent["authorization_summary"]["required_failed_count"],
        "authorization_validation_total_checks": parent["authorization_summary"]["total_checks"],
        "candidate_id": config.frozen_h2.candidate_id,
        "candidate_fingerprint_sha256": config.frozen_h2.candidate_fingerprint_sha256,
        "canonical_sha256": parent["canonical_sha"],
        "canonical_document_count": parent["canonical_count"],
        "canonical_snapshot_matches_authorization": True,
        "authorization_already_consumed": consumed,
        "consumed_by_build_id": consumed_build,
        "plan_runs_model_inference": False,
        "plan_writes_candidate": False,
        "candidate_build_executed": False,
        "full_corpus_model_inference_executed": False,
        "human_reference_mentions_read": False,
        "threshold_tuning_executed": False,
        "policy_revision_executed": False,
        "canonical_truth_mutated": False,
        "production_latest_promotion_authorized": False,
        "build_id": selected_id,
        "output_dir": str(output_dir).replace("\\", "/"),
        "next_slice": config.next_steps.after_plan,
    }
    if not execute:
        return report

    selected_backend = backend
    runtime_meta: dict[str, Any] = {"backend_injected_for_test": backend is not None}
    if selected_backend is None:
        loaded = load_native_gliner_backend(
            config=parent["runtime_config"],
            allow_model_download=allow_model_download,
            cache_dir=model_cache_dir,
        )
        selected_backend = loaded.backend
        runtime_meta.update({
            "model_artifact_verified": loaded.model_artifact_verified,
            "backbone_config_verified": loaded.backbone_config_verified,
            "model_weights_downloaded": loaded.model_weights_downloaded,
            "backbone_config_downloaded": loaded.backbone_config_downloaded,
        })

    _, raw_fp, adapter = _raw_extractor(root, parent["runtime_config"], selected_backend)
    materialization_fp = _materialization_fingerprint(
        config,
        authorization_id=config.authorization.authorization_id,
        raw_extractor_fingerprint=raw_fp,
    )
    raw_build_id = selected_id + "-upstream-raw-v02c"
    policy = _threshold_policy(parent["policy_config"])

    selected_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{selected_id}.", dir=selected_root))
    handles = {name: (staging / name).open("w", encoding="utf-8", newline="\n") for name in JSONL_FILES}
    raw_count = baseline_count = method_count = scored = fallback = override_count = final_count = 0
    baseline_types: Counter[str] = Counter()
    final_types: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    started = time.perf_counter()
    processed_docs = 0
    try:
        for processed_docs, document in enumerate(_iter_canonical(canonical_path), start=1):
            source_values = {
                ScientificEntitySourceField.TITLE: document.title,
                ScientificEntitySourceField.ABSTRACT: document.abstract,
            }
            raw_rows = _iter_raw_mentions_for_document(
                document=document,
                adapter=adapter,
                extractor_fingerprint=raw_fp,
                raw_build_id=raw_build_id,
            )
            for row in raw_rows:
                handles["upstream_raw_mentions.jsonl"].write(_json_line(row))
            raw_count += len(raw_rows)
            baseline_rows = filter_predictions(
                raw_rows,
                policy=policy,
                input_threshold=parent["policy_config"].policy.input_threshold,
            )
            for baseline in baseline_rows:
                handles["baseline_mentions.jsonl"].write(_json_line(baseline))
                baseline_count += 1
                baseline_types[baseline.entity_type.value] += 1
                source_counts[baseline.source_field.value] += 1
                case = None
                semantic = None
                override = False
                if baseline.entity_type == ScientificEntityType.METHOD:
                    method_count += 1
                    source_text = source_values[baseline.source_field]
                    if source_text in (None, "") or sha256_text(source_text) != baseline.source_text_sha256:
                        raise H2FullCorpusCandidateError("Baseline source text drifted during full-corpus build")
                    case = _case_for_method(
                        authorization_id=config.authorization.authorization_id,
                        row=baseline,
                        source_text=source_text,
                        semantic_config=parent["semantic_config"],
                    )
                    handles["semantic_typer_cases.jsonl"].write(_json_line(case))
                    semantic = type_semantic_case(config=parent["semantic_config"], case=case, backend=selected_backend)
                    handles["semantic_typer_predictions.jsonl"].write(_json_line(semantic))
                    if semantic.used_baseline_fallback:
                        fallback += 1
                    else:
                        scored += 1
                    override = (
                        not semantic.used_baseline_fallback
                        and semantic.predicted_entity_type == ScientificEntityType.MODEL
                        and semantic.score_margin is not None
                        and semantic.score_margin >= config.frozen_h2.threshold
                    )
                    if override:
                        override_row = H2FullCorpusOverride(
                            build_id=selected_id,
                            case_id=case.case_id,
                            baseline_prediction_evidence_id=baseline.evidence_id,
                            canonical_id=baseline.canonical_id,
                            source_field=baseline.source_field,
                            source_text_sha256=baseline.source_text_sha256,
                            char_start=baseline.char_start,
                            char_end=baseline.char_end,
                            surface_text=baseline.surface_text,
                            baseline_entity_type=ScientificEntityType.METHOD,
                            semantic_typer_entity_type=ScientificEntityType.MODEL,
                            semantic_typer_score_margin=semantic.score_margin,
                            final_entity_type=ScientificEntityType.MODEL,
                        )
                        handles["h2_overrides.jsonl"].write(_json_line(override_row))
                        override_count += 1
                final = _final_row(
                    build_id=selected_id,
                    baseline=baseline,
                    materialization_fingerprint=materialization_fp,
                    semantic_case=case,
                    semantic_prediction=semantic,
                    override=override,
                )
                handles["final_mentions.jsonl"].write(_json_line(final))
                final_count += 1
                final_types[final.final_entity_type.value] += 1
            if config.execution.progress_every_documents and processed_docs % config.execution.progress_every_documents == 0:
                print(f"[PROGRESS] documents={processed_docs}/{parent['canonical_count']} baseline_mentions={baseline_count} method_cases={method_count} overrides={override_count}")
        if processed_docs != parent["canonical_count"]:
            raise H2FullCorpusCandidateError("Processed canonical document count drifted")
    except Exception:
        for handle in handles.values():
            handle.close()
        shutil.rmtree(staging, ignore_errors=True)
        raise
    else:
        for handle in handles.values():
            handle.close()

    duration = time.perf_counter() - started
    summary = H2FullCorpusSummary(
        build_id=selected_id,
        input_document_count=processed_docs,
        upstream_raw_mention_count=raw_count,
        baseline_prediction_count=baseline_count,
        baseline_method_count=method_count,
        semantic_typer_case_count=method_count,
        semantic_typer_scored_count=scored,
        semantic_typer_fallback_count=fallback,
        typer_coverage_over_method_cases=round(scored / method_count, 6) if method_count else 0.0,
        h2_override_count=override_count,
        final_mention_count=final_count,
        baseline_count_by_type={kind.value: baseline_types[kind.value] for kind in ScientificEntityType},
        final_count_by_type={kind.value: final_types[kind.value] for kind in ScientificEntityType},
        source_field_counts={field.value: source_counts[field.value] for field in ScientificEntitySourceField},
    )
    (staging / "summary.json").write_bytes(_json_bytes(summary))
    (staging / "README.md").write_text(
        "# H2 v0.3 full-corpus candidate materialization\n\n"
        f"Build ID: `{selected_id}`\n\n"
        f"Authorization: `{config.authorization.authorization_id}`\n\n"
        f"Canonical snapshot: `{config.canonical_snapshot.sha256}` / `{config.canonical_snapshot.document_count}` documents.\n\n"
        "This is an immutable derived candidate, not production latest. The frozen v0.2c baseline is reproduced over the exact authorized canonical snapshot. "
        "The semantic typer is run only on baseline `method` mentions because H2 can only change `method -> model`; all non-method baseline mentions are preserved without semantic inference. "
        "No human held-out labels are read. Validation and any promotion are separate later slices.\n",
        encoding="utf-8",
        newline="\n",
    )
    file_shas = {name: _sha256_file(staging / name) for name in (*JSONL_FILES, "summary.json", "README.md")}
    manifest = H2FullCorpusManifest(
        build_id=selected_id,
        authorization_id=config.authorization.authorization_id,
        candidate_id=config.frozen_h2.candidate_id,
        candidate_fingerprint_sha256=config.frozen_h2.candidate_fingerprint_sha256,
        materialization_config_sha256=canonical_config_sha256(config),
        materialization_fingerprint_sha256=materialization_fp,
        canonical_path=_relative(root, canonical_path),
        canonical_sha256=parent["canonical_sha"],
        canonical_document_count=parent["canonical_count"],
        upstream_runtime_config_sha256=parent["runtime_sha"],
        baseline_policy_config_sha256=parent["policy_sha"],
        semantic_typer_config_sha256=parent["semantic_sha"],
        semantic_typer_fingerprint_sha256=parent["semantic_fp"],
        h2_threshold=config.frozen_h2.threshold,
        upstream_raw_mention_count=raw_count,
        baseline_prediction_count=baseline_count,
        semantic_typer_case_count=method_count,
        semantic_typer_scored_count=scored,
        semantic_typer_fallback_count=fallback,
        h2_override_count=override_count,
        final_mention_count=final_count,
        files=file_shas,
        exact_authorized_canonical_snapshot_verified=True,
        authorization_validated_before_model_load=True,
        reference_labels_used=False,
        threshold_tuning_executed=False,
        policy_revision_executed=False,
        span_mutated=False,
        canonical_truth_mutated=False,
        production_latest_promotion_authorized=False,
        latest_overwrite_allowed=False,
        publication_ready=False,
        candidate_validation_required_before_promotion=True,
        next_slice=config.next_steps.after_execute,
    )
    (staging / "manifest.json").write_bytes(_json_bytes(manifest))
    checksum_names = sorted(name for name in REQUIRED_FILES if name != "checksums.txt")
    (staging / "checksums.txt").write_text(
        "".join(f"{_sha256_file(staging / name)}  {name}\n" for name in checksum_names),
        encoding="utf-8",
        newline="\n",
    )
    if output_dir.exists():
        shutil.rmtree(staging, ignore_errors=True)
        raise FileExistsError(f"Immutable candidate output already exists: {output_dir}")
    staging.rename(output_dir)

    report.update({
        "phase_complete": True,
        "authorization_already_consumed": True,
        "consumed_by_build_id": selected_id,
        "candidate_build_executed": True,
        "full_corpus_model_inference_executed": True,
        "upstream_raw_mention_count": raw_count,
        "baseline_prediction_count": baseline_count,
        "baseline_method_count": method_count,
        "semantic_typer_scored_count": scored,
        "semantic_typer_fallback_count": fallback,
        "typer_coverage_over_method_cases": summary.typer_coverage_over_method_cases,
        "h2_override_count": override_count,
        "final_mention_count": final_count,
        "materialization_fingerprint_sha256": materialization_fp,
        "duration_seconds": round(duration, 6),
        "model_artifact_verified": runtime_meta.get("model_artifact_verified"),
        "backbone_config_verified": runtime_meta.get("backbone_config_verified"),
        "next_slice": config.next_steps.after_execute,
    })
    return report


def validate_h2_full_corpus_candidate(
    *,
    project_root: Path,
    config_path: Path,
    candidate_dir: Path,
    authorization_dir: Path,
    decision_dir: Path,
    evaluation_dir: Path,
    inference_dir: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    previous_heldout_sample_dir: Path,
    frozen_candidate_dir: Path,
    canonical_path: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    root = project_root.resolve()
    parent = _validate_parent(
        root=root,
        config_path=config_path.resolve(),
        authorization_dir=authorization_dir.resolve(),
        decision_dir=decision_dir.resolve(),
        evaluation_dir=evaluation_dir.resolve(),
        inference_dir=inference_dir.resolve(),
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        development_package_dir=development_package_dir.resolve(),
        previous_heldout_sample_dir=previous_heldout_sample_dir.resolve(),
        frozen_candidate_dir=frozen_candidate_dir.resolve(),
        canonical_path=canonical_path.resolve(),
    )
    config = parent["config"]
    candidate_dir = candidate_dir.resolve()
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    add("candidate_directory_exists", candidate_dir.is_dir(), candidate_dir)
    if not candidate_dir.is_dir():
        return checks, {"report": REPORT_NAME, "total_checks": len(checks), "required_failed_count": 1, "next_slice": "fix_h2_full_corpus_candidate_materialization"}
    actual = {path.name for path in candidate_dir.iterdir() if path.is_file()}
    add("exact_file_layout", actual == set(REQUIRED_FILES), sorted(actual))
    checksum_map: dict[str, str] = {}
    for line in (candidate_dir / "checksums.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split("  ", 1)
            checksum_map[name] = digest
    add("checksum_set_exact", set(checksum_map) == set(CHECKSUM_FILES), sorted(checksum_map))
    for name in CHECKSUM_FILES:
        add(f"checksum:{name}", checksum_map.get(name) == _sha256_file(candidate_dir / name), name)
    for name in REQUIRED_FILES:
        data = (candidate_dir / name).read_bytes()
        add(f"lf:{name}", b"\r" not in data, name)

    manifest = H2FullCorpusManifest.model_validate(json.loads((candidate_dir / "manifest.json").read_text(encoding="utf-8")))
    summary = H2FullCorpusSummary.model_validate(json.loads((candidate_dir / "summary.json").read_text(encoding="utf-8")))
    add("directory_matches_build_id", candidate_dir.name == manifest.build_id, manifest.build_id)
    add("authorization_id_matches", manifest.authorization_id == config.authorization.authorization_id, manifest.authorization_id)
    add("candidate_identity_matches", manifest.candidate_id == config.frozen_h2.candidate_id and manifest.candidate_fingerprint_sha256 == config.frozen_h2.candidate_fingerprint_sha256)
    add("canonical_snapshot_matches", manifest.canonical_sha256 == parent["canonical_sha"] and manifest.canonical_document_count == parent["canonical_count"])
    add("config_sha_matches", manifest.materialization_config_sha256 == canonical_config_sha256(config))
    add("runtime_sha_matches", manifest.upstream_runtime_config_sha256 == parent["runtime_sha"])
    add("policy_sha_matches", manifest.baseline_policy_config_sha256 == parent["policy_sha"])
    add("semantic_sha_matches", manifest.semantic_typer_config_sha256 == parent["semantic_sha"] and manifest.semantic_typer_fingerprint_sha256 == parent["semantic_fp"])
    add("safety_flags", all((manifest.reference_labels_used is False, manifest.threshold_tuning_executed is False, manifest.policy_revision_executed is False, manifest.span_mutated is False, manifest.canonical_truth_mutated is False, manifest.production_latest_promotion_authorized is False, manifest.latest_overwrite_allowed is False, manifest.publication_ready is False)))

    def read_rows(name: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with (candidate_dir / name).open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    raise H2FullCorpusCandidateError(f"Blank JSONL line {name}:{line_number}")
                rows.append(json.loads(line))
        return rows

    raw_payloads = read_rows("upstream_raw_mentions.jsonl")
    baseline_payloads = read_rows("baseline_mentions.jsonl")
    case_payloads = read_rows("semantic_typer_cases.jsonl")
    prediction_payloads = read_rows("semantic_typer_predictions.jsonl")
    override_payloads = read_rows("h2_overrides.jsonl")
    final_payloads = read_rows("final_mentions.jsonl")
    raw_rows = tuple(ScientificEntityMentionEvidence.model_validate(row) for row in raw_payloads)
    baseline_rows = tuple(ScientificEntityMentionEvidence.model_validate(row) for row in baseline_payloads)
    cases = tuple(H2FullCorpusCase.model_validate(row) for row in case_payloads)
    predictions = tuple(SemanticTyperPrediction.model_validate(row) for row in prediction_payloads)
    overrides = tuple(H2FullCorpusOverride.model_validate(row) for row in override_payloads)
    finals = tuple(H2FullCorpusFinalMention.model_validate(row) for row in final_payloads)

    recomputed_baseline = filter_predictions(raw_rows, policy=_threshold_policy(parent["policy_config"]), input_threshold=parent["policy_config"].policy.input_threshold)
    add("baseline_recomputes_from_raw", [row.model_dump(mode="json") for row in recomputed_baseline] == [row.model_dump(mode="json") for row in baseline_rows], len(baseline_rows))
    method_rows = [row for row in baseline_rows if row.entity_type == ScientificEntityType.METHOD]
    add("semantic_case_scope_is_exactly_baseline_methods", len(cases) == len(method_rows) == summary.baseline_method_count)
    add("semantic_prediction_count_matches_cases", len(predictions) == len(cases))
    add("semantic_case_prediction_order_matches", [row.case_id for row in predictions] == [row.case_id for row in cases])
    add("final_count_equals_baseline_count", len(finals) == len(baseline_rows) == summary.final_mention_count)
    add("manifest_counts_match", all((manifest.upstream_raw_mention_count == len(raw_rows), manifest.baseline_prediction_count == len(baseline_rows), manifest.semantic_typer_case_count == len(cases), manifest.h2_override_count == len(overrides), manifest.final_mention_count == len(finals))))

    pred_by_case = {row.case_id: row for row in predictions}
    case_by_evidence = {row.baseline_prediction_evidence_id: row for row in cases}
    override_by_evidence = {row.baseline_prediction_evidence_id: row for row in overrides}
    final_by_evidence = {row.baseline_prediction_evidence_id: row for row in finals}
    add("unique_case_ids", len(pred_by_case) == len(predictions))
    add("unique_final_lineage", len(final_by_evidence) == len(finals))
    add("unique_override_lineage", len(override_by_evidence) == len(overrides))

    semantics_ok = True
    for baseline in baseline_rows:
        final = final_by_evidence.get(baseline.evidence_id)
        if final is None:
            semantics_ok = False
            break
        if (final.canonical_id, final.source_field, final.source_text_sha256, final.char_start, final.char_end, final.surface_text) != (baseline.canonical_id, baseline.source_field, baseline.source_text_sha256, baseline.char_start, baseline.char_end, baseline.surface_text):
            semantics_ok = False
            break
        if baseline.entity_type != ScientificEntityType.METHOD:
            if final.final_entity_type != baseline.entity_type or final.h2_override_applied:
                semantics_ok = False
                break
            continue
        case = case_by_evidence.get(baseline.evidence_id)
        pred = None if case is None else pred_by_case.get(case.case_id)
        if case is None or pred is None:
            semantics_ok = False
            break
        expected_override = (not pred.used_baseline_fallback and pred.predicted_entity_type == ScientificEntityType.MODEL and pred.score_margin is not None and pred.score_margin >= config.frozen_h2.threshold)
        if final.h2_override_applied != expected_override:
            semantics_ok = False
            break
        if final.final_entity_type != (ScientificEntityType.MODEL if expected_override else ScientificEntityType.METHOD):
            semantics_ok = False
            break
        if expected_override and baseline.evidence_id not in override_by_evidence:
            semantics_ok = False
            break
        if not expected_override and baseline.evidence_id in override_by_evidence:
            semantics_ok = False
            break
    add("h2_semantics_recompute_from_frozen_policy", semantics_ok)

    docs_by_id = {doc.canonical_id: doc for doc in _iter_canonical(canonical_path.resolve())}
    spans_ok = True
    for final in finals:
        doc = docs_by_id.get(final.canonical_id)
        if doc is None:
            spans_ok = False
            break
        text = doc.title if final.source_field == ScientificEntitySourceField.TITLE else doc.abstract
        if text in (None, "") or sha256_text(text) != final.source_text_sha256 or text[final.char_start:final.char_end] != final.surface_text:
            spans_ok = False
            break
    add("all_final_spans_match_authorized_canonical", spans_ok)

    failed = [name for name, ok, _ in checks if not ok]
    validation_summary = {
        "report": REPORT_NAME,
        "validation_scope": "h2_full_corpus_candidate_materialization",
        "build_id": manifest.build_id,
        "authorization_id": manifest.authorization_id,
        "canonical_document_count": manifest.canonical_document_count,
        "baseline_prediction_count": len(baseline_rows),
        "semantic_typer_case_count": len(cases),
        "h2_override_count": len(overrides),
        "final_mention_count": len(finals),
        "candidate_build_validated": not failed,
        "production_latest_promotion_authorized": False,
        "canonical_truth_mutated": False,
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "next_slice": config.next_steps.after_validation if not failed else "fix_h2_full_corpus_candidate_materialization",
    }
    return checks, validation_summary


__all__ = [
    "PROJECT_ROOT",
    "DEFAULT_CONFIG",
    "DEFAULT_CANONICAL",
    "REPORT_NAME",
    "REQUIRED_FILES",
    "plan_or_execute_h2_full_corpus_candidate",
    "validate_h2_full_corpus_candidate",
]
