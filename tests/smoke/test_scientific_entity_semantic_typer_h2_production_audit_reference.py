from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit import (
    H2ProductionAuditAnnotation,
    H2ProductionAuditManifest,
    canonical_config_sha256 as audit_config_canonical_sha256,
    load_h2_production_audit_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit_reference import (
    REFERENCE_ID,
    load_h2_production_audit_reference_config,
)
import radar_core.entities.scientific_entity_semantic_typer_h2_production_audit_reference as mod

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_audit_reference_freeze_v0.3.yaml"
AUDIT_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_audit_v0.3.yaml"


def _annotation(i: int, *, complete: bool, status: str | None = None, entity_type: str | None = None) -> H2ProductionAuditAnnotation:
    text = f"Entity{i} context"
    surface = f"Entity{i}"
    return H2ProductionAuditAnnotation(
        audit_id="scientific-entity-semantic-typer-h2-production-audit-v0.3-20261003T121605823276Z",
        audit_case_id=f"audit:{i:032x}",
        canonical_id=f"p{i}",
        source_field="title",
        source_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        source_text=text,
        char_start=0,
        char_end=len(surface),
        surface_text=surface,
        reference_entity_type=entity_type,
        span_status=status,
        annotation_confidence="high" if complete else None,
        reviewer_note=None,
        annotation_complete=complete,
    )


def _write_audit_package(tmp_path: Path) -> tuple[Path, list[H2ProductionAuditAnnotation]]:
    config = load_h2_production_audit_config(AUDIT_CONFIG)
    audit = tmp_path / "audit"
    audit.mkdir()
    blanks = [_annotation(i, complete=False) for i in range(240)]
    cases = []
    for row in blanks:
        payload = row.model_dump(mode="json")
        for key in ("reference_entity_type", "span_status", "annotation_confidence", "reviewer_note", "annotation_complete"):
            payload.pop(key)
        payload["schema_version"] = "scientific_entity_semantic_typer_h2_production_audit_case_v0.3"
        cases.append(payload)
    (audit / "audit_cases.jsonl").write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in cases), encoding="utf-8", newline="\n")
    (audit / "blank_annotations.jsonl").write_text("".join(json.dumps(x.model_dump(mode="json"), sort_keys=True) + "\n" for x in blanks), encoding="utf-8", newline="\n")
    manifest = H2ProductionAuditManifest(
        audit_id=config.sampling.audit_id,
        candidate_build_id=config.candidate.build_id,
        candidate_id=config.candidate.candidate_id,
        candidate_fingerprint_sha256=config.candidate.candidate_fingerprint_sha256,
        materialization_fingerprint_sha256=config.candidate.materialization_fingerprint_sha256,
        canonical_sha256=config.canonical_snapshot.sha256,
        canonical_document_count=config.canonical_snapshot.document_count,
        audit_config_sha256=audit_config_canonical_sha256(config),
        selection_seed_sha256=config.sampling.selection_seed_sha256,
        blind_order_seed_sha256=config.sampling.blind_order_seed_sha256,
        audit_case_count=240,
        override_count=100,
        preserved_method_count=100,
        fallback_method_count=40,
        prediction_blind=True,
        sampled_stratum_exposed_in_cases=False,
        candidate_prediction_exposed_in_cases=False,
        semantic_scores_exposed_in_cases=False,
        model_inference_executed=False,
        threshold_tuning_executed=False,
        policy_revision_executed=False,
        canonical_truth_mutated=False,
        production_latest_promotion_authorized=False,
    )
    (audit / "manifest.json").write_text(json.dumps(manifest.model_dump(mode="json"), sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    (audit / "reviewer.html").write_text("<html></html>\n", encoding="utf-8", newline="\n")
    (audit / "README.md").write_text("audit\n", encoding="utf-8", newline="\n")
    checksum_names = ("README.md", "audit_cases.jsonl", "blank_annotations.jsonl", "manifest.json", "reviewer.html")
    (audit / "checksums.txt").write_text("".join(f"{mod._sha256_file(audit/name)}  {name}\n" for name in checksum_names), encoding="utf-8", newline="\n")
    return audit, blanks


def _write_completed(tmp_path: Path, blanks: list[H2ProductionAuditAnnotation]) -> Path:
    rows = []
    for i, blank in enumerate(blanks):
        payload = blank.model_dump(mode="json")
        payload.update(
            reference_entity_type="model" if i < 80 else "method",
            span_status="valid_entity_span" if i < 227 else "not_an_entity",
            annotation_confidence="high",
            annotation_complete=True,
        )
        if i >= 227:
            payload["reference_entity_type"] = None
        rows.append(H2ProductionAuditAnnotation.model_validate(payload))
    path = tmp_path / "annotations_completed.jsonl"
    path.write_text("".join(json.dumps(x.model_dump(mode="json"), sort_keys=True) + "\n" for x in rows), encoding="utf-8", newline="\n")
    return path


def test_config_freezes_reference_without_unblinding() -> None:
    config = load_h2_production_audit_reference_config(CONFIG)
    assert config.lineage.expected_audit_case_count == 240
    assert config.outputs.reference_id == REFERENCE_ID
    assert config.safety.candidate_prediction_files_may_be_read is False
    assert config.safety.sampled_strata_may_be_reconstructed is False
    assert config.safety.unblinding_allowed is False
    assert config.safety.promotion_gate_evaluation_allowed is False
    assert config.safety.production_latest_promotion_authorized is False


def test_audit_config_text_hash_is_portable_across_crlf_checkout(tmp_path: Path) -> None:
    config = load_h2_production_audit_reference_config(CONFIG)
    lf_bytes = AUDIT_CONFIG.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    crlf_path = tmp_path / "audit_config_crlf.yaml"
    crlf_path.write_bytes(lf_bytes.replace(b"\n", b"\r\n"))
    assert mod._sha256_text_file_lf(crlf_path) == config.lineage.audit_config_file_sha256


def test_plan_validates_complete_annotations_but_writes_nothing(tmp_path: Path) -> None:
    audit, blanks = _write_audit_package(tmp_path)
    annotations = _write_completed(tmp_path, blanks)
    report = mod.freeze_h2_production_audit_reference(
        project_root=ROOT,
        config_path=CONFIG,
        audit_config_path=AUDIT_CONFIG,
        audit_dir=audit,
        annotations_path=annotations,
        annotator_ids=["human-reviewer-1"],
        output_root=tmp_path / "out",
        execute=False,
    )
    assert report["phase_complete"] is False
    assert report["plan_writes_output"] is False
    assert report["candidate_prediction_files_read"] is False
    assert report["sampled_strata_reconstructed"] is False
    assert not (tmp_path / "out").exists()


def test_freeze_rejects_incomplete_annotations(tmp_path: Path) -> None:
    audit, blanks = _write_audit_package(tmp_path)
    annotations = tmp_path / "annotations_completed.jsonl"
    annotations.write_text("".join(json.dumps(x.model_dump(mode="json"), sort_keys=True) + "\n" for x in blanks), encoding="utf-8")
    with pytest.raises(Exception):
        mod.freeze_h2_production_audit_reference(
            project_root=ROOT, config_path=CONFIG, audit_config_path=AUDIT_CONFIG,
            audit_dir=audit, annotations_path=annotations, annotator_ids=["human-reviewer-1"],
            output_root=tmp_path / "out", execute=False,
        )


def test_freeze_rejects_immutable_source_field_mutation(tmp_path: Path) -> None:
    audit, blanks = _write_audit_package(tmp_path)
    annotations = _write_completed(tmp_path, blanks)
    rows = [json.loads(line) for line in annotations.read_text(encoding="utf-8").splitlines()]
    rows[0]["canonical_id"] = "mutated"
    annotations.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in rows), encoding="utf-8")
    with pytest.raises(Exception):
        mod.freeze_h2_production_audit_reference(
            project_root=ROOT, config_path=CONFIG, audit_config_path=AUDIT_CONFIG,
            audit_dir=audit, annotations_path=annotations, annotator_ids=["human-reviewer-1"],
            output_root=tmp_path / "out", execute=False,
        )


