"""Fail-closed freeze of completed blind full-field NER annotations.

No production predictions are read. Parent 9A is checked by its strict validator,
and all 120 annotation rows must exactly match the immutable sampled fields.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from radar_core.contracts.scientific_entity_full_ner_coverage_audit import (
    FullNerCoverageAnnotationRow,
    FullNerCoverageAuditField,
)
from radar_core.contracts.scientific_entity_full_ner_coverage_reference import (
    ReferenceManifest,
    ReferenceSummary,
)
from radar_core.entities.scientific_entity_full_ner_coverage_audit import (
    validate_sample_package,
)


class FullNerReferenceError(RuntimeError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _bytes_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _rel(repo_root: Path, path: Path) -> str:
    return str(path.relative_to(repo_root)).replace("\\", "/")


def _path(repo_root: Path, value: str) -> Path:
    target = (repo_root / value).resolve()
    if not target.is_relative_to(repo_root.resolve()):
        raise FullNerReferenceError("Configured path escapes repository")
    return target


def load_reference_config(config_path: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("schema_version") != "scientific_entity_full_ner_coverage_reference_config_v0.1":
        raise FullNerReferenceError("Invalid reference configuration")
    if config.get("unblind_authorized_in_this_slice") is not False or config.get("production_prediction_files_read_in_this_slice") is not False:
        raise FullNerReferenceError("This slice must remain strictly prediction-blind")
    return config


def _parse_file(path: Path, model: type) -> list[Any]:
    if not path.is_file():
        raise FullNerReferenceError(f"Missing file: {path}")
    raw = path.read_bytes()
    if not raw or not raw.endswith(b"\n") or b"\r" in raw:
        raise FullNerReferenceError(f"Expected nonempty LF-terminated UTF-8 JSONL: {path}")
    try:
        return [model.model_validate_json(line) for line in raw.split(b"\n")[:-1]]
    except (ValueError, UnicodeDecodeError) as exc:
        raise FullNerReferenceError(f"Invalid JSONL schema: {path}") from exc


def _overlaps(row: FullNerCoverageAnnotationRow) -> int:
    spans = sorted((m.char_start, m.char_end) for m in row.mentions)
    n = 0
    for i, (start, end) in enumerate(spans):
        for next_start, next_end in spans[i + 1:]:
            if next_start >= end:
                break
            if next_end > start:
                n += 1
    return n


def _summary(config: dict[str, Any], rows: list[FullNerCoverageAnnotationRow]) -> ReferenceSummary:
    types = Counter(m.entity_type for row in rows for m in row.mentions)
    uncertain = Counter(m.entity_type for row in rows for m in row.mentions if m.uncertain)
    return ReferenceSummary(
        schema_version="scientific_entity_full_ner_coverage_reference_summary_v0.1",
        audit_id=config["audit_id"], reference_id=config["reference_id"],
        field_count=len(rows), title_count=sum(r.source_field == "title" for r in rows),
        abstract_count=sum(r.source_field == "abstract" for r in rows),
        mention_count=sum(map(lambda r: len(r.mentions), rows)),
        uncertain_mention_count=sum(bool(m.uncertain) for r in rows for m in r.mentions),
        fields_with_uncertain_mentions=sum(any(m.uncertain for m in r.mentions) for r in rows),
        overlap_pair_count=sum(_overlaps(r) for r in rows),
        entity_type_counts=dict(sorted(types.items())),
        uncertain_entity_type_counts=dict(sorted(uncertain.items())),
        annotation_complete=all(r.annotation_complete for r in rows),
        uncertain_flags_preserved=True, prediction_blind=True,
        production_predictions_read=False, future_unblind_not_executed=True,
    )


def _preflight(config: dict[str, Any], repo_root: Path, annotations_path: Path | None = None, *, check_workspace_sha: bool = True) -> dict[str, Any]:
    sample_path = _path(repo_root, config["parent_sample_dir"])
    parent_config = _path(repo_root, config["parent_sampling_config_path"])
    parent_guide = _path(repo_root, config["parent_annotation_guide_path"])
    sample_validation = validate_sample_package(parent_config, repo_root, parent_guide)
    if sample_validation.get("required_failed_count") != 0 or not sample_validation.get("sample_validated"):
        raise FullNerReferenceError("Immutable 9A sample strict validation failed")
    manifest_path = sample_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("audit_id") != config["audit_id"] or manifest.get("prediction_blind") is not True or manifest.get("production_prediction_file_read") is not False:
        raise FullNerReferenceError("Parent 9A sample identity/blindness mismatch")
    fields = _parse_file(sample_path / "audit_fields.jsonl", FullNerCoverageAuditField)
    source = annotations_path.resolve() if annotations_path else _path(repo_root, config["working_annotation_path"])
    if not source.is_relative_to(repo_root.resolve()):
        raise FullNerReferenceError("Annotation source must live inside repository")
    raw = source.read_bytes()
    if check_workspace_sha and _sha(raw) != config["expected_annotation_sha256"]:
        raise FullNerReferenceError(f"Completed annotation byte SHA mismatch: actual={_sha(raw)} expected={config['expected_annotation_sha256']}")
    rows = _parse_file(source, FullNerCoverageAnnotationRow)
    if len(rows) != len(fields) or len(rows) != config["expected_total_fields"]:
        raise FullNerReferenceError("Annotation field count does not match sample")
    fixed_keys = ("audit_id", "audit_case_id", "canonical_id", "source_field", "source_text", "source_text_sha256")
    for i, (row, field) in enumerate(zip(rows, fields, strict=True), 1):
        if any(getattr(row, key) != getattr(field, key) for key in fixed_keys):
            raise FullNerReferenceError(f"Annotation identity/text/order does not match 9A audit_fields at row {i}")
        if not row.annotation_complete:
            raise FullNerReferenceError(f"Incomplete annotation row {i}")
        seen: set[tuple[int,int,str]] = set()
        for mention in row.mentions:
            if mention.uncertain and (not mention.reviewer_note or not mention.reviewer_note.strip()):
                raise FullNerReferenceError(f"Uncertain mention without explanation at row {i}")
            key = (mention.char_start, mention.char_end, mention.entity_type)
            if key in seen:
                raise FullNerReferenceError(f"Duplicate mention at row {i}: {key}")
            seen.add(key)
    summary = _summary(config, rows)
    for key, actual, expected_key in [
        ("title_count", summary.title_count, "expected_title_fields"),
        ("abstract_count", summary.abstract_count, "expected_abstract_fields"),
        ("mention_count", summary.mention_count, "expected_total_mentions"),
        ("uncertain_mention_count", summary.uncertain_mention_count, "expected_uncertain_mentions"),
        ("overlap_pair_count", summary.overlap_pair_count, "expected_overlap_pairs"),
    ]:
        if actual != config[expected_key]:
            raise FullNerReferenceError(f"{key} mismatch: actual={actual} expected={config[expected_key]}")
    return {
        "source": source, "raw": raw, "rows": rows, "summary": summary,
        "sample_manifest_sha256": _file_sha(manifest_path),
        "audit_fields_sha256": _file_sha(sample_path / "audit_fields.jsonl"),
        "sample_manifest": manifest,
    }


def _readme(config: dict[str, Any], summary: ReferenceSummary) -> bytes:
    return (f"# Full NER Coverage Audit v0.1 — Frozen Annotation Reference\n\n"
        f"Audit ID: `{config['audit_id']}`\n\n"
        f"Reference ID: `{config['reference_id']}`\n\n"
        f"Fields: {summary.field_count} (titles={summary.title_count}; abstracts={summary.abstract_count})\n\n"
        f"Mentions: {summary.mention_count}; uncertain={summary.uncertain_mention_count}; "
        f"fields with uncertainty={summary.fields_with_uncertain_mentions}.\n\n"
        "This is a prediction-blind immutable snapshot of human annotation, NOT a tuning set.\n"
        "Uncertain mentions are preserved as unresolved annotations and must not be treated as unequivocal gold.\n"
        "Unblind/evaluation requires a separate pre-registered scoring policy and slice.\n"
        "No model inference, production update, publication, or threshold revision occurs here.\n").encode("utf-8")


def _content(config: dict[str, Any], repo_root: Path, prepared: dict[str, Any]) -> dict[str, bytes]:
    summary = prepared["summary"]
    base = {
        "README.md": _readme(config, summary),
        "annotations.jsonl": prepared["raw"],
        "summary.json": _bytes_json(summary.model_dump(mode="json")),
    }
    parent = prepared["sample_manifest"]
    manifest = ReferenceManifest(
        schema_version="scientific_entity_full_ner_coverage_reference_manifest_v0.1",
        audit_id=config["audit_id"], reference_id=config["reference_id"],
        sample_manifest_sha256=prepared["sample_manifest_sha256"],
        audit_fields_sha256=prepared["audit_fields_sha256"],
        annotations_sha256=_sha(prepared["raw"]),
        reference_summary_sha256=_sha(base["summary.json"]),
        trusted_candidate_build_id=parent["trusted_candidate_build_id"],
        trusted_final_mentions_sha256=parent["trusted_final_mentions_sha256"],
        canonical_sha256=parent["canonical_sha256"],
        source_working_path=_rel(repo_root, prepared["source"]),
        source_working_sha256=_sha(prepared["raw"]),
        complete_annotation_count=summary.field_count,
        uncertainty_policy="preserve_as_unresolved_for_preregistered_scoring",
        unblinding_executed=False, production_prediction_files_read=False,
        canonical_mutated=False, production_latest_mutated=False,
        reference_frozen=True, next_slice="preregister_full_ner_coverage_scoring_before_unblind",
        files={name: _sha(data) for name, data in base.items()},
    )
    base["manifest.json"] = _bytes_json(manifest.model_dump(mode="json"))
    base["checksums.txt"] = "".join(f"{_sha(base[name])}  {name}\n" for name in sorted(base) if name != "checksums.txt").encode("utf-8")
    return base


def plan_reference_freeze(config_path: Path, repo_root: Path, annotations_path: Path | None = None) -> dict[str, Any]:
    config = load_reference_config(config_path)
    prep = _preflight(config, repo_root, annotations_path)
    output = _path(repo_root, config["output_dir"])
    return {
        "report": "scientific_entity_full_ner_coverage_reference_v01",
        "mode": "plan", "phase_complete": False,
        "audit_id": config["audit_id"], "reference_id": config["reference_id"],
        "sample_validated": True, "annotations_match_immutable_sample": True,
        "annotation_sha256": _sha(prep["raw"]),
        "annotation_complete_count": prep["summary"].field_count,
        "annotation_mention_count": prep["summary"].mention_count,
        "uncertain_mention_count": prep["summary"].uncertain_mention_count,
        "fields_with_uncertain": prep["summary"].fields_with_uncertain_mentions,
        "overlap_pair_count": prep["summary"].overlap_pair_count,
        "reference_already_exists": output.exists(),
        "future_unblinding_allowed_before_freeze": False,
        "production_prediction_file_read": False,
        "source_path": str(prep["source"]), "output_dir": str(output),
        "plan_writes_output": False,
        "next_slice": "commit_full_ner_coverage_reference_freeze_tooling_before_execute",
    }


def execute_reference_freeze(config_path: Path, repo_root: Path, annotations_path: Path | None = None) -> dict[str, Any]:
    config = load_reference_config(config_path)
    out = _path(repo_root, config["output_dir"])
    if out.exists():
        raise FullNerReferenceError(f"Immutable reference already exists: {out}")
    prep = _preflight(config, repo_root, annotations_path)
    if _sha(prep["source"].read_bytes()) != _sha(prep["raw"]):
        raise FullNerReferenceError("Annotations changed after validation")
    files = _content(config, repo_root, prep)
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".full_ner_reference_staging_", dir=out.parent))
    try:
        for name, data in files.items():
            (staging / name).write_bytes(data)
        for name, data in files.items():
            if (staging / name).read_bytes() != data:
                raise FullNerReferenceError(f"Staging write drift: {name}")
        if out.exists():
            raise FullNerReferenceError("Reference destination appeared during execute")
        os.replace(staging, out)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {
        "report": "scientific_entity_full_ner_coverage_reference_v01",
        "mode": "execute", "phase_complete": True,
        "audit_id": config["audit_id"], "reference_id": config["reference_id"],
        "reference_frozen": True, "annotation_sha256": _sha(prep["raw"]),
        "annotation_complete_count": prep["summary"].field_count,
        "annotation_mention_count": prep["summary"].mention_count,
        "uncertain_mention_count": prep["summary"].uncertain_mention_count,
        "prediction_blind": True, "production_prediction_file_read": False,
        "output_dir": str(out),
        "next_slice": "validate_immutable_full_ner_coverage_reference",
    }


def validate_frozen_reference(config_path: Path, repo_root: Path) -> dict[str, Any]:
    config = load_reference_config(config_path)
    sample = _path(repo_root, config["parent_sample_dir"])
    sample_validation = validate_sample_package(
        _path(repo_root, config["parent_sampling_config_path"]), repo_root,
        _path(repo_root, config["parent_annotation_guide_path"]),
    )
    checks: list[tuple[str,bool]] = [("parent_sample_still_valid", sample_validation.get("sample_validated") is True and sample_validation.get("required_failed_count") == 0)]
    out = _path(repo_root, config["output_dir"])
    checks.append(("reference_directory_exists",out.is_dir()))
    expected_names = {"README.md", "annotations.jsonl", "summary.json", "manifest.json", "checksums.txt"}
    checks.append(("reference_exact_file_layout", out.is_dir() and {p.name for p in out.iterdir()} == expected_names))
    if not out.is_dir():
        return _format_validation(config,checks)
    try:
        ledger = out.joinpath("checksums.txt").read_text("utf-8")
        mapping = {name: digest for digest, name in (line.split("  ", 1) for line in ledger.splitlines() if line.strip())}
        checks.append(("checksum_ledger_exact", set(mapping)==expected_names-{"checksums.txt"} and len(mapping)==4))
        for name in sorted(expected_names):
            data=(out/name).read_bytes()
            checks.append((f"lf:{name}", data.endswith(b"\n") and b"\r" not in data))
            if name != "checksums.txt":
                checks.append((f"checksum:{name}", _sha(data)==mapping.get(name)))
        m=ReferenceManifest.model_validate_json((out/"manifest.json").read_bytes())
        s=ReferenceSummary.model_validate_json((out/"summary.json").read_bytes())
        checks.append(("manifest_identity", m.audit_id==config["audit_id"] and m.reference_id==config["reference_id"]))
        checks.append(("sample_manifest_exact",m.sample_manifest_sha256==_file_sha(sample/"manifest.json")))
        checks.append(("sample_fields_exact",m.audit_fields_sha256==_file_sha(sample/"audit_fields.jsonl")))
        checks.append(("annotations_sha_exact",m.annotations_sha256==_file_sha(out/"annotations.jsonl") == config["expected_annotation_sha256"]))
        checks.append(("manifest_summary_sha_exact",m.reference_summary_sha256==_file_sha(out/"summary.json")))
        checks.append(("manifest_files_exact",m.files=={name:_file_sha(out/name) for name in ("README.md","annotations.jsonl","summary.json")}))
        fields = _parse_file(sample/"audit_fields.jsonl",FullNerCoverageAuditField)
        rows = _parse_file(out/"annotations.jsonl",FullNerCoverageAnnotationRow)
        checks.append(("annotation_count_exact",len(rows)==len(fields)==config["expected_total_fields"]))
        fixed=("audit_id", "audit_case_id", "canonical_id", "source_field", "source_text", "source_text_sha256")
        checks.append(("annotations_match_sample",len(rows)==len(fields) and all(all(getattr(r,key)==getattr(f,key) for key in fixed) for r,f in zip(rows,fields))))
        checks.append(("completed_and_uncertain_explained",all(r.annotation_complete and all(not m.uncertain or bool(m.reviewer_note and m.reviewer_note.strip()) for m in r.mentions) for r in rows)))
        recomputed=_summary(config,rows)
        checks.append(("summary_exact_recompute",s == recomputed and (out/"summary.json").read_bytes()==_bytes_json(s.model_dump(mode="json"))))
        checks.append(("readme_exact_recompute",(out/"README.md").read_bytes()==_readme(config,s)))
        checks.append(("manifest_exact_canonical_bytes",(out/"manifest.json").read_bytes()==_bytes_json(m.model_dump(mode="json"))))
        checks.append(("ledger_exact_recompute", (out/"checksums.txt").read_bytes()=="".join(f"{_file_sha(out/name)}  {name}\n" for name in sorted(expected_names-{"checksums.txt"})).encode("utf-8")))
        checks.append(("frozen_uncertainty_preserved",s.uncertain_mention_count==config["expected_uncertain_mentions"] and s.uncertain_flags_preserved))
        checks.append(("frozen_counts_exact",s.field_count==config["expected_total_fields"] and s.mention_count==config["expected_total_mentions"] and s.overlap_pair_count==config["expected_overlap_pairs"]))
        checks.append(("no_unblind_or_mutation",m.unblinding_executed is False and m.production_prediction_files_read is False and m.canonical_mutated is False and m.production_latest_mutated is False))
    except (OSError,ValueError,KeyError,TypeError,FullNerReferenceError) as ex:
        checks.append(("reference_integrity_read",False))
        return _format_validation(config,checks,error=str(ex))
    return _format_validation(config,checks)


def _format_validation(config:dict[str,Any],checks:list[tuple[str,bool]],error:str|None=None)->dict[str,Any]:
    failures=[name for name,passed in checks if not passed]
    return {
        "report":"scientific_entity_full_ner_coverage_reference_v01",
        "reference_id":config["reference_id"],
        "checks":[{"name":name,"passed":passed} for name,passed in checks],
        "reference_validated":not failures,
        "reference_frozen":not failures,
        "prediction_blind":True,
        "production_prediction_file_read":False,
        "total_checks":len(checks),
        "required_failed_count":len(failures),
        "error":error,
        "next_slice":"preregister_full_ner_coverage_scoring_before_unblind" if not failures else "investigate_full_ner_reference_validation",
    }
