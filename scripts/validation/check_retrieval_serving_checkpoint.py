from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "retrieval_serving_checkpoint_v1"

DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")

DEFAULT_RANKING_CONFIG_PATH = Path("configs/ranking_evaluation_v1.yaml")
DEFAULT_RANKING_REPORT_PATH = Path(
    "artifacts/reports/evaluation/ranking_evaluation_latest.json"
)
DEFAULT_RETRIEVAL_MANIFEST_PATH = Path(
    "artifacts/retrieval/manifests/latest.json"
)

DEFAULT_QDRANT_HYBRID_CONFIG_PATH = Path(
    "configs/qdrant_hybrid_evaluation_v1.yaml"
)
DEFAULT_QDRANT_HYBRID_REPORT_PATH = Path(
    "artifacts/reports/evaluation/qdrant_hybrid_evaluation_latest.json"
)

DEFAULT_QDRANT_SERVING_PERFORMANCE_REPORT_PATH = Path(
    "artifacts/reports/evaluation/qdrant_serving_performance_latest.json"
)
DEFAULT_QDRANT_COLLECTION_CONFIG_PATH = Path("configs/qdrant_benchmark_v1.yaml")

DEFAULT_API_SMOKE_TESTS = [
    "tests/integration/test_api_smoke.py",
    "tests/integration/test_api_errors.py",
    "tests/integration/test_api_reload.py",
]


@dataclass(frozen=True)
class Step:
    name: str
    cmd: list[str]
    required: bool = True
    env: dict[str, str] | None = None
    evidence_path: Path | None = None
    description: str = ""


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def python_cmd(module: str, *args: str | Path) -> list[str]:
    return [sys.executable, "-m", module, *[str(arg) for arg in args]]


