from __future__ import annotations

from typing import Any, Callable

import requests


class ComparisonClientError(RuntimeError):
    """Structured error returned by the paper-comparison API."""

    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details

    def __str__(self) -> str:
        details_text = f" Details: {self.details}" if self.details else ""
        return f"{self.error_code}: {self.message}{details_text}"


class ComparisonClient:
    """Thin synchronous client for Paper Comparison Workspace v0.1."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 30,
        request_func: Callable[..., requests.Response] | None = None,
    ) -> None:
        cleaned_base_url = str(base_url or "").strip().rstrip("/")
        if not cleaned_base_url:
            raise ValueError("Comparison API base URL must not be blank")

        self.base_url = cleaned_base_url
        self.timeout_seconds = timeout_seconds
        self._request_func = request_func or requests.request

    @staticmethod
    def _error_fields(
        payload: dict[str, Any],
        *,
        status_code: int,
    ) -> tuple[str, str, Any]:
        error_code = str(
            payload.get("error_code") or f"http_{status_code}"
        )
        message = payload.get("message")
        details = payload.get("details")
        detail = payload.get("detail")

        if isinstance(detail, dict):
            message = message or detail.get("message")
            details = details if details is not None else detail
        elif isinstance(detail, list):
            message = message or "Comparison request validation failed"
            details = details if details is not None else detail
        elif detail not in (None, ""):
            message = message or str(detail)

        return error_code, str(message or "Comparison request failed"), details

    def compare_papers(self, canonical_ids: list[str]) -> dict[str, Any]:
        normalized_ids = [str(value).strip() for value in canonical_ids]
        url = f"{self.base_url}/discovery/papers/compare"

        try:
            response = self._request_func(
                "POST",
                url,
                params=None,
                json={"canonical_ids": normalized_ids},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise ComparisonClientError(
                "comparison_request_failed",
                f"Could not reach the comparison API: {exc}",
            ) from exc

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type.lower():
            try:
                payload: Any = response.json()
            except ValueError:
                payload = {"message": response.text}
        else:
            payload = {"message": response.text}

        if response.ok:
            if isinstance(payload, dict):
                return payload
            raise ComparisonClientError(
                "comparison_invalid_response",
                "Comparison API returned a non-object JSON response.",
                status_code=response.status_code,
            )

        if not isinstance(payload, dict):
            payload = {}
        error_code, message, details = self._error_fields(
            payload,
            status_code=response.status_code,
        )
        raise ComparisonClientError(
            error_code,
            message,
            status_code=response.status_code,
            details=details,
        )
