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
DEFAULT_CANONICAL_DIR = Path("data/analytics/reconciled")
DEFAULT_NORMALIZED_DIR = Path("data/normalized")

DEFAULT_MERGE_REPORTS = {
    "openalex_alignment": DEFAULT_UPDATE_DIR / "merge_openalex_alignment_latest.json",
    "semantic_scholar_alignment": DEFAULT_UPDATE_DIR / "merge_semantic_scholar_alignment_latest.json",
    "crossref_alignment": DEFAULT_UPDATE_DIR / "merge_crossref_alignment_latest.json",
}


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


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def safe_get(d: Any, *keys: str, default: Any = None) -> Any:
    cur = d
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


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


def summarize_canonical(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Canonical corpus not found: {path}")

    doc_count = 0
    multisource_docs = 0
    doi_count = 0
    max_source_count = 0

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            doc_count += 1

            source_count = int(payload.get("source_count", 0) or 0)
            if source_count > 1:
                multisource_docs += 1
            max_source_count = max(max_source_count, source_count)

            if payload.get("doi"):
                doi_count += 1

    return {
        "path": normalize_path(path),
        "doc_count": doc_count,
        "multisource_docs": multisource_docs,
        "doi_count": doi_count,
        "max_source_count": max_source_count,
    }


def is_full_snapshot_file(path: Path) -> bool:
    name = path.name
    if not name.startswith("documents.") or not name.endswith(".jsonl"):
        return False

    disallowed_suffixes = (
        ".new.jsonl",
        ".updated.jsonl",
        ".unchanged.jsonl",
    )
    return not name.endswith(disallowed_suffixes)


def discover_latest_full_snapshot(source_dir: Path) -> Path:
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    candidates = sorted(
        p for p in source_dir.glob("documents.*.jsonl")
        if is_full_snapshot_file(p)
    )
    if not candidates:
        raise FileNotFoundError(f"No full snapshot JSONL found in: {source_dir}")
    return candidates[-1]


def parse_merge_report_arg(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise ValueError(
            f"Invalid --merge-report value: {raw}. Expected format: source_name=path/to/report.json"
        )
    source_name, raw_path = raw.split("=", 1)
    source_name = source_name.strip()
    raw_path = raw_path.strip()

    if not source_name:
        raise ValueError(f"Invalid --merge-report source_name in: {raw}")
    if not raw_path:
        raise ValueError(f"Invalid --merge-report path in: {raw}")

    return source_name, Path(raw_path)


def resolve_merge_report_specs(
    cli_values: list[str] | None,
) -> dict[str, Path]:
    if cli_values:
        resolved: dict[str, Path] = {}
        for raw in cli_values:
            source_name, path = parse_merge_report_arg(raw)
            resolved[source_name] = path
        return resolved

    return dict(DEFAULT_MERGE_REPORTS)


def resolve_merged_snapshot_from_report(report_path: Path) -> dict[str, Any]:
    report = load_json(report_path)

    source_name = report.get("source_name")
    merged_snapshot_raw = safe_get(report, "output", "merged_snapshot")
    if not merged_snapshot_raw:
        raise ValueError(f"Merge report does not contain output.merged_snapshot: {report_path}")

    merged_snapshot = Path(str(merged_snapshot_raw))
    if not merged_snapshot.exists():
        raise FileNotFoundError(
            f"Merged snapshot declared in report does not exist: {merged_snapshot}"
        )

    return {
        "source_name": source_name,
        "report_path": report_path,
        "merged_snapshot": merged_snapshot,
        "stats": report.get("stats", {}),
        "generated_at_utc": report.get("generated_at_utc"),
        "run_ts": report.get("run_ts"),
    }


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Incremental reconcile stage report")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at']}")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Mode: `{report['mode']}`")
    lines.append(f"- Reconcile input mode: `{report['reconcile_input_mode']}`")
    lines.append("")

    lines.append("## Inputs")
    for k, v in report["inputs"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    lines.append("## Resolved input files")
    for k, v in report["resolved_inputs"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    lines.append("## Merge reports used")
    for item in report["merge_reports_used"]:
        lines.append(
            f"- `{item['source_name']}` | report=`{item['report_path']}` | "
            f"merged_snapshot=`{item['merged_snapshot']}`"
        )
    lines.append("")

    lines.append("## Readiness")
    for k, v in report["readiness"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    if report.get("candidate_output"):
        lines.append("## Candidate output")
        for k, v in report["candidate_output"].items():
            lines.append(f"- {k}: `{v}`")
        lines.append("")

    if report.get("canonical_summary"):
        lines.append("## Canonical summary")
        for k, v in report["canonical_summary"].items():
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
        description=(
            "Run incremental reconcile stage after selective enrichment refresh cycle "
            "using explicit merged full snapshots only."
        )
    )
    parser.add_argument(
        "--update-dir",
        type=Path,
        default=DEFAULT_UPDATE_DIR,
        help="Directory containing latest update reports.",
    )
    parser.add_argument(
        "--canonical-dir",
        type=Path,
        default=DEFAULT_CANONICAL_DIR,
        help="Directory containing canonical corpus JSONL files.",
    )
    parser.add_argument(
        "--normalized-dir",
        type=Path,
        default=DEFAULT_NORMALIZED_DIR,
        help="Base directory for normalized source snapshots.",
    )
    parser.add_argument(
        "--refresh-cycle-report",
        type=Path,
        default=None,
        help="Explicit path to refresh cycle report JSON. Defaults to update-dir/run_incremental_refresh_cycle_latest.json",
    )
    parser.add_argument(
        "--arxiv-input",
        type=Path,
        default=None,
        help="Explicit full arXiv snapshot JSONL path. If omitted, latest full arXiv snapshot is discovered automatically.",
    )
    parser.add_argument(
        "--merge-report",
        action="append",
        default=None,
        help=(
            "Alignment merge report in the format source_name=path/to/report.json. "
            "Can be passed multiple times. If omitted, defaults to latest OpenAlex / Semantic Scholar / Crossref merge reports."
        ),
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help=(
            "Candidate canonical output path. "
            "Defaults to data/analytics/reconciled/canonical_documents.incremental_candidate.<run_ts>.jsonl"
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute reconcile step instead of dry-run only.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    update_dir: Path = args.update_dir
    canonical_dir: Path = args.canonical_dir
    normalized_dir: Path = args.normalized_dir

    refresh_cycle_report_path = (
        args.refresh_cycle_report
        if args.refresh_cycle_report is not None
        else update_dir / "run_incremental_refresh_cycle_latest.json"
    )
    refresh_cycle_report = load_json(refresh_cycle_report_path)

    arxiv_input = (
        args.arxiv_input
        if args.arxiv_input is not None
        else discover_latest_full_snapshot(normalized_dir / "arxiv")
    )
    if not arxiv_input.exists():
        raise FileNotFoundError(f"Resolved arXiv input not found: {arxiv_input}")

    merge_report_specs = resolve_merge_report_specs(args.merge_report)
    merge_reports_used: list[dict[str, Any]] = []
    resolved_alignment_inputs: list[Path] = []

    missing_merge_reports: list[str] = []
    failed_merge_reports: list[str] = []

    for source_name, report_path in merge_report_specs.items():
        try:
            resolved = resolve_merged_snapshot_from_report(report_path)
            merge_reports_used.append(
                {
                    "source_name": source_name,
                    "report_path": normalize_path(report_path),
                    "merged_snapshot": normalize_path(resolved["merged_snapshot"]),
                    "stats": resolved.get("stats", {}),
                    "run_ts": resolved.get("run_ts"),
                    "generated_at_utc": resolved.get("generated_at_utc"),
                }
            )
            resolved_alignment_inputs.append(Path(resolved["merged_snapshot"]))
        except FileNotFoundError:
            missing_merge_reports.append(f"{source_name}::{normalize_path(report_path)}")
        except Exception as exc:
            failed_merge_reports.append(f"{source_name}::{exc}")

    candidate_output = (
        args.output_path
        if args.output_path is not None
        else canonical_dir / f"canonical_documents.incremental_candidate.{run_ts}.jsonl"
    )

    readiness = {
        "ready_for_reconcile_candidate": bool(
            safe_get(
                refresh_cycle_report,
                "readiness_summary",
                "ready_for_reconcile_candidate",
                default=False,
            )
        ),
        "selective_execution_ok": bool(
            safe_get(
                refresh_cycle_report,
                "execution_summary",
                "all_successful",
                default=False,
            )
        ),
        "has_any_enrichment_hits": bool(
            safe_get(
                refresh_cycle_report,
                "readiness_summary",
                "has_any_enrichment_hits",
                default=False,
            )
        ),
        "total_found_rows_across_sources": int(
            safe_get(
                refresh_cycle_report,
                "readiness_summary",
                "total_found_rows_across_sources",
                default=0,
            ) or 0
        ),
        "merge_reports_resolved_ok": len(missing_merge_reports) == 0 and len(failed_merge_reports) == 0,
        "resolved_alignment_input_count": len(resolved_alignment_inputs),
        "resolved_alignment_inputs_exist": all(p.exists() for p in resolved_alignment_inputs),
        "arxiv_input_exists": arxiv_input.exists(),
        "safe_input_set": (
            arxiv_input.exists()
            and len(resolved_alignment_inputs) > 0
            and all(p.exists() for p in resolved_alignment_inputs)
            and len(missing_merge_reports) == 0
            and len(failed_merge_reports) == 0
        ),
    }

    readiness["safe_to_execute"] = (
        readiness["ready_for_reconcile_candidate"]
        and readiness["selective_execution_ok"]
        and readiness["has_any_enrichment_hits"]
        and readiness["safe_input_set"]
    )

    reconcile_input_mode = "merged_full_inputs"

    reconcile_cmd = [
        sys.executable,
        "-m",
        "scripts.normalize.run_reconcile",
        "--inputs",
        str(arxiv_input),
        *[str(p) for p in resolved_alignment_inputs],
        "--output",
        str(candidate_output),
    ]

    planned_steps = [
        {
            "name": "verify_refresh_cycle_readiness",
            "will_run": True,
            "reason": (
                "Refresh cycle report is available and treated as the upstream gate."
            ),
            "cmd": None,
        },
        {
            "name": "resolve_safe_reconcile_inputs",
            "will_run": True,
            "reason": (
                "Merged full snapshots are required. latest-only reconcile is intentionally forbidden."
            ),
            "cmd": None,
        },
        {
            "name": "full_reconcile_candidate",
            "will_run": readiness["safe_to_execute"],
            "reason": (
                "Safe reconcile candidate can run because refresh readiness passed and merged full inputs were resolved."
                if readiness["safe_to_execute"]
                else "Reconcile candidate is blocked because safe merged full inputs or upstream readiness are incomplete."
            ),
            "cmd": " ".join(reconcile_cmd),
        },
        {
            "name": "promote_canonical_latest",
            "will_run": False,
            "reason": "Deferred intentionally. Promotion must remain a separate controlled step after candidate validation.",
            "cmd": None,
        },
        {
            "name": "full_export_postgres",
            "will_run": False,
            "reason": "Deferred. Export remains downstream after candidate validation and promotion.",
            "cmd": f"{sys.executable} -m scripts.export.export_postgres_v1",
        },
        {
            "name": "full_retrieval_rebuild",
            "will_run": False,
            "reason": "Deferred. Retrieval rebuild remains downstream after export.",
            "cmd": f"{sys.executable} -m scripts.retrieval.build_indexes",
        },
    ]

    executed_steps: list[dict[str, Any]] = []
    canonical_summary: dict[str, Any] | None = None

    should_run_reconcile = args.execute and readiness["safe_to_execute"]

    if should_run_reconcile:
        executed_steps.append(run_step("full_reconcile_candidate", reconcile_cmd))
        if executed_steps[-1]["ok"]:
            canonical_summary = summarize_canonical(candidate_output)

    execution_summary = {
        "executed_count": len(executed_steps),
        "failed_count": len([s for s in executed_steps if not s["ok"]]),
        "all_successful": all(s["ok"] for s in executed_steps) if executed_steps else True,
        "failed_step_names": [s["name"] for s in executed_steps if not s["ok"]],
    }

    report = {
        "report_name": "run_incremental_reconcile_stage",
        "generated_at": utc_now_iso(),
        "run_ts": run_ts,
        "mode": "execute" if args.execute else "dry_run",
        "reconcile_input_mode": reconcile_input_mode,
        "inputs": {
            "refresh_cycle_report": normalize_path(refresh_cycle_report_path),
            "arxiv_input_requested": normalize_path(args.arxiv_input),
            "canonical_dir": normalize_path(canonical_dir),
            "normalized_dir": normalize_path(normalized_dir),
            "output_path_requested": normalize_path(args.output_path),
        },
        "resolved_inputs": {
            "arxiv_full_snapshot": normalize_path(arxiv_input),
            "alignment_merged_snapshots": [normalize_path(p) for p in resolved_alignment_inputs],
        },
        "merge_reports_used": merge_reports_used,
        "merge_report_resolution_errors": {
            "missing_merge_reports": missing_merge_reports,
            "failed_merge_reports": failed_merge_reports,
        },
        "readiness": readiness,
        "candidate_output": {
            "path": normalize_path(candidate_output),
            "exists": candidate_output.exists(),
        },
        "canonical_summary": canonical_summary,
        "planned_steps": planned_steps,
        "execution_summary": execution_summary,
        "executed_steps": executed_steps,
    }

    latest_json = update_dir / "run_incremental_reconcile_stage_latest.json"
    latest_md = update_dir / "run_incremental_reconcile_stage_latest.md"
    hist_json = update_dir / "history" / f"run_incremental_reconcile_stage_{run_ts}.json"
    hist_md = update_dir / "history" / f"run_incremental_reconcile_stage_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] mode={report['mode']}")
    print(f"[OK] reconcile_input_mode={report['reconcile_input_mode']}")
    print(f"[OK] ready_for_reconcile_candidate={readiness['ready_for_reconcile_candidate']}")
    print(f"[OK] selective_execution_ok={readiness['selective_execution_ok']}")
    print(f"[OK] safe_input_set={readiness['safe_input_set']}")
    print(f"[OK] safe_to_execute={readiness['safe_to_execute']}")
    print(f"[OK] executed_count={execution_summary['executed_count']}")
    print(f"[OK] failed_count={execution_summary['failed_count']}")
    print(f"[OK] candidate_output_path={normalize_path(candidate_output)}")
    if canonical_summary:
        print(f"[OK] canonical_doc_count={canonical_summary['doc_count']}")
        print(f"[OK] multisource_docs={canonical_summary['multisource_docs']}")
        print(f"[OK] canonical_path={canonical_summary['path']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()