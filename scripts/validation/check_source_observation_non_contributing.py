from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row

from radar_core.contracts.document import NormalizedDocument
from radar_core.normalize.reconcile import (
    build_reconciliation_key,
    build_title_year_reconciliation_key,
    get_doc_arxiv_base_for_key,
    get_doc_doi_for_key,
    normalize_arxiv_base_for_key,
    normalize_doi_for_key,
    normalize_title_for_key,
)
from radar_core.utils.source_observation_identity import (
    build_source_observation_identity_from_mapping,
    normalize_source_name,
)
from scripts.validation.check_source_observation_identity_contract import (
    iter_jsonl_rows,
    normalize_path,
    resolve_selected_snapshots,
    ts_slug,
)


REPORT_NAME = "source_observation_non_contributing_classification_v01"
SCHEMA_VERSION = "source_observation_non_contributing_classification_v0.1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANONICAL_PATH = (
    PROJECT_ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
)
DEFAULT_NORMALIZED_ROOT = PROJECT_ROOT / "data" / "normalized"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "reports" / "validation"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "canonical_id": str(row.get("canonical_id") or ""),
        "reconciliation_key": row.get("reconciliation_key"),
        "title": row.get("title"),
        "year": row.get("year"),
        "doi": row.get("doi"),
        "arxiv_id": row.get("arxiv_id"),
        "source_count": row.get("source_count"),
        "unique_source_count": row.get("unique_source_count"),
    }


def _observation_summary(
    row: Mapping[str, Any],
    *,
    source_observation_id: str,
) -> dict[str, Any]:
    return {
        "source": normalize_source_name(row.get("source")),
        "source_observation_id": source_observation_id,
        "source_record_id": row.get("source_record_id"),
        "source_id": row.get("source_id"),
        "doc_id": row.get("doc_id"),
        "source_record_url": (
            str(row.get("source_record_url"))
            if row.get("source_record_url") is not None
            else None
        ),
        "canonical_url": (
            str(row.get("canonical_url"))
            if row.get("canonical_url") is not None
            else None
        ),
        "title": row.get("title"),
        "year": row.get("year"),
        "doi": row.get("doi"),
        "arxiv_id": row.get("arxiv_id"),
    }


def load_selected_observations(
    selected_snapshots: Mapping[str, Path],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    selected: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []

    for expected_source, path in selected_snapshots.items():
        for line_no, row in iter_jsonl_rows(path):
            try:
                document = NormalizedDocument(**row)
                identity = build_source_observation_identity_from_mapping(row)
                source = normalize_source_name(row.get("source"))
            except (TypeError, ValueError) as exc:
                errors.append(
                    {
                        "path": normalize_path(path),
                        "line_no": line_no,
                        "error": str(exc),
                        "source": row.get("source"),
                        "source_record_id": row.get("source_record_id"),
                        "doc_id": row.get("doc_id"),
                    }
                )
                continue

            if source != expected_source:
                errors.append(
                    {
                        "path": normalize_path(path),
                        "line_no": line_no,
                        "error": "selected snapshot source mismatch",
                        "expected_source": expected_source,
                        "actual_source": source,
                        "source_record_id": row.get("source_record_id"),
                    }
                )
                continue

            observation_id = identity.source_observation_id
            descriptor = {
                "row": row,
                "document": document,
                "summary": _observation_summary(
                    row,
                    source_observation_id=observation_id,
                ),
            }
            previous = selected.get(observation_id)
            if previous is not None and previous["summary"] != descriptor["summary"]:
                errors.append(
                    {
                        "error": "source_observation_id collision",
                        "source_observation_id": observation_id,
                        "first": previous["summary"],
                        "second": descriptor["summary"],
                    }
                )
                continue
            selected[observation_id] = descriptor

    return selected, errors


def _add_index(
    index: dict[str, list[dict[str, Any]]],
    key: str | None,
    canonical: dict[str, Any],
) -> None:
    if key:
        index[key].append(canonical)


def build_canonical_indexes(
    canonical_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    by_reconciliation_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_doi: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_arxiv_base: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_title_year: dict[str, list[dict[str, Any]]] = defaultdict(list)

    provenance_observation_ids: set[str] = set()
    provenance_errors: list[dict[str, Any]] = []
    canonical_count = 0

    for row in canonical_rows:
        canonical_count += 1
        canonical = _canonical_summary(row)
        canonical_id = canonical["canonical_id"]

        _add_index(
            by_reconciliation_key,
            str(row.get("reconciliation_key") or "").strip() or None,
            canonical,
        )
        _add_index(
            by_doi,
            normalize_doi_for_key(row.get("doi")),
            canonical,
        )
        _add_index(
            by_arxiv_base,
            normalize_arxiv_base_for_key(row.get("arxiv_id")),
            canonical,
        )

        normalized_title = normalize_title_for_key(str(row.get("title") or ""))
        year = row.get("year")
        if normalized_title:
            year_text = str(year) if year is not None else "unknown"
            _add_index(
                by_title_year,
                f"title_year::{normalized_title}::{year_text}",
                canonical,
            )

        sources = row.get("sources")
        if not isinstance(sources, list):
            continue

        for source_row in sources:
            if not isinstance(source_row, dict):
                provenance_errors.append(
                    {
                        "canonical_id": canonical_id,
                        "error": "canonical source row is not an object",
                    }
                )
                continue
            try:
                identity = build_source_observation_identity_from_mapping(source_row)
            except (TypeError, ValueError) as exc:
                provenance_errors.append(
                    {
                        "canonical_id": canonical_id,
                        "error": str(exc),
                        "source": source_row.get("source"),
                        "source_record_id": source_row.get("source_record_id"),
                    }
                )
                continue
            provenance_observation_ids.add(identity.source_observation_id)

    return {
        "canonical_count": canonical_count,
        "by_reconciliation_key": dict(by_reconciliation_key),
        "by_doi": dict(by_doi),
        "by_arxiv_base": dict(by_arxiv_base),
        "by_title_year": dict(by_title_year),
        "provenance_observation_ids": provenance_observation_ids,
        "provenance_errors": provenance_errors,
    }


def load_canonical_indexes(canonical_path: Path) -> dict[str, Any]:
    rows = (row for _, row in iter_jsonl_rows(canonical_path))
    return build_canonical_indexes(rows)


def _unique_matches(
    *groups: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for group in groups:
        for item in group:
            canonical_id = str(item.get("canonical_id") or "")
            if canonical_id:
                by_id[canonical_id] = dict(item)
    return [by_id[key] for key in sorted(by_id)]


def classify_observation(
    *,
    source_observation_id: str,
    document: NormalizedDocument,
    summary: Mapping[str, Any],
    canonical_indexes: Mapping[str, Any],
    db_observation_ids: set[str] | None,
) -> dict[str, Any]:
    reconciliation_key = build_reconciliation_key(document)
    doi = get_doc_doi_for_key(document)
    arxiv_base = get_doc_arxiv_base_for_key(document)
    title_year_key = build_title_year_reconciliation_key(document)

    exact_matches = list(
        canonical_indexes["by_reconciliation_key"].get(reconciliation_key, [])
    )
    doi_matches = list(canonical_indexes["by_doi"].get(doi, [])) if doi else []
    arxiv_matches = (
        list(canonical_indexes["by_arxiv_base"].get(arxiv_base, []))
        if arxiv_base
        else []
    )
    title_year_matches = list(
        canonical_indexes["by_title_year"].get(title_year_key, [])
    )

    strong_matches = _unique_matches(doi_matches, arxiv_matches)

    if len(exact_matches) == 1:
        classification = "same_reconciliation_key_not_contributing"
        matched = exact_matches
        match_basis = "reconciliation_key"
    elif len(exact_matches) > 1:
        classification = "ambiguous_reconciliation_key_match"
        matched = exact_matches
        match_basis = "reconciliation_key"
    elif len(strong_matches) == 1:
        classification = "strong_identity_match_not_contributing"
        matched = strong_matches
        if doi_matches and arxiv_matches:
            match_basis = "doi+arxiv"
        elif doi_matches:
            match_basis = "doi"
        else:
            match_basis = "arxiv"
    elif len(strong_matches) > 1:
        classification = "ambiguous_strong_identity_match"
        matched = strong_matches
        match_basis = "doi/arxiv"
    elif len(title_year_matches) == 1:
        classification = "title_year_match_not_contributing"
        matched = title_year_matches
        match_basis = "title_year"
    elif len(title_year_matches) > 1:
        classification = "ambiguous_title_year_match"
        matched = title_year_matches
        match_basis = "title_year"
    else:
        classification = "no_matching_promoted_canonical_identity"
        matched = []
        match_basis = None

    db_materialized = (
        None
        if db_observation_ids is None
        else source_observation_id in db_observation_ids
    )

    source = normalize_source_name(document.source)
    review_hint: str | None = None
    if source == "acl_anthology":
        if classification in {
            "strong_identity_match_not_contributing",
            "title_year_match_not_contributing",
            "ambiguous_strong_identity_match",
            "ambiguous_title_year_match",
        }:
            review_hint = "acl_filtered_candidate_identity_overlap_review"
        elif classification == "no_matching_promoted_canonical_identity":
            review_hint = "acl_not_present_in_promoted_canonical_identity_indexes"

    return {
        **dict(summary),
        "candidate_reconciliation_key": reconciliation_key,
        "candidate_identity": {
            "doi": doi,
            "arxiv_base": arxiv_base,
            "title_year_key": title_year_key,
        },
        "classification": classification,
        "match_basis": match_basis,
        "matched_canonical_count": len(matched),
        "matched_canonical": matched,
        "db_materialized": db_materialized,
        "review_hint": review_hint,
    }


def collect_db_observation_ids(
    *,
    db_config: Mapping[str, Any],
) -> tuple[set[str], list[dict[str, Any]]]:
    observation_ids: set[str] = set()
    errors: list[dict[str, Any]] = []

    with psycopg.connect(**dict(db_config), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    source, source_record_id, source_id, source_record_url,
                    source_api_url, doc_id, canonical_url, landing_page_url
                FROM source_documents
                ORDER BY source, doc_id
                """
            )
            for row in cur:
                try:
                    identity = build_source_observation_identity_from_mapping(row)
                except (TypeError, ValueError) as exc:
                    errors.append(
                        {
                            "error": str(exc),
                            "source": row.get("source"),
                            "source_record_id": row.get("source_record_id"),
                            "doc_id": row.get("doc_id"),
                        }
                    )
                    continue
                observation_ids.add(identity.source_observation_id)

    return observation_ids, errors


def build_report(
    *,
    selected_count: int,
    canonical_count: int,
    provenance_count: int,
    rows: list[dict[str, Any]],
    selected_errors: list[dict[str, Any]],
    provenance_errors: list[dict[str, Any]],
    db_errors: list[dict[str, Any]],
    selected_snapshots: Mapping[str, Path],
    canonical_path: Path,
    db_checked: bool,
    sample_limit: int,
) -> dict[str, Any]:
    classification_counts = Counter(str(row["classification"]) for row in rows)
    source_counts = Counter(str(row["source"]) for row in rows)
    db_presence_counts = Counter(
        "not_checked"
        if row["db_materialized"] is None
        else ("materialized" if row["db_materialized"] else "missing")
        for row in rows
    )
    classification_by_source: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        classification_by_source[str(row["source"])][
            str(row["classification"])
        ] += 1

    checks = {
        "selected_observations_non_empty": selected_count > 0,
        "canonical_documents_non_empty": canonical_count > 0,
        "no_selected_identity_or_contract_errors": not selected_errors,
        "no_canonical_provenance_identity_errors": not provenance_errors,
        "classification_count_matches_non_contributing_count": (
            len(rows) == selected_count - provenance_count
        ),
        "every_row_has_classification": all(
            bool(row.get("classification")) for row in rows
        ),
        "db_identity_errors_zero_when_checked": (
            not db_checked or not db_errors
        ),
    }
    failed = [name for name, ok in checks.items() if not ok]

    return {
        "report_name": REPORT_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "status": "internal_review_only",
        "publication_ready": False,
        "may_be_used_as_reconcile_input": False,
        "semantic_scholar_rows_private_diagnostic_only": True,
        "inputs": {
            "canonical_path": normalize_path(canonical_path),
            "selected_snapshots": {
                source: normalize_path(path)
                for source, path in selected_snapshots.items()
            },
            "db_checked": db_checked,
            "sample_limit": sample_limit,
        },
        "summary": {
            "selected_observation_count": selected_count,
            "canonical_document_count": canonical_count,
            "canonical_provenance_observation_count": provenance_count,
            "non_contributing_observation_count": len(rows),
            "classification_counts": dict(sorted(classification_counts.items())),
            "source_counts": dict(sorted(source_counts.items())),
            "db_presence_counts": dict(sorted(db_presence_counts.items())),
            "classification_by_source": {
                source: dict(sorted(counts.items()))
                for source, counts in sorted(classification_by_source.items())
            },
        },
        "checks": checks,
        "errors": {
            "selected": selected_errors[:sample_limit],
            "canonical_provenance": provenance_errors[:sample_limit],
            "db": db_errors[:sample_limit],
        },
        "samples": {
            "rows": rows[:sample_limit],
        },
        "verdict": {
            "ok": not failed,
            "required_failed_count": len(failed),
            "required_failed_checks": failed,
            "canonical_truth_mutation_required": False,
            "reconciliation_behavior_change_required": False,
            "classification_is_diagnostic_not_promotion_logic": True,
        },
    }


def write_outputs(
    *,
    report: Mapping[str, Any],
    rows: list[dict[str, Any]],
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    history_dir = output_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    run_ts = ts_slug()
    latest_json = (
        output_dir
        / "source_observation_non_contributing_classification_latest.json"
    )
    latest_jsonl = (
        output_dir
        / "source_observation_non_contributing_classification_latest.jsonl"
    )
    history_json = (
        history_dir
        / f"source_observation_non_contributing_classification_{run_ts}.json"
    )
    history_jsonl = (
        history_dir
        / f"source_observation_non_contributing_classification_{run_ts}.jsonl"
    )

    report_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    rows_text = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in rows
    )
    latest_json.write_text(report_text, encoding="utf-8")
    history_json.write_text(report_text, encoding="utf-8")
    latest_jsonl.write_text(rows_text, encoding="utf-8")
    history_jsonl.write_text(rows_text, encoding="utf-8")

    return {
        "latest_json": latest_json,
        "latest_jsonl": latest_jsonl,
        "history_json": history_json,
        "history_jsonl": history_jsonl,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Classify normalized source observations that are absent from "
            "promoted canonical provenance. The command is read-only."
        )
    )
    parser.add_argument(
        "--canonical-path",
        type=Path,
        default=DEFAULT_CANONICAL_PATH,
    )
    parser.add_argument(
        "--normalized-root",
        type=Path,
        default=DEFAULT_NORMALIZED_ROOT,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=15432)
    parser.add_argument("--dbname", default="ml_radar")
    parser.add_argument("--user", default="ml_radar")
    parser.add_argument("--password", default="ml_radar_dev")
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Skip the read-only source_documents presence check.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sample_limit = max(1, int(args.sample_limit))

    try:
        selected_snapshots = resolve_selected_snapshots(args.normalized_root)
        selected, selected_errors = load_selected_observations(selected_snapshots)
        canonical_indexes = load_canonical_indexes(args.canonical_path)

        db_observation_ids: set[str] | None = None
        db_errors: list[dict[str, Any]] = []
        if not args.skip_db:
            db_observation_ids, db_errors = collect_db_observation_ids(
                db_config={
                    "host": args.host,
                    "port": args.port,
                    "dbname": args.dbname,
                    "user": args.user,
                    "password": args.password,
                }
            )

        provenance_ids = set(canonical_indexes["provenance_observation_ids"])
        non_contributing_ids = sorted(set(selected) - provenance_ids)

        rows = [
            classify_observation(
                source_observation_id=observation_id,
                document=selected[observation_id]["document"],
                summary=selected[observation_id]["summary"],
                canonical_indexes=canonical_indexes,
                db_observation_ids=db_observation_ids,
            )
            for observation_id in non_contributing_ids
        ]

        report = build_report(
            selected_count=len(selected),
            canonical_count=int(canonical_indexes["canonical_count"]),
            provenance_count=len(provenance_ids),
            rows=rows,
            selected_errors=selected_errors,
            provenance_errors=list(canonical_indexes["provenance_errors"]),
            db_errors=db_errors,
            selected_snapshots=selected_snapshots,
            canonical_path=args.canonical_path,
            db_checked=not args.skip_db,
            sample_limit=sample_limit,
        )
        outputs = write_outputs(
            report=report,
            rows=rows,
            output_dir=args.output_dir,
        )
    except (
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1
    except psycopg.Error as exc:
        print(f"[FAILED] PostgreSQL error: {exc}")
        return 1

    status = "OK" if report["verdict"]["ok"] else "FAILED"
    summary = report["summary"]
    print(f"[{status}] report_name={REPORT_NAME}")
    print(
        f"[{status}] selected_observations="
        f"{summary['selected_observation_count']}"
    )
    print(
        f"[{status}] canonical_provenance_observations="
        f"{summary['canonical_provenance_observation_count']}"
    )
    print(
        f"[{status}] non_contributing_observations="
        f"{summary['non_contributing_observation_count']}"
    )
    print(f"[{status}] classification_counts={summary['classification_counts']}")
    print(f"[{status}] db_presence_counts={summary['db_presence_counts']}")
    print(
        f"[{status}] required_failed_count="
        f"{report['verdict']['required_failed_count']}"
    )
    print(f"[{status}] latest report: {outputs['latest_json']}")
    print(f"[{status}] latest rows: {outputs['latest_jsonl']}")

    if report["verdict"]["required_failed_checks"]:
        print("[FAILED] Required checks:")
        for name in report["verdict"]["required_failed_checks"]:
            print(f"- {name}")

    return 0 if report["verdict"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
