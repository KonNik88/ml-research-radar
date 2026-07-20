from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row

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


REPORT_NAME = "source_observation_materialization_parity_v01"
SCHEMA_VERSION = "source_observation_materialization_parity_v0.1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANONICAL_PATH = (
    PROJECT_ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
)
DEFAULT_NORMALIZED_ROOT = PROJECT_ROOT / "data" / "normalized"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "reports" / "validation"

IDENTITY_FIELDS = (
    "source",
    "source_record_id",
    "source_id",
    "source_record_url",
    "source_api_url",
    "doc_id",
    "canonical_url",
    "landing_page_url",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sample_append(
    samples: dict[str, list[dict[str, Any]]],
    key: str,
    payload: dict[str, Any],
    *,
    sample_limit: int,
) -> None:
    if len(samples[key]) < sample_limit:
        samples[key].append(payload)


def _observation_summary(
    row: Mapping[str, Any],
    *,
    source_observation_id: str | None = None,
    canonical_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "source": row.get("source"),
        "source_observation_id": source_observation_id,
        "source_record_id": row.get("source_record_id"),
        "source_id": row.get("source_id"),
        "doc_id": row.get("doc_id"),
        "source_record_url": row.get("source_record_url"),
        "canonical_url": row.get("canonical_url"),
    }
    if canonical_id is not None:
        payload["canonical_id"] = canonical_id
    return payload


def _build_identity(row: Mapping[str, Any]) -> tuple[str, str]:
    identity = build_source_observation_identity_from_mapping(row)
    return normalize_source_name(row.get("source")), identity.source_observation_id


def collect_file_evidence(
    *,
    selected_snapshots: Mapping[str, Path],
    canonical_path: Path,
    sample_limit: int = 20,
) -> dict[str, Any]:
    """Collect read-only file evidence for source observations and canonical provenance."""

    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    selected_by_id: dict[str, dict[str, Any]] = {}
    selected_source_counts: Counter[str] = Counter()
    selected_identity_conflicts = 0
    selected_identity_errors = 0
    selected_duplicate_rows = 0

    for expected_source, snapshot_path in selected_snapshots.items():
        for line_no, row in iter_jsonl_rows(snapshot_path):
            try:
                source, observation_id = _build_identity(row)
            except (TypeError, ValueError) as exc:
                selected_identity_errors += 1
                _sample_append(
                    samples,
                    "selected_identity_errors",
                    {
                        "path": normalize_path(snapshot_path),
                        "line_no": line_no,
                        "error": str(exc),
                        **_observation_summary(row),
                    },
                    sample_limit=sample_limit,
                )
                continue

            if source != expected_source:
                _sample_append(
                    samples,
                    "selected_source_mismatches",
                    {
                        "path": normalize_path(snapshot_path),
                        "line_no": line_no,
                        "expected_source": expected_source,
                        "actual_source": source,
                        **_observation_summary(row, source_observation_id=observation_id),
                    },
                    sample_limit=sample_limit,
                )

            selected_source_counts[source] += 1
            compact = _observation_summary(row, source_observation_id=observation_id)
            previous = selected_by_id.get(observation_id)
            if previous is None:
                selected_by_id[observation_id] = compact
            elif previous == compact:
                selected_duplicate_rows += 1
                _sample_append(
                    samples,
                    "selected_duplicate_observation_rows",
                    compact,
                    sample_limit=sample_limit,
                )
            else:
                selected_identity_conflicts += 1
                _sample_append(
                    samples,
                    "selected_identity_conflicts",
                    {
                        "source_observation_id": observation_id,
                        "first": previous,
                        "second": compact,
                    },
                    sample_limit=sample_limit,
                )

    canonical_count = 0
    canonical_source_row_count = 0
    canonical_source_counts: Counter[str] = Counter()
    canonical_identity_errors = 0
    canonical_duplicate_pairs = 0
    provenance_pairs: set[tuple[str, str]] = set()
    provenance_observation_ids: set[str] = set()
    provenance_rows_by_id: dict[str, dict[str, Any]] = {}

    for _, canonical in iter_jsonl_rows(canonical_path):
        canonical_count += 1
        canonical_id = str(canonical.get("canonical_id") or "").strip()
        sources = canonical.get("sources")
        if not isinstance(sources, list):
            continue

        for source_row in sources:
            canonical_source_row_count += 1
            if not isinstance(source_row, dict):
                canonical_identity_errors += 1
                _sample_append(
                    samples,
                    "canonical_source_row_errors",
                    {
                        "canonical_id": canonical_id,
                        "error": "source provenance row is not an object",
                        "value_type": type(source_row).__name__,
                    },
                    sample_limit=sample_limit,
                )
                continue

            try:
                source, observation_id = _build_identity(source_row)
            except (TypeError, ValueError) as exc:
                canonical_identity_errors += 1
                _sample_append(
                    samples,
                    "canonical_identity_errors",
                    {
                        "canonical_id": canonical_id,
                        "error": str(exc),
                        **_observation_summary(source_row),
                    },
                    sample_limit=sample_limit,
                )
                continue

            canonical_source_counts[source] += 1
            pair = (canonical_id, observation_id)
            if pair in provenance_pairs:
                canonical_duplicate_pairs += 1
                _sample_append(
                    samples,
                    "canonical_duplicate_pairs",
                    _observation_summary(
                        source_row,
                        source_observation_id=observation_id,
                        canonical_id=canonical_id,
                    ),
                    sample_limit=sample_limit,
                )
            provenance_pairs.add(pair)
            provenance_observation_ids.add(observation_id)
            provenance_rows_by_id.setdefault(
                observation_id,
                _observation_summary(
                    source_row,
                    source_observation_id=observation_id,
                    canonical_id=canonical_id,
                ),
            )

    selected_ids = set(selected_by_id)
    non_contributing_ids = selected_ids - provenance_observation_ids
    provenance_missing_from_selected = provenance_observation_ids - selected_ids
    non_contributing_source_counts: Counter[str] = Counter()

    for observation_id in sorted(non_contributing_ids):
        row = selected_by_id[observation_id]
        source = str(row.get("source") or "unknown")
        non_contributing_source_counts[source] += 1
        _sample_append(
            samples,
            "non_contributing_observations",
            {
                **row,
                "classification": "not_in_promoted_canonical_provenance",
                "classification_status": "coarse_deterministic_classification",
            },
            sample_limit=sample_limit,
        )

    for observation_id in sorted(provenance_missing_from_selected):
        _sample_append(
            samples,
            "canonical_provenance_missing_from_selected_snapshots",
            provenance_rows_by_id.get(
                observation_id,
                {"source_observation_id": observation_id},
            ),
            sample_limit=sample_limit,
        )

    return {
        "inputs": {
            "canonical_path": normalize_path(canonical_path),
            "selected_snapshots": {
                source: normalize_path(path)
                for source, path in selected_snapshots.items()
            },
        },
        "summary": {
            "selected_observation_row_count": sum(selected_source_counts.values()),
            "selected_observation_unique_count": len(selected_by_id),
            "selected_observation_duplicate_row_count": selected_duplicate_rows,
            "selected_identity_error_count": selected_identity_errors,
            "selected_identity_conflict_count": selected_identity_conflicts,
            "selected_source_counts": dict(sorted(selected_source_counts.items())),
            "canonical_document_count": canonical_count,
            "canonical_source_row_count": canonical_source_row_count,
            "canonical_provenance_pair_count": len(provenance_pairs),
            "canonical_provenance_observation_count": len(provenance_observation_ids),
            "canonical_duplicate_pair_count": canonical_duplicate_pairs,
            "canonical_identity_error_count": canonical_identity_errors,
            "canonical_source_counts": dict(sorted(canonical_source_counts.items())),
            "non_contributing_observation_count": len(non_contributing_ids),
            "non_contributing_source_counts": dict(
                sorted(non_contributing_source_counts.items())
            ),
            "canonical_provenance_missing_from_selected_count": len(
                provenance_missing_from_selected
            ),
        },
        "selected_observation_ids": selected_ids,
        "selected_observations_by_id": selected_by_id,
        "canonical_provenance_pairs": provenance_pairs,
        "canonical_provenance_observation_ids": provenance_observation_ids,
        "samples": dict(samples),
    }


def _table_columns(cur: psycopg.Cursor[Any], table_name: str) -> list[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table_name,),
    )
    return [str(row["column_name"]) for row in cur.fetchall()]


def _count_by_source(cur: psycopg.Cursor[Any], table_name: str) -> dict[str, int]:
    cur.execute(
        f"SELECT source, COUNT(*) AS total FROM {table_name} GROUP BY source ORDER BY source"
    )
    return {str(row["source"]): int(row["total"]) for row in cur.fetchall()}


def collect_db_evidence(
    *,
    db_config: Mapping[str, Any],
    selected_observation_ids: set[str],
    selected_observations_by_id: Mapping[str, Mapping[str, Any]],
    canonical_provenance_pairs: set[tuple[str, str]],
    sample_limit: int = 20,
) -> dict[str, Any]:
    """Read current PostgreSQL materialization without mutating it."""

    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    db_observation_ids: set[str] = set()
    db_observation_source_counts: Counter[str] = Counter()
    db_identity_errors = 0
    db_duplicate_observation_ids = 0
    db_observation_descriptors: dict[str, dict[str, Any]] = {}

    link_pairs: set[tuple[str, str]] = set()
    link_observation_ids: set[str] = set()
    link_identity_errors = 0
    link_duplicate_pairs = 0

    with psycopg.connect(**dict(db_config), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            db_ping = bool(cur.fetchone()["ok"])

            source_columns = _table_columns(cur, "source_documents")
            link_columns = _table_columns(cur, "canonical_source_links")

            cur.execute("SELECT COUNT(*) AS total FROM source_documents")
            source_documents_count = int(cur.fetchone()["total"])
            source_documents_by_source = _count_by_source(cur, "source_documents")

            cur.execute("SELECT COUNT(*) AS total FROM canonical_source_links")
            canonical_source_links_count = int(cur.fetchone()["total"])

            cur.execute(
                """
                SELECT
                    source,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE doc_id IS NOT NULL) AS resolved,
                    COUNT(*) FILTER (WHERE doc_id IS NULL) AS unresolved
                FROM canonical_source_links
                GROUP BY source
                ORDER BY source
                """
            )
            links_by_source = {
                str(row["source"]): {
                    "total": int(row["total"]),
                    "resolved": int(row["resolved"]),
                    "unresolved": int(row["unresolved"]),
                }
                for row in cur.fetchall()
            }

            cur.execute(
                "SELECT COUNT(*) AS total FROM canonical_source_links WHERE doc_id IS NULL"
            )
            null_link_count = int(cur.fetchone()["total"])

            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM canonical_source_links csl
                LEFT JOIN source_documents sd ON sd.doc_id = csl.doc_id
                WHERE csl.doc_id IS NOT NULL
                  AND sd.doc_id IS NULL
                """
            )
            dangling_non_null_link_count = int(cur.fetchone()["total"])

            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM canonical_source_links csl
                JOIN source_documents sd ON sd.doc_id = csl.doc_id
                WHERE csl.source IS DISTINCT FROM sd.source
                """
            )
            joined_source_mismatch_count = int(cur.fetchone()["total"])

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
                    source, observation_id = _build_identity(row)
                except (TypeError, ValueError) as exc:
                    db_identity_errors += 1
                    _sample_append(
                        samples,
                        "db_source_identity_errors",
                        {"error": str(exc), **_observation_summary(row)},
                        sample_limit=sample_limit,
                    )
                    continue

                compact = _observation_summary(
                    row,
                    source_observation_id=observation_id,
                )
                previous = db_observation_descriptors.get(observation_id)
                if previous is not None:
                    db_duplicate_observation_ids += 1
                    _sample_append(
                        samples,
                        "db_duplicate_observation_ids",
                        {"first": previous, "second": compact},
                        sample_limit=sample_limit,
                    )
                else:
                    db_observation_descriptors[observation_id] = compact
                db_observation_ids.add(observation_id)
                db_observation_source_counts[source] += 1

            cur.execute(
                """
                SELECT
                    canonical_id, doc_id, source, source_id, source_record_id,
                    source_record_url, source_api_url, canonical_url
                FROM canonical_source_links
                ORDER BY canonical_id, id
                """
            )
            for row in cur:
                try:
                    _, observation_id = _build_identity(row)
                except (TypeError, ValueError) as exc:
                    link_identity_errors += 1
                    _sample_append(
                        samples,
                        "db_link_identity_errors",
                        {
                            "error": str(exc),
                            **_observation_summary(
                                row,
                                canonical_id=str(row.get("canonical_id") or ""),
                            ),
                        },
                        sample_limit=sample_limit,
                    )
                    continue

                canonical_id = str(row.get("canonical_id") or "")
                pair = (canonical_id, observation_id)
                if pair in link_pairs:
                    link_duplicate_pairs += 1
                    _sample_append(
                        samples,
                        "db_duplicate_link_pairs",
                        _observation_summary(
                            row,
                            source_observation_id=observation_id,
                            canonical_id=canonical_id,
                        ),
                        sample_limit=sample_limit,
                    )
                link_pairs.add(pair)
                link_observation_ids.add(observation_id)

    missing_db_observation_ids = selected_observation_ids - db_observation_ids
    unexpected_db_observation_ids = db_observation_ids - selected_observation_ids
    canonical_pairs_missing_from_db = canonical_provenance_pairs - link_pairs
    db_pairs_missing_from_canonical = link_pairs - canonical_provenance_pairs

    missing_db_by_source: Counter[str] = Counter()
    for observation_id in sorted(missing_db_observation_ids):
        source_row = selected_observations_by_id.get(observation_id, {})
        source = str(source_row.get("source") or "unknown")
        missing_db_by_source[source] += 1
        _sample_append(
            samples,
            "selected_observations_missing_from_db",
            dict(source_row) or {"source_observation_id": observation_id},
            sample_limit=sample_limit,
        )

    for observation_id in sorted(unexpected_db_observation_ids):
        _sample_append(
            samples,
            "unexpected_db_observations",
            db_observation_descriptors.get(
                observation_id,
                {"source_observation_id": observation_id},
            ),
            sample_limit=sample_limit,
        )

    for canonical_id, observation_id in sorted(canonical_pairs_missing_from_db):
        _sample_append(
            samples,
            "canonical_pairs_missing_from_db_links",
            {
                "canonical_id": canonical_id,
                "source_observation_id": observation_id,
            },
            sample_limit=sample_limit,
        )

    for canonical_id, observation_id in sorted(db_pairs_missing_from_canonical):
        _sample_append(
            samples,
            "db_link_pairs_missing_from_canonical",
            {
                "canonical_id": canonical_id,
                "source_observation_id": observation_id,
            },
            sample_limit=sample_limit,
        )

    return {
        "db_ping": db_ping,
        "schema": {
            "source_documents_columns": source_columns,
            "canonical_source_links_columns": link_columns,
            "source_documents_has_source_observation_id": (
                "source_observation_id" in source_columns
            ),
            "canonical_source_links_has_source_observation_id": (
                "source_observation_id" in link_columns
            ),
            "legacy_source_documents_doc_id_present": "doc_id" in source_columns,
            "legacy_canonical_source_links_doc_id_present": "doc_id" in link_columns,
        },
        "summary": {
            "source_documents_count": source_documents_count,
            "source_documents_by_source": source_documents_by_source,
            "db_observation_identity_count": len(db_observation_ids),
            "db_observation_identity_error_count": db_identity_errors,
            "db_duplicate_observation_id_count": db_duplicate_observation_ids,
            "db_observation_source_counts": dict(
                sorted(db_observation_source_counts.items())
            ),
            "canonical_source_links_count": canonical_source_links_count,
            "resolved_link_count": canonical_source_links_count - null_link_count,
            "null_link_count": null_link_count,
            "dangling_non_null_link_count": dangling_non_null_link_count,
            "joined_source_mismatch_count": joined_source_mismatch_count,
            "links_by_source": links_by_source,
            "db_link_identity_count": len(link_observation_ids),
            "db_link_pair_count": len(link_pairs),
            "db_link_identity_error_count": link_identity_errors,
            "db_duplicate_link_pair_count": link_duplicate_pairs,
            "selected_observation_missing_from_db_count": len(
                missing_db_observation_ids
            ),
            "selected_observation_missing_from_db_by_source": dict(
                sorted(missing_db_by_source.items())
            ),
            "unexpected_db_observation_count": len(unexpected_db_observation_ids),
            "canonical_pair_missing_from_db_count": len(
                canonical_pairs_missing_from_db
            ),
            "db_pair_missing_from_canonical_count": len(
                db_pairs_missing_from_canonical
            ),
        },
        "samples": dict(samples),
    }


