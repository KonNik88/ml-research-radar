from __future__ import annotations

import asyncio
import json

from fastapi.exceptions import RequestValidationError

from services.api.app import app, handle_validation_error
from services.api.runtime import ApiRuntime
from services.api.workspace.errors import WorkspaceError


def test_workspace_routes_match_v01_contract() -> None:
    actual = {
        (method, route.path)
        for route in app.routes
        for method in (route.methods or set())
        if route.path.startswith("/collections")
    }

    assert actual == {
        ("POST", "/collections"),
        ("GET", "/collections"),
        ("GET", "/collections/{collection_id}"),
        ("PATCH", "/collections/{collection_id}"),
        ("DELETE", "/collections/{collection_id}"),
        (
            "PUT",
            "/collections/{collection_id}/items/{canonical_id}",
        ),
        (
            "PATCH",
            "/collections/{collection_id}/items/{canonical_id}",
        ),
        (
            "DELETE",
            "/collections/{collection_id}/items/{canonical_id}",
        ),
    }


def test_workspace_domain_error_handler_is_registered() -> None:
    assert WorkspaceError in app.exception_handlers


def test_validation_handler_serializes_pydantic_error_context() -> None:
    error = RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("body",),
                "msg": "Value error, invalid patch",
                "input": {},
                "ctx": {"error": ValueError("invalid patch")},
            }
        ]
    )

    response = asyncio.run(handle_validation_error(None, error))
    payload = json.loads(response.body)

    assert response.status_code == 422
    assert payload["error_code"] == "validation_error"
    assert payload["details"]["errors"][0]["msg"] == ("Value error, invalid patch")


def test_workspace_modules_do_not_extend_document_store_with_user_state() -> None:
    from services.api.db import PostgresDocumentStore

    forbidden_methods = {
        "create_collection",
        "update_collection",
        "delete_collection",
        "upsert_collection_item",
    }

    assert forbidden_methods.isdisjoint(dir(PostgresDocumentStore))


def test_current_paper_lookup_supports_file_and_db_backends() -> None:
    file_record = {"canonical_id": "file-paper", "title": "File paper"}
    file_runtime = ApiRuntime(
        backend_mode="file",
        document_index={"file-paper": file_record},
    )
    assert file_runtime.get_documents_by_ids(["file-paper", "missing"]) == {
        "file-paper": file_record
    }

    class FakeDocumentStore:
        def get_documents_by_ids(self, canonical_ids):
            return {
                canonical_id: {
                    "canonical_id": canonical_id,
                    "title": "DB paper",
                }
                for canonical_id in canonical_ids
            }

    db_runtime = ApiRuntime(
        backend_mode="db",
        db_store=FakeDocumentStore(),
    )
    assert set(db_runtime.get_documents_by_ids(["db-paper"])) == {"db-paper"}
