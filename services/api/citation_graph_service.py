from __future__ import annotations

from services.api.schemas import (
    CitationGraphStatusGraph,
    CitationGraphStatusResponse,
)
from services.api.settings import ApiSettings


GRAPH_NAME = "citation_reference_graph"
STATUS_ENDPOINT = "/citation-graph/status"

DEFAULT_CITATION_GRAPH_CAVEATS = [
    "metadata_reference_fields_only",
    "not_a_complete_citation_index",
    "manual_review_required",
    "publication_ready_false",
]


def build_citation_graph_status(
    *,
    settings: ApiSettings,
) -> CitationGraphStatusResponse:
    """Return a read-only diagnostic status for the future graph API.

    This first code slice intentionally does not load graph artifacts. It only
    exposes the disabled/default runtime boundary required before adding any
    traversal endpoints.
    """

    runtime_enabled = bool(settings.citation_graph_api_enabled)
    error_code = None if runtime_enabled else "graph_runtime_not_enabled"
    message = (
        "Citation/reference graph API is enabled, but graph runtime loading is "
        "not implemented in this slice."
        if runtime_enabled
        else "Citation/reference graph API is disabled by default."
    )

    return CitationGraphStatusResponse(
        graph=CitationGraphStatusGraph(
            name=GRAPH_NAME,
            version=settings.citation_graph_version,
            runtime_enabled=runtime_enabled,
            available=False,
            exposure_mode=settings.citation_graph_exposure_mode,
        ),
        query={
            "endpoint": STATUS_ENDPOINT,
        },
        items=[],
        page={
            "limit": 0,
            "offset": 0,
            "returned": 0,
            "total_estimate": None,
        },
        caveats=list(DEFAULT_CITATION_GRAPH_CAVEATS),
        availability={
            "configured": runtime_enabled,
            "available": False,
            "runtime_enabled": runtime_enabled,
            "safe_to_serve_locally": False,
            "runtime_loader_implemented": False,
            "traversal_endpoints_implemented": False,
        },
        error_code=error_code or "graph_runtime_not_enabled",
        message=message,
    )
