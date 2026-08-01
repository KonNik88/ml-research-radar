from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from services.api.runtime_services import (
    RUNTIME_SERVICE_CONTRACT_VERSION,
    build_runtime_service_status,
)
from services.api.schemas import RuntimeSnapshotResponse


def _settings(**overrides):
    values = {
        "workspace_database_url": None,
        "citation_graph_api_enabled": False,
        "citation_graph_root": Path("data/graphs/citation_reference_graph/v0.1"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_file_runtime_services_make_optional_qdrant_unavailability_explicit() -> None:
    snapshot = {
        "ready": True,
        "backend_mode": "file",
        "build_id": "build-file",
        "corpus_doc_count": 2,
        "loaded_components": {
            "manifest": True,
            "documents": True,
            "lexical_artifacts": True,
            "dense_artifacts": True,
            "embedding_model": True,
            "db_store": False,
        },
        "db_connected": False,
        "qdrant": {
            "ok": False,
            "collection_exists": False,
            "collection_name": "ml_radar_dense_benchmark_v1",
            "profile_name": "ef_256",
            "error": None,
        },
    }

    status = build_runtime_service_status(
        snapshot=snapshot,
        settings=_settings(),
    )

    assert status["schema_version"] == RUNTIME_SERVICE_CONTRACT_VERSION
    assert status["overall_status"] == "ready"
    assert status["backend_mode"] == "file"
    assert status["services"]["api_runtime"]["available"] is True
    assert status["services"]["file_retrieval_runtime"]["available"] is True
    assert status["services"]["postgres_document_runtime"]["status"] == "not_configured"
    assert status["services"]["search_lexical"]["available"] is True
    assert status["services"]["search_dense"]["available"] is True
    assert status["services"]["search_hybrid"]["available"] is True
    assert status["services"]["artifact_api"]["status"] == "not_configured"
    assert status["services"]["qdrant_experimental"]["status"] == "unavailable"
    assert status["services"]["qdrant_experimental"]["health_blocking"] is False
    assert status["services"]["citation_graph"]["status"] == "not_configured"
    assert status["counts"]["required_available_count"] == status["counts"]["required_count"]


def test_db_runtime_services_reject_dense_without_making_runtime_unhealthy() -> None:
    snapshot = {
        "ready": True,
        "backend_mode": "db",
        "build_id": "db-runtime",
        "corpus_doc_count": 2,
        "loaded_components": {
            "manifest": False,
            "documents": False,
            "lexical_artifacts": False,
            "dense_artifacts": False,
            "embedding_model": False,
            "db_store": True,
        },
        "db_connected": True,
        "qdrant": {
            "ok": False,
            "collection_exists": False,
        },
    }

    status = build_runtime_service_status(
        snapshot=snapshot,
        settings=_settings(workspace_database_url="postgresql://test/test"),
    )

    assert status["overall_status"] == "ready"
    assert status["services"]["postgres_document_runtime"]["available"] is True
    assert status["services"]["search_lexical"]["available"] is True
    assert status["services"]["search_dense"]["status"] == "unsupported"
    assert status["services"]["search_hybrid"]["status"] == "unsupported"
    assert status["services"]["artifact_api"]["available"] is True
    assert status["services"]["workspace_collections"]["available"] is True
    assert status["services"]["qdrant_experimental"]["status"] == "unsupported"
    assert status["counts"]["required_available_count"] == status["counts"]["required_count"]


def test_runtime_snapshot_response_accepts_service_status_contract() -> None:
    payload = RuntimeSnapshotResponse(
        ready=True,
        backend_mode="file",
        build_id="build-file",
        corpus_doc_count=2,
        artifacts_root="artifacts/retrieval",
        loaded_components={"manifest": True},
        db_connected=False,
        service_status={
            "schema_version": RUNTIME_SERVICE_CONTRACT_VERSION,
            "overall_status": "ready",
            "services": {},
            "counts": {},
            "caveats": [],
        },
    ).model_dump()

    assert payload["service_status"]["schema_version"] == RUNTIME_SERVICE_CONTRACT_VERSION
