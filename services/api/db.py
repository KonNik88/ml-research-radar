from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row


@dataclass(slots=True)
class PostgresConfig:
    host: str = "127.0.0.1"
    port: int = 15432
    dbname: str = "ml_radar"
    user: str = "ml_radar"
    password: str = "ml_radar_dev"


class PostgresDocumentStore:
    def __init__(self, config: PostgresConfig) -> None:
        self._config = config

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        conn = psycopg.connect(
            host=self._config.host,
            port=self._config.port,
            dbname=self._config.dbname,
            user=self._config.user,
            password=self._config.password,
            row_factory=dict_row,
        )
        try:
            yield conn
        finally:
            conn.close()

    def ping(self) -> bool:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            row = cur.fetchone()
            return bool(row and row["ok"] == 1)

    def get_document_by_id(self, canonical_id: str) -> dict[str, Any] | None:
        query = """
        SELECT *
        FROM canonical_documents
        WHERE canonical_id = %s
        """
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(query, (canonical_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._normalize_row(row)

    def list_documents(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "year_desc",
    ) -> list[dict[str, Any]]:
        order_by = self._build_order_by(sort_by)

        query = f"""
        SELECT *
        FROM canonical_documents
        {order_by}
        LIMIT %s OFFSET %s
        """

        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(query, (limit, offset))
            rows = cur.fetchall()
            return [self._normalize_row(row) for row in rows]

    def search_documents(
        self,
        *,
        query_text: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        category: str | None = None,
        source: str | None = None,
        publication_type: str | None = None,
        venue: str | None = None,
        is_open_access: bool | None = None,
        has_code_link: bool | None = None,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "year_desc",
    ) -> list[dict[str, Any]]:
        where_clauses: list[str] = []
        params: list[Any] = []

        if query_text:
            where_clauses.append(
                """
                (
                    title ILIKE %s
                    OR COALESCE(abstract, '') ILIKE %s
                    OR COALESCE(venue, '') ILIKE %s
                    OR COALESCE(journal, '') ILIKE %s
                    OR COALESCE(conference, '') ILIKE %s
                    OR COALESCE(publisher, '') ILIKE %s
                )
                """
            )
            pattern = f"%{query_text}%"
            params.extend([pattern, pattern, pattern, pattern, pattern, pattern])

        if year_from is not None:
            where_clauses.append("year >= %s")
            params.append(year_from)

        if year_to is not None:
            where_clauses.append("year <= %s")
            params.append(year_to)

        if category:
            where_clauses.append("categories @> %s::jsonb")
            params.append(json.dumps([category], ensure_ascii=False))

        if source:
            where_clauses.append(
                """
                canonical_id IN (
                    SELECT canonical_id
                    FROM canonical_source_links
                    WHERE source = %s
                )
                """
            )
            params.append(source)

        if publication_type:
            where_clauses.append("publication_type = %s")
            params.append(publication_type)

        if venue:
            where_clauses.append("LOWER(COALESCE(venue, '')) = LOWER(%s)")
            params.append(venue)

        if is_open_access is not None:
            where_clauses.append("is_open_access = %s")
            params.append(is_open_access)

        if has_code_link is not None:
            where_clauses.append("has_code_link = %s")
            params.append(has_code_link)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        order_by = self._build_order_by(sort_by)

        sql = f"""
        SELECT *
        FROM canonical_documents
        {where_sql}
        {order_by}
        LIMIT %s OFFSET %s
        """

        params.extend([limit, offset])

        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [self._normalize_row(row) for row in rows]



    def search_search_documents(
        self,
        *,
        query_text: str,
        year_from: int | None = None,
        year_to: int | None = None,
        category: str | None = None,
        source: str | None = None,
        publication_type: str | None = None,
        venue: str | None = None,
        is_open_access: bool | None = None,
        has_code_link: bool | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where_clauses: list[str] = []
        params: list[Any] = []

        pattern = f"%{query_text}%"
        where_clauses.append(
            """
            (
                title ILIKE %s
                OR COALESCE(abstract, '') ILIKE %s
                OR COALESCE(authors::text, '') ILIKE %s
            )
            """
        )
        params.extend([pattern, pattern, pattern])

        if year_from is not None:
            where_clauses.append("year >= %s")
            params.append(year_from)

        if year_to is not None:
            where_clauses.append("year <= %s")
            params.append(year_to)

        if category:
            where_clauses.append(
                """
                (
                    categories @> %s::jsonb
                    OR tags @> %s::jsonb
                    OR concepts @> %s::jsonb
                    OR keywords @> %s::jsonb
                )
                """
            )
            category_json = json.dumps([category], ensure_ascii=False)
            params.extend([category_json, category_json, category_json, category_json])

        if source:
            where_clauses.append(
                """
                canonical_id IN (
                    SELECT canonical_id
                    FROM canonical_source_links
                    WHERE source = %s
                )
                """
            )
            params.append(source)

        if publication_type:
            where_clauses.append("publication_type = %s")
            params.append(publication_type)

        if venue:
            where_clauses.append(
                """
                (
                    LOWER(COALESCE(venue, '')) = LOWER(%s)
                    OR LOWER(COALESCE(journal, '')) = LOWER(%s)
                    OR LOWER(COALESCE(conference, '')) = LOWER(%s)
                    OR LOWER(COALESCE(publisher, '')) = LOWER(%s)
                )
                """
            )
            params.extend([venue, venue, venue, venue])

        if is_open_access is not None:
            where_clauses.append("is_open_access = %s")
            params.append(is_open_access)

        if has_code_link is not None:
            where_clauses.append("has_code_link = %s")
            params.append(has_code_link)

        where_sql = "WHERE " + " AND ".join(where_clauses)

        sql = f"""
        SELECT
            *,
            (
                CASE
                    WHEN LOWER(title) = LOWER(%s) THEN 100.0
                    WHEN title ILIKE %s THEN 30.0
                    ELSE 0.0
                END
                + CASE
                    WHEN COALESCE(abstract, '') ILIKE %s THEN 10.0
                    ELSE 0.0
                END
                + CASE
                    WHEN COALESCE(authors::text, '') ILIKE %s THEN 5.0
                    ELSE 0.0
                END
            ) AS score
        FROM canonical_documents
        {where_sql}
        ORDER BY score DESC, year DESC NULLS LAST, canonical_id ASC
        LIMIT %s OFFSET %s
        """

        score_exact = query_text
        score_pattern = pattern
        final_params = [score_exact, score_pattern, score_pattern, score_pattern, *params, limit, offset]

        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, final_params)
            rows = cur.fetchall()
            return [self._normalize_row(row) for row in rows]

    def count_search_documents(
        self,
        *,
        query_text: str,
        year_from: int | None = None,
        year_to: int | None = None,
        category: str | None = None,
        source: str | None = None,
        publication_type: str | None = None,
        venue: str | None = None,
        is_open_access: bool | None = None,
        has_code_link: bool | None = None,
    ) -> int:
        where_clauses: list[str] = []
        params: list[Any] = []

        pattern = f"%{query_text}%"
        where_clauses.append(
            """
            (
                title ILIKE %s
                OR COALESCE(abstract, '') ILIKE %s
                OR COALESCE(authors::text, '') ILIKE %s
            )
            """
        )
        params.extend([pattern, pattern, pattern])

        if year_from is not None:
            where_clauses.append("year >= %s")
            params.append(year_from)

        if year_to is not None:
            where_clauses.append("year <= %s")
            params.append(year_to)

        if category:
            where_clauses.append(
                """
                (
                    categories @> %s::jsonb
                    OR tags @> %s::jsonb
                    OR concepts @> %s::jsonb
                    OR keywords @> %s::jsonb
                )
                """
            )
            category_json = json.dumps([category], ensure_ascii=False)
            params.extend([category_json, category_json, category_json, category_json])

        if source:
            where_clauses.append(
                """
                canonical_id IN (
                    SELECT canonical_id
                    FROM canonical_source_links
                    WHERE source = %s
                )
                """
            )
            params.append(source)

        if publication_type:
            where_clauses.append("publication_type = %s")
            params.append(publication_type)

        if venue:
            where_clauses.append(
                """
                (
                    LOWER(COALESCE(venue, '')) = LOWER(%s)
                    OR LOWER(COALESCE(journal, '')) = LOWER(%s)
                    OR LOWER(COALESCE(conference, '')) = LOWER(%s)
                    OR LOWER(COALESCE(publisher, '')) = LOWER(%s)
                )
                """
            )
            params.extend([venue, venue, venue, venue])

        if is_open_access is not None:
            where_clauses.append("is_open_access = %s")
            params.append(is_open_access)

        if has_code_link is not None:
            where_clauses.append("has_code_link = %s")
            params.append(has_code_link)

        where_sql = "WHERE " + " AND ".join(where_clauses)

        sql = f"""
        SELECT COUNT(*) AS total
        FROM canonical_documents
        {where_sql}
        """

        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return int(row["total"]) if row else 0

    def count_documents(
        self,
        *,
        query_text: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        category: str | None = None,
        source: str | None = None,
        publication_type: str | None = None,
        venue: str | None = None,
        is_open_access: bool | None = None,
        has_code_link: bool | None = None,
    ) -> int:
        where_clauses: list[str] = []
        params: list[Any] = []

        if query_text:
            where_clauses.append(
                """
                (
                    title ILIKE %s
                    OR COALESCE(abstract, '') ILIKE %s
                    OR COALESCE(venue, '') ILIKE %s
                    OR COALESCE(journal, '') ILIKE %s
                    OR COALESCE(conference, '') ILIKE %s
                    OR COALESCE(publisher, '') ILIKE %s
                )
                """
            )
            pattern = f"%{query_text}%"
            params.extend([pattern, pattern, pattern, pattern, pattern, pattern])

        if year_from is not None:
            where_clauses.append("year >= %s")
            params.append(year_from)

        if year_to is not None:
            where_clauses.append("year <= %s")
            params.append(year_to)

        if category:
            where_clauses.append("categories @> %s::jsonb")
            params.append(json.dumps([category], ensure_ascii=False))

        if source:
            where_clauses.append(
                """
                canonical_id IN (
                    SELECT canonical_id
                    FROM canonical_source_links
                    WHERE source = %s
                )
                """
            )
            params.append(source)

        if publication_type:
            where_clauses.append("publication_type = %s")
            params.append(publication_type)

        if venue:
            where_clauses.append("LOWER(COALESCE(venue, '')) = LOWER(%s)")
            params.append(venue)

        if is_open_access is not None:
            where_clauses.append("is_open_access = %s")
            params.append(is_open_access)

        if has_code_link is not None:
            where_clauses.append("has_code_link = %s")
            params.append(has_code_link)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        sql = f"""
        SELECT COUNT(*) AS total
        FROM canonical_documents
        {where_sql}
        """

        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return int(row["total"]) if row else 0

    @staticmethod
    def _build_order_by(sort_by: str) -> str:
        if sort_by == "year_asc":
            return "ORDER BY year ASC NULLS LAST, canonical_id ASC"
        if sort_by == "year_desc":
            return "ORDER BY year DESC NULLS LAST, canonical_id ASC"
        if sort_by == "title_asc":
            return "ORDER BY title ASC NULLS LAST, canonical_id ASC"
        return "ORDER BY year DESC NULLS LAST, canonical_id ASC"

    @staticmethod
    def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(row)

        json_fields = [
            "authors",
            "source_ids",
            "external_ids",
            "categories",
            "concepts",
            "keywords",
            "tags",
            "referenced_ids",
            "referenced_dois",
            "referenced_arxiv_ids",
            "code_links",
            "dataset_links",
            "model_links",
            "doc_ids",
        ]

        for field in json_fields:
            value = normalized.get(field)
            if value is None:
                continue
            if isinstance(value, str):
                try:
                    normalized[field] = json.loads(value)
                except json.JSONDecodeError:
                    pass

        return normalized