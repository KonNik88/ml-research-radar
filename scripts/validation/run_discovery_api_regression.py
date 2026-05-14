from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


DEFAULT_DOD_FLAGS = [
    "--require-known-issues",
    "--require-artifacts",
    "--require-github-enrichment",
    "--require-huggingface-enrichment",
    "--require-paper-features",
    "--require-similar-papers",
    "--require-discovery-api",
    "--require-topic-clusters",
    "--require-streamlit-discovery-ui",
]


@dataclass(frozen=True)
class Step:
    name: str
    cmd: list[str]
    env: dict[str, str] | None = None


def run_step(step: Step) -> bool:
    print("")
    print("=" * 100)
    print(f"[RUN] {step.name}")
    print("[CMD]", " ".join(step.cmd))
    print("=" * 100)

    env = os.environ.copy()
    if step.env:
        env.update(step.env)

    result = subprocess.run(step.cmd, env=env)

    if result.returncode == 0:
        print(f"[OK] {step.name}")
        return True

    print(f"[FAIL] {step.name} returncode={result.returncode}")
    return False


def python_cmd(module: str, *args: str) -> list[str]:
    return [sys.executable, "-m", module, *args]


def build_steps(args: argparse.Namespace) -> list[Step]:
    file_env = {"ML_RADAR_SEARCH_BACKEND": "file"}

    steps = [
        Step(
            name="pytest_discovery_api",
            cmd=python_cmd("pytest", "tests/integration/test_api_discovery.py", "-q"),
            env=file_env,
        ),
        Step(
            name="check_discovery_api",
            cmd=python_cmd("scripts.validation.check_discovery_api", "--strict"),
            env=file_env,
        ),
        Step(
            name="check_topic_clusters",
            cmd=python_cmd("scripts.validation.check_topic_clusters", "--strict"),
            env=file_env,
        ),
        Step(
            name="check_streamlit_discovery_ui_static",
            cmd=python_cmd(
                "scripts.validation.check_streamlit_discovery_ui",
                "--strict",
            ),
            env=file_env,
        ),
    ]

    if not args.skip_similar_rebuild:
        steps.extend(
            [
                Step(
                    name="rebuild_latest_similar_report",
                    cmd=python_cmd(
                        "scripts.retrieval.find_similar_papers",
                        "--from-latest-detail",
                        "--top-k",
                        str(args.similar_top_k),
                    ),
                    env=file_env,
                ),
                Step(
                    name="check_similar_papers_report",
                    cmd=python_cmd(
                        "scripts.validation.check_similar_papers_report",
                        "--strict",
                    ),
                    env=file_env,
                ),
            ]
        )

    if args.include_live_ui_check:
        steps.append(
            Step(
                name="check_streamlit_discovery_ui_live_api",
                cmd=python_cmd(
                    "scripts.validation.check_streamlit_discovery_ui",
                    "--strict",
                    "--check-api",
                ),
                env=file_env,
            )
        )

    if args.include_db_smoke:
        steps.append(
            Step(
                name="test_db_read",
                cmd=python_cmd("scripts.export.test_db_read"),
            )
        )

    if args.include_dod:
        steps.append(
            Step(
                name="strict_dod_with_discovery_api",
                cmd=python_cmd(
                    "scripts.update.check_refresh_definition_of_done",
                    *DEFAULT_DOD_FLAGS,
                ),
            )
        )

    return steps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Discovery API regression checks."
    )
    parser.add_argument(
        "--skip-similar-rebuild",
        action="store_true",
        help="Skip rebuilding latest similar papers report.",
    )
    parser.add_argument(
        "--similar-top-k",
        type=int,
        default=20,
        help="top_k for scripts.retrieval.find_similar_papers.",
    )
    parser.add_argument(
        "--include-db-smoke",
        action="store_true",
        help="Also run scripts.export.test_db_read. Requires Postgres container.",
    )
    parser.add_argument(
        "--include-dod",
        action="store_true",
        help="Also run strict DoD with --require-discovery-api. Requires fresh DB smoke report.",
    )
    parser.add_argument(
        "--include-live-ui-check",
        action="store_true",
        help=(
            "Also run Streamlit UI validator with --check-api. "
            "Requires a live API at ML_RADAR_API_BASE_URL / localhost."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.similar_top_k < 1:
        raise SystemExit("--similar-top-k must be >= 1")

    steps = build_steps(args)

    failed: list[str] = []
    for step in steps:
        if not run_step(step):
            failed.append(step.name)
            break

    print("")
    print("=" * 100)
    if failed:
        print(f"[FAIL] Discovery API regression failed: {failed}")
        raise SystemExit(1)

    print("[OK] Discovery API regression passed")
    print("=" * 100)


if __name__ == "__main__":
    main()