def test_freeze_preserves_uncertain_as_valid_human_reference_state(tmp_path: Path) -> None:
    audit, blanks = _write_audit_package(tmp_path)
    annotations = _write_completed(tmp_path, blanks)
    rows = [json.loads(line) for line in annotations.read_text(encoding="utf-8").splitlines()]
    rows[0]["span_status"] = "uncertain"
    rows[0]["reference_entity_type"] = None
    rows[0]["annotation_confidence"] = "low"
    annotations.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in rows), encoding="utf-8")
    report = mod.freeze_h2_production_audit_reference(
        project_root=ROOT, config_path=CONFIG, audit_config_path=AUDIT_CONFIG,
        audit_dir=audit, annotations_path=annotations, annotator_ids=["human-reviewer-1"],
        output_root=tmp_path / "out", execute=False,
    )
    assert report["uncertain_count"] == 1
    assert report["promotion_gates_evaluated"] is False


def test_execute_writes_exact_immutable_reference_package(tmp_path: Path) -> None:
    audit, blanks = _write_audit_package(tmp_path)
    annotations = _write_completed(tmp_path, blanks)
    report = mod.freeze_h2_production_audit_reference(
        project_root=ROOT, config_path=CONFIG, audit_config_path=AUDIT_CONFIG,
        audit_dir=audit, annotations_path=annotations, annotator_ids=["human-reviewer-1"],
        output_root=tmp_path / "out", execute=True,
    )
    out = Path(report["output_dir"])
    assert report["phase_complete"] is True
    assert {p.name for p in out.iterdir()} == set(mod.REFERENCE_FILES)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["reference_frozen"] is True
    assert manifest["candidate_prediction_files_read"] is False
    assert manifest["unblinding_executed"] is False
    assert manifest["promotion_gates_evaluated"] is False