def tail_text(text: str, *, max_chars: int = 6000) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def load_json_if_exists(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def summarize_evidence(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Extract a compact, schema-tolerant evidence summary."""

    if payload is None:
        return {
            "evidence_loaded": False,
        }

    verdict = _mapping(payload.get("verdict"))
    summary = _mapping(payload.get("summary"))
    extracted = _mapping(payload.get("extracted_values"))

    required_failed_count = payload.get("required_failed_count")
    if required_failed_count is None:
        required_failed_count = verdict.get("required_failed_count")

    ok = payload.get("ok")
    if ok is None:
        ok = verdict.get("ok")

    return {
        "evidence_loaded": True,
        "schema_version": payload.get("schema_version"),
        "report_name": payload.get("report_name"),
        "ok": ok,
        "required_failed_count": required_failed_count,
        "required_failed_checks": (
            payload.get("required_failed_checks")
            or verdict.get("required_failed_checks")
            or []
        ),
        "build_id": (
            extracted.get("evaluation_build_id")
            or extracted.get("manifest_build_id")
            or summary.get("build_id")
        ),
        "corpus_doc_count": (
            extracted.get("evaluation_corpus_doc_count")
            or extracted.get("manifest_corpus_doc_count")
            or summary.get("corpus_doc_count")
        ),
        "recommended_outcome": extracted.get("recommended_outcome"),
        "collection_name": summary.get("collection_name"),
        "profile_name": summary.get("profile_name"),
        "input_schema_version": summary.get("input_schema_version"),
    }


def run_step(step: Step) -> dict[str, Any]:
    env = os.environ.copy()
    if step.env:
        env.update(step.env)

    started = datetime.now(timezone.utc)
    completed = None

    result = subprocess.run(
        step.cmd,
        env=env,
        text=True,
        capture_output=True,
    )
    completed = datetime.now(timezone.utc)

    evidence = load_json_if_exists(step.evidence_path)

    status = "passed" if result.returncode == 0 else "failed"
    if not step.required and result.returncode != 0:
        status = "optional_failed"

    return {
        "name": step.name,
        "description": step.description,
        "required": step.required,
        "status": status,
        "returncode": result.returncode,
        "cmd": step.cmd,
        "env_overrides": step.env or {},
        "started_at_utc": started.isoformat(),
        "completed_at_utc": completed.isoformat(),
        "stdout_tail": tail_text(result.stdout),
        "stderr_tail": tail_text(result.stderr),
        "evidence_path": normalize_path(step.evidence_path),
        "evidence": summarize_evidence(evidence),
    }


def build_steps(args: argparse.Namespace) -> list[Step]:
    file_env = {"ML_RADAR_SEARCH_BACKEND": "file"}
    output_dir = Path(args.output_dir)

    steps: list[Step] = [
        Step(
            name="ranking_evidence_regression",
            cmd=python_cmd(
                "scripts.validation.check_ranking_evidence_regression",
                "--config-path",
                args.ranking_config_path,
                "--report-path",
                args.ranking_report_path,
                "--retrieval-manifest-path",
                args.retrieval_manifest_path,
                "--output-dir",
                output_dir,
            ),
            required=True,
            env=file_env,
            evidence_path=output_dir / "ranking_evidence_regression_latest.json",
            description=(
                "Strict integrity + freshness + regression-policy gate for the "
                "accepted ranking evaluation evidence."
            ),
        ),
    ]

    if not args.skip_qdrant_hybrid_evidence:
        steps.append(
            Step(
                name="qdrant_hybrid_evidence",
                cmd=python_cmd(
                    "scripts.validation.check_qdrant_hybrid_evaluation",
                    "--config-path",
                    args.qdrant_hybrid_config_path,
                    "--report-path",
                    args.qdrant_hybrid_report_path,
                    "--output-dir",
                    output_dir,
                    "--strict",
                ),
                required=True,
                env=file_env,
                evidence_path=(
                    output_dir / "qdrant_hybrid_evaluation_quality_latest.json"
                ),
                description=(
                    "Strict accepted-report validation for the controlled "
                    "file-vs-Qdrant hybrid evaluation."
                ),
            )
        )

    if args.include_serving_performance_evidence or args.require_serving_performance_evidence:
        steps.append(
            Step(
                name="qdrant_serving_performance_evidence",
                cmd=python_cmd(
                    "scripts.validation.check_qdrant_serving_performance",
                    "--report-path",
                    args.qdrant_serving_performance_report_path,
                    "--output-dir",
                    output_dir,
                    "--strict",
                ),
                required=bool(args.require_serving_performance_evidence),
                env=file_env,
                evidence_path=(
                    output_dir / "qdrant_serving_performance_quality_latest.json"
                ),
                description=(
                    "Strict validation of the existing Qdrant serving-performance "
                    "evidence report. This does not rerun the heavy benchmark."
                ),
            )
        )

    if args.include_qdrant_collection_live or args.require_qdrant_collection_live:
        steps.append(
            Step(
                name="qdrant_collection_live",
                cmd=python_cmd(
                    "scripts.validation.check_qdrant_collection",
                    "--config-path",
                    args.qdrant_collection_config_path,
                    "--output-dir",
                    output_dir,
                    "--strict",
                ),
                required=bool(args.require_qdrant_collection_live),
                env=file_env,
                evidence_path=output_dir / "qdrant_collection_quality_latest.json",
                description=(
                    "Live read-only Qdrant collection compatibility check. "
                    "This requires a running Qdrant container."
                ),
            )
        )

    if args.include_api_smoke:
        steps.append(
            Step(
                name="api_runtime_smoke",
                cmd=python_cmd("pytest", *args.api_smoke_tests, "-q"),
                required=True,
                env=file_env,
                evidence_path=None,
                description=(
                    "FastAPI/TestClient smoke coverage for /health, /runtime, "
                    "/search, error mapping, reload, and Qdrant failure visibility."
                ),
            )
        )

    return steps


def build_report(args: argparse.Namespace, step_results: list[dict[str, Any]]) -> dict[str, Any]:
    required_steps = [row for row in step_results if row["required"]]
    failed_required_steps = [
        row["name"]
        for row in required_steps
        if row["returncode"] != 0
    ]

    optional_failed_steps = [
        row["name"]
        for row in step_results
        if not row["required"] and row["returncode"] != 0
    ]

    checks = {
        "ranking_evidence_regression_passed": any(
            row["name"] == "ranking_evidence_regression"
            and row["returncode"] == 0
            for row in step_results
        ),
        "qdrant_hybrid_evidence_passed_or_skipped": (
            args.skip_qdrant_hybrid_evidence
            or any(
                row["name"] == "qdrant_hybrid_evidence"
                and row["returncode"] == 0
                for row in step_results
            )
        ),
        "required_steps_passed": not failed_required_steps,
        "public_search_behavior_changed": False,
        "qdrant_required_for_health": False,
        "fallback_allowed": False,
        "file_dense_reference_preserved": True,
        "heavy_benchmarks_rerun_by_default": False,
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "report_name": "check_retrieval_serving_checkpoint",
        "generated_at_utc": utc_now_iso(),
        "inputs": {
            "ranking_config_path": normalize_path(args.ranking_config_path),
            "ranking_report_path": normalize_path(args.ranking_report_path),
            "retrieval_manifest_path": normalize_path(args.retrieval_manifest_path),
            "qdrant_hybrid_config_path": normalize_path(args.qdrant_hybrid_config_path),
            "qdrant_hybrid_report_path": normalize_path(args.qdrant_hybrid_report_path),
            "qdrant_serving_performance_report_path": normalize_path(
                args.qdrant_serving_performance_report_path
            ),
            "qdrant_collection_config_path": normalize_path(
                args.qdrant_collection_config_path
            ),
        },
        "policy": {
            "public_search_behavior_change_allowed": False,
            "public_qdrant_promotion_allowed": False,
            "fallback_allowed": False,
            "qdrant_required_for_health": False,
            "rerun_heavy_benchmarks_by_default": False,
            "ranking_recommendation_expected": "reject_heuristic_reranking",
        },
        "options": {
            "skip_qdrant_hybrid_evidence": bool(args.skip_qdrant_hybrid_evidence),
            "include_serving_performance_evidence": bool(
                args.include_serving_performance_evidence
            ),
            "require_serving_performance_evidence": bool(
                args.require_serving_performance_evidence
            ),
            "include_qdrant_collection_live": bool(args.include_qdrant_collection_live),
            "require_qdrant_collection_live": bool(args.require_qdrant_collection_live),
            "include_api_smoke": bool(args.include_api_smoke),
        },
        "checks": checks,
        "steps": step_results,
        "required_failed_count": len(failed_required_steps),
        "required_failed_steps": failed_required_steps,
        "optional_failed_steps": optional_failed_steps,
        "ok": not failed_required_steps,
    }

    return report


def build_markdown(report: Mapping[str, Any]) -> str:
    lines: list[str] = []

    lines.append("# Retrieval Serving Checkpoint")
    lines.append("")
    lines.append(f"- schema_version: `{report.get('schema_version')}`")
    lines.append(f"- generated_at_utc: `{report.get('generated_at_utc')}`")
    lines.append(f"- ok: **{report.get('ok')}**")
    lines.append(
        f"- required_failed_count: `{report.get('required_failed_count')}`"
    )
    lines.append("")

    lines.append("## Policy")
    lines.append("")
    for name, value in _mapping(report.get("policy")).items():
        lines.append(f"- {name}: `{value}`")
    lines.append("")

    lines.append("## Checks")
    lines.append("")
    for name, value in _mapping(report.get("checks")).items():
        icon = "✅" if value is True else "❌"
        lines.append(f"- {icon} `{name}` = `{value}`")
    lines.append("")

    lines.append("## Steps")
    lines.append("")
    for row in report.get("steps") or []:
        evidence = _mapping(row.get("evidence"))
        status_icon = "✅" if row.get("returncode") == 0 else "❌"
        required = "required" if row.get("required") else "optional"
        lines.append(
            f"### {status_icon} `{row.get('name')}` ({required})"
        )
        lines.append("")
        if row.get("description"):
            lines.append(str(row.get("description")))
            lines.append("")
        lines.append(f"- returncode: `{row.get('returncode')}`")
        lines.append(f"- evidence_path: `{row.get('evidence_path')}`")
        lines.append(f"- evidence_schema: `{evidence.get('schema_version')}`")
        lines.append(f"- evidence_ok: `{evidence.get('ok')}`")
        lines.append(
            f"- evidence_required_failed_count: "
            f"`{evidence.get('required_failed_count')}`"
        )
        if evidence.get("recommended_outcome") is not None:
            lines.append(
                f"- recommended_outcome: `{evidence.get('recommended_outcome')}`"
            )
        if evidence.get("build_id") is not None:
            lines.append(f"- build_id: `{evidence.get('build_id')}`")
        if evidence.get("collection_name") is not None:
            lines.append(f"- collection_name: `{evidence.get('collection_name')}`")
        if row.get("returncode") != 0:
            stdout_tail = str(row.get("stdout_tail") or "").strip()
            stderr_tail = str(row.get("stderr_tail") or "").strip()
            if stdout_tail:
                lines.append("")
                lines.append("```text")
                lines.append(stdout_tail)
                lines.append("```")
            if stderr_tail:
                lines.append("")
                lines.append("```text")
                lines.append(stderr_tail)
                lines.append("```")
        lines.append("")

    failed = report.get("required_failed_steps") or []
    if failed:
        lines.append("## Required failures")
        lines.append("")
        for name in failed:
            lines.append(f"- `{name}`")
        lines.append("")

    lines.append("## Semantics")
    lines.append("")
    lines.append(
        "This wrapper is a lightweight retrieval-serving checkpoint gate. "
        "It validates already accepted evidence and optional live checks. "
        "It does not rerun heavy benchmark/evaluation jobs by default, does "
        "not promote Qdrant, does not change public /search behavior, and "
        "does not introduce fallback."
    )
    lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a lightweight retrieval-serving checkpoint over accepted "
            "ranking/Qdrant/search evidence. This command composes existing "
            "validators and does not rerun heavy benchmark jobs by default."
        )
    )

    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)

    parser.add_argument(
        "--ranking-config-path",
        type=Path,
        default=DEFAULT_RANKING_CONFIG_PATH,
    )
    parser.add_argument(
        "--ranking-report-path",
        type=Path,
        default=DEFAULT_RANKING_REPORT_PATH,
    )
    parser.add_argument(
        "--retrieval-manifest-path",
        type=Path,
        default=DEFAULT_RETRIEVAL_MANIFEST_PATH,
    )

    parser.add_argument(
        "--qdrant-hybrid-config-path",
        type=Path,
        default=DEFAULT_QDRANT_HYBRID_CONFIG_PATH,
    )
    parser.add_argument(
        "--qdrant-hybrid-report-path",
        type=Path,
        default=DEFAULT_QDRANT_HYBRID_REPORT_PATH,
    )
    parser.add_argument(
        "--skip-qdrant-hybrid-evidence",
        action="store_true",
        help=(
            "Skip the accepted Qdrant hybrid evidence check. Intended only "
            "for partial local debugging, not for milestone validation."
        ),
    )

    parser.add_argument(
        "--qdrant-serving-performance-report-path",
        type=Path,
        default=DEFAULT_QDRANT_SERVING_PERFORMANCE_REPORT_PATH,
    )
    parser.add_argument(
        "--include-serving-performance-evidence",
        action="store_true",
        help=(
            "Validate the existing Qdrant serving-performance report if present. "
            "This does not rerun the heavy benchmark."
        ),
    )
    parser.add_argument(
        "--require-serving-performance-evidence",
        action="store_true",
        help=(
            "Validate the existing Qdrant serving-performance report and fail "
            "the checkpoint if it fails."
        ),
    )

    parser.add_argument(
        "--qdrant-collection-config-path",
        type=Path,
        default=DEFAULT_QDRANT_COLLECTION_CONFIG_PATH,
    )
    parser.add_argument(
        "--include-qdrant-collection-live",
        action="store_true",
        help=(
            "Run the live read-only Qdrant collection validator. Requires a "
            "running Qdrant container."
        ),
    )
    parser.add_argument(
        "--require-qdrant-collection-live",
        action="store_true",
        help=(
            "Run the live read-only Qdrant collection validator and fail the "
            "checkpoint if it fails."
        ),
    )

    parser.add_argument(
        "--include-api-smoke",
        action="store_true",
        help=(
            "Run API/TestClient smoke tests for runtime/search/error/reload "
            "semantics. This can be slower because it loads the API runtime."
        ),
    )
    parser.add_argument(
        "--api-smoke-tests",
        nargs="*",
        default=DEFAULT_API_SMOKE_TESTS,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the composed steps without executing them.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    run_ts = utc_now_ts()

    steps = build_steps(args)

    if args.dry_run:
        print("[DRY-RUN] retrieval serving checkpoint steps:")
        for step in steps:
            required = "required" if step.required else "optional"
            print(f"- {step.name} ({required}): {' '.join(step.cmd)}")
        return

    results = []
    for step in steps:
        print("")
        print("=" * 100)
        print(f"[RUN] {step.name}")
        print("[CMD]", " ".join(step.cmd))
        print("=" * 100)

        result = run_step(step)
        results.append(result)

        if result["returncode"] == 0:
            print(f"[OK] {step.name}")
        else:
            print(
                f"[FAIL] {step.name} returncode={result['returncode']} "
                f"required={step.required}"
            )
            if step.required:
                break

    report = build_report(args, results)
    report["run_ts"] = run_ts

    output_dir = Path(args.output_dir)
    latest_json = output_dir / "retrieval_serving_checkpoint_latest.json"
    latest_md = output_dir / "retrieval_serving_checkpoint_latest.md"
    history_json = (
        output_dir / "history" / f"retrieval_serving_checkpoint_{run_ts}.json"
    )
    history_md = (
        output_dir / "history" / f"retrieval_serving_checkpoint_{run_ts}.md"
    )

    markdown = build_markdown(report)

    dump_json(latest_json, report)
    dump_text(latest_md, markdown)
    dump_json(history_json, report)
    dump_text(history_md, markdown)

    print("")
    print("=" * 100)
    print(f"[OK] schema_version={SCHEMA_VERSION}")
    print(f"[OK] required_failed_count={report['required_failed_count']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history Markdown: {history_md}")

    if not report["ok"]:
        print("[FAIL] required_failed_steps:")
        for name in report["required_failed_steps"]:
            print(f"  - {name}")
        raise SystemExit(1)

    print("[OK] Retrieval serving checkpoint passed")
    print("=" * 100)


if __name__ == "__main__":
    main()
