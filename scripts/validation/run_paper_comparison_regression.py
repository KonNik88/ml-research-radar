from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = "paper_comparison_regression_runner_v1"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_REPORTS_DIR = Path("artifacts/reports/validation")

TARGET_TEST_PATHS = [
    "tests/smoke/test_paper_comparison.py",
    "tests/integration/test_api_discovery.py",
    "tests/smoke/test_citation_graph_fixture_store.py",
    "tests/integration/test_api_citation_graph_failure_isolation.py",
    "tests/integration/test_api_citation_graph_references.py",
    "tests/smoke/test_comparison_ui_client.py",
    "tests/smoke/test_comparison_ui.py",
    "tests/smoke/test_streamlit_discovery_ui.py",
    "tests/smoke/test_workspace_ui_client.py",
    "tests/smoke/test_paper_comparison_live_smoke.py",
    "tests/smoke/test_paper_comparison_regression.py",
]


@dataclass(frozen=True)
class Step:
    name: str
    cmd: list[str]
    env: dict[str, str] | None = None


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def python_cmd(module: str, *args: str) -> list[str]:
    return [sys.executable, "-m", module, *args]


def build_steps(args: argparse.Namespace) -> list[Step]:
    file_env = {"ML_RADAR_SEARCH_BACKEND": "file"}
    steps = [
        Step(
            name="pytest_paper_comparison_regression",
            cmd=python_cmd("pytest", *TARGET_TEST_PATHS, "-q"),
            env=file_env,
        ),
        Step(
            name="check_streamlit_discovery_ui",
            cmd=python_cmd(
                "scripts.validation.check_streamlit_discovery_ui",
                "--strict",
            ),
            env=file_env,
        ),
    ]

    if args.include_live_smoke:
        steps.append(
            Step(
                name="check_paper_comparison_live_smoke",
                cmd=python_cmd(
                    "scripts.validation.check_paper_comparison_live_smoke",
                    "--strict",
                    "--base-url",
                    str(args.base_url),
                    "--reports-dir",
                    str(args.reports_dir),
                ),
                env=file_env,
            )
        )

    return steps


def step_result(
    *,
    step: Step,
    returncode: int,
    duration_sec: float,
) -> dict[str, Any]:
    return {
        "name": step.name,
        "cmd": step.cmd,
        "env": step.env or {},
        "returncode": int(returncode),
        "ok": returncode == 0,
        "duration_sec": round(duration_sec, 3),
    }


def run_step(step: Step) -> dict[str, Any]:
    print("")
    print("=" * 100)
    print(f"[RUN] {step.name}")
    print("[CMD]", " ".join(step.cmd))
    print("=" * 100)

    env = os.environ.copy()
    if step.env:
        env.update(step.env)

    started_at = time.perf_counter()
    completed = subprocess.run(step.cmd, env=env)
    duration_sec = time.perf_counter() - started_at

    if completed.returncode == 0:
        print(f"[OK] {step.name}")
    else:
        print(f"[FAIL] {step.name} returncode={completed.returncode}")

    return step_result(
        step=step,
        returncode=completed.returncode,
        duration_sec=duration_sec,
    )


def args_to_report_inputs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "base_url": str(args.base_url),
        "include_live_smoke": bool(args.include_live_smoke),
        "reports_dir": normalize_path(args.reports_dir),
        "backend_mode": "file",
        "workspace_postgres_required": False,
        "qdrant_required": False,
    }


