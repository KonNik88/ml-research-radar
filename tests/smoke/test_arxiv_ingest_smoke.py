from radar_core.ingest.arxiv import ArxivIngestor, ArxivQuery


def test_arxiv_ingest_smoke():
    ingestor = ArxivIngestor()
    raw_docs, normalized_docs = ingestor.ingest(
        ArxivQuery(search_query="cat:cs.LG", max_results=3)
    )

    assert len(raw_docs) == len(normalized_docs)
    assert len(normalized_docs) > 0

    doc = normalized_docs[0]

    assert doc.doc_id
    assert doc.canonical_url
    assert doc.content_hash
    assert doc.source == "arxiv"
    assert doc.title
    assert isinstance(doc.authors, list)
    assert isinstance(doc.categories, list)