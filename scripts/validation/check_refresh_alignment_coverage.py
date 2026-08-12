from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from scripts.validation import check_refresh_candidate_delta as candidate_delta


REPORT_NAME = "refresh_alignment_coverage_diagnostics"
SCHEMA_VERSION = "refresh_alignment_coverage_diagnostics_v0.1"

DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_DELTA_REPORT_PATH = (
    Path("artifacts/reports/validation") / "refresh_candidate_delta_review_latest.json"
)
DEFAULT_UPDATE_DIR = Path("artifacts/reports/update")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/validation")

ALIGNMENT_SOURCES = (
    "openalex_alignment",
    "semantic_scholar_alignment",
    "crossref_alignment",
)

DEFAULT_MERGE_REPORTS = {
    "openalex_alignment": DEFAULT_UPDATE_DIR / "merge_openalex_alignment_latest.json",
    "semantic_scholar_alignment": (
        DEFAULT_UPDATE_DIR / "merge_semantic_scholar_alignment_latest.json"
    ),
    "crossref_alignment": DEFAULT_UPDATE_DIR / "merge_crossref_alignment_latest.json",
}

SOURCE_ALIASES = {
    "openalex": "openalex_alignment",
    "openalex_alignment": "openalex_alignment",
    "semantic_scholar": "semantic_scholar_alignment",
    "semanticscholar": "semantic_scholar_alignment",
    "s2": "semantic_scholar_alignment",
    "semantic_scholar_alignment": "semantic_scholar_alignment",
    "crossref": "crossref_alignment",
    "crossref_alignment": "crossref_alignment",
    "arxiv": "arxiv",
    "arxiv_id": "arxiv",
    "acl": "acl_anthology",
    "acl_anthology": "acl_anthology",
}

FAMILY_ID_FIELDS = {
    "openalex_alignment": ("openalex_id", "openalex", "openalex_alignment"),
    "semantic_scholar_alignment": (
        "semantic_scholar_id",
        "semantic_scholar",
        "semantic_scholar_alignment",
        "semanticscholar",
        "s2",
    ),
    "crossref_alignment": ("crossref", "crossref_alignment", "doi"),
}

DOI_PREFIX_RE = re.compile(r"^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)", re.I)
ARXIV_PREFIX_RE = re.compile(r"^(?:arxiv:|https?://arxiv\.org/(?:abs|pdf)/)", re.I)
ARXIV_VERSION_RE = re.compile(r"v\d+$", re.I)


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


def read_json(path: Path | None) -> Mapping[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping):
        return payload
    return {}


def safe_int(value: Any, default: int = 0) -> int:
    return candidate_delta.safe_int(value, default=default)


def normalize_family(value: Any) -> str | None:
    text = str(value or "").strip().lower().replace("-", "_")
    if not text:
        return None
    return SOURCE_ALIASES.get(text, text)


def canonical_families(row: Mapping[str, Any]) -> set[str]:
    return {
        family
        for family in (
            normalize_family(value) for value in candidate_delta.source_families(row)
        )
        if family
    }


