from __future__ import annotations

import io
import re
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
ALEMBIC_DIR = PROJECT_ROOT / "store" / "alembic"
REVISION = "20260728_0001"


def _config_with_buffer() -> tuple[Config, io.StringIO]:
    output = io.StringIO()
    config = Config(
        str(ALEMBIC_INI),
        stdout=output,
        output_buffer=output,
    )
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    return config, output


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.lower().replace('"', "").split())


def test_alembic_has_one_workspace_head() -> None:
    config, _output = _config_with_buffer()
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == [REVISION]

    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision is None
    assert revision.module.WORKSPACE_SCHEMA == "workspace"


def test_upgrade_sql_renders_workspace_contract_without_database() -> None:
    config, output = _config_with_buffer()

    command.upgrade(config, "head", sql=True)

    sql = _normalize_sql(output.getvalue())

    assert "create schema if not exists workspace" in sql
    assert "create table workspace.research_collections" in sql
    assert "create table workspace.research_collection_items" in sql

    assert "primary key (collection_id)" in sql
    assert "primary key (collection_id, canonical_id)" in sql
    assert "reading_status in ('to_read', 'reading', 'read')" in sql
    assert "btrim(canonical_id) <> ''" in sql

    assert (
        "create unique index uq_workspace_research_collections_name_normalized "
        "on workspace.research_collections (lower(btrim(name)))"
    ) in sql
    assert (
        "create index ix_workspace_research_collection_items_canonical_id "
        "on workspace.research_collection_items (canonical_id)"
    ) in sql

    assert (
        "foreign key(collection_id) references "
        "workspace.research_collections (collection_id) on delete cascade"
    ) in sql
    assert "canonical_documents" not in sql


def test_downgrade_sql_fails_closed_without_schema_cascade() -> None:
    config, output = _config_with_buffer()

    command.downgrade(config, f"{REVISION}:base", sql=True)

    sql = _normalize_sql(output.getvalue())

    assert "drop table workspace.research_collection_items" in sql
    assert "drop table workspace.research_collections" in sql
    assert "drop schema if exists workspace" in sql
    assert not re.search(
        r"drop schema if exists workspace(?:\s+restrict)?\s+cascade",
        sql,
    )


def test_legacy_init_sql_does_not_own_workspace_tables() -> None:
    sql_root = PROJECT_ROOT / "store" / "sql"
    legacy_sql = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(sql_root.glob("*.sql"))
    ).lower()

    assert "research_collections" not in legacy_sql
    assert "research_collection_items" not in legacy_sql
    assert "create schema workspace" not in legacy_sql
    assert "create schema if not exists workspace" not in legacy_sql


def test_contract_documents_durable_soft_reference_boundary() -> None:
    contract = (PROJECT_ROOT / "docs" / "saved_research_collections_v0.1.md").read_text(
        encoding="utf-8"
    )

    required_statements = [
        "durable_user_state = true",
        "workspace.research_collections",
        "workspace.research_collection_items",
        "canonical_id` deliberately has no foreign key",
        "ON DELETE CASCADE",
        "ML_RADAR_WORKSPACE_DATABASE_URL",
        "local single-user",
    ]

    for statement in required_statements:
        assert statement in contract
