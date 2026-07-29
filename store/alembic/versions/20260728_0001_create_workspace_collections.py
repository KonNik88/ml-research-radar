"""Create durable Saved Research Collections workspace tables.

Revision ID: 20260728_0001
Revises:
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260728_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKSPACE_SCHEMA = "workspace"
COLLECTIONS_TABLE = "research_collections"
ITEMS_TABLE = "research_collection_items"


def upgrade() -> None:
    op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{WORKSPACE_SCHEMA}"'))

    op.create_table(
        COLLECTIONS_TABLE,
        sa.Column(
            "collection_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 200",
            name="ck_workspace_research_collections_name_length",
        ),
        sa.CheckConstraint(
            "description IS NULL OR char_length(description) <= 2000",
            name="ck_workspace_research_collections_description_length",
        ),
        sa.PrimaryKeyConstraint(
            "collection_id",
            name="pk_workspace_research_collections",
        ),
        schema=WORKSPACE_SCHEMA,
    )

    op.create_index(
        "uq_workspace_research_collections_name_normalized",
        COLLECTIONS_TABLE,
        [sa.text("lower(btrim(name))")],
        unique=True,
        schema=WORKSPACE_SCHEMA,
    )

    op.create_table(
        ITEMS_TABLE,
        sa.Column(
            "collection_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("canonical_id", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "reading_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'to_read'"),
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "btrim(canonical_id) <> ''",
            name="ck_workspace_research_collection_items_canonical_id_nonempty",
        ),
        sa.CheckConstraint(
            "note IS NULL OR char_length(note) <= 20000",
            name="ck_workspace_research_collection_items_note_length",
        ),
        sa.CheckConstraint(
            "reading_status IN ('to_read', 'reading', 'read')",
            name="ck_workspace_research_collection_items_reading_status",
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            [
                f"{WORKSPACE_SCHEMA}.{COLLECTIONS_TABLE}.collection_id",
            ],
            name="fk_workspace_research_collection_items_collection_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "collection_id",
            "canonical_id",
            name="pk_workspace_research_collection_items",
        ),
        schema=WORKSPACE_SCHEMA,
    )

    op.create_index(
        "ix_workspace_research_collection_items_canonical_id",
        ITEMS_TABLE,
        ["canonical_id"],
        unique=False,
        schema=WORKSPACE_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_research_collection_items_canonical_id",
        table_name=ITEMS_TABLE,
        schema=WORKSPACE_SCHEMA,
    )
    op.drop_table(ITEMS_TABLE, schema=WORKSPACE_SCHEMA)

    op.drop_index(
        "uq_workspace_research_collections_name_normalized",
        table_name=COLLECTIONS_TABLE,
        schema=WORKSPACE_SCHEMA,
    )
    op.drop_table(COLLECTIONS_TABLE, schema=WORKSPACE_SCHEMA)

    # Intentionally no CASCADE: an unexpected workspace object must make a
    # destructive downgrade fail closed.
    op.execute(sa.text(f'DROP SCHEMA IF EXISTS "{WORKSPACE_SCHEMA}"'))