def build_report(
    *,
    file_evidence: Mapping[str, Any],
    db_evidence: Mapping[str, Any],
    require_full_parity: bool,
    sample_limit: int,
) -> dict[str, Any]:
    file_summary = file_evidence["summary"]
    db_summary = db_evidence["summary"]

    audit_checks = {
        "db_connected": bool(db_evidence.get("db_ping")),
        "selected_observations_non_empty": (
            int(file_summary["selected_observation_unique_count"]) > 0
        ),
        "canonical_provenance_non_empty": (
            int(file_summary["canonical_provenance_pair_count"]) > 0
        ),
        "no_file_identity_errors": (
            int(file_summary["selected_identity_error_count"]) == 0
            and int(file_summary["canonical_identity_error_count"]) == 0
        ),
        "no_file_identity_conflicts": (
            int(file_summary["selected_identity_conflict_count"]) == 0
        ),
        "canonical_provenance_resolves_to_selected_snapshots": (
            int(file_summary["canonical_provenance_missing_from_selected_count"])
            == 0
        ),
        "db_rows_have_identity": (
            int(db_summary["db_observation_identity_error_count"]) == 0
            and int(db_summary["db_link_identity_error_count"]) == 0
        ),
        "no_dangling_non_null_links": (
            int(db_summary["dangling_non_null_link_count"]) == 0
        ),
        "no_joined_source_mismatches": (
            int(db_summary["joined_source_mismatch_count"]) == 0
        ),
        "db_link_pairs_match_canonical_provenance": (
            int(db_summary["canonical_pair_missing_from_db_count"]) == 0
            and int(db_summary["db_pair_missing_from_canonical_count"]) == 0
        ),
    }

    parity_checks = {
        "source_documents_cover_all_selected_observations": (
            int(db_summary["selected_observation_missing_from_db_count"]) == 0
            and int(db_summary["unexpected_db_observation_count"]) == 0
            and int(db_summary["db_observation_identity_count"])
            == int(file_summary["selected_observation_unique_count"])
        ),
        "canonical_links_are_fully_resolved": int(db_summary["null_link_count"]) == 0,
        "canonical_link_count_matches_provenance": (
            int(db_summary["canonical_source_links_count"])
            == int(file_summary["canonical_provenance_pair_count"])
        ),
        "source_observation_id_materialized_in_source_documents": bool(
            db_evidence["schema"]["source_documents_has_source_observation_id"]
        ),
        "source_observation_id_materialized_in_links": bool(
            db_evidence["schema"][
                "canonical_source_links_has_source_observation_id"
            ]
        ),
    }

    required_checks = dict(audit_checks)
    if require_full_parity:
        required_checks.update(parity_checks)

    failed = [name for name, ok in required_checks.items() if not ok]
    parity_failed = [name for name, ok in parity_checks.items() if not ok]

    return {
        "report_name": REPORT_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now().isoformat(),
        "mode": "require_full_parity" if require_full_parity else "audit_baseline",
        "inputs": {
            **file_evidence["inputs"],
            "sample_limit": sample_limit,
        },
        "file_evidence": {
            "summary": dict(file_summary),
            "samples": file_evidence.get("samples", {}),
        },
        "postgres_evidence": dict(db_evidence),
        "checks": {
            "audit": audit_checks,
            "full_parity": parity_checks,
        },
        "verdict": {
            "ok": not failed,
            "require_full_parity": require_full_parity,
            "required_check_count": len(required_checks),
            "required_failed_count": len(failed),
            "required_failed_checks": failed,
            "full_parity_ok": not parity_failed,
            "full_parity_failed_checks": parity_failed,
            "materialization_gap_detected": bool(parity_failed),
            "parallel_source_observation_plane_required": False,
            "strengthen_existing_materialization_candidate": bool(parity_failed),
            "canonical_truth_mutation_required": False,
            "reconciliation_behavior_change_required": False,
        },
    }


def write_report(report: Mapping[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    history_dir = output_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    run_ts = ts_slug()
    latest_path = output_dir / "source_observation_materialization_parity_latest.json"
    history_path = (
        history_dir / f"source_observation_materialization_parity_{run_ts}.json"
    )
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    latest_path.write_text(text, encoding="utf-8")
    history_path.write_text(text, encoding="utf-8")
    return latest_path, history_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit parity between selected normalized source observations, "
            "canonical provenance, source_documents, and canonical_source_links. "
            "The command is read-only with respect to PostgreSQL."
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
        "--require-full-parity",
        action="store_true",
        help=(
            "Fail unless every selected source observation is materialized and "
            "every canonical provenance link is non-null and referentially complete."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sample_limit = max(1, int(args.sample_limit))

    try:
        selected_snapshots = resolve_selected_snapshots(args.normalized_root)
        file_evidence = collect_file_evidence(
            selected_snapshots=selected_snapshots,
            canonical_path=args.canonical_path,
            sample_limit=sample_limit,
        )
        db_evidence = collect_db_evidence(
            db_config={
                "host": args.host,
                "port": args.port,
                "dbname": args.dbname,
                "user": args.user,
                "password": args.password,
            },
            selected_observation_ids=set(file_evidence["selected_observation_ids"]),
            selected_observations_by_id=file_evidence["selected_observations_by_id"],
            canonical_provenance_pairs=set(
                file_evidence["canonical_provenance_pairs"]
            ),
            sample_limit=sample_limit,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1
    except psycopg.Error as exc:
        print(f"[FAILED] PostgreSQL error: {exc}")
        return 1

    report = build_report(
        file_evidence=file_evidence,
        db_evidence=db_evidence,
        require_full_parity=bool(args.require_full_parity),
        sample_limit=sample_limit,
    )
    latest_path, history_path = write_report(report, args.output_dir)

    file_summary = report["file_evidence"]["summary"]
    db_summary = report["postgres_evidence"]["summary"]
    verdict = report["verdict"]
    status = "OK" if verdict["ok"] else "FAILED"

    print(f"[{status}] report_name={REPORT_NAME}")
    print(
        f"[{status}] selected_observations="
        f"{file_summary['selected_observation_unique_count']}"
    )
    print(
        f"[{status}] canonical_provenance_pairs="
        f"{file_summary['canonical_provenance_pair_count']}"
    )
    print(
        f"[{status}] non_contributing_observations="
        f"{file_summary['non_contributing_observation_count']}"
    )
    print(
        f"[{status}] source_documents="
        f"{db_summary['source_documents_count']}"
    )
    print(
        f"[{status}] canonical_source_links="
        f"{db_summary['canonical_source_links_count']}"
    )
    print(f"[{status}] resolved_links={db_summary['resolved_link_count']}")
    print(f"[{status}] null_links={db_summary['null_link_count']}")
    print(
        f"[{status}] dangling_non_null_links="
        f"{db_summary['dangling_non_null_link_count']}"
    )
    print(
        f"[{status}] selected_observations_missing_from_db="
        f"{db_summary['selected_observation_missing_from_db_count']}"
    )
    print(f"[{status}] full_parity_ok={verdict['full_parity_ok']}")
    print(f"[{status}] required_failed_count={verdict['required_failed_count']}")
    print(f"[{status}] latest report: {latest_path}")
    print(f"[{status}] history report: {history_path}")

    if verdict["required_failed_checks"]:
        print("[FAILED] Required checks:")
        for check_name in verdict["required_failed_checks"]:
            print(f"- {check_name}")

    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
