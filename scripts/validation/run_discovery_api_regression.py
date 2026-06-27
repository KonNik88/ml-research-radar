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

DB_PREFLIGHT_REQUIRED_TABLES = [
    "canonical_documents",
    "artifact_entities",
    "paper_artifact_links",
]

DEFAULT_REPORTS_DIR = Path("artifacts/reports/validation")
REPORT_SCHEMA_VERSION = "discovery_api_regression_runner_report_v1"


@dataclass(frozen=True)
class Step:
    name: str
    cmd: list[str]
    env: dict[str, str] | None = None


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def normalize_path(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def step_result(
    *,
    name: str,
    cmd: list[str] | None,
    env: dict[str, str] | None,
    returncode: int,
    duration_sec: float,
    kind: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "kind": kind,
        "cmd": cmd,
        "env": env or {},
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
    result = subprocess.run(step.cmd, env=env)
    duration_sec = time.perf_counter() - started_at

    if result.returncode == 0:
        print(f"[OK] {step.name}")
    else:
        print(f"[FAIL] {step.name} returncode={result.returncode}")

    return step_result(
        name=step.name,
        cmd=step.cmd,
        env=step.env,
        returncode=result.returncode,
        duration_sec=duration_sec,
        kind="subprocess",
    )


def python_cmd(module: str, *args: str) -> list[str]:
    return [sys.executable, "-m", module, *args]


def needs_db_preflight(args: argparse.Namespace) -> bool:
    return bool(args.include_artifact_api_filters or args.include_db_smoke)


def _restore_env_var(name: str, previous_value: str | None) -> None:
    if previous_value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = previous_value


def run_db_preflight() -> bool:
    print("")
    print("=" * 100)
    print("[RUN] db_runtime_preflight")
    print("[INFO] DB-backed regression steps require Postgres and ML_RADAR_SEARCH_BACKEND=db.")
    print("=" * 100)

    previous_backend = os.environ.get("ML_RADAR_SEARCH_BACKEND")
    os.environ["ML_RADAR_SEARCH_BACKEND"] = "db"

    try:
        from services.api.db import PostgresConfig, PostgresDocumentStore
        from services.api.settings import get_settings

        get_settings.cache_clear()
        settings = get_settings()

        print(f"[OK] configured_backend_mode={settings.search_backend}")
        print(f"[OK] postgres_host={settings.postgres_host}")
        print(f"[OK] postgres_port={settings.postgres_port}")
        print(f"[OK] postgres_dbname={settings.postgres_dbname}")
        print(f"[OK] postgres_user={settings.postgres_user}")

        if settings.search_backend != "db":
            print(
                "[FAIL] db_preflight_backend_mode=False: "
                f"expected db, got {settings.search_backend!r}"
            )
            return False

        store = PostgresDocumentStore(
            PostgresConfig(
                host=settings.postgres_host,
                port=settings.postgres_port,
                dbname=settings.postgres_dbname,
                user=settings.postgres_user,
                password=settings.postgres_password,
            )
        )

        if not store.ping():
            print("[FAIL] db_preflight_ping=False")
            return False

        print("[OK] db_preflight_ping=True")

        with store.connection() as conn, conn.cursor() as cur:
            for table_name in DB_PREFLIGHT_REQUIRED_TABLES:
                cur.execute("SELECT to_regclass(%s) AS table_ref", (table_name,))
                row = cur.fetchone()
                table_ref = row.get("table_ref") if row else None
                if table_ref is None:
                    print(f"[FAIL] db_preflight_table_exists_{table_name}=False")
                    return False

                cur.execute(f"SELECT COUNT(*) AS total FROM {table_name}")
                count_row = cur.fetchone()
                row_count = int(count_row["total"]) if count_row else 0

                if row_count <= 0:
                    print(f"[FAIL] db_preflight_table_non_empty_{table_name}=False")
                    return False

                print(f"[OK] db_preflight_table_exists_{table_name}=True")
                print(f"[OK] db_preflight_table_rows_{table_name}={row_count}")

        print("[OK] db_runtime_preflight passed")
        return True

    except Exception as exc:  # noqa: BLE001 - preflight must print actionable diagnostics.
        print(f"[FAIL] db_runtime_preflight failed: {type(exc).__name__}: {exc}")
        print(
            "[INFO] Recommended action: start the Postgres container and rerun with "
            "DB-backed checks enabled, for example `docker compose -f "
            "infra/docker/docker-compose.yml up -d postgres` and "
            "`set ML_RADAR_SEARCH_BACKEND=db`."
        )
        return False

    finally:
        try:
            from services.api.settings import get_settings

            get_settings.cache_clear()
        except Exception:
            pass
        _restore_env_var("ML_RADAR_SEARCH_BACKEND", previous_backend)


def run_db_preflight_step() -> dict[str, Any]:
    started_at = time.perf_counter()
    ok = run_db_preflight()
    duration_sec = time.perf_counter() - started_at

    return step_result(
        name="db_runtime_preflight",
        cmd=None,
        env={"ML_RADAR_SEARCH_BACKEND": "db"},
        returncode=0 if ok else 1,
        duration_sec=duration_sec,
        kind="preflight",
    )


def args_to_report_inputs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        key: value
        for key, value in sorted(vars(args).items())
        if isinstance(value, (str, int, float, bool, type(None)))
    }


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Discovery API regression runner report")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Schema version: `{report['schema_version']}`")
    lines.append("")

    lines.append("## Summary")
    for key, value in report["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Inputs")
    for key, value in report["inputs"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Steps")
    lines.append("")
    lines.append("| # | step | kind | ok | returncode | duration_sec | env | command |")
    lines.append("|---:|---|---|---:|---:|---:|---|---|")
    for index, step in enumerate(report["steps"], start=1):
        command = " ".join(step["cmd"]) if step.get("cmd") else ""
        env = ", ".join(f"{key}={value}" for key, value in step.get("env", {}).items())
        lines.append(
            "| "
            f"{index} | `{step['name']}` | `{step['kind']}` | "
            f"`{step['ok']}` | `{step['returncode']}` | "
            f"`{step['duration_sec']}` | `{env}` | `{command}` |"
        )
    lines.append("")

    lines.append("## Verdict")
    for key, value in report["verdict"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    return "\n".join(lines)


def build_report(
    *,
    args: argparse.Namespace,
    run_ts: str,
    started_at: float,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    failed_steps = [step["name"] for step in steps if not step["ok"]]
    ok = len(failed_steps) == 0

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "inputs": args_to_report_inputs(args),
        "summary": {
            "ok": ok,
            "steps_count": len(steps),
            "failed_steps_count": len(failed_steps),
            "duration_sec": round(time.perf_counter() - started_at, 3),
        },
        "steps": steps,
        "verdict": {
            "ok": ok,
            "failed_steps": failed_steps,
            "stopped_after_first_failure": bool(failed_steps),
        },
    }


def write_report(
    report: dict[str, Any],
    *,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
) -> dict[str, str]:
    run_ts = str(report["run_ts"])

    latest_json = reports_dir / "discovery_api_regression_runner_latest.json"
    latest_md = reports_dir / "discovery_api_regression_runner_latest.md"
    history_json = (
        reports_dir
        / "history"
        / f"discovery_api_regression_runner_{run_ts}.json"
    )
    history_md = (
        reports_dir
        / "history"
        / f"discovery_api_regression_runner_{run_ts}.md"
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


def print_report_paths(paths: dict[str, str]) -> None:
    print(f"[OK] latest JSON: {paths['latest_json']}")
    print(f"[OK] latest Markdown: {paths['latest_markdown']}")
    print(f"[OK] history JSON: {paths['history_json']}")
    print(f"[OK] history Markdown: {paths['history_markdown']}")


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
    run_ts = utc_now_ts()
    started_at = time.perf_counter()
    args = build_parser().parse_args(argv)

    if args.similar_top_k < 1:
        raise SystemExit("--similar-top-k must be >= 1")

    step_results: list[dict[str, Any]] = []

    if needs_db_preflight(args):
        preflight_result = run_db_preflight_step()
        step_results.append(preflight_result)

        if not preflight_result["ok"]:
            report = build_report(
                args=args,
                run_ts=run_ts,
                started_at=started_at,
                steps=step_results,
            )
            report_paths = write_report(report)

            print("")
            print("=" * 100)
            print("[FAIL] Discovery API regression DB preflight failed")
            print_report_paths(report_paths)
            print("=" * 100)
            raise SystemExit(1)

    steps = build_steps(args)

    for step in steps:
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
    report_paths = write_report(report)
    failed = report["verdict"]["failed_steps"]

    print("")
    print("=" * 100)
    if failed:
        print(f"[FAIL] Discovery API regression failed: {failed}")
        print_report_paths(report_paths)
        print("=" * 100)
        raise SystemExit(1)

    print("[OK] Discovery API regression passed")
    print_report_paths(report_paths)
    print("=" * 100)


if __name__ == "__main__":
    main()