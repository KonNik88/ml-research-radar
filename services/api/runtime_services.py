from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.api.settings import ApiSettings


RUNTIME_SERVICE_CONTRACT_VERSION = "runtime_services_v0.1"

ServiceStatus = dict[str, Any]


def _service(
    *,
    status: str,
    available: bool | None,
    configured: bool,
    required: bool,
    health_blocking: bool,
    reason: str | None = None,
    backend_mode: str | None = None,
    endpoints: list[str] | None = None,
    caveats: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ServiceStatus:
    payload: ServiceStatus = {
        "status": status,
        "available": available,
        "configured": configured,
        "required": required,
        "health_blocking": health_blocking,
        "reason": reason,
        "backend_mode": backend_mode,
        "endpoints": endpoints or [],
        "caveats": caveats or [],
        "metadata": metadata or {},
    }
    return payload


def _available_service(
    *,
    required: bool,
    health_blocking: bool,
    backend_mode: str,
    endpoints: list[str],
    metadata: dict[str, Any] | None = None,
) -> ServiceStatus:
    return _service(
        status="available",
        available=True,
        configured=True,
        required=required,
        health_blocking=health_blocking,
        backend_mode=backend_mode,
        endpoints=endpoints,
        metadata=metadata,
    )


def _missing_service(
    *,
    status: str,
    reason: str,
    required: bool,
    health_blocking: bool,
    backend_mode: str,
    configured: bool = True,
    available: bool | None = False,
    endpoints: list[str] | None = None,
    caveats: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ServiceStatus:
    return _service(
        status=status,
        available=available,
        configured=configured,
        required=required,
        health_blocking=health_blocking,
        reason=reason,
        backend_mode=backend_mode,
        endpoints=endpoints,
        caveats=caveats,
        metadata=metadata,
    )


def _component_available(
    loaded_components: Mapping[str, Any],
    *names: str,
) -> bool:
    return all(bool(loaded_components.get(name)) for name in names)


def _service_counts(services: Mapping[str, ServiceStatus]) -> dict[str, int]:
    required = [service for service in services.values() if service["required"]]
    optional = [service for service in services.values() if not service["required"]]
    health_blocking = [
        service for service in services.values() if service["health_blocking"]
    ]

    return {
        "service_count": len(services),
        "required_count": len(required),
        "required_available_count": sum(
            1 for service in required if service["available"] is True
        ),
        "optional_count": len(optional),
        "optional_available_count": sum(
            1 for service in optional if service["available"] is True
        ),
        "optional_unavailable_count": sum(
            1 for service in optional if service["available"] is False
        ),
        "health_blocking_count": len(health_blocking),
        "health_blocking_available_count": sum(
            1 for service in health_blocking if service["available"] is True
        ),
    }


def _overall_status(
    *,
    ready: bool,
    services: Mapping[str, ServiceStatus],
) -> str:
    if not ready:
        return "unavailable"

    for service in services.values():
        if service["health_blocking"] and service["available"] is not True:
            return "unavailable"

    return "ready"


def build_runtime_service_status(
    *,
    snapshot: Mapping[str, Any],
    settings: ApiSettings,
) -> dict[str, Any]:
    """Build a stable service-capability view for the API runtime.

    This is intentionally a pure projection over the already loaded runtime
    snapshot and settings. It must not perform network, Qdrant, or database
    probes on its own; endpoint-local checks remain owned by their endpoints.
    """

    backend_mode = str(snapshot.get("backend_mode") or "unknown")
    ready = bool(snapshot.get("ready"))
    db_connected = bool(snapshot.get("db_connected"))
    loaded_components = snapshot.get("loaded_components") or {}
    if not isinstance(loaded_components, Mapping):
        loaded_components = {}

    qdrant = snapshot.get("qdrant")
    qdrant_ok = bool(qdrant.get("ok")) if isinstance(qdrant, Mapping) else None
    qdrant_reason = None
    if isinstance(qdrant, Mapping):
        qdrant_reason = qdrant.get("error")
        if qdrant_reason is None and qdrant.get("collection_exists") is False:
            qdrant_reason = "Qdrant collection is not available"

    file_runtime_ready = (
        backend_mode == "file"
        and ready
        and _component_available(
            loaded_components,
            "manifest",
            "documents",
            "lexical_artifacts",
        )
    )
    dense_file_ready = (
        file_runtime_ready
        and _component_available(
            loaded_components,
            "dense_artifacts",
            "embedding_model",
        )
    )
    db_runtime_ready = backend_mode == "db" and ready and db_connected

    services: dict[str, ServiceStatus] = {}

    services["api_runtime"] = (
        _available_service(
            required=True,
            health_blocking=True,
            backend_mode=backend_mode,
            endpoints=["/health", "/info", "/runtime"],
            metadata={"build_id": snapshot.get("build_id")},
        )
        if ready
        else _missing_service(
            status="unavailable",
            reason=str(snapshot.get("last_load_error") or "Runtime is not ready"),
            required=True,
            health_blocking=True,
            backend_mode=backend_mode,
            endpoints=["/health", "/info", "/runtime"],
        )
    )

    if backend_mode == "file":
        services["file_retrieval_runtime"] = (
            _available_service(
                required=True,
                health_blocking=True,
                backend_mode=backend_mode,
                endpoints=["/search", "/discovery/profiles", "/discovery/ranking/{profile_name}"],
                metadata={"corpus_doc_count": snapshot.get("corpus_doc_count")},
            )
            if file_runtime_ready
            else _missing_service(
                status="unavailable",
                reason="File retrieval artifacts are incomplete",
                required=True,
                health_blocking=True,
                backend_mode=backend_mode,
                endpoints=["/search", "/discovery/profiles", "/discovery/ranking/{profile_name}"],
            )
        )
        services["postgres_document_runtime"] = _missing_service(
            status="not_configured",
            reason="PostgreSQL document serving is not selected in file backend mode",
            required=False,
            health_blocking=False,
            backend_mode=backend_mode,
            configured=False,
            endpoints=["/documents", "/artifacts"],
        )
    elif backend_mode == "db":
        services["file_retrieval_runtime"] = _missing_service(
            status="not_configured",
            reason="File retrieval artifacts are not loaded in DB backend mode",
            required=False,
            health_blocking=False,
            backend_mode=backend_mode,
            configured=False,
            endpoints=["/search", "/discovery/profiles", "/discovery/ranking/{profile_name}"],
        )
        services["postgres_document_runtime"] = (
            _available_service(
                required=True,
                health_blocking=True,
                backend_mode=backend_mode,
                endpoints=["/documents", "/artifacts", "/search"],
                metadata={"db_connected": db_connected},
            )
            if db_runtime_ready
            else _missing_service(
                status="unavailable",
                reason="PostgreSQL document store is not connected",
                required=True,
                health_blocking=True,
                backend_mode=backend_mode,
                endpoints=["/documents", "/artifacts", "/search"],
                metadata={"db_connected": db_connected},
            )
        )
    else:
        services["file_retrieval_runtime"] = _missing_service(
            status="unsupported",
            reason=f"Unsupported backend mode: {backend_mode}",
            required=True,
            health_blocking=True,
            backend_mode=backend_mode,
        )
        services["postgres_document_runtime"] = _missing_service(
            status="unsupported",
            reason=f"Unsupported backend mode: {backend_mode}",
            required=True,
            health_blocking=True,
            backend_mode=backend_mode,
        )

    services["search_lexical"] = (
        _available_service(
            required=True,
            health_blocking=True,
            backend_mode=backend_mode,
            endpoints=["/search?mode=lexical"],
        )
        if (file_runtime_ready or db_runtime_ready)
        else _missing_service(
            status="unavailable",
            reason="Lexical search requires a ready file or DB runtime",
            required=True,
            health_blocking=True,
            backend_mode=backend_mode,
            endpoints=["/search?mode=lexical"],
        )
    )

    for service_name, endpoint in (
        ("search_dense", "/search?mode=dense"),
        ("search_hybrid", "/search?mode=hybrid"),
    ):
        if backend_mode == "file":
            services[service_name] = (
                _available_service(
                    required=False,
                    health_blocking=False,
                    backend_mode=backend_mode,
                    endpoints=[endpoint],
                )
                if dense_file_ready
                else _missing_service(
                    status="unavailable",
                    reason="Dense artifacts or embedding model are not loaded",
                    required=False,
                    health_blocking=False,
                    backend_mode=backend_mode,
                    endpoints=[endpoint],
                )
            )
        elif backend_mode == "db":
            services[service_name] = _missing_service(
                status="unsupported",
                reason=f"{service_name} is not supported for DB backend v1",
                required=False,
                health_blocking=False,
                backend_mode=backend_mode,
                available=False,
                endpoints=[endpoint],
            )
        else:
            services[service_name] = _missing_service(
                status="unsupported",
                reason=f"Unsupported backend mode: {backend_mode}",
                required=False,
                health_blocking=False,
                backend_mode=backend_mode,
                endpoints=[endpoint],
            )

    services["artifact_api"] = (
        _available_service(
            required=False,
            health_blocking=False,
            backend_mode=backend_mode,
            endpoints=["/artifacts", "/documents/{canonical_id}/artifacts"],
            metadata={"db_connected": db_connected},
        )
        if db_runtime_ready
        else _missing_service(
            status=(
                "not_configured" if backend_mode == "file" else "unavailable"
            ),
            reason="Artifact API is DB-backed in v0.1",
            required=False,
            health_blocking=False,
            backend_mode=backend_mode,
            configured=backend_mode == "db",
            endpoints=["/artifacts", "/documents/{canonical_id}/artifacts"],
            metadata={"db_connected": db_connected},
        )
    )

    workspace_known_available = db_runtime_ready
    services["workspace_collections"] = (
        _available_service(
            required=False,
            health_blocking=False,
            backend_mode=backend_mode,
            endpoints=["/collections"],
            metadata={
                "uses_postgres": True,
                "explicit_database_url": bool(settings.workspace_database_url),
            },
        )
        if workspace_known_available
        else _missing_service(
            status="unknown",
            reason=(
                "Workspace availability is checked by /collections endpoints; "
                "/runtime does not perform a workspace DB probe"
            ),
            required=False,
            health_blocking=False,
            backend_mode=backend_mode,
            configured=True,
            available=None,
            endpoints=["/collections"],
            metadata={
                "uses_postgres": True,
                "explicit_database_url": bool(settings.workspace_database_url),
            },
        )
    )

    if backend_mode != "file":
        services["qdrant_experimental"] = _missing_service(
            status="unsupported",
            reason="Experimental Qdrant search requires file backend runtime",
            required=False,
            health_blocking=False,
            backend_mode=backend_mode,
            endpoints=["/experimental/search/qdrant"],
            caveats=["optional_vector_serving_backend"],
        )
    elif qdrant_ok is True:
        services["qdrant_experimental"] = _available_service(
            required=False,
            health_blocking=False,
            backend_mode=backend_mode,
            endpoints=["/experimental/search/qdrant"],
            metadata={
                "collection_name": (
                    qdrant.get("collection_name") if isinstance(qdrant, Mapping) else None
                ),
                "profile_name": (
                    qdrant.get("profile_name") if isinstance(qdrant, Mapping) else None
                ),
            },
        )
    else:
        services["qdrant_experimental"] = _missing_service(
            status="unavailable" if qdrant_ok is False else "unknown",
            reason=str(qdrant_reason or "Qdrant diagnostics are not available"),
            required=False,
            health_blocking=False,
            backend_mode=backend_mode,
            endpoints=["/experimental/search/qdrant"],
            caveats=["optional_vector_serving_backend"],
            available=False if qdrant_ok is False else None,
        )

    citation_configured = bool(settings.citation_graph_api_enabled)
    citation_graph_root_exists = settings.citation_graph_root.exists()
    citation_available = citation_configured and citation_graph_root_exists
    services["citation_graph"] = (
        _available_service(
            required=False,
            health_blocking=False,
            backend_mode=backend_mode,
            endpoints=[
                "/citation-graph/status",
                "/citation-graph/papers/{canonical_id}/references",
                "/citation-graph/papers/{canonical_id}/citations",
            ],
            caveats=[
                "metadata_reference_fields_only",
                "not_a_complete_citation_index",
                "not_promoted_full_graph_runtime",
            ],
            metadata={"graph_root": str(settings.citation_graph_root)},
        )
        if citation_available
        else _missing_service(
            status="not_configured" if not citation_configured else "unavailable",
            reason=(
                "Citation graph API is disabled"
                if not citation_configured
                else "Citation graph root is not available"
            ),
            required=False,
            health_blocking=False,
            backend_mode=backend_mode,
            configured=citation_configured,
            endpoints=[
                "/citation-graph/status",
                "/citation-graph/papers/{canonical_id}/references",
                "/citation-graph/papers/{canonical_id}/citations",
            ],
            caveats=[
                "metadata_reference_fields_only",
                "not_a_complete_citation_index",
                "not_promoted_full_graph_runtime",
            ],
            metadata={"graph_root": str(settings.citation_graph_root)},
        )
    )

    counts = _service_counts(services)
    service_caveats = sorted(
        {
            caveat
            for service in services.values()
            for caveat in service.get("caveats", [])
        }
    )

    return {
        "schema_version": RUNTIME_SERVICE_CONTRACT_VERSION,
        "overall_status": _overall_status(ready=ready, services=services),
        "backend_mode": backend_mode,
        "services": services,
        "counts": counts,
        "caveats": service_caveats,
    }
