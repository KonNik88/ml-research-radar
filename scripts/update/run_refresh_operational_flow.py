from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


REPORT_NAME = "run_refresh_operational_flow"
SCHEMA_VERSION = "refresh_operational_orchestration_v0.1"

DEFAULT_CANONICAL_DIR = Path("data/analytics/reconciled")
DEFAULT_UPDATE_DIR = Path("artifacts/reports/update")
DEFAULT_VALIDATION_DIR = Path("artifacts/reports/validation")

PHASE_ORDER = (
    "preflight",
    "candidate",
    "promote",
    "core-derived",
    "postgres",
    "discovery-derived",
)
PUBLIC_PHASES = (*PHASE_ORDER, "full")

MUTATION_NONE = "none"
MUTATION_ALIGNMENT = "alignment-derived"
MUTATION_CANDIDATE = "candidate-derived"
MUTATION_CANONICAL = "canonical-latest"
MUTATION_RETRIEVAL = "retrieval-derived"
MUTATION_POSTGRES = "postgres-derived"
MUTATION_DISCOVERY = "discovery-derived"


@dataclass(frozen=True)
class StepSpec:
    name: str
    phase: str
    command: tuple[str, ...]
    mutation_domain: str = MUTATION_NONE
    description: str = ""


StepRunner = Callable[[StepSpec, int], dict[str, Any]]


