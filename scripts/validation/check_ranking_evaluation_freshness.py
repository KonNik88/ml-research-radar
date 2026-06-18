from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPORT_PATH = Path(
    "artifacts/reports/evaluation/ranking_evaluation_latest.json"
)
DEFAULT_RETRIEVAL_MANIFEST_PATH = Path(
    "artifacts/retrieval/manifests/latest.json"
)
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")


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


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def runtime_from_report(report: dict[str, Any]) -> dict[str, Any]:
    runtime = report.get("runtime") or {}
    if not isinstance(runtime, dict):
        return {}
    return runtime


def summary_from_report(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") or {}
    if not isinstance(summary, dict):
        return {}
    return summary


def build_freshness_report(
    *,
    evaluation_report: dict[str, Any],
    retrieval_manifest: dict[str, Any],
    report_path: Path,
    retrieval_manifest_path: Path,
) -> dict[str, Any]:
    runtime = runtime_from_report(evaluation_report)
    summary = summary_from_report(evaluation_report)
    decision = evaluation_report.get("decision") or {}

    report_build_id = runtime.get("build_id")
    manifest_build_id = retrieval_manifest.get("build_id")

    report_doc_count = runtime.get("corpus_doc_count")
    manifest_doc_count = retrieval_manifest.get("corpus_doc_count")

    report_model = runtime.get("embedding_model_name")
    manifest_model = retrieval_manifest.get("embedding_model_name")

    checks = {
        "evaluation_schema_version_ok": (
            evaluation_report.get("schema_version")
            == "ranking_evaluation_v1"
        ),
        "evaluation_report_name_ok": (
            evaluation_report.get("report_name")
            == "ranking_evaluation"
        ),
        "retrieval_manifest_build_id_present": bool(manifest_build_id),
        "evaluation_build_id_present": bool(report_build_id),
        "build_id_matches_current_retrieval_manifest": (
            bool(report_build_id)
            and bool(manifest_build_id)
            and report_build_id == manifest_build_id
        ),
        "corpus_doc_count_matches_current_retrieval_manifest": (
            safe_int(report_doc_count, -1)
            == safe_int(manifest_doc_count, -2)
        ),
        "embedding_model_matches_current_retrieval_manifest": (
            bool(report_model)
            and bool(manifest_model)
            and report_model == manifest_model
        ),
        "evaluation_runtime_ready": bool(runtime.get("ready")),
        "evaluation_error_count_zero": (
            safe_int(summary.get("error_count"), -1) == 0
        ),
        "evaluation_determinism_failure_count_zero": (
            safe_int(summary.get("determinism_failure_count"), -1) == 0
        ),
        "evaluation_runs_present": safe_int(summary.get("runs_count")) > 0,
        "decision_present": bool(decision),
        "decision_disallows_public_change": (
            not bool(decision.get("automatic_public_change_allowed"))
        ),
    }

    failed = [
        name for name, value in checks.items() if not value
    ]

    extracted_values = {
        "report_path": normalize_path(report_path),
        "retrieval_manifest_path": normalize_path(retrieval_manifest_path),
        "evaluation_build_id": report_build_id,
        "manifest_build_id": manifest_build_id,
        "evaluation_corpus_doc_count": report_doc_count,
        "manifest_corpus_doc_count": manifest_doc_count,
        "evaluation_embedding_model_name": report_model,
        "manifest_embedding_model_name": manifest_model,
        "evaluation_runs_count": summary.get("runs_count"),
        "evaluation_error_count": summary.get("error_count"),
        "evaluation_determinism_failure_count": summary.get(
            "determinism_failure_count"
        ),
        "recommended_outcome": decision.get("recommended_outcome"),
        "retrieval_corpus_fingerprint": retrieval_manifest.get(
            "corpus_fingerprint"
        ),
    }

    return {
        "schema_version": "ranking_evaluation_freshness_v1",
        "report_name": "check_ranking_evaluation_freshness",
        "generated_at_utc": utc_now_iso(),
        "inputs": {
            "report_path": normalize_path(report_path),
            "retrieval_manifest_path": normalize_path(
                retrieval_manifest_path
            ),
        },
        "extracted_values": extracted_values,
        "checks": checks,
        "required_failed_count": len(failed),
        "required_failed_checks": failed,
        "ok": len(failed) == 0,
    }


def build_markdown(report: dict[str, Any]) -> str:
    extracted = report.get("extracted_values") or {}
    lines: list[str] = []
    lines.append("# Ranking evaluation freshness check")
    lines.append("")
    lines.append(f"- Generated at: `{report.get('generated_at_utc')}`")
    lines.append(f"- OK: **{report.get('ok')}**")
    lines.append(
        f"- Required failed count: "
        f"`{report.get('required_failed_count')}`"
    )
    lines.append("")

    lines.append("## Build identity")
    lines.append("")
    lines.append(
        f"- Evaluation build id: "
        f"`{extracted.get('evaluation_build_id')}`"
    )
    lines.append(
        f"- Current retrieval manifest build id: "
        f"`{extracted.get('manifest_build_id')}`"
    )
    lines.append(
        f"- Evaluation corpus doc count: "
        f"`{extracted.get('evaluation_corpus_doc_count')}`"
    )
    lines.append(
        f"- Current retrieval corpus doc count: "
        f"`{extracted.get('manifest_corpus_doc_count')}`"
    )
    lines.append(
        f"- Evaluation embedding model: "
        f"`{extracted.get('evaluation_embedding_model_name')}`"
    )
    lines.append(
        f"- Current retrieval embedding model: "
        f"`{extracted.get('manifest_embedding_model_name')}`"
    )
    lines.append(
        f"- Retrieval corpus fingerprint: "
        f"`{extracted.get('retrieval_corpus_fingerprint')}`"
    )
    lines.append("")

    lines.append("## Checks")
    lines.append("")
    for name, value in (report.get("checks") or {}).items():
        lines.append(f"- {name}: `{value}`")
    lines.append("")

    if report.get("required_failed_checks"):
        lines.append("## Required failures")
        lines.append("")
        for name in report.get("required_failed_checks") or []:
            lines.append(f"- `{name}`")
        lines.append("")

    lines.append("## Semantics")
    lines.append("")
    lines.append(
        "This check prevents a stale ranking evaluation report from being "
        "accepted after the retrieval artifacts have been rebuilt. It does "
        "not rerun retrieval or ranking; it only compares the accepted "
        "ranking evidence report against the current retrieval manifest."
    )
    lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check that the accepted ranking evaluation report belongs to "
            "the current retrieval build."
        )
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_PATH,
    )
    parser.add_argument(
        "--retrieval-manifest-path",
        type=Path,
        default=DEFAULT_RETRIEVAL_MANIFEST_PATH,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_ts = utc_now_ts()

    evaluation_report = load_json_object(args.report_path)
    retrieval_manifest = load_json_object(args.retrieval_manifest_path)

    report = build_freshness_report(
        evaluation_report=evaluation_report,
        retrieval_manifest=retrieval_manifest,
        report_path=args.report_path,
        retrieval_manifest_path=args.retrieval_manifest_path,
    )

    output_dir = args.output_dir
    latest_json = output_dir / "ranking_evaluation_freshness_latest.json"
    latest_md = output_dir / "ranking_evaluation_freshness_latest.md"
    history_json = (
        output_dir
        / "history"
        / f"ranking_evaluation_freshness_{run_ts}.json"
    )
    history_md = (
        output_dir
        / "history"
        / f"ranking_evaluation_freshness_{run_ts}.md"
    )

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(history_json, report)
    dump_text(history_md, build_markdown(report))

    extracted = report.get("extracted_values") or {}

    print(f"[OK] report_path={args.report_path}")
    print(f"[OK] retrieval_manifest_path={args.retrieval_manifest_path}")
    print(
        "[OK] evaluation_build_id="
        f"{extracted.get('evaluation_build_id')}"
    )
    print(
        "[OK] manifest_build_id="
        f"{extracted.get('manifest_build_id')}"
    )
    print(
        "[OK] recommended_outcome="
        f"{extracted.get('recommended_outcome')}"
    )
    print(f"[OK] required_failed_count={report['required_failed_count']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history Markdown: {history_md}")

    if not report["ok"]:
        print("[FAIL] required_failed_checks:")
        for name in report["required_failed_checks"]:
            print(f"  - {name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
