from __future__ import annotations

from pathlib import Path

from scripts.validation.check_source_observation_materialization_promotion import (
    EXPECTED_CANONICAL_SHA256,
    EXPECTED_LEGACY_COUNTS,
    EXPECTED_SHARED_LEGACY_DOC_ID_VALUES,
    EXPECTED_TARGET_COUNTS,
    MUTATION_CAPABILITIES,
    build_parser,
    build_report,
    is_legacy_shape,
    is_target_shape,
    _unique_constraints,
)


def _target_snapshot(dbname: str = "ml_radar_source_identity_candidate_v01") -> dict:
    return {
        "dbname": dbname,
        "exists": True,
        "counts": dict(EXPECTED_TARGET_COUNTS),
        "schema": {
            "source_documents_columns": {
                "source_observation_id": {"is_nullable": "NO"},
                "doc_id": {"is_nullable": "NO"},
            },
            "canonical_source_links_columns": {
                "source_observation_id": {"is_nullable": "NO"},
                "doc_id": {"is_nullable": "YES"},
            },
            "source_documents_primary_key": ["source_observation_id"],
            "canonical_source_links_unique_constraints": [
                ["canonical_id", "source_observation_id"]
            ],
            "canonical_source_links_foreign_keys": [
                {
                    "column_name": "source_observation_id",
                    "target_table": "source_documents",
                    "target_column": "source_observation_id",
                    "delete_rule": "RESTRICT",
                }
            ],
        },
        "identity": {
            "source_observation_id_unique_count": 88178,
            "null_source_observation_links": 0,
            "dangling_source_observation_links": 0,
            "shared_cross_source_legacy_doc_id_values": (
                EXPECTED_SHARED_LEGACY_DOC_ID_VALUES
            ),
        },
        "integrity": {
            "dangling_paper_artifact_links": 0,
            "dangling_artifact_entity_links": 0,
        },
    }


def _legacy_snapshot(dbname: str = "ml_radar") -> dict:
    return {
        "dbname": dbname,
        "exists": True,
        "counts": dict(EXPECTED_LEGACY_COUNTS),
        "schema": {
            "source_documents_columns": {
                "doc_id": {"is_nullable": "NO"},
            },
            "canonical_source_links_columns": {
                "doc_id": {"is_nullable": "YES"},
            },
            "source_documents_primary_key": ["doc_id"],
            "canonical_source_links_unique_constraints": [],
            "canonical_source_links_foreign_keys": [],
        },
        "identity": {
            "source_observation_id_unique_count": None,
            "null_source_observation_links": None,
            "dangling_source_observation_links": None,
            "shared_cross_source_legacy_doc_id_values": 0,
        },
        "integrity": {
            "dangling_paper_artifact_links": 0,
            "dangling_artifact_entity_links": 0,
        },
    }


def _catalog(
    *,
    operational_exists: bool = True,
    candidate_exists: bool = True,
    archive_name: str | None = None,
    archive_exists: bool = False,
    operational_connections: int = 0,
    candidate_connections: int = 0,
    archive_connections: int = 0,
) -> dict:
    databases = {
        "ml_radar": {
            "exists": operational_exists,
            "owner": "ml_radar" if operational_exists else None,
            "active_connections": operational_connections,
        },
        "ml_radar_source_identity_candidate_v01": {
            "exists": candidate_exists,
            "owner": "ml_radar" if candidate_exists else None,
            "active_connections": candidate_connections,
        },
    }
    if archive_name:
        databases[archive_name] = {
            "exists": archive_exists,
            "owner": "ml_radar" if archive_exists else None,
            "active_connections": archive_connections,
        }
    return {
        "databases": databases,
        "role": {
            "exists": True,
            "rolname": "ml_radar",
            "rolsuper": True,
            "rolcreatedb": True,
            "rolcanlogin": True,
        },
    }


def _empty_backup_evidence() -> dict:
    return {
        "operational_backup": {"non_empty": False},
        "candidate_backup": {"non_empty": False},
        "operational_backup_list": {"non_empty": False},
        "candidate_backup_list": {"non_empty": False},
    }


def _complete_backup_evidence() -> dict:
    return {
        "operational_backup": {"non_empty": True},
        "candidate_backup": {"non_empty": True},
        "operational_backup_list": {"non_empty": True},
        "candidate_backup_list": {"non_empty": True},
    }


def _build(
    *,
    phase: str,
    catalog: dict,
    operational_snapshot: dict,
    candidate_snapshot: dict,
    archive_name: str | None = None,
    archive_snapshot: dict | None = None,
    backups: dict | None = None,
    require_backups: bool = False,
) -> dict:
    return build_report(
        phase=phase,
        strict=True,
        operational_dbname="ml_radar",
        candidate_dbname="ml_radar_source_identity_candidate_v01",
        archive_dbname=archive_name,
        canonical_path=Path(__file__),
        canonical_sha256=EXPECTED_CANONICAL_SHA256,
        catalog_evidence=catalog,
        operational_snapshot=operational_snapshot,
        candidate_snapshot=candidate_snapshot,
        archive_snapshot=archive_snapshot,
        disk_evidence={"free_gb": 100.0},
        min_free_gb=5.0,
        backup_evidence=backups or _empty_backup_evidence(),
        require_backups=require_backups,
    )


def test_shape_helpers_distinguish_legacy_and_target() -> None:
    assert is_legacy_shape(_legacy_snapshot()) is True
    assert is_target_shape(_legacy_snapshot()) is False
    assert is_target_shape(_target_snapshot()) is True
    assert is_legacy_shape(_target_snapshot()) is False


