from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
import requests

from services.ui.comparison_client import ComparisonClient, ComparisonClientError


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


def test_comparison_client_sends_one_ordered_batch_request() -> None:
    recorder = RequestRecorder(
        [
            FakeResponse(
                payload={
                    "schema_version": "paper_comparison_v0.1",
                    "canonical_ids": ["paper-b", "paper-a"],
                    "paper_count": 2,
                }
            )
        ]
    )
    client = ComparisonClient(
        "http://127.0.0.1:8000/",
        timeout_seconds=9,
        request_func=recorder,
    )

    payload = client.compare_papers([" paper-b ", "paper-a"])

    assert payload["canonical_ids"] == ["paper-b", "paper-a"]
    assert recorder.calls == [
        {
            "method": "POST",
            "url": "http://127.0.0.1:8000/discovery/papers/compare",
            "params": None,
            "json": {"canonical_ids": ["paper-b", "paper-a"]},
            "timeout": 9,
        }
    ]


def test_comparison_client_preserves_missing_paper_details() -> None:
    recorder = RequestRecorder(
        [
            FakeResponse(
                status_code=404,
                payload={
                    "detail": {
                        "message": "One or more papers were not found.",
                        "missing_canonical_ids": ["missing-paper"],
                    }
                },
            )
        ]
    )
    client = ComparisonClient("http://api", request_func=recorder)

    with pytest.raises(ComparisonClientError) as exc_info:
        client.compare_papers(["known-paper", "missing-paper"])

    error = exc_info.value
    assert error.status_code == 404
    assert error.error_code == "http_404"
    assert error.message == "One or more papers were not found."
    assert error.details == {
        "message": "One or more papers were not found.",
        "missing_canonical_ids": ["missing-paper"],
    }


def test_comparison_client_preserves_validation_error_rows() -> None:
    detail = [
        {
            "type": "value_error",
            "loc": ["body", "canonical_ids"],
            "msg": "canonical_ids must be unique",
        }
    ]
    recorder = RequestRecorder(
        [
            FakeResponse(
                status_code=422,
                payload={"error_code": "validation_error", "details": detail},
            )
        ]
    )
    client = ComparisonClient("http://api", request_func=recorder)

    with pytest.raises(ComparisonClientError) as exc_info:
        client.compare_papers(["paper-a", "paper-a"])

    assert exc_info.value.error_code == "validation_error"
    assert exc_info.value.details == detail


def test_comparison_client_wraps_transport_failure() -> None:
    def fail_request(*args: Any, **kwargs: Any) -> FakeResponse:
        raise requests.ConnectionError("offline")

    client = ComparisonClient("http://api", request_func=fail_request)

    with pytest.raises(ComparisonClientError, match="comparison_request_failed"):
        client.compare_papers(["paper-a", "paper-b"])


def test_comparison_client_rejects_non_object_success_response() -> None:
    recorder = RequestRecorder([FakeResponse(payload=["unexpected"])])
    client = ComparisonClient("http://api", request_func=recorder)

    with pytest.raises(
        ComparisonClientError,
        match="comparison_invalid_response",
    ):
        client.compare_papers(["paper-a", "paper-b"])
