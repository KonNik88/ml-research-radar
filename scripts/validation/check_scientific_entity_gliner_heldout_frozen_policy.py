from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntityEvidenceManifest,
    ScientificEntityMentionEvidence,
    build_evidence_id,
    build_extractor_fingerprint,
)
from radar_core.contracts.scientific_entity_gliner_frozen_policy import ScientificEntityFrozenPolicyEvidenceLineage
from radar_core.contracts.scientific_entity_gliner_heldout_policy import ScientificEntityGLiNERHeldoutPolicyDerivationManifest
from radar_core.entities.scientific_entity_gliner_calibration import filter_predictions
from radar_core.entities.scientific_entity_gliner_heldout_policy import load_config

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_gliner_heldout_frozen_policy_v0.1.yaml"
REQUIRED_FILES = {
    "mentions.jsonl", "manifest.json", "schema.json", "data_quality_summary.json",
    "README.md", "derivation_manifest.json", "evidence_lineage.jsonl", "checksums.txt"
}


def _resolve(path: Path | str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p.resolve()


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    x = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x, dict):
        raise ValueError(path)
    return x


def _jsonl(path: Path) -> list[dict[str, Any]]:
    out=[]
    for i,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip():
            raise ValueError(f"blank line {path}:{i}")
        x=json.loads(line)
        if not isinstance(x,dict):
            raise ValueError(f"non-object {path}:{i}")
        out.append(x)
    return out


def _parse_checksums(path: Path) -> dict[str, str]:
    out={}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest,name=line.split("  ",1)
        out[name]=digest
    return out


