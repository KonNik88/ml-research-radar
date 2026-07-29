from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL_ENV = "ML_RADAR_WORKSPACE_TEST_DATABASE_URL"
OPERATIONAL_DATABASE_NAME = "ml_radar"
REVISION = "20260728_0001"


@dataclass(frozen=True)
class MigrationHarness:
    engine: Engine
    alembic_config: Config


def _require_disposable_test_url() -> URL:
    raw_url = os.getenv(TEST_DATABASE_URL_ENV)
    if not raw_url:
        pytest.skip(
            f"{TEST_DATABASE_URL_ENV} is not set; "
            "workspace migration integration test was not requested"
        )

    try:
        url = make_url(raw_url)
    except sa.exc.ArgumentError as exc:
        pytest.fail(f"{TEST_DATABASE_URL_ENV} is not a valid SQLAlchemy URL: {exc}")

    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")

    if url.drivername != "postgresql+psycopg":
        pytest.fail(
            f"{TEST_DATABASE_URL_ENV} must use PostgreSQL with the psycopg driver"
        )

    database = (url.database or "").lower()
    if database == OPERATIONAL_DATABASE_NAME:
        pytest.fail("Refusing to run destructive migration tests against ml_radar")

    if not re.search(r"(?:^test_|_test$|_test_)", database):
        pytest.fail(
            "Disposable database name must start with 'test_' or contain/end in '_test'"
        )

    return url


def _alembic_config() -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(PROJECT_ROOT / "store" / "alembic"),
    )
    return config


def _reset_workspace_migration_state(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql('DROP SCHEMA IF EXISTS "workspace" CASCADE')
        connection.exec_driver_sql("DROP TABLE IF EXISTS public.alembic_version")


def test_database_guard_rejects_operational_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        TEST_DATABASE_URL_ENV,
        "postgresql+psycopg://ml_radar:password@127.0.0.1:15432/ml_radar",
    )

    with pytest.raises(
        pytest.fail.Exception,
        match="Refusing to run destructive migration tests against ml_radar",
    ):
        _require_disposable_test_url()


def test_database_guard_rejects_unmarked_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        TEST_DATABASE_URL_ENV,
        "postgresql+psycopg://ml_radar:password@127.0.0.1:15432/staging",
    )

    with pytest.raises(
        pytest.fail.Exception,
        match="Disposable database name",
    ):
        _require_disposable_test_url()


def test_database_guard_accepts_explicit_test_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        TEST_DATABASE_URL_ENV,
        "postgresql://ml_radar:password@127.0.0.1:15432/ml_radar_collections_test",
    )

    url = _require_disposable_test_url()

    assert url.drivername == "postgresql+psycopg"
    assert url.database == "ml_radar_collections_test"


@pytest.fixture
def migration_harness(monkeypatch: pytest.MonkeyPatch) -> MigrationHarness:
    url = _require_disposable_test_url()
    engine = sa.create_engine(url, poolclass=NullPool)

    try:
        with engine.connect() as connection:
            assert connection.scalar(sa.text("SELECT 1")) == 1

        _reset_workspace_migration_state(engine)
        monkeypatch.setenv(
            "ML_RADAR_WORKSPACE_DATABASE_URL",
            url.render_as_string(hide_password=False),
        )

        yield MigrationHarness(
            engine=engine,
            alembic_config=_alembic_config(),
        )
    finally:
        _reset_workspace_migration_state(engine)
        engine.dispose()