def utc_now_ts() -> str:
    # Microseconds keep immutable history paths distinct even when operators run
    # a plan and its follow-up command within the same wall-clock second.
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: Mapping[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def dig(data: Any, *keys: str, default: Any = None) -> Any:
    current = data
    for key in keys:
        if not isinstance(current, Mapping):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def paths_match(left: Path | str | None, right: Path | str | None) -> bool:
    if left is None or right is None:
        return False
    left_path = Path(str(left)).expanduser().resolve(strict=False)
    right_path = Path(str(right)).expanduser().resolve(strict=False)
    return left_path == right_path


def bounded_tail(value: str | None, limit: int) -> str:
    if not value or limit == 0:
        return ""
    return value[-limit:]


def module_command(module: str, *items: str | Path) -> list[str]:
    return [sys.executable, "-m", module, *(str(item) for item in items)]


def append_refresh_inputs(cmd: list[str], args: argparse.Namespace) -> None:
    if args.arxiv_input is not None:
        cmd.extend(["--arxiv-input", str(args.arxiv_input)])
    if args.acl_input is not None:
        cmd.extend(["--acl-input", str(args.acl_input)])
    for merge_report in args.merge_report or []:
        cmd.extend(["--merge-report", merge_report])


def preflight_steps(args: argparse.Namespace) -> list[StepSpec]:
    canonical_path = args.canonical_dir / "canonical_documents.jsonl"
    candidate_path = args.candidate_path or (
        args.canonical_dir / "canonical_documents.candidate_refresh_v1.jsonl"
    )

    alignment_cmd = module_command(
        "scripts.update.build_refresh_alignment_merged_snapshots",
        "--canonical-path",
        canonical_path,
        "--reports-dir",
        args.update_dir.parent,
        "--update-dir",
        args.update_dir,
        "--strict",
    )
    if args.execute:
        alignment_cmd.append("--execute")

    preflight_cmd = module_command(
        "scripts.validation.check_refresh_preflight_contract",
        "--canonical-path",
        canonical_path,
        "--candidate-path",
        candidate_path,
        "--update-dir",
        args.update_dir,
        "--reports-dir",
        args.update_dir,
        "--strict",
        "--require-known-issues",
        "--require-merged-inputs",
        "--require-refresh-cycle-report",
    )
    append_refresh_inputs(preflight_cmd, args)

    return [
        StepSpec(
            name="build_alignment_merged_snapshots",
            phase="preflight",
            command=tuple(alignment_cmd),
            mutation_domain=MUTATION_ALIGNMENT,
            description="Build full merged alignment inputs without touching canonical latest.",
        ),
        StepSpec(
            name="check_refresh_preflight_contract",
            phase="preflight",
            command=tuple(preflight_cmd),
            description="Validate refresh inputs, current derived state, and runbook wiring.",
        ),
    ]


def candidate_steps(args: argparse.Namespace) -> list[StepSpec]:
    canonical_path = args.canonical_dir / "canonical_documents.jsonl"

    rehearsal_cmd = module_command(
        "scripts.update.run_refresh_pipeline_v1",
        "--candidate-rehearsal",
        "--strict",
        "--canonical-dir",
        args.canonical_dir,
        "--update-dir",
        args.update_dir,
        "--validation-dir",
        args.validation_dir,
    )
    if args.candidate_path is not None:
        rehearsal_cmd.extend(["--candidate-path", str(args.candidate_path)])
    append_refresh_inputs(rehearsal_cmd, args)
    if args.execute:
        rehearsal_cmd.append("--execute")

    alignment_coverage_cmd = module_command(
        "scripts.validation.check_refresh_alignment_coverage",
        "--update-dir",
        args.update_dir,
        "--reports-dir",
        args.validation_dir,
    )
    source_coverage_cmd = module_command(
        "scripts.validation.check_refresh_source_coverage",
        "--reports-dir",
        args.validation_dir,
    )
    readiness_cmd = module_command(
        "scripts.validation.check_refresh_promotion_readiness",
        "--canonical-path",
        canonical_path,
        "--update-dir",
        args.update_dir,
        "--validation-dir",
        args.validation_dir,
        "--reports-dir",
        args.validation_dir,
        "--strict",
    )

    if args.candidate_path is not None:
        for cmd in (alignment_coverage_cmd, source_coverage_cmd, readiness_cmd):
            cmd.extend(["--candidate-path", str(args.candidate_path)])
    for merge_report in args.merge_report or []:
        alignment_coverage_cmd.extend(["--merge-report", merge_report])
    if args.require_db_smoke:
        readiness_cmd.append("--require-db-smoke")

    return [
        StepSpec(
            name="run_candidate_rehearsal",
            phase="candidate",
            command=tuple(rehearsal_cmd),
            mutation_domain=MUTATION_CANDIDATE,
            description="Create and validate a timestamped candidate without promotion.",
        ),
        StepSpec(
            name="check_refresh_alignment_coverage",
            phase="candidate",
            command=tuple(alignment_coverage_cmd),
            description="Explain retained alignment coverage and destructive losses.",
        ),
        StepSpec(
            name="check_refresh_source_coverage",
            phase="candidate",
            command=tuple(source_coverage_cmd),
            description="Distinguish destructive source loss from additive enrichment.",
        ),
        StepSpec(
            name="check_refresh_promotion_readiness",
            phase="candidate",
            command=tuple(readiness_cmd),
            description="Produce the strict promotion-ready verdict.",
        ),
    ]


def promote_steps(args: argparse.Namespace) -> list[StepSpec]:
    cmd = module_command(
        "scripts.update.run_refresh_controlled_promotion",
        "--canonical-dir",
        args.canonical_dir,
        "--update-dir",
        args.update_dir,
        "--validation-dir",
        args.validation_dir,
        "--readiness-report-path",
        args.readiness_report_path,
        "--strict",
    )
    if args.candidate_path is not None:
        cmd.extend(["--candidate-path", str(args.candidate_path)])
    if args.require_db_smoke:
        cmd.append("--require-db-smoke")
    if args.execute:
        cmd.append("--execute")

    return [
        StepSpec(
            name=(
                "execute_controlled_promotion"
                if args.execute
                else "dry_run_controlled_promotion"
            ),
            phase="promote",
            command=tuple(cmd),
            mutation_domain=MUTATION_CANONICAL if args.execute else MUTATION_NONE,
            description="Use the controlled promotion wrapper; never promote directly.",
        )
    ]


def core_derived_steps(args: argparse.Namespace) -> list[StepSpec]:
    canonical_path = args.canonical_dir / "canonical_documents.jsonl"
    return [
        StepSpec(
            "build_retrieval_indexes",
            "core-derived",
            tuple(
                module_command(
                    "scripts.retrieval.build_indexes",
                    "--corpus-path",
                    canonical_path,
                )
            ),
            MUTATION_RETRIEVAL,
            "Rebuild lexical and dense retrieval artifacts from canonical latest.",
        ),
        StepSpec(
            "run_retrieval_checks",
            "core-derived",
            tuple(module_command("scripts.validation.run_retrieval_checks")),
            MUTATION_RETRIEVAL,
            "Refresh retrieval validation reports.",
        ),
        StepSpec(
            "run_postpass_audit",
            "core-derived",
            tuple(module_command("scripts.validation.run_postpass_audit")),
            MUTATION_RETRIEVAL,
            "Refresh canonical/source post-pass audit reports.",
        ),
        StepSpec(
            "build_known_issues_snapshot",
            "core-derived",
            tuple(module_command("scripts.validation.build_known_issues_snapshot")),
            MUTATION_RETRIEVAL,
            "Refresh the known-issues snapshot for the new retrieval build.",
        ),
        StepSpec(
            "check_core_definition_of_done",
            "core-derived",
            tuple(
                module_command(
                    "scripts.update.check_refresh_definition_of_done",
                    "--canonical-path",
                    canonical_path,
                    "--require-known-issues",
                    "--strict",
                )
            ),
            MUTATION_NONE,
            "Fail when canonical, manifest, retrieval, audit, or known issues diverge.",
        ),
    ]


def postgres_steps(args: argparse.Namespace) -> list[StepSpec]:
    canonical_path = args.canonical_dir / "canonical_documents.jsonl"
    return [
        StepSpec(
            "postgres_pre_export_smoke",
            "postgres",
            tuple(module_command("scripts.export.test_db_read")),
            MUTATION_NONE,
            "Require an already-running and readable Postgres service.",
        ),
        StepSpec(
            "export_postgres_replace",
            "postgres",
            tuple(
                module_command(
                    "scripts.export.export_postgres_v1",
                    "--canonical-path",
                    canonical_path,
                    "--replace",
                )
            ),
            MUTATION_POSTGRES,
            "Replace only rebuildable paper materialization tables.",
        ),
        StepSpec(
            "postgres_post_export_smoke",
            "postgres",
            tuple(module_command("scripts.export.test_db_read")),
            MUTATION_NONE,
            "Verify the exported Postgres paper state.",
        ),
        StepSpec(
            "check_postgres_definition_of_done",
            "postgres",
            tuple(
                module_command(
                    "scripts.update.check_refresh_definition_of_done",
                    "--canonical-path",
                    canonical_path,
                    "--require-known-issues",
                    "--strict",
                )
            ),
            MUTATION_NONE,
            "Verify canonical/DB parity through the strict DoD gate.",
        ),
    ]


def discovery_derived_steps(args: argparse.Namespace) -> list[StepSpec]:
    canonical_path = args.canonical_dir / "canonical_documents.jsonl"
    final_dod = module_command(
        "scripts.update.check_refresh_definition_of_done",
        "--canonical-path",
        canonical_path,
        "--require-known-issues",
        "--require-paper-features",
        "--require-similar-papers",
        "--require-topic-clusters",
        "--require-topic-projection",
        "--require-discovery-api",
        "--require-streamlit-discovery-ui",
        "--strict",
    )

    raw_steps = [
        (
            "build_paper_features",
            module_command(
                "scripts.features.build_paper_features",
                "--canonical-path",
                canonical_path,
            ),
            MUTATION_DISCOVERY,
        ),
        (
            "check_paper_features",
            module_command(
                "scripts.validation.check_paper_features",
                "--canonical-path",
                canonical_path,
                "--strict",
            ),
            MUTATION_NONE,
        ),
        (
            "check_ranking_profiles",
            module_command("scripts.validation.check_ranking_profiles", "--strict"),
            MUTATION_NONE,
        ),
        (
            "build_ranking_sample",
            module_command(
                "scripts.ranking.demo_radar_ranking",
                "--profile",
                args.ranking_profile,
                "--top-k",
                str(args.ranking_top_k),
            ),
            MUTATION_DISCOVERY,
        ),
        (
            "check_ranking_sample",
            module_command("scripts.validation.check_ranking_report", "--strict"),
            MUTATION_NONE,
        ),
        (
            "build_paper_detail",
            module_command(
                "scripts.details.build_paper_detail",
                "--from-latest-ranking-rank",
                "1",
                "--canonical-path",
                canonical_path,
            ),
            MUTATION_DISCOVERY,
        ),
        (
            "check_paper_detail",
            module_command("scripts.validation.check_paper_detail_report", "--strict"),
            MUTATION_NONE,
        ),
        (
            "build_similar_papers",
            module_command(
                "scripts.retrieval.find_similar_papers",
                "--from-latest-detail",
                "--canonical-path",
                canonical_path,
                "--top-k",
                str(args.similar_top_k),
            ),
            MUTATION_DISCOVERY,
        ),
        (
            "check_similar_papers",
            module_command("scripts.validation.check_similar_papers_report", "--strict"),
            MUTATION_NONE,
        ),
        (
            "build_topic_clusters",
            module_command("scripts.analytics.build_topic_clusters"),
            MUTATION_DISCOVERY,
        ),
        (
            "check_topic_clusters",
            module_command("scripts.validation.check_topic_clusters", "--strict"),
            MUTATION_NONE,
        ),
        (
            "build_topic_projection",
            module_command("scripts.analytics.build_topic_projection"),
            MUTATION_DISCOVERY,
        ),
        (
            "check_topic_projection",
            module_command("scripts.validation.check_topic_projection", "--strict"),
            MUTATION_NONE,
        ),
        (
            "check_discovery_api",
            module_command("scripts.validation.check_discovery_api", "--strict"),
            MUTATION_NONE,
        ),
        (
            "check_streamlit_discovery_ui",
            module_command("scripts.validation.check_streamlit_discovery_ui", "--strict"),
            MUTATION_NONE,
        ),
        (
            "check_discovery_definition_of_done",
            final_dod,
            MUTATION_NONE,
        ),
    ]

    return [
        StepSpec(
            name=name,
            phase="discovery-derived",
            command=tuple(command),
            mutation_domain=mutation_domain,
        )
        for name, command, mutation_domain in raw_steps
    ]


PHASE_BUILDERS: dict[str, Callable[[argparse.Namespace], list[StepSpec]]] = {
    "preflight": preflight_steps,
    "candidate": candidate_steps,
    "promote": promote_steps,
    "core-derived": core_derived_steps,
    "postgres": postgres_steps,
    "discovery-derived": discovery_derived_steps,
}


def build_phase_plan(args: argparse.Namespace) -> list[StepSpec]:
    phases = PHASE_ORDER if args.phase == "full" else (args.phase,)
    steps: list[StepSpec] = []
    for phase in phases:
        steps.extend(PHASE_BUILDERS[phase](args))
    return steps


def run_step(step: StepSpec, stdout_tail_chars: int = 4000) -> dict[str, Any]:
    started_at = utc_now_iso()
    started = time.perf_counter()
    result = subprocess.run(
        list(step.command),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "name": step.name,
        "phase": step.phase,
        "command": list(step.command),
        "cmd": " ".join(step.command),
        "mutation_domain": step.mutation_domain,
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "returncode": result.returncode,
        "stdout_tail": bounded_tail(result.stdout, stdout_tail_chars),
        "stderr_tail": bounded_tail(result.stderr, stdout_tail_chars),
        "ok": result.returncode == 0,
    }


def promotion_dry_run_prechecks(args: argparse.Namespace) -> list[dict[str, Any]]:
    dry_run_path = args.update_dir / "run_refresh_controlled_promotion_latest.json"
    dry_run = load_json_if_exists(dry_run_path)
    readiness = load_json_if_exists(args.readiness_report_path)

    expected_candidate = args.candidate_path or dig(
        readiness,
        "summary",
        "candidate_path",
        default=dig(readiness, "inputs", "candidate_path"),
    )
    dry_run_candidate = dig(dry_run, "summary", "candidate_path")
    candidate_path = Path(str(expected_candidate)) if expected_candidate else None

    dry_run_mtime = dry_run_path.stat().st_mtime if dry_run_path.exists() else None
    readiness_mtime = (
        args.readiness_report_path.stat().st_mtime
        if args.readiness_report_path.exists()
        else None
    )
    candidate_mtime = (
        candidate_path.stat().st_mtime
        if candidate_path is not None and candidate_path.exists()
        else None
    )

    return [
        {
            "name": "controlled_promotion_dry_run_report_exists",
            "ok": bool(dry_run),
            "details": normalize_path(dry_run_path),
        },
        {
            "name": "controlled_promotion_dry_run_mode",
            "ok": dry_run.get("mode") == "dry_run",
            "details": dry_run.get("mode"),
        },
        {
            "name": "controlled_promotion_dry_run_safe",
            "ok": bool(
                dig(dry_run, "verdict", "ok", default=False)
                and dig(dry_run, "verdict", "safe_to_execute", default=False)
                and not dig(
                    dry_run,
                    "verdict",
                    "controlled_promotion_complete",
                    default=True,
                )
                and not dig(
                    dry_run,
                    "verdict",
                    "canonical_latest_mutated",
                    default=True,
                )
            ),
            "details": dig(dry_run, "verdict", default={}),
        },
        {
            "name": "controlled_promotion_candidate_matches_readiness",
            "ok": paths_match(dry_run_candidate, expected_candidate),
            "details": {
                "dry_run_candidate": normalize_path(dry_run_candidate),
                "expected_candidate": normalize_path(expected_candidate),
            },
        },
        {
            "name": "controlled_promotion_dry_run_not_older_than_readiness",
            "ok": bool(
                dry_run_mtime is not None
                and readiness_mtime is not None
                and dry_run_mtime >= readiness_mtime
            ),
            "details": None,
        },
        {
            "name": "controlled_promotion_dry_run_not_older_than_candidate",
            "ok": bool(
                dry_run_mtime is not None
                and candidate_mtime is not None
                and dry_run_mtime >= candidate_mtime
            ),
            "details": None,
        },
    ]


def execution_prechecks(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.phase == "full" and args.execute:
        return [
            {
                "name": "full_execute_blocked_in_v0_1",
                "ok": False,
                "details": (
                    "Run preflight, candidate, promote dry-run, promote --execute, "
                    "core-derived, postgres, and discovery-derived as separate commands."
                ),
            }
        ]
    if args.phase == "promote" and args.execute:
        return promotion_dry_run_prechecks(args)
    return []


def should_run_plan(args: argparse.Namespace) -> bool:
    if args.phase == "full":
        return False
    if args.phase == "promote":
        return True
    return bool(args.execute)


def build_markdown(report: Mapping[str, Any]) -> str:
    verdict = report["verdict"]
    summary = report["execution_summary"]
    lines = [
        "# Refresh Operational Orchestration v0.1",
        "",
        f"- Generated at: `{report['generated_at_utc']}`",
        f"- Phase: `{report['phase']}`",
        f"- Mode: `{report['mode']}`",
        f"- Execute requested: `{report['execute']}`",
        "",
        "## Execution prechecks",
        "",
    ]
    if report["execution_prechecks"]:
        for item in report["execution_prechecks"]:
            lines.append(f"- {item['name']}: `{item['ok']}`")
    else:
        lines.append("- none")

    lines.extend(["", "## Planned steps", ""])
    for step in report["planned_steps"]:
        lines.extend(
            [
                f"### {step['name']}",
                f"- phase: `{step['phase']}`",
                f"- will_run: `{step['will_run']}`",
                f"- mutation_domain: `{step['mutation_domain']}`",
                f"- command: `{step['cmd']}`",
                "",
            ]
        )

    lines.extend(["## Executed steps", ""])
    if report["executed_steps"]:
        for step in report["executed_steps"]:
            lines.extend(
                [
                    f"### {step['name']}",
                    f"- ok: `{step['ok']}`",
                    f"- returncode: `{step['returncode']}`",
                    f"- duration_seconds: `{step['duration_seconds']}`",
                    "",
                ]
            )
    else:
        lines.extend(["- none", ""])

    lines.extend(
        [
            "## Execution summary",
            "",
            f"- executed_count: `{summary['executed_count']}`",
            f"- skipped_count: `{summary['skipped_count']}`",
            f"- failed_count: `{summary['failed_count']}`",
            f"- failed_step_names: `{summary['failed_step_names']}`",
            f"- stopped_early_due_to_failure: `{summary['stopped_early_due_to_failure']}`",
            "",
            "## Verdict",
            "",
            f"- ok: `{verdict['ok']}`",
            f"- phase_complete: `{verdict['phase_complete']}`",
            f"- required_failed_count: `{verdict['required_failed_count']}`",
            f"- required_failed_checks: `{verdict['required_failed_checks']}`",
            f"- canonical_latest_mutated: `{verdict['canonical_latest_mutated']}`",
            f"- postgres_exported: `{verdict['postgres_exported']}`",
            f"- derived_layers_rebuilt: `{verdict['derived_layers_rebuilt']}`",
            "",
        ]
    )
    return "\n".join(lines)


def build_report(
    args: argparse.Namespace,
    *,
    runner: StepRunner = run_step,
) -> dict[str, Any]:
    run_ts = utc_now_ts()
    steps = build_phase_plan(args)
    prechecks = execution_prechecks(args)
    failed_prechecks = [item["name"] for item in prechecks if not item["ok"]]
    run_requested = should_run_plan(args)
    will_run = bool(run_requested and not failed_prechecks)

    planned_steps = [
        {
            "name": step.name,
            "phase": step.phase,
            "command": list(step.command),
            "cmd": " ".join(step.command),
            "mutation_domain": step.mutation_domain,
            "description": step.description,
            "will_run": will_run,
        }
        for step in steps
    ]

    executed_steps: list[dict[str, Any]] = []
    stopped_early = False
    if will_run:
        for step in steps:
            result = runner(step, args.stdout_tail_chars)
            executed_steps.append(result)
            if not result.get("ok", False):
                stopped_early = True
                break

    failed_steps = [
        str(step.get("name"))
        for step in executed_steps
        if not step.get("ok", False)
    ]
    required_failed_checks = [
        *(f"precheck::{name}" for name in failed_prechecks),
        *(f"step::{name}" for name in failed_steps),
    ]
    phase_complete = bool(
        will_run
        and not required_failed_checks
        and len(executed_steps) == len(steps)
    )

    controlled_report = load_json_if_exists(
        args.update_dir / "run_refresh_controlled_promotion_latest.json"
    )
    canonical_latest_mutated = bool(
        args.phase == "promote"
        and args.execute
        and dig(
            controlled_report,
            "verdict",
            "canonical_latest_mutated",
            default=False,
        )
    )
    postgres_exported = any(
        step.get("name") == "export_postgres_replace" and step.get("ok")
        for step in executed_steps
    )
    derived_layers_rebuilt = bool(
        phase_complete and args.phase in {"core-derived", "discovery-derived"}
    )

    mode = (
        "execute"
        if args.execute
        else "promotion_dry_run"
        if args.phase == "promote"
        else "plan"
    )
    report = {
        "report_name": REPORT_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "phase": args.phase,
        "mode": mode,
        "execute": bool(args.execute),
        "inputs": {
            "candidate_path": normalize_path(args.candidate_path),
            "canonical_dir": normalize_path(args.canonical_dir),
            "update_dir": normalize_path(args.update_dir),
            "validation_dir": normalize_path(args.validation_dir),
            "readiness_report_path": normalize_path(args.readiness_report_path),
            "arxiv_input": normalize_path(args.arxiv_input),
            "acl_input": normalize_path(args.acl_input),
            "merge_reports": list(args.merge_report or []),
            "require_db_smoke": bool(args.require_db_smoke),
            "ranking_profile": args.ranking_profile,
            "ranking_top_k": args.ranking_top_k,
            "similar_top_k": args.similar_top_k,
        },
        "mutation_policy": {
            "canonical_mutation_allowed": bool(
                args.phase == "promote" and args.execute
            ),
            "postgres_mutation_allowed": bool(
                args.phase == "postgres" and args.execute
            ),
            "derived_mutation_allowed": bool(
                args.execute
                and args.phase
                in {
                    "preflight",
                    "candidate",
                    "core-derived",
                    "discovery-derived",
                }
            ),
            "full_execute_allowed": False,
        },
        "execution_prechecks": prechecks,
        "planned_steps": planned_steps,
        "executed_steps": executed_steps,
        "execution_summary": {
            "run_requested": run_requested,
            "executed_count": len(executed_steps),
            "skipped_count": max(len(steps) - len(executed_steps), 0),
            "failed_count": len(failed_steps),
            "failed_step_names": failed_steps,
            "stopped_early_due_to_failure": stopped_early,
        },
        "verdict": {
            "ok": not required_failed_checks,
            "phase_complete": phase_complete,
            "plan_only": mode == "plan",
            "required_failed_count": len(required_failed_checks),
            "required_failed_checks": required_failed_checks,
            "canonical_latest_mutated": canonical_latest_mutated,
            "postgres_exported": postgres_exported,
            "derived_layers_rebuilt": derived_layers_rebuilt,
        },
    }
    return report


def write_reports(
    report: Mapping[str, Any],
    reports_dir: Path,
) -> tuple[Path, Path, Path, Path]:
    run_ts = str(report["run_ts"])
    latest_json = reports_dir / f"{REPORT_NAME}_latest.json"
    latest_md = reports_dir / f"{REPORT_NAME}_latest.md"
    history_json = reports_dir / "history" / f"{REPORT_NAME}_{run_ts}.json"
    history_md = reports_dir / "history" / f"{REPORT_NAME}_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(history_json, report)
    dump_text(history_md, build_markdown(report))
    return latest_json, latest_md, history_json, history_md


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Recommended phase-based operational entrypoint for the safe ML Research "
            "Radar refresh runbook. The legacy run_refresh_pipeline_v1 remains a "
            "lower-level candidate-rehearsal runner."
        )
    )
    parser.add_argument("--phase", choices=PUBLIC_PHASES, required=True)
    parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Execute the selected phase. Without this flag, phases are plan-only, "
            "except promote, which runs the controlled non-mutating promotion dry-run."
        ),
    )
    parser.add_argument("--candidate-path", type=Path, default=None)
    parser.add_argument("--canonical-dir", type=Path, default=DEFAULT_CANONICAL_DIR)
    parser.add_argument("--update-dir", type=Path, default=DEFAULT_UPDATE_DIR)
    parser.add_argument("--validation-dir", type=Path, default=DEFAULT_VALIDATION_DIR)
    parser.add_argument(
        "--readiness-report-path",
        type=Path,
        default=None,
        help=(
            "Promotion-readiness JSON. Defaults to "
            "<validation-dir>/refresh_promotion_readiness_latest.json."
        ),
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=None,
        help="Orchestration report directory. Defaults to --update-dir.",
    )
    parser.add_argument("--arxiv-input", type=Path, default=None)
    parser.add_argument("--acl-input", type=Path, default=None)
    parser.add_argument(
        "--merge-report",
        action="append",
        default=None,
        help="source_name=path/to/merge_report.json; may be repeated.",
    )
    parser.add_argument("--require-db-smoke", action="store_true")
    parser.add_argument("--ranking-profile", default="huggingface_ready")
    parser.add_argument("--ranking-top-k", type=int, default=5)
    parser.add_argument("--similar-top-k", type=int, default=20)
    parser.add_argument("--stdout-tail-chars", type=int, default=4000)
    return parser


