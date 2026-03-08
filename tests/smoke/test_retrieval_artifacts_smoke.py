from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.retrieval.artifacts import (
    RetrievalBuildManifest,
    load_dense_artifacts,
    load_json,
    load_lexical_artifacts,
    read_latest_manifest,
    save_dense_artifacts,
    save_json,
    save_lexical_artifacts,
    write_manifest,
)
from radar_core.retrieval.builders import build_dense_embeddings, build_lexical_index


def _make_docs() -> list[CanonicalDocument]:
    corpus_path = Path("data/analytics/reconciled/canonical_documents.jsonl")
    assert corpus_path.exists(), f"Canonical corpus not found: {corpus_path}"

    docs: list[CanonicalDocument] = []
    with corpus_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            docs.append(CanonicalDocument.model_validate(payload))
            if len(docs) >= 3:
                break

    assert len(docs) == 3, "Need at least 3 canonical documents for smoke test"
    return docs


def test_save_json_serializes_datetime(tmp_path: Path) -> None:
    payload = {
        "created_at": datetime(2026, 3, 8, 12, 30, 0, tzinfo=timezone.utc),
        "name": "retrieval-artifacts",
    }
    out_path = tmp_path / "sample.json"

    save_json(out_path, payload)

    loaded = load_json(out_path)
    assert isinstance(loaded["created_at"], str)
    assert loaded["created_at"].startswith("2026-03-08T12:30:00")
    assert loaded["name"] == "retrieval-artifacts"


def test_dense_artifacts_roundtrip(tmp_path: Path) -> None:
    docs = _make_docs()
    embeddings, ids, meta = build_dense_embeddings(
        docs,
        model_name="sentence-transformers/all-MiniLM-L6-v2",
    )

    save_dense_artifacts(
        embeddings=embeddings,
        ids=ids,
        meta=meta,
        build_id="testbuild",
        root_dir=tmp_path,
    )

    loaded = load_dense_artifacts(
        embeddings_path=tmp_path / "dense" / "embeddings_testbuild.npy",
        ids_path=tmp_path / "dense" / "ids_testbuild.json",
        meta_path=tmp_path / "dense" / "meta_testbuild.json",
    )

    assert loaded.embeddings.shape == embeddings.shape
    assert loaded.ids == ids
    assert isinstance(loaded.meta, dict)

    assert loaded.meta["model_name"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert loaded.meta["embedding_dim"] == embeddings.shape[1]
    assert loaded.meta["doc_count"] == len(docs)
    assert loaded.meta["normalized"] is True
    assert "batch_size" in loaded.meta

    assert loaded.meta == meta


def test_lexical_artifacts_roundtrip(tmp_path: Path) -> None:
    docs = _make_docs()
    index = build_lexical_index(docs)

    save_lexical_artifacts(
        index=index,
        ids=[doc.canonical_id for doc in docs],
        build_id="testbuild",
        root_dir=tmp_path,
    )

    loaded = load_lexical_artifacts(
        index_path=tmp_path / "lexical" / "bm25_testbuild.pkl",
        ids_path=tmp_path / "lexical" / "ids_testbuild.json",
    )

    assert len(loaded.ids) == len(docs)
    assert len(loaded.index.documents) == len(docs)

    query = docs[0].title.split()[0]
    results = loaded.index.search(query, top_k=3)
    assert isinstance(results, list)
    assert len(results) >= 1


def test_manifest_write_and_read(tmp_path: Path) -> None:
    manifest = RetrievalBuildManifest(
        build_id="20260308T123000Z",
        created_at="20260308T123005Z",
        corpus_path="data/analytics/reconciled/canonical_documents.jsonl",
        corpus_doc_count=3,
        corpus_fingerprint="abc123",
        lexical_index_path=str(tmp_path / "lexical" / "bm25_20260308T123000Z.pkl"),
        lexical_ids_path=str(tmp_path / "lexical" / "ids_20260308T123000Z.json"),
        dense_embeddings_path=str(tmp_path / "dense" / "embeddings_20260308T123000Z.npy"),
        dense_ids_path=str(tmp_path / "dense" / "ids_20260308T123000Z.json"),
        dense_meta_path=str(tmp_path / "dense" / "meta_20260308T123000Z.json"),
        embedding_model_name="sentence-transformers/all-MiniLM-L6-v2",
        text_fields=["title", "abstract", "authors", "categories", "tags", "primary_category"],
    )

    write_manifest(manifest, root_dir=tmp_path)

    loaded = read_latest_manifest(root_dir=tmp_path)
    assert loaded.build_id == manifest.build_id
    assert loaded.corpus_doc_count == 3
    assert loaded.embedding_model_name == "sentence-transformers/all-MiniLM-L6-v2"


def test_loaded_lexical_and_dense_are_consistent(tmp_path: Path) -> None:
    docs = _make_docs()

    lexical = build_lexical_index(docs)
    embeddings, dense_ids, meta = build_dense_embeddings(
        docs,
        model_name="sentence-transformers/all-MiniLM-L6-v2",
    )

    ids = [doc.canonical_id for doc in docs]

    save_lexical_artifacts(
        index=lexical,
        ids=ids,
        build_id="testbuild",
        root_dir=tmp_path,
    )
    save_dense_artifacts(
        embeddings=embeddings,
        ids=dense_ids,
        meta=meta,
        build_id="testbuild",
        root_dir=tmp_path,
    )

    loaded_lexical = load_lexical_artifacts(
        index_path=tmp_path / "lexical" / "bm25_testbuild.pkl",
        ids_path=tmp_path / "lexical" / "ids_testbuild.json",
    )
    loaded_dense = load_dense_artifacts(
        embeddings_path=tmp_path / "dense" / "embeddings_testbuild.npy",
        ids_path=tmp_path / "dense" / "ids_testbuild.json",
        meta_path=tmp_path / "dense" / "meta_testbuild.json",
    )

    assert loaded_lexical.ids == loaded_dense.ids
    assert len(loaded_dense.ids) == len(docs)
    assert loaded_dense.embeddings.shape[0] == len(docs)