from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CANONICAL_DIR = Path("data/analytics/reconciled")
DEFAULT_UPDATE_DIR = Path("artifacts/reports/update")
DEFAULT_VALIDATION_DIR = Path("artifacts/reports/validation")


STEP_ORDER = [
    "reconcile_candidate",
    "candidate_provenance_audit",
    "promote_candidate",
    "export_postgres",
    "rebuild_retrieval",
    "retrieval_checks",
    "postpass_audit",
    "known_issues",
    "dod_check",
]


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


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def summarize_canonical(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None

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


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Refresh pipeline v1 report")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Mode: `{report['mode']}`")
    lines.append(f"- Stop after: `{report['stop_after']}`")
    lines.append("")

    lines.append("## Inputs")
    for k, v in report["inputs"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    lines.append("## Candidate")
    for k, v in report["candidate"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    if report.get("candidate_summary"):
        lines.append("## Candidate summary")
        for k, v in report["candidate_summary"].items():
            lines.append(f"- {k}: `{v}`")
        lines.append("")

    lines.append("## Planned steps")
    for step in report["planned_steps"]:
        lines.append(
            f"- `{step['name']}` | enabled={step['enabled']} | "
            f"will_run={step['will_run']} | reason={step['reason']}"
        )
    lines.append("")

    lines.append("## Execution summary")
    for k, v in report["execution_summary"].items():
        lines.append(f"- {k}: `{v}`")
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
        description="Thin orchestration wrapper for the manual safe refresh pipeline."
    )
    parser.add_argument(
        "--arxiv-input",
        type=Path,
        default=None,
        help="Explicit full arXiv snapshot path forwarded to run_incremental_reconcile_stage.py",
    )
    parser.add_argument(
        "--candidate-path",
        type=Path,
        default=None,
        help="Candidate canonical path. If omitted, a timestamped candidate path is created.",
    )
    parser.add_argument(
        "--canonical-dir",
        type=Path,
        default=DEFAULT_CANONICAL_DIR,
        help="Canonical directory.",
    )
    parser.add_argument(
        "--update-dir",
        type=Path,
        default=DEFAULT_UPDATE_DIR,
        help="Update reports directory.",
    )
    parser.add_argument(
        "--validation-dir",
        type=Path,
        default=DEFAULT_VALIDATION_DIR,
        help="Validation reports directory.",
    )
    parser.add_argument(
        "--merge-report",
        action="append",
        default=None,
        help=(
            "Optional passthrough merge report spec for reconcile stage: "
            "source_name=path/to/report.json. Can be repeated."
        ),
    )
    parser.add_argument(
        "--stop-after",
        choices=STEP_ORDER,
        default="dod_check",
        help="Last step to include in this pipeline run.",
    )
    parser.add_argument(
        "--require-known-issues",
        action="store_true",
        help="Forward --require-known-issues to DoD check.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the pipeline. Without this flag, dry-run only.",
    )
    return parser


def step_enabled(step_name: str, stop_after: str) -> bool:
    return STEP_ORDER.index(step_name) <= STEP_ORDER.index(stop_after)


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    candidate_path = (
        args.candidate_path
        if args.candidate_path is not None
        else args.canonical_dir / f"canonical_documents.pipeline_candidate.{run_ts}.jsonl"
    )

    reconcile_cmd = [sys.executable, "-m", "scripts.update.run_incremental_reconcile_stage"]
    if args.arxiv_input is not None:
        reconcile_cmd.extend(["--arxiv-input", str(args.arxiv_input)])
    if args.merge_report:
        for item in args.merge_report:
            reconcile_cmd.extend(["--merge-report", item])
    reconcile_cmd.extend(["--output-path", str(candidate_path)])
    if args.execute:
        reconcile_cmd.append("--execute")

    candidate_provenance_cmd = [
        sys.executable,
        "-m",
        "scripts.validation.check_canonical_provenance_consistency",
        "--canonical-path",
        str(candidate_path),
    ]

    promote_cmd = [
        sys.executable,
        "-m",
        "scripts.update.promote_canonical_candidate",
        "--candidate-path",
        str(candidate_path),
    ]
    if args.execute:
        promote_cmd.append("--execute")

    export_cmd = [sys.executable, "-m", "scripts.export.export_postgres_v1"]
    rebuild_cmd = [sys.executable, "-m", "scripts.retrieval.build_indexes"]
    retrieval_checks_cmd = [sys.executable, "-m", "scripts.validation.run_retrieval_checks"]
    postpass_audit_cmd = [sys.executable, "-m", "scripts.validation.run_postpass_audit"]
    known_issues_cmd = [sys.executable, "-m", "scripts.validation.build_known_issues_snapshot"]

    dod_cmd = [sys.executable, "-m", "scripts.update.check_refresh_definition_of_done"]
    if args.require_known_issues:
        dod_cmd.append("--require-known-issues")

    step_cmds = {
        "reconcile_candidate": reconcile_cmd,
        "candidate_provenance_audit": candidate_provenance_cmd,
        "promote_candidate": promote_cmd,
        "export_postgres": export_cmd,
        "rebuild_retrieval": rebuild_cmd,
        "retrieval_checks": retrieval_checks_cmd,
        "postpass_audit": postpass_audit_cmd,
        "known_issues": known_issues_cmd,
        "dod_check": dod_cmd,
    }

    planned_steps = []
    for step_name in STEP_ORDER:
        enabled = step_enabled(step_name, args.stop_after)
        will_run = bool(args.execute and enabled)
        if not enabled:
            reason = f"Excluded because stop-after={args.stop_after}"
        elif not args.execute:
            reason = "Dry-run mode only"
        else:
            reason = "Included in execute run"
        planned_steps.append(
            {
                "name": step_name,
                "enabled": enabled,
                "will_run": will_run,
                "reason": reason,
                "cmd": " ".join(step_cmds[step_name]),
            }
        )

    executed_steps: list[dict[str, Any]] = []
    failed = False

    if args.execute:
        for step_name in STEP_ORDER:
            if not step_enabled(step_name, args.stop_after):
                continue

            result = run_step(step_name, step_cmds[step_name])
            executed_steps.append(result)

            if not result["ok"]:
                failed = True
                break

    candidate_summary = summarize_canonical(candidate_path)

    execution_summary = {
        "executed_count": len(executed_steps),
        "failed_count": len([s for s in executed_steps if not s["ok"]]),
        "all_successful": all(s["ok"] for s in executed_steps) if executed_steps else True,
        "failed_step_names": [s["name"] for s in executed_steps if not s["ok"]],
        "stopped_early_due_to_failure": failed,
    }

    report = {
        "report_name": "run_refresh_pipeline_v1",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "mode": "execute" if args.execute else "dry_run",
        "stop_after": args.stop_after,
        "inputs": {
            "arxiv_input": normalize_path(args.arxiv_input),
            "canonical_dir": normalize_path(args.canonical_dir),
            "update_dir": normalize_path(args.update_dir),
            "validation_dir": normalize_path(args.validation_dir),
            "merge_reports": args.merge_report or [],
            "require_known_issues": bool(args.require_known_issues),
        },
        "candidate": {
            "path": normalize_path(candidate_path),
            "exists": candidate_path.exists(),
        },
        "candidate_summary": candidate_summary,
        "planned_steps": planned_steps,
        "execution_summary": execution_summary,
        "executed_steps": executed_steps,
    }

    latest_json = args.update_dir / "run_refresh_pipeline_v1_latest.json"
    latest_md = args.update_dir / "run_refresh_pipeline_v1_latest.md"
    hist_json = args.update_dir / "history" / f"run_refresh_pipeline_v1_{run_ts}.json"
    hist_md = args.update_dir / "history" / f"run_refresh_pipeline_v1_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] mode={report['mode']}")
    print(f"[OK] stop_after={report['stop_after']}")
    print(f"[OK] candidate_path={normalize_path(candidate_path)}")
    if candidate_summary:
        print(f"[OK] candidate_doc_count={candidate_summary['doc_count']}")
        print(f"[OK] candidate_multisource_docs={candidate_summary['multisource_docs']}")
    print(f"[OK] executed_count={execution_summary['executed_count']}")
    print(f"[OK] failed_count={execution_summary['failed_count']}")
    print(f"[OK] failed_step_names={execution_summary['failed_step_names']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()