from __future__ import annotations

import json
from pathlib import Path

from scripts.ingest.kaggle_arxiv_snapshot_utils import (
    detect_snapshot_format,
    iter_snapshot_rows,
    load_arxiv_taxonomy_categories,
    map_kaggle_row_to_documents,
    parse_categories,
    parse_versions,
)


def test_load_arxiv_taxonomy_categories_expanded() -> None:
    categories = load_arxiv_taxonomy_categories(mode="expanded")
    assert "cs.LG" in categories
    assert "cs.AI" in categories
    assert "cs.CV" in categories
    assert "cs.CL" in categories
    assert "stat.ML" in categories
    assert "cs.IR" in categories


def _sample_rows() -> list[dict]:
    return [
        {
            "id": "2501.12345",
            "title": "A Test Paper",
            "authors": "Alice, Bob",
            "categories": "cs.LG cs.AI",
            "abstract": "Test abstract.",
            "comments": "Accepted at ICLR 2025. Code: https://github.com/example/repo",
            "doi": "10.1234/test",
            "versions": [
                {"version": "v1", "created": "Mon, 01 Jan 2025 12:00:00 GMT"},
                {"version": "v2", "created": "Tue, 02 Jan 2025 12:00:00 GMT"},
            ],
            "update_date": "2025-01-02",
        },
        {
            "id": "2501.12346",
            "title": "Another Test Paper",
            "authors": "Carol",
            "categories": "cs.CV",
            "abstract": "Another abstract.",
            "versions": [{"version": "v1", "created": "Wed, 03 Jan 2025 12:00:00 GMT"}],
            "update_date": "2025-01-03",
        },
    ]


def test_kaggle_snapshot_utils_smoke(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "kaggle_snapshot_test.jsonl"

    with snapshot_path.open("w", encoding="utf-8") as f:
        for row in _sample_rows():
            f.write(json.dumps(row) + "\n")

    info = detect_snapshot_format(snapshot_path)
    assert info.format_name == "ndjson"

    rows = [row for _, row in iter_snapshot_rows(snapshot_path)]
    assert len(rows) == 2
    assert parse_categories(rows[0]["categories"]) == ["cs.LG", "cs.AI"]
    assert len(parse_versions(rows[0]["versions"])) == 2

    mapped = map_kaggle_row_to_documents(rows[0], raw_artifact_path="sample#1")
    doc = mapped.normalized_document

    assert doc.source == "arxiv"
    assert doc.arxiv_id == "2501.12345v2"
    assert doc.doi == "10.1234/test"
    assert doc.primary_category == "cs.LG"
    assert doc.has_code_link is True
    assert doc.repo_url is not None
    assert doc.publication_type == "preprint"