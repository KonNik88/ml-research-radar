from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_MANIFEST_PATH = Path("artifacts/retrieval/manifests/latest.json")
DEFAULT_RETRIEVAL_CHECKS_PATH = Path("artifacts/reports/validation/retrieval_checks_latest.json")
DEFAULT_POSTPASS_AUDIT_PATH = Path("artifacts/reports/validation/postpass_audit_summary_latest.json")
DEFAULT_KNOWN_ISSUES_PATH = Path("artifacts/reports/validation/known_issues_snapshot_latest.json")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/update")


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


def dig(data: Any, *keys: str, default: Any = None) -> Any:
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def first_present(data: dict[str, Any], paths: list[tuple[str, ...]], default: Any = None) -> Any:
    for path in paths:
        val = dig(data, *path, default=None)
        if val is not None:
            return val
    return default


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


def run_db_smoke() -> dict[str, Any]:
    cmd = [sys.executable, "-m", "scripts.export.test_db_read"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    stdout = result.stdout or ""
    stderr = result.stderr or ""

    ping_match = re.search(r"Ping:\s*(True|False)", stdout)
    total_docs_match = re.search(r"Total docs:\s*(\d+)", stdout)

    return {
        "cmd": " ".join(cmd),
        "returncode": result.returncode,
        "ping": (ping_match.group(1) == "True") if ping_match else None,
        "total_docs": int(total_docs_match.group(1)) if total_docs_match else None,
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
        "ok": result.returncode == 0 and (ping_match is not None),
    }


def extract_postpass_values(postpass_audit: dict[str, Any]) -> dict[str, Any]:
    total_docs = first_present(
        postpass_audit,
        [
            ("total_docs",),
            ("summary", "total_docs"),
            ("corpus_summary", "total_docs"),
            ("audit_summary", "total_docs"),
        ],
    )

    merge_stats = first_present(
        postpass_audit,
        [
            ("merge_stats",),
            ("summary", "merge_stats"),
            ("corpus_summary", "merge_stats"),
            ("audit_summary", "merge_stats"),
        ],
        default={},
    ) or {}

    multi_source_docs = None
    if isinstance(merge_stats, dict):
        multi_source_docs = first_present(
            merge_stats,
            [
                ("multi_source_docs",),
                ("source_count_gt1_docs",),
            ],
        )

    return {
        "total_docs": total_docs,
        "merge_stats": merge_stats,
        "multi_source_docs": multi_source_docs,
    }


def extract_known_issues_values(known_issues: dict[str, Any] | None) -> dict[str, Any]:
    if known_issues is None:
        return {
            "canonical_corpus_doc_count": None,
            "retrieval_build_id": None,
        }

    canonical_corpus_doc_count = first_present(
        known_issues,
        [
            ("canonical_corpus_doc_count",),
            ("summary", "canonical_corpus_doc_count"),
            ("current_state", "canonical_corpus_doc_count"),
            ("snapshot", "canonical_corpus_doc_count"),
        ],
    )

    retrieval_build_id = first_present(
        known_issues,
        [
            ("retrieval_build_id",),
            ("summary", "retrieval_build_id"),
            ("current_state", "retrieval_build_id"),
            ("snapshot", "retrieval_build_id"),
        ],
    )

    return {
        "canonical_corpus_doc_count": canonical_corpus_doc_count,
        "retrieval_build_id": retrieval_build_id,
    }


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Refresh Definition of Done check")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append("")

    lines.append("## Inputs")
    for k, v in report["inputs"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    lines.append("## Canonical summary")
    for k, v in report["canonical_summary"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    lines.append("## Extracted values")
    for k, v in report["extracted_values"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    lines.append("## Checks")
    for k, v in report["checks"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    lines.append("## Verdict")
    for k, v in report["verdict"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    if report.get("db_smoke"):
        lines.append("## DB smoke")
        db = report["db_smoke"]
        for k in ("cmd", "returncode", "ping", "total_docs", "ok"):
            lines.append(f"- {k}: `{db.get(k)}`")
        lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check refresh Definition of Done against canonical, DB, retrieval, and validation outputs."
    )
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--retrieval-checks-path", type=Path, default=DEFAULT_RETRIEVAL_CHECKS_PATH)
    parser.add_argument("--postpass-audit-path", type=Path, default=DEFAULT_POSTPASS_AUDIT_PATH)
    parser.add_argument("--known-issues-path", type=Path, default=DEFAULT_KNOWN_ISSUES_PATH)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument(
        "--require-known-issues",
        action="store_true",
        help="Treat known_issues_snapshot presence and consistency as a required DoD condition.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    canonical_summary = summarize_canonical(args.canonical_path)

    manifest = load_json(args.manifest_path)
    retrieval_checks = load_json(args.retrieval_checks_path)
    postpass_audit = load_json(args.postpass_audit_path)

    known_issues = None
    known_issues_exists = args.known_issues_path.exists()
    if known_issues_exists:
        known_issues = load_json(args.known_issues_path)

    db_smoke = run_db_smoke()

    manifest_doc_count = manifest.get("corpus_doc_count")
    manifest_build_id = manifest.get("build_id")

    retrieval_checks_doc_count = retrieval_checks.get("corpus_doc_count")
    retrieval_checks_build_id = retrieval_checks.get("build_id")

    postpass_values = extract_postpass_values(postpass_audit)
    postpass_total_docs = postpass_values["total_docs"]
    postpass_multisource_docs = postpass_values["multi_source_docs"]

    known_issues_values = extract_known_issues_values(known_issues)
    known_issues_doc_count = known_issues_values["canonical_corpus_doc_count"]
    known_issues_build_id = known_issues_values["retrieval_build_id"]

    checks = {
        "canonical_exists": args.canonical_path.exists(),
        "manifest_exists": args.manifest_path.exists(),
        "retrieval_checks_exists": args.retrieval_checks_path.exists(),
        "postpass_audit_exists": args.postpass_audit_path.exists(),
        "db_smoke_ok": db_smoke["ok"],
        "db_ping_true": db_smoke["ping"] is True,
        "canonical_vs_manifest_doc_count_match": canonical_summary["doc_count"] == manifest_doc_count,
        "canonical_vs_retrieval_checks_doc_count_match": canonical_summary["doc_count"] == retrieval_checks_doc_count,
        "canonical_vs_postpass_doc_count_match": canonical_summary["doc_count"] == postpass_total_docs,
        "canonical_vs_postpass_multisource_match": canonical_summary["multisource_docs"] == postpass_multisource_docs,
        "manifest_vs_retrieval_checks_build_id_match": manifest_build_id == retrieval_checks_build_id,
        "canonical_vs_db_doc_count_match": canonical_summary["doc_count"] == db_smoke["total_docs"],
        "known_issues_exists": known_issues_exists,
        "canonical_vs_known_issues_doc_count_match": (
            (known_issues_doc_count == canonical_summary["doc_count"]) if known_issues is not None else False
        ),
        "manifest_vs_known_issues_build_id_match": (
            (known_issues_build_id == manifest_build_id) if known_issues is not None else False
        ),
    }

    required_check_names = [
        "canonical_exists",
        "manifest_exists",
        "retrieval_checks_exists",
        "postpass_audit_exists",
        "db_smoke_ok",
        "db_ping_true",
        "canonical_vs_manifest_doc_count_match",
        "canonical_vs_retrieval_checks_doc_count_match",
        "canonical_vs_postpass_doc_count_match",
        "canonical_vs_postpass_multisource_match",
        "manifest_vs_retrieval_checks_build_id_match",
        "canonical_vs_db_doc_count_match",
    ]

    if args.require_known_issues:
        required_check_names.extend(
            [
                "known_issues_exists",
                "canonical_vs_known_issues_doc_count_match",
                "manifest_vs_known_issues_build_id_match",
            ]
        )

    required_failed = [name for name in required_check_names if not checks.get(name, False)]

    verdict = {
        "required_check_count": len(required_check_names),
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
        "dod_passed": len(required_failed) == 0,
        "known_issues_required": bool(args.require_known_issues),
    }

    report = {
        "report_name": "check_refresh_definition_of_done",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "inputs": {
            "canonical_path": normalize_path(args.canonical_path),
            "manifest_path": normalize_path(args.manifest_path),
            "retrieval_checks_path": normalize_path(args.retrieval_checks_path),
            "postpass_audit_path": normalize_path(args.postpass_audit_path),
            "known_issues_path": normalize_path(args.known_issues_path),
        },
        "canonical_summary": canonical_summary,
        "extracted_values": {
            "manifest_doc_count": manifest_doc_count,
            "manifest_build_id": manifest_build_id,
            "retrieval_checks_doc_count": retrieval_checks_doc_count,
            "retrieval_checks_build_id": retrieval_checks_build_id,
            "postpass_total_docs": postpass_total_docs,
            "postpass_multisource_docs": postpass_multisource_docs,
            "db_total_docs": db_smoke["total_docs"],
            "known_issues_doc_count": known_issues_doc_count,
            "known_issues_build_id": known_issues_build_id,
        },
        "checks": checks,
        "verdict": verdict,
        "db_smoke": db_smoke,
    }

    latest_json = args.reports_dir / "check_refresh_definition_of_done_latest.json"
    latest_md = args.reports_dir / "check_refresh_definition_of_done_latest.md"
    hist_json = args.reports_dir / "history" / f"check_refresh_definition_of_done_{run_ts}.json"
    hist_md = args.reports_dir / "history" / f"check_refresh_definition_of_done_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] canonical_doc_count={canonical_summary['doc_count']}")
    print(f"[OK] canonical_multisource_docs={canonical_summary['multisource_docs']}")
    for k, v in checks.items():
        print(f"[OK] {k}={v}")
    print(f"[OK] dod_passed={verdict['dod_passed']}")
    print(f"[OK] required_failed_count={verdict['required_failed_count']}")
    print(f"[OK] required_failed_checks={verdict['required_failed_checks']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()