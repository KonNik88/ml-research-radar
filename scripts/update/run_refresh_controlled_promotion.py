from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


REPORT_NAME = "run_refresh_controlled_promotion"
SCHEMA_VERSION = "refresh_controlled_promotion_v0.1"

DEFAULT_CANONICAL_DIR = Path("data/analytics/reconciled")
DEFAULT_UPDATE_DIR = Path("artifacts/reports/update")
DEFAULT_VALIDATION_DIR = Path("artifacts/reports/validation")


STEP_ORDER = [
    "promotion_readiness",
    "promote_candidate",
    "canonical_provenance_consistency",
    "canonical_contract_check",
]


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: Mapping[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def paths_match(left: Path | str | None, right: Path | str | None) -> bool:
    left_text = normalize_path(left)
    right_text = normalize_path(right)
    if not left_text or not right_text:
        return False
    if left_text == right_text:
        return True
    return left_text.endswith(f"/{right_text}") or right_text.endswith(f"/{left_text}")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    return {}


def as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def dig(data: Any, *keys: str, default: Any = None) -> Any:
    cur = data
    for key in keys:
        if not isinstance(cur, Mapping):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def readiness_candidate_path(readiness: Mapping[str, Any]) -> str | None:
    return (
        dig(readiness, "summary", "candidate_path", default=None)
        or dig(readiness, "inputs", "candidate_path", default=None)
    )


def readiness_promotion_ready(readiness: Mapping[str, Any]) -> bool:
    return bool(
        dig(readiness, "verdict", "promotion_ready", default=False)
        and safe_int(dig(readiness, "verdict", "required_failed_count", default=1)) == 0
    )


def summarize_jsonl(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {
            "path": normalize_path(path),
            "exists": False,
            "doc_count": 0,
            "bad_json_count": 0,
            "missing_canonical_id_count": 0,
            "duplicate_canonical_id_count": 0,
        }

    doc_count = 0
    bad_json_count = 0
    missing_canonical_id_count = 0
    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                bad_json_count += 1
                continue
            if not isinstance(row, Mapping):
                bad_json_count += 1
                continue

            doc_count += 1
            canonical_id = row.get("canonical_id")
            if not canonical_id:
                missing_canonical_id_count += 1
                continue
            key = str(canonical_id)
            if key in seen_ids:
                duplicate_ids.add(key)
            seen_ids.add(key)

    return {
        "path": normalize_path(path),
        "exists": True,
        "doc_count": doc_count,
        "bad_json_count": bad_json_count,
        "missing_canonical_id_count": missing_canonical_id_count,
        "duplicate_canonical_id_count": len(duplicate_ids),
    }


def resolve_candidate_path(
    *,
    explicit_candidate_path: Path | None,
    readiness: Mapping[str, Any],
) -> Path | None:
    if explicit_candidate_path is not None:
        return explicit_candidate_path
    raw = readiness_candidate_path(readiness)
    return Path(str(raw)) if raw else None


def build_prechecks(
    *,
    canonical_dir: Path,
    candidate_path: Path | None,
    readiness_path: Path,
    readiness: Mapping[str, Any],
) -> dict[str, bool]:
    latest_path = canonical_dir / "canonical_documents.jsonl"
    readiness_candidate = readiness_candidate_path(readiness)
    candidate_summary = summarize_jsonl(candidate_path)
    latest_summary = summarize_jsonl(latest_path)

    return {
        "readiness_report_exists": bool(readiness_path.exists() and readiness),
        "readiness_promotion_ready": readiness_promotion_ready(readiness),
        "candidate_path_resolved": candidate_path is not None,
        "candidate_path_matches_readiness": paths_match(candidate_path, readiness_candidate),
        "candidate_exists": bool(candidate_summary["exists"]),
        "candidate_jsonl_valid": candidate_summary["bad_json_count"] == 0,
        "candidate_ids_present": candidate_summary["missing_canonical_id_count"] == 0,
        "candidate_ids_unique": candidate_summary["duplicate_canonical_id_count"] == 0,
        "latest_exists": bool(latest_summary["exists"]),
        "candidate_differs_from_latest_path": bool(
            candidate_path is not None and not paths_match(candidate_path, latest_path)
        ),
    }


def build_required_precheck_names() -> list[str]:
    return [
        "readiness_report_exists",
        "readiness_promotion_ready",
        "candidate_path_resolved",
        "candidate_path_matches_readiness",
        "candidate_exists",
        "candidate_jsonl_valid",
        "candidate_ids_present",
        "candidate_ids_unique",
        "latest_exists",
        "candidate_differs_from_latest_path",
    ]


def build_step_commands(
    *,
    candidate_path: Path,
    canonical_dir: Path,
    update_dir: Path,
    validation_dir: Path,
    require_db_smoke: bool,
    execute: bool,
) -> dict[str, list[str]]:
    latest_path = canonical_dir / "canonical_documents.jsonl"

    readiness_cmd = [
        sys.executable,
        "-m",
        "scripts.validation.check_refresh_promotion_readiness",
        "--strict",
        "--candidate-path",
        str(candidate_path),
        "--update-dir",
        str(update_dir),
        "--validation-dir",
        str(validation_dir),
    ]
    if require_db_smoke:
        readiness_cmd.append("--require-db-smoke")

    promote_cmd = [
        sys.executable,
        "-m",
        "scripts.update.promote_canonical_candidate",
        "--candidate-path",
        str(candidate_path),
        "--canonical-dir",
        str(canonical_dir),
        "--update-dir",
        str(update_dir),
    ]
    if execute:
        promote_cmd.append("--execute")

    return {
        "promotion_readiness": readiness_cmd,
        "promote_candidate": promote_cmd,
        "canonical_provenance_consistency": [
            sys.executable,
            "-m",
            "scripts.validation.check_canonical_provenance_consistency",
            "--canonical-path",
            str(latest_path),
            "--reports-dir",
            str(validation_dir),
        ],
        "canonical_contract_check": [
            sys.executable,
            "-m",
            "scripts.validation.check_canonical_contract",
            "--strict",
            "--canonical-path",
            str(latest_path),
            "--reports-dir",
            str(validation_dir),
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
    return {
        "name": name,
        "cmd": " ".join(cmd),
        "returncode": result.returncode,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_sec": round(time.perf_counter() - t0, 3),
        "stdout_tail": (result.stdout or "")[-4000:],
        "stderr_tail": (result.stderr or "")[-4000:],
        "ok": result.returncode == 0,
    }


StepRunner = Callable[[str, list[str]], dict[str, Any]]


def load_post_execution_reports(
    *,
    update_dir: Path,
    validation_dir: Path,
) -> dict[str, Mapping[str, Any]]:
    return {
        "promote": read_json(update_dir / "promote_canonical_candidate_latest.json"),
        "canonical_provenance": read_json(
            validation_dir / "canonical_provenance_consistency_latest.json"
        ),
        "canonical_contract": read_json(validation_dir / "canonical_contract_latest.json"),
    }


def build_post_execution_checks(
    *,
    reports: Mapping[str, Mapping[str, Any]],
    candidate_doc_count: int,
) -> dict[str, bool]:
    promote = as_mapping(reports.get("promote"))
    provenance = as_mapping(reports.get("canonical_provenance"))
    contract = as_mapping(reports.get("canonical_contract"))

    return {
        "promote_report_exists": bool(promote),
        "promote_executed": bool(dig(promote, "execution_summary", "executed")),
        "promote_backup_created": bool(
            dig(promote, "execution_summary", "backup_created")
        ),
        "promote_performed": bool(
            dig(promote, "execution_summary", "promotion_performed")
        ),
        "promote_postcheck_match": bool(
            dig(promote, "execution_summary", "postcheck_match")
        ),
        "promoted_doc_count_matches_candidate": (
            safe_int(dig(promote, "new_latest_summary", "doc_count", default=-1), default=-1)
            == candidate_doc_count
        ),
        "canonical_provenance_report_exists": bool(provenance),
        "canonical_provenance_error_checks_clean": bool(
            dig(provenance, "summary", "all_error_checks_clean", default=False)
        ),
        "canonical_contract_report_exists": bool(contract),
        "canonical_contract_ok": bool(dig(contract, "verdict", "ok", default=False)),
        "canonical_contract_doc_count_matches_candidate": (
            safe_int(dig(contract, "summary", "rows_count", default=-1), default=-1)
            == candidate_doc_count
        ),
    }


def build_required_postcheck_names() -> list[str]:
    return [
        "promote_report_exists",
        "promote_executed",
        "promote_backup_created",
        "promote_performed",
        "promote_postcheck_match",
        "promoted_doc_count_matches_candidate",
        "canonical_provenance_report_exists",
        "canonical_provenance_error_checks_clean",
        "canonical_contract_report_exists",
        "canonical_contract_ok",
        "canonical_contract_doc_count_matches_candidate",
    ]


def build_markdown(report: Mapping[str, Any]) -> str:
    lines: list[str] = [
        "# Refresh controlled promotion v0.1",
        "",
        f"- Generated at: `{report['generated_at_utc']}`",
        f"- Run ts: `{report['run_ts']}`",
        f"- Mode: `{report['mode']}`",
        "",
        "## Summary",
        "",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Prechecks", ""])
    for key, value in report["prechecks"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Post Execution Checks", ""])
    for key, value in report["post_execution_checks"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Executed Steps", ""])
    if report["executed_steps"]:
        for step in report["executed_steps"]:
            lines.append(f"### {step['name']}")
            lines.append(f"- ok: `{step['ok']}`")
            lines.append(f"- returncode: `{step['returncode']}`")
            lines.append(f"- cmd: `{step['cmd']}`")
            lines.append("")
    else:
        lines.append("- none")

    lines.extend(["", "## Verdict", ""])
    for key, value in report["verdict"].items():
        lines.append(f"- {key}: `{value}`")

    return "\n".join(lines)


def write_reports(
    report: Mapping[str, Any],
    update_dir: Path,
) -> tuple[Path, Path, Path, Path]:
    run_ts = str(report["run_ts"])
    latest_json = update_dir / f"{REPORT_NAME}_latest.json"
    latest_md = update_dir / f"{REPORT_NAME}_latest.md"
    hist_json = update_dir / "history" / f"{REPORT_NAME}_{run_ts}.json"
    hist_md = update_dir / "history" / f"{REPORT_NAME}_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    return latest_json, latest_md, hist_json, hist_md


def build_report(
    *,
    candidate_path: Path | None,
    canonical_dir: Path,
    update_dir: Path,
    validation_dir: Path,
    readiness_report_path: Path,
    execute: bool,
    require_db_smoke: bool,
    runner: StepRunner = run_step,
) -> dict[str, Any]:
    readiness = read_json(readiness_report_path)
    resolved_candidate_path = resolve_candidate_path(
        explicit_candidate_path=candidate_path,
        readiness=readiness,
    )
    latest_path = canonical_dir / "canonical_documents.jsonl"
    candidate_summary = summarize_jsonl(resolved_candidate_path)
    previous_latest_summary = summarize_jsonl(latest_path)
    prechecks = build_prechecks(
        canonical_dir=canonical_dir,
        candidate_path=resolved_candidate_path,
        readiness_path=readiness_report_path,
        readiness=readiness,
    )
    precheck_failed = [
        name for name in build_required_precheck_names() if not prechecks.get(name, False)
    ]

    step_cmds: dict[str, list[str]] = {}
    if resolved_candidate_path is not None:
        step_cmds = build_step_commands(
            candidate_path=resolved_candidate_path,
            canonical_dir=canonical_dir,
            update_dir=update_dir,
            validation_dir=validation_dir,
            require_db_smoke=require_db_smoke,
            execute=execute,
        )

    executed_steps: list[dict[str, Any]] = []
    stopped_early_due_to_failure = False
    post_execution_reports: dict[str, Mapping[str, Any]] = {}
    post_execution_checks: dict[str, bool] = {}
    postcheck_failed: list[str] = []

    if execute and not precheck_failed:
        for step_name in STEP_ORDER:
            result = runner(step_name, step_cmds[step_name])
            executed_steps.append(result)
            if not result["ok"]:
                stopped_early_due_to_failure = True
                break

        if not stopped_early_due_to_failure:
            post_execution_reports = dict(
                load_post_execution_reports(
                    update_dir=update_dir,
                    validation_dir=validation_dir,
                )
            )
            post_execution_checks = build_post_execution_checks(
                reports=post_execution_reports,
                candidate_doc_count=safe_int(candidate_summary.get("doc_count")),
            )
            postcheck_failed = [
                name
                for name in build_required_postcheck_names()
                if not post_execution_checks.get(name, False)
            ]

    execution_failed_steps = [step["name"] for step in executed_steps if not step["ok"]]
    required_failed_checks = [
        *(f"precheck::{name}" for name in precheck_failed),
        *(f"step::{name}" for name in execution_failed_steps),
        *(f"postcheck::{name}" for name in postcheck_failed),
    ]
    controlled_promotion_complete = bool(
        execute and not required_failed_checks and len(executed_steps) == len(STEP_ORDER)
    )

    planned_steps = [
        {
            "name": step_name,
            "cmd": " ".join(step_cmds.get(step_name, [])),
            "will_run": bool(execute and not precheck_failed),
        }
        for step_name in STEP_ORDER
    ]

    return {
        "report_name": REPORT_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": utc_now_ts(),
        "mode": "execute" if execute else "dry_run",
        "status": "controlled_promotion",
        "inputs": {
            "candidate_path": normalize_path(resolved_candidate_path),
            "canonical_dir": normalize_path(canonical_dir),
            "update_dir": normalize_path(update_dir),
            "validation_dir": normalize_path(validation_dir),
            "readiness_report_path": normalize_path(readiness_report_path),
            "require_db_smoke": bool(require_db_smoke),
        },
        "paths": {
            "latest_path": normalize_path(latest_path),
        },
        "readiness_summary": {
            "report_exists": bool(readiness),
            "promotion_ready": readiness_promotion_ready(readiness),
            "candidate_path": readiness_candidate_path(readiness),
            "required_failed_count": safe_int(
                dig(readiness, "verdict", "required_failed_count", default=1),
                default=1,
            ),
            "required_failed_checks": dig(
                readiness,
                "verdict",
                "required_failed_checks",
                default=[],
            ),
        },
        "candidate_summary": candidate_summary,
        "previous_latest_summary": previous_latest_summary,
        "prechecks": prechecks,
        "planned_steps": planned_steps,
        "executed_steps": executed_steps,
        "post_execution_checks": post_execution_checks,
        "execution_summary": {
            "executed": bool(execute),
            "executed_count": len(executed_steps),
            "failed_count": len(execution_failed_steps),
            "failed_step_names": execution_failed_steps,
            "stopped_early_due_to_failure": stopped_early_due_to_failure,
        },
        "summary": {
            "candidate_path": normalize_path(resolved_candidate_path),
            "candidate_doc_count": safe_int(candidate_summary.get("doc_count")),
            "previous_latest_doc_count": safe_int(previous_latest_summary.get("doc_count")),
            "doc_count_delta_after_promotion": (
                safe_int(candidate_summary.get("doc_count"))
                - safe_int(previous_latest_summary.get("doc_count"))
            ),
            "precheck_failed_count": len(precheck_failed),
            "postcheck_failed_count": len(postcheck_failed),
            "controlled_promotion_complete": controlled_promotion_complete,
        },
        "verdict": {
            "ok": not required_failed_checks,
            "safe_to_execute": not precheck_failed,
            "controlled_promotion_complete": controlled_promotion_complete,
            "required_failed_count": len(required_failed_checks),
            "required_failed_checks": required_failed_checks,
            "canonical_latest_mutated": bool(
                controlled_promotion_complete
                or any(step["name"] == "promote_candidate" and step["ok"] for step in executed_steps)
            ),
            "derived_layers_rebuilt": False,
            "postgres_exported": False,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Promote the latest refresh candidate only after the promotion readiness "
            "gate is green, then run canonical-layer post-promotion checks."
        )
    )
    parser.add_argument(
        "--candidate-path",
        type=Path,
        default=None,
        help="Candidate path to promote. Defaults to the latest readiness report candidate.",
    )
    parser.add_argument(
        "--canonical-dir",
        type=Path,
        default=DEFAULT_CANONICAL_DIR,
    )
    parser.add_argument(
        "--update-dir",
        type=Path,
        default=DEFAULT_UPDATE_DIR,
    )
    parser.add_argument(
        "--validation-dir",
        type=Path,
        default=DEFAULT_VALIDATION_DIR,
    )
    parser.add_argument(
        "--readiness-report-path",
        type=Path,
        default=DEFAULT_VALIDATION_DIR / "refresh_promotion_readiness_latest.json",
    )
    parser.add_argument(
        "--require-db-smoke",
        action="store_true",
        help="Forward --require-db-smoke to the readiness gate.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually promote canonical latest. Without this flag this is a dry-run plan.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when prechecks, execution, or postchecks fail.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_report(
        candidate_path=args.candidate_path,
        canonical_dir=args.canonical_dir,
        update_dir=args.update_dir,
        validation_dir=args.validation_dir,
        readiness_report_path=args.readiness_report_path,
        execute=bool(args.execute),
        require_db_smoke=bool(args.require_db_smoke),
    )
    latest_json, latest_md, hist_json, hist_md = write_reports(report, args.update_dir)

    verdict = report["verdict"]
    status = "OK" if verdict["ok"] else "FAILED"
    print(f"[{status}] report={REPORT_NAME}")
    print(f"[{status}] mode={report['mode']}")
    print(f"[{status}] candidate_path={report['summary']['candidate_path']}")
    print(f"[{status}] candidate_doc_count={report['summary']['candidate_doc_count']}")
    print(
        f"[{status}] previous_latest_doc_count="
        f"{report['summary']['previous_latest_doc_count']}"
    )
    print(
        f"[{status}] doc_count_delta_after_promotion="
        f"{report['summary']['doc_count_delta_after_promotion']}"
    )
    print(f"[{status}] safe_to_execute={verdict['safe_to_execute']}")
    print(
        f"[{status}] controlled_promotion_complete="
        f"{verdict['controlled_promotion_complete']}"
    )
    print(f"[{status}] canonical_latest_mutated={verdict['canonical_latest_mutated']}")
    print(f"[{status}] derived_layers_rebuilt={verdict['derived_layers_rebuilt']}")
    print(f"[{status}] postgres_exported={verdict['postgres_exported']}")
    print(f"[{status}] required_failed_count={verdict['required_failed_count']}")
    print(f"[{status}] required_failed_checks={verdict['required_failed_checks']}")
    print(f"[{status}] latest JSON: {latest_json}")
    print(f"[{status}] latest Markdown: {latest_md}")
    print(f"[{status}] history JSON: {hist_json}")
    print(f"[{status}] history Markdown: {hist_md}")

    if args.strict and not verdict["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
