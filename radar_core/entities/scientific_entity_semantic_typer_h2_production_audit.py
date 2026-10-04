from __future__ import annotations

import hashlib
import heapq
import json
import shutil
from pathlib import Path
from typing import Any, Iterator, Sequence

from radar_core.contracts.scientific_entity_evidence import ScientificEntityType
from radar_core.contracts.scientific_entity_semantic_typer_h2_full_corpus_candidate import (
    H2FullCorpusFinalMention,
    H2FullCorpusManifest,
    H2FullCorpusSummary,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit import (
    ANNOTATION_SCHEMA_VERSION,
    CASE_SCHEMA_VERSION,
    H2ProductionAuditAnnotation,
    H2ProductionAuditCase,
    H2ProductionAuditConfig,
    H2ProductionAuditError,
    H2ProductionAuditManifest,
    MANIFEST_SCHEMA_VERSION,
    canonical_config_sha256,
    load_h2_production_audit_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_audit_v0.3.yaml"
REPORT_NAME = "scientific_entity_semantic_typer_h2_production_audit_v03"
REQUIRED_FILES = ("README.md", "audit_cases.jsonl", "blank_annotations.jsonl", "reviewer.html", "manifest.json", "checksums.txt")
CHECKSUM_FILES = tuple(name for name in REQUIRED_FILES if name != "checksums.txt")
FORBIDDEN_BLIND_KEYS = {
    "stratum", "baseline_entity_type", "final_entity_type", "h2_override_applied",
    "semantic_typer_predicted_entity_type", "semantic_typer_score_margin",
    "semantic_typer_used_baseline_fallback", "baseline_confidence_score", "candidate_evidence_id",
}


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _stable_hash(seed: str, value: str) -> int:
    return int(hashlib.sha256(f"{seed}\0{value}".encode("utf-8")).hexdigest(), 16)


def _stable_case_id(audit_id: str, candidate_evidence_id: str) -> str:
    digest = hashlib.sha256(f"{audit_id}\0{candidate_evidence_id}".encode("utf-8")).hexdigest()[:32]
    return f"audit:{digest}"


def _candidate_parent(root: Path, config: H2ProductionAuditConfig, candidate_dir: Path, canonical_path: Path) -> dict[str, Any]:
    candidate_dir = candidate_dir.resolve()
    canonical_path = canonical_path.resolve()
    if not candidate_dir.is_dir():
        raise H2ProductionAuditError(f"Candidate directory does not exist: {candidate_dir}")
    if candidate_dir.name != config.candidate.build_id:
        raise H2ProductionAuditError("Candidate directory does not match frozen build_id")
    if not canonical_path.is_file():
        raise H2ProductionAuditError(f"Canonical file does not exist: {canonical_path}")
    if _sha256_file(canonical_path) != config.canonical_snapshot.sha256:
        raise H2ProductionAuditError("Canonical SHA-256 does not match frozen audit snapshot")

    manifest = H2FullCorpusManifest.model_validate(json.loads((candidate_dir / "manifest.json").read_text(encoding="utf-8")))
    summary = H2FullCorpusSummary.model_validate(json.loads((candidate_dir / "summary.json").read_text(encoding="utf-8")))
    expected = config.candidate
    checks = [
        manifest.build_id == expected.build_id,
        manifest.candidate_id == expected.candidate_id,
        manifest.candidate_fingerprint_sha256 == expected.candidate_fingerprint_sha256,
        manifest.materialization_fingerprint_sha256 == expected.materialization_fingerprint_sha256,
        manifest.canonical_sha256 == config.canonical_snapshot.sha256,
        manifest.canonical_document_count == config.canonical_snapshot.document_count,
        manifest.baseline_prediction_count == expected.baseline_prediction_count,
        manifest.semantic_typer_case_count == expected.baseline_method_count,
        manifest.h2_override_count == expected.h2_override_count,
        manifest.final_mention_count == expected.final_mention_count,
        summary.baseline_prediction_count == expected.baseline_prediction_count,
        summary.baseline_method_count == expected.baseline_method_count,
        summary.h2_override_count == expected.h2_override_count,
        summary.final_mention_count == expected.final_mention_count,
        manifest.canonical_truth_mutated is False,
        manifest.production_latest_promotion_authorized is False,
    ]
    if not all(checks):
        raise H2ProductionAuditError("Candidate manifest/summary does not match frozen validated candidate")

    checksum_map: dict[str, str] = {}
    for line in (candidate_dir / "checksums.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split("  ", 1)
            checksum_map[name] = digest
    for name in ("manifest.json", "summary.json", "final_mentions.jsonl"):
        if checksum_map.get(name) != _sha256_file(candidate_dir / name):
            raise H2ProductionAuditError(f"Candidate checksum mismatch: {name}")
    return {"manifest": manifest, "summary": summary}


def _stratum(row: H2FullCorpusFinalMention) -> str | None:
    if row.baseline_entity_type != ScientificEntityType.METHOD:
        return None
    if row.h2_override_applied:
        return "override"
    if row.semantic_typer_used_baseline_fallback is True:
        return "fallback_method"
    if row.semantic_typer_used_baseline_fallback is False:
        return "preserved_method"
    raise H2ProductionAuditError("Method row lacks semantic typer fallback state")


def _select_final_rows(candidate_dir: Path, config: H2ProductionAuditConfig) -> dict[str, list[H2FullCorpusFinalMention]]:
    targets = {
        "override": config.sampling.override_count,
        "preserved_method": config.sampling.preserved_method_count,
        "fallback_method": config.sampling.fallback_method_count,
    }
    heaps: dict[str, list[tuple[int, str, H2FullCorpusFinalMention]]] = {key: [] for key in targets}
    with (candidate_dir / "final_mentions.jsonl").open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                raise H2ProductionAuditError(f"Blank final_mentions line {line_number}")
            row = H2FullCorpusFinalMention.model_validate(json.loads(line))
            stratum = _stratum(row)
            if stratum is None:
                continue
            rank = _stable_hash(config.sampling.selection_seed_sha256 + ":" + stratum, row.baseline_prediction_evidence_id)
            heap = heaps[stratum]
            item = (-rank, row.baseline_prediction_evidence_id, row)
            if len(heap) < targets[stratum]:
                heapq.heappush(heap, item)
            elif rank < -heap[0][0]:
                heapq.heapreplace(heap, item)
    selected: dict[str, list[H2FullCorpusFinalMention]] = {}
    for stratum, heap in heaps.items():
        if len(heap) != targets[stratum]:
            raise H2ProductionAuditError(f"Insufficient rows for {stratum}: {len(heap)} < {targets[stratum]}")
        selected[stratum] = [item[2] for item in sorted(heap, key=lambda item: (-item[0], item[1]))]
    return selected


def _load_source_texts(canonical_path: Path, selected: Sequence[H2FullCorpusFinalMention]) -> dict[tuple[str, str], str]:
    wanted = {(row.canonical_id, row.source_field.value) for row in selected}
    found: dict[tuple[str, str], str] = {}
    with canonical_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                raise H2ProductionAuditError(f"Blank canonical line {line_number}")
            payload = json.loads(line)
            canonical_id = payload.get("canonical_id")
            if not isinstance(canonical_id, str) or not canonical_id:
                raise H2ProductionAuditError(f"Invalid canonical_id on line {line_number}")
            for field in ("title", "abstract"):
                key = (canonical_id, field)
                if key in wanted:
                    value = payload.get(field)
                    if not isinstance(value, str) or not value:
                        raise H2ProductionAuditError(f"Missing source text for selected case {key}")
                    found[key] = value
            if len(found) == len(wanted):
                break
    missing = wanted - set(found)
    if missing:
        raise H2ProductionAuditError(f"Selected source texts missing from canonical: {sorted(missing)[:3]}")
    return found


def _build_blind_cases(config: H2ProductionAuditConfig, selected_by_stratum: dict[str, list[H2FullCorpusFinalMention]], source_texts: dict[tuple[str, str], str]) -> list[H2ProductionAuditCase]:
    rows: list[H2ProductionAuditCase] = []
    for selected in selected_by_stratum.values():
        for row in selected:
            text = source_texts[(row.canonical_id, row.source_field.value)]
            actual_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if actual_sha != row.source_text_sha256:
                raise H2ProductionAuditError("Selected row source_text_sha256 does not match canonical")
            if text[row.char_start:row.char_end] != row.surface_text:
                raise H2ProductionAuditError("Selected row span does not match canonical source text")
            rows.append(H2ProductionAuditCase(
                schema_version=CASE_SCHEMA_VERSION,
                audit_id=config.sampling.audit_id,
                audit_case_id=_stable_case_id(config.sampling.audit_id, row.baseline_prediction_evidence_id),
                canonical_id=row.canonical_id,
                source_field=row.source_field,
                source_text_sha256=row.source_text_sha256,
                source_text=text,
                char_start=row.char_start,
                char_end=row.char_end,
                surface_text=row.surface_text,
            ))
    rows.sort(key=lambda row: (_stable_hash(config.sampling.blind_order_seed_sha256, row.audit_case_id), row.audit_case_id))
    return rows


def _blank_annotation(case: H2ProductionAuditCase) -> H2ProductionAuditAnnotation:
    return H2ProductionAuditAnnotation(
        schema_version=ANNOTATION_SCHEMA_VERSION,
        **case.model_dump(mode="json", exclude={"schema_version"}),
        reference_entity_type=None,
        span_status=None,
        annotation_confidence=None,
        reviewer_note=None,
        annotation_complete=False,
    )


def _reviewer_html(config: H2ProductionAuditConfig) -> str:
    audit_id = json.dumps(config.sampling.audit_id)
    total = config.sampling.total_count
    types = json.dumps([x.value for x in config.annotation.allowed_entity_types])
    statuses = json.dumps(config.annotation.allowed_span_statuses)
    confidences = json.dumps(config.annotation.confidence_levels)
    return fr"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ML Research Radar — H2 v0.3 Production Audit</title>
<style>
body{{font-family:system-ui,Segoe UI,sans-serif;margin:0;background:#f5f7fa;color:#172033}} header{{position:sticky;top:0;background:white;border-bottom:1px solid #d7dde7;padding:12px 18px;z-index:3}} main{{max-width:1100px;margin:auto;padding:18px}} button,label{{font:inherit}} button,.file{{padding:7px 10px;border:1px solid #cbd3df;border-radius:7px;background:white;cursor:pointer;margin:2px}} button.on{{background:#dbeafe;border-color:#2563eb}} .card{{background:white;border:1px solid #d7dde7;border-radius:10px;padding:14px;margin:12px 0}} .source{{white-space:pre-wrap;line-height:1.55;background:#fbfcfe;border:1px solid #e1e6ee;border-radius:7px;padding:10px}} mark{{background:#fde68a}} .meta{{font-size:12px;color:#667085}} .group{{margin-top:10px}} textarea{{width:100%;min-height:52px}} input[type=file]{{display:none}} .warn{{background:#fff7ed;border:1px solid #fed7aa;padding:10px;border-radius:8px;margin-bottom:12px}} .ok{{color:#067647}} .bad{{color:#b42318}}
</style></head><body>
<header><b>H2 v0.3 Production Audit — prediction blind</b> <label class="file">Load annotations JSONL<input id="file" type="file"></label><button id="export" disabled>Export annotations_completed.jsonl</button><button id="next" disabled>Next incomplete</button><span id="status" class="meta"></span></header>
<main><div class="warn"><b>Blindness guard:</b> this file contains no sampling stratum, baseline/final type, H2 decision, semantic score, or candidate prediction. Do not search case IDs in candidate files before reference freeze.</div><div id="app">Load the mutable annotation working JSONL.</div></main>
<script>
const AUDIT_ID={audit_id}, EXPECTED={total}, TYPES={types}, STATUSES={statuses}, CONF={confidences}; let rows=[];
const esc=s=>String(s).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
function valid(r){{if(r.audit_id!==AUDIT_ID)return false;if(!r.annotation_complete)return true;if(!r.span_status||!r.annotation_confidence)return false;if(['valid_entity_span','boundary_issue'].includes(r.span_status))return TYPES.includes(r.reference_entity_type);return r.reference_entity_type==null;}}
function render(){{const app=document.getElementById('app');app.innerHTML='';rows.forEach((r,i)=>{{const c=document.createElement('div');c.className='card';const cp=Array.from(r.source_text), before=esc(cp.slice(0,r.char_start).join('')), mid=esc(cp.slice(r.char_start,r.char_end).join('')), after=esc(cp.slice(r.char_end).join(''));c.innerHTML=`<div class="meta">${{i+1}}/${{rows.length}} · ${{esc(r.canonical_id)}} · ${{esc(r.source_field)}} · <span id="done-${{i}}"></span></div><div class="source">${{before}}<mark>${{mid}}</mark>${{after}}</div><div class="group"><b>Span status</b><div id="s-${{i}}"></div></div><div class="group"><b>Reference type</b><div id="t-${{i}}"></div></div><div class="group"><b>Confidence</b><div id="c-${{i}}"></div></div><div class="group"><textarea id="n-${{i}}" placeholder="Optional reviewer note"></textarea></div>`;app.appendChild(c);const sb=c.querySelector('#s-'+i),tb=c.querySelector('#t-'+i),cb=c.querySelector('#c-'+i);STATUSES.forEach(x=>{{let b=document.createElement('button');b.textContent=x;if(r.span_status===x)b.className='on';b.onclick=()=>{{r.span_status=x;if(['not_an_entity','uncertain'].includes(x))r.reference_entity_type=null;sync(i);render();}};sb.appendChild(b);}});TYPES.forEach(x=>{{let b=document.createElement('button');b.textContent=x;if(r.reference_entity_type===x)b.className='on';b.onclick=()=>{{r.reference_entity_type=x;if(!['valid_entity_span','boundary_issue'].includes(r.span_status))r.span_status='valid_entity_span';sync(i);render();}};tb.appendChild(b);}});CONF.forEach(x=>{{let b=document.createElement('button');b.textContent=x;if(r.annotation_confidence===x)b.className='on';b.onclick=()=>{{r.annotation_confidence=x;sync(i);render();}};cb.appendChild(b);}});const note=c.querySelector('#n-'+i);note.value=r.reviewer_note||'';note.onchange=()=>{{r.reviewer_note=note.value||null;sync(i);update();}};sync(i);}});update();}}
function sync(i){{let r=rows[i];r.annotation_complete=!!r.span_status&&!!r.annotation_confidence&&((['valid_entity_span','boundary_issue'].includes(r.span_status)&&TYPES.includes(r.reference_entity_type))||(['not_an_entity','uncertain'].includes(r.span_status)&&r.reference_entity_type==null));}}
function update(){{let n=rows.filter(r=>r.annotation_complete).length;document.getElementById('status').textContent=` complete ${{n}}/${{rows.length}}`;rows.forEach((r,i)=>{{let e=document.getElementById('done-'+i);if(e){{e.textContent=r.annotation_complete?'complete':'incomplete';e.className=r.annotation_complete?'ok':'bad';}}}});}}
document.getElementById('file').onchange=async e=>{{let text=await e.target.files[0].text();rows=text.split(/\r?\n/).filter(x=>x.trim()).map(JSON.parse);if(rows.length!==EXPECTED)throw Error(`Expected ${{EXPECTED}} rows, got ${{rows.length}}`);if(rows.some(r=>!valid(r)))throw Error('Invalid annotation file');document.getElementById('export').disabled=false;document.getElementById('next').disabled=false;render();}};
document.getElementById('export').onclick=()=>{{rows.forEach((_,i)=>sync(i));let blob=new Blob([rows.map(r=>JSON.stringify(r)).join('\n')+'\n'],{{type:'application/jsonl'}}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='annotations_completed.jsonl';a.click();URL.revokeObjectURL(a.href);}};
document.getElementById('next').onclick=()=>{{rows.forEach((_,i)=>sync(i));let i=rows.findIndex(r=>!r.annotation_complete);if(i>=0)document.querySelectorAll('.card')[i].scrollIntoView({{behavior:'smooth',block:'start'}});update();}};
</script></body></html>"""


def _readme(config: H2ProductionAuditConfig) -> str:
    return f"""# H2 v0.3 Production Audit Sample\n\nAudit ID: `{config.sampling.audit_id}`\n\nThis package is prediction-blind. It contains {config.sampling.total_count} already-extracted baseline-method spans sampled deterministically from the validated full-corpus candidate.\n\nDo not search sampled case IDs in `final_mentions.jsonl` or other candidate files before the human reference is frozen.\n\nFiles:\n- `audit_cases.jsonl`: immutable blind cases;\n- `blank_annotations.jsonl`: blank annotation schema;\n- `reviewer.html`: offline local reviewer;\n- `manifest.json`: frozen lineage and counts;\n- `checksums.txt`: package integrity.\n\nPromotion is not authorized by this package.\n"""


def _write_package(output_dir: Path, config: H2ProductionAuditConfig, cases: Sequence[H2ProductionAuditCase]) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "audit_cases.jsonl").write_text("".join(_json_line(x.model_dump(mode="json")) for x in cases), encoding="utf-8", newline="\n")
    blanks = [_blank_annotation(case) for case in cases]
    (output_dir / "blank_annotations.jsonl").write_text("".join(_json_line(x.model_dump(mode="json")) for x in blanks), encoding="utf-8", newline="\n")
    manifest = H2ProductionAuditManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        audit_id=config.sampling.audit_id,
        candidate_build_id=config.candidate.build_id,
        candidate_id=config.candidate.candidate_id,
        candidate_fingerprint_sha256=config.candidate.candidate_fingerprint_sha256,
        materialization_fingerprint_sha256=config.candidate.materialization_fingerprint_sha256,
        canonical_sha256=config.canonical_snapshot.sha256,
        canonical_document_count=config.canonical_snapshot.document_count,
        audit_config_sha256=canonical_config_sha256(config),
        selection_seed_sha256=config.sampling.selection_seed_sha256,
        blind_order_seed_sha256=config.sampling.blind_order_seed_sha256,
        audit_case_count=config.sampling.total_count,
        override_count=config.sampling.override_count,
        preserved_method_count=config.sampling.preserved_method_count,
        fallback_method_count=config.sampling.fallback_method_count,
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
    (output_dir / "manifest.json").write_text(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    (output_dir / "reviewer.html").write_text(_reviewer_html(config), encoding="utf-8", newline="\n")
    (output_dir / "README.md").write_text(_readme(config), encoding="utf-8", newline="\n")
    lines = [f"{_sha256_file(output_dir / name)}  {name}\n" for name in CHECKSUM_FILES]
    (output_dir / "checksums.txt").write_text("".join(lines), encoding="utf-8", newline="\n")


def plan_or_execute_h2_production_audit_sample(*, project_root: Path, config_path: Path, candidate_dir: Path, canonical_path: Path, output_root: Path | None = None, execute: bool = False) -> dict[str, Any]:
    root = project_root.resolve()
    config = load_h2_production_audit_config(config_path.resolve())
    candidate_dir = candidate_dir.resolve()
    canonical_path = canonical_path.resolve()
    parent = _candidate_parent(root, config, candidate_dir, canonical_path)
    selected_root = _resolve(root, output_root or config.execution.output_root)
    output_dir = selected_root / config.sampling.audit_id
    exists = output_dir.exists()
    report = {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "audit_id": config.sampling.audit_id,
        "candidate_build_id": parent["manifest"].build_id,
        "materialization_fingerprint_sha256": parent["manifest"].materialization_fingerprint_sha256,
        "canonical_sha256": config.canonical_snapshot.sha256,
        "canonical_document_count": config.canonical_snapshot.document_count,
        "audit_case_count": config.sampling.total_count,
        "override_sample_count": config.sampling.override_count,
        "preserved_method_sample_count": config.sampling.preserved_method_count,
        "fallback_method_sample_count": config.sampling.fallback_method_count,
        "sample_already_exists": exists,
        "prediction_blind": True,
        "plan_writes_output": False,
        "plan_reads_candidate_predictions": False,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "policy_revision_executed": False,
        "canonical_truth_mutated": False,
        "production_latest_promotion_authorized": False,
        "output_dir": str(output_dir),
        "next_slice": config.next_steps.after_plan if not execute else config.next_steps.after_execute,
    }
    if not execute:
        return report
    if exists:
        raise H2ProductionAuditError(f"Audit sample output already exists: {output_dir}")
    selected_by_stratum = _select_final_rows(candidate_dir, config)
    flat = [row for rows in selected_by_stratum.values() for row in rows]
    source_texts = _load_source_texts(canonical_path, flat)
    cases = _build_blind_cases(config, selected_by_stratum, source_texts)
    if len(cases) != config.sampling.total_count:
        raise H2ProductionAuditError("Audit case count mismatch")
    _write_package(output_dir, config, cases)
    report.update({"phase_complete": True, "sample_created": True, "sample_already_exists": True})
    return report


def prepare_h2_production_audit_annotation_work(*, project_root: Path, config_path: Path, audit_dir: Path, output_root: Path | None = None, execute: bool = False) -> dict[str, Any]:
    root = project_root.resolve()
    config = load_h2_production_audit_config(config_path.resolve())
    audit_dir = audit_dir.resolve()
    manifest = H2ProductionAuditManifest.model_validate(json.loads((audit_dir / "manifest.json").read_text(encoding="utf-8")))
    if manifest.audit_id != config.sampling.audit_id:
        raise H2ProductionAuditError("Audit package does not match config")
    selected_root = _resolve(root, output_root or config.execution.annotation_work_root)
    output_dir = selected_root / config.sampling.audit_id
    report = {
        "report": REPORT_NAME + "_annotation_work",
        "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "audit_id": config.sampling.audit_id,
        "annotation_row_count": config.sampling.total_count,
        "prediction_blind": True,
        "working_copy_is_mutable_non_evidence": True,
        "output_dir": str(output_dir),
        "next_slice": "complete_prediction_blind_h2_production_audit_annotation",
    }
    if not execute:
        return report
    if output_dir.exists():
        raise H2ProductionAuditError(f"Annotation work output already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    shutil.copyfile(audit_dir / "blank_annotations.jsonl", output_dir / "annotations_working.jsonl")
    shutil.copyfile(audit_dir / "reviewer.html", output_dir / "reviewer.html")
    (output_dir / "README.md").write_text(
        "# Mutable H2 production audit annotation work\n\nLoad `annotations_working.jsonl` in `reviewer.html`. Export frequently. This directory is mutable non-evidence until the next slice freezes the completed reference.\n",
        encoding="utf-8", newline="\n",
    )
    report["phase_complete"] = True
    return report


def validate_h2_production_audit_sample(*, project_root: Path, config_path: Path, audit_dir: Path, candidate_dir: Path, canonical_path: Path) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    root = project_root.resolve()
    config = load_h2_production_audit_config(config_path.resolve())
    audit_dir = audit_dir.resolve()
    candidate_dir = candidate_dir.resolve()
    canonical_path = canonical_path.resolve()
    checks: list[tuple[str, bool, str]] = []
    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))
    add("audit_directory_exists", audit_dir.is_dir(), audit_dir)
    if not audit_dir.is_dir():
        return checks, {"report": REPORT_NAME, "total_checks": len(checks), "required_failed_count": 1, "next_slice": "fix_h2_production_audit_sample"}
    actual = {p.name for p in audit_dir.iterdir() if p.is_file()}
    add("exact_file_layout", actual == set(REQUIRED_FILES), sorted(actual))
    checksum_map: dict[str, str] = {}
    for line in (audit_dir / "checksums.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split("  ", 1); checksum_map[name] = digest
    add("checksum_set_exact", set(checksum_map) == set(CHECKSUM_FILES), sorted(checksum_map))
    for name in CHECKSUM_FILES:
        add(f"checksum:{name}", checksum_map.get(name) == _sha256_file(audit_dir / name), name)
    for name in REQUIRED_FILES:
        add(f"lf:{name}", b"\r" not in (audit_dir / name).read_bytes(), name)
    parent = _candidate_parent(root, config, candidate_dir, canonical_path)
    manifest = H2ProductionAuditManifest.model_validate(json.loads((audit_dir / "manifest.json").read_text(encoding="utf-8")))
    add("audit_id_matches", manifest.audit_id == config.sampling.audit_id, manifest.audit_id)
    add("candidate_identity_matches", manifest.candidate_build_id == config.candidate.build_id and manifest.materialization_fingerprint_sha256 == config.candidate.materialization_fingerprint_sha256)
    add("canonical_snapshot_matches", manifest.canonical_sha256 == config.canonical_snapshot.sha256 and manifest.canonical_document_count == config.canonical_snapshot.document_count)
    add("audit_config_sha_matches", manifest.audit_config_sha256 == canonical_config_sha256(config))
    add("manifest_blindness_flags", all((manifest.prediction_blind, not manifest.sampled_stratum_exposed_in_cases, not manifest.candidate_prediction_exposed_in_cases, not manifest.semantic_scores_exposed_in_cases)))
    add("manifest_safety_flags", all((not manifest.model_inference_executed, not manifest.threshold_tuning_executed, not manifest.policy_revision_executed, not manifest.canonical_truth_mutated, not manifest.production_latest_promotion_authorized)))

    cases = [H2ProductionAuditCase.model_validate(json.loads(line)) for line in (audit_dir / "audit_cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    blanks = [H2ProductionAuditAnnotation.model_validate(json.loads(line)) for line in (audit_dir / "blank_annotations.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    add("audit_case_count_matches", len(cases) == config.sampling.total_count == manifest.audit_case_count, len(cases))
    add("audit_case_ids_unique", len({x.audit_case_id for x in cases}) == len(cases))
    add("blind_case_schema_has_no_forbidden_keys", all(not (set(x.model_dump(mode="json")) & FORBIDDEN_BLIND_KEYS) for x in cases))
    add("blank_annotations_align_exactly", len(blanks) == len(cases) and all((b.audit_case_id == c.audit_case_id and b.annotation_complete is False and b.reference_entity_type is None and b.span_status is None) for b, c in zip(blanks, cases)))

    selected_by_stratum = _select_final_rows(candidate_dir, config)
    flat = [row for rows in selected_by_stratum.values() for row in rows]
    source_texts = _load_source_texts(canonical_path, flat)
    expected = _build_blind_cases(config, selected_by_stratum, source_texts)
    add("deterministic_sample_recomputes_exactly", [x.model_dump(mode="json") for x in cases] == [x.model_dump(mode="json") for x in expected])
    add("stratum_counts_recompute_exactly", {k: len(v) for k, v in selected_by_stratum.items()} == {"override": config.sampling.override_count, "preserved_method": config.sampling.preserved_method_count, "fallback_method": config.sampling.fallback_method_count})
    add("all_sample_spans_match_authorized_canonical", all(hashlib.sha256(x.source_text.encode("utf-8")).hexdigest() == x.source_text_sha256 and x.source_text[x.char_start:x.char_end] == x.surface_text for x in cases))
    required_failed = sum(1 for _, ok, _ in checks if not ok)
    summary = {
        "report": REPORT_NAME,
        "validation_scope": "h2_production_audit_prediction_blind_sample",
        "audit_id": config.sampling.audit_id,
        "candidate_build_id": parent["manifest"].build_id,
        "audit_case_count": len(cases),
        "prediction_blind": True,
        "production_latest_promotion_authorized": False,
        "canonical_truth_mutated": False,
        "total_checks": len(checks),
        "required_failed_count": required_failed,
        "next_slice": "complete_prediction_blind_h2_production_audit_annotation" if required_failed == 0 else "fix_h2_production_audit_sample",
    }
    return checks, summary
