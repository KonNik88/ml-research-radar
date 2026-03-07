from radar_core.ingest.arxiv import ArxivIngestor, ArxivQuery


def test_arxiv_ingestor_implements_base_contract():
    ingestor = ArxivIngestor()

    assert hasattr(ingestor, "source_name")
    assert hasattr(ingestor, "fetch_feed")
    assert hasattr(ingestor, "iter_entries")
    assert hasattr(ingestor, "parse_entry_to_raw")
    assert hasattr(ingestor, "parse_entry_to_normalized")
    assert hasattr(ingestor, "ingest")

    raw_docs, normalized_docs = ingestor.ingest(
        ArxivQuery(search_query="cat:cs.LG", max_results=2)
    )

    assert len(raw_docs) == len(normalized_docs)
    assert len(raw_docs) > 0