def _constraint_definitions(engine: Engine, table_name: str) -> dict[str, str]:
    query = sa.text(
        """
        SELECT constraint_name, pg_get_constraintdef(pc.oid) AS definition
        FROM information_schema.table_constraints tc
        JOIN pg_constraint pc
          ON pc.conname = tc.constraint_name
         AND pc.conrelid = (
             quote_ident(tc.table_schema) || '.' || quote_ident(tc.table_name)
         )::regclass
        WHERE tc.table_schema = 'workspace'
          AND tc.table_name = :table_name
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"table_name": table_name}).mappings()
        return {str(row["constraint_name"]): str(row["definition"]) for row in rows}


def _index_definitions(engine: Engine, table_name: str) -> dict[str, str]:
    query = sa.text(
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'workspace'
          AND tablename = :table_name
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"table_name": table_name}).mappings()
        return {str(row["indexname"]): str(row["indexdef"]) for row in rows}


def test_workspace_migration_round_trip_and_constraints(
    migration_harness: MigrationHarness,
) -> None:
    engine = migration_harness.engine
    config = migration_harness.alembic_config

    command.upgrade(config, "head")

    inspector = sa.inspect(engine)
    assert "workspace" in inspector.get_schema_names()
    assert set(inspector.get_table_names(schema="workspace")) == {
        "research_collections",
        "research_collection_items",
    }

    collection_columns = {
        column["name"]
        for column in inspector.get_columns(
            "research_collections",
            schema="workspace",
        )
    }
    assert collection_columns == {
        "collection_id",
        "name",
        "description",
        "created_at",
        "updated_at",
    }

    item_columns = {
        column["name"]
        for column in inspector.get_columns(
            "research_collection_items",
            schema="workspace",
        )
    }
    assert item_columns == {
        "collection_id",
        "canonical_id",
        "note",
        "reading_status",
        "added_at",
        "updated_at",
    }

    assert inspector.get_pk_constraint(
        "research_collections",
        schema="workspace",
    )["constrained_columns"] == ["collection_id"]
    assert inspector.get_pk_constraint(
        "research_collection_items",
        schema="workspace",
    )["constrained_columns"] == ["collection_id", "canonical_id"]

    foreign_keys = inspector.get_foreign_keys(
        "research_collection_items",
        schema="workspace",
    )
    assert len(foreign_keys) == 1
    assert foreign_keys[0]["constrained_columns"] == ["collection_id"]
    assert foreign_keys[0]["referred_schema"] == "workspace"
    assert foreign_keys[0]["referred_table"] == "research_collections"
    assert foreign_keys[0]["referred_columns"] == ["collection_id"]
    assert foreign_keys[0]["options"]["ondelete"] == "CASCADE"

    item_constraints = _constraint_definitions(
        engine,
        "research_collection_items",
    )
    assert "ck_workspace_research_collection_items_reading_status" in item_constraints
    assert (
        "ck_workspace_research_collection_items_canonical_id_nonempty"
        in item_constraints
    )
    assert "canonical_documents" not in " ".join(item_constraints.values())

    collection_indexes = _index_definitions(
        engine,
        "research_collections",
    )
    normalized_name_index = collection_indexes[
        "uq_workspace_research_collections_name_normalized"
    ].lower()
    assert "unique index" in normalized_name_index
    assert "lower(btrim(name))" in normalized_name_index

    item_indexes = _index_definitions(
        engine,
        "research_collection_items",
    )
    assert "ix_workspace_research_collection_items_canonical_id" in item_indexes

    with engine.connect() as connection:
        assert (
            connection.scalar(sa.text("SELECT version_num FROM public.alembic_version"))
            == REVISION
        )

    # A second upgrade is intentionally a no-op.
    command.upgrade(config, "head")

    collection_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO workspace.research_collections (
                    collection_id,
                    name,
                    description
                )
                VALUES (:collection_id, :name, :description)
                """
            ),
            {
                "collection_id": collection_id,
                "name": "My Papers",
                "description": "Migration integration test",
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO workspace.research_collection_items (
                    collection_id,
                    canonical_id,
                    note
                )
                VALUES (:collection_id, :canonical_id, :note)
                """
            ),
            {
                "collection_id": collection_id,
                "canonical_id": "paper-not-present-in-current-corpus",
                "note": "Soft references must be allowed by the database.",
            },
        )

    with engine.connect() as connection:
        stored_status = connection.scalar(
            sa.text(
                """
                SELECT reading_status
                FROM workspace.research_collection_items
                WHERE collection_id = :collection_id
                """
            ),
            {"collection_id": collection_id},
        )
    assert stored_status == "to_read"

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO workspace.research_collections (
                        collection_id,
                        name
                    )
                    VALUES (:collection_id, :name)
                    """
                ),
                {
                    "collection_id": uuid4(),
                    "name": "  mY pApErS  ",
                },
            )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO workspace.research_collection_items (
                        collection_id,
                        canonical_id
                    )
                    VALUES (:collection_id, :canonical_id)
                    """
                ),
                {
                    "collection_id": collection_id,
                    "canonical_id": "paper-not-present-in-current-corpus",
                },
            )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO workspace.research_collection_items (
                        collection_id,
                        canonical_id,
                        reading_status
                    )
                    VALUES (:collection_id, :canonical_id, :reading_status)
                    """
                ),
                {
                    "collection_id": collection_id,
                    "canonical_id": "another-paper",
                    "reading_status": "abandoned",
                },
            )

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                DELETE FROM workspace.research_collections
                WHERE collection_id = :collection_id
                """
            ),
            {"collection_id": collection_id},
        )

    with engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text("SELECT COUNT(*) FROM workspace.research_collection_items")
            )
            == 0
        )

    command.downgrade(config, "base")

    assert "workspace" not in sa.inspect(engine).get_schema_names()


def test_workspace_migration_preserves_existing_canonical_table(
    migration_harness: MigrationHarness,
) -> None:
    engine = migration_harness.engine
    config = migration_harness.alembic_config

    with engine.connect() as connection:
        canonical_existed = bool(
            connection.scalar(
                sa.text("SELECT to_regclass('public.canonical_documents') IS NOT NULL")
            )
        )

    try:
        if not canonical_existed:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    """
                    CREATE TABLE public.canonical_documents (
                        canonical_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO public.canonical_documents (
                            canonical_id,
                            title
                        )
                        VALUES (:canonical_id, :title)
                        """
                    ),
                    {
                        "canonical_id": "migration-sentinel-paper",
                        "title": "Migration sentinel",
                    },
                )

        with engine.connect() as connection:
            count_before = int(
                connection.scalar(
                    sa.text("SELECT COUNT(*) FROM public.canonical_documents")
                )
                or 0
            )

        command.upgrade(config, "head")

        with engine.connect() as connection:
            assert (
                int(
                    connection.scalar(
                        sa.text("SELECT COUNT(*) FROM public.canonical_documents")
                    )
                    or 0
                )
                == count_before
            )

        command.downgrade(config, "base")

        with engine.connect() as connection:
            assert connection.scalar(
                sa.text("SELECT to_regclass('public.canonical_documents') IS NOT NULL")
            )
            assert (
                int(
                    connection.scalar(
                        sa.text("SELECT COUNT(*) FROM public.canonical_documents")
                    )
                    or 0
                )
                == count_before
            )
    finally:
        if not canonical_existed:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "DROP TABLE IF EXISTS public.canonical_documents"
                )
