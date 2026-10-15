from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from radar_core.contracts.scientific_entity_evidence import ScientificEntitySourceField, ScientificEntityType
from radar_core.contracts.scientific_entity_semantic_typer_h2_full_corpus_candidate import (
    H2FullCorpusFinalMention,
    H2FullCorpusManifest,
    H2FullCorpusSummary,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit import load_h2_production_audit_config
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit_evaluation import (
    CANDIDATE_BUILD_ID,
    CANDIDATE_FINGERPRINT,
    CANDIDATE_ID,
    CANONICAL_SHA256,
    EVALUATION_ID,
    MATERIALIZATION_FINGERPRINT,
    H2ProductionAuditEvaluationError,
    load_h2_production_audit_evaluation_config,
)
from radar_core.entities.scientific_entity_semantic_typer_h2_production_audit import (
    _build_blind_cases,
    _select_final_rows,
    _write_package,
)
from radar_core.entities.scientific_entity_semantic_typer_h2_production_audit_evaluation import (
    plan_or_execute_h2_production_audit_evaluation,
    validate_h2_production_audit_evaluation,
)
from radar_core.entities.scientific_entity_semantic_typer_h2_production_audit_reference import freeze_h2_production_audit_reference

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_audit_evaluation_v0.3.yaml"
AUDIT_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_audit_v0.3.yaml"
REFERENCE_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_audit_reference_freeze_v0.3.yaml"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_line(value) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _make_final_row(i: int, stratum: str) -> tuple[H2FullCorpusFinalMention, str]:
    surface = f"Entity{i}"
    source = f"{surface} appears in a synthetic audit context."
    source_sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
    override = stratum == "override"
    fallback = stratum == "fallback_method"
    semantic_type = ScientificEntityType.MODEL if override else ScientificEntityType.METHOD
    row = H2FullCorpusFinalMention(
        build_id=CANDIDATE_BUILD_ID,
        candidate_evidence_id=f"evidence:{100000 + i:032x}",
        final_mention_id=f"mention:{200000 + i:032x}",
        canonical_id=f"paper-{i:04d}",
        source_field=ScientificEntitySourceField.ABSTRACT,
        source_text_sha256=source_sha,
        char_start=0,
        char_end=len(surface),
        surface_text=surface,
        baseline_prediction_evidence_id=f"evidence:{i:032x}",
        baseline_entity_type=ScientificEntityType.METHOD,
        baseline_confidence_score=0.8,
        semantic_typer_case_id=f"case-{i}",
        semantic_typer_predicted_entity_type=semantic_type,
        semantic_typer_used_baseline_fallback=fallback,
        semantic_typer_score_margin=0.2 if override else 0.05,
        h2_override_applied=override,
        final_entity_type=ScientificEntityType.MODEL if override else ScientificEntityType.METHOD,
        materialization_fingerprint_sha256=MATERIALIZATION_FINGERPRINT,
    )
    return row, source


def _write_candidate(tmp_path: Path) -> tuple[Path, dict[str, list[H2FullCorpusFinalMention]], dict[tuple[str, str], str]]:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    rows: list[H2FullCorpusFinalMention] = []
    source_texts: dict[tuple[str, str], str] = {}
    index = 1
    for stratum, count in (("override", 100), ("preserved_method", 100), ("fallback_method", 40)):
        for _ in range(count):
            row, source = _make_final_row(index, stratum)
            rows.append(row)
            source_texts[(row.canonical_id, row.source_field.value)] = source
            index += 1
    (candidate / "final_mentions.jsonl").write_text("".join(_json_line(row) for row in rows), encoding="utf-8", newline="\n")
    summary = H2FullCorpusSummary(
        build_id=CANDIDATE_BUILD_ID,
        input_document_count=61075,
        upstream_raw_mention_count=1396180,
        baseline_prediction_count=846264,
        baseline_method_count=260200,
        semantic_typer_case_count=260200,
        semantic_typer_scored_count=253481,
        semantic_typer_fallback_count=6719,
        typer_coverage_over_method_cases=0.974178,
        h2_override_count=33469,
        final_mention_count=846264,
        baseline_count_by_type={"method": 260200},
        final_count_by_type={"method": 226731, "model": 33469},
        source_field_counts={"abstract": 846264},
    )
    (candidate / "summary.json").write_text(json.dumps(summary.model_dump(mode="json"), sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    manifest = H2FullCorpusManifest(
        build_id=CANDIDATE_BUILD_ID,
        authorization_id="authorization-fixture",
        candidate_id=CANDIDATE_ID,
        candidate_fingerprint_sha256=CANDIDATE_FINGERPRINT,
        materialization_config_sha256="1" * 64,
        materialization_fingerprint_sha256=MATERIALIZATION_FINGERPRINT,
        canonical_path="data/analytics/reconciled/canonical_documents.jsonl",
        canonical_sha256=CANONICAL_SHA256,
        canonical_document_count=61075,
        upstream_runtime_config_sha256="2" * 64,
        baseline_policy_config_sha256="3" * 64,
        semantic_typer_config_sha256="4" * 64,
        semantic_typer_fingerprint_sha256="5" * 64,
        h2_threshold=0.1,
        upstream_raw_mention_count=1396180,
        baseline_prediction_count=846264,
        semantic_typer_case_count=260200,
        semantic_typer_scored_count=253481,
        semantic_typer_fallback_count=6719,
        h2_override_count=33469,
        final_mention_count=846264,
        files={},
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
        next_slice="validate_h2_full_corpus_candidate_materialization",
    )
    (candidate / "manifest.json").write_text(json.dumps(manifest.model_dump(mode="json"), sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    (candidate / "checksums.txt").write_text(
        "".join(f"{_sha(candidate / name)}  {name}\n" for name in ("final_mentions.jsonl", "manifest.json", "summary.json")),
        encoding="utf-8", newline="\n",
    )
    audit_config = load_h2_production_audit_config(AUDIT_CONFIG)
    selected = _select_final_rows(candidate, audit_config)
    return candidate, selected, source_texts


def _label_for(stratum: str, position: int, passing: bool) -> tuple[str, str | None]:
    if not passing and stratum == "override":
        return "valid_entity_span", "method" if position < 80 else "model"
    if stratum == "override":
        if position < 80:
            return "valid_entity_span", "model"
        if position < 95:
            return "valid_entity_span", "method"
        return "boundary_issue", "task"
    if stratum == "preserved_method":
        if position < 70:
            return "valid_entity_span", "method"
        if position < 90:
            return "valid_entity_span", "model"
        return "boundary_issue", "task"
    if position < 35:
        return "valid_entity_span", "method"
    return "not_an_entity", None


def _fixture(tmp_path: Path, passing: bool = True):
    candidate, selected, source_texts = _write_candidate(tmp_path)
    audit_config = load_h2_production_audit_config(AUDIT_CONFIG)
    audit_dir = tmp_path / "audit"
    cases = _build_blind_cases(audit_config, selected, source_texts)
    _write_package(audit_dir, audit_config, cases)

    stratum_by_case: dict[str, tuple[str, int]] = {}
    from radar_core.entities.scientific_entity_semantic_typer_h2_production_audit import _stable_case_id
    for stratum, rows in selected.items():
        for position, row in enumerate(rows):
            stratum_by_case[_stable_case_id(audit_config.sampling.audit_id, row.baseline_prediction_evidence_id)] = (stratum, position)

    blank_rows = [json.loads(line) for line in (audit_dir / "blank_annotations.jsonl").read_text(encoding="utf-8").splitlines()]
    completed = tmp_path / "annotations_completed.jsonl"
    for row in blank_rows:
        stratum, position = stratum_by_case[row["audit_case_id"]]
        status, entity_type = _label_for(stratum, position, passing)
        row["span_status"] = status
        row["reference_entity_type"] = entity_type
        row["annotation_confidence"] = "high"
        row["reviewer_note"] = None
        row["annotation_complete"] = True
    completed.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in blank_rows), encoding="utf-8", newline="\n")

    reference_root = tmp_path / "reference_root"
    report = freeze_h2_production_audit_reference(
        project_root=ROOT,
        config_path=REFERENCE_CONFIG,
        audit_config_path=AUDIT_CONFIG,
        audit_dir=audit_dir,
        annotations_path=completed,
        annotator_ids=["human-reviewer-1"],
        output_root=reference_root,
        execute=True,
    )
    reference_dir = Path(report["output_dir"])
    return candidate, audit_dir, reference_dir


def _kwargs(tmp_path: Path, passing: bool = True):
    candidate, audit_dir, reference_dir = _fixture(tmp_path, passing=passing)
    return dict(
        project_root=ROOT,
        config_path=CONFIG,
        audit_config_path=AUDIT_CONFIG,
        reference_config_path=REFERENCE_CONFIG,
        audit_dir=audit_dir,
        reference_dir=reference_dir,
        candidate_dir=candidate,
        output_root=tmp_path / "evaluation_root",
    )


def test_config_keeps_preregistered_gate_thresholds() -> None:
    config = load_h2_production_audit_evaluation_config(CONFIG)
    assert config.promotion_gates.min_override_reference_model_rate == 0.45
    assert config.promotion_gates.max_preserved_reference_model_rate == 0.30
    assert config.evaluation.reference_type_rate_denominator == "usable_cases_only"


def test_plan_validates_frozen_parents_without_unblinding(tmp_path: Path) -> None:
    kwargs = _kwargs(tmp_path)
    report = plan_or_execute_h2_production_audit_evaluation(**kwargs, execute=False)
    assert report["phase_complete"] is False
    assert report["reference_frozen"] is True
    assert report["candidate_prediction_files_read"] is False
    assert report["sampled_strata_reconstructed"] is False
    assert report["unblinding_executed"] is False
    assert report["quality_metrics_exposed"] is False
    assert not Path(report["output_dir"]).exists()


def test_execute_reconstructs_exact_strata_and_passes_fixture(tmp_path: Path) -> None:
    kwargs = _kwargs(tmp_path, passing=True)
    report = plan_or_execute_h2_production_audit_evaluation(**kwargs, execute=True)
    assert report["phase_complete"] is True
    assert report["override_count"] == 100
    assert report["preserved_method_count"] == 100
    assert report["fallback_method_count"] == 40
    assert report["all_hard_gates_pass"] is True
    assert report["gate_verdict"] == "pass_h2_production_audit_gate"
    assert report["production_latest_promotion_authorized"] is False


def test_boundary_issue_is_usable_and_fallback_not_entity_uses_full_stratum_denominator(tmp_path: Path) -> None:
    kwargs = _kwargs(tmp_path, passing=True)
    report = plan_or_execute_h2_production_audit_evaluation(**kwargs, execute=True)
    summary = json.loads((Path(report["output_dir"]) / "summary.json").read_text(encoding="utf-8"))
    by = {row["stratum"]: row for row in summary["strata"]}
    assert by["override"]["usable_count"] == 100
    assert by["preserved_method"]["usable_count"] == 100
    assert by["fallback_method"]["usable_count"] == 35
    assert by["fallback_method"]["unresolved_or_not_entity_rate"] == pytest.approx(5 / 40)


def test_failed_semantic_gate_is_valid_evaluation_evidence_not_authorization(tmp_path: Path) -> None:
    kwargs = _kwargs(tmp_path, passing=False)
    report = plan_or_execute_h2_production_audit_evaluation(**kwargs, execute=True)
    assert report["all_hard_gates_pass"] is False
    assert report["gate_verdict"] == "fail_h2_production_audit_gate"
    checks, validation = validate_h2_production_audit_evaluation(**{k: v for k, v in kwargs.items() if k != "output_root"}, evaluation_dir=Path(report["output_dir"]))
    assert validation["required_failed_count"] == 0
    assert validation["promotion_gate_passed"] is False
    assert validation["production_latest_promotion_authorized"] is False


def test_execute_refuses_overwrite(tmp_path: Path) -> None:
    kwargs = _kwargs(tmp_path)
    plan_or_execute_h2_production_audit_evaluation(**kwargs, execute=True)
    with pytest.raises(H2ProductionAuditEvaluationError, match="already exists"):
        plan_or_execute_h2_production_audit_evaluation(**kwargs, execute=True)


def test_strict_validator_recomputes_package_exactly(tmp_path: Path) -> None:
    kwargs = _kwargs(tmp_path)
    report = plan_or_execute_h2_production_audit_evaluation(**kwargs, execute=True)
    checks, summary = validate_h2_production_audit_evaluation(**{k: v for k, v in kwargs.items() if k != "output_root"}, evaluation_dir=Path(report["output_dir"]))
    assert summary["required_failed_count"] == 0
    assert summary["evaluation_validated"] is True
    assert summary["promotion_gate_passed"] is True
    assert all(ok for _, ok, _ in checks)


def test_validator_detects_tampered_case_evidence(tmp_path: Path) -> None:
    kwargs = _kwargs(tmp_path)
    report = plan_or_execute_h2_production_audit_evaluation(**kwargs, execute=True)
    evaluation_dir = Path(report["output_dir"])
    path = evaluation_dir / "case_evaluations.jsonl"
    path.write_text(path.read_text(encoding="utf-8").replace('"surface_text":"Entity', '"surface_text":"Tampered', 1), encoding="utf-8", newline="\n")
    _, summary = validate_h2_production_audit_evaluation(**{k: v for k, v in kwargs.items() if k != "output_root"}, evaluation_dir=evaluation_dir)
    assert summary["required_failed_count"] > 0


def test_reference_must_be_frozen_before_plan(tmp_path: Path) -> None:
    kwargs = _kwargs(tmp_path)
    reference_dir = kwargs["reference_dir"]
    manifest_path = reference_dir / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["reference_frozen"] = False
    manifest_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    # Even with a recomputed checksum, the schema/safety contract must fail closed.
    checksums = {}
    for line in (reference_dir / "checksums.txt").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        checksums[name] = digest
    checksums["manifest.json"] = _sha(manifest_path)
    (reference_dir / "checksums.txt").write_text("".join(f"{checksums[name]}  {name}\n" for name in sorted(checksums)), encoding="utf-8", newline="\n")
    with pytest.raises(Exception):
        plan_or_execute_h2_production_audit_evaluation(**kwargs, execute=False)
