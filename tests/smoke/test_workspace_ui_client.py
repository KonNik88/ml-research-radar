from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
import requests

from services.ui.workspace_client import WorkspaceClient, WorkspaceClientError


@dataclass
class FakeResponse:
    status_code: int = 200
    payload: Any = field(default_factory=dict)
    content_type: str = "application/json"
    text: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 400

    @property
    def headers(self) -> dict[str, str]:
        return {"content-type": self.content_type}

    def json(self) -> Any:
        return self.payload


class RequestRecorder:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)


def test_workspace_client_collection_crud_contract() -> None:
    recorder = RequestRecorder(
        [
            FakeResponse(payload={"total": 0, "results": []}),
            FakeResponse(status_code=201, payload={"collection_id": "c-1"}),
            FakeResponse(payload={"collection_id": "c-1", "name": "Updated"}),
            FakeResponse(status_code=204),
        ]
    )
    client = WorkspaceClient(
        "http://127.0.0.1:8000/",
        timeout_seconds=7,
        request_func=recorder,
    )

    assert client.list_collections(limit=25, offset=5)["total"] == 0
    assert client.create_collection(name="Papers", description=None) == {
        "collection_id": "c-1"
    }
    assert client.update_collection("c-1", name="Updated")["name"] == "Updated"
    assert client.delete_collection("c-1") is None

    assert recorder.calls == [
        {
            "method": "GET",
            "url": "http://127.0.0.1:8000/collections",
            "params": {"limit": 25, "offset": 5},
            "json": None,
            "timeout": 7,
        },
        {
            "method": "POST",
            "url": "http://127.0.0.1:8000/collections",
            "params": None,
            "json": {"name": "Papers", "description": None},
            "timeout": 7,
        },
        {
            "method": "PATCH",
            "url": "http://127.0.0.1:8000/collections/c-1",
            "params": None,
            "json": {"name": "Updated"},
            "timeout": 7,
        },
        {
            "method": "DELETE",
            "url": "http://127.0.0.1:8000/collections/c-1",
            "params": None,
            "json": None,
            "timeout": 7,
        },
    ]


def test_workspace_client_item_contract_and_path_encoding() -> None:
    recorder = RequestRecorder(
        [
            FakeResponse(payload={"reading_status": "to_read"}),
            FakeResponse(payload={"reading_status": "reading", "note": "Inspect"}),
            FakeResponse(status_code=204),
        ]
    )
    client = WorkspaceClient("http://api", request_func=recorder)

    client.upsert_item("collection/one", "arxiv/1234.5678")
    client.update_item(
        "collection/one",
        "arxiv/1234.5678",
        note="Inspect",
        reading_status="reading",
    )
    client.delete_item("collection/one", "arxiv/1234.5678")

    expected_path = "/collections/collection%2Fone/items/arxiv%2F1234.5678"
    assert [call["url"] for call in recorder.calls] == [
        f"http://api{expected_path}",
        f"http://api{expected_path}",
        f"http://api{expected_path}",
    ]
    assert recorder.calls[0]["json"] == {}
    assert recorder.calls[1]["json"] == {
        "note": "Inspect",
        "reading_status": "reading",
    }


def test_workspace_client_preserves_structured_domain_error() -> None:
    recorder = RequestRecorder(
        [
            FakeResponse(
                status_code=409,
                payload={
                    "error_code": "collection_name_conflict",
                    "message": "Collection already exists",
                    "details": {"name": "Research"},
                },
            )
        ]
    )
    client = WorkspaceClient("http://api", request_func=recorder)

    with pytest.raises(WorkspaceClientError) as exc_info:
        client.create_collection(name="Research")

    error = exc_info.value
    assert error.status_code == 409
    assert error.error_code == "collection_name_conflict"
    assert error.details == {"name": "Research"}
    assert str(error) == (
        "collection_name_conflict: Collection already exists "
        "Details: {'name': 'Research'}"
    )


def test_workspace_client_wraps_transport_failure() -> None:
    def fail_request(*args: Any, **kwargs: Any) -> FakeResponse:
        raise requests.ConnectionError("offline")

    client = WorkspaceClient("http://api", request_func=fail_request)

    with pytest.raises(WorkspaceClientError, match="workspace_request_failed"):
        client.list_collections()


def test_workspace_client_rejects_empty_patch_and_ids() -> None:
    client = WorkspaceClient("http://api", request_func=RequestRecorder([]))

    with pytest.raises(ValueError, match="At least one collection field"):
        client.update_collection("collection-id")
    with pytest.raises(ValueError, match="At least one item field"):
        client.update_item("collection-id", "paper-id")
    with pytest.raises(ValueError, match="canonical_id must not be blank"):
        client.delete_item("collection-id", " ")
