from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CANONICAL_DIR = Path("data/analytics/reconciled")
DEFAULT_UPDATE_DIR = Path("artifacts/reports/update")


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


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Promote canonical candidate report")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Mode: `{report['mode']}`")
    lines.append("")

    lines.append("## Inputs")
    for k, v in report["inputs"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    lines.append("## Paths")
    for k, v in report["paths"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    lines.append("## Prechecks")
    for k, v in report["prechecks"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    if report.get("candidate_summary"):
        lines.append("## Candidate summary")
        for k, v in report["candidate_summary"].items():
            lines.append(f"- {k}: `{v}`")
        lines.append("")

    if report.get("previous_latest_summary"):
        lines.append("## Previous latest summary")
        for k, v in report["previous_latest_summary"].items():
            lines.append(f"- {k}: `{v}`")
        lines.append("")

    if report.get("new_latest_summary"):
        lines.append("## New latest summary")
        for k, v in report["new_latest_summary"].items():
            lines.append(f"- {k}: `{v}`")
        lines.append("")

    lines.append("## Execution summary")
    for k, v in report["execution_summary"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Promote canonical candidate JSONL to canonical latest with backup."
    )
    parser.add_argument(
        "--candidate-path",
        type=Path,
        required=True,
        help="Path to candidate canonical JSONL file.",
    )
    parser.add_argument(
        "--canonical-dir",
        type=Path,
        default=DEFAULT_CANONICAL_DIR,
        help="Canonical directory containing canonical_documents.jsonl",
    )
    parser.add_argument(
        "--update-dir",
        type=Path,
        default=DEFAULT_UPDATE_DIR,
        help="Directory for update reports.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform backup and promotion. Without this flag the script runs in dry-run mode.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    candidate_path: Path = args.candidate_path
    canonical_dir: Path = args.canonical_dir
    update_dir: Path = args.update_dir

    latest_path = canonical_dir / "canonical_documents.jsonl"
    backup_path = canonical_dir / f"canonical_documents.backup_before_promotion.{run_ts}.jsonl"

    prechecks = {
        "candidate_exists": candidate_path.exists(),
        "latest_exists": latest_path.exists(),
    }

    if not prechecks["candidate_exists"]:
        raise FileNotFoundError(f"Candidate file not found: {candidate_path}")
    if not prechecks["latest_exists"]:
        raise FileNotFoundError(f"Latest canonical file not found: {latest_path}")

    candidate_summary = summarize_canonical(candidate_path)
    previous_latest_summary = summarize_canonical(latest_path)

    execution_summary = {
        "executed": bool(args.execute),
        "backup_created": False,
        "promotion_performed": False,
        "postcheck_match": False,
    }

    new_latest_summary: dict[str, Any] | None = None

    if args.execute:
        ensure_parent(backup_path)
        shutil.copy2(latest_path, backup_path)
        execution_summary["backup_created"] = True

        shutil.copy2(candidate_path, latest_path)
        execution_summary["promotion_performed"] = True

        new_latest_summary = summarize_canonical(latest_path)
        execution_summary["postcheck_match"] = (
            candidate_summary["doc_count"] == new_latest_summary["doc_count"]
            and candidate_summary["multisource_docs"] == new_latest_summary["multisource_docs"]
            and candidate_summary["doi_count"] == new_latest_summary["doi_count"]
        )

    report = {
        "report_name": "promote_canonical_candidate",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "mode": "execute" if args.execute else "dry_run",
        "inputs": {
            "candidate_path": normalize_path(candidate_path),
            "canonical_dir": normalize_path(canonical_dir),
        },
        "paths": {
            "latest_path": normalize_path(latest_path),
            "backup_path": normalize_path(backup_path),
        },
        "prechecks": prechecks,
        "candidate_summary": candidate_summary,
        "previous_latest_summary": previous_latest_summary,
        "new_latest_summary": new_latest_summary,
        "execution_summary": execution_summary,
    }

    latest_json = update_dir / "promote_canonical_candidate_latest.json"
    latest_md = update_dir / "promote_canonical_candidate_latest.md"
    hist_json = update_dir / "history" / f"promote_canonical_candidate_{run_ts}.json"
    hist_md = update_dir / "history" / f"promote_canonical_candidate_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] mode={report['mode']}")
    print(f"[OK] candidate_path={normalize_path(candidate_path)}")
    print(f"[OK] latest_path={normalize_path(latest_path)}")
    print(f"[OK] backup_path={normalize_path(backup_path)}")
    print(f"[OK] candidate_doc_count={candidate_summary['doc_count']}")
    print(f"[OK] previous_latest_doc_count={previous_latest_summary['doc_count']}")
    if new_latest_summary:
        print(f"[OK] new_latest_doc_count={new_latest_summary['doc_count']}")
    print(f"[OK] backup_created={execution_summary['backup_created']}")
    print(f"[OK] promotion_performed={execution_summary['promotion_performed']}")
    print(f"[OK] postcheck_match={execution_summary['postcheck_match']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()