from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPORTS_DIR = Path("artifacts/reports")
DEFAULT_UPDATE_DIR = DEFAULT_REPORTS_DIR / "update"


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def safe_get(d: Any, *keys: str, default: Any = None) -> Any:
    cur = d
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def summarize_openalex(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": True,
        "input_mode": safe_get(report, "inputs", "input_mode", default=None),
        "requested_doi_count": safe_get(report, "inputs", "requested_doi_count", default=None),
        "found": int(safe_get(report, "summary", "found", default=0) or 0),
        "not_found": int(safe_get(report, "summary", "not_found", default=0) or 0),
        "error": int(safe_get(report, "summary", "error", default=0) or 0),
        "normalized_docs_written": int(
            safe_get(report, "summary", "normalized_docs_written", default=0) or 0
        ),
        "report_run_ts": report.get("generated_at_utc"),
    }


def summarize_semantic_scholar(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": True,
        "input_mode": report.get("input_mode"),
        "doi_candidates": report.get("doi_candidates"),
        "fetched_entries": report.get("fetched_entries", 0),
        "normalized_docs": report.get("normalized_docs", 0),
        "failed_batches": report.get("failed_batches", 0),
        "report_run_ts": report.get("run_ts"),
    }


def summarize_crossref(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": True,
        "input_mode": report.get("input_mode"),
        "doi_candidates": report.get("doi_candidates"),
        "fetched_entries": int(report.get("fetched_entries", 0) or 0),
        "normalized_docs": int(report.get("normalized_docs", 0) or 0),
        "found": int(safe_get(report, "status_counts", "found", default=0) or 0),
        "not_found": int(safe_get(report, "status_counts", "not_found", default=0) or 0),
        "error": int(report.get("error", 0) or 0),
        "report_run_ts": report.get("generated_at"),
    }


def build_enrichment_summary(
    openalex_report: dict[str, Any] | None,
    semantic_report: dict[str, Any] | None,
    crossref_report: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "openalex": summarize_openalex(openalex_report) if openalex_report else {"available": False},
        "semantic_scholar": summarize_semantic_scholar(semantic_report) if semantic_report else {"available": False},
        "crossref": summarize_crossref(crossref_report) if crossref_report else {"available": False},
    }


def build_readiness_summary(
    *,
    doi_candidates_count: int,
    enrichment_summary: dict[str, Any],
) -> dict[str, Any]:
    openalex_hits = int(safe_get(enrichment_summary, "openalex", "normalized_docs_written", default=0) or 0)
    semantic_hits = int(safe_get(enrichment_summary, "semantic_scholar", "normalized_docs", default=0) or 0)
    crossref_hits = int(safe_get(enrichment_summary, "crossref", "normalized_docs", default=0) or 0)

    total_found_rows = openalex_hits + semantic_hits + crossref_hits
    has_any_hits = total_found_rows > 0

    return {
        "has_doi_candidates": doi_candidates_count > 0,
        "has_any_enrichment_hits": has_any_hits,
        "openalex_has_hits": openalex_hits > 0,
        "semantic_scholar_has_hits": semantic_hits > 0,
        "crossref_has_hits": crossref_hits > 0,
        "total_found_rows_across_sources": total_found_rows,
        "ready_for_reconcile_candidate": doi_candidates_count > 0 and has_any_hits,
    }


def build_cmds(doi_input: Path, doi_candidates_count: int) -> dict[str, list[str]]:
    py = sys.executable

    return {
        "selective_openalex_alignment": [
            py,
            "-m",
            "scripts.ingest.run_openalex_alignment",
            "--doi-list",
            str(doi_input),
            "--limit",
            str(doi_candidates_count),
            "--sleep-seconds",
            "0.2",
        ],
        "selective_semantic_scholar_alignment": [
            py,
            "-m",
            "scripts.ingest.run_semantic_scholar_alignment",
            "--doi-list",
            str(doi_input),
            "--batch-size",
            "10",
            "--sleep-seconds",
            "1.5",
        ],
        "selective_crossref_alignment": [
            py,
            "-m",
            "scripts.ingest.run_crossref_alignment",
            "--doi-list",
            str(doi_input),
            "--batch-size",
            "10",
        ],
    }


