from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from radar_core.contracts.scientific_entity_evidence import ScientificEntityType
from radar_core.contracts.scientific_entity_semantic_typer_h2_full_corpus_candidate import (
    H2FullCorpusFinalMention,
    H2FullCorpusManifest,
    H2FullCorpusSummary,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit import (
    H2ProductionAuditCase,
    H2ProductionAuditManifest,
    canonical_config_sha256 as audit_config_sha256,
    load_h2_production_audit_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit_evaluation import (
    AUDIT_CONFIG_CANONICAL_SHA256,
    AUDIT_ID,
    CANDIDATE_BUILD_ID,
    CANDIDATE_FINGERPRINT,
    CANDIDATE_ID,
    CANONICAL_SHA256,
    EVALUATION_ID,
    MATERIALIZATION_FINGERPRINT,
    REFERENCE_CONFIG_CANONICAL_SHA256,
    REFERENCE_ID,
    H2ProductionAuditEvaluationCase,
    H2ProductionAuditEvaluationConfig,
    H2ProductionAuditEvaluationError,
    H2ProductionAuditEvaluationManifest,
    H2ProductionAuditEvaluationSummary,
    H2ProductionAuditGateResult,
    H2ProductionAuditGateResults,
    H2ProductionAuditStratumMetrics,
    canonical_config_sha256,
    load_h2_production_audit_evaluation_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit_reference import (
    H2ProductionAuditReferenceManifest,
    H2ProductionAuditReferenceSummary,
    canonical_config_sha256 as reference_config_sha256,
    load_h2_production_audit_reference_config,
)
from radar_core.entities.scientific_entity_semantic_typer_h2_production_audit import (
    _select_final_rows,
    _stable_case_id,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_audit_evaluation_v0.3.yaml"
REPORT_NAME = "scientific_entity_semantic_typer_h2_production_audit_evaluation_v03"
OUTPUT_FILES = ("README.md", "case_evaluations.jsonl", "gate_results.json", "manifest.json", "summary.json", "checksums.txt")
CHECKSUM_FILES = tuple(name for name in OUTPUT_FILES if name != "checksums.txt")
AUDIT_REQUIRED = ("audit_cases.jsonl", "manifest.json", "checksums.txt")
REFERENCE_REQUIRED = ("reference_annotations.jsonl", "annotation_summary.json", "manifest.json", "checksums.txt")
CANDIDATE_REQUIRED = ("final_mentions.jsonl", "manifest.json", "summary.json", "checksums.txt")
USABLE_STATUSES = {"valid_entity_span", "boundary_issue"}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(value: Any) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _jsonl_bytes(rows: Sequence[Any]) -> bytes:
    chunks: list[str] = []
    for row in rows:
        value = row.model_dump(mode="json") if hasattr(row, "model_dump") else row
        chunks.append(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    return "".join(chunks).encode("utf-8")


def _parse_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        if name in result:
            raise H2ProductionAuditEvaluationError(f"Duplicate checksum entry: {name}")
        result[name] = digest
    return result


def _lf_ok(path: Path) -> bool:
    return b"\r" not in path.read_bytes()


def _require_files(directory: Path, names: Sequence[str], label: str) -> None:
    if not directory.is_dir():
        raise H2ProductionAuditEvaluationError(f"{label} directory does not exist: {directory}")
    missing = [name for name in names if not (directory / name).is_file()]
    if missing:
        raise H2ProductionAuditEvaluationError(f"{label} missing files: {missing}")


def _validate_configs(
    config: H2ProductionAuditEvaluationConfig,
    audit_config_path: Path,
    reference_config_path: Path,
) -> tuple[Any, Any]:
    audit_config = load_h2_production_audit_config(audit_config_path)
    if audit_config_sha256(audit_config) != AUDIT_CONFIG_CANONICAL_SHA256:
        raise H2ProductionAuditEvaluationError("Audit config canonical SHA-256 drifted")
    reference_config = load_h2_production_audit_reference_config(reference_config_path)
    if reference_config_sha256(reference_config) != REFERENCE_CONFIG_CANONICAL_SHA256:
        raise H2ProductionAuditEvaluationError("Reference-freeze config canonical SHA-256 drifted")
    gates = config.promotion_gates
    parent_gates = audit_config.promotion_gates
    comparisons = (
        gates.max_overall_uncertain_rate == parent_gates.max_overall_uncertain_rate,
        gates.max_overall_not_entity_rate == parent_gates.max_overall_not_entity_rate,
        gates.min_override_usable_count == parent_gates.min_override_usable_count,
        gates.min_override_reference_model_rate == parent_gates.min_override_reference_model_rate,
        gates.max_override_reference_method_rate == parent_gates.max_override_reference_method_rate,
        gates.min_override_net_model_minus_method_rate == parent_gates.min_override_net_model_minus_method_rate,
        gates.min_preserved_usable_count == parent_gates.min_preserved_usable_count,
        gates.min_preserved_reference_method_rate == parent_gates.min_preserved_reference_method_rate,
        gates.max_preserved_reference_model_rate == parent_gates.max_preserved_reference_model_rate,
        gates.min_fallback_usable_count == parent_gates.min_fallback_usable_count,
        gates.max_fallback_unresolved_or_not_entity_rate == parent_gates.max_fallback_unresolved_or_not_entity_rate,
    )
    if not all(comparisons):
        raise H2ProductionAuditEvaluationError("Promotion gates drifted from preregistered audit config")
    return audit_config, reference_config


def _validate_audit_static(audit_dir: Path) -> tuple[H2ProductionAuditManifest, list[H2ProductionAuditCase]]:
    _require_files(audit_dir, AUDIT_REQUIRED, "Audit sample")
    checksums = _parse_checksums(audit_dir / "checksums.txt")
    for name in ("audit_cases.jsonl", "manifest.json"):
        if checksums.get(name) != _sha256_file(audit_dir / name):
            raise H2ProductionAuditEvaluationError(f"Audit sample checksum mismatch: {name}")
    manifest = H2ProductionAuditManifest.model_validate(json.loads((audit_dir / "manifest.json").read_text(encoding="utf-8")))
    if manifest.audit_id != AUDIT_ID or manifest.candidate_build_id != CANDIDATE_BUILD_ID:
        raise H2ProductionAuditEvaluationError("Audit sample lineage mismatch")
    if manifest.candidate_fingerprint_sha256 != CANDIDATE_FINGERPRINT or manifest.materialization_fingerprint_sha256 != MATERIALIZATION_FINGERPRINT:
        raise H2ProductionAuditEvaluationError("Audit sample candidate fingerprint mismatch")
    if manifest.canonical_sha256 != CANONICAL_SHA256 or manifest.canonical_document_count != 61075:
        raise H2ProductionAuditEvaluationError("Audit sample canonical lineage mismatch")
    if not manifest.prediction_blind or manifest.audit_case_count != 240:
        raise H2ProductionAuditEvaluationError("Audit sample blindness/count contract drifted")
    rows = [H2ProductionAuditCase.model_validate(json.loads(line)) for line in (audit_dir / "audit_cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 240 or len({row.audit_case_id for row in rows}) != 240:
        raise H2ProductionAuditEvaluationError("Audit sample row count/identity drifted")
    return manifest, rows


def _validate_reference_static(reference_dir: Path) -> tuple[H2ProductionAuditReferenceManifest, H2ProductionAuditReferenceSummary, list[Any]]:
    _require_files(reference_dir, REFERENCE_REQUIRED, "Frozen reference")
    names = sorted(path.name for path in reference_dir.iterdir() if path.is_file())
    expected = sorted(["README.md", "annotation_summary.json", "checksums.txt", "manifest.json", "reference_annotations.jsonl"])
    if names != expected:
        raise H2ProductionAuditEvaluationError(f"Frozen reference exact layout drifted: {names}")
    checksums = _parse_checksums(reference_dir / "checksums.txt")
    for name in ("README.md", "annotation_summary.json", "manifest.json", "reference_annotations.jsonl"):
        if checksums.get(name) != _sha256_file(reference_dir / name):
            raise H2ProductionAuditEvaluationError(f"Frozen reference checksum mismatch: {name}")
    manifest = H2ProductionAuditReferenceManifest.model_validate(json.loads((reference_dir / "manifest.json").read_text(encoding="utf-8")))
    summary = H2ProductionAuditReferenceSummary.model_validate(json.loads((reference_dir / "annotation_summary.json").read_text(encoding="utf-8")))
    if not manifest.reference_frozen or not manifest.prediction_blind:
        raise H2ProductionAuditEvaluationError("Reference must be frozen while still prediction-blind")
    if manifest.candidate_prediction_files_read or manifest.sampled_strata_reconstructed or manifest.unblinding_executed or manifest.promotion_gates_evaluated:
        raise H2ProductionAuditEvaluationError("Reference package was not frozen before unblinding")
    if manifest.reference_id != REFERENCE_ID or manifest.audit_id != AUDIT_ID or summary.reference_id != REFERENCE_ID:
        raise H2ProductionAuditEvaluationError("Reference lineage mismatch")
    from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit import H2ProductionAuditAnnotation
    rows = [H2ProductionAuditAnnotation.model_validate(json.loads(line)) for line in (reference_dir / "reference_annotations.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 240 or not all(row.annotation_complete for row in rows):
        raise H2ProductionAuditEvaluationError("Frozen reference must contain 240 complete rows")
    return manifest, summary, rows


def _validate_candidate_static(candidate_dir: Path, *, read_final_mentions: bool) -> tuple[H2FullCorpusManifest, H2FullCorpusSummary, str]:
    _require_files(candidate_dir, CANDIDATE_REQUIRED, "Full-corpus candidate")
    checksums = _parse_checksums(candidate_dir / "checksums.txt")
    for name in ("manifest.json", "summary.json"):
        if checksums.get(name) != _sha256_file(candidate_dir / name):
            raise H2ProductionAuditEvaluationError(f"Candidate checksum mismatch: {name}")
    manifest = H2FullCorpusManifest.model_validate(json.loads((candidate_dir / "manifest.json").read_text(encoding="utf-8")))
    summary = H2FullCorpusSummary.model_validate(json.loads((candidate_dir / "summary.json").read_text(encoding="utf-8")))
    if manifest.build_id != CANDIDATE_BUILD_ID or manifest.candidate_id != CANDIDATE_ID:
        raise H2ProductionAuditEvaluationError("Candidate identity mismatch")
    if manifest.candidate_fingerprint_sha256 != CANDIDATE_FINGERPRINT or manifest.materialization_fingerprint_sha256 != MATERIALIZATION_FINGERPRINT:
        raise H2ProductionAuditEvaluationError("Candidate fingerprint mismatch")
    if manifest.canonical_sha256 != CANONICAL_SHA256 or manifest.canonical_document_count != 61075:
        raise H2ProductionAuditEvaluationError("Candidate canonical lineage mismatch")
    if manifest.baseline_prediction_count != 846264 or manifest.semantic_typer_case_count != 260200 or manifest.h2_override_count != 33469 or manifest.final_mention_count != 846264:
        raise H2ProductionAuditEvaluationError("Candidate frozen counts mismatch")
    if summary.baseline_prediction_count != 846264 or summary.baseline_method_count != 260200 or summary.h2_override_count != 33469 or summary.final_mention_count != 846264:
        raise H2ProductionAuditEvaluationError("Candidate summary frozen counts mismatch")
    expected_final_sha = checksums.get("final_mentions.jsonl")
    if expected_final_sha is None:
        raise H2ProductionAuditEvaluationError("Candidate checksums omit final_mentions.jsonl")
    if read_final_mentions and _sha256_file(candidate_dir / "final_mentions.jsonl") != expected_final_sha:
        raise H2ProductionAuditEvaluationError("Candidate checksum mismatch: final_mentions.jsonl")
    return manifest, summary, expected_final_sha


def _preflight(
    *,
    config_path: Path,
    audit_config_path: Path,
    reference_config_path: Path,
    audit_dir: Path,
    reference_dir: Path,
    candidate_dir: Path,
) -> dict[str, Any]:
    config = load_h2_production_audit_evaluation_config(config_path)
    _validate_configs(config, audit_config_path, reference_config_path)
    audit_manifest, audit_cases = _validate_audit_static(audit_dir)
    reference_manifest, reference_summary, reference_rows = _validate_reference_static(reference_dir)
    candidate_manifest, _, expected_final_sha = _validate_candidate_static(candidate_dir, read_final_mentions=False)
    if [row.audit_case_id for row in reference_rows] != [row.audit_case_id for row in audit_cases]:
        raise H2ProductionAuditEvaluationError("Frozen reference row order/identity does not exactly align to audit sample")
    if reference_manifest.audit_sample_manifest_sha256 != _sha256_file(audit_dir / "manifest.json"):
        raise H2ProductionAuditEvaluationError("Reference does not bind current audit sample manifest")
    if reference_manifest.audit_cases_sha256 != _sha256_file(audit_dir / "audit_cases.jsonl"):
        raise H2ProductionAuditEvaluationError("Reference does not bind current audit cases")
    return {
        "config": config,
        "audit_manifest": audit_manifest,
        "audit_cases": audit_cases,
        "reference_manifest": reference_manifest,
        "reference_summary": reference_summary,
        "reference_rows": reference_rows,
        "candidate_manifest": candidate_manifest,
        "candidate_final_mentions_expected_sha256": expected_final_sha,
    }


def _stratum_metrics(stratum: str, rows: Sequence[H2ProductionAuditEvaluationCase]) -> H2ProductionAuditStratumMetrics:
    total = len(rows)
    statuses = Counter(row.span_status for row in rows)
    usable = [row for row in rows if row.usable_for_reference_type_rates]
    types = Counter(row.reference_entity_type.value for row in usable if row.reference_entity_type is not None)
    usable_count = len(usable)
    model_rate = types.get("model", 0) / usable_count if usable_count else None
    method_rate = types.get("method", 0) / usable_count if usable_count else None
    net_rate = (model_rate - method_rate) if model_rate is not None and method_rate is not None else None
    unresolved_rate = (statuses.get("uncertain", 0) + statuses.get("not_an_entity", 0)) / total
    baseline_correct = sum(row.baseline_matches_reference is True for row in rows)
    final_correct = sum(row.final_matches_reference is True for row in rows)
    corrected = sum(row.baseline_matches_reference is False and row.final_matches_reference is True for row in rows)
    regressed = sum(row.baseline_matches_reference is True and row.final_matches_reference is False for row in rows)
    return H2ProductionAuditStratumMetrics(
        stratum=stratum,
        total_count=total,
        usable_count=usable_count,
        valid_entity_span_count=statuses.get("valid_entity_span", 0),
        boundary_issue_count=statuses.get("boundary_issue", 0),
        not_an_entity_count=statuses.get("not_an_entity", 0),
        uncertain_count=statuses.get("uncertain", 0),
        reference_type_count={entity_type.value: types.get(entity_type.value, 0) for entity_type in ScientificEntityType},
        reference_model_rate=model_rate,
        reference_method_rate=method_rate,
        model_minus_method_rate=net_rate,
        unresolved_or_not_entity_rate=unresolved_rate,
        baseline_correct_count=baseline_correct,
        final_correct_count=final_correct,
        corrected_by_h2_count=corrected,
        regressed_by_h2_count=regressed,
    )


def _gate(name: str, observed: float, comparator: str, threshold: float) -> H2ProductionAuditGateResult:
    passed = observed <= threshold if comparator == "<=" else observed >= threshold
    return H2ProductionAuditGateResult(gate_name=name, observed_value=observed, comparator=comparator, threshold=threshold, passed=passed)


def _gate_results(config: H2ProductionAuditEvaluationConfig, summary: H2ProductionAuditEvaluationSummary) -> H2ProductionAuditGateResults:
    by = {row.stratum: row for row in summary.strata}
    override = by["override"]
    preserved = by["preserved_method"]
    fallback = by["fallback_method"]
    if override.reference_model_rate is None or override.reference_method_rate is None or override.model_minus_method_rate is None:
        raise H2ProductionAuditEvaluationError("Override usable denominator is zero")
    if preserved.reference_model_rate is None or preserved.reference_method_rate is None:
        raise H2ProductionAuditEvaluationError("Preserved usable denominator is zero")
    g = config.promotion_gates
    gates = [
        _gate("overall_uncertain_rate", summary.uncertain_rate, "<=", g.max_overall_uncertain_rate),
        _gate("overall_not_an_entity_rate", summary.not_an_entity_rate, "<=", g.max_overall_not_entity_rate),
        _gate("override_usable_count", float(override.usable_count), ">=", float(g.min_override_usable_count)),
        _gate("override_reference_model_rate", override.reference_model_rate, ">=", g.min_override_reference_model_rate),
        _gate("override_reference_method_rate", override.reference_method_rate, "<=", g.max_override_reference_method_rate),
        _gate("override_model_minus_method_rate", override.model_minus_method_rate, ">=", g.min_override_net_model_minus_method_rate),
        _gate("preserved_usable_count", float(preserved.usable_count), ">=", float(g.min_preserved_usable_count)),
        _gate("preserved_reference_method_rate", preserved.reference_method_rate, ">=", g.min_preserved_reference_method_rate),
        _gate("preserved_reference_model_rate", preserved.reference_model_rate, "<=", g.max_preserved_reference_model_rate),
        _gate("fallback_usable_count", float(fallback.usable_count), ">=", float(g.min_fallback_usable_count)),
        _gate("fallback_unresolved_or_not_entity_rate", fallback.unresolved_or_not_entity_rate, "<=", g.max_fallback_unresolved_or_not_entity_rate),
    ]
    all_pass = all(row.passed for row in gates)
    return H2ProductionAuditGateResults(
        evaluation_id=EVALUATION_ID,
        gate_count=11,
        gates=gates,
        all_hard_gates_pass=all_pass,
        gate_verdict="pass_h2_production_audit_gate" if all_pass else "fail_h2_production_audit_gate",
        thresholds_revised_after_annotation=False,
        promotion_decision_made=False,
        production_latest_promotion_authorized=False,
    )


def _compute_evaluation_package(
    *,
    config_path: Path,
    audit_config_path: Path,
    reference_config_path: Path,
    audit_dir: Path,
    reference_dir: Path,
    candidate_dir: Path,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    parent = _preflight(
        config_path=config_path,
        audit_config_path=audit_config_path,
        reference_config_path=reference_config_path,
        audit_dir=audit_dir,
        reference_dir=reference_dir,
        candidate_dir=candidate_dir,
    )
    config: H2ProductionAuditEvaluationConfig = parent["config"]
    audit_config = load_h2_production_audit_config(audit_config_path)
    _validate_candidate_static(candidate_dir, read_final_mentions=True)
    selected_by_stratum = _select_final_rows(candidate_dir, audit_config)
    selected_by_case: dict[str, tuple[str, H2FullCorpusFinalMention]] = {}
    for stratum, rows in selected_by_stratum.items():
        for row in rows:
            audit_case_id = _stable_case_id(AUDIT_ID, row.baseline_prediction_evidence_id)
            if audit_case_id in selected_by_case:
                raise H2ProductionAuditEvaluationError("Duplicate reconstructed audit_case_id")
            selected_by_case[audit_case_id] = (stratum, row)
    if len(selected_by_case) != 240:
        raise H2ProductionAuditEvaluationError("Reconstructed sample count mismatch")
    audit_cases = {row.audit_case_id: row for row in parent["audit_cases"]}
    if set(selected_by_case) != set(audit_cases):
        raise H2ProductionAuditEvaluationError("Deterministic reconstructed sample does not match immutable blind audit sample")

    evaluation_rows: list[H2ProductionAuditEvaluationCase] = []
    for reference in parent["reference_rows"]:
        blind = audit_cases[reference.audit_case_id]
        stratum, candidate = selected_by_case[reference.audit_case_id]
        immutable_match = (
            blind.canonical_id == candidate.canonical_id == reference.canonical_id
            and blind.source_field == candidate.source_field == reference.source_field
            and blind.source_text_sha256 == candidate.source_text_sha256 == reference.source_text_sha256
            and blind.char_start == candidate.char_start == reference.char_start
            and blind.char_end == candidate.char_end == reference.char_end
            and blind.surface_text == candidate.surface_text == reference.surface_text
        )
        if not immutable_match:
            raise H2ProductionAuditEvaluationError(f"Case lineage mismatch after unblinding: {reference.audit_case_id}")
        if candidate.baseline_entity_type != ScientificEntityType.METHOD or candidate.semantic_typer_used_baseline_fallback is None:
            raise H2ProductionAuditEvaluationError("Reconstructed audit row is not a fully materialized baseline-method case")
        usable = reference.span_status in USABLE_STATUSES
        baseline_matches = candidate.baseline_entity_type == reference.reference_entity_type if usable else None
        final_matches = candidate.final_entity_type == reference.reference_entity_type if usable else None
        evaluation_rows.append(H2ProductionAuditEvaluationCase(
            evaluation_id=EVALUATION_ID,
            audit_id=AUDIT_ID,
            reference_id=REFERENCE_ID,
            audit_case_id=reference.audit_case_id,
            stratum=stratum,
            candidate_evidence_id=candidate.candidate_evidence_id,
            baseline_prediction_evidence_id=candidate.baseline_prediction_evidence_id,
            canonical_id=candidate.canonical_id,
            source_field=candidate.source_field.value,
            source_text_sha256=candidate.source_text_sha256,
            char_start=candidate.char_start,
            char_end=candidate.char_end,
            surface_text=candidate.surface_text,
            baseline_entity_type=candidate.baseline_entity_type,
            final_entity_type=candidate.final_entity_type,
            semantic_typer_predicted_entity_type=candidate.semantic_typer_predicted_entity_type,
            semantic_typer_used_baseline_fallback=candidate.semantic_typer_used_baseline_fallback,
            semantic_typer_score_margin=candidate.semantic_typer_score_margin,
            h2_override_applied=candidate.h2_override_applied,
            reference_entity_type=reference.reference_entity_type,
            span_status=reference.span_status,
            annotation_confidence=reference.annotation_confidence,
            reviewer_note=reference.reviewer_note,
            usable_for_reference_type_rates=usable,
            baseline_matches_reference=baseline_matches,
            final_matches_reference=final_matches,
        ))

    by_stratum = {name: [row for row in evaluation_rows if row.stratum == name] for name in ("override", "preserved_method", "fallback_method")}
    expected_counts = {"override": 100, "preserved_method": 100, "fallback_method": 40}
    if {name: len(rows) for name, rows in by_stratum.items()} != expected_counts:
        raise H2ProductionAuditEvaluationError("Reconstructed stratum counts drifted")
    strata = [_stratum_metrics(name, by_stratum[name]) for name in ("override", "preserved_method", "fallback_method")]
    status = Counter(row.span_status for row in evaluation_rows)
    summary_stub = H2ProductionAuditEvaluationSummary(
        evaluation_id=EVALUATION_ID,
        audit_id=AUDIT_ID,
        reference_id=REFERENCE_ID,
        audit_case_count=240,
        usable_count=sum(row.usable_for_reference_type_rates for row in evaluation_rows),
        uncertain_count=status.get("uncertain", 0),
        not_an_entity_count=status.get("not_an_entity", 0),
        boundary_issue_count=status.get("boundary_issue", 0),
        uncertain_rate=status.get("uncertain", 0) / 240,
        not_an_entity_rate=status.get("not_an_entity", 0) / 240,
        boundary_issue_rate=status.get("boundary_issue", 0) / 240,
        strata=strata,
        all_hard_gates_pass=False,
        gate_verdict="fail_h2_production_audit_gate",
        candidate_prediction_files_read=True,
        sampled_strata_reconstructed=True,
        unblinding_executed=True,
        promotion_gates_evaluated=True,
        model_inference_executed=False,
        threshold_tuning_executed=False,
        policy_revision_executed=False,
        candidate_mutated=False,
        canonical_truth_mutated=False,
        promotion_decision_made=False,
        production_latest_promotion_authorized=False,
    )
    gates = _gate_results(config, summary_stub)
    summary = summary_stub.model_copy(update={"all_hard_gates_pass": gates.all_hard_gates_pass, "gate_verdict": gates.gate_verdict})

    cases_bytes = _jsonl_bytes(evaluation_rows)
    gates_bytes = _json_bytes(gates)
    summary_bytes = _json_bytes(summary)
    readme = (
        "# H2 v0.3 Production Audit Evaluation\n\n"
        f"Evaluation ID: `{EVALUATION_ID}`\n\n"
        f"Frozen reference: `{REFERENCE_ID}`\n\n"
        "This one-shot slice reconstructs the hidden audit strata only after the human reference was frozen, reads the already validated full-corpus candidate, and evaluates the preregistered promotion-safety gates.\n\n"
        "Reference model/method rates use only usable cases (`valid_entity_span` + `boundary_issue`) as denominator. The fallback unresolved/not-entity rate uses all fallback cases. Boundary issues remain diagnostic-only.\n\n"
        "This artifact is evaluation evidence only. It does not revise H2, make the separate promotion decision, authorize production latest, mutate canonical truth, or overwrite latest.\n"
    ).encode("utf-8")
    files: dict[str, bytes] = {
        "case_evaluations.jsonl": cases_bytes,
        "gate_results.json": gates_bytes,
        "summary.json": summary_bytes,
        "README.md": readme,
    }
    manifest = H2ProductionAuditEvaluationManifest(
        evaluation_id=EVALUATION_ID,
        audit_id=AUDIT_ID,
        reference_id=REFERENCE_ID,
        candidate_build_id=CANDIDATE_BUILD_ID,
        candidate_id=CANDIDATE_ID,
        candidate_fingerprint_sha256=CANDIDATE_FINGERPRINT,
        materialization_fingerprint_sha256=MATERIALIZATION_FINGERPRINT,
        canonical_sha256=CANONICAL_SHA256,
        canonical_document_count=61075,
        evaluation_config_sha256=canonical_config_sha256(config),
        audit_config_canonical_sha256=AUDIT_CONFIG_CANONICAL_SHA256,
        reference_freeze_config_canonical_sha256=REFERENCE_CONFIG_CANONICAL_SHA256,
        audit_sample_manifest_sha256=_sha256_file(audit_dir / "manifest.json"),
        reference_manifest_sha256=_sha256_file(reference_dir / "manifest.json"),
        candidate_manifest_sha256=_sha256_file(candidate_dir / "manifest.json"),
        candidate_final_mentions_sha256=_sha256_file(candidate_dir / "final_mentions.jsonl"),
        files={name: _sha256_bytes(payload) for name, payload in sorted(files.items())},
        audit_case_count=240,
        override_count=100,
        preserved_method_count=100,
        fallback_method_count=40,
        frozen_reference_verified_before_unblinding=True,
        deterministic_sample_reconstructed_exactly=True,
        candidate_prediction_files_read=True,
        sampled_strata_reconstructed=True,
        unblinding_executed=True,
        promotion_gates_evaluated=True,
        model_inference_executed=False,
        threshold_tuning_executed=False,
        policy_revision_executed=False,
        candidate_mutated=False,
        canonical_truth_mutated=False,
        promotion_decision_made=False,
        production_latest_promotion_authorized=False,
        latest_overwritten=False,
        publication_ready=False,
        next_slice="validate_h2_production_audit_evaluation",
    )
    files["manifest.json"] = _json_bytes(manifest)
    files["checksums.txt"] = "".join(f"{_sha256_bytes(files[name])}  {name}\n" for name in sorted(files)).encode("utf-8")
    report = {
        "report": REPORT_NAME,
        "evaluation_id": EVALUATION_ID,
        "audit_id": AUDIT_ID,
        "reference_id": REFERENCE_ID,
        "audit_case_count": 240,
        "override_count": 100,
        "preserved_method_count": 100,
        "fallback_method_count": 40,
        "uncertain_count": summary.uncertain_count,
        "not_an_entity_count": summary.not_an_entity_count,
        "boundary_issue_count": summary.boundary_issue_count,
        "all_hard_gates_pass": gates.all_hard_gates_pass,
        "gate_verdict": gates.gate_verdict,
        "candidate_prediction_files_read": True,
        "sampled_strata_reconstructed": True,
        "unblinding_executed": True,
        "promotion_gates_evaluated": True,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "policy_revision_executed": False,
        "candidate_mutated": False,
        "canonical_truth_mutated": False,
        "promotion_decision_made": False,
        "production_latest_promotion_authorized": False,
        "next_slice": "validate_h2_production_audit_evaluation",
    }
    return files, report


def plan_or_execute_h2_production_audit_evaluation(
    *,
    project_root: Path,
    config_path: Path,
    audit_config_path: Path,
    reference_config_path: Path,
    audit_dir: Path,
    reference_dir: Path,
    candidate_dir: Path,
    output_root: Path | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    preflight = _preflight(
        config_path=config_path.resolve(),
        audit_config_path=audit_config_path.resolve(),
        reference_config_path=reference_config_path.resolve(),
        audit_dir=audit_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        candidate_dir=candidate_dir.resolve(),
    )
    config: H2ProductionAuditEvaluationConfig = preflight["config"]
    root = output_root.resolve() if output_root is not None else (project_root.resolve() / config.execution.output_root).resolve()
    output_dir = root / config.execution.evaluation_id
    exists = output_dir.exists()
    if not execute:
        return {
            "report": REPORT_NAME,
            "mode": "plan",
            "phase_complete": False,
            "evaluation_id": EVALUATION_ID,
            "audit_id": AUDIT_ID,
            "reference_id": REFERENCE_ID,
            "audit_case_count": 240,
            "reference_frozen": True,
            "candidate_build_id": CANDIDATE_BUILD_ID,
            "candidate_prediction_files_read": False,
            "sampled_strata_reconstructed": False,
            "unblinding_executed": False,
            "promotion_gates_evaluated": False,
            "quality_metrics_exposed": False,
            "model_inference_executed": False,
            "threshold_tuning_executed": False,
            "policy_revision_executed": False,
            "candidate_mutated": False,
            "canonical_truth_mutated": False,
            "promotion_decision_made": False,
            "production_latest_promotion_authorized": False,
            "evaluation_already_exists": exists,
            "plan_writes_output": False,
            "output_dir": str(output_dir),
            "next_slice": config.next_steps.after_plan,
        }
    if exists:
        raise H2ProductionAuditEvaluationError(f"Immutable evaluation directory already exists: {output_dir}")
    files, report = _compute_evaluation_package(
        config_path=config_path.resolve(),
        audit_config_path=audit_config_path.resolve(),
        reference_config_path=reference_config_path.resolve(),
        audit_dir=audit_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        candidate_dir=candidate_dir.resolve(),
    )
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{EVALUATION_ID}.tmp-", dir=root))
    try:
        for name, payload in files.items():
            (staging / name).write_bytes(payload)
        staging.rename(output_dir)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return {**report, "mode": "execute", "phase_complete": True, "evaluation_already_exists": True, "output_dir": str(output_dir)}


def validate_h2_production_audit_evaluation(
    *,
    project_root: Path,
    config_path: Path,
    audit_config_path: Path,
    reference_config_path: Path,
    audit_dir: Path,
    reference_dir: Path,
    candidate_dir: Path,
    evaluation_dir: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    evaluation_dir = evaluation_dir.resolve()
    add("evaluation_directory_exists", evaluation_dir.is_dir(), evaluation_dir)
    if not evaluation_dir.is_dir():
        return checks, {"report": REPORT_NAME, "total_checks": len(checks), "required_failed_count": 1, "next_slice": "fix_h2_production_audit_evaluation_artifact"}
    names = sorted(path.name for path in evaluation_dir.iterdir() if path.is_file())
    add("exact_file_layout", names == sorted(OUTPUT_FILES), names)
    checksum_map = _parse_checksums(evaluation_dir / "checksums.txt") if (evaluation_dir / "checksums.txt").is_file() else {}
    add("checksum_set_exact", sorted(checksum_map) == sorted(CHECKSUM_FILES), sorted(checksum_map))
    for name in CHECKSUM_FILES:
        path = evaluation_dir / name
        add(f"checksum:{name}", path.is_file() and checksum_map.get(name) == _sha256_file(path), name)
    for name in OUTPUT_FILES:
        path = evaluation_dir / name
        add(f"lf:{name}", path.is_file() and _lf_ok(path), name)

    try:
        expected_files, expected_report = _compute_evaluation_package(
            config_path=config_path.resolve(),
            audit_config_path=audit_config_path.resolve(),
            reference_config_path=reference_config_path.resolve(),
            audit_dir=audit_dir.resolve(),
            reference_dir=reference_dir.resolve(),
            candidate_dir=candidate_dir.resolve(),
        )
        manifest = H2ProductionAuditEvaluationManifest.model_validate(json.loads((evaluation_dir / "manifest.json").read_text(encoding="utf-8")))
        summary_model = H2ProductionAuditEvaluationSummary.model_validate(json.loads((evaluation_dir / "summary.json").read_text(encoding="utf-8")))
        gates_model = H2ProductionAuditGateResults.model_validate(json.loads((evaluation_dir / "gate_results.json").read_text(encoding="utf-8")))
        rows = [H2ProductionAuditEvaluationCase.model_validate(json.loads(line)) for line in (evaluation_dir / "case_evaluations.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        add("manifest_schema_and_lineage", manifest.evaluation_id == EVALUATION_ID and manifest.reference_id == REFERENCE_ID and manifest.candidate_build_id == CANDIDATE_BUILD_ID)
        add("manifest_unblinding_flags", manifest.frozen_reference_verified_before_unblinding and manifest.deterministic_sample_reconstructed_exactly and manifest.candidate_prediction_files_read and manifest.sampled_strata_reconstructed and manifest.unblinding_executed and manifest.promotion_gates_evaluated)
        add("manifest_safety_flags", not manifest.model_inference_executed and not manifest.threshold_tuning_executed and not manifest.policy_revision_executed and not manifest.candidate_mutated and not manifest.canonical_truth_mutated and not manifest.promotion_decision_made and not manifest.production_latest_promotion_authorized and not manifest.latest_overwritten)
        add("case_row_count", len(rows) == 240, len(rows))
        add("case_ids_unique", len({row.audit_case_id for row in rows}) == 240)
        add("stratum_counts_exact", Counter(row.stratum for row in rows) == Counter({"override": 100, "preserved_method": 100, "fallback_method": 40}), dict(Counter(row.stratum for row in rows)))
        add("gate_count_exact", gates_model.gate_count == 11 and len(gates_model.gates) == 11)
        add("summary_gate_consistency", summary_model.all_hard_gates_pass == gates_model.all_hard_gates_pass and summary_model.gate_verdict == gates_model.gate_verdict)
        for name in ("README.md", "case_evaluations.jsonl", "gate_results.json", "manifest.json", "summary.json", "checksums.txt"):
            add(f"recompute_exact:{name}", (evaluation_dir / name).read_bytes() == expected_files[name], name)
        add("report_gate_consistency", expected_report["all_hard_gates_pass"] == gates_model.all_hard_gates_pass)
    except Exception as exc:
        add("recompute_evaluation", False, f"{type(exc).__name__}: {exc}")
        gates_model = None

    required_failed = sum(1 for _, ok, _ in checks if not ok)
    gate_pass = gates_model.all_hard_gates_pass if gates_model is not None else False
    summary = {
        "report": REPORT_NAME,
        "evaluation_id": EVALUATION_ID,
        "audit_id": AUDIT_ID,
        "reference_id": REFERENCE_ID,
        "evaluation_validated": required_failed == 0,
        "promotion_gate_passed": gate_pass if required_failed == 0 else False,
        "promotion_decision_made": False,
        "production_latest_promotion_authorized": False,
        "canonical_truth_mutated": False,
        "total_checks": len(checks),
        "required_failed_count": required_failed,
        "next_slice": "make_immutable_h2_production_promotion_decision" if required_failed == 0 else "fix_h2_production_audit_evaluation_artifact",
    }
    return checks, summary
