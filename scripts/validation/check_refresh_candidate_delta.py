from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


REPORT_NAME = "refresh_candidate_delta_review"
SCHEMA_VERSION = "refresh_candidate_delta_review_v0.1"

DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/validation")

IDENTIFIER_FIELDS = (
    "doi",
    "arxiv_id",
    "openalex_id",
    "pmid",
    "pmcid",
    "semantic_scholar_id",
    "dblp_id",
    "mag_id",
    "reconciliation_key",
)


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


def stable_digest(payload: Mapping[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_families(row: Mapping[str, Any]) -> list[str]:
    families: set[str] = set()

    sources = row.get("sources")
    if isinstance(sources, list):
        for source in sources:
            if not isinstance(source, Mapping):
                continue
            name = source.get("source")
            if name:
                families.add(str(name))

    source_ids = row.get("source_ids")
    if isinstance(source_ids, Mapping):
        families.update(str(name) for name in source_ids.keys() if str(name).strip())

    return sorted(families)


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def sample_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "canonical_id": row.get("canonical_id"),
        "title": row.get("title"),
        "doi": row.get("doi"),
        "arxiv_id": row.get("arxiv_id"),
        "openalex_id": row.get("openalex_id"),
        "semantic_scholar_id": row.get("semantic_scholar_id"),
        "reconciliation_key": row.get("reconciliation_key"),
        "unique_source_count": row.get("unique_source_count"),
        "source_families": source_families(row),
    }


def load_canonical_index(path: Path) -> dict[str, Any]:
    rows_by_id: dict[str, dict[str, Any]] = {}
    duplicate_ids: set[str] = set()
    missing_id_count = 0
    bad_json_count = 0
    non_object_count = 0
    rows_count = 0
    multisource_docs = 0
    doi_count = 0
    max_unique_source_count = 0
    source_family_counts: Counter[str] = Counter()

    if not path.exists():
        return {
            "path": normalize_path(path),
            "exists": False,
            "rows_by_id": rows_by_id,
            "rows_count": 0,
            "bad_json_count": 0,
            "non_object_count": 0,
            "missing_canonical_id_count": 0,
            "duplicate_canonical_id_count": 0,
            "duplicate_canonical_ids_sample": [],
            "doc_count": 0,
            "multisource_docs": 0,
            "doi_count": 0,
            "max_unique_source_count": 0,
            "source_family_counts": {},
        }

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                bad_json_count += 1
                continue
            if not isinstance(row, dict):
                non_object_count += 1
                continue

            rows_count += 1
            canonical_id = str(row.get("canonical_id") or "").strip()
            if not canonical_id:
                missing_id_count += 1
                continue

            if canonical_id in rows_by_id:
                duplicate_ids.add(canonical_id)
            else:
                rows_by_id[canonical_id] = row

            unique_source_count = safe_int(
                row.get("unique_source_count", row.get("source_count")),
                default=0,
            )
            if unique_source_count > 1:
                multisource_docs += 1
            max_unique_source_count = max(max_unique_source_count, unique_source_count)

            if row.get("doi"):
                doi_count += 1

            for family in source_families(row):
                source_family_counts[family] += 1

    return {
        "path": normalize_path(path),
        "exists": True,
        "rows_by_id": rows_by_id,
        "rows_count": rows_count,
        "bad_json_count": bad_json_count,
        "non_object_count": non_object_count,
        "missing_canonical_id_count": missing_id_count,
        "duplicate_canonical_id_count": len(duplicate_ids),
        "duplicate_canonical_ids_sample": sorted(duplicate_ids)[:20],
        "doc_count": len(rows_by_id),
        "multisource_docs": multisource_docs,
        "doi_count": doi_count,
        "max_unique_source_count": max_unique_source_count,
        "source_family_counts": dict(sorted(source_family_counts.items())),
    }


def public_summary(index: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": index["path"],
        "exists": index["exists"],
        "rows_count": index["rows_count"],
        "doc_count": index["doc_count"],
        "bad_json_count": index["bad_json_count"],
        "non_object_count": index["non_object_count"],
        "missing_canonical_id_count": index["missing_canonical_id_count"],
        "duplicate_canonical_id_count": index["duplicate_canonical_id_count"],
        "duplicate_canonical_ids_sample": index["duplicate_canonical_ids_sample"],
        "multisource_docs": index["multisource_docs"],
        "doi_count": index["doi_count"],
        "max_unique_source_count": index["max_unique_source_count"],
        "source_family_counts": index["source_family_counts"],
    }


def identifier_delta(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any] | None:
    changed: dict[str, dict[str, Any]] = {}
    for field in IDENTIFIER_FIELDS:
        left = baseline.get(field)
        right = candidate.get(field)
        if left != right:
            changed[field] = {
                "baseline": left,
                "candidate": right,
            }

    baseline_source_ids = baseline.get("source_ids")
    candidate_source_ids = candidate.get("source_ids")
    if baseline_source_ids != candidate_source_ids:
        changed["source_ids"] = {
            "baseline": baseline_source_ids,
            "candidate": candidate_source_ids,
        }

    if not changed:
        return None

    return {
        "canonical_id": baseline.get("canonical_id"),
        "title": candidate.get("title") or baseline.get("title"),
        "changed_fields": changed,
    }


def compare_indexes(
    baseline_index: Mapping[str, Any],
    candidate_index: Mapping[str, Any],
    *,
    sample_limit: int,
) -> dict[str, Any]:
    baseline_rows = baseline_index["rows_by_id"]
    candidate_rows = candidate_index["rows_by_id"]
    baseline_ids = set(baseline_rows.keys())
    candidate_ids = set(candidate_rows.keys())

    added_ids = sorted(candidate_ids - baseline_ids)
    removed_ids = sorted(baseline_ids - candidate_ids)
    retained_ids = sorted(baseline_ids & candidate_ids)

    changed_ids: list[str] = []
    identifier_churn: list[dict[str, Any]] = []
    source_family_changed_ids: list[str] = []
    unique_source_count_changed_ids: list[str] = []
    title_changed_ids: list[str] = []
    doi_changed_ids: list[str] = []

    for canonical_id in retained_ids:
        baseline_row = baseline_rows[canonical_id]
        candidate_row = candidate_rows[canonical_id]

        if stable_digest(baseline_row) != stable_digest(candidate_row):
            changed_ids.append(canonical_id)

        id_delta = identifier_delta(baseline_row, candidate_row)
        if id_delta:
            identifier_churn.append(id_delta)

        if source_families(baseline_row) != source_families(candidate_row):
            source_family_changed_ids.append(canonical_id)

        if safe_int(baseline_row.get("unique_source_count")) != safe_int(
            candidate_row.get("unique_source_count")
        ):
            unique_source_count_changed_ids.append(canonical_id)

        if baseline_row.get("title") != candidate_row.get("title"):
            title_changed_ids.append(canonical_id)

        if baseline_row.get("doi") != candidate_row.get("doi"):
            doi_changed_ids.append(canonical_id)

    source_family_delta = {
        family: candidate_index["source_family_counts"].get(family, 0)
        - baseline_index["source_family_counts"].get(family, 0)
        for family in sorted(
            set(baseline_index["source_family_counts"])
            | set(candidate_index["source_family_counts"])
        )
    }

    return {
        "counts": {
            "baseline_doc_count": baseline_index["doc_count"],
            "candidate_doc_count": candidate_index["doc_count"],
            "doc_count_delta": candidate_index["doc_count"] - baseline_index["doc_count"],
            "added_count": len(added_ids),
            "removed_count": len(removed_ids),
            "retained_count": len(retained_ids),
            "changed_retained_count": len(changed_ids),
            "identifier_churn_count": len(identifier_churn),
            "source_family_changed_count": len(source_family_changed_ids),
            "unique_source_count_changed_count": len(unique_source_count_changed_ids),
            "title_changed_count": len(title_changed_ids),
            "doi_changed_count": len(doi_changed_ids),
            "multisource_docs_delta": (
                candidate_index["multisource_docs"] - baseline_index["multisource_docs"]
            ),
            "doi_count_delta": candidate_index["doi_count"] - baseline_index["doi_count"],
        },
        "source_family_delta": source_family_delta,
        "samples": {
            "added": [sample_row(candidate_rows[item]) for item in added_ids[:sample_limit]],
            "removed": [
                sample_row(baseline_rows[item]) for item in removed_ids[:sample_limit]
            ],
            "changed_retained": [
                {
                    "canonical_id": item,
                    "baseline": sample_row(baseline_rows[item]),
                    "candidate": sample_row(candidate_rows[item]),
                }
                for item in changed_ids[:sample_limit]
            ],
            "identifier_churn": identifier_churn[:sample_limit],
            "source_family_changed": source_family_changed_ids[:sample_limit],
            "unique_source_count_changed": unique_source_count_changed_ids[:sample_limit],
        },
    }


def build_checks(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    delta: Mapping[str, Any],
    *,
    candidate_path: Path,
    canonical_path: Path,
    max_removed: int,
    max_identifier_churn: int,
) -> dict[str, bool]:
    counts = delta["counts"]
    return {
        "canonical_path_exists": bool(baseline["exists"]),
        "candidate_path_exists": bool(candidate["exists"]),
        "candidate_path_differs_from_canonical": normalize_path(candidate_path)
        != normalize_path(canonical_path),
        "canonical_jsonl_valid": baseline["bad_json_count"] == 0,
        "candidate_jsonl_valid": candidate["bad_json_count"] == 0,
        "canonical_rows_are_objects": baseline["non_object_count"] == 0,
        "candidate_rows_are_objects": candidate["non_object_count"] == 0,
        "canonical_ids_present": baseline["missing_canonical_id_count"] == 0,
        "candidate_ids_present": candidate["missing_canonical_id_count"] == 0,
        "canonical_ids_unique": baseline["duplicate_canonical_id_count"] == 0,
        "candidate_ids_unique": candidate["duplicate_canonical_id_count"] == 0,
        "candidate_non_empty": candidate["doc_count"] > 0,
        "candidate_not_smaller_than_canonical": counts["doc_count_delta"] >= 0,
        "removed_count_within_threshold": counts["removed_count"] <= max_removed,
        "identifier_churn_within_threshold": (
            counts["identifier_churn_count"] <= max_identifier_churn
        ),
    }


def build_markdown(report: Mapping[str, Any]) -> str:
    lines: list[str] = [
        "# Refresh candidate delta review v0.1",
        "",
        f"- Generated at: `{report['generated_at_utc']}`",
        f"- Run ts: `{report['run_ts']}`",
        f"- Strict: `{report['strict']}`",
        f"- Read only: `{report['read_only']}`",
        "",
        "## Summary",
        "",
    ]

    for name, value in report["summary"].items():
        lines.append(f"- {name}: `{value}`")

    lines.extend(["", "## Delta Counts", ""])
    for name, value in report["delta"]["counts"].items():
        lines.append(f"- {name}: `{value}`")

    lines.extend(["", "## Checks", ""])
    for name, value in report["checks"].items():
        lines.append(f"- {name}: `{value}`")

    lines.extend(["", "## Verdict", ""])
    for name, value in report["verdict"].items():
        lines.append(f"- {name}: `{value}`")

    lines.extend(["", "## Source Family Delta", ""])
    if report["delta"]["source_family_delta"]:
        for name, value in report["delta"]["source_family_delta"].items():
            lines.append(f"- {name}: `{value}`")
    else:
        lines.append("- none")

    lines.extend(["", "## Samples", ""])
    for section_name, rows in report["delta"]["samples"].items():
        lines.append(f"### {section_name}")
        if not rows:
            lines.append("- none")
            lines.append("")
            continue
        for row in rows:
            lines.append(f"- `{row}`")
        lines.append("")

    return "\n".join(lines)


def build_report(
    *,
    canonical_path: Path,
    candidate_path: Path,
    reports_dir: Path,
    strict: bool,
    max_removed: int,
    max_identifier_churn: int,
    sample_limit: int,
) -> dict[str, Any]:
    baseline = load_canonical_index(canonical_path)
    candidate = load_canonical_index(candidate_path)
    delta = compare_indexes(baseline, candidate, sample_limit=sample_limit)
    checks = build_checks(
        baseline,
        candidate,
        delta,
        candidate_path=candidate_path,
        canonical_path=canonical_path,
        max_removed=max_removed,
        max_identifier_churn=max_identifier_churn,
    )
    failed = [name for name, ok in checks.items() if not ok]
    counts = delta["counts"]

    return {
        "report_name": REPORT_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": utc_now_ts(),
        "strict": bool(strict),
        "status": "read_only_validation",
        "read_only": True,
        "canonical_truth_mutated": False,
        "promotion_executed": False,
        "derived_layers_rebuilt": False,
        "inputs": {
            "canonical_path": normalize_path(canonical_path),
            "candidate_path": normalize_path(candidate_path),
            "reports_dir": normalize_path(reports_dir),
            "max_removed": max_removed,
            "max_identifier_churn": max_identifier_churn,
            "sample_limit": sample_limit,
        },
        "baseline": public_summary(baseline),
        "candidate": public_summary(candidate),
        "delta": delta,
        "checks": checks,
        "summary": {
            "baseline_doc_count": counts["baseline_doc_count"],
            "candidate_doc_count": counts["candidate_doc_count"],
            "doc_count_delta": counts["doc_count_delta"],
            "added_count": counts["added_count"],
            "removed_count": counts["removed_count"],
            "identifier_churn_count": counts["identifier_churn_count"],
            "source_family_changed_count": counts["source_family_changed_count"],
            "multisource_docs_delta": counts["multisource_docs_delta"],
        },
        "verdict": {
            "ok": not failed,
            "required_failed_count": len(failed),
            "required_failed_checks": failed,
            "promotion_delta_review_ready": not failed,
            "manual_review_required": bool(
                counts["removed_count"] > 0
                or counts["identifier_churn_count"] > 0
                or counts["changed_retained_count"] > 0
            ),
            "canonical_truth_mutation_required": False,
            "derived_layer_mutation_required": False,
        },
    }


def write_reports(
    report: Mapping[str, Any],
    reports_dir: Path,
) -> tuple[Path, Path, Path, Path]:
    run_ts = str(report["run_ts"])
    latest_json = reports_dir / f"{REPORT_NAME}_latest.json"
    latest_md = reports_dir / f"{REPORT_NAME}_latest.md"
    hist_json = reports_dir / "history" / f"{REPORT_NAME}_{run_ts}.json"
    hist_md = reports_dir / "history" / f"{REPORT_NAME}_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    return latest_json, latest_md, hist_json, hist_md


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare current canonical latest and a refresh candidate before any "
            "promotion/export/retrieval step."
        )
    )
    parser.add_argument(
        "--canonical-path",
        type=Path,
        default=DEFAULT_CANONICAL_PATH,
        help="Current stable canonical JSONL path.",
    )
    parser.add_argument(
        "--candidate-path",
        type=Path,
        required=True,
        help="Candidate canonical JSONL path produced by the refresh rehearsal.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Directory where validation reports are written.",
    )
    parser.add_argument(
        "--max-removed",
        type=int,
        default=0,
        help="Maximum removed canonical IDs allowed in strict mode.",
    )
    parser.add_argument(
        "--max-identifier-churn",
        type=int,
        default=0,
        help="Maximum retained-row identifier churn allowed in strict mode.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="Maximum sample rows per report bucket.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when required checks fail.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_report(
        canonical_path=args.canonical_path,
        candidate_path=args.candidate_path,
        reports_dir=args.reports_dir,
        strict=bool(args.strict),
        max_removed=args.max_removed,
        max_identifier_churn=args.max_identifier_churn,
        sample_limit=max(0, int(args.sample_limit)),
    )
    latest_json, latest_md, hist_json, hist_md = write_reports(report, args.reports_dir)

    verdict = report["verdict"]
    summary = report["summary"]
    status = "OK" if verdict["ok"] else "FAILED"
    print(f"[{status}] report_name={REPORT_NAME}")
    print(f"[{status}] strict={bool(args.strict)}")
    print(f"[{status}] read_only={report['read_only']}")
    print(f"[{status}] baseline_doc_count={summary['baseline_doc_count']}")
    print(f"[{status}] candidate_doc_count={summary['candidate_doc_count']}")
    print(f"[{status}] doc_count_delta={summary['doc_count_delta']}")
    print(f"[{status}] added_count={summary['added_count']}")
    print(f"[{status}] removed_count={summary['removed_count']}")
    print(f"[{status}] identifier_churn_count={summary['identifier_churn_count']}")
    print(f"[{status}] promotion_delta_review_ready={verdict['promotion_delta_review_ready']}")
    print(f"[{status}] manual_review_required={verdict['manual_review_required']}")
    print(f"[{status}] required_failed_count={verdict['required_failed_count']}")
    print(f"[{status}] latest JSON: {latest_json}")
    print(f"[{status}] latest Markdown: {latest_md}")
    print(f"[{status}] history JSON: {hist_json}")
    print(f"[{status}] history Markdown: {hist_md}")

    if args.strict and not verdict["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