def normalize_args(args: argparse.Namespace) -> argparse.Namespace:
    if args.readiness_report_path is None:
        args.readiness_report_path = (
            args.validation_dir / "refresh_promotion_readiness_latest.json"
        )
    if args.reports_dir is None:
        args.reports_dir = args.update_dir
    if args.ranking_top_k < 1:
        raise SystemExit("--ranking-top-k must be >= 1")
    if args.similar_top_k < 1:
        raise SystemExit("--similar-top-k must be >= 1")
    if args.stdout_tail_chars < 0:
        raise SystemExit("--stdout-tail-chars must be >= 0")
    return args


def main(argv: Sequence[str] | None = None) -> None:
    args = normalize_args(build_parser().parse_args(argv))
    report = build_report(args)
    paths = write_reports(report, args.reports_dir)

    verdict = report["verdict"]
    status = "OK" if verdict["ok"] else "FAILED"
    print(f"[{status}] report={REPORT_NAME}")
    print(f"[{status}] phase={report['phase']}")
    print(f"[{status}] mode={report['mode']}")
    print(f"[{status}] phase_complete={verdict['phase_complete']}")
    print(f"[{status}] required_failed_count={verdict['required_failed_count']}")
    print(f"[{status}] required_failed_checks={verdict['required_failed_checks']}")
    print(f"[{status}] latest JSON: {paths[0]}")
    print(f"[{status}] latest Markdown: {paths[1]}")
    print(f"[{status}] history JSON: {paths[2]}")
    print(f"[{status}] history Markdown: {paths[3]}")

    if not verdict["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
