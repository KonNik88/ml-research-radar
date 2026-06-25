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
    "--require-topic-projection",
    "--require-streamlit-discovery-ui",
    "--require-golden-queries",
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


def dod_flags_for_args(args: argparse.Namespace) -> list[str]:
    flags = list(DEFAULT_DOD_FLAGS)

    if args.include_artifact_api_filters:
        # Keep the normal DoD behavior unchanged unless the caller explicitly
        # asks the regression runner to generate the Artifact API filters report.
        # In that case, the DoD step should require the freshly generated report.
        flags.insert(2, "--require-artifact-api-filters")

    return flags


def build_steps(args: argparse.Namespace) -> list[Step]:
    file_env = {"ML_RADAR_SEARCH_BACKEND": "file"}
    db_env = {"ML_RADAR_SEARCH_BACKEND": "db"}

    steps = [
        Step(
            name="check_golden_queries",
            cmd=python_cmd("scripts.validation.check_golden_queries", "--strict"),
            env=file_env,
        ),
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
            name="check_topic_projection",
            cmd=python_cmd("scripts.validation.check_topic_projection", "--strict"),
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

    if args.include_qdrant_benchmark:
        steps.extend(
            [
                Step(
                    name="run_qdrant_retrieval_benchmark",
                    cmd=python_cmd("scripts.evaluation.run_qdrant_retrieval_benchmark"),
                    env=file_env,
                ),
                Step(
                    name="check_qdrant_retrieval_benchmark",
                    cmd=python_cmd(
                        "scripts.validation.check_qdrant_retrieval_benchmark",
                        "--strict",
                    ),
                    env=file_env,
                ),
            ]
        )

    if args.include_qdrant_serving_poc:
        steps.extend(
            [
                Step(
                    name="check_qdrant_collection",
                    cmd=python_cmd(
                        "scripts.validation.check_qdrant_collection",
                        "--strict",
                    ),
                    env=file_env,
                ),
                Step(
                    name="compare_qdrant_file_dense",
                    cmd=python_cmd("scripts.evaluation.compare_qdrant_file_dense"),
                    env=file_env,
                ),
                Step(
                    name="check_qdrant_file_dense_comparison",
                    cmd=python_cmd(
                        "scripts.validation.check_qdrant_file_dense_comparison",
                        "--strict",
                    ),
                    env=file_env,
                ),
            ]
        )

    if args.include_qdrant_profile_sweep:
        steps.extend(
            [
                Step(
                    name="run_qdrant_search_profile_sweep",
                    cmd=python_cmd(
                        "scripts.evaluation.run_qdrant_search_profile_sweep"
                    ),
                    env=file_env,
                ),
                Step(
                    name="check_qdrant_search_profile_sweep",
                    cmd=python_cmd(
                        "scripts.validation.check_qdrant_search_profile_sweep",
                        "--strict",
                    ),
                    env=file_env,
                ),
            ]
        )

    if args.include_qdrant_serving_performance:
        steps.extend(
            [
                Step(
                    name="run_qdrant_serving_performance",
                    cmd=python_cmd(
                        "scripts.evaluation.run_qdrant_serving_performance",
                        "--preset",
                        "full",
                    ),
                    env=file_env,
                ),
                Step(
                    name="check_qdrant_serving_performance",
                    cmd=python_cmd(
                        "scripts.validation.check_qdrant_serving_performance",
                        "--strict",
                    ),
                    env=file_env,
                ),
            ]
        )

    if args.include_qdrant_api:
        steps.append(
            Step(
                name="check_qdrant_api_experimental",
                cmd=python_cmd(
                    "scripts.validation.check_qdrant_api_experimental",
                    "--strict",
                ),
                env=file_env,
            )
        )

    if args.include_qdrant_hybrid_evaluation:
        steps.extend(
            [
                Step(
                    name=(
                        "run_qdrant_hybrid_evaluation"
                    ),
                    cmd=python_cmd(
                        (
                            "scripts.evaluation."
                            "run_qdrant_hybrid_evaluation"
                        ),
                    ),
                    env=file_env,
                ),
                Step(
                    name=(
                        "check_qdrant_hybrid_evaluation"
                    ),
                    cmd=python_cmd(
                        (
                            "scripts.validation."
                            "check_qdrant_hybrid_evaluation"
                        ),
                        "--strict",
                    ),
                    env=file_env,
                ),
            ]
        )

    if args.include_retrieval_eval:
        steps.extend(
            [
                Step(
                    name="run_retrieval_eval",
                    cmd=python_cmd("scripts.evaluation.run_retrieval_eval"),
                    env=file_env,
                ),
                Step(
                    name="check_retrieval_eval",
                    cmd=python_cmd(
                        "scripts.validation.check_retrieval_eval",
                        "--strict",
                    ),
                    env=file_env,
                ),
            ]
        )

    if args.include_search_quality_experiments:
        steps.extend(
            [
                Step(
                    name="run_search_quality_experiments",
                    cmd=python_cmd(
                        "scripts.evaluation.run_search_quality_experiments",
                    ),
                    env=file_env,
                ),
                Step(
                    name="check_search_quality_experiments",
                    cmd=python_cmd(
                        "scripts.validation.check_search_quality_experiments",
                        "--strict",
                    ),
                    env=file_env,
                ),
            ]
        )

    if args.include_controlled_search_quality_experiments:
        steps.extend(
            [
                Step(
                    name="run_search_quality_controlled_experiments",
                    cmd=python_cmd(
                        "scripts.evaluation.run_search_quality_controlled_experiments",
                    ),
                    env=file_env,
                ),
                Step(
                    name="check_search_quality_controlled_experiments",
                    cmd=python_cmd(
                        "scripts.validation.check_search_quality_controlled_experiments",
                        "--strict",
                    ),
                    env=file_env,
                ),
            ]
        )

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

    if args.include_artifact_api_filters:
        steps.append(
            Step(
                name="check_artifact_api_filters",
                cmd=python_cmd(
                    "scripts.validation.check_artifact_api_filters",
                    "--strict",
                ),
                env=db_env,
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
                    *dod_flags_for_args(args),
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
        "--include-retrieval-eval",
        action="store_true",
        help=(
            "Also run retrieval evaluation v1 and strict retrieval eval quality check. "
            "Uses file backend and does not require a live API server."
        ),
    )
    parser.add_argument(
        "--include-search-quality-experiments",
        action="store_true",
        help=(
            "Also run search quality experiments v1 and strict quality check. "
            "This analyzes retrieval_eval_latest.json; use together with "
            "--include-retrieval-eval when you want a fresh retrieval eval report."
        ),
    )
    parser.add_argument(
        "--include-controlled-search-quality-experiments",
        action="store_true",
        help=(
            "Also run controlled search quality experiments v1 and strict quality check. "
            "This runs evaluation-only hybrid weight / candidate_k / rank experiments "
            "over the file backend and does not modify API defaults."
        ),
    )
    parser.add_argument(
        "--include-qdrant-benchmark",
        action="store_true",
        help=(
            "Also run Qdrant retrieval benchmark and strict benchmark validator. "
            "Requires Qdrant container and current dense retrieval artifacts. "
            "This is evaluation-only and does not change API defaults."
        ),
    )
    parser.add_argument(
        "--include-qdrant-serving-poc",
        action="store_true",
        help=(
            "Also run lightweight Qdrant serving POC checks over an existing "
            "Qdrant collection: collection validator, file-dense comparison, "
            "and strict comparison validator. Requires Qdrant container and a "
            "previously built collection, but does not recreate or upload vectors."
        ),
    )
    parser.add_argument(
        "--include-qdrant-profile-sweep",
        action="store_true",
        help=(
            "Also run the full Qdrant search-profile sweep and strict validator "
            "over all enabled golden queries. This compares default, ef_128, "
            "ef_256, ef_512, and exact profiles against the exact file-dense "
            "reference. It is evaluation-only, requires an existing Qdrant "
            "collection, and does not change API defaults."
        ),
    )
    parser.add_argument(
        "--include-qdrant-serving-performance",
        action="store_true",
        help=(
            "Also run the full read-only Qdrant serving-performance benchmark "
            "and strict evidence validator. This measures backend-only and API "
            "serving latency, concurrency, resource usage, and result parity "
            "over all enabled golden queries. It requires an existing compatible "
            "Qdrant collection, does not recreate or upload vectors, does not "
            "change public search defaults, and does not promote Qdrant."
        ),
    )
    parser.add_argument(
        "--include-qdrant-api",
        action="store_true",
        help=(
            "Also validate the experimental Qdrant API endpoint "
            "GET /experimental/search/qdrant. Requires file backend runtime, "
            "Qdrant container, and an existing benchmark collection. This does "
            "not change /search defaults or SearchRuntime backend selection."
        ),
    )
    parser.add_argument(
        "--include-qdrant-hybrid-evaluation",
        action="store_true",
        help=(
            "Run the controlled file-vs-Qdrant "
            "hybrid evaluation and its strict validator."
        ),
    )
    parser.add_argument(
        "--include-artifact-api-filters",
        action="store_true",
        help=(
            "Also run the DB-backed Artifact API filters validator. "
            "This uses ML_RADAR_SEARCH_BACKEND=db, generates "
            "artifact_api_filters_check_latest.json, does not call external "
            "artifact providers, and does not mutate canonical/retrieval data. "
            "When used together with --include-dod, the DoD step also gets "
            "--require-artifact-api-filters."
        ),
    )
    parser.add_argument(
        "--include-db-smoke",
        action="store_true",
        help="Also run scripts.export.test_db_read. Requires Postgres container.",
    )
    parser.add_argument(
        "--include-dod",
        action="store_true",
        help=("Also run strict DoD with the current regression-runner required gates. " "Requires fresh validation reports for the selected gates."),
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