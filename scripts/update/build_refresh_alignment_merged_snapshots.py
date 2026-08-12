from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from scripts.update.merge_selective_alignment_snapshots import merge_rows
from scripts.validation import check_refresh_alignment_coverage as coverage


DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_NORMALIZED_ROOT = Path("data/normalized")
DEFAULT_REPORTS_DIR = Path("artifacts/reports")
DEFAULT_UPDATE_DIR = DEFAULT_REPORTS_DIR / "update"

ALIGNMENT_SOURCES = (
    "openalex_alignment",
    "semantic_scholar_alignment",
    "crossref_alignment",
)

DEFAULT_INGEST_REPORTS = {
    "openalex_alignment": DEFAULT_REPORTS_DIR / "openalex_alignment_ingest_latest.json",
    "semantic_scholar_alignment": (
        DEFAULT_REPORTS_DIR / "semantic_scholar_alignment_ingest_latest.json"
    ),
    "crossref_alignment": DEFAULT_REPORTS_DIR / "crossref_alignment_ingest_latest.json",
}

FULL_SNAPSHOT_EXCLUDED_SUFFIXES = (
    ".new.jsonl",
    ".updated.jsonl",
    ".unchanged.jsonl",
)


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def path_from_report_value(value: Any) -> Path | None:
    if not value:
        return None
    return Path(str(value).replace("\\", "/"))


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: Mapping[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required JSON file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object in {path}, got {type(payload)!r}")
    return payload


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return load_json(path)


def load_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def dump_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def safe_get(data: Any, *keys: str, default: Any = None) -> Any:
    cur = data
    for key in keys:
        if not isinstance(cur, Mapping):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def is_full_snapshot_file(path: Path) -> bool:
    name = path.name
    if name == "documents_latest.jsonl":
        return True
    if not name.startswith("documents") or not name.endswith(".jsonl"):
        return False
    return not name.endswith(FULL_SNAPSHOT_EXCLUDED_SUFFIXES)


def iter_full_snapshot_candidates(
    source_dir: Path,
    *,
    exclude_paths: set[Path],
) -> list[Path]:
    if not source_dir.exists():
        return []

    normalized_excludes = {Path(normalize_path(path) or "") for path in exclude_paths}
    candidates: list[Path] = []
    for path in sorted(source_dir.glob("documents*.jsonl")):
        normalized_path = Path(normalize_path(path) or "")
        if normalized_path in normalized_excludes:
            continue
        if is_full_snapshot_file(path):
            candidates.append(path)
    return candidates


def resolve_incremental_snapshot(
    *,
    source_name: str,
    ingest_report_path: Path,
    fallback_merge_report_path: Path | None = None,
) -> dict[str, Any]:
    report = load_json_if_exists(ingest_report_path)
    raw_path = None
    resolved_from = None
    if report is not None:
        raw_path = (
            safe_get(report, "artifacts", "normalized_jsonl")
            or report.get("normalized_output")
            or safe_get(report, "summary", "normalized_output")
        )
        if raw_path:
            resolved_from = "ingest_report"

    if not raw_path and fallback_merge_report_path is not None:
        fallback_report = load_json_if_exists(fallback_merge_report_path)
        raw_path = safe_get(fallback_report, "output", "merged_snapshot")
        if raw_path:
            resolved_from = "fallback_merge_report_output"

    incremental_path = path_from_report_value(raw_path)
    return {
        "source_name": source_name,
        "ingest_report_path": normalize_path(ingest_report_path),
        "ingest_report_exists": report is not None,
        "fallback_merge_report_path": normalize_path(fallback_merge_report_path),
        "incremental_resolved_from": resolved_from,
        "incremental_snapshot": normalize_path(incremental_path),
        "incremental_snapshot_exists": bool(
            incremental_path is not None and incremental_path.exists()
        ),
    }


def baseline_rows_with_family(
    canonical_path: Path,
    family: str,
) -> list[Mapping[str, Any]]:
    baseline = coverage.candidate_delta.load_canonical_index(canonical_path)
    rows: list[Mapping[str, Any]] = []
    for row in baseline["rows_by_id"].values():
        if family in coverage.canonical_families(row):
            rows.append(row)
    return rows


def count_covered_baseline_rows(
    *,
    baseline_rows: list[Mapping[str, Any]],
    snapshot_rows: list[Mapping[str, Any]],
    family: str,
) -> int:
    key_to_row: dict[str, Mapping[str, Any]] = {}
    for row in snapshot_rows:
        for key in coverage.row_match_keys(row, family):
            key_to_row.setdefault(key, row)

    covered = 0
    snapshot_keys = set(key_to_row)
    for row in baseline_rows:
        if coverage.row_match_keys(row, family) & snapshot_keys:
            covered += 1
    return covered


def summarize_snapshot_coverage(
    *,
    path: Path | None,
    baseline_rows: list[Mapping[str, Any]],
    family: str,
) -> dict[str, Any]:
    rows = load_jsonl(path)
    coverage_count = count_covered_baseline_rows(
        baseline_rows=baseline_rows,
        snapshot_rows=rows,
        family=family,
    )
    return {
        "path": normalize_path(path),
        "exists": bool(path is not None and path.exists()),
        "rows_count": len(rows),
        "baseline_source_docs_count": len(baseline_rows),
        "baseline_source_docs_covered_count": coverage_count,
        "baseline_source_docs_missing_count": max(len(baseline_rows) - coverage_count, 0),
    }


def choose_base_snapshot(
    *,
    source_dir: Path,
    baseline_rows: list[Mapping[str, Any]],
    family: str,
    exclude_paths: set[Path],
) -> dict[str, Any]:
    candidates = iter_full_snapshot_candidates(source_dir, exclude_paths=exclude_paths)
    scored: list[dict[str, Any]] = []
    for path in candidates:
        summary = summarize_snapshot_coverage(
            path=path,
            baseline_rows=baseline_rows,
            family=family,
        )
        scored.append(summary)

    scored.sort(
        key=lambda item: (
            int(item["baseline_source_docs_covered_count"]),
            int(item["rows_count"]),
            str(item["path"] or ""),
        ),
        reverse=True,
    )

    selected = scored[0] if scored else None
    return {
        "candidate_count": len(scored),
        "selected": selected,
        "top_candidates": scored[:5],
    }


def build_source_merge(
    *,
    source_name: str,
    canonical_path: Path,
    normalized_root: Path,
    ingest_report_path: Path,
    update_dir: Path,
    run_ts: str,
    execute: bool,
) -> dict[str, Any]:
    source_dir = normalized_root / source_name
    latest_merge_report_path = update_dir / f"merge_{source_name}_latest.json"
    history_merge_report_path = (
        update_dir / "history" / f"merge_{source_name}_{run_ts}.json"
    )
    incremental = resolve_incremental_snapshot(
        source_name=source_name,
        ingest_report_path=ingest_report_path,
        fallback_merge_report_path=latest_merge_report_path,
    )
    incremental_path = path_from_report_value(incremental["incremental_snapshot"])
    baseline_rows = baseline_rows_with_family(canonical_path, source_name)

    base_choice = choose_base_snapshot(
        source_dir=source_dir,
        baseline_rows=baseline_rows,
        family=source_name,
        exclude_paths={incremental_path} if incremental_path is not None else set(),
    )
    selected_base_raw = safe_get(base_choice, "selected", "path")
    selected_base_path = path_from_report_value(selected_base_raw)

    base_rows = load_jsonl(selected_base_path)
    incremental_rows = load_jsonl(incremental_path)
    merged_rows, merge_stats = merge_rows(base_rows, incremental_rows)

    output_path = source_dir / f"documents.{run_ts}.jsonl"
    output_summary = {
        "path": normalize_path(output_path),
        "rows_count": len(merged_rows),
        "baseline_source_docs_count": len(baseline_rows),
        "baseline_source_docs_covered_count": count_covered_baseline_rows(
            baseline_rows=baseline_rows,
            snapshot_rows=merged_rows,
            family=source_name,
        ),
    }
    output_summary["baseline_source_docs_missing_count"] = max(
        output_summary["baseline_source_docs_count"]
        - output_summary["baseline_source_docs_covered_count"],
        0,
    )

    coverage_safe = output_summary["baseline_source_docs_missing_count"] == 0
    source_ok = bool(
        incremental["incremental_snapshot_exists"]
        and selected_base_path is not None
        and selected_base_path.exists()
        and coverage_safe
    )

    merge_report = {
        "report_name": "merge_selective_alignment_snapshots",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "source_name": source_name,
        "inputs": {
            "base_snapshot": normalize_path(selected_base_path),
            "incremental_snapshot": normalize_path(incremental_path),
            "base_selection_mode": "max_baseline_alignment_coverage",
        },
        "output": {
            "merged_snapshot": normalize_path(output_path),
        },
        "stats": {
            **merge_stats,
            "baseline_source_docs_count": output_summary[
                "baseline_source_docs_count"
            ],
            "baseline_source_docs_covered_count": output_summary[
                "baseline_source_docs_covered_count"
            ],
            "baseline_source_docs_missing_count": output_summary[
                "baseline_source_docs_missing_count"
            ],
        },
    }

    if execute and source_ok:
        dump_jsonl(output_path, merged_rows)
        dump_json(latest_merge_report_path, merge_report)
        dump_json(history_merge_report_path, merge_report)

    return {
        "source_name": source_name,
        "ok": source_ok,
        "execute": execute,
        "incremental": incremental,
        "base_selection": base_choice,
        "output": {
            **output_summary,
            "written": bool(execute and source_ok),
        },
        "merge_stats": merge_stats,
        "coverage_safe": coverage_safe,
        "latest_merge_report": normalize_path(latest_merge_report_path),
        "history_merge_report": normalize_path(history_merge_report_path),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    run_ts = utc_now_ts()
    source_names = args.source or list(ALIGNMENT_SOURCES)
    ingest_reports = {
        source_name: args.reports_dir / DEFAULT_INGEST_REPORTS[source_name].name
        for source_name in source_names
    }

    source_results = [
        build_source_merge(
            source_name=source_name,
            canonical_path=args.canonical_path,
            normalized_root=args.normalized_root,
            ingest_report_path=ingest_reports[source_name],
            update_dir=args.update_dir,
            run_ts=run_ts,
            execute=args.execute,
        )
        for source_name in source_names
    ]

    ok = all(result["ok"] for result in source_results)
    return {
        "report_name": "build_refresh_alignment_merged_snapshots",
        "schema_version": "build_refresh_alignment_merged_snapshots_v0.1",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "mode": "execute" if args.execute else "dry_run",
        "canonical_truth_mutated": False,
        "promotion_executed": False,
        "inputs": {
            "canonical_path": normalize_path(args.canonical_path),
            "normalized_root": normalize_path(args.normalized_root),
            "reports_dir": normalize_path(args.reports_dir),
            "update_dir": normalize_path(args.update_dir),
            "sources": source_names,
        },
        "source_results": source_results,
        "summary": {
            "source_count": len(source_results),
            "ok_source_count": sum(1 for item in source_results if item["ok"]),
            "coverage_safe_source_count": sum(
                1 for item in source_results if item["coverage_safe"]
            ),
            "outputs_written_count": sum(
                1 for item in source_results if item["output"]["written"]
            ),
        },
        "verdict": {
            "ok": ok,
            "manual_review_required": not ok,
            "safe_to_run_reconcile_candidate": ok,
        },
    }


def build_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Refresh alignment merged snapshots build",
        "",
        f"- Generated at: `{report['generated_at_utc']}`",
        f"- Run ts: `{report['run_ts']}`",
        f"- Mode: `{report['mode']}`",
        f"- OK: `{coverage.as_mapping(report['verdict']).get('ok')}`",
        "",
        "## Summary",
    ]
    for key, value in coverage.as_mapping(report["summary"]).items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Sources"])
    for result in report["source_results"]:
        output = coverage.as_mapping(result["output"])
        selected_base = coverage.as_mapping(
            coverage.as_mapping(result["base_selection"]).get("selected")
        )
        lines.append(f"### {result['source_name']}")
        lines.append(f"- ok: `{result['ok']}`")
        lines.append(f"- selected_base: `{selected_base.get('path')}`")
        lines.append(f"- output: `{output.get('path')}`")
        lines.append(
            "- baseline_source_docs_missing_count: "
            f"`{output.get('baseline_source_docs_missing_count')}`"
        )
        lines.append("")

    return "\n".join(lines)


def write_report(report: Mapping[str, Any], update_dir: Path) -> tuple[Path, Path, Path, Path]:
    run_ts = str(report["run_ts"])
    latest_json = update_dir / "build_refresh_alignment_merged_snapshots_latest.json"
    latest_md = update_dir / "build_refresh_alignment_merged_snapshots_latest.md"
    history_json = (
        update_dir / "history" / f"build_refresh_alignment_merged_snapshots_{run_ts}.json"
    )
    history_md = (
        update_dir / "history" / f"build_refresh_alignment_merged_snapshots_{run_ts}.md"
    )
    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(history_json, report)
    dump_text(history_md, build_markdown(report))
    return latest_json, latest_md, history_json, history_md


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build coverage-safe full alignment snapshots for refresh reconcile input."
        )
    )
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument("--normalized-root", type=Path, default=DEFAULT_NORMALIZED_ROOT)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--update-dir", type=Path, default=DEFAULT_UPDATE_DIR)
    parser.add_argument(
        "--source",
        action="append",
        choices=ALIGNMENT_SOURCES,
        default=None,
        help="Alignment source to build. Can be repeated. Defaults to all alignment sources.",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_report(args)
    latest_json, latest_md, history_json, history_md = write_report(
        report,
        args.update_dir,
    )

    print(f"[OK] mode={report['mode']}")
    print(f"[OK] ok={report['verdict']['ok']}")
    for result in report["source_results"]:
        output = result["output"]
        print(f"[OK] {result['source_name']}.ok={result['ok']}")
        print(
            f"[OK] {result['source_name']}.baseline_missing="
            f"{output['baseline_source_docs_missing_count']}"
        )
        print(f"[OK] {result['source_name']}.output={output['path']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history Markdown: {history_md}")

    if args.strict and not report["verdict"]["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