def validate(*, build_dir: Path, config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config=load_config(config_path.resolve())
    build_dir=build_dir.resolve()
    checks: list[tuple[str,bool]]=[]
    def check(name: str, ok: bool):
        checks.append((name,bool(ok)))

    check("build_dir_exists", build_dir.is_dir())
    actual_files={p.name for p in build_dir.iterdir() if p.is_file()} if build_dir.is_dir() else set()
    check("output_files_exact", actual_files == REQUIRED_FILES)
    for name in REQUIRED_FILES:
        check(f"file_exists:{name}", (build_dir/name).is_file())
    if not all(ok for _,ok in checks):
        failed=[n for n,ok in checks if not ok]
        return {"ok":False,"total_checks":len(checks),"required_failed_count":len(failed),"required_failed_checks":failed}

    manifest=ScientificEntityEvidenceManifest.model_validate(_json(build_dir/"manifest.json"))
    deriv=ScientificEntityGLiNERHeldoutPolicyDerivationManifest.model_validate(_json(build_dir/"derivation_manifest.json"))
    quality=_json(build_dir/"data_quality_summary.json")
    mentions=tuple(ScientificEntityMentionEvidence.model_validate(x) for x in _jsonl(build_dir/"mentions.jsonl"))
    lineage=tuple(ScientificEntityFrozenPolicyEvidenceLineage.model_validate(x) for x in _jsonl(build_dir/"evidence_lineage.jsonl"))
    checksums=_parse_checksums(build_dir/"checksums.txt")

    check("manifest_build_matches_dir", manifest.build_id == build_dir.name)
    check("derivation_build_matches_manifest", deriv.build_id == manifest.build_id)
    check("manifest_fingerprint_recomputes", build_extractor_fingerprint(manifest.extractor) == manifest.extractor_fingerprint)
    check("manifest_mentions_sha", manifest.mentions_sha256 == _sha(build_dir/"mentions.jsonl"))
    check("manifest_mention_count", manifest.mention_count == len(mentions) == config.parent.expected_selected_prediction_count)
    check("derivation_review_id", deriv.heldout_review_id == config.heldout.review_id)
    check("derivation_document_count", deriv.heldout_document_count == config.heldout.expected_document_count)
    check("derivation_policy", deriv.policy == config.policy_origin.policy)
    check("derivation_trial", deriv.selected_trial_id == config.policy_origin.selected_trial_id)
    check("derivation_counts", (deriv.input_prediction_count,deriv.selected_prediction_count,deriv.rejected_prediction_count)==(config.parent.expected_input_prediction_count,config.parent.expected_selected_prediction_count,config.parent.expected_rejected_prediction_count))
    check("derivation_lineage_sha", deriv.lineage_sha256 == _sha(build_dir/"evidence_lineage.jsonl"))
    check("derivation_lineage_count", deriv.lineage_count == len(lineage) == len(mentions))
    check("quality_counts", (quality.get("input_prediction_count"),quality.get("selected_prediction_count"),quality.get("rejected_prediction_count")) == (config.parent.expected_input_prediction_count,config.parent.expected_selected_prediction_count,config.parent.expected_rejected_prediction_count))
    check("quality_no_inference", quality.get("model_inference_executed") is False)
    check("quality_no_tuning", quality.get("threshold_tuning_executed") is False)
    check("quality_no_reference_mutation", quality.get("heldout_references_mutated") is False)

    expected_checksum_files=REQUIRED_FILES-{"checksums.txt"}
    check("checksums_cover_exact_files", set(checksums)==expected_checksum_files)
    for name in sorted(expected_checksum_files):
        check(f"checksum_matches:{name}", checksums.get(name)==_sha(build_dir/name))

    parent_dir=_resolve(config.parent.build_root)/config.parent.build_id
    parent_manifest=ScientificEntityEvidenceManifest.model_validate(_json(parent_dir/"manifest.json"))
    parent_mentions=tuple(ScientificEntityMentionEvidence.model_validate(x) for x in _jsonl(parent_dir/"mentions.jsonl"))
    check("parent_build_id", parent_manifest.build_id == config.parent.build_id == deriv.parent_build_id)
    check("parent_mentions_sha", deriv.parent_mentions_sha256 == _sha(parent_dir/"mentions.jsonl"))
    check("parent_count", len(parent_mentions)==config.parent.expected_input_prediction_count)
    expected=filter_predictions(parent_mentions, policy=config.policy_origin.policy, input_threshold=config.policy_origin.input_threshold)
    check("recomputed_selected_count", len(expected)==config.parent.expected_selected_prediction_count)
    expected_by_mention={x.mention_id:x for x in expected}
    actual_by_mention={x.mention_id:x for x in mentions}
    check("selected_mention_set_exact", set(actual_by_mention)==set(expected_by_mention))
    lineage_by_mention={x.mention_id:x for x in lineage}
    check("lineage_mention_set_exact", set(lineage_by_mention)==set(expected_by_mention))
    for mention_id,parent in expected_by_mention.items():
        actual=actual_by_mention.get(mention_id)
        lin=lineage_by_mention.get(mention_id)
        check(f"row_exists:{mention_id}", actual is not None and lin is not None)
        if actual is None or lin is None:
            continue
        check(f"span_preserved:{mention_id}", (actual.canonical_id,actual.source_field,actual.source_text_sha256,actual.char_start,actual.char_end,actual.surface_text,actual.entity_type)==(parent.canonical_id,parent.source_field,parent.source_text_sha256,parent.char_start,parent.char_end,parent.surface_text,parent.entity_type))
        check(f"confidence_preserved:{mention_id}", (actual.confidence_kind,actual.confidence_score)==(parent.confidence_kind,parent.confidence_score))
        check(f"mention_id_preserved:{mention_id}", actual.mention_id==parent.mention_id)
        expected_evidence=build_evidence_id(mention_id=parent.mention_id, extractor_fingerprint=manifest.extractor_fingerprint)
        check(f"evidence_id_recomputed:{mention_id}", actual.evidence_id==expected_evidence and actual.evidence_id!=parent.evidence_id)
        check(f"lineage_correct:{mention_id}", lin.parent_build_id==parent_manifest.build_id and lin.parent_evidence_id==parent.evidence_id and lin.candidate_evidence_id==actual.evidence_id)

    failed=[n for n,ok in checks if not ok]
    return {
        "ok":not failed,
        "report":"scientific_entity_gliner_heldout_frozen_policy",
        "total_checks":len(checks),
        "required_failed_count":len(failed),
        "required_failed_checks":failed,
        "build_id":manifest.build_id,
        "heldout_review_id":deriv.heldout_review_id,
        "input_prediction_count":deriv.input_prediction_count,
        "selected_prediction_count":deriv.selected_prediction_count,
        "rejected_prediction_count":deriv.rejected_prediction_count,
        "next_slice":"run_one_heldout_evaluation_v0.1" if not failed else None,
    }


def main(argv: Sequence[str] | None=None) -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--build-dir",type=Path,required=True)
    p.add_argument("--config",type=Path,default=DEFAULT_CONFIG)
    p.add_argument("--strict",action="store_true")
    p.add_argument("--no-write-reports",action="store_true")
    args=p.parse_args(argv)
    report=validate(build_dir=args.build_dir,config_path=args.config)
    prefix="OK" if report["ok"] else "FAILED"
    for key in ("report","total_checks","required_failed_count","build_id","heldout_review_id","input_prediction_count","selected_prediction_count","rejected_prediction_count","next_slice"):
        if key in report:
            print(f"[{prefix}] {key}={report[key]}")
    if report.get("required_failed_checks"):
        print(f"[{prefix}] required_failed_checks:")
        for x in report["required_failed_checks"]:
            print(f"- {x}")
    return 1 if args.strict and not report["ok"] else 0


if __name__=="__main__":
    raise SystemExit(main())
