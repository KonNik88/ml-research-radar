from radar_core.ingest.arxiv import ArxivIngestor, ArxivQuery


def test_arxiv_ingest_smoke():
    ingestor = ArxivIngestor()
    raw_docs, normalized_docs = ingestor.ingest(
        ArxivQuery(search_query="cat:cs.LG", max_results=3)
    )

    assert len(raw_docs) == len(normalized_docs)
    assert len(normalized_docs) > 0
    assert normalized_docs[0].doc_id
    assert normalized_docs[0].canonical_url
    assert normalized_docs[0].content_hash