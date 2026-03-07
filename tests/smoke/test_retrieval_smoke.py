from radar_core.contracts.canonical_document import CanonicalDocument, SourceLink
from radar_core.retrieval.lexical import build_bm25_index


def test_bm25_lexical_search_returns_relevant_doc_first():
    docs = [
        CanonicalDocument(
            canonical_id="1",
            reconciliation_key="title_year::graph neural networks::2025",
            doc_ids=["a"],
            title="Graph Neural Networks for Molecular Property Prediction",
            abstract="We study graph neural networks on molecular graphs.",
            authors=["Alice"],
            year=2025,
            categories=["Graph Neural Networks", "Molecular ML"],
            tags=["gnn", "molecules"],
            sources=[SourceLink(source="arxiv")],
            source_count=1,
        ),
        CanonicalDocument(
            canonical_id="2",
            reconciliation_key="title_year::time series forecasting::2025",
            doc_ids=["b"],
            title="Time Series Forecasting with Transformers",
            abstract="We study forecasting with transformers.",
            authors=["Bob"],
            year=2025,
            categories=["Time Series"],
            tags=["forecasting", "transformers"],
            sources=[SourceLink(source="openalex")],
            source_count=1,
        ),
    ]

    index = build_bm25_index(docs)
    results = index.search("graph neural networks for molecules", top_k=2)

    assert len(results) == 2
    assert results[0].canonical_id == "1"
