from __future__ import annotations

import os
from logging.config import fileConfig

import sqlalchemy as sa
from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import URL, make_url


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = None


def _database_url() -> URL:
    explicit_url = os.getenv("ML_RADAR_WORKSPACE_DATABASE_URL")
    if explicit_url:
        url = make_url(explicit_url)
        if url.drivername == "postgresql":
            url = url.set(drivername="postgresql+psycopg")
        return url

    return URL.create(
        drivername="postgresql+psycopg",
        username=os.getenv("ML_RADAR_POSTGRES_USER", "ml_radar"),
        password=os.getenv("ML_RADAR_POSTGRES_PASSWORD", "ml_radar_dev"),
        host=os.getenv("ML_RADAR_POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("ML_RADAR_POSTGRES_PORT", "15432")),
        database=os.getenv("ML_RADAR_POSTGRES_DBNAME", "ml_radar"),
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = sa.create_engine(
        _database_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