def test_preflight_is_green_before_backups_when_not_required() -> None:
    archive_name = "ml_radar_pre_source_identity_v01_20260722t120000z"
    report = _build(
        phase="preflight",
        archive_name=archive_name,
        catalog=_catalog(archive_name=archive_name, archive_exists=False),
        operational_snapshot=_legacy_snapshot(),
        candidate_snapshot=_target_snapshot(),
    )

    assert report["verdict"]["ok"] is True
    assert report["verdict"]["promotion_preflight_ready"] is True
    assert report["verdict"]["required_failed_count"] == 0
    assert "operational_backup_non_empty" not in report["checks"]


def test_preflight_fails_when_candidate_has_active_connection() -> None:
    report = _build(
        phase="preflight",
        catalog=_catalog(candidate_connections=1),
        operational_snapshot=_legacy_snapshot(),
        candidate_snapshot=_target_snapshot(),
    )

    assert report["verdict"]["ok"] is False
    assert "candidate_external_connections_zero" in report["verdict"][
        "required_failed_checks"
    ]


def test_preflight_fails_when_candidate_identity_count_is_wrong() -> None:
    candidate = _target_snapshot()
    candidate["identity"]["source_observation_id_unique_count"] = 88177
    report = _build(
        phase="preflight",
        catalog=_catalog(),
        operational_snapshot=_legacy_snapshot(),
        candidate_snapshot=candidate,
    )

    assert report["verdict"]["ok"] is False
    assert "candidate_source_observation_ids_unique" in report["verdict"][
        "required_failed_checks"
    ]


def test_preflight_requires_all_backup_evidence_when_requested() -> None:
    report = _build(
        phase="preflight",
        catalog=_catalog(),
        operational_snapshot=_legacy_snapshot(),
        candidate_snapshot=_target_snapshot(),
        require_backups=True,
    )

    assert report["verdict"]["ok"] is False
    assert report["verdict"]["required_failed_count"] == 4
    assert "candidate_backup_list_non_empty" in report["verdict"][
        "required_failed_checks"
    ]


def test_post_promotion_is_green_with_retained_legacy_archive() -> None:
    archive_name = "ml_radar_pre_source_identity_v01_20260722t120000z"
    report = _build(
        phase="post-promotion",
        archive_name=archive_name,
        catalog=_catalog(
            candidate_exists=False,
            archive_name=archive_name,
            archive_exists=True,
        ),
        operational_snapshot=_target_snapshot("ml_radar"),
        candidate_snapshot={"dbname": "candidate", "exists": False},
        archive_snapshot=_legacy_snapshot(archive_name),
        backups=_complete_backup_evidence(),
    )

    assert report["verdict"]["ok"] is True
    assert report["verdict"]["operational_promotion_validated"] is True
    assert report["verdict"]["rollback_database_retained"] is True
    assert report["verdict"]["required_failed_count"] == 0


def test_post_promotion_fails_without_archive_database() -> None:
    archive_name = "ml_radar_pre_source_identity_v01_20260722t120000z"
    report = _build(
        phase="post-promotion",
        archive_name=archive_name,
        catalog=_catalog(
            candidate_exists=False,
            archive_name=archive_name,
            archive_exists=False,
        ),
        operational_snapshot=_target_snapshot("ml_radar"),
        candidate_snapshot={"dbname": "candidate", "exists": False},
        archive_snapshot={"dbname": archive_name, "exists": False},
        backups=_complete_backup_evidence(),
    )

    assert report["verdict"]["ok"] is False
    assert "archive_database_exists" in report["verdict"][
        "required_failed_checks"
    ]
    assert "archive_legacy_shape" in report["verdict"][
        "required_failed_checks"
    ]


def test_validator_declares_no_database_mutation_capabilities() -> None:
    assert MUTATION_CAPABILITIES
    assert all(value is False for value in MUTATION_CAPABILITIES.values())


def test_parser_requires_phase_and_accepts_backup_evidence_paths() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "--phase",
            "preflight",
            "--strict",
            "--archive-dbname",
            "ml_radar_pre_source_identity_v01_20260722t120000z",
            "--require-backups",
            "--operational-backup-path",
            "backups/postgres/operational.dump",
            "--candidate-backup-path",
            "backups/postgres/candidate.dump",
            "--operational-backup-list-path",
            "backups/postgres/operational.list.txt",
            "--candidate-backup-list-path",
            "backups/postgres/candidate.list.txt",
        ]
    )

    assert args.phase == "preflight"
    assert args.strict is True
    assert args.require_backups is True
    assert args.operational_backup_path == Path(
        "backups/postgres/operational.dump"
    )


class _UniqueConstraintCursor:
    def __init__(self) -> None:
        self.executed = False

    def execute(self, query: str, params: tuple[str, ...]) -> None:
        self.executed = True
        assert "array_agg" not in query
        assert params == ("canonical_source_links",)

    def fetchall(self) -> list[dict[str, object]]:
        assert self.executed is True
        return [
            {
                "constraint_name": (
                    "canonical_source_links_canonical_id_"
                    "source_observation_id_key"
                ),
                "column_name": "canonical_id",
                "ordinal_position": 1,
            },
            {
                "constraint_name": (
                    "canonical_source_links_canonical_id_"
                    "source_observation_id_key"
                ),
                "column_name": "source_observation_id",
                "ordinal_position": 2,
            },
        ]


def test_unique_constraints_avoids_driver_specific_array_decoding() -> None:
    cursor = _UniqueConstraintCursor()

    constraints = _unique_constraints(cursor, "canonical_source_links")

    assert constraints == [["canonical_id", "source_observation_id"]]