def run_step(name: str, cmd: list[str]) -> dict[str, Any]:
    started_at = utc_now_iso()
    t0 = time.perf_counter()

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    finished_at = utc_now_iso()
    duration_sec = round(time.perf_counter() - t0, 3)

    return {
        "name": name,
        "cmd": " ".join(cmd),
        "returncode": result.returncode,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_sec": duration_sec,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
        "ok": result.returncode == 0,
    }


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []

    lines.append("# Incremental refresh cycle report")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at']}")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Mode: `{report['mode']}`")
    lines.append("")

    counts = report["counts"]
    lines.append("## Counts")
    lines.append(f"- new_docs_total: **{counts['new_docs_total']}**")
    lines.append(f"- updated_docs_total: **{counts['updated_docs_total']}**")
    lines.append(f"- unique_doi_candidates: **{counts['unique_doi_candidates']}**")
    lines.append(f"- canonical_doc_count: **{counts['canonical_doc_count']}**")
    lines.append(f"- retrieval_doc_count: **{counts['retrieval_doc_count']}**")
    lines.append("")

    lines.append("## Enrichment summary")
    for source_name, item in report["enrichment_summary"].items():
        lines.append(f"### {source_name}")
        for k, v in item.items():
            lines.append(f"- {k}: `{v}`")
        lines.append("")

    lines.append("## Readiness summary")
    for k, v in report["readiness_summary"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    lines.append("## Execution summary")
    for k, v in report["execution_summary"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    lines.append("## Planned steps")
    for step in report["planned_steps"]:
        lines.append(
            f"- `{step['name']}` | will_run={step['will_run']} | reason={step['reason']}"
        )
    lines.append("")

    if report.get("executed_steps"):
        lines.append("## Executed steps")
        for step in report["executed_steps"]:
            lines.append(f"### {step['name']}")
            lines.append(f"- ok: `{step['ok']}`")
            lines.append(f"- returncode: `{step['returncode']}`")
            lines.append(f"- duration_sec: `{step['duration_sec']}`")
            lines.append(f"- cmd: `{step['cmd']}`")
            lines.append("")
    else:
        lines.append("## Executed steps")
        lines.append("- none")
        lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run incremental refresh cycle orchestration for selective DOI enrichment."
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Base reports directory.",
    )
    parser.add_argument(
        "--update-dir",
        type=Path,
        default=DEFAULT_UPDATE_DIR,
        help="Directory containing latest update reports.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute selective enrichment steps instead of dry-run only.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    reports_dir: Path = args.reports_dir
    update_dir: Path = args.update_dir

    plan_report_path = update_dir / "plan_incremental_refresh_latest.json"
    doi_extract_report_path = update_dir / "extract_incremental_doi_candidates_latest.json"
    doi_input_path = update_dir / "doi_candidates_latest.jsonl"

    openalex_latest_report_path = reports_dir / "openalex_alignment_ingest_latest.json"
    semantic_latest_report_path = reports_dir / "semantic_scholar_alignment_ingest_latest.json"
    crossref_latest_report_path = reports_dir / "crossref_alignment_ingest_latest.json"

    plan_report = load_json(plan_report_path)
    doi_extract_report = load_json(doi_extract_report_path)

    if not doi_input_path.exists():
        raise FileNotFoundError(f"DOI input file not found: {doi_input_path}")

    unique_doi_candidates = int(
        safe_get(doi_extract_report, "counts", "unique_doi_candidates", default=0) or 0
    )
    new_docs_total = int(safe_get(doi_extract_report, "counts", "new_docs_total", default=0) or 0)
    updated_docs_total = int(
        safe_get(doi_extract_report, "counts", "updated_docs_total", default=0) or 0
    )

    canonical_doc_count = int(
        safe_get(plan_report, "canonical_summary", "doc_count", default=0) or 0
    )
    retrieval_doc_count = int(
        safe_get(plan_report, "retrieval_summary", "corpus_doc_count", default=0) or 0
    )

    cmds = build_cmds(doi_input_path, unique_doi_candidates)

    planned_steps = [
        {
            "name": "inspect_incremental_merge",
            "will_run": True,
            "reason": "Latest incremental merge and DOI candidate extraction reports are available.",
            "cmd": None,
        },
        {
            "name": "selective_openalex_alignment",
            "will_run": unique_doi_candidates > 0,
            "reason": "Selective OpenAlex enrichment should run on DOI candidates."
            if unique_doi_candidates > 0
            else "No DOI candidates found.",
            "cmd": " ".join(cmds["selective_openalex_alignment"]) if unique_doi_candidates > 0 else None,
        },
        {
            "name": "selective_semantic_scholar_alignment",
            "will_run": unique_doi_candidates > 0,
            "reason": "Selective Semantic Scholar enrichment should run on DOI candidates."
            if unique_doi_candidates > 0
            else "No DOI candidates found.",
            "cmd": " ".join(cmds["selective_semantic_scholar_alignment"]) if unique_doi_candidates > 0 else None,
        },
        {
            "name": "selective_crossref_alignment",
            "will_run": unique_doi_candidates > 0,
            "reason": "Selective Crossref enrichment should run on DOI candidates."
            if unique_doi_candidates > 0
            else "No DOI candidates found.",
            "cmd": " ".join(cmds["selective_crossref_alignment"]) if unique_doi_candidates > 0 else None,
        },
        {
            "name": "full_reconcile",
            "will_run": False,
            "reason": "Deferred in this version. This report records that reconcile is the next downstream full rebuild step after selective enrichment.",
            "cmd": f"{sys.executable} -m scripts.normalize.run_reconcile",
        },
        {
            "name": "full_export_postgres",
            "will_run": False,
            "reason": "Deferred in this version. Export follows reconcile.",
            "cmd": f"{sys.executable} -m scripts.export.export_postgres_v1",
        },
        {
            "name": "full_retrieval_rebuild",
            "will_run": False,
            "reason": "Deferred in this version. Retrieval rebuild follows export.",
            "cmd": f"{sys.executable} -m scripts.retrieval.build_indexes",
        },
    ]

    executed_steps: list[dict[str, Any]] = []

    if args.execute and unique_doi_candidates > 0:
        for step_name in [
            "selective_openalex_alignment",
            "selective_semantic_scholar_alignment",
            "selective_crossref_alignment",
        ]:
            executed_steps.append(run_step(step_name, cmds[step_name]))

    openalex_report = load_json(openalex_latest_report_path) if openalex_latest_report_path.exists() else None
    semantic_report = load_json(semantic_latest_report_path) if semantic_latest_report_path.exists() else None
    crossref_report = load_json(crossref_latest_report_path) if crossref_latest_report_path.exists() else None

    enrichment_summary = build_enrichment_summary(
        openalex_report=openalex_report,
        semantic_report=semantic_report,
        crossref_report=crossref_report,
    )

    readiness_summary = build_readiness_summary(
        doi_candidates_count=unique_doi_candidates,
        enrichment_summary=enrichment_summary,
    )

    failed_step_names = [step["name"] for step in executed_steps if not step["ok"]]
    execution_summary = {
        "executed_count": len(executed_steps),
        "failed_count": len(failed_step_names),
        "all_successful": len(failed_step_names) == 0,
        "failed_step_names": failed_step_names,
    }

    report = {
        "report_name": "run_incremental_refresh_cycle",
        "generated_at": utc_now_iso(),
        "run_ts": run_ts,
        "mode": "execute" if args.execute else "dry_run",
        "inputs": {
            "plan_report": normalize_path(plan_report_path),
            "doi_extract_report": normalize_path(doi_extract_report_path),
            "doi_input": normalize_path(doi_input_path),
            "openalex_latest_report": normalize_path(openalex_latest_report_path),
            "semantic_scholar_latest_report": normalize_path(semantic_latest_report_path),
            "crossref_latest_report": normalize_path(crossref_latest_report_path),
            "incremental_merge_report": safe_get(
                plan_report, "incremental_merge_summary", "path", default=None
            ),
        },
        "counts": {
            "new_docs_total": new_docs_total,
            "updated_docs_total": updated_docs_total,
            "unique_doi_candidates": unique_doi_candidates,
            "canonical_doc_count": canonical_doc_count,
            "retrieval_doc_count": retrieval_doc_count,
        },
        "enrichment_summary": enrichment_summary,
        "readiness_summary": readiness_summary,
        "execution_summary": execution_summary,
        "planned_steps": planned_steps,
        "executed_steps": executed_steps,
    }

    latest_json = update_dir / "run_incremental_refresh_cycle_latest.json"
    latest_md = update_dir / "run_incremental_refresh_cycle_latest.md"
    hist_json = update_dir / "history" / f"run_incremental_refresh_cycle_{run_ts}.json"
    hist_md = update_dir / "history" / f"run_incremental_refresh_cycle_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] mode={report['mode']}")
    print(f"[OK] unique_doi_candidates={unique_doi_candidates}")
    print(f"[OK] ready_for_reconcile_candidate={readiness_summary['ready_for_reconcile_candidate']}")
    print(f"[OK] executed_count={execution_summary['executed_count']}")
    print(f"[OK] failed_count={execution_summary['failed_count']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()