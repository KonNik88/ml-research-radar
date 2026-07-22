from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    import psycopg
    from psycopg.rows import dict_row
except ModuleNotFoundError:  # pragma: no cover - unit tests exercise pure logic.
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]


REPORT_NAME = "source_observation_materialization_promotion_v01"
SCHEMA_VERSION = "source_observation_materialization_operational_promotion_v0.1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CANONICAL_PATH = (
    PROJECT_ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "reports" / "validation"
DEFAULT_BACKUP_DIR = PROJECT_ROOT / "backups" / "postgres"

DEFAULT_OPERATIONAL_DBNAME = "ml_radar"
DEFAULT_CANDIDATE_DBNAME = "ml_radar_source_identity_candidate_v01"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 15432
DEFAULT_USER = "ml_radar"
DEFAULT_PASSWORD = "ml_radar_dev"

EXPECTED_CANONICAL_SHA256 = (
    "6282e3e78a604490d0626a243e1e93a1c8e2a012b6558739a88448cf19970fc7"
)
EXPECTED_TARGET_COUNTS = {
    "canonical_documents": 60954,
    "source_documents": 88178,
    "canonical_source_links": 88037,
    "document_references": 709662,
    "artifact_entities": 7333,
    "artifact_observations": 38246,
    "paper_artifact_links": 7430,
}
EXPECTED_LEGACY_COUNTS = {
    **EXPECTED_TARGET_COUNTS,
    "source_documents": 70244,
}
EXPECTED_SHARED_LEGACY_DOC_ID_VALUES = 9119