def test_execute_refuses_overwrite(tmp_path: Path) -> None:
    audit, blanks = _write_audit_package(tmp_path)
    annotations = _write_completed(tmp_path, blanks)
    kwargs = dict(project_root=ROOT, config_path=CONFIG, audit_config_path=AUDIT_CONFIG, audit_dir=audit, annotations_path=annotations, annotator_ids=["human-reviewer-1"], output_root=tmp_path / "out", execute=True)
    mod.freeze_h2_production_audit_reference(**kwargs)
    with pytest.raises(Exception):
        mod.freeze_h2_production_audit_reference(**kwargs)


def test_strict_validator_recomputes_reference_without_candidate_predictions(tmp_path: Path) -> None:
    audit, blanks = _write_audit_package(tmp_path)
    annotations = _write_completed(tmp_path, blanks)
    report = mod.freeze_h2_production_audit_reference(
        project_root=ROOT, config_path=CONFIG, audit_config_path=AUDIT_CONFIG,
        audit_dir=audit, annotations_path=annotations, annotator_ids=["human-reviewer-1"],
        output_root=tmp_path / "out", execute=True,
    )
    checks, summary = mod.validate_frozen_h2_production_audit_reference(
        project_root=ROOT, config_path=CONFIG, audit_config_path=AUDIT_CONFIG,
        audit_dir=audit, annotations_path=annotations, reference_dir=Path(report["output_dir"]),
    )
    assert all(ok for _, ok, _ in checks)
    assert summary["required_failed_count"] == 0
    assert summary["candidate_prediction_files_read"] is False
    assert summary["sampled_strata_reconstructed"] is False
    assert summary["unblinding_executed"] is False
    assert summary["promotion_gates_evaluated"] is False
    assert summary["next_slice"] == "unblind_and_evaluate_h2_production_audit_promotion_gate"


def _rewrite_checksums(audit: Path) -> None:
    checksum_names = ("README.md", "audit_cases.jsonl", "blank_annotations.jsonl", "manifest.json", "reviewer.html")
    (audit / "checksums.txt").write_text(
        "".join(f"{mod._sha256_file(audit / name)}  {name}\n" for name in checksum_names),
        encoding="utf-8",
        newline="\n",
    )


def test_parent_reviewer_html_crlf_is_portable_when_checksum_matches(tmp_path: Path) -> None:
    audit, blanks = _write_audit_package(tmp_path)
    reviewer = audit / "reviewer.html"
    reviewer.write_bytes(reviewer.read_bytes().replace(b"\n", b"\r\n"))
    _rewrite_checksums(audit)
    annotations = _write_completed(tmp_path, blanks)
    report = mod.freeze_h2_production_audit_reference(
        project_root=ROOT,
        config_path=CONFIG,
        audit_config_path=AUDIT_CONFIG,
        audit_dir=audit,
        annotations_path=annotations,
        annotator_ids=["human-reviewer-1"],
        output_root=tmp_path / "out",
        execute=False,
    )
    assert report["phase_complete"] is False
    assert report["candidate_prediction_files_read"] is False


def test_parent_semantic_jsonl_still_requires_lf_even_if_checksum_matches(tmp_path: Path) -> None:
    audit, blanks = _write_audit_package(tmp_path)
    target = audit / "blank_annotations.jsonl"
    target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
    _rewrite_checksums(audit)
    annotations = _write_completed(tmp_path, blanks)
    with pytest.raises(mod.H2ProductionAuditReferenceError, match="Audit file must be UTF-8 LF: blank_annotations.jsonl"):
        mod.freeze_h2_production_audit_reference(
            project_root=ROOT,
            config_path=CONFIG,
            audit_config_path=AUDIT_CONFIG,
            audit_dir=audit,
            annotations_path=annotations,
            annotator_ids=["human-reviewer-1"],
            output_root=tmp_path / "out",
            execute=False,
        )
