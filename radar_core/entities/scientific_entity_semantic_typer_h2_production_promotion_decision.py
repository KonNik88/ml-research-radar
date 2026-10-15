from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Sequence

from radar_core.contracts.scientific_entity_semantic_typer_h2_full_corpus_candidate import H2FullCorpusManifest, H2FullCorpusSummary
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_authorization import H2ProductionAuthorizationManifest, H2ProductionAuthorizationRecord
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit_evaluation import (
    H2ProductionAuditEvaluationManifest,
    H2ProductionAuditEvaluationSummary,
    H2ProductionAuditGateResults,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit_reference import (
    H2ProductionAuditReferenceManifest,
    H2ProductionAuditReferenceSummary,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_promotion_decision import (
    AUTHORIZATION_ID,
    CANDIDATE_BUILD_ID,
    CANDIDATE_FINGERPRINT,
    CANDIDATE_ID,
    CANONICAL_SHA256,
    DECISION_ID,
    EVALUATION_ID,
    MATERIALIZATION_FINGERPRINT,
    REFERENCE_ID,
    H2ProductionPromotionDecisionConfig,
    H2ProductionPromotionDecisionError,
    H2ProductionPromotionDecisionManifest,
    H2ProductionPromotionDecisionRecord,
    canonical_config_sha256,
    load_h2_production_promotion_decision_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_promotion_decision_v0.3.yaml"
REPORT_NAME = "scientific_entity_semantic_typer_h2_production_promotion_decision_v03"
OUTPUT_FILES = ("README.md", "decision.json", "manifest.json", "checksums.txt")
CHECKSUM_FILES = ("README.md", "decision.json", "manifest.json")
AUTHORIZATION_FILES = ("README.md", "authorization.json", "manifest.json", "checksums.txt")
REFERENCE_FILES = ("README.md", "annotation_summary.json", "reference_annotations.jsonl", "manifest.json", "checksums.txt")
CANDIDATE_FILES = (
    "README.md", "baseline_mentions.jsonl", "final_mentions.jsonl", "h2_overrides.jsonl", "semantic_typer_cases.jsonl",
    "semantic_typer_predictions.jsonl", "summary.json", "upstream_raw_mentions.jsonl", "manifest.json", "checksums.txt",
)
EVALUATION_FILES = ("README.md", "case_evaluations.jsonl", "gate_results.json", "manifest.json", "summary.json", "checksums.txt")


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


def _parse_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        if name in result:
            raise H2ProductionPromotionDecisionError(f"Duplicate checksum entry: {name}")
        result[name] = digest
    return result


def _lf_ok(path: Path) -> bool:
    return b"\r" not in path.read_bytes()


def _require_exact_files(directory: Path, expected: Sequence[str], label: str) -> None:
    if not directory.is_dir():
        raise H2ProductionPromotionDecisionError(f"{label} directory does not exist: {directory}")
    actual = sorted(path.name for path in directory.iterdir() if path.is_file())
    if actual != sorted(expected):
        raise H2ProductionPromotionDecisionError(f"{label} exact file layout drifted: {actual}")


def _validate_authorization(config: H2ProductionPromotionDecisionConfig, authorization_dir: Path) -> tuple[H2ProductionAuthorizationManifest, H2ProductionAuthorizationRecord]:
    _require_exact_files(authorization_dir, AUTHORIZATION_FILES, "Authorization")
    checksums = _parse_checksums(authorization_dir / "checksums.txt")
    if set(checksums) != {"README.md", "authorization.json", "manifest.json"}:
        raise H2ProductionPromotionDecisionError("Authorization checksum set drifted")
    for name in checksums:
        if checksums[name] != _sha256_file(authorization_dir / name):
            raise H2ProductionPromotionDecisionError(f"Authorization checksum mismatch: {name}")
    if _sha256_file(authorization_dir / "manifest.json") != config.lineage.authorization_manifest_sha256:
        raise H2ProductionPromotionDecisionError("Authorization manifest SHA-256 drifted")
    if _sha256_file(authorization_dir / "authorization.json") != config.lineage.authorization_record_sha256:
        raise H2ProductionPromotionDecisionError("Authorization record SHA-256 drifted")
    manifest = H2ProductionAuthorizationManifest.model_validate(json.loads((authorization_dir / "manifest.json").read_text(encoding="utf-8")))
    record = H2ProductionAuthorizationRecord.model_validate(json.loads((authorization_dir / "authorization.json").read_text(encoding="utf-8")))
    if manifest.authorization_id != AUTHORIZATION_ID or record.authorization_id != AUTHORIZATION_ID:
        raise H2ProductionPromotionDecisionError("Authorization identity mismatch")
    if not manifest.authorization_made or not manifest.full_corpus_candidate_build_authorized or not record.full_corpus_candidate_build_authorized:
        raise H2ProductionPromotionDecisionError("Candidate-build authorization prerequisite is not satisfied")
    if manifest.production_latest_promotion_authorized or record.production_latest_promotion_authorized:
        raise H2ProductionPromotionDecisionError("Parent authorization must not already authorize production latest")
    if manifest.candidate_id != CANDIDATE_ID or record.candidate_id != CANDIDATE_ID:
        raise H2ProductionPromotionDecisionError("Authorization candidate ID mismatch")
    if manifest.candidate_fingerprint_sha256 != CANDIDATE_FINGERPRINT or record.candidate_fingerprint_sha256 != CANDIDATE_FINGERPRINT:
        raise H2ProductionPromotionDecisionError("Authorization candidate fingerprint mismatch")
    if manifest.canonical_sha256 != CANONICAL_SHA256 or record.canonical_sha256 != CANONICAL_SHA256:
        raise H2ProductionPromotionDecisionError("Authorization canonical snapshot mismatch")
    return manifest, record


def _validate_candidate(config: H2ProductionPromotionDecisionConfig, candidate_dir: Path) -> tuple[H2FullCorpusManifest, H2FullCorpusSummary, dict[str, str]]:
    _require_exact_files(candidate_dir, CANDIDATE_FILES, "Candidate")
    checksums = _parse_checksums(candidate_dir / "checksums.txt")
    expected_checksum_names = set(CANDIDATE_FILES) - {"checksums.txt"}
    if set(checksums) != expected_checksum_names:
        raise H2ProductionPromotionDecisionError("Candidate checksum set drifted")
    # This decision slice intentionally hashes only metadata. 8F must hash final_mentions.jsonl immediately before mutation.
    for name in ("README.md", "manifest.json", "summary.json"):
        if checksums[name] != _sha256_file(candidate_dir / name):
            raise H2ProductionPromotionDecisionError(f"Candidate metadata checksum mismatch: {name}")
    if _sha256_file(candidate_dir / "manifest.json") != config.lineage.candidate_manifest_sha256:
        raise H2ProductionPromotionDecisionError("Candidate manifest SHA-256 drifted")
    if _sha256_file(candidate_dir / "summary.json") != config.lineage.candidate_summary_sha256:
        raise H2ProductionPromotionDecisionError("Candidate summary SHA-256 drifted")
    if checksums.get("final_mentions.jsonl") != config.lineage.candidate_final_mentions_sha256:
        raise H2ProductionPromotionDecisionError("Authorized candidate final_mentions SHA-256 drifted")
    manifest = H2FullCorpusManifest.model_validate(json.loads((candidate_dir / "manifest.json").read_text(encoding="utf-8")))
    summary = H2FullCorpusSummary.model_validate(json.loads((candidate_dir / "summary.json").read_text(encoding="utf-8")))
    if manifest.build_id != CANDIDATE_BUILD_ID or summary.build_id != CANDIDATE_BUILD_ID:
        raise H2ProductionPromotionDecisionError("Candidate build identity mismatch")
    if manifest.authorization_id != AUTHORIZATION_ID:
        raise H2ProductionPromotionDecisionError("Candidate does not bind expected authorization")
    if manifest.candidate_id != CANDIDATE_ID or manifest.candidate_fingerprint_sha256 != CANDIDATE_FINGERPRINT:
        raise H2ProductionPromotionDecisionError("Candidate identity/fingerprint mismatch")
    if manifest.materialization_fingerprint_sha256 != MATERIALIZATION_FINGERPRINT:
        raise H2ProductionPromotionDecisionError("Candidate materialization fingerprint mismatch")
    if manifest.canonical_sha256 != CANONICAL_SHA256 or manifest.canonical_document_count != 61075 or summary.input_document_count != 61075:
        raise H2ProductionPromotionDecisionError("Candidate canonical lineage mismatch")
    if manifest.files != {name: checksums[name] for name in manifest.files}:
        raise H2ProductionPromotionDecisionError("Candidate manifest file hashes do not match checksum ledger")
    if manifest.files.get("final_mentions.jsonl") != config.lineage.candidate_final_mentions_sha256:
        raise H2ProductionPromotionDecisionError("Candidate manifest does not bind authorized final_mentions SHA-256")
    if any((manifest.reference_labels_used, manifest.threshold_tuning_executed, manifest.policy_revision_executed, manifest.span_mutated, manifest.canonical_truth_mutated, manifest.production_latest_promotion_authorized, manifest.latest_overwrite_allowed, manifest.publication_ready)):
        raise H2ProductionPromotionDecisionError("Candidate safety flags are not promotion-decision clean")
    return manifest, summary, checksums


def _validate_reference(config: H2ProductionPromotionDecisionConfig, reference_dir: Path) -> tuple[H2ProductionAuditReferenceManifest, H2ProductionAuditReferenceSummary]:
    _require_exact_files(reference_dir, REFERENCE_FILES, "Reference")
    checksums = _parse_checksums(reference_dir / "checksums.txt")
    expected = set(REFERENCE_FILES) - {"checksums.txt"}
    if set(checksums) != expected:
        raise H2ProductionPromotionDecisionError("Reference checksum set drifted")
    for name in expected:
        if checksums[name] != _sha256_file(reference_dir / name):
            raise H2ProductionPromotionDecisionError(f"Reference checksum mismatch: {name}")
    if _sha256_file(reference_dir / "manifest.json") != config.lineage.reference_manifest_sha256:
        raise H2ProductionPromotionDecisionError("Reference manifest SHA-256 drifted")
    if _sha256_file(reference_dir / "annotation_summary.json") != config.lineage.reference_summary_sha256:
        raise H2ProductionPromotionDecisionError("Reference summary SHA-256 drifted")
    if _sha256_file(reference_dir / "reference_annotations.jsonl") != config.lineage.reference_annotations_sha256:
        raise H2ProductionPromotionDecisionError("Reference annotations SHA-256 drifted")
    manifest = H2ProductionAuditReferenceManifest.model_validate(json.loads((reference_dir / "manifest.json").read_text(encoding="utf-8")))
    summary = H2ProductionAuditReferenceSummary.model_validate(json.loads((reference_dir / "annotation_summary.json").read_text(encoding="utf-8")))
    if manifest.reference_id != REFERENCE_ID or summary.reference_id != REFERENCE_ID:
        raise H2ProductionPromotionDecisionError("Reference identity mismatch")
    if not manifest.reference_frozen or not manifest.prediction_blind:
        raise H2ProductionPromotionDecisionError("Reference was not frozen prediction-blind")
    if manifest.candidate_build_id != CANDIDATE_BUILD_ID or manifest.candidate_fingerprint_sha256 != CANDIDATE_FINGERPRINT:
        raise H2ProductionPromotionDecisionError("Reference candidate lineage mismatch")
    if manifest.materialization_fingerprint_sha256 != MATERIALIZATION_FINGERPRINT or manifest.canonical_sha256 != CANONICAL_SHA256:
        raise H2ProductionPromotionDecisionError("Reference materialization/canonical lineage mismatch")
    if any((manifest.candidate_prediction_files_read, manifest.sampled_strata_reconstructed, manifest.unblinding_executed, manifest.promotion_gates_evaluated, manifest.model_inference_executed, manifest.threshold_tuning_executed, manifest.policy_revision_executed, manifest.candidate_mutated, manifest.canonical_truth_mutated, manifest.production_latest_promotion_authorized, manifest.latest_overwritten, manifest.publication_ready)):
        raise H2ProductionPromotionDecisionError("Frozen reference safety flags drifted")
    return manifest, summary


def _validate_evaluation(
    config: H2ProductionPromotionDecisionConfig,
    evaluation_dir: Path,
    *,
    reference_manifest_sha256: str,
    candidate_manifest_sha256: str,
    candidate_final_mentions_sha256: str,
) -> tuple[H2ProductionAuditEvaluationManifest, H2ProductionAuditEvaluationSummary, H2ProductionAuditGateResults]:
    _require_exact_files(evaluation_dir, EVALUATION_FILES, "Evaluation")
    checksums = _parse_checksums(evaluation_dir / "checksums.txt")
    expected = set(EVALUATION_FILES) - {"checksums.txt"}
    if set(checksums) != expected:
        raise H2ProductionPromotionDecisionError("Evaluation checksum set drifted")
    for name in expected:
        if checksums[name] != _sha256_file(evaluation_dir / name):
            raise H2ProductionPromotionDecisionError(f"Evaluation checksum mismatch: {name}")
    expected_hashes = {
        "manifest.json": config.lineage.evaluation_manifest_sha256,
        "summary.json": config.lineage.evaluation_summary_sha256,
        "gate_results.json": config.lineage.evaluation_gate_results_sha256,
        "case_evaluations.jsonl": config.lineage.evaluation_case_evaluations_sha256,
    }
    for name, expected_sha in expected_hashes.items():
        if _sha256_file(evaluation_dir / name) != expected_sha:
            raise H2ProductionPromotionDecisionError(f"Evaluation lineage SHA-256 drifted: {name}")
    manifest = H2ProductionAuditEvaluationManifest.model_validate(json.loads((evaluation_dir / "manifest.json").read_text(encoding="utf-8")))
    summary = H2ProductionAuditEvaluationSummary.model_validate(json.loads((evaluation_dir / "summary.json").read_text(encoding="utf-8")))
    gates = H2ProductionAuditGateResults.model_validate(json.loads((evaluation_dir / "gate_results.json").read_text(encoding="utf-8")))
    if manifest.evaluation_id != EVALUATION_ID or summary.evaluation_id != EVALUATION_ID or gates.evaluation_id != EVALUATION_ID:
        raise H2ProductionPromotionDecisionError("Evaluation identity mismatch")
    if manifest.reference_id != REFERENCE_ID or manifest.candidate_build_id != CANDIDATE_BUILD_ID:
        raise H2ProductionPromotionDecisionError("Evaluation parent identity mismatch")
    if manifest.reference_manifest_sha256 != reference_manifest_sha256:
        raise H2ProductionPromotionDecisionError("Evaluation does not bind current frozen-reference manifest")
    if manifest.candidate_manifest_sha256 != candidate_manifest_sha256:
        raise H2ProductionPromotionDecisionError("Evaluation does not bind current candidate manifest")
    if manifest.candidate_final_mentions_sha256 != candidate_final_mentions_sha256:
        raise H2ProductionPromotionDecisionError("Evaluation does not bind authorized final_mentions SHA-256")
    if manifest.candidate_fingerprint_sha256 != CANDIDATE_FINGERPRINT or manifest.materialization_fingerprint_sha256 != MATERIALIZATION_FINGERPRINT:
        raise H2ProductionPromotionDecisionError("Evaluation candidate fingerprint mismatch")
    if manifest.canonical_sha256 != CANONICAL_SHA256 or manifest.canonical_document_count != 61075:
        raise H2ProductionPromotionDecisionError("Evaluation canonical lineage mismatch")
    if not manifest.frozen_reference_verified_before_unblinding or not manifest.deterministic_sample_reconstructed_exactly:
        raise H2ProductionPromotionDecisionError("Evaluation did not prove frozen-reference/sample lineage")
    if not gates.all_hard_gates_pass or gates.gate_verdict != "pass_h2_production_audit_gate" or gates.gate_count != 11:
        raise H2ProductionPromotionDecisionError("Production audit promotion gate did not pass")
    if not summary.all_hard_gates_pass or summary.gate_verdict != "pass_h2_production_audit_gate":
        raise H2ProductionPromotionDecisionError("Evaluation summary does not record a passing gate")
    if gates.thresholds_revised_after_annotation:
        raise H2ProductionPromotionDecisionError("Evaluation thresholds were revised after annotation")
    if any((manifest.model_inference_executed, manifest.threshold_tuning_executed, manifest.policy_revision_executed, manifest.candidate_mutated, manifest.canonical_truth_mutated, manifest.promotion_decision_made, manifest.production_latest_promotion_authorized, manifest.latest_overwritten, manifest.publication_ready)):
        raise H2ProductionPromotionDecisionError("Evaluation safety flags are not decision-ready")
    return manifest, summary, gates


def _preflight(
    *,
    config_path: Path,
    authorization_dir: Path,
    candidate_dir: Path,
    reference_dir: Path,
    evaluation_dir: Path,
) -> dict[str, Any]:
    config = load_h2_production_promotion_decision_config(config_path)
    authorization_manifest, authorization_record = _validate_authorization(config, authorization_dir)
    candidate_manifest, candidate_summary, candidate_checksums = _validate_candidate(config, candidate_dir)
    reference_manifest, reference_summary = _validate_reference(config, reference_dir)
    actual_reference_manifest_sha = _sha256_file(reference_dir / "manifest.json")
    actual_candidate_manifest_sha = _sha256_file(candidate_dir / "manifest.json")
    evaluation_manifest, evaluation_summary, gates = _validate_evaluation(
        config,
        evaluation_dir,
        reference_manifest_sha256=actual_reference_manifest_sha,
        candidate_manifest_sha256=actual_candidate_manifest_sha,
        candidate_final_mentions_sha256=candidate_checksums["final_mentions.jsonl"],
    )
    if candidate_manifest.authorization_id != authorization_manifest.authorization_id or candidate_manifest.authorization_id != authorization_record.authorization_id:
        raise H2ProductionPromotionDecisionError("Authorization -> candidate lineage mismatch")
    if reference_manifest.candidate_build_id != candidate_manifest.build_id or evaluation_manifest.candidate_build_id != candidate_manifest.build_id:
        raise H2ProductionPromotionDecisionError("Candidate build lineage mismatch across reference/evaluation")
    return {
        "config": config,
        "authorization_manifest": authorization_manifest,
        "authorization_record": authorization_record,
        "candidate_manifest": candidate_manifest,
        "candidate_summary": candidate_summary,
        "candidate_checksums": candidate_checksums,
        "reference_manifest": reference_manifest,
        "reference_summary": reference_summary,
        "evaluation_manifest": evaluation_manifest,
        "evaluation_summary": evaluation_summary,
        "gates": gates,
    }


def _compute_decision_package(
    *,
    config_path: Path,
    authorization_dir: Path,
    candidate_dir: Path,
    reference_dir: Path,
    evaluation_dir: Path,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    parent = _preflight(
        config_path=config_path,
        authorization_dir=authorization_dir,
        candidate_dir=candidate_dir,
        reference_dir=reference_dir,
        evaluation_dir=evaluation_dir,
    )
    config: H2ProductionPromotionDecisionConfig = parent["config"]
    gates: H2ProductionAuditGateResults = parent["gates"]
    decision = H2ProductionPromotionDecisionRecord(
        decision_id=DECISION_ID,
        decision="authorize_controlled_h2_production_latest_promotion",
        authorization_id=AUTHORIZATION_ID,
        candidate_build_id=CANDIDATE_BUILD_ID,
        reference_id=REFERENCE_ID,
        evaluation_id=EVALUATION_ID,
        candidate_id=CANDIDATE_ID,
        candidate_fingerprint_sha256=CANDIDATE_FINGERPRINT,
        materialization_fingerprint_sha256=MATERIALIZATION_FINGERPRINT,
        canonical_sha256=CANONICAL_SHA256,
        canonical_document_count=61075,
        candidate_final_mentions_sha256=config.lineage.candidate_final_mentions_sha256,
        evaluation_gate_count=gates.gate_count,
        evaluation_all_hard_gates_pass=True,
        evaluation_gate_verdict="pass_h2_production_audit_gate",
        thresholds_revised_after_annotation=False,
        promotion_decision_made=True,
        production_latest_promotion_authorized=True,
        authorization_scope=config.promotion_boundary.authorization_scope,
        authorized_promotion_count=1,
        exact_candidate_final_mentions_sha256_required_at_promotion=True,
        backup_previous_trusted_latest_required=True,
        rollback_path_required=True,
        post_promotion_validation_required=True,
        candidate_prediction_files_read_in_this_slice=False,
        model_inference_executed=False,
        threshold_tuning_executed=False,
        policy_revision_executed=False,
        candidate_mutated=False,
        canonical_truth_mutated=False,
        promotion_executed=False,
        latest_overwritten=False,
        publication_authorized=False,
        next_slice="build_controlled_h2_production_latest_promotion_tooling",
    )
    decision_bytes = _json_bytes(decision)
    readme = (
        "# H2 v0.3 Production Promotion Decision\n\n"
        f"Decision ID: `{DECISION_ID}`\n\n"
        f"Candidate build: `{CANDIDATE_BUILD_ID}`\n\n"
        f"Authorized final_mentions SHA-256: `{config.lineage.candidate_final_mentions_sha256}`\n\n"
        "Decision: **authorize one later controlled candidate-to-trusted-latest promotion**.\n\n"
        "All eleven preregistered production-audit hard gates passed on the exact frozen reference and candidate lineage. "
        "This package authorizes the next promotion slice only; it does not itself copy or overwrite trusted/latest, mutate canonical truth, run model inference, revise H2, or authorize publication.\n\n"
        "The promotion executor must re-hash the actual final_mentions.jsonl immediately before mutation, require an exact SHA match, back up the previous trusted latest state, preserve a rollback path, and run post-promotion validation.\n"
    ).encode("utf-8")
    files: dict[str, bytes] = {"README.md": readme, "decision.json": decision_bytes}
    manifest = H2ProductionPromotionDecisionManifest(
        decision_id=DECISION_ID,
        decision_config_sha256=canonical_config_sha256(config),
        authorization_id=AUTHORIZATION_ID,
        authorization_manifest_sha256=config.lineage.authorization_manifest_sha256,
        authorization_record_sha256=config.lineage.authorization_record_sha256,
        candidate_build_id=CANDIDATE_BUILD_ID,
        candidate_manifest_sha256=config.lineage.candidate_manifest_sha256,
        candidate_summary_sha256=config.lineage.candidate_summary_sha256,
        candidate_final_mentions_sha256=config.lineage.candidate_final_mentions_sha256,
        reference_id=REFERENCE_ID,
        reference_manifest_sha256=config.lineage.reference_manifest_sha256,
        reference_summary_sha256=config.lineage.reference_summary_sha256,
        reference_annotations_sha256=config.lineage.reference_annotations_sha256,
        evaluation_id=EVALUATION_ID,
        evaluation_manifest_sha256=config.lineage.evaluation_manifest_sha256,
        evaluation_summary_sha256=config.lineage.evaluation_summary_sha256,
        evaluation_gate_results_sha256=config.lineage.evaluation_gate_results_sha256,
        evaluation_case_evaluations_sha256=config.lineage.evaluation_case_evaluations_sha256,
        candidate_id=CANDIDATE_ID,
        candidate_fingerprint_sha256=CANDIDATE_FINGERPRINT,
        materialization_fingerprint_sha256=MATERIALIZATION_FINGERPRINT,
        canonical_sha256=CANONICAL_SHA256,
        canonical_document_count=61075,
        parent_lineage_verified=True,
        evaluation_gate_count=11,
        evaluation_all_hard_gates_pass=True,
        promotion_decision_made=True,
        production_latest_promotion_authorized=True,
        candidate_prediction_files_read_in_this_slice=False,
        model_inference_executed=False,
        threshold_tuning_executed=False,
        policy_revision_executed=False,
        candidate_mutated=False,
        canonical_truth_mutated=False,
        promotion_executed=False,
        latest_overwritten=False,
        publication_authorized=False,
        files={name: _sha256_bytes(payload) for name, payload in sorted(files.items())},
        next_slice="validate_immutable_h2_production_promotion_decision",
    )
    files["manifest.json"] = _json_bytes(manifest)
    files["checksums.txt"] = "".join(f"{_sha256_bytes(files[name])}  {name}\n" for name in sorted(files)).encode("utf-8")
    report = {
        "report": REPORT_NAME,
        "decision_id": DECISION_ID,
        "authorization_id": AUTHORIZATION_ID,
        "candidate_build_id": CANDIDATE_BUILD_ID,
        "reference_id": REFERENCE_ID,
        "evaluation_id": EVALUATION_ID,
        "candidate_final_mentions_sha256": config.lineage.candidate_final_mentions_sha256,
        "evaluation_gate_count": 11,
        "all_hard_gates_pass": True,
        "promotion_decision_made": True,
        "production_latest_promotion_authorized": True,
        "candidate_prediction_files_read_in_this_slice": False,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "policy_revision_executed": False,
        "candidate_mutated": False,
        "canonical_truth_mutated": False,
        "promotion_executed": False,
        "latest_overwritten": False,
        "publication_authorized": False,
        "next_slice": "validate_immutable_h2_production_promotion_decision",
    }
    return files, report


def plan_or_execute_h2_production_promotion_decision(
    *,
    project_root: Path,
    config_path: Path,
    authorization_dir: Path,
    candidate_dir: Path,
    reference_dir: Path,
    evaluation_dir: Path,
    output_root: Path | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    parent = _preflight(
        config_path=config_path.resolve(),
        authorization_dir=authorization_dir.resolve(),
        candidate_dir=candidate_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        evaluation_dir=evaluation_dir.resolve(),
    )
    config: H2ProductionPromotionDecisionConfig = parent["config"]
    root = output_root.resolve() if output_root is not None else (project_root.resolve() / config.execution.output_root).resolve()
    output_dir = root / config.execution.decision_id
    exists = output_dir.exists()
    if not execute:
        return {
            "report": REPORT_NAME,
            "mode": "plan",
            "phase_complete": False,
            "decision_id": DECISION_ID,
            "authorization_id": AUTHORIZATION_ID,
            "candidate_build_id": CANDIDATE_BUILD_ID,
            "reference_id": REFERENCE_ID,
            "evaluation_id": EVALUATION_ID,
            "candidate_final_mentions_sha256": config.lineage.candidate_final_mentions_sha256,
            "evaluation_gate_count": parent["gates"].gate_count,
            "all_hard_gates_pass": parent["gates"].all_hard_gates_pass,
            "parent_lineage_verified": True,
            "promotion_decision_made": False,
            "production_latest_promotion_authorized": False,
            "candidate_prediction_files_read_in_this_slice": False,
            "model_inference_executed": False,
            "threshold_tuning_executed": False,
            "policy_revision_executed": False,
            "candidate_mutated": False,
            "canonical_truth_mutated": False,
            "promotion_executed": False,
            "latest_overwritten": False,
            "publication_authorized": False,
            "decision_already_exists": exists,
            "plan_writes_output": False,
            "output_dir": str(output_dir),
            "next_slice": config.next_steps.after_plan,
        }
    if exists:
        raise FileExistsError(f"Immutable promotion-decision directory already exists: {output_dir}")
    files, report = _compute_decision_package(
        config_path=config_path.resolve(),
        authorization_dir=authorization_dir.resolve(),
        candidate_dir=candidate_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        evaluation_dir=evaluation_dir.resolve(),
    )
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{DECISION_ID}.tmp-", dir=root))
    try:
        for name, payload in files.items():
            (staging / name).write_bytes(payload)
        staging.rename(output_dir)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return {**report, "mode": "execute", "phase_complete": True, "decision_already_exists": True, "output_dir": str(output_dir)}


def validate_h2_production_promotion_decision(
    *,
    project_root: Path,
    config_path: Path,
    authorization_dir: Path,
    candidate_dir: Path,
    reference_dir: Path,
    evaluation_dir: Path,
    decision_dir: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    decision_dir = decision_dir.resolve()
    add("decision_directory_exists", decision_dir.is_dir(), decision_dir)
    if not decision_dir.is_dir():
        return checks, {"report": REPORT_NAME, "total_checks": len(checks), "required_failed_count": 1, "next_slice": "fix_h2_production_promotion_decision_artifact"}
    actual = sorted(path.name for path in decision_dir.iterdir() if path.is_file())
    add("exact_file_layout", actual == sorted(OUTPUT_FILES), actual)
    checksum_map = _parse_checksums(decision_dir / "checksums.txt") if (decision_dir / "checksums.txt").is_file() else {}
    add("checksum_set_exact", set(checksum_map) == set(CHECKSUM_FILES), sorted(checksum_map))
    for name in CHECKSUM_FILES:
        path = decision_dir / name
        add(f"checksum:{name}", path.is_file() and checksum_map.get(name) == _sha256_file(path), name)
    for name in OUTPUT_FILES:
        path = decision_dir / name
        add(f"lf:{name}", path.is_file() and _lf_ok(path), name)

    try:
        expected_files, expected_report = _compute_decision_package(
            config_path=config_path.resolve(),
            authorization_dir=authorization_dir.resolve(),
            candidate_dir=candidate_dir.resolve(),
            reference_dir=reference_dir.resolve(),
            evaluation_dir=evaluation_dir.resolve(),
        )
        decision = H2ProductionPromotionDecisionRecord.model_validate(json.loads((decision_dir / "decision.json").read_text(encoding="utf-8")))
        manifest = H2ProductionPromotionDecisionManifest.model_validate(json.loads((decision_dir / "manifest.json").read_text(encoding="utf-8")))
        add("decision_schema_and_identity", decision.decision_id == DECISION_ID and decision.candidate_build_id == CANDIDATE_BUILD_ID and decision.evaluation_id == EVALUATION_ID)
        add("decision_authorizes_exactly_one_controlled_promotion", decision.promotion_decision_made and decision.production_latest_promotion_authorized and decision.authorized_promotion_count == 1)
        add("decision_requires_exact_final_mentions_sha", decision.exact_candidate_final_mentions_sha256_required_at_promotion and decision.candidate_final_mentions_sha256 == manifest.candidate_final_mentions_sha256)
        add("decision_requires_backup_rollback_postvalidation", decision.backup_previous_trusted_latest_required and decision.rollback_path_required and decision.post_promotion_validation_required)
        add("decision_has_no_promotion_side_effects", not decision.promotion_executed and not decision.latest_overwritten and not decision.canonical_truth_mutated and not decision.candidate_mutated)
        add("manifest_parent_lineage_verified", manifest.parent_lineage_verified and manifest.evaluation_all_hard_gates_pass and manifest.evaluation_gate_count == 11)
        add("manifest_safety_flags", not manifest.candidate_prediction_files_read_in_this_slice and not manifest.model_inference_executed and not manifest.threshold_tuning_executed and not manifest.policy_revision_executed and not manifest.candidate_mutated and not manifest.canonical_truth_mutated and not manifest.promotion_executed and not manifest.latest_overwritten and not manifest.publication_authorized)
        for name in OUTPUT_FILES:
            add(f"recompute_exact:{name}", (decision_dir / name).read_bytes() == expected_files[name], name)
        add("report_decision_consistency", expected_report["production_latest_promotion_authorized"] is True)
    except Exception as exc:
        add("recompute_decision", False, f"{type(exc).__name__}: {exc}")
        decision = None

    failed = [name for name, ok, _ in checks if not ok]
    summary = {
        "report": REPORT_NAME,
        "decision_id": DECISION_ID,
        "decision_validated": not failed,
        "promotion_decision_made": bool(decision and decision.promotion_decision_made and not failed),
        "production_latest_promotion_authorized": bool(decision and decision.production_latest_promotion_authorized and not failed),
        "promotion_executed": False,
        "latest_overwritten": False,
        "canonical_truth_mutated": False,
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "next_slice": "build_controlled_h2_production_latest_promotion_tooling" if not failed else "fix_h2_production_promotion_decision_artifact",
    }
    return checks, summary