def normalize_doi(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = DOI_PREFIX_RE.sub("", text).strip().rstrip(".")
    if not text:
        return None
    return text.lower()


def normalize_arxiv_base(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = ARXIV_PREFIX_RE.sub("", text).strip()
    text = text.removesuffix(".pdf")
    text = text.split("?")[0].split("#")[0].strip()
    if not text:
        return None
    return ARXIV_VERSION_RE.sub("", text).lower()


def add_key(keys: set[str], prefix: str, value: str | None) -> None:
    if value:
        keys.add(f"{prefix}::{value}")


def iter_source_entries(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    entries = row.get("sources")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, Mapping)]


def mapping_values_for_keys(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> list[Any]:
    values: list[Any] = []
    wanted = {key.lower() for key in keys}
    for key, value in mapping.items():
        key_text = str(key).strip().lower()
        if key_text in wanted:
            values.append(value)
    return values


def row_match_keys(row: Mapping[str, Any], family: str | None = None) -> set[str]:
    keys: set[str] = set()
    external_ids = as_mapping(row.get("external_ids"))
    source_ids = as_mapping(row.get("source_ids"))

    for value in (
        row.get("doi"),
        *mapping_values_for_keys(external_ids, ("doi", "DOI")),
        *mapping_values_for_keys(source_ids, ("doi", "DOI")),
    ):
        add_key(keys, "doi", normalize_doi(value))

    for value in (
        row.get("arxiv_id"),
        *mapping_values_for_keys(external_ids, ("arxiv", "arxiv_id")),
        *mapping_values_for_keys(source_ids, ("arxiv", "arxiv_id")),
    ):
        add_key(keys, "arxiv", normalize_arxiv_base(value))

    family_fields = FAMILY_ID_FIELDS.get(family or "", ())
    for value in mapping_values_for_keys(source_ids, family_fields):
        value_text = str(value or "").strip()
        if value_text:
            add_key(keys, "source_id", value_text.casefold())

    for field in family_fields:
        value = row.get(field)
        value_text = str(value or "").strip()
        if value_text:
            add_key(keys, "source_id", value_text.casefold())

    for field in ("source_id", "source_record_id", "doc_id", "id"):
        value = row.get(field)
        value_text = str(value or "").strip()
        if value_text:
            add_key(keys, "source_id", value_text.casefold())

    for entry in iter_source_entries(row):
        entry_family = normalize_family(
            entry.get("source") or entry.get("source_name") or entry.get("raw_source_name")
        )
        if family and entry_family != family:
            continue
        for field in ("source_id", "source_record_id", "doc_id", "id"):
            value = entry.get(field)
            value_text = str(value or "").strip()
            if value_text:
                add_key(keys, "source_id", value_text.casefold())

    return keys


def bridge_keys(keys: set[str]) -> set[str]:
    return {key for key in keys if key.startswith("doi::") or key.startswith("arxiv::")}


def parse_merge_report_arg(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise ValueError(
            "Invalid --merge-report value. Expected source_name=path/to/report.json"
        )
    source_name, raw_path = raw.split("=", 1)
    source_name = source_name.strip()
    raw_path = raw_path.strip()
    if not source_name or not raw_path:
        raise ValueError(
            "Invalid --merge-report value. Expected source_name=path/to/report.json"
        )
    return source_name, Path(raw_path)


def resolve_merge_report_specs(
    update_dir: Path,
    cli_values: list[str] | None,
) -> dict[str, Path]:
    if cli_values:
        return dict(parse_merge_report_arg(item) for item in cli_values)
    return {
        source_name: update_dir / report_path.name
        for source_name, report_path in DEFAULT_MERGE_REPORTS.items()
    }


def resolved_snapshot_from_report(report_path: Path) -> Path | None:
    report = read_json(report_path)
    raw = (
        as_mapping(report.get("output")).get("merged_snapshot")
        or as_mapping(report.get("outputs")).get("merged_snapshot")
        or report.get("merged_snapshot")
    )
    if not raw:
        return None
    return Path(str(raw))


def load_snapshot_index(path: Path | None, family: str) -> dict[str, Any]:
    rows_count = 0
    bad_json_count = 0
    non_object_count = 0
    key_to_row: dict[str, dict[str, Any]] = {}
    key_prefix_counts: Counter[str] = Counter()

    if path is None or not path.exists():
        return {
            "path": normalize_path(path),
            "exists": False,
            "rows_count": 0,
            "bad_json_count": 0,
            "non_object_count": 0,
            "key_to_row": key_to_row,
            "key_count": 0,
            "key_prefix_counts": {},
        }

    with path.open("r", encoding="utf-8") as f:
        for line in f:
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
            for key in row_match_keys(row, family):
                key_to_row.setdefault(key, row)
                key_prefix_counts[key.split("::", 1)[0]] += 1

    return {
        "path": normalize_path(path),
        "exists": True,
        "rows_count": rows_count,
        "bad_json_count": bad_json_count,
        "non_object_count": non_object_count,
        "key_to_row": key_to_row,
        "key_count": len(key_to_row),
        "key_prefix_counts": dict(sorted(key_prefix_counts.items())),
    }


def public_snapshot_summary(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": snapshot.get("path"),
        "exists": snapshot.get("exists"),
        "rows_count": snapshot.get("rows_count"),
        "bad_json_count": snapshot.get("bad_json_count"),
        "non_object_count": snapshot.get("non_object_count"),
        "key_count": snapshot.get("key_count"),
        "key_prefix_counts": snapshot.get("key_prefix_counts"),
    }


def compact_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "canonical_id": row.get("canonical_id"),
        "title": row.get("title"),
        "doi": row.get("doi"),
        "arxiv_id": row.get("arxiv_id"),
        "openalex_id": row.get("openalex_id"),
        "semantic_scholar_id": row.get("semantic_scholar_id"),
        "source_ids": as_mapping(row.get("source_ids")),
        "source_families": sorted(canonical_families(row)),
        "unique_source_count": row.get("unique_source_count", row.get("source_count")),
    }


def classify_lost_source(
    *,
    baseline_row: Mapping[str, Any],
    candidate_row: Mapping[str, Any],
    family: str,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    baseline_keys = row_match_keys(baseline_row, family)
    candidate_keys = row_match_keys(candidate_row, family)
    snapshot_keys = set(as_mapping(snapshot.get("key_to_row")).keys())
    matching_keys = sorted(baseline_keys & snapshot_keys)

    if not baseline_keys:
        classification = "no_baseline_match_keys"
        matched_snapshot_keys: list[str] = []
        shared_bridge_keys: list[str] = []
    elif not matching_keys:
        classification = "missing_from_merged_snapshot"
        matched_snapshot_keys = []
        shared_bridge_keys = []
    else:
        matched_snapshot_keys = matching_keys
        snapshot_row = as_mapping(snapshot["key_to_row"][matching_keys[0]])
        snapshot_row_keys = row_match_keys(snapshot_row, family)
        shared_bridge = bridge_keys(snapshot_row_keys) & bridge_keys(candidate_keys)
        shared_bridge_keys = sorted(shared_bridge)
        if shared_bridge:
            classification = "present_with_reconcile_bridge_keys"
        else:
            classification = "present_without_reconcile_bridge_keys"

    return {
        "family": family,
        "classification": classification,
        "baseline_key_count": len(baseline_keys),
        "candidate_bridge_keys": sorted(bridge_keys(candidate_keys)),
        "matched_snapshot_keys": matched_snapshot_keys[:10],
        "shared_bridge_keys": shared_bridge_keys[:10],
    }


def build_loss_diagnostics(
    *,
    baseline_rows: Mapping[str, Mapping[str, Any]],
    candidate_rows: Mapping[str, Mapping[str, Any]],
    snapshot_indexes: Mapping[str, Mapping[str, Any]],
    sample_limit: int,
) -> dict[str, Any]:
    retained_ids = sorted(set(baseline_rows) & set(candidate_rows))
    lost_docs_count = 0
    lost_observation_count = 0
    lost_by_family: Counter[str] = Counter()
    classification_counts: Counter[str] = Counter()
    classification_by_family: dict[str, Counter[str]] = {
        family: Counter() for family in ALIGNMENT_SOURCES
    }
    samples: list[dict[str, Any]] = []

    for canonical_id in retained_ids:
        baseline_row = baseline_rows[canonical_id]
        candidate_row = candidate_rows[canonical_id]
        baseline_families = canonical_families(baseline_row)
        candidate_families = canonical_families(candidate_row)
        lost_families = sorted(
            (baseline_families - candidate_families) & set(ALIGNMENT_SOURCES)
        )
        if not lost_families:
            continue

        lost_docs_count += 1
        source_results: list[dict[str, Any]] = []
        for family in lost_families:
            snapshot = snapshot_indexes.get(family, {})
            result = classify_lost_source(
                baseline_row=baseline_row,
                candidate_row=candidate_row,
                family=family,
                snapshot=snapshot,
            )
            source_results.append(result)
            lost_observation_count += 1
            lost_by_family[family] += 1
            classification_counts[result["classification"]] += 1
            classification_by_family[family][result["classification"]] += 1

        if len(samples) < sample_limit:
            samples.append(
                {
                    "canonical_id": canonical_id,
                    "baseline": compact_row(baseline_row),
                    "candidate": compact_row(candidate_row),
                    "lost_families": lost_families,
                    "source_results": source_results,
                }
            )

    return {
        "retained_alignment_source_loss_docs_count": lost_docs_count,
        "lost_alignment_source_observation_count": lost_observation_count,
        "lost_by_family": dict(sorted(lost_by_family.items())),
        "classification_counts": dict(sorted(classification_counts.items())),
        "classification_by_family": {
            family: dict(sorted(counts.items()))
            for family, counts in classification_by_family.items()
        },
        "samples": samples,
    }


def build_signals(losses: Mapping[str, Any]) -> dict[str, Any]:
    total = safe_int(losses.get("lost_alignment_source_observation_count"))
    classifications = as_mapping(losses.get("classification_counts"))
    missing = safe_int(classifications.get("missing_from_merged_snapshot"))
    present_without_bridge = safe_int(
        classifications.get("present_without_reconcile_bridge_keys")
    )
    present_with_bridge = safe_int(
        classifications.get("present_with_reconcile_bridge_keys")
    )

    return {
        "alignment_coverage_regression_detected": total > 0,
        "likely_merged_snapshots_missing_baseline_coverage": bool(
            total > 0 and missing / max(total, 1) >= 0.5
        ),
        "likely_alignment_rows_present_but_unjoinable": bool(present_without_bridge > 0),
        "likely_reconcile_or_identifier_semantics_issue": bool(present_with_bridge > 0),
    }


def resolve_paths_from_delta_report(
    delta_report: Mapping[str, Any],
    *,
    canonical_path: Path | None,
    candidate_path: Path | None,
) -> tuple[Path, Path]:
    inputs = as_mapping(delta_report.get("inputs"))
    resolved_canonical = canonical_path or Path(
        str(inputs.get("canonical_path") or DEFAULT_CANONICAL_PATH)
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
    merge_report_specs: Mapping[str, Path],
    reports_dir: Path,
    delta_report_path: Path | None,
    sample_limit: int,
) -> dict[str, Any]:
    baseline = candidate_delta.load_canonical_index(canonical_path)
    candidate = candidate_delta.load_canonical_index(candidate_path)

    snapshot_indexes: dict[str, dict[str, Any]] = {}
    merge_reports_used: list[dict[str, Any]] = []
    for family, report_path in merge_report_specs.items():
        normalized_family = normalize_family(family) or str(family)
        if normalized_family not in ALIGNMENT_SOURCES:
            continue
        snapshot_path = resolved_snapshot_from_report(report_path)
        snapshot = load_snapshot_index(snapshot_path, normalized_family)
        snapshot_indexes[normalized_family] = snapshot
        merge_reports_used.append(
            {
                "source_name": normalized_family,
                "report_path": normalize_path(report_path),
                "report_exists": report_path.exists(),
                "merged_snapshot": normalize_path(snapshot_path),
                "merged_snapshot_exists": snapshot["exists"],
                "merged_snapshot_rows_count": snapshot["rows_count"],
                "merged_snapshot_bad_json_count": snapshot["bad_json_count"],
                "merged_snapshot_key_count": snapshot["key_count"],
            }
        )

    losses = build_loss_diagnostics(
        baseline_rows=baseline["rows_by_id"],
        candidate_rows=candidate["rows_by_id"],
        snapshot_indexes=snapshot_indexes,
        sample_limit=sample_limit,
    )
    signals = build_signals(losses)
    delta_report = read_json(delta_report_path)

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
        "merge_reports_used": merge_reports_used,
        "snapshot_summaries": {
            family: public_snapshot_summary(snapshot)
            for family, snapshot in sorted(snapshot_indexes.items())
        },
        "diagnostics": {
            "retained_alignment_losses": losses,
            "signals": signals,
        },
        "summary": {
            "baseline_doc_count": baseline["doc_count"],
            "candidate_doc_count": candidate["doc_count"],
            "retained_alignment_source_loss_docs_count": losses[
                "retained_alignment_source_loss_docs_count"
            ],
            "lost_alignment_source_observation_count": losses[
                "lost_alignment_source_observation_count"
            ],
            "missing_from_merged_snapshot_count": safe_int(
                losses["classification_counts"].get("missing_from_merged_snapshot")
            ),
            "present_without_reconcile_bridge_keys_count": safe_int(
                losses["classification_counts"].get(
                    "present_without_reconcile_bridge_keys"
                )
            ),
            "present_with_reconcile_bridge_keys_count": safe_int(
                losses["classification_counts"].get(
                    "present_with_reconcile_bridge_keys"
                )
            ),
        },
        "verdict": {
            "diagnostics_ok": True,
            "manual_review_required": signals["alignment_coverage_regression_detected"],
            "promotion_safe": not signals["alignment_coverage_regression_detected"],
            "canonical_truth_mutation_required": False,
            "derived_layer_mutation_required": False,
        },
    }


def build_markdown(report: Mapping[str, Any]) -> str:
    lines: list[str] = [
        "# Refresh alignment coverage diagnostics v0.1",
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

    lines.extend(["", "## Signals", ""])
    for name, value in report["diagnostics"]["signals"].items():
        lines.append(f"- {name}: `{value}`")

    lines.extend(["", "## Merge Reports Used", ""])
    for row in report["merge_reports_used"]:
        lines.append(f"- `{row}`")

    lines.extend(["", "## Snapshot Summaries", ""])
    for family, snapshot in report["snapshot_summaries"].items():
        lines.append(f"- {family}: `{snapshot}`")

    losses = report["diagnostics"]["retained_alignment_losses"]
    lines.extend(["", "## Retained Alignment Losses", ""])
    for name in (
        "retained_alignment_source_loss_docs_count",
        "lost_alignment_source_observation_count",
        "lost_by_family",
        "classification_counts",
        "classification_by_family",
    ):
        lines.append(f"- {name}: `{losses[name]}`")

    lines.extend(["", "## Verdict", ""])
    for name, value in report["verdict"].items():
        lines.append(f"- {name}: `{value}`")

    lines.extend(["", "## Samples", ""])
    samples = losses["samples"]
    if not samples:
        lines.append("- none")
    else:
        for row in samples:
            lines.append(f"- `{row}`")

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
            "Trace retained multi-source coverage losses against the merged "
            "OpenAlex/Semantic Scholar/Crossref snapshots used by refresh rehearsal."
        )
    )
    parser.add_argument("--canonical-path", type=Path, default=None)
    parser.add_argument("--candidate-path", type=Path, default=None)
    parser.add_argument(
        "--delta-report-path",
        type=Path,
        default=DEFAULT_DELTA_REPORT_PATH,
        help="Latest candidate delta review JSON report.",
    )
    parser.add_argument(
        "--update-dir",
        type=Path,
        default=DEFAULT_UPDATE_DIR,
        help="Directory containing latest alignment merge reports.",
    )
    parser.add_argument(
        "--merge-report",
        action="append",
        default=None,
        help=(
            "Alignment merge report in source_name=path/to/report.json format. "
            "Can be repeated. Defaults to latest OpenAlex/Semantic Scholar/Crossref reports."
        ),
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Directory where validation reports are written.",
    )
    parser.add_argument("--sample-limit", type=int, default=10)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    delta_report = read_json(args.delta_report_path)
    canonical_path, candidate_path = resolve_paths_from_delta_report(
        delta_report,
        canonical_path=args.canonical_path,
        candidate_path=args.candidate_path,
    )
    merge_report_specs = resolve_merge_report_specs(
        update_dir=args.update_dir,
        cli_values=args.merge_report,
    )
    report = build_report(
        canonical_path=canonical_path,
        candidate_path=candidate_path,
        merge_report_specs=merge_report_specs,
        reports_dir=args.reports_dir,
        delta_report_path=args.delta_report_path,
        sample_limit=max(0, int(args.sample_limit)),
    )
    latest_json, latest_md, hist_json, hist_md = write_reports(report, args.reports_dir)

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