def build_report(
    *,
    args: argparse.Namespace,
    run_ts: str,
    started_at: float,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    failed_steps = [step["name"] for step in steps if not step["ok"]]
    ok = not failed_steps
    live_step_present = any(
        step["name"] == "check_paper_comparison_live_smoke"
        for step in steps
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "inputs": args_to_report_inputs(args),
        "summary": {
            "ok": ok,
            "steps_count": len(steps),
            "failed_steps_count": len(failed_steps),
            "duration_sec": round(time.perf_counter() - started_at, 3),
            "target_test_files_count": len(TARGET_TEST_PATHS),
        },
        "steps": steps,
        "verdict": {
            "ok": ok,
            "failed_steps": failed_steps,
            "stopped_after_first_failure": bool(failed_steps),
            "targeted_regression_complete": (
                ok and any(
                    step["name"] == "pytest_paper_comparison_regression"
                    for step in steps
                )
            ),
            "streamlit_static_gate_complete": (
                ok and any(
                    step["name"] == "check_streamlit_discovery_ui"
                    for step in steps
                )
            ),
            "live_smoke_requested": bool(args.include_live_smoke),
            "live_smoke_complete": (
                ok and bool(args.include_live_smoke) and live_step_present
            ),
            "canonical_truth_mutated": False,
            "workspace_postgres_required": False,
            "qdrant_required": False,
        },
    }


def build_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Paper Comparison regression runner",
        "",
        f"- schema_version: `{report['schema_version']}`",
        f"- generated_at_utc: `{report['generated_at_utc']}`",
        f"- run_ts: `{report['run_ts']}`",
        "",
        "## Summary",
        "",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Inputs", ""])
    for key, value in report["inputs"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(
        [
            "",
            "## Steps",
            "",
            "| # | step | ok | returncode | duration_sec | env | command |",
            "|---:|---|---:|---:|---:|---|---|",
        ]
    )
    for index, step in enumerate(report["steps"], start=1):
        command = " ".join(step["cmd"])
        env = ", ".join(
            f"{key}={value}" for key, value in step.get("env", {}).items()
        )
        lines.append(
            "| "
            f"{index} | `{step['name']}` | `{step['ok']}` | "
            f"`{step['returncode']}` | `{step['duration_sec']}` | "
            f"`{env}` | `{command}` |"
        )

    lines.extend(["", "## Verdict", ""])
    for key, value in report["verdict"].items():
        lines.append(f"- {key}: `{value}`")

    return "\n".join(lines) + "\n"


def write_report(
    report: dict[str, Any],
    *,
    reports_dir: Path,
) -> dict[str, str]:
    run_ts = str(report["run_ts"])
    latest_json = reports_dir / "paper_comparison_regression_latest.json"
    latest_md = reports_dir / "paper_comparison_regression_latest.md"
    history_json = (
        reports_dir
        / "history"
        / f"paper_comparison_regression_{run_ts}.json"
    )
    history_md = (
        reports_dir
        / "history"
        / f"paper_comparison_regression_{run_ts}.md"
    )

    markdown = build_markdown(report)
    dump_json(latest_json, report)
    dump_text(latest_md, markdown)
    dump_json(history_json, report)
    dump_text(history_md, markdown)

    return {
        "latest_json": normalize_path(latest_json),
        "latest_markdown": normalize_path(latest_md),
        "history_json": normalize_path(history_json),
        "history_markdown": normalize_path(history_md),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the bounded Paper Comparison v0.1 regression matrix and, "
            "optionally, the live HTTP merge gate."
        )
    )
    parser.add_argument(
        "--include-live-smoke",
        action="store_true",
        help=(
            "Also run the live Paper Comparison HTTP smoke. Requires an "
            "already running API at --base-url."
        ),
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    run_ts = utc_now_ts()
    started_at = time.perf_counter()
    step_results: list[dict[str, Any]] = []

    for step in build_steps(args):
        result = run_step(step)
        step_results.append(result)
        if not result["ok"]:
            break

    report = build_report(
        args=args,
        run_ts=run_ts,
        started_at=started_at,
        steps=step_results,
    )
    report_paths = write_report(
        report,
        reports_dir=Path(args.reports_dir),
    )

    print("")
    print("=" * 100)
    print(
        json.dumps(
            report["summary"],
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    for key, value in report_paths.items():
        print(f"[report] {key}: {value}")

    if not report["verdict"]["ok"]:
        print(f"[FAIL] failed_steps={report['verdict']['failed_steps']}")
        print("=" * 100)
        raise SystemExit(1)

    print("[OK] Paper Comparison regression passed")
    print("=" * 100)


if __name__ == "__main__":
    main()
