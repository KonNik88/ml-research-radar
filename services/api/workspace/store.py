from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator
from uuid import UUID

import psycopg
from psycopg import errors
from psycopg.rows import dict_row

from services.api.workspace.errors import (
    CollectionNameConflictError,
    CollectionNotFoundError,
    WorkspaceUnavailableError,
    WorkspaceValidationError,
)


@dataclass(frozen=True, slots=True)
class WorkspacePostgresConfig:
    database_url: str | None = None
    host: str = "127.0.0.1"
    port: int = 15432
    dbname: str = "ml_radar"
    user: str = "ml_radar"
    password: str = "ml_radar_dev"
    connect_timeout_sec: int = 5

    def psycopg_conninfo(self) -> str | None:
        if self.database_url is None:
            return None

        return self.database_url.replace(
            "postgresql+psycopg://",
            "postgresql://",
            1,
        )


class WorkspaceStore:
    """PostgreSQL persistence for user-authored workspace state only."""

    def __init__(self, config: WorkspacePostgresConfig) -> None:
        self._config = config

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        conninfo = self._config.psycopg_conninfo()
        try:
            if conninfo is not None:
                conn = psycopg.connect(
                    conninfo,
                    connect_timeout=self._config.connect_timeout_sec,
                    row_factory=dict_row,
                )
            else:
                conn = psycopg.connect(
                    host=self._config.host,
                    port=self._config.port,
                    dbname=self._config.dbname,
                    user=self._config.user,
                    password=self._config.password,
                    connect_timeout=self._config.connect_timeout_sec,
                    row_factory=dict_row,
                )
        except psycopg.Error as exc:
            raise WorkspaceUnavailableError() from exc

        try:
            yield conn
        finally:
            conn.close()

    def ping(self) -> bool:
        try:
            with self.connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                row = cur.fetchone()
                return bool(row and row["ok"] == 1)
        except WorkspaceUnavailableError:
            raise
        except psycopg.Error as exc:
            raise WorkspaceUnavailableError() from exc

    def create_collection(
        self,
        *,
        collection_id: UUID,
        name: str,
        description: str | None,
    ) -> dict[str, Any]:
        sql = """
        INSERT INTO workspace.research_collections (
            collection_id,
            name,
            description
        )
        VALUES (%s, %s, %s)
        RETURNING
            collection_id,
            name,
            description,
            created_at,
            updated_at,
            0::bigint AS item_count
        """
        try:
            with self.connection() as conn, conn.cursor() as cur:
                cur.execute(sql, (collection_id, name, description))
                row = cur.fetchone()
                conn.commit()
        except errors.UniqueViolation as exc:
            raise CollectionNameConflictError(name) from exc
        except errors.CheckViolation as exc:
            raise WorkspaceValidationError(
                "Collection values violate workspace storage constraints"
            ) from exc
        except WorkspaceUnavailableError:
            raise
        except psycopg.Error as exc:
            raise WorkspaceUnavailableError() from exc

        if row is None:
            raise WorkspaceUnavailableError()
        return self._normalize_collection_row(row)

    def list_collections(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        sql = """
        SELECT
            collection.collection_id,
            collection.name,
            collection.description,
            collection.created_at,
            collection.updated_at,
            COUNT(item.canonical_id)::bigint AS item_count
        FROM workspace.research_collections AS collection
        LEFT JOIN workspace.research_collection_items AS item
          ON item.collection_id = collection.collection_id
        GROUP BY collection.collection_id
        ORDER BY
            collection.updated_at DESC,
            lower(collection.name) ASC,
            collection.collection_id ASC
        LIMIT %s OFFSET %s
        """
        try:
            with self.connection() as conn, conn.cursor() as cur:
                cur.execute(sql, (limit, offset))
                rows = cur.fetchall()
        except WorkspaceUnavailableError:
            raise
        except psycopg.Error as exc:
            raise WorkspaceUnavailableError() from exc

        return [self._normalize_collection_row(row) for row in rows]

    def count_collections(self) -> int:
        sql = "SELECT COUNT(*) AS total FROM workspace.research_collections"
        try:
            with self.connection() as conn, conn.cursor() as cur:
                cur.execute(sql)
                row = cur.fetchone()
        except WorkspaceUnavailableError:
            raise
        except psycopg.Error as exc:
            raise WorkspaceUnavailableError() from exc

        return int(row["total"]) if row else 0

    def get_collection(
        self,
        collection_id: UUID,
    ) -> dict[str, Any] | None:
        sql = """
        SELECT
            collection.collection_id,
            collection.name,
            collection.description,
            collection.created_at,
            collection.updated_at,
            COUNT(item.canonical_id)::bigint AS item_count
        FROM workspace.research_collections AS collection
        LEFT JOIN workspace.research_collection_items AS item
          ON item.collection_id = collection.collection_id
        WHERE collection.collection_id = %s
        GROUP BY collection.collection_id
        """
        try:
            with self.connection() as conn, conn.cursor() as cur:
                cur.execute(sql, (collection_id,))
                row = cur.fetchone()
        except WorkspaceUnavailableError:
            raise
        except psycopg.Error as exc:
            raise WorkspaceUnavailableError() from exc

        if row is None:
            return None
        return self._normalize_collection_row(row)

    def update_collection(
        self,
        collection_id: UUID,
        *,
        name: str | None,
        name_supplied: bool,
        description: str | None,
        description_supplied: bool,
    ) -> dict[str, Any] | None:
        sql = """
        UPDATE workspace.research_collections
        SET
            name = CASE WHEN %s THEN %s ELSE name END,
            description = CASE WHEN %s THEN %s ELSE description END,
            updated_at = CURRENT_TIMESTAMP
        WHERE collection_id = %s
        RETURNING
            collection_id,
            name,
            description,
            created_at,
            updated_at,
            (
                SELECT COUNT(*)::bigint
                FROM workspace.research_collection_items AS item
                WHERE item.collection_id =
                    workspace.research_collections.collection_id
            ) AS item_count
        """
        try:
            with self.connection() as conn, conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        name_supplied,
                        name,
                        description_supplied,
                        description,
                        collection_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
        except errors.UniqueViolation as exc:
            raise CollectionNameConflictError(name or "") from exc
        except errors.CheckViolation as exc:
            raise WorkspaceValidationError(
                "Collection values violate workspace storage constraints"
            ) from exc
        except WorkspaceUnavailableError:
            raise
        except psycopg.Error as exc:
            raise WorkspaceUnavailableError() from exc

        if row is None:
            return None
        return self._normalize_collection_row(row)

    def delete_collection(self, collection_id: UUID) -> bool:
        sql = """
        DELETE FROM workspace.research_collections
        WHERE collection_id = %s
        RETURNING collection_id
        """
        try:
            with self.connection() as conn, conn.cursor() as cur:
                cur.execute(sql, (collection_id,))
                deleted = cur.fetchone() is not None
                conn.commit()
        except WorkspaceUnavailableError:
            raise
        except psycopg.Error as exc:
            raise WorkspaceUnavailableError() from exc
        return deleted

    def list_items(self, collection_id: UUID) -> list[dict[str, Any]]:
        sql = """
        SELECT
            collection_id,
            canonical_id,
            note,
            reading_status,
            added_at,
            updated_at
        FROM workspace.research_collection_items
        WHERE collection_id = %s
        ORDER BY added_at DESC, canonical_id ASC
        """
        try:
            with self.connection() as conn, conn.cursor() as cur:
                cur.execute(sql, (collection_id,))
                rows = cur.fetchall()
        except WorkspaceUnavailableError:
            raise
        except psycopg.Error as exc:
            raise WorkspaceUnavailableError() from exc

        return [dict(row) for row in rows]

    def get_item(
        self,
        collection_id: UUID,
        canonical_id: str,
    ) -> dict[str, Any] | None:
        sql = """
        SELECT
            collection_id,
            canonical_id,
            note,
            reading_status,
            added_at,
            updated_at
        FROM workspace.research_collection_items
        WHERE collection_id = %s
          AND canonical_id = %s
        """
        try:
            with self.connection() as conn, conn.cursor() as cur:
                cur.execute(sql, (collection_id, canonical_id))
                row = cur.fetchone()
        except WorkspaceUnavailableError:
            raise
        except psycopg.Error as exc:
            raise WorkspaceUnavailableError() from exc

        return dict(row) if row is not None else None

    def upsert_item(
        self,
        *,
        collection_id: UUID,
        canonical_id: str,
        note: str | None,
        note_supplied: bool,
        reading_status: str | None,
        reading_status_supplied: bool,
        touch_collection: bool,
    ) -> dict[str, Any]:
        insert_status = reading_status if reading_status_supplied else "to_read"
        sql = """
        INSERT INTO workspace.research_collection_items AS stored (
            collection_id,
            canonical_id,
            note,
            reading_status
        )
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (collection_id, canonical_id)
        DO UPDATE SET
            note = CASE
                WHEN %s THEN EXCLUDED.note
                ELSE stored.note
            END,
            reading_status = CASE
                WHEN %s THEN EXCLUDED.reading_status
                ELSE stored.reading_status
            END,
            updated_at = CASE
                WHEN %s OR %s THEN CURRENT_TIMESTAMP
                ELSE stored.updated_at
            END
        RETURNING
            collection_id,
            canonical_id,
            note,
            reading_status,
            added_at,
            updated_at
        """
        try:
            with self.connection() as conn, conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        collection_id,
                        canonical_id,
                        note if note_supplied else None,
                        insert_status,
                        note_supplied,
                        reading_status_supplied,
                        note_supplied,
                        reading_status_supplied,
                    ),
                )
                row = cur.fetchone()
                if touch_collection:
                    cur.execute(
                        """
                        UPDATE workspace.research_collections
                        SET updated_at = CURRENT_TIMESTAMP
                        WHERE collection_id = %s
                        """,
                        (collection_id,),
                    )
                conn.commit()
        except errors.ForeignKeyViolation as exc:
            raise CollectionNotFoundError(collection_id) from exc
        except errors.CheckViolation as exc:
            raise WorkspaceValidationError(
                "Collection item values violate workspace storage constraints"
            ) from exc
        except WorkspaceUnavailableError:
            raise
        except psycopg.Error as exc:
            raise WorkspaceUnavailableError() from exc

        if row is None:
            raise WorkspaceUnavailableError()
        return dict(row)

    def update_item(
        self,
        *,
        collection_id: UUID,
        canonical_id: str,
        note: str | None,
        note_supplied: bool,
        reading_status: str | None,
        reading_status_supplied: bool,
    ) -> dict[str, Any] | None:
        sql = """
        UPDATE workspace.research_collection_items
        SET
            note = CASE WHEN %s THEN %s ELSE note END,
            reading_status = CASE
                WHEN %s THEN %s
                ELSE reading_status
            END,
            updated_at = CURRENT_TIMESTAMP
        WHERE collection_id = %s
          AND canonical_id = %s
        RETURNING
            collection_id,
            canonical_id,
            note,
            reading_status,
            added_at,
            updated_at
        """
        try:
            with self.connection() as conn, conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        note_supplied,
                        note,
                        reading_status_supplied,
                        reading_status,
                        collection_id,
                        canonical_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
        except errors.CheckViolation as exc:
            raise WorkspaceValidationError(
                "Collection item values violate workspace storage constraints"
            ) from exc
        except WorkspaceUnavailableError:
            raise
        except psycopg.Error as exc:
            raise WorkspaceUnavailableError() from exc

        return dict(row) if row is not None else None

    def delete_item(
        self,
        collection_id: UUID,
        canonical_id: str,
    ) -> bool:
        sql = """
        WITH deleted AS (
            DELETE FROM workspace.research_collection_items
            WHERE collection_id = %s
              AND canonical_id = %s
            RETURNING collection_id
        )
        UPDATE workspace.research_collections AS collection
        SET updated_at = CURRENT_TIMESTAMP
        FROM deleted
        WHERE collection.collection_id = deleted.collection_id
        RETURNING collection.collection_id
        """
        try:
            with self.connection() as conn, conn.cursor() as cur:
                cur.execute(sql, (collection_id, canonical_id))
                deleted = cur.fetchone() is not None
                conn.commit()
        except WorkspaceUnavailableError:
            raise
        except psycopg.Error as exc:
            raise WorkspaceUnavailableError() from exc
        return deleted

    @staticmethod
    def _normalize_collection_row(row: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(row)
        normalized["item_count"] = int(normalized.get("item_count") or 0)
        return normalized