MUTATION_CAPABILITIES = {
    "executes_alter_database": False,
    "executes_drop_database": False,
    "executes_create_database": False,
    "executes_truncate": False,
    "executes_insert": False,
    "executes_update": False,
    "executes_delete": False,
    "executes_pg_terminate_backend": False,
    "executes_pg_cancel_backend": False,
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ts_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def load_dotenv_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        os.environ.setdefault(
            key.strip(),
            value.strip().strip('"').strip("'"),
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _nearest_existing_parent(path: Path) -> Path:
    candidate = path.resolve()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    if not candidate.exists():
        raise FileNotFoundError(f"No existing parent for path: {path}")
    return candidate


def collect_disk_evidence(backup_dir: Path) -> dict[str, Any]:
    inspected_path = _nearest_existing_parent(backup_dir)
    usage = shutil.disk_usage(inspected_path)
    return {
        "backup_dir": normalize_path(backup_dir),
        "inspected_path": normalize_path(inspected_path),
        "total_bytes": int(usage.total),
        "used_bytes": int(usage.used),
        "free_bytes": int(usage.free),
        "free_gb": round(usage.free / (1024**3), 3),
    }


def file_evidence(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "path": None,
            "exists": False,
            "is_file": False,
            "size_bytes": 0,
            "non_empty": False,
        }
    exists = path.exists()
    is_file = path.is_file()
    size_bytes = int(path.stat().st_size) if is_file else 0
    return {
        "path": normalize_path(path),
        "exists": exists,
        "is_file": is_file,
        "size_bytes": size_bytes,
        "non_empty": is_file and size_bytes > 0,
    }


def _connect(config: Mapping[str, Any], dbname: str):
    if psycopg is None:
        raise RuntimeError("psycopg is required to inspect PostgreSQL")
    return psycopg.connect(
        host=config["host"],
        port=config["port"],
        dbname=dbname,
        user=config["user"],
        password=config["password"],
        row_factory=dict_row,
    )


def collect_catalog_evidence(
    *,
    db_config: Mapping[str, Any],
    database_names: Sequence[str],
) -> dict[str, Any]:
    unique_names = sorted({name for name in database_names if name})
    rows_by_name: dict[str, dict[str, Any]] = {}

    with _connect(db_config, "postgres") as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                d.datname,
                pg_get_userbyid(d.datdba) AS owner,
                pg_database_size(d.datname) AS size_bytes,
                d.datallowconn,
                COALESCE(a.active_connections, 0) AS active_connections
            FROM pg_database d
            LEFT JOIN (
                SELECT datname, COUNT(*) AS active_connections
                FROM pg_stat_activity
                WHERE pid <> pg_backend_pid()
                GROUP BY datname
            ) a ON a.datname = d.datname
            WHERE d.datname = ANY(%s)
            ORDER BY d.datname
            """,
            (unique_names,),
        )
        for row in cur.fetchall():
            rows_by_name[str(row["datname"])] = {
                "exists": True,
                "owner": row["owner"],
                "size_bytes": int(row["size_bytes"] or 0),
                "datallowconn": bool(row["datallowconn"]),
                "active_connections": int(row["active_connections"] or 0),
            }

        cur.execute(
            """
            SELECT rolname, rolsuper, rolcreatedb, rolcanlogin
            FROM pg_roles
            WHERE rolname = %s
            """,
            (db_config["user"],),
        )
        role_row = cur.fetchone()

    databases = {
        name: rows_by_name.get(
            name,
            {
                "exists": False,
                "owner": None,
                "size_bytes": 0,
                "datallowconn": False,
                "active_connections": 0,
            },
        )
        for name in unique_names
    }
    role = {
        "exists": bool(role_row),
        "rolname": role_row["rolname"] if role_row else None,
        "rolsuper": bool(role_row["rolsuper"]) if role_row else False,
        "rolcreatedb": bool(role_row["rolcreatedb"]) if role_row else False,
        "rolcanlogin": bool(role_row["rolcanlogin"]) if role_row else False,
    }
    return {"databases": databases, "role": role}


def _table_exists(cur: Any, table_name: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = %s
        ) AS exists
        """,
        (table_name,),
    )
    row = cur.fetchone()
    return bool(row and row["exists"])


def _scalar_int(cur: Any, sql: str, params: Sequence[Any] = ()) -> int:
    cur.execute(sql, tuple(params))
    row = cur.fetchone()
    if not row:
        return 0
    return int(next(iter(row.values())) or 0)


def _column_map(cur: Any, table_name: str) -> dict[str, dict[str, Any]]:
    cur.execute(
        """
        SELECT column_name, is_nullable, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table_name,),
    )
    return {
        str(row["column_name"]): {
            "is_nullable": str(row["is_nullable"]),
            "data_type": str(row["data_type"]),
        }
        for row in cur.fetchall()
    }


def _primary_key_columns(cur: Any, table_name: str) -> list[str]:
    cur.execute(
        """
        SELECT a.attname AS column_name
        FROM pg_index i
        JOIN pg_class t ON t.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE n.nspname = 'public'
          AND t.relname = %s
          AND i.indisprimary
        ORDER BY k.ord
        """,
        (table_name,),
    )
    return [str(row["column_name"]) for row in cur.fetchall()]


def _unique_constraints(cur: Any, table_name: str) -> list[list[str]]:
    """Return ordered UNIQUE-constraint columns without array decoding.

    Reading one row per constrained column avoids driver-specific PostgreSQL
    array handling. In particular, some driver/configuration combinations may
    return ``array_agg(...)`` as the text value
    ``{canonical_id,source_observation_id}``; applying ``list(...)`` to that
    value incorrectly splits it into individual characters.
    """

    cur.execute(
        """
        SELECT
            tc.constraint_name,
            kcu.column_name,
            kcu.ordinal_position
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON kcu.constraint_schema = tc.constraint_schema
         AND kcu.constraint_name = tc.constraint_name
        WHERE tc.table_schema = 'public'
          AND tc.table_name = %s
          AND tc.constraint_type = 'UNIQUE'
        ORDER BY tc.constraint_name, kcu.ordinal_position
        """,
        (table_name,),
    )

    columns_by_constraint: dict[str, list[str]] = {}
    for row in cur.fetchall():
        constraint_name = str(row["constraint_name"])
        column_name = str(row["column_name"])
        columns_by_constraint.setdefault(constraint_name, []).append(column_name)

    return list(columns_by_constraint.values())


def _foreign_keys(cur: Any, table_name: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT
            tc.constraint_name,
            kcu.column_name,
            ccu.table_name AS target_table,
            ccu.column_name AS target_column,
            rc.delete_rule
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON kcu.constraint_schema = tc.constraint_schema
         AND kcu.constraint_name = tc.constraint_name
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_schema = tc.constraint_schema
         AND ccu.constraint_name = tc.constraint_name
        JOIN information_schema.referential_constraints rc
          ON rc.constraint_schema = tc.constraint_schema
         AND rc.constraint_name = tc.constraint_name
        WHERE tc.table_schema = 'public'
          AND tc.table_name = %s
          AND tc.constraint_type = 'FOREIGN KEY'
        ORDER BY tc.constraint_name, kcu.ordinal_position
        """,
        (table_name,),
    )
    return [dict(row) for row in cur.fetchall()]


def collect_database_snapshot(
    *,
    db_config: Mapping[str, Any],
    dbname: str,
    exists: bool,
) -> dict[str, Any]:
    if not exists:
        return {
            "dbname": dbname,
            "exists": False,
            "tables": {},
            "counts": {},
            "schema": {},
            "identity": {},
            "integrity": {},
        }

    required_tables = tuple(EXPECTED_TARGET_COUNTS)
    with _connect(db_config, dbname) as conn, conn.cursor() as cur:
        tables = {name: _table_exists(cur, name) for name in required_tables}
        counts = {
            name: (
                _scalar_int(cur, f'SELECT COUNT(*) AS count FROM "{name}"')
                if tables[name]
                else None
            )
            for name in required_tables
        }

        source_columns = (
            _column_map(cur, "source_documents")
            if tables["source_documents"]
            else {}
        )
        link_columns = (
            _column_map(cur, "canonical_source_links")
            if tables["canonical_source_links"]
            else {}
        )
        source_pk = (
            _primary_key_columns(cur, "source_documents")
            if tables["source_documents"]
            else []
        )
        link_uniques = (
            _unique_constraints(cur, "canonical_source_links")
            if tables["canonical_source_links"]
            else []
        )
        link_fks = (
            _foreign_keys(cur, "canonical_source_links")
            if tables["canonical_source_links"]
            else []
        )

        has_source_observation_id = "source_observation_id" in source_columns
        link_has_source_observation_id = "source_observation_id" in link_columns

        identity: dict[str, Any] = {
            "source_observation_id_unique_count": None,
            "null_source_observation_links": None,
            "dangling_source_observation_links": None,
            "shared_cross_source_legacy_doc_id_values": None,
        }
        if tables["source_documents"]:
            identity["shared_cross_source_legacy_doc_id_values"] = _scalar_int(
                cur,
                """
                SELECT COUNT(*) AS count
                FROM (
                    SELECT doc_id
                    FROM source_documents
                    GROUP BY doc_id
                    HAVING COUNT(DISTINCT source) > 1
                ) x
                """,
            )
            if has_source_observation_id:
                identity["source_observation_id_unique_count"] = _scalar_int(
                    cur,
                    "SELECT COUNT(DISTINCT source_observation_id) AS count FROM source_documents",
                )
        if tables["canonical_source_links"] and link_has_source_observation_id:
            identity["null_source_observation_links"] = _scalar_int(
                cur,
                "SELECT COUNT(*) AS count FROM canonical_source_links WHERE source_observation_id IS NULL",
            )
            if tables["source_documents"] and has_source_observation_id:
                identity["dangling_source_observation_links"] = _scalar_int(
                    cur,
                    """
                    SELECT COUNT(*) AS count
                    FROM canonical_source_links csl
                    LEFT JOIN source_documents sd
                      ON sd.source_observation_id = csl.source_observation_id
                    WHERE sd.source_observation_id IS NULL
                    """,
                )

        integrity: dict[str, Any] = {
            "dangling_paper_artifact_links": None,
            "dangling_artifact_entity_links": None,
        }
        if tables["paper_artifact_links"] and tables["canonical_documents"]:
            integrity["dangling_paper_artifact_links"] = _scalar_int(
                cur,
                """
                SELECT COUNT(*) AS count
                FROM paper_artifact_links pal
                LEFT JOIN canonical_documents cd
                  ON cd.canonical_id = pal.canonical_id
                WHERE cd.canonical_id IS NULL
                """,
            )
        if tables["paper_artifact_links"] and tables["artifact_entities"]:
            integrity["dangling_artifact_entity_links"] = _scalar_int(
                cur,
                """
                SELECT COUNT(*) AS count
                FROM paper_artifact_links pal
                LEFT JOIN artifact_entities ae
                  ON ae.artifact_id = pal.artifact_id
                WHERE ae.artifact_id IS NULL
                """,
            )

    return {
        "dbname": dbname,
        "exists": True,
        "tables": tables,
        "counts": counts,
        "schema": {
            "source_documents_columns": source_columns,
            "canonical_source_links_columns": link_columns,
            "source_documents_primary_key": source_pk,
            "canonical_source_links_unique_constraints": link_uniques,
            "canonical_source_links_foreign_keys": link_fks,
        },
        "identity": identity,
        "integrity": integrity,
    }


def _column_not_null(columns: Mapping[str, Any], name: str) -> bool:
    value = columns.get(name)
    return bool(value and value.get("is_nullable") == "NO")


def is_target_shape(snapshot: Mapping[str, Any]) -> bool:
    schema = snapshot.get("schema") or {}
    source_columns = schema.get("source_documents_columns") or {}
    link_columns = schema.get("canonical_source_links_columns") or {}
    source_pk = schema.get("source_documents_primary_key") or []
    link_uniques = schema.get("canonical_source_links_unique_constraints") or []
    link_fks = schema.get("canonical_source_links_foreign_keys") or []

    expected_fk = any(
        row.get("column_name") == "source_observation_id"
        and row.get("target_table") == "source_documents"
        and row.get("target_column") == "source_observation_id"
        and str(row.get("delete_rule") or "").upper() == "RESTRICT"
        for row in link_fks
    )
    expected_unique = ["canonical_id", "source_observation_id"] in link_uniques

    return bool(
        snapshot.get("exists")
        and _column_not_null(source_columns, "source_observation_id")
        and source_pk == ["source_observation_id"]
        and _column_not_null(source_columns, "doc_id")
        and _column_not_null(link_columns, "source_observation_id")
        and "doc_id" in link_columns
        and link_columns["doc_id"].get("is_nullable") == "YES"
        and expected_fk
        and expected_unique
    )


def is_legacy_shape(snapshot: Mapping[str, Any]) -> bool:
    schema = snapshot.get("schema") or {}
    source_columns = schema.get("source_documents_columns") or {}
    link_columns = schema.get("canonical_source_links_columns") or {}
    source_pk = schema.get("source_documents_primary_key") or []
    return bool(
        snapshot.get("exists")
        and "source_observation_id" not in source_columns
        and "source_observation_id" not in link_columns
        and _column_not_null(source_columns, "doc_id")
        and source_pk == ["doc_id"]
    )


def counts_match(
    snapshot: Mapping[str, Any],
    expected: Mapping[str, int],
) -> bool:
    counts = snapshot.get("counts") or {}
    return all(counts.get(name) == value for name, value in expected.items())


def _backup_checks(
    backup_evidence: Mapping[str, Mapping[str, Any]],
) -> dict[str, bool]:
    return {
        "operational_backup_non_empty": bool(
            backup_evidence["operational_backup"].get("non_empty")
        ),
        "candidate_backup_non_empty": bool(
            backup_evidence["candidate_backup"].get("non_empty")
        ),
        "operational_backup_list_non_empty": bool(
            backup_evidence["operational_backup_list"].get("non_empty")
        ),
        "candidate_backup_list_non_empty": bool(
            backup_evidence["candidate_backup_list"].get("non_empty")
        ),
    }


def build_report(
    *,
    phase: str,
    strict: bool,
    operational_dbname: str,
    candidate_dbname: str,
    archive_dbname: str | None,
    canonical_path: Path,
    canonical_sha256: str,
    catalog_evidence: Mapping[str, Any],
    operational_snapshot: Mapping[str, Any],
    candidate_snapshot: Mapping[str, Any],
    archive_snapshot: Mapping[str, Any] | None,
    disk_evidence: Mapping[str, Any],
    min_free_gb: float,
    backup_evidence: Mapping[str, Mapping[str, Any]],
    require_backups: bool,
) -> dict[str, Any]:
    databases = catalog_evidence.get("databases") or {}
    role = catalog_evidence.get("role") or {}
    operational_catalog = databases.get(operational_dbname) or {}
    candidate_catalog = databases.get(candidate_dbname) or {}
    archive_catalog = databases.get(archive_dbname) or {} if archive_dbname else {}

    common_checks: dict[str, bool] = {
        "canonical_file_exists": canonical_path.is_file(),
        "canonical_sha256_matches": canonical_sha256 == EXPECTED_CANONICAL_SHA256,
        "postgres_role_exists": bool(role.get("exists")),
        "postgres_role_can_login": bool(role.get("rolcanlogin")),
        "postgres_role_can_manage_database": bool(
            role.get("rolsuper") or role.get("rolcreatedb")
        ),
        "backup_disk_free_space_sufficient": float(disk_evidence.get("free_gb") or 0.0)
        >= float(min_free_gb),
        "validator_is_read_only": not any(MUTATION_CAPABILITIES.values()),
    }

    backup_checks = _backup_checks(backup_evidence)

    if phase == "preflight":
        phase_checks: dict[str, bool] = {
            "operational_database_exists": bool(operational_catalog.get("exists")),
            "candidate_database_exists": bool(candidate_catalog.get("exists")),
            "operational_database_owner_matches": operational_catalog.get("owner")
            == role.get("rolname"),
            "candidate_database_owner_matches": candidate_catalog.get("owner")
            == role.get("rolname"),
            "operational_external_connections_zero": int(
                operational_catalog.get("active_connections") or 0
            )
            == 0,
            "candidate_external_connections_zero": int(
                candidate_catalog.get("active_connections") or 0
            )
            == 0,
            "planned_archive_database_absent": (
                True
                if not archive_dbname
                else not bool(archive_catalog.get("exists"))
            ),
            "operational_legacy_shape": is_legacy_shape(operational_snapshot),
            "operational_legacy_counts_match": counts_match(
                operational_snapshot,
                EXPECTED_LEGACY_COUNTS,
            ),
            "candidate_target_shape": is_target_shape(candidate_snapshot),
            "candidate_target_counts_match": counts_match(
                candidate_snapshot,
                EXPECTED_TARGET_COUNTS,
            ),
            "candidate_source_observation_ids_unique": (
                candidate_snapshot.get("identity", {}).get(
                    "source_observation_id_unique_count"
                )
                == EXPECTED_TARGET_COUNTS["source_documents"]
            ),
            "candidate_authoritative_null_links_zero": (
                candidate_snapshot.get("identity", {}).get(
                    "null_source_observation_links"
                )
                == 0
            ),
            "candidate_authoritative_dangling_links_zero": (
                candidate_snapshot.get("identity", {}).get(
                    "dangling_source_observation_links"
                )
                == 0
            ),
            "candidate_shared_legacy_doc_id_values_preserved": (
                candidate_snapshot.get("identity", {}).get(
                    "shared_cross_source_legacy_doc_id_values"
                )
                == EXPECTED_SHARED_LEGACY_DOC_ID_VALUES
            ),
            "candidate_dangling_paper_artifact_links_zero": (
                candidate_snapshot.get("integrity", {}).get(
                    "dangling_paper_artifact_links"
                )
                == 0
            ),
            "candidate_dangling_artifact_entity_links_zero": (
                candidate_snapshot.get("integrity", {}).get(
                    "dangling_artifact_entity_links"
                )
                == 0
            ),
        }
    elif phase == "post-promotion":
        phase_checks = {
            "operational_database_exists": bool(operational_catalog.get("exists")),
            "operational_database_owner_matches": operational_catalog.get("owner")
            == role.get("rolname"),
            "operational_external_connections_zero": int(
                operational_catalog.get("active_connections") or 0
            )
            == 0,
            "operational_target_shape": is_target_shape(operational_snapshot),
            "operational_target_counts_match": counts_match(
                operational_snapshot,
                EXPECTED_TARGET_COUNTS,
            ),
            "operational_source_observation_ids_unique": (
                operational_snapshot.get("identity", {}).get(
                    "source_observation_id_unique_count"
                )
                == EXPECTED_TARGET_COUNTS["source_documents"]
            ),
            "operational_authoritative_null_links_zero": (
                operational_snapshot.get("identity", {}).get(
                    "null_source_observation_links"
                )
                == 0
            ),
            "operational_authoritative_dangling_links_zero": (
                operational_snapshot.get("identity", {}).get(
                    "dangling_source_observation_links"
                )
                == 0
            ),
            "operational_shared_legacy_doc_id_values_preserved": (
                operational_snapshot.get("identity", {}).get(
                    "shared_cross_source_legacy_doc_id_values"
                )
                == EXPECTED_SHARED_LEGACY_DOC_ID_VALUES
            ),
            "operational_dangling_paper_artifact_links_zero": (
                operational_snapshot.get("integrity", {}).get(
                    "dangling_paper_artifact_links"
                )
                == 0
            ),
            "operational_dangling_artifact_entity_links_zero": (
                operational_snapshot.get("integrity", {}).get(
                    "dangling_artifact_entity_links"
                )
                == 0
            ),
            "original_candidate_database_name_absent": not bool(
                candidate_catalog.get("exists")
            ),
            "archive_database_name_supplied": bool(archive_dbname),
            "archive_database_exists": bool(archive_catalog.get("exists")),
            "archive_database_owner_matches": (
                bool(archive_dbname)
                and archive_catalog.get("owner") == role.get("rolname")
            ),
            "archive_external_connections_zero": int(
                archive_catalog.get("active_connections") or 0
            )
            == 0,
            "archive_legacy_shape": bool(
                archive_snapshot and is_legacy_shape(archive_snapshot)
            ),
            "archive_legacy_counts_match": bool(
                archive_snapshot
                and counts_match(archive_snapshot, EXPECTED_LEGACY_COUNTS)
            ),
        }
    else:
        raise ValueError(f"Unsupported phase: {phase}")

    effective_require_backups = bool(require_backups or phase == "post-promotion")
    checks = {**common_checks, **phase_checks}
    if effective_require_backups:
        checks.update(backup_checks)

    failed = [name for name, ok in checks.items() if not ok]
    report = {
        "report_name": REPORT_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "phase": phase,
        "strict": strict,
        "status": "read_only_validation",
        "read_only": True,
        "database_mutation_performed": False,
        "canonical_truth_mutated": False,
        "reconcile_executed": False,
        "inputs": {
            "operational_dbname": operational_dbname,
            "candidate_dbname": candidate_dbname,
            "archive_dbname": archive_dbname,
            "canonical_path": normalize_path(canonical_path),
            "expected_canonical_sha256": EXPECTED_CANONICAL_SHA256,
            "min_free_gb": min_free_gb,
            "require_backups": effective_require_backups,
        },
        "canonical_evidence": {
            "path": normalize_path(canonical_path),
            "sha256": canonical_sha256,
        },
        "disk_evidence": dict(disk_evidence),
        "backup_evidence": {
            key: dict(value) for key, value in backup_evidence.items()
        },
        "postgres_catalog": dict(catalog_evidence),
        "database_snapshots": {
            "operational": dict(operational_snapshot),
            "candidate": dict(candidate_snapshot),
            "archive": dict(archive_snapshot) if archive_snapshot else None,
        },
        "mutation_capabilities": dict(MUTATION_CAPABILITIES),
        "checks": checks,
        "summary": {
            "checks_count": len(checks),
            "passed_checks_count": len(checks) - len(failed),
            "failed_checks_count": len(failed),
            "operational_source_documents_count": operational_snapshot.get(
                "counts", {}
            ).get("source_documents"),
            "candidate_source_documents_count": candidate_snapshot.get(
                "counts", {}
            ).get("source_documents"),
            "archive_source_documents_count": (
                archive_snapshot.get("counts", {}).get("source_documents")
                if archive_snapshot
                else None
            ),
        },
        "verdict": {
            "ok": not failed,
            "required_failed_count": len(failed),
            "required_failed_checks": failed,
            "promotion_preflight_ready": phase == "preflight" and not failed,
            "operational_promotion_validated": (
                phase == "post-promotion" and not failed
            ),
            "rollback_database_retained": (
                phase == "post-promotion"
                and bool(archive_snapshot)
                and is_legacy_shape(archive_snapshot)
            ),
            "canonical_truth_mutation_required": False,
            "reconciliation_behavior_change_required": False,
        },
    }
    return report


def build_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Source Observation Materialization Operational Promotion v0.1",
        "",
        f"- Generated at: `{report['generated_at_utc']}`",
        f"- Phase: `{report['phase']}`",
        f"- Strict: `{report['strict']}`",
        f"- Read only: `{report['read_only']}`",
        "",
        "## Summary",
        "",
    ]
    for name, value in report["summary"].items():
        lines.append(f"- {name}: `{value}`")
    lines.extend(["", "## Checks", ""])
    for name, value in report["checks"].items():
        lines.append(f"- {name}: `{value}`")
    lines.extend(["", "## Verdict", ""])
    for name, value in report["verdict"].items():
        lines.append(f"- {name}: `{value}`")
    lines.append("")
    return "\n".join(lines)


