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
        SELECT cd.*
        FROM canonical_documents cd
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
        has_trusted_artifact: bool | None = None,
        has_trusted_code_artifact: bool | None = None,
        has_trusted_dataset_artifact: bool | None = None,
        has_trusted_model_artifact: bool | None = None,
        has_trusted_demo_artifact: bool | None = None,
        artifact_provider: str | None = None,
        artifact_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "year_desc",
    ) -> list[dict[str, Any]]:
        where_clauses, params = self._build_document_where(
            query_text=query_text,
            year_from=year_from,
            year_to=year_to,
            category=category,
            source=source,
            publication_type=publication_type,
            venue=venue,
            is_open_access=is_open_access,
            has_code_link=has_code_link,
            has_trusted_artifact=has_trusted_artifact,
            has_trusted_code_artifact=has_trusted_code_artifact,
            has_trusted_dataset_artifact=has_trusted_dataset_artifact,
            has_trusted_model_artifact=has_trusted_model_artifact,
            has_trusted_demo_artifact=has_trusted_demo_artifact,
            artifact_provider=artifact_provider,
            artifact_type=artifact_type,
        )

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        order_by = self._build_order_by(sort_by)

        sql = f"""
        SELECT cd.*
        FROM canonical_documents cd
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
                cd.title ILIKE %s
                OR COALESCE(cd.abstract, '') ILIKE %s
                OR COALESCE(cd.authors::text, '') ILIKE %s
            )
            """
        )
        params.extend([pattern, pattern, pattern])

        if year_from is not None:
            where_clauses.append("cd.year >= %s")
            params.append(year_from)

        if year_to is not None:
            where_clauses.append("cd.year <= %s")
            params.append(year_to)

        if category:
            where_clauses.append(
                """
                (
                    cd.categories @> %s::jsonb
                    OR cd.tags @> %s::jsonb
                    OR cd.concepts @> %s::jsonb
                    OR cd.keywords @> %s::jsonb
                )
                """
            )
            category_json = json.dumps([category], ensure_ascii=False)
            params.extend([category_json, category_json, category_json, category_json])

        if source:
            where_clauses.append(
                """
                cd.canonical_id IN (
                    SELECT canonical_id
                    FROM canonical_source_links
                    WHERE source = %s
                )
                """
            )
            params.append(source)

        if publication_type:
            where_clauses.append("cd.publication_type = %s")
            params.append(publication_type)

        if venue:
            where_clauses.append(
                """
                (
                    LOWER(COALESCE(cd.venue, '')) = LOWER(%s)
                    OR LOWER(COALESCE(cd.journal, '')) = LOWER(%s)
                    OR LOWER(COALESCE(cd.conference, '')) = LOWER(%s)
                    OR LOWER(COALESCE(cd.publisher, '')) = LOWER(%s)
                )
                """
            )
            params.extend([venue, venue, venue, venue])

        if is_open_access is not None:
            where_clauses.append("cd.is_open_access = %s")
            params.append(is_open_access)

        if has_code_link is not None:
            where_clauses.append("cd.has_code_link = %s")
            params.append(has_code_link)

        where_sql = "WHERE " + " AND ".join(where_clauses)

        sql = f"""
        SELECT
            cd.*,
            (
                CASE
                    WHEN LOWER(cd.title) = LOWER(%s) THEN 100.0
                    WHEN cd.title ILIKE %s THEN 30.0
                    ELSE 0.0
                END
                + CASE
                    WHEN COALESCE(cd.abstract, '') ILIKE %s THEN 10.0
                    ELSE 0.0
                END
                + CASE
                    WHEN COALESCE(cd.authors::text, '') ILIKE %s THEN 5.0
                    ELSE 0.0
                END
            ) AS score
        FROM canonical_documents cd
        {where_sql}
        ORDER BY score DESC, cd.year DESC NULLS LAST, cd.canonical_id ASC
        LIMIT %s OFFSET %s
        """

        final_params = [
            query_text,
            pattern,
            pattern,
            pattern,
            *params,
            limit,
            offset,
        ]

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
                cd.title ILIKE %s
                OR COALESCE(cd.abstract, '') ILIKE %s
                OR COALESCE(cd.authors::text, '') ILIKE %s
            )
            """
        )
        params.extend([pattern, pattern, pattern])

        if year_from is not None:
            where_clauses.append("cd.year >= %s")
            params.append(year_from)

        if year_to is not None:
            where_clauses.append("cd.year <= %s")
            params.append(year_to)

        if category:
            where_clauses.append(
                """
                (
                    cd.categories @> %s::jsonb
                    OR cd.tags @> %s::jsonb
                    OR cd.concepts @> %s::jsonb
                    OR cd.keywords @> %s::jsonb
                )
                """
            )
            category_json = json.dumps([category], ensure_ascii=False)
            params.extend([category_json, category_json, category_json, category_json])

        if source:
            where_clauses.append(
                """
                cd.canonical_id IN (
                    SELECT canonical_id
                    FROM canonical_source_links
                    WHERE source = %s
                )
                """
            )
            params.append(source)

        if publication_type:
            where_clauses.append("cd.publication_type = %s")
            params.append(publication_type)

        if venue:
            where_clauses.append(
                """
                (
                    LOWER(COALESCE(cd.venue, '')) = LOWER(%s)
                    OR LOWER(COALESCE(cd.journal, '')) = LOWER(%s)
                    OR LOWER(COALESCE(cd.conference, '')) = LOWER(%s)
                    OR LOWER(COALESCE(cd.publisher, '')) = LOWER(%s)
                )
                """
            )
            params.extend([venue, venue, venue, venue])

        if is_open_access is not None:
            where_clauses.append("cd.is_open_access = %s")
            params.append(is_open_access)

        if has_code_link is not None:
            where_clauses.append("cd.has_code_link = %s")
            params.append(has_code_link)

        where_sql = "WHERE " + " AND ".join(where_clauses)

        sql = f"""
        SELECT COUNT(*) AS total
        FROM canonical_documents cd
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
        has_trusted_artifact: bool | None = None,
        has_trusted_code_artifact: bool | None = None,
        has_trusted_dataset_artifact: bool | None = None,
        has_trusted_model_artifact: bool | None = None,
        has_trusted_demo_artifact: bool | None = None,
        artifact_provider: str | None = None,
        artifact_type: str | None = None,
    ) -> int:
        where_clauses, params = self._build_document_where(
            query_text=query_text,
            year_from=year_from,
            year_to=year_to,
            category=category,
            source=source,
            publication_type=publication_type,
            venue=venue,
            is_open_access=is_open_access,
            has_code_link=has_code_link,
            has_trusted_artifact=has_trusted_artifact,
            has_trusted_code_artifact=has_trusted_code_artifact,
            has_trusted_dataset_artifact=has_trusted_dataset_artifact,
            has_trusted_model_artifact=has_trusted_model_artifact,
            has_trusted_demo_artifact=has_trusted_demo_artifact,
            artifact_provider=artifact_provider,
            artifact_type=artifact_type,
        )

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        sql = f"""
        SELECT COUNT(*) AS total
        FROM canonical_documents cd
        {where_sql}
        """

        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return int(row["total"]) if row else 0

    def list_artifacts(
        self,
        *,
        provider: str | None = None,
        artifact_type: str | None = None,
        relation_type: str | None = None,
        owner: str | None = None,
        min_confidence: float | None = None,
        has_paper_links: bool | None = None,
        min_stars: int | None = None,
        max_stars: int | None = None,
        language: str | None = None,
        license: str | None = None,
        archived: bool | None = None,
        github_status: str | None = None,
        has_github_metadata: bool | None = None,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "linked_papers_desc",
    ) -> list[dict[str, Any]]:
        where_clauses, params = self._build_artifact_where(
            provider=provider,
            artifact_type=artifact_type,
            relation_type=relation_type,
            owner=owner,
            min_confidence=min_confidence,
            has_paper_links=has_paper_links,
            min_stars=min_stars,
            max_stars=max_stars,
            language=language,
            license=license,
            archived=archived,
            github_status=github_status,
            has_github_metadata=has_github_metadata,
        )

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        order_by = self._build_artifact_order_by(sort_by)

        sql = f"""
        SELECT
            ae.*,
            COALESCE(stats.linked_papers_count, 0) AS linked_papers_count,
            COALESCE(stats.relation_types, '[]'::jsonb) AS relation_types
        FROM artifact_entities ae
        LEFT JOIN (
            SELECT
                artifact_id,
                COUNT(DISTINCT canonical_id) AS linked_papers_count,
                jsonb_agg(DISTINCT relation_type ORDER BY relation_type) AS relation_types,
                MAX(confidence) AS max_confidence
            FROM paper_artifact_links
            GROUP BY artifact_id
        ) stats
          ON stats.artifact_id = ae.artifact_id
        {where_sql}
        {order_by}
        LIMIT %s OFFSET %s
        """

        params.extend([limit, offset])

        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [self._normalize_artifact_row(row) for row in rows]

    def count_artifacts(
        self,
        *,
        provider: str | None = None,
        artifact_type: str | None = None,
        relation_type: str | None = None,
        owner: str | None = None,
        min_confidence: float | None = None,
        has_paper_links: bool | None = None,
        min_stars: int | None = None,
        max_stars: int | None = None,
        language: str | None = None,
        license: str | None = None,
        archived: bool | None = None,
        github_status: str | None = None,
        has_github_metadata: bool | None = None,
    ) -> int:
        where_clauses, params = self._build_artifact_where(
            provider=provider,
            artifact_type=artifact_type,
            relation_type=relation_type,
            owner=owner,
            min_confidence=min_confidence,
            has_paper_links=has_paper_links,
            min_stars=min_stars,
            max_stars=max_stars,
            language=language,
            license=license,
            archived=archived,
            github_status=github_status,
            has_github_metadata=has_github_metadata,
        )

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        sql = f"""
        SELECT COUNT(*) AS total
        FROM artifact_entities ae
        {where_sql}
        """

        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return int(row["total"]) if row else 0

    def get_document_artifacts(
        self,
        canonical_id: str,
        *,
        relation_type: str | None = None,
        provider: str | None = None,
        artifact_type: str | None = None,
        min_confidence: float | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where_clauses = ["pal.canonical_id = %s"]
        params: list[Any] = [canonical_id]

        if relation_type:
            where_clauses.append("pal.relation_type = %s")
            params.append(relation_type)

        if provider:
            where_clauses.append("ae.provider = %s")
            params.append(provider)

        if artifact_type:
            where_clauses.append("ae.artifact_type = %s")
            params.append(artifact_type)

        if min_confidence is not None:
            where_clauses.append("pal.confidence >= %s")
            params.append(float(min_confidence))

        where_sql = "WHERE " + " AND ".join(where_clauses)

        sql = f"""
        SELECT
            pal.link_id AS link_id,
            pal.canonical_id AS link_canonical_id,
            pal.artifact_id AS link_artifact_id,
            pal.relation_type AS link_relation_type,
            pal.confidence AS link_confidence,
            pal.evidence_source AS link_evidence_source,
            pal.evidence_url AS link_evidence_url,
            pal.source_field AS link_source_field,
            pal.source_doc_id AS link_source_doc_id,
            pal.metadata AS link_metadata,
            pal.created_at AS link_created_at,
            pal.updated_at AS link_updated_at,

            ae.artifact_id AS artifact_id,
            ae.artifact_type AS artifact_type,
            ae.provider AS provider,
            ae.external_id AS external_id,
            ae.normalized_url AS normalized_url,
            ae.canonical_url AS canonical_url,
            ae.name AS name,
            ae.owner AS owner,
            ae.title AS title,
            ae.description AS description,
            ae.license AS license,
            ae.stars AS stars,
            ae.forks AS forks,
            ae.downloads AS downloads,
            ae.likes AS likes,
            ae.topics AS topics,
            ae.tags AS tags,
            ae.metadata AS metadata,
            ae.first_seen_at AS first_seen_at,
            ae.last_seen_at AS last_seen_at,
            ae.fetched_at AS fetched_at,
            ae.created_at AS created_at,
            ae.updated_at AS updated_at
        FROM paper_artifact_links pal
        JOIN artifact_entities ae
          ON ae.artifact_id = pal.artifact_id
        {where_sql}
        ORDER BY pal.confidence DESC, ae.provider ASC, ae.normalized_url ASC
        LIMIT %s OFFSET %s
        """

        params.extend([limit, offset])

        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [self._normalize_document_artifact_link_row(row) for row in rows]

    def count_document_artifacts(
        self,
        canonical_id: str,
        *,
        relation_type: str | None = None,
        provider: str | None = None,
        artifact_type: str | None = None,
        min_confidence: float | None = None,
    ) -> int:
        where_clauses = ["pal.canonical_id = %s"]
        params: list[Any] = [canonical_id]

        if relation_type:
            where_clauses.append("pal.relation_type = %s")
            params.append(relation_type)

        if provider:
            where_clauses.append("ae.provider = %s")
            params.append(provider)

        if artifact_type:
            where_clauses.append("ae.artifact_type = %s")
            params.append(artifact_type)

        if min_confidence is not None:
            where_clauses.append("pal.confidence >= %s")
            params.append(float(min_confidence))

        where_sql = "WHERE " + " AND ".join(where_clauses)

        sql = f"""
        SELECT COUNT(*) AS total
        FROM paper_artifact_links pal
        JOIN artifact_entities ae
          ON ae.artifact_id = pal.artifact_id
        {where_sql}
        """

        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return int(row["total"]) if row else 0

    @staticmethod
    def _build_document_where(
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
        has_trusted_artifact: bool | None = None,
        has_trusted_code_artifact: bool | None = None,
        has_trusted_dataset_artifact: bool | None = None,
        has_trusted_model_artifact: bool | None = None,
        has_trusted_demo_artifact: bool | None = None,
        artifact_provider: str | None = None,
        artifact_type: str | None = None,
    ) -> tuple[list[str], list[Any]]:
        where_clauses: list[str] = []
        params: list[Any] = []

        if query_text:
            where_clauses.append(
                """
                (
                    cd.title ILIKE %s
                    OR COALESCE(cd.abstract, '') ILIKE %s
                    OR COALESCE(cd.venue, '') ILIKE %s
                    OR COALESCE(cd.journal, '') ILIKE %s
                    OR COALESCE(cd.conference, '') ILIKE %s
                    OR COALESCE(cd.publisher, '') ILIKE %s
                )
                """
            )
            pattern = f"%{query_text}%"
            params.extend([pattern, pattern, pattern, pattern, pattern, pattern])

        if year_from is not None:
            where_clauses.append("cd.year >= %s")
            params.append(year_from)

        if year_to is not None:
            where_clauses.append("cd.year <= %s")
            params.append(year_to)

        if category:
            where_clauses.append("cd.categories @> %s::jsonb")
            params.append(json.dumps([category], ensure_ascii=False))

        if source:
            where_clauses.append(
                """
                cd.canonical_id IN (
                    SELECT canonical_id
                    FROM canonical_source_links
                    WHERE source = %s
                )
                """
            )
            params.append(source)

        if publication_type:
            where_clauses.append("cd.publication_type = %s")
            params.append(publication_type)

        if venue:
            where_clauses.append("LOWER(COALESCE(cd.venue, '')) = LOWER(%s)")
            params.append(venue)

        if is_open_access is not None:
            where_clauses.append("cd.is_open_access = %s")
            params.append(is_open_access)

        if has_code_link is not None:
            where_clauses.append("cd.has_code_link = %s")
            params.append(has_code_link)

        PostgresDocumentStore._append_document_artifact_filters(
            where_clauses=where_clauses,
            params=params,
            has_trusted_artifact=has_trusted_artifact,
            has_trusted_code_artifact=has_trusted_code_artifact,
            has_trusted_dataset_artifact=has_trusted_dataset_artifact,
            has_trusted_model_artifact=has_trusted_model_artifact,
            has_trusted_demo_artifact=has_trusted_demo_artifact,
            artifact_provider=artifact_provider,
            artifact_type=artifact_type,
        )

        return where_clauses, params

    @staticmethod
    def _append_document_artifact_filters(
        *,
        where_clauses: list[str],
        params: list[Any],
        has_trusted_artifact: bool | None,
        has_trusted_code_artifact: bool | None,
        has_trusted_dataset_artifact: bool | None,
        has_trusted_model_artifact: bool | None,
        has_trusted_demo_artifact: bool | None,
        artifact_provider: str | None,
        artifact_type: str | None,
    ) -> None:
        relation_flags = {
            "code": has_trusted_code_artifact,
            "dataset": has_trusted_dataset_artifact,
            "model": has_trusted_model_artifact,
            "demo": has_trusted_demo_artifact,
        }

        has_relation_filter = any(flag is not None for flag in relation_flags.values())
        has_artifact_scope_filter = artifact_provider is not None or artifact_type is not None

        if has_trusted_artifact is True:
            clause, clause_params = PostgresDocumentStore._document_artifact_exists_clause(
                relation_type=None,
                provider=artifact_provider,
                artifact_type=artifact_type,
                negate=False,
            )
            where_clauses.append(clause)
            params.extend(clause_params)

        elif has_trusted_artifact is False:
            clause, clause_params = PostgresDocumentStore._document_artifact_exists_clause(
                relation_type=None,
                provider=None,
                artifact_type=None,
                negate=True,
            )
            where_clauses.append(clause)
            params.extend(clause_params)

        for relation_type, flag in relation_flags.items():
            if flag is True:
                clause, clause_params = PostgresDocumentStore._document_artifact_exists_clause(
                    relation_type=relation_type,
                    provider=artifact_provider,
                    artifact_type=artifact_type,
                    negate=False,
                )
                where_clauses.append(clause)
                params.extend(clause_params)

            elif flag is False:
                clause, clause_params = PostgresDocumentStore._document_artifact_exists_clause(
                    relation_type=relation_type,
                    provider=artifact_provider,
                    artifact_type=artifact_type,
                    negate=True,
                )
                where_clauses.append(clause)
                params.extend(clause_params)

        if (
            has_artifact_scope_filter
            and has_trusted_artifact is None
            and not has_relation_filter
        ):
            clause, clause_params = PostgresDocumentStore._document_artifact_exists_clause(
                relation_type=None,
                provider=artifact_provider,
                artifact_type=artifact_type,
                negate=False,
            )
            where_clauses.append(clause)
            params.extend(clause_params)

    @staticmethod
    def _document_artifact_exists_clause(
        *,
        relation_type: str | None,
        provider: str | None,
        artifact_type: str | None,
        negate: bool,
    ) -> tuple[str, list[Any]]:
        inner_clauses = ["pal_filter.canonical_id = cd.canonical_id"]
        params: list[Any] = []

        if relation_type:
            inner_clauses.append("pal_filter.relation_type = %s")
            params.append(relation_type)

        if provider:
            inner_clauses.append("ae_filter.provider = %s")
            params.append(provider)

        if artifact_type:
            inner_clauses.append("ae_filter.artifact_type = %s")
            params.append(artifact_type)

        exists_sql = f"""
        EXISTS (
            SELECT 1
            FROM paper_artifact_links pal_filter
            JOIN artifact_entities ae_filter
              ON ae_filter.artifact_id = pal_filter.artifact_id
            WHERE {" AND ".join(inner_clauses)}
        )
        """

        if negate:
            return f"NOT {exists_sql}", params

        return exists_sql, params

    @staticmethod
    def _build_artifact_where(
        *,
        provider: str | None = None,
        artifact_type: str | None = None,
        relation_type: str | None = None,
        owner: str | None = None,
        min_confidence: float | None = None,
        has_paper_links: bool | None = None,
        min_stars: int | None = None,
        max_stars: int | None = None,
        language: str | None = None,
        license: str | None = None,
        archived: bool | None = None,
        github_status: str | None = None,
        has_github_metadata: bool | None = None,
    ) -> tuple[list[str], list[Any]]:
        where_clauses: list[str] = []
        params: list[Any] = []

        if provider:
            where_clauses.append("ae.provider = %s")
            params.append(provider)

        if artifact_type:
            where_clauses.append("ae.artifact_type = %s")
            params.append(artifact_type)

        if owner:
            where_clauses.append("LOWER(COALESCE(ae.owner, '')) = LOWER(%s)")
            params.append(owner)

        if relation_type:
            where_clauses.append(
                """
                EXISTS (
                    SELECT 1
                    FROM paper_artifact_links pal_filter
                    WHERE pal_filter.artifact_id = ae.artifact_id
                      AND pal_filter.relation_type = %s
                )
                """
            )
            params.append(relation_type)

        if min_confidence is not None:
            where_clauses.append(
                """
                EXISTS (
                    SELECT 1
                    FROM paper_artifact_links pal_filter
                    WHERE pal_filter.artifact_id = ae.artifact_id
                      AND pal_filter.confidence >= %s
                )
                """
            )
            params.append(float(min_confidence))

        if has_paper_links is True:
            where_clauses.append(
                """
                EXISTS (
                    SELECT 1
                    FROM paper_artifact_links pal_filter
                    WHERE pal_filter.artifact_id = ae.artifact_id
                )
                """
            )
        elif has_paper_links is False:
            where_clauses.append(
                """
                NOT EXISTS (
                    SELECT 1
                    FROM paper_artifact_links pal_filter
                    WHERE pal_filter.artifact_id = ae.artifact_id
                )
                """
            )

        if min_stars is not None:
            where_clauses.append("ae.stars >= %s")
            params.append(int(min_stars))

        if max_stars is not None:
            where_clauses.append("ae.stars <= %s")
            params.append(int(max_stars))

        if language:
            where_clauses.append(
                "LOWER(COALESCE(ae.metadata->'github'->>'language', '')) = LOWER(%s)"
            )
            params.append(language)

        if license:
            where_clauses.append("LOWER(COALESCE(ae.license, '')) = LOWER(%s)")
            params.append(license)

        if archived is not None:
            where_clauses.append(
                """
                (COALESCE(ae.metadata, '{}'::jsonb) ? 'github')
                AND (ae.metadata->'github'->>'archived')::boolean = %s
                """
            )
            params.append(bool(archived))

        if github_status:
            where_clauses.append("ae.metadata->'github'->>'status' = %s")
            params.append(github_status)

        if has_github_metadata is True:
            where_clauses.append("COALESCE(ae.metadata, '{}'::jsonb) ? 'github'")
        elif has_github_metadata is False:
            where_clauses.append("NOT (COALESCE(ae.metadata, '{}'::jsonb) ? 'github')")

        return where_clauses, params

    @staticmethod
    def _build_order_by(sort_by: str) -> str:
        if sort_by == "year_asc":
            return "ORDER BY cd.year ASC NULLS LAST, cd.canonical_id ASC"
        if sort_by == "year_desc":
            return "ORDER BY cd.year DESC NULLS LAST, cd.canonical_id ASC"
        if sort_by == "title_asc":
            return "ORDER BY cd.title ASC NULLS LAST, cd.canonical_id ASC"
        return "ORDER BY cd.year DESC NULLS LAST, cd.canonical_id ASC"

    @staticmethod
    def _build_artifact_order_by(sort_by: str) -> str:
        if sort_by == "provider_asc":
            return "ORDER BY ae.provider ASC, ae.normalized_url ASC"
        if sort_by == "type_asc":
            return "ORDER BY ae.artifact_type ASC, ae.provider ASC, ae.normalized_url ASC"
        if sort_by == "owner_asc":
            return "ORDER BY ae.owner ASC NULLS LAST, ae.provider ASC, ae.normalized_url ASC"
        if sort_by == "last_seen_desc":
            return "ORDER BY ae.last_seen_at DESC NULLS LAST, ae.provider ASC, ae.normalized_url ASC"
        if sort_by == "stars_desc":
            return "ORDER BY ae.stars DESC NULLS LAST, ae.provider ASC, ae.normalized_url ASC"
        if sort_by == "forks_desc":
            return "ORDER BY ae.forks DESC NULLS LAST, ae.provider ASC, ae.normalized_url ASC"
        if sort_by == "linked_papers_desc":
            return "ORDER BY COALESCE(stats.linked_papers_count, 0) DESC, ae.provider ASC, ae.normalized_url ASC"
        return "ORDER BY COALESCE(stats.linked_papers_count, 0) DESC, ae.provider ASC, ae.normalized_url ASC"

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

    @staticmethod
    def _normalize_artifact_row(row: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(row)

        for field in ("topics", "tags", "metadata", "relation_types"):
            value = normalized.get(field)
            if value is None:
                if field in ("topics", "tags", "relation_types"):
                    normalized[field] = []
                elif field == "metadata":
                    normalized[field] = {}
                continue

            if isinstance(value, str):
                try:
                    normalized[field] = json.loads(value)
                except json.JSONDecodeError:
                    pass

        for field in (
            "first_seen_at",
            "last_seen_at",
            "fetched_at",
            "created_at",
            "updated_at",
        ):
            value = normalized.get(field)
            if value is not None and not isinstance(value, str):
                normalized[field] = value.isoformat()

        return normalized

    @staticmethod
    def _normalize_document_artifact_link_row(row: dict[str, Any]) -> dict[str, Any]:
        artifact = {
            "artifact_id": row.get("artifact_id"),
            "artifact_type": row.get("artifact_type"),
            "provider": row.get("provider"),
            "external_id": row.get("external_id"),
            "normalized_url": row.get("normalized_url"),
            "canonical_url": row.get("canonical_url"),
            "name": row.get("name"),
            "owner": row.get("owner"),
            "title": row.get("title"),
            "description": row.get("description"),
            "license": row.get("license"),
            "stars": row.get("stars"),
            "forks": row.get("forks"),
            "downloads": row.get("downloads"),
            "likes": row.get("likes"),
            "topics": row.get("topics"),
            "tags": row.get("tags"),
            "metadata": row.get("metadata"),
            "first_seen_at": row.get("first_seen_at"),
            "last_seen_at": row.get("last_seen_at"),
            "fetched_at": row.get("fetched_at"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "linked_papers_count": None,
            "relation_types": [],
        }
        artifact = PostgresDocumentStore._normalize_artifact_row(artifact)

        link_metadata = row.get("link_metadata")
        if isinstance(link_metadata, str):
            try:
                link_metadata = json.loads(link_metadata)
            except json.JSONDecodeError:
                pass
        if link_metadata is None:
            link_metadata = {}

        out = {
            "link_id": row.get("link_id"),
            "canonical_id": row.get("link_canonical_id"),
            "artifact_id": row.get("link_artifact_id"),
            "relation_type": row.get("link_relation_type"),
            "confidence": float(row.get("link_confidence") or 0.0),
            "evidence_source": row.get("link_evidence_source"),
            "evidence_url": row.get("link_evidence_url"),
            "source_field": row.get("link_source_field"),
            "source_doc_id": row.get("link_source_doc_id"),
            "metadata": link_metadata,
            "created_at": row.get("link_created_at"),
            "updated_at": row.get("link_updated_at"),
            "artifact": artifact,
        }

        for field in ("created_at", "updated_at"):
            value = out.get(field)
            if value is not None and not isinstance(value, str):
                out[field] = value.isoformat()

        return out