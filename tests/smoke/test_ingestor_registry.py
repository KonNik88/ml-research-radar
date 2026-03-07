import pytest

from radar_core.ingest.registry import get_ingestor


def test_get_ingestor_arxiv():
    ingestor = get_ingestor("arxiv")
    assert ingestor.source_name == "arxiv"


def test_get_ingestor_unknown_source():
    with pytest.raises(ValueError):
        get_ingestor("unknown_source")