def write_report(
    report: Mapping[str, Any],
    output_dir: Path,
) -> tuple[Path, Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    history_dir = output_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    run_ts = ts_slug()

    latest_json = output_dir / f"{REPORT_NAME}_latest.json"
    latest_md = output_dir / f"{REPORT_NAME}_latest.md"
    history_json = history_dir / f"{REPORT_NAME}_{run_ts}.json"
    history_md = history_dir / f"{REPORT_NAME}_{run_ts}.md"

    json_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    markdown_text = build_markdown(report)
    latest_json.write_text(json_text, encoding="utf-8")
    history_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(markdown_text, encoding="utf-8")
    history_md.write_text(markdown_text, encoding="utf-8")
    return latest_json, latest_md, history_json, history_md


def build_parser() -> argparse.ArgumentParser:
    load_dotenv_file(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(
        description=(
            "Read-only operational promotion validator for the source_observation_id "
            "PostgreSQL materialization. It never renames, creates, drops, truncates, "
            "or modifies databases."
        )
    )
    parser.add_argument(
        "--phase",
        choices=["preflight", "post-promotion"],
        required=True,
    )
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--host", default=os.getenv("ML_RADAR_POSTGRES_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("ML_RADAR_POSTGRES_PORT", str(DEFAULT_PORT))),
    )
    parser.add_argument(
        "--user",
        default=os.getenv("ML_RADAR_POSTGRES_USER", DEFAULT_USER),
    )
    parser.add_argument(
        "--password",
        default=os.getenv("ML_RADAR_POSTGRES_PASSWORD", DEFAULT_PASSWORD),
    )
    parser.add_argument(
        "--operational-dbname",
        default=DEFAULT_OPERATIONAL_DBNAME,
    )
    parser.add_argument(
        "--candidate-dbname",
        default=DEFAULT_CANDIDATE_DBNAME,
    )
    parser.add_argument("--archive-dbname", default=None)
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--min-free-gb", type=float, default=5.0)
    parser.add_argument("--require-backups", action="store_true")
    parser.add_argument("--operational-backup-path", type=Path, default=None)
    parser.add_argument("--candidate-backup-path", type=Path, default=None)
    parser.add_argument("--operational-backup-list-path", type=Path, default=None)
    parser.add_argument("--candidate-backup-list-path", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    archive_dbname = str(args.archive_dbname).strip() if args.archive_dbname else None
    database_names = [args.operational_dbname, args.candidate_dbname]
    if archive_dbname:
        database_names.append(archive_dbname)

    db_config = {
        "host": args.host,
        "port": args.port,
        "user": args.user,
        "password": args.password,
    }

    try:
        canonical_sha256 = sha256_file(args.canonical_path)
        disk_evidence = collect_disk_evidence(args.backup_dir)
        catalog_evidence = collect_catalog_evidence(
            db_config=db_config,
            database_names=database_names,
        )
        databases = catalog_evidence["databases"]
        operational_snapshot = collect_database_snapshot(
            db_config=db_config,
            dbname=args.operational_dbname,
            exists=bool(databases[args.operational_dbname]["exists"]),
        )
        candidate_snapshot = collect_database_snapshot(
            db_config=db_config,
            dbname=args.candidate_dbname,
            exists=bool(databases[args.candidate_dbname]["exists"]),
        )
        archive_snapshot = None
        if archive_dbname:
            archive_snapshot = collect_database_snapshot(
                db_config=db_config,
                dbname=archive_dbname,
                exists=bool(databases[archive_dbname]["exists"]),
            )
    except (FileNotFoundError, OSError, TypeError, ValueError, RuntimeError) as exc:
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1
    except Exception as exc:
        if psycopg is not None and isinstance(exc, psycopg.Error):
            print(f"[FAILED] PostgreSQL error: {exc}")
            return 1
        raise

    backup_evidence = {
        "operational_backup": file_evidence(args.operational_backup_path),
        "candidate_backup": file_evidence(args.candidate_backup_path),
        "operational_backup_list": file_evidence(
            args.operational_backup_list_path
        ),
        "candidate_backup_list": file_evidence(args.candidate_backup_list_path),
    }

    report = build_report(
        phase=args.phase,
        strict=bool(args.strict),
        operational_dbname=args.operational_dbname,
        candidate_dbname=args.candidate_dbname,
        archive_dbname=archive_dbname,
        canonical_path=args.canonical_path,
        canonical_sha256=canonical_sha256,
        catalog_evidence=catalog_evidence,
        operational_snapshot=operational_snapshot,
        candidate_snapshot=candidate_snapshot,
        archive_snapshot=archive_snapshot,
        disk_evidence=disk_evidence,
        min_free_gb=float(args.min_free_gb),
        backup_evidence=backup_evidence,
        require_backups=bool(args.require_backups),
    )
    latest_json, latest_md, history_json, history_md = write_report(
        report,
        args.output_dir,
    )

    verdict = report["verdict"]
    status = "OK" if verdict["ok"] else "FAILED"
    print(f"[{status}] report_name={REPORT_NAME}")
    print(f"[{status}] phase={report['phase']}")
    print(f"[{status}] checks_count={report['summary']['checks_count']}")
    print(
        f"[{status}] passed_checks_count="
        f"{report['summary']['passed_checks_count']}"
    )
    print(
        f"[{status}] required_failed_count="
        f"{verdict['required_failed_count']}"
    )
    print(
        f"[{status}] promotion_preflight_ready="
        f"{verdict['promotion_preflight_ready']}"
    )
    print(
        f"[{status}] operational_promotion_validated="
        f"{verdict['operational_promotion_validated']}"
    )
    print(f"[{status}] latest JSON: {latest_json}")
    print(f"[{status}] latest MD: {latest_md}")
    print(f"[{status}] history JSON: {history_json}")
    print(f"[{status}] history MD: {history_md}")

    if verdict["required_failed_checks"]:
        print("[FAILED] Required checks:")
        for name in verdict["required_failed_checks"]:
            print(f"- {name}")

    if args.strict and not verdict["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
