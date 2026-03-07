from radar_core.contracts.document import (
    DocumentType,
    NormalizedDocument,
)
from radar_core.normalize.reconcile import reconcile_documents


def test_reconcile_documents_by_doi():
    arxiv_doc = NormalizedDocument(
        doc_id="doc_arxiv_1",
        canonical_url="https://arxiv.org/abs/1234.5678",
        content_hash="hash1",
        document_type=DocumentType.PAPER,
        source="arxiv",
        source_id="arxiv:1234.5678",
        source_record_url="https://arxiv.org/abs/1234.5678",
        title="A Great ML Paper",
        abstract="Short abstract",
        authors=["Alice", "Bob"],
        year=2025,
        doi="10.1234/test-doi",
        categories=["cs.LG"],
        tags=["cs.LG"],
        has_pdf=True,
        is_withdrawn=False,
    )

    openalex_doc = NormalizedDocument(
        doc_id="doc_openalex_1",
        canonical_url="https://doi.org/10.1234/test-doi",
        content_hash="hash2",
        document_type=DocumentType.PAPER,
        source="openalex",
        source_id="https://openalex.org/W123",
        source_record_url="https://openalex.org/W123",
        title="A Great ML Paper Extended Title",
        abstract="Longer and better abstract for the same paper",
        authors=["Alice", "Bob", "Carol"],
        year=2025,
        doi="10.1234/test-doi",
        categories=["Machine Learning"],
        tags=["Machine Learning", "Deep Learning"],
        has_pdf=False,
        is_withdrawn=False,
    )

    canonical_docs = reconcile_documents([arxiv_doc, openalex_doc])

    assert len(canonical_docs) == 1
    canonical = canonical_docs[0]

    assert canonical.source_count == 2
    assert len(canonical.doc_ids) == 2
    assert canonical.doi == "10.1234/test-doi"
    assert "Carol" in canonical.authors
    assert canonical.title == "A Great ML Paper Extended Title"