from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from radar_core.utils.source_observation_identity import (
    build_source_observation_identity_from_mapping,
)
from scripts.export.export_postgres_v1 import (
    insert_link,
    insert_source,
    source_row,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class RecordingCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def execute(self, query: str, params: Any = None) -> None:
        self.calls.append((query, params))


def _normalized_row(
    *,
    source: str,
    source_record_id: str,
    doc_id: str = "shared-doc-id",
    title: str | None = "Example title",
    source_id: str | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "source_id": source_id if source_id is not None else source_record_id,
        "source_record_id": source_record_id,
        "doc_id": doc_id,
        "canonical_url": f"https://example.test/{doc_id}",
        "title": title,
        "authors": [],
    }


def _table_block(schema: str, table_name: str, next_table_name: str) -> str:
    start = schema.index(f"CREATE TABLE IF NOT EXISTS {table_name}")
    end = schema.index(f"CREATE TABLE IF NOT EXISTS {next_table_name}", start)
    return schema[start:end]


def test_same_legacy_doc_id_materializes_as_distinct_source_rows() -> None:
    crossref = source_row(
        _normalized_row(
            source="crossref",
            source_record_id="10.1234/example",
        )
    )
    openalex = source_row(
        _normalized_row(
            source="openalex",
            source_record_id="https://openalex.org/W123",
        )
    )

    assert crossref["doc_id"] == openalex["doc_id"]
    assert crossref["source_observation_id"] != openalex["source_observation_id"]


def test_source_row_uses_shared_identity_helper_and_normalized_source() -> None:
    raw = _normalized_row(
        source="openalex_alignment",
        source_record_id="https://openalex.org/w123",
    )

    row = source_row(raw)
    expected = build_source_observation_identity_from_mapping(raw)

    assert row["source_observation_id"] == expected.source_observation_id
    assert row["source"] == "openalex"


def test_source_row_preserves_identity_valid_missing_title() -> None:
    raw = _normalized_row(
        source="openalex",
        source_record_id="https://openalex.org/W999",
        title=None,
    )

    row = source_row(raw)

    assert row["source_observation_id"]
    assert row["title"] is None


def test_source_row_allows_missing_source_id_when_record_id_exists() -> None:
    raw = _normalized_row(
        source="openalex",
        source_record_id="https://openalex.org/W1000",
        source_id="",
    )

    row = source_row(raw)

    assert row["source_observation_id"]
    assert row["source_id"] == ""


def test_source_row_fails_closed_without_usable_identity() -> None:
    with pytest.raises(ValueError):
        source_row(
            {
                "source": "openalex",
                "title": "Missing identity",
            }
        )


def test_insert_source_conflicts_on_source_observation_id() -> None:
    cursor = RecordingCursor()
    insert_source(
        cursor,
        source_row(
            _normalized_row(
                source="crossref",
                source_record_id="10.1234/example",
            )
        ),
    )

    assert len(cursor.calls) == 1
    sql, params = cursor.calls[0]
    assert "source_observation_id" in sql
    assert "ON CONFLICT (source_observation_id) DO UPDATE SET" in sql
    assert isinstance(params, dict)
    assert params["source_observation_id"]


def test_insert_link_builds_identity_without_legacy_lookup_query() -> None:
    cursor = RecordingCursor()
    link = _normalized_row(
        source="semantic_scholar",
        source_record_id="paper-id",
    )
    expected = build_source_observation_identity_from_mapping(link)

    insert_link(cursor, "paper-1", link)

    assert len(cursor.calls) == 1
    sql, params = cursor.calls[0]
    assert "INSERT INTO canonical_source_links" in sql
    assert "source_observation_id" in sql
    assert "SELECT doc_id" not in sql
    assert params[0] == "paper-1"
    assert params[1] == expected.source_observation_id
    assert params[2] == link["doc_id"]


def test_insert_link_allows_missing_legacy_doc_id() -> None:
    cursor = RecordingCursor()
    link = {
        "source": "arxiv",
        "source_id": "2601.01675v1",
        "source_record_id": "2601.01675v1",
        "source_record_url": "http://arxiv.org/abs/2601.01675v1",
        "canonical_url": "http://arxiv.org/abs/2601.01675v1",
    }

    insert_link(cursor, "paper-1", link)

    assert len(cursor.calls) == 1
    _, params = cursor.calls[0]
    assert params[1]
    assert params[2] is None


def test_candidate_schema_contains_required_identity_constraints() -> None:
    schema = (PROJECT_ROOT / "store" / "sql" / "01_schema.sql").read_text(
        encoding="utf-8"
    )
    source_block = _table_block(
        schema,
        "source_documents",
        "canonical_source_links",
    )
    link_block = _table_block(
        schema,
        "canonical_source_links",
        "document_references",
    )

    assert "source_observation_id TEXT PRIMARY KEY" in source_block
    assert "doc_id TEXT NOT NULL" in source_block
    assert "source_id TEXT," in source_block
    assert "source_id TEXT NOT NULL" not in source_block
    assert "title TEXT," in source_block
    assert "title TEXT NOT NULL" not in source_block

    assert "source_observation_id TEXT NOT NULL" in link_block
    assert "REFERENCES source_documents(source_observation_id)" in link_block
    assert "ON DELETE RESTRICT" in link_block
    assert "doc_id TEXT NULL" in link_block
    assert "UNIQUE (canonical_id, source_observation_id)" in link_block
    assert "REFERENCES source_documents(doc_id)" not in link_block


def test_candidate_indexes_preserve_legacy_lookup_and_add_identity_lookup() -> None:
    indexes = (PROJECT_ROOT / "store" / "sql" / "02_indexes.sql").read_text(
        encoding="utf-8"
    )

    assert "idx_source_documents_doc_id" in indexes
    assert "ON source_documents (doc_id)" in indexes
    assert "idx_canonical_source_links_source_observation_id" in indexes
    assert "ON canonical_source_links (source_observation_id)" in indexes


def test_exporter_has_no_legacy_primary_link_resolver() -> None:
    exporter = (
        PROJECT_ROOT / "scripts" / "export" / "export_postgres_v1.py"
    ).read_text(encoding="utf-8")

    assert "def resolve_source_doc_id" not in exporter
    assert "SOURCE_DOC_LOOKUP_FIELDS" not in exporter
    assert "ON CONFLICT (doc_id) DO UPDATE SET" not in exporter
    assert "build_source_observation_identity_from_mapping" in exporter
    assert 'missing_fields.append("title")' not in exporter
    assert 'missing_fields.append("source_id")' not in exporter
