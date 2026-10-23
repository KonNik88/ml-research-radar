from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from radar_core.contracts.scientific_entity_full_ner_coverage_audit import (
    FullNerCoverageAnnotationRow,
    FullNerCoverageAuditField,
)

FORBIDDEN_PREDICTION_KEYS = {
    "prediction",
    "predictions",
    "predicted_type",
    "prediction_entity_type",
    "prediction_count",
    "prediction_density",
    "semantic_typer_score",
    "score_margin",
    "h2_override",
    "candidate_decision",
}


class FullNerCoverageAuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuditPaths:
    sample_dir: Path
    work_dir: Path


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _write_text_lf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    path.write_bytes(data)


def _write_json(path: Path, obj: Any) -> None:
    _write_text_lf(path, _canonical_json(obj))


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    _write_text_lf(path, "".join(_canonical_json(row) for row in rows))


def load_config(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise FullNerCoverageAuditError("Config must be a mapping")
    return data


def _repo_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def _validate_closure(config: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    closure_dir = _repo_path(repo_root, config["closure_dir"])
    closure_path = closure_dir / "closure.json"
    if not closure_path.exists():
        raise FullNerCoverageAuditError(f"Missing closure record: {closure_path}")
    closure = json.loads(closure_path.read_text(encoding="utf-8"))
    if closure.get("closure_id") != config["expected_closure_id"]:
        raise FullNerCoverageAuditError("Closure ID mismatch")
    if closure.get("h2_v03_lifecycle_closed") is not True:
        raise FullNerCoverageAuditError("H2 v0.3 lifecycle is not closed")
    if closure.get("future_full_ner_coverage_audit_requires_fresh_prediction_blind_sample") is not True:
        raise FullNerCoverageAuditError("Closure does not require a fresh prediction-blind sample")
    if closure.get("future_h2_v03_tuning_allowed") is not False:
        raise FullNerCoverageAuditError("Closure unexpectedly permits future H2 v0.3 tuning")
    return closure


def _validate_latest_pointer(config: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    latest_path = _repo_path(repo_root, config["production_latest_pointer_path"])
    if not latest_path.exists():
        raise FullNerCoverageAuditError(f"Missing trusted latest pointer: {latest_path}")
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    if latest.get("state") != "trusted_latest":
        raise FullNerCoverageAuditError("Scientific Entity production latest is not trusted_latest")
    if latest.get("candidate_build_id") != config["expected_trusted_candidate_build_id"]:
        raise FullNerCoverageAuditError("Trusted candidate build mismatch")
    if latest.get("candidate_final_mentions_sha256") != config["expected_trusted_final_mentions_sha256"]:
        raise FullNerCoverageAuditError("Trusted final_mentions SHA mismatch")
    if latest.get("canonical_sha256") != config["canonical_sha256"]:
        raise FullNerCoverageAuditError("Trusted latest canonical SHA mismatch")
    return latest


def _collect_historical_ids(config: dict[str, Any], repo_root: Path) -> tuple[set[str], list[str]]:
    ids: set[str] = set()
    files_read: list[str] = []
    for root_value in config.get("historical_exclusion_roots", []):
        root = _repo_path(repo_root, root_value)
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.jsonl")):
            files_read.append(path.as_posix())
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    canonical_id = row.get("canonical_id")
                    if isinstance(canonical_id, str) and canonical_id:
                        ids.add(canonical_id)
    return ids, files_read


def _rank(seed: str, field: str, canonical_id: str) -> str:
    return hashlib.sha256(f"{seed}|{field}|{canonical_id}".encode("utf-8")).hexdigest()


def _case_id(audit_id: str, canonical_id: str, field: str, text_sha: str) -> str:
    digest = hashlib.sha256(f"{audit_id}|{canonical_id}|{field}|{text_sha}".encode("utf-8")).hexdigest()[:32]
    return f"coverage:{digest}"


def _load_canonical_candidates(
    *,
    canonical_path: Path,
    excluded_ids: set[str],
    audit_id: str,
    seed: str,
) -> tuple[dict[str, list[tuple[str, FullNerCoverageAuditField]]], int]:
    candidates: dict[str, list[tuple[str, FullNerCoverageAuditField]]] = {"title": [], "abstract": []}
    doc_count = 0
    with canonical_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            doc_count += 1
            canonical_id = row.get("canonical_id")
            if not isinstance(canonical_id, str) or not canonical_id or canonical_id in excluded_ids:
                continue
            for field in ("title", "abstract"):
                text = row.get(field)
                if not isinstance(text, str):
                    continue
                text = text.strip()
                if not text:
                    continue
                text_sha = _sha256_text(text)
                audit_row = FullNerCoverageAuditField(
                    schema_version="scientific_entity_full_ner_coverage_audit_field_v0.1",
                    audit_id=audit_id,
                    audit_case_id=_case_id(audit_id, canonical_id, field, text_sha),
                    canonical_id=canonical_id,
                    source_field=field,
                    source_text=text,
                    source_text_sha256=text_sha,
                )
                candidates[field].append((_rank(seed, field, canonical_id), audit_row))
    return candidates, doc_count


def _select_rows(config: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    canonical_path = _repo_path(repo_root, config["canonical_path"])
    if not canonical_path.exists():
        raise FullNerCoverageAuditError(f"Missing canonical corpus: {canonical_path}")
    canonical_sha = _sha256_file(canonical_path)
    if canonical_sha != config["canonical_sha256"]:
        raise FullNerCoverageAuditError(f"Canonical SHA mismatch: {canonical_sha}")

    excluded_ids, exclusion_files = _collect_historical_ids(config, repo_root)
    candidates, doc_count = _load_canonical_candidates(
        canonical_path=canonical_path,
        excluded_ids=excluded_ids,
        audit_id=config["audit_id"],
        seed=config["sampling_seed"],
    )
    if doc_count != int(config["canonical_document_count"]):
        raise FullNerCoverageAuditError(f"Canonical document count mismatch: {doc_count}")

    selected: list[FullNerCoverageAuditField] = []
    eligible_counts: dict[str, int] = {}
    for field in ("title", "abstract"):
        ordered = sorted(candidates[field], key=lambda x: (x[0], x[1].canonical_id))
        eligible_counts[field] = len(ordered)
        target = int(config["sample_counts"][field])
        if len(ordered) < target:
            raise FullNerCoverageAuditError(f"Not enough eligible {field} fields: {len(ordered)} < {target}")
        selected.extend(row for _, row in ordered[:target])

    selected.sort(key=lambda row: _rank(config["sampling_seed"] + "|output", row.source_field, row.canonical_id))
    return {
        "rows": selected,
        "excluded_ids": excluded_ids,
        "exclusion_files": exclusion_files,
        "eligible_counts": eligible_counts,
        "canonical_sha256": canonical_sha,
        "canonical_document_count": doc_count,
    }


def _annotation_row(field: FullNerCoverageAuditField) -> FullNerCoverageAnnotationRow:
    return FullNerCoverageAnnotationRow(
        schema_version="scientific_entity_full_ner_coverage_annotation_working_v0.1",
        audit_id=field.audit_id,
        audit_case_id=field.audit_case_id,
        canonical_id=field.canonical_id,
        source_field=field.source_field,
        source_text=field.source_text,
        source_text_sha256=field.source_text_sha256,
        mentions=[],
        annotation_complete=False,
        reviewer_note=None,
    )


def _paths(config: dict[str, Any], repo_root: Path) -> AuditPaths:
    return AuditPaths(
        sample_dir=_repo_path(repo_root, config["sample_output_root"]) / config["audit_id"],
        work_dir=_repo_path(repo_root, config["annotation_work_root"]) / config["audit_id"],
    )


def plan_full_ner_coverage_audit(config_path: Path, repo_root: Path) -> dict[str, Any]:
    config = load_config(config_path)
    closure = _validate_closure(config, repo_root)
    latest = _validate_latest_pointer(config, repo_root)
    sample = _select_rows(config, repo_root)
    paths = _paths(config, repo_root)
    counts = {"title": 0, "abstract": 0}
    for row in sample["rows"]:
        counts[row.source_field] += 1
    return {
        "report": "scientific_entity_full_ner_coverage_audit_v01",
        "mode": "plan",
        "phase_complete": False,
        "audit_id": config["audit_id"],
        "canonical_sha256": sample["canonical_sha256"],
        "canonical_document_count": sample["canonical_document_count"],
        "trusted_candidate_build_id": latest["candidate_build_id"],
        "trusted_final_mentions_sha256": latest["candidate_final_mentions_sha256"],
        "closure_id": closure["closure_id"],
        "prediction_blind": True,
        "production_prediction_file_read": False,
        "historical_canonical_id_exclusion_count": len(sample["excluded_ids"]),
        "historical_exclusion_file_count": len(sample["exclusion_files"]),
        "eligible_title_count": sample["eligible_counts"]["title"],
        "eligible_abstract_count": sample["eligible_counts"]["abstract"],
        "sample_title_count": counts["title"],
        "sample_abstract_count": counts["abstract"],
        "sample_total_count": len(sample["rows"]),
        "sample_output_exists": paths.sample_dir.exists(),
        "annotation_work_exists": paths.work_dir.exists(),
        "plan_writes_output": False,
        "annotation_ready": False,
        "sample_dir": str(paths.sample_dir),
        "annotation_work_dir": str(paths.work_dir),
        "next_slice": "commit_full_ner_coverage_audit_sampling_tooling_before_execute",
    }


def execute_full_ner_coverage_audit(config_path: Path, repo_root: Path, guide_source: Path) -> dict[str, Any]:
    config = load_config(config_path)
    closure = _validate_closure(config, repo_root)
    latest = _validate_latest_pointer(config, repo_root)
    sample = _select_rows(config, repo_root)
    paths = _paths(config, repo_root)
    if paths.sample_dir.exists() or paths.work_dir.exists():
        raise FullNerCoverageAuditError("Audit sample/workspace already exists; execution is one-shot")

    rows: list[FullNerCoverageAuditField] = sample["rows"]
    blank_rows = [_annotation_row(row) for row in rows]
    paths.sample_dir.mkdir(parents=True, exist_ok=False)
    paths.work_dir.mkdir(parents=True, exist_ok=False)

    audit_fields = [row.model_dump(mode="json") for row in rows]
    annotations = [row.model_dump(mode="json") for row in blank_rows]
    _write_jsonl(paths.sample_dir / "audit_fields.jsonl", audit_fields)
    _write_jsonl(paths.sample_dir / "blank_annotations.jsonl", annotations)
    guide_text = guide_source.read_text(encoding="utf-8")
    _write_text_lf(paths.sample_dir / "ANNOTATION_GUIDE.md", guide_text)

    counts = {"title": 0, "abstract": 0}
    for row in rows:
        counts[row.source_field] += 1

    manifest = {
        "schema_version": "scientific_entity_full_ner_coverage_audit_manifest_v0.1",
        "audit_id": config["audit_id"],
        "canonical_path": config["canonical_path"],
        "canonical_sha256": sample["canonical_sha256"],
        "canonical_document_count": sample["canonical_document_count"],
        "trusted_latest_pointer_path": config["production_latest_pointer_path"],
        "trusted_candidate_build_id": latest["candidate_build_id"],
        "trusted_final_mentions_sha256": latest["candidate_final_mentions_sha256"],
        "closure_id": closure["closure_id"],
        "sampling_seed": config["sampling_seed"],
        "sampling_method": "deterministic_uniform_hash_sampling_by_field",
        "prediction_blind": True,
        "production_prediction_file_read": False,
        "historical_canonical_id_exclusion_count": len(sample["excluded_ids"]),
        "historical_exclusion_file_count": len(sample["exclusion_files"]),
        "eligible_field_counts": sample["eligible_counts"],
        "sample_field_counts": counts,
        "sample_total_count": len(rows),
        "annotation_taxonomy": config["annotation_taxonomy"],
        "sample_contains_prediction_metadata": False,
        "future_unblinding_allowed_before_reference_freeze": False,
        "next_slice": "complete_prediction_blind_full_ner_coverage_annotation",
    }
    _write_json(paths.sample_dir / "manifest.json", manifest)

    sample_readme = f"""# Full NER Coverage Audit v0.1\n\nAudit ID: `{config['audit_id']}`\n\nThis is an immutable prediction-blind sample of complete canonical fields.\n\n- titles: `{counts['title']}`\n- abstracts: `{counts['abstract']}`\n- total fields: `{len(rows)}`\n- production prediction files read during selection: `False`\n\nEdit only the mutable workspace copy under `{config['annotation_work_root']}/{config['audit_id']}/annotations_working.jsonl`.\n"""
    _write_text_lf(paths.sample_dir / "README.md", sample_readme)

    checksum_names = ["README.md", "ANNOTATION_GUIDE.md", "audit_fields.jsonl", "blank_annotations.jsonl", "manifest.json"]
    checksum_lines = [f"{_sha256_file(paths.sample_dir / name)}  {name}" for name in checksum_names]
    _write_text_lf(paths.sample_dir / "checksums.txt", "\n".join(checksum_lines) + "\n")

    shutil.copy2(paths.sample_dir / "blank_annotations.jsonl", paths.work_dir / "annotations_working.jsonl")
    _write_text_lf(paths.work_dir / "ANNOTATION_GUIDE.md", guide_text)
    work_readme = f"""# Mutable Full NER Coverage Annotation Workspace\n\nAudit ID: `{config['audit_id']}`\n\nEdit `annotations_working.jsonl` only. Do not inspect production predictions while annotating.\n\nWhen all rows have `annotation_complete=true`, save the completed JSONL for the future immutable reference-freeze slice.\n"""
    _write_text_lf(paths.work_dir / "README.md", work_readme)

    return {
        "report": "scientific_entity_full_ner_coverage_audit_v01",
        "mode": "execute",
        "phase_complete": True,
        "audit_id": config["audit_id"],
        "prediction_blind": True,
        "production_prediction_file_read": False,
        "historical_canonical_id_exclusion_count": len(sample["excluded_ids"]),
        "sample_title_count": counts["title"],
        "sample_abstract_count": counts["abstract"],
        "sample_total_count": len(rows),
        "sample_dir": str(paths.sample_dir),
        "annotation_work_dir": str(paths.work_dir),
        "annotation_file": str(paths.work_dir / "annotations_working.jsonl"),
        "annotation_guide": str(paths.work_dir / "ANNOTATION_GUIDE.md"),
        "annotation_ready": True,
        "future_unblinding_allowed_before_reference_freeze": False,
        "next_slice": "complete_prediction_blind_full_ner_coverage_annotation",
    }


def validate_sample_package(config_path: Path, repo_root: Path, guide_source: Path) -> dict[str, Any]:
    config = load_config(config_path)
    _validate_closure(config, repo_root)
    _validate_latest_pointer(config, repo_root)
    recomputed = _select_rows(config, repo_root)
    paths = _paths(config, repo_root)
    checks: list[tuple[str, bool, str]] = []

    expected_layout = {"README.md", "ANNOTATION_GUIDE.md", "audit_fields.jsonl", "blank_annotations.jsonl", "manifest.json", "checksums.txt"}
    actual_layout = {p.name for p in paths.sample_dir.iterdir()} if paths.sample_dir.exists() else set()
    checks.append(("sample_directory_exists", paths.sample_dir.exists(), str(paths.sample_dir)))
    checks.append(("exact_file_layout", actual_layout == expected_layout, str(sorted(actual_layout))))

    checksum_map: dict[str, str] = {}
    checksum_path = paths.sample_dir / "checksums.txt"
    if checksum_path.exists():
        for line in checksum_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            sha, name = line.split("  ", 1)
            checksum_map[name] = sha
    checks.append(("checksum_set_exact", set(checksum_map) == expected_layout - {"checksums.txt"}, str(sorted(checksum_map))))
    for name, expected_sha in checksum_map.items():
        path = paths.sample_dir / name
        checks.append((f"checksum:{name}", path.exists() and _sha256_file(path) == expected_sha, name))

    fields: list[FullNerCoverageAuditField] = []
    field_path = paths.sample_dir / "audit_fields.jsonl"
    if field_path.exists():
        for line in field_path.read_text(encoding="utf-8").splitlines():
            fields.append(FullNerCoverageAuditField.model_validate_json(line))
    recomputed_rows: list[FullNerCoverageAuditField] = recomputed["rows"]
    checks.append(("sample_recomputes_exactly", [x.model_dump() for x in fields] == [x.model_dump() for x in recomputed_rows], ""))
    checks.append(("sample_count_120", len(fields) == 120, str(len(fields))))
    checks.append(("title_count_60", sum(x.source_field == "title" for x in fields) == 60, ""))
    checks.append(("abstract_count_60", sum(x.source_field == "abstract" for x in fields) == 60, ""))
    checks.append(("unique_audit_case_ids", len({x.audit_case_id for x in fields}) == len(fields), ""))
    checks.append(("historical_ids_excluded", not ({x.canonical_id for x in fields} & recomputed["excluded_ids"]), ""))
    forbidden_present = any(FORBIDDEN_PREDICTION_KEYS & set(x.model_dump()) for x in fields)
    checks.append(("prediction_blind_schema", not forbidden_present, ""))
    checks.append(("annotation_guide_exact", (paths.sample_dir / "ANNOTATION_GUIDE.md").read_text(encoding="utf-8") == guide_source.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n"), ""))

    blanks: list[FullNerCoverageAnnotationRow] = []
    blank_path = paths.sample_dir / "blank_annotations.jsonl"
    if blank_path.exists():
        for line in blank_path.read_text(encoding="utf-8").splitlines():
            blanks.append(FullNerCoverageAnnotationRow.model_validate_json(line))
    checks.append(("blank_annotations_align", [x.audit_case_id for x in blanks] == [x.audit_case_id for x in fields], ""))
    checks.append(("blank_annotations_are_blank", all(not x.mentions and not x.annotation_complete for x in blanks), ""))

    failed = [name for name, ok, _ in checks if not ok]
    return {
        "report": "scientific_entity_full_ner_coverage_audit_v01",
        "audit_id": config["audit_id"],
        "sample_validated": not failed,
        "prediction_blind": True,
        "production_prediction_file_read": False,
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "failed_checks": failed,
        "checks": [{"check": name, "ok": ok, "detail": detail} for name, ok, detail in checks],
        "next_slice": "complete_prediction_blind_full_ner_coverage_annotation" if not failed else "fix_full_ner_coverage_audit_sample",
    }
