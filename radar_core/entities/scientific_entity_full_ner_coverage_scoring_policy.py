"""9C preregistered scoring policy: bind frozen reference to fixed rules before unblind.

This module only reads 9B reference files and trusted *pointer metadata*, never the
large production prediction file. All outputs are one-shot immutable metadata.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

from radar_core.contracts.scientific_entity_full_ner_coverage_scoring_policy import (
    ScoringPolicyRecord, ScoringPolicyManifest,
)
from radar_core.contracts.scientific_entity_full_ner_coverage_reference import (
    ReferenceManifest, ReferenceSummary,
)
from radar_core.entities.scientific_entity_full_ner_coverage_reference import (
    validate_frozen_reference,
)


class FullNerScoringPolicyError(RuntimeError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_sha(path: Path) -> str:
    return _sha(path.read_bytes())


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise FullNerScoringPolicyError("Invalid configured path")
    out = (root / relative).resolve()
    if not out.is_relative_to(root.resolve()):
        raise FullNerScoringPolicyError(f"Path outside project: {relative}")
    return out


RULE_KEYS = (
    "sampling_interpretation", "taxonomy", "primary_uncertainty_handling",
    "uncertainty_overlap_condition", "uncertainty_certain_precedence",
    "span_exact_match", "span_relaxed_match", "relaxed_iou_threshold",
    "matching", "matching_scope", "allow_nested_gold_spans", "type_aware_matching",
    "prediction_duplicates", "scoring_panels", "primary_panel", "aggregation",
    "report_title_abstract_separately", "per_type_metrics", "macro_f1",
    "zero_denominator", "metrics", "uncertainty_sensitivity",
    "error_diagnostics", "quality_acceptance_thresholds_precommitted",
)

# These safeguards make critical pre-registration choices fail closed if edited.
EXPECTED_RULES = {
    "taxonomy": ["task", "method", "dataset", "metric", "model", "domain"],
    "scoring_panels": ["span_only_exact", "span_only_relaxed", "typed_exact", "typed_relaxed"],
    "primary_panel": "typed_exact",
    "relaxed_iou_threshold": 0.5,
    "primary_uncertainty_handling": "omit_uncertain_references_and_ignore_predictions_overlapping_uncertain_only",
    "uncertainty_overlap_condition": "positive_character_intersection",
    "uncertainty_certain_precedence": "keep_predictions_touching_any_certain_reference",
    "matching": "maximum_cardinality_then_maximum_total_iou_then_stable_tie_break",
    "matching_scope": "separately_within_each_audit_field",
    "allow_nested_gold_spans": True,
    "type_aware_matching": "require_identical_entity_type",
    "prediction_duplicates": "count_as_separate_predictions",
    "aggregation": "micro_pooled_over_balanced_fields",
    "sampling_interpretation": "balanced_60_title_60_abstract_not_corpus_prevalence_weighted",
    "report_title_abstract_separately": True,
    "quality_acceptance_thresholds_precommitted": False,
    "zero_denominator": "null_not_zero",
    "span_exact_match": "equal_start_and_end",
    "span_relaxed_match": "character_iou_at_least_0_5",
    "per_type_metrics": True,
    "macro_f1": "mean_across_reference_supported_types_only",
    "metrics": ["precision", "recall", "f1", "tp", "fp", "fn", "reference_support", "prediction_count"],
    "uncertainty_sensitivity": "report_counts_and_alternative_include_uncertain_as_gold_separately",
    "error_diagnostics": ["type_only_exact_span", "boundary_only_same_type", "boundary_and_type", "unmatched_reference", "unmatched_prediction", "nested_overlap"],
}


def load_policy_config(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FullNerScoringPolicyError(f"Could not load policy config: {path}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != "scientific_entity_full_ner_coverage_scoring_policy_config_v0.1":
        raise FullNerScoringPolicyError("Invalid 9C config schema")
    if any(data.get(key) is not False for key in (
        "production_predictions_read_in_this_slice", "unblind_authorized_in_this_slice",
        "reference_mutation_allowed", "production_mutation_allowed",
    )):
        raise FullNerScoringPolicyError("9C must not read/unblind/mutate production or reference")
    if any(key not in data for key in RULE_KEYS):
        raise FullNerScoringPolicyError("Incomplete policy rule set")
    for key, expected in EXPECTED_RULES.items():
        if type(data.get(key)) is not type(expected) or data[key] != expected:
            raise FullNerScoringPolicyError(f"Frozen preregistration invariant drift: {key}")
    if data.get("expected_frozen_field_count") != 120 or data.get("expected_frozen_mention_count") != 972 or data.get("expected_uncertain_mention_count") != 68 or data.get("expected_overlap_pair_count") != 5:
        raise FullNerScoringPolicyError("Frozen reference counts changed")
    if data.get("expected_annotations_sha256") != "95e231b4187de26fa57d9c71b3ec74c4d5303ce3c22c5a96560059c948235c75":
        raise FullNerScoringPolicyError("Frozen annotation reference hash changed")
    if data.get("expected_final_mentions_sha256") != "518f3984d3dcd2aa5e2a84c96eec2fadce8b6dc6b49eef0d7a908533145394c1":
        raise FullNerScoringPolicyError("Trusted production target hash changed")
    return data


def _preflight(config_path: Path, root: Path) -> dict[str, Any]:
    cfg = load_policy_config(config_path)
    reference_config = _path(root, cfg["reference_config_path"])
    validation = validate_frozen_reference(reference_config, root)
    if validation.get("required_failed_count") != 0 or validation.get("reference_validated") is not True:
        raise FullNerScoringPolicyError(f"9B strict validation not green: {validation.get('error')}")
    ref_dir = _path(root, cfg["reference_dir"])
    ref_manifest_path = ref_dir / "manifest.json"
    ref_summary_path = ref_dir / "summary.json"
    ref_ann_path = ref_dir / "annotations.jsonl"
    ref_manifest = ReferenceManifest.model_validate_json(ref_manifest_path.read_bytes())
    ref_summary = ReferenceSummary.model_validate_json(ref_summary_path.read_bytes())
    if (ref_manifest.reference_id != cfg["reference_id"] or ref_manifest.audit_id != cfg["audit_id"] or
        ref_manifest.annotations_sha256 != cfg["expected_annotations_sha256"] or
        _file_sha(ref_ann_path) != cfg["expected_annotations_sha256"] or
        ref_manifest.trusted_final_mentions_sha256 != cfg["expected_final_mentions_sha256"] or
        ref_manifest.trusted_candidate_build_id != cfg["expected_candidate_build_id"]):
        raise FullNerScoringPolicyError("Frozen 9B lineage mismatch")
    if (ref_summary.field_count != 120 or ref_summary.title_count != 60 or ref_summary.abstract_count != 60 or
        ref_summary.mention_count != 972 or ref_summary.uncertain_mention_count != 68 or
        ref_summary.overlap_pair_count != 5 or not ref_summary.prediction_blind):
        raise FullNerScoringPolicyError("Frozen reference summary mismatch")
    pointer_path = _path(root, cfg["trusted_latest_pointer_path"])
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    if (pointer.get("state") != "trusted_latest" or
        pointer.get("candidate_build_id") != cfg["expected_candidate_build_id"] or
        pointer.get("candidate_final_mentions_sha256") != cfg["expected_final_mentions_sha256"] or
        pointer.get("final_mention_count") != 846264):
        raise FullNerScoringPolicyError("Trusted latest pointer metadata changed")
    return {
        "config": cfg, "config_sha": _file_sha(config_path),
        "reference_manifest_sha": _file_sha(ref_manifest_path),
        "reference_summary_sha": _file_sha(ref_summary_path),
        "reference_annotations_sha": _file_sha(ref_ann_path),
        "pointer_sha": _file_sha(pointer_path),
        "reference_summary": ref_summary,
    }


def _content(prep: dict[str, Any]) -> dict[str, bytes]:
    cfg = prep["config"]
    policy = ScoringPolicyRecord(
        schema_version="scientific_entity_full_ner_coverage_scoring_policy_record_v0.1",
        policy_id=cfg["policy_id"], audit_id=cfg["audit_id"], reference_id=cfg["reference_id"],
        reference_annotations_sha256=prep["reference_annotations_sha"],
        trusted_candidate_build_id=cfg["expected_candidate_build_id"],
        trusted_final_mentions_sha256=cfg["expected_final_mentions_sha256"],
        scoring_rules={key: cfg[key] for key in RULE_KEYS},
        original_field_count=120, frozen_mention_count=972, uncertain_mention_count=68,
        overlap_pair_count=5, production_predictions_read=False, unblind_authorized=False,
        production_mutated=False, reference_mutated=False,
    )
    readme = (
        "# Preregistered Full NER Coverage Audit v0.1 Scoring Policy\n\n"
        f"Policy ID: `{cfg['policy_id']}`\n\n"
        f"Reference ID: `{cfg['reference_id']}`\n\n"
        "Prediction-blind preregistration ONLY. No model predictions read, no unblind, "
        "no evaluation/tuning/promotion.\n\n"
        "Primary panel: typed_exact; separate span-only/relaxed panels. "
        "Uncertain mentions excluded from primary reference recall, "
        "uncertain-only overlapping predictions ignored; retain predictions touching certain gold.\n\n"
        "Balanced 60 title / 60 abstract fields: NOT a population-weighted corpus estimate.\n"
    ).encode("utf-8")
    files = {"README.md":readme, "policy.json":_json_bytes(policy.model_dump(mode="json"))}
    manifest = ScoringPolicyManifest(
        schema_version="scientific_entity_full_ner_coverage_scoring_policy_manifest_v0.1",
        policy_id=cfg["policy_id"], audit_id=cfg["audit_id"], reference_id=cfg["reference_id"],
        config_sha256=prep["config_sha"], reference_manifest_sha256=prep["reference_manifest_sha"],
        reference_annotations_sha256=prep["reference_annotations_sha"],
        reference_summary_sha256=prep["reference_summary_sha"],
        latest_pointer_sha256=prep["pointer_sha"],policy_sha256=_sha(files["policy.json"]),
        policy_preregistered=True, production_predictions_read=False,
        unblind_executed=False, reference_mutated=False, production_mutated=False,
        next_slice="build_full_ner_coverage_unblind_evaluation",
        files={name:_sha(data) for name,data in files.items()},
    )
    files["manifest.json"] = _json_bytes(manifest.model_dump(mode="json"))
    files["checksums.txt"] = "".join(f"{_sha(files[name])}  {name}\n" for name in sorted(files)).encode("utf-8")
    return files


def plan_scoring_policy(config_path: Path, root: Path) -> dict[str, Any]:
    prep = _preflight(config_path, root)
    cfg = prep["config"]
    out = _path(root, cfg["output_dir"])
    return {
        "report":"scientific_entity_full_ner_coverage_scoring_policy_v01",
        "mode":"plan", "phase_complete":False,
        "policy_id":cfg["policy_id"],"reference_id":cfg["reference_id"],
        "reference_strict_validated":True,"reference_annotations_sha256":prep["reference_annotations_sha"],
        "frozen_field_count":120,"frozen_mention_count":972,"uncertain_mention_count":68,
        "scoring_primary_panel":"typed_exact","relaxed_iou_threshold":0.5,
        "uncertain_policy_preregistered":True,"balanced_sampling_interpretation_preregistered":True,
        "trusted_latest_pointer_metadata_verified":True,
        "production_prediction_file_read":False,"unblind_executed":False,
        "reference_mutated":False,"production_mutated":False,
        "policy_record_already_exists":out.exists(), "plan_writes_output":False,
        "output_dir":str(out),
        "next_slice":"commit_full_ner_scoring_policy_tooling_before_execute",
    }


def execute_scoring_policy(config_path: Path, root: Path) -> dict[str, Any]:
    cfg = load_policy_config(config_path)
    out = _path(root,cfg["output_dir"])
    if out.exists():
        raise FullNerScoringPolicyError(f"Immutable policy package already exists: {out}")
    prep = _preflight(config_path,root)
    files = _content(prep)
    # Refuse if a parent changes while the exact metadata package is prepared.
    if any((_file_sha(_path(root, path)) != prep[key]) for path, key in (
        (cfg["trusted_latest_pointer_path"], "pointer_sha"),
        (cfg["reference_dir"] + "/manifest.json", "reference_manifest_sha"),
        (cfg["reference_dir"] + "/summary.json", "reference_summary_sha"),
        (cfg["reference_dir"] + "/annotations.jsonl", "reference_annotations_sha"),
    )) or _file_sha(config_path) != prep["config_sha"]:
        raise FullNerScoringPolicyError("Trusted lineage changed before atomic freeze")
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".full_ner_scoring_policy_staging_",dir=out.parent))
    try:
        for name,data in files.items():
            (staging/name).write_bytes(data)
        if any((staging/name).read_bytes()!=data for name,data in files.items()):
            raise FullNerScoringPolicyError("Scoring policy staging content drift")
        if out.exists():
            raise FullNerScoringPolicyError("Immutable policy destination appeared during execute")
        os.replace(staging,out)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {
        "report":"scientific_entity_full_ner_coverage_scoring_policy_v01",
        "mode":"execute","phase_complete":True,"policy_id":cfg["policy_id"],
        "policy_preregistered":True,"reference_strict_validated":True,
        "production_prediction_file_read":False,"unblind_executed":False,
        "reference_mutated":False,"production_mutated":False,
        "output_dir":str(out),
        "next_slice":"validate_immutable_full_ner_scoring_policy",
    }


def validate_scoring_policy(config_path:Path,root:Path)->dict[str,Any]:
    cfg=load_policy_config(config_path)
    out=_path(root,cfg["output_dir"])
    checks:list[tuple[str,bool]]=[]
    checks.append(("policy_directory_exists",out.is_dir()))
    expected={"README.md","policy.json","manifest.json","checksums.txt"}
    checks.append(("exact_file_layout",out.is_dir() and {p.name for p in out.iterdir()}==expected))
    error=None
    try:
        prep=_preflight(config_path,root)
        checks.append(("frozen_reference_still_valid",True))
        expected_data=_content(prep)
        if not out.is_dir():
            raise FullNerScoringPolicyError("Immutable scoring policy directory missing")
        actual={name:(out/name).read_bytes() for name in sorted(expected)}
        for name in sorted(expected):
            checks.append((f"lf:{name}",actual[name].endswith(b"\n") and b"\r" not in actual[name]))
            checks.append((f"recompute_exact:{name}",actual[name]==expected_data[name]))
        ledger_lines=actual["checksums.txt"].decode("utf-8").splitlines()
        checks.append(("checksum_ledger_exact",ledger_lines==[f"{_sha(actual[name])}  {name}" for name in sorted(expected-{"checksums.txt"})]))
        manifest=ScoringPolicyManifest.model_validate_json(actual["manifest.json"])
        policy=ScoringPolicyRecord.model_validate_json(actual["policy.json"])
        checks.append(("schema_identity",manifest.policy_id==policy.policy_id==cfg["policy_id"] and manifest.reference_id==policy.reference_id==cfg["reference_id"]))
        checks.append(("policy_integrity",manifest.policy_sha256==_sha(actual["policy.json"]) and manifest.files=={name:_sha(actual[name]) for name in ("README.md","policy.json")}))
        checks.append(("no_unblind_or_mutation",not manifest.production_predictions_read and not manifest.unblind_executed and not manifest.reference_mutated and not manifest.production_mutated and not policy.production_predictions_read and not policy.unblind_authorized))
        checks.append(("rule_lock",policy.scoring_rules=={key:cfg[key] for key in RULE_KEYS}))
    except (OSError,ValueError,KeyError,TypeError,FullNerScoringPolicyError) as exc:
        error=str(exc)
        checks.append(("policy_integrity_read",False))
    failed=[name for name, passed in checks if not passed]
    return {
        "report":"scientific_entity_full_ner_coverage_scoring_policy_v01",
        "policy_id":cfg["policy_id"],"checks":[{"name":name,"passed":ok} for name,ok in checks],
        "policy_validated":not failed,"policy_preregistered":not failed,
        "production_prediction_file_read":False,"unblind_executed":False,
        "total_checks":len(checks),"required_failed_count":len(failed),"error":error,
        "next_slice":"build_full_ner_coverage_unblind_evaluation" if not failed else "investigate_scoring_policy",
    }
