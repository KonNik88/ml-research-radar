from radar_core.ingest.openalex import OpenAlexIngestor, OpenAlexQuery


def test_openalex_ingest_smoke():
    ingestor = OpenAlexIngestor()
    raw_docs, normalized_docs = ingestor.ingest(
        OpenAlexQuery(
            search="machine learning",
            filter="from_publication_date:2025-01-01",
            per_page=2,
            sort="publication_date:desc",
        )
    )

    assert len(raw_docs) == len(normalized_docs)
    assert len(normalized_docs) > 0

    doc = normalized_docs[0]

    assert doc.doc_id
    assert doc.canonical_url
    assert doc.content_hash
    assert doc.source == "openalex"
    assert doc.title
    assert isinstance(doc.authors, list)
    assert isinstance(doc.categories, list)