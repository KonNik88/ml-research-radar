from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from scripts.validation import check_refresh_candidate_delta as candidate_delta


REPORT_NAME = "refresh_source_coverage_diagnostics"
SCHEMA_VERSION = "refresh_source_coverage_diagnostics_v0.1"

DEFAULT_DELTA_REPORT_PATH = (
    Path("artifacts/reports/validation") / "refresh_candidate_delta_review_latest.json"
)
DEFAULT_REPORTS_DIR = Path("artifacts/reports/validation")


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


def as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def read_json(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping):
        return payload
    return {}


def source_families(row: Mapping[str, Any]) -> list[str]:
    return candidate_delta.source_families(row)


def source_family_set(row: Mapping[str, Any]) -> set[str]:
    return set(source_families(row))


def source_family_key(families: set[str] | list[str] | tuple[str, ...]) -> str:
    values = sorted(str(item) for item in families if str(item).strip())
    if not values:
        return "(none)"
    return "+".join(values)


def source_ids(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return as_mapping(row.get("source_ids"))


def safe_int(value: Any, default: int = 0) -> int:
    return candidate_delta.safe_int(value, default=default)


def compact_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "canonical_id": row.get("canonical_id"),
        "title": row.get("title"),
        "doi": row.get("doi"),
        "arxiv_id": row.get("arxiv_id"),
        "openalex_id": row.get("openalex_id"),
        "semantic_scholar_id": row.get("semantic_scholar_id"),
        "reconciliation_key": row.get("reconciliation_key"),
        "unique_source_count": row.get("unique_source_count", row.get("source_count")),
        "source_families": source_families(row),
    }


def lost_identifier_fields(
    baseline_row: Mapping[str, Any],
    candidate_row: Mapping[str, Any],
) -> list[str]:
    lost: list[str] = []
    for field in candidate_delta.IDENTIFIER_FIELDS:
        baseline_value = baseline_row.get(field)
        candidate_value = candidate_row.get(field)
        if baseline_value and not candidate_value:
            lost.append(field)
    return lost


def gained_identifier_fields(
    baseline_row: Mapping[str, Any],
    candidate_row: Mapping[str, Any],
) -> list[str]:
    gained: list[str] = []
    for field in candidate_delta.IDENTIFIER_FIELDS:
        baseline_value = baseline_row.get(field)
        candidate_value = candidate_row.get(field)
        if candidate_value and not baseline_value:
            gained.append(field)
    return gained


def lost_source_id_families(
    baseline_row: Mapping[str, Any],
    candidate_row: Mapping[str, Any],
) -> list[str]:
    baseline_ids = source_ids(baseline_row)
    candidate_ids = source_ids(candidate_row)
    return sorted(str(key) for key in set(baseline_ids) - set(candidate_ids))


def gained_source_id_families(
    baseline_row: Mapping[str, Any],
    candidate_row: Mapping[str, Any],
) -> list[str]:
    baseline_ids = source_ids(baseline_row)
    candidate_ids = source_ids(candidate_row)
    return sorted(str(key) for key in set(candidate_ids) - set(baseline_ids))


def diagnose_removed(
    baseline_rows: Mapping[str, Mapping[str, Any]],
    removed_ids: list[str],
    *,
    sample_limit: int,
) -> dict[str, Any]:
    by_family_combo: Counter[str] = Counter()
    by_source_family: Counter[str] = Counter()
    acl_only_count = 0
    arxiv_only_count = 0
    multisource_count = 0
    with_doi_count = 0
    samples: list[dict[str, Any]] = []

    for canonical_id in removed_ids:
        row = baseline_rows[canonical_id]
        families = source_family_set(row)
        by_family_combo[source_family_key(families)] += 1
        for family in families:
            by_source_family[family] += 1

        if families == {"acl_anthology"}:
            acl_only_count += 1
        if families == {"arxiv"}:
            arxiv_only_count += 1
        if len(families) > 1 or safe_int(row.get("unique_source_count")) > 1:
            multisource_count += 1
        if row.get("doi"):
            with_doi_count += 1
        if len(samples) < sample_limit:
            samples.append(compact_row(row))

    return {
        "count": len(removed_ids),
        "by_family_combo": dict(sorted(by_family_combo.items())),
        "by_source_family": dict(sorted(by_source_family.items())),
        "acl_only_count": acl_only_count,
        "arxiv_only_count": arxiv_only_count,
        "multisource_count": multisource_count,
        "with_doi_count": with_doi_count,
        "samples": samples,
    }


def diagnose_added(
    candidate_rows: Mapping[str, Mapping[str, Any]],
    added_ids: list[str],
    *,
    sample_limit: int,
) -> dict[str, Any]:
    by_family_combo: Counter[str] = Counter()
    by_source_family: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []

    for canonical_id in added_ids:
        row = candidate_rows[canonical_id]
        families = source_family_set(row)
        by_family_combo[source_family_key(families)] += 1
        for family in families:
            by_source_family[family] += 1
        if len(samples) < sample_limit:
            samples.append(compact_row(row))

    return {
        "count": len(added_ids),
        "by_family_combo": dict(sorted(by_family_combo.items())),
        "by_source_family": dict(sorted(by_source_family.items())),
        "samples": samples,
    }


def diagnose_retained(
    baseline_rows: Mapping[str, Mapping[str, Any]],
    candidate_rows: Mapping[str, Mapping[str, Any]],
    retained_ids: list[str],
    *,
    sample_limit: int,
) -> dict[str, Any]:
    transition_counts: Counter[str] = Counter()
    lost_family_counts: Counter[str] = Counter()
    gained_family_counts: Counter[str] = Counter()
    identifier_loss_counts: Counter[str] = Counter()
    identifier_gain_counts: Counter[str] = Counter()
    source_id_loss_counts: Counter[str] = Counter()
    source_id_gain_counts: Counter[str] = Counter()

    source_family_changed_count = 0
    unique_source_count_drop_count = 0
    multisource_to_single_source_count = 0
    multisource_to_arxiv_only_count = 0
    identifier_loss_rows_count = 0
    source_id_loss_rows_count = 0

    source_family_changed_samples: list[dict[str, Any]] = []
    identifier_loss_samples: list[dict[str, Any]] = []

    for canonical_id in retained_ids:
        baseline_row = baseline_rows[canonical_id]
        candidate_row = candidate_rows[canonical_id]
        baseline_families = source_family_set(baseline_row)
        candidate_families = source_family_set(candidate_row)

        if baseline_families != candidate_families:
            source_family_changed_count += 1
            transition_counts[
                f"{source_family_key(baseline_families)} -> "
                f"{source_family_key(candidate_families)}"
            ] += 1
            for family in baseline_families - candidate_families:
                lost_family_counts[family] += 1
            for family in candidate_families - baseline_families:
                gained_family_counts[family] += 1
            if len(source_family_changed_samples) < sample_limit:
                source_family_changed_samples.append(
                    {
                        "canonical_id": canonical_id,
                        "title": candidate_row.get("title") or baseline_row.get("title"),
                        "baseline_source_families": sorted(baseline_families),
                        "candidate_source_families": sorted(candidate_families),
                        "baseline_unique_source_count": baseline_row.get(
                            "unique_source_count", baseline_row.get("source_count")
                        ),
                        "candidate_unique_source_count": candidate_row.get(
                            "unique_source_count", candidate_row.get("source_count")
                        ),
                    }
                )

        baseline_unique_source_count = safe_int(
            baseline_row.get("unique_source_count", baseline_row.get("source_count"))
        )
        candidate_unique_source_count = safe_int(
            candidate_row.get("unique_source_count", candidate_row.get("source_count"))
        )
        if candidate_unique_source_count < baseline_unique_source_count:
            unique_source_count_drop_count += 1
        if baseline_unique_source_count > 1 and candidate_unique_source_count <= 1:
            multisource_to_single_source_count += 1
        if baseline_unique_source_count > 1 and candidate_families == {"arxiv"}:
            multisource_to_arxiv_only_count += 1

        lost_fields = lost_identifier_fields(baseline_row, candidate_row)
        gained_fields = gained_identifier_fields(baseline_row, candidate_row)
        lost_source_ids = lost_source_id_families(baseline_row, candidate_row)
        gained_source_ids = gained_source_id_families(baseline_row, candidate_row)

        if lost_fields:
            identifier_loss_rows_count += 1
            identifier_loss_counts.update(lost_fields)
        if gained_fields:
            identifier_gain_counts.update(gained_fields)
        if lost_source_ids:
            source_id_loss_rows_count += 1
            source_id_loss_counts.update(lost_source_ids)
        if gained_source_ids:
            source_id_gain_counts.update(gained_source_ids)

        if (lost_fields or lost_source_ids) and len(identifier_loss_samples) < sample_limit:
            identifier_loss_samples.append(
                {
                    "canonical_id": canonical_id,
                    "title": candidate_row.get("title") or baseline_row.get("title"),
                    "baseline_source_families": sorted(baseline_families),
                    "candidate_source_families": sorted(candidate_families),
                    "lost_identifier_fields": lost_fields,
                    "lost_source_id_families": lost_source_ids,
                }
            )

    return {
        "count": len(retained_ids),
        "source_family_changed_count": source_family_changed_count,
        "source_family_transition_counts": dict(transition_counts.most_common(25)),
        "lost_source_family_counts": dict(sorted(lost_family_counts.items())),
        "gained_source_family_counts": dict(sorted(gained_family_counts.items())),
        "unique_source_count_drop_count": unique_source_count_drop_count,
        "multisource_to_single_source_count": multisource_to_single_source_count,
        "multisource_to_arxiv_only_count": multisource_to_arxiv_only_count,
        "identifier_loss": {
            "rows_count": identifier_loss_rows_count,
            "by_field": dict(sorted(identifier_loss_counts.items())),
            "gained_by_field": dict(sorted(identifier_gain_counts.items())),
            "samples": identifier_loss_samples,
        },
        "source_id_loss": {
            "rows_count": source_id_loss_rows_count,
            "by_source_family": dict(sorted(source_id_loss_counts.items())),
            "gained_by_source_family": dict(sorted(source_id_gain_counts.items())),
        },
        "source_family_changed_samples": source_family_changed_samples,
    }


def build_signals(
    *,
    removed: Mapping[str, Any],
    retained: Mapping[str, Any],
) -> dict[str, Any]:
    removed_count = safe_int(removed.get("count"))
    acl_only_removed_count = safe_int(removed.get("acl_only_count"))
    retained_identifier_loss_count = safe_int(
        as_mapping(retained.get("identifier_loss")).get("rows_count")
    )
    retained_source_id_loss_count = safe_int(
        as_mapping(retained.get("source_id_loss")).get("rows_count")
    )
    multisource_to_arxiv_only_count = safe_int(
        retained.get("multisource_to_arxiv_only_count")
    )

    return {
        "source_coverage_regression_detected": bool(
            removed_count
            or retained.get("source_family_changed_count")
            or retained_identifier_loss_count
            or retained_source_id_loss_count
        ),
        "likely_missing_acl_input": bool(
            removed_count > 0 and acl_only_removed_count / max(removed_count, 1) >= 0.5
        ),
        "likely_retained_non_arxiv_source_loss": bool(
            retained_source_id_loss_count > 0 or retained_identifier_loss_count > 0
        ),
        "likely_multisource_collapse_to_arxiv_only": bool(
            multisource_to_arxiv_only_count > 0
        ),
    }


def resolve_paths_from_delta_report(
    delta_report: Mapping[str, Any],
    *,
    canonical_path: Path | None,
    candidate_path: Path | None,
) -> tuple[Path, Path]:
    inputs = as_mapping(delta_report.get("inputs"))
    resolved_canonical = canonical_path or Path(
        str(inputs.get("canonical_path") or candidate_delta.DEFAULT_CANONICAL_PATH)
    )
    resolved_candidate = candidate_path or Path(str(inputs.get("candidate_path") or ""))
    if not str(resolved_candidate):
        raise SystemExit(
            "--candidate-path is required when no delta report with inputs.candidate_path "
            "is available"
        )
    return resolved_canonical, resolved_candidate


def build_report(
    *,
    canonical_path: Path,
    candidate_path: Path,
    reports_dir: Path,
    delta_report_path: Path | None,
    sample_limit: int,
) -> dict[str, Any]:
    baseline = candidate_delta.load_canonical_index(canonical_path)
    candidate = candidate_delta.load_canonical_index(candidate_path)
    baseline_rows = baseline["rows_by_id"]
    candidate_rows = candidate["rows_by_id"]

    baseline_ids = set(baseline_rows)
    candidate_ids = set(candidate_rows)
    added_ids = sorted(candidate_ids - baseline_ids)
    removed_ids = sorted(baseline_ids - candidate_ids)
    retained_ids = sorted(baseline_ids & candidate_ids)

    removed = diagnose_removed(
        baseline_rows,
        removed_ids,
        sample_limit=sample_limit,
    )
    added = diagnose_added(
        candidate_rows,
        added_ids,
        sample_limit=sample_limit,
    )
    retained = diagnose_retained(
        baseline_rows,
        candidate_rows,
        retained_ids,
        sample_limit=sample_limit,
    )
    signals = build_signals(removed=removed, retained=retained)
    delta_report = read_json(delta_report_path) if delta_report_path else {}

    return {
        "report_name": REPORT_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": utc_now_ts(),
        "status": "read_only_diagnostics",
        "read_only": True,
        "canonical_truth_mutated": False,
        "promotion_executed": False,
        "derived_layers_rebuilt": False,
        "inputs": {
            "canonical_path": normalize_path(canonical_path),
            "candidate_path": normalize_path(candidate_path),
            "delta_report_path": normalize_path(delta_report_path),
            "reports_dir": normalize_path(reports_dir),
            "sample_limit": sample_limit,
        },
        "delta_gate_context": {
            "exists": bool(delta_report),
            "failed_checks": as_mapping(delta_report.get("verdict")).get(
                "required_failed_checks", []
            ),
            "summary": as_mapping(delta_report.get("summary")),
        },
        "baseline": candidate_delta.public_summary(baseline),
        "candidate": candidate_delta.public_summary(candidate),
        "diagnostics": {
            "added": added,
            "removed": removed,
            "retained": retained,
            "source_family_totals": {
                "baseline": baseline["source_family_counts"],
                "candidate": candidate["source_family_counts"],
                "delta": {
                    family: candidate["source_family_counts"].get(family, 0)
                    - baseline["source_family_counts"].get(family, 0)
                    for family in sorted(
                        set(baseline["source_family_counts"])
                        | set(candidate["source_family_counts"])
                    )
                },
            },
            "signals": signals,
        },
        "summary": {
            "baseline_doc_count": baseline["doc_count"],
            "candidate_doc_count": candidate["doc_count"],
            "doc_count_delta": candidate["doc_count"] - baseline["doc_count"],
            "added_count": len(added_ids),
            "removed_count": len(removed_ids),
            "acl_only_removed_count": removed["acl_only_count"],
            "retained_count": len(retained_ids),
            "retained_source_family_changed_count": retained[
                "source_family_changed_count"
            ],
            "retained_multisource_to_single_source_count": retained[
                "multisource_to_single_source_count"
            ],
            "retained_multisource_to_arxiv_only_count": retained[
                "multisource_to_arxiv_only_count"
            ],
            "retained_identifier_loss_count": retained["identifier_loss"]["rows_count"],
            "retained_source_id_loss_count": retained["source_id_loss"]["rows_count"],
        },
        "verdict": {
            "diagnostics_ok": True,
            "manual_review_required": signals["source_coverage_regression_detected"],
            "promotion_safe": not signals["source_coverage_regression_detected"],
            "canonical_truth_mutation_required": False,
            "derived_layer_mutation_required": False,
        },
    }


def build_markdown(report: Mapping[str, Any]) -> str:
    lines: list[str] = [
        "# Refresh source coverage diagnostics v0.1",
        "",
        f"- Generated at: `{report['generated_at_utc']}`",
        f"- Run ts: `{report['run_ts']}`",
        f"- Read only: `{report['read_only']}`",
        "",
        "## Summary",
        "",
    ]

    for name, value in report["summary"].items():
        lines.append(f"- {name}: `{value}`")

    lines.extend(["", "## Delta Gate Context", ""])
    for name, value in report["delta_gate_context"].items():
        lines.append(f"- {name}: `{value}`")

    lines.extend(["", "## Signals", ""])
    for name, value in report["diagnostics"]["signals"].items():
        lines.append(f"- {name}: `{value}`")

    lines.extend(["", "## Removed Source Coverage", ""])
    removed = report["diagnostics"]["removed"]
    for name in (
        "count",
        "acl_only_count",
        "arxiv_only_count",
        "multisource_count",
        "with_doi_count",
    ):
        lines.append(f"- {name}: `{removed[name]}`")
    lines.append(f"- by_family_combo: `{removed['by_family_combo']}`")
    lines.append(f"- by_source_family: `{removed['by_source_family']}`")

    lines.extend(["", "## Retained Source Coverage", ""])
    retained = report["diagnostics"]["retained"]
    for name in (
        "source_family_changed_count",
        "unique_source_count_drop_count",
        "multisource_to_single_source_count",
        "multisource_to_arxiv_only_count",
    ):
        lines.append(f"- {name}: `{retained[name]}`")
    lines.append(
        "- source_family_transition_counts: "
        f"`{retained['source_family_transition_counts']}`"
    )
    lines.append(f"- lost_source_family_counts: `{retained['lost_source_family_counts']}`")
    lines.append(
        "- identifier_loss_by_field: "
        f"`{retained['identifier_loss']['by_field']}`"
    )
    lines.append(
        "- source_id_loss_by_source_family: "
        f"`{retained['source_id_loss']['by_source_family']}`"
    )

    lines.extend(["", "## Verdict", ""])
    for name, value in report["verdict"].items():
        lines.append(f"- {name}: `{value}`")

    lines.extend(["", "## Samples", ""])
    for sample_name, rows in (
        ("removed", removed["samples"]),
        ("source_family_changed", retained["source_family_changed_samples"]),
        ("identifier_loss", retained["identifier_loss"]["samples"]),
    ):
        lines.append(f"### {sample_name}")
        if not rows:
            lines.append("- none")
            lines.append("")
            continue
        for row in rows:
            lines.append(f"- `{row}`")
        lines.append("")

    return "\n".join(lines)


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
            "Explain source-family and identifier coverage regressions between "
            "current canonical latest and a refresh candidate."
        )
    )
    parser.add_argument(
        "--canonical-path",
        type=Path,
        default=None,
        help=(
            "Current stable canonical JSONL path. Defaults to the path stored in "
            "the latest candidate delta report, then to canonical_documents.jsonl."
        ),
    )
    parser.add_argument(
        "--candidate-path",
        type=Path,
        default=None,
        help=(
            "Refresh candidate JSONL path. Defaults to inputs.candidate_path from "
            "the latest candidate delta report."
        ),
    )
    parser.add_argument(
        "--delta-report-path",
        type=Path,
        default=DEFAULT_DELTA_REPORT_PATH,
        help="Latest candidate delta review JSON report.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Directory where validation reports are written.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="Maximum sample rows per report bucket.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    delta_report = read_json(args.delta_report_path)
    canonical_path, candidate_path = resolve_paths_from_delta_report(
        delta_report,
        canonical_path=args.canonical_path,
        candidate_path=args.candidate_path,
    )
    report = build_report(
        canonical_path=canonical_path,
        candidate_path=candidate_path,
        reports_dir=args.reports_dir,
        delta_report_path=args.delta_report_path,
        sample_limit=args.sample_limit,
    )
    latest_json, latest_md, hist_json, hist_md = write_reports(
        report,
        args.reports_dir,
    )

    print(f"[OK] report={REPORT_NAME}")
    print("[OK] read_only=True")
    for name, value in report["summary"].items():
        print(f"[OK] {name}={value}")
    for name, value in report["diagnostics"]["signals"].items():
        print(f"[OK] {name}={value}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()
