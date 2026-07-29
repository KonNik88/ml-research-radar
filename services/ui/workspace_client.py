from __future__ import annotations

from typing import Any, Callable
from urllib.parse import quote

import requests


_UNSET = object()


class WorkspaceClientError(RuntimeError):
    """Structured error returned by the durable workspace API."""

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


class WorkspaceClient:
    """Thin synchronous client for Saved Research Collections v0.1."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 30,
        request_func: Callable[..., requests.Response] | None = None,
    ) -> None:
        cleaned_base_url = str(base_url or "").strip().rstrip("/")
        if not cleaned_base_url:
            raise ValueError("Workspace API base URL must not be blank")

        self.base_url = cleaned_base_url
        self.timeout_seconds = timeout_seconds
        self._request_func = request_func or requests.request

    @staticmethod
    def _path_value(value: Any, *, field_name: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"{field_name} must not be blank")
        return quote(normalized, safe="")

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = self._request_func(
                method,
                url,
                params=params,
                json=json_payload,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise WorkspaceClientError(
                "workspace_request_failed",
                f"Could not reach the workspace API: {exc}",
            ) from exc

        if response.status_code == 204:
            return {}

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
            raise WorkspaceClientError(
                "workspace_invalid_response",
                "Workspace API returned a non-object JSON response.",
                status_code=response.status_code,
            )

        if not isinstance(payload, dict):
            payload = {}

        raise WorkspaceClientError(
            str(payload.get("error_code") or f"http_{response.status_code}"),
            str(payload.get("message") or "Workspace request failed"),
            status_code=response.status_code,
            details=payload.get("details"),
        )

    def list_collections(self, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return self._request(
            "GET",
            "/collections",
            params={"limit": int(limit), "offset": int(offset)},
        )

    def get_collection(self, collection_id: Any) -> dict[str, Any]:
        collection = self._path_value(collection_id, field_name="collection_id")
        return self._request("GET", f"/collections/{collection}")

    def create_collection(
        self,
        *,
        name: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/collections",
            json_payload={"name": name, "description": description},
        )

    def update_collection(
        self,
        collection_id: Any,
        *,
        name: Any = _UNSET,
        description: Any = _UNSET,
    ) -> dict[str, Any]:
        collection = self._path_value(collection_id, field_name="collection_id")
        payload: dict[str, Any] = {}
        if name is not _UNSET:
            payload["name"] = name
        if description is not _UNSET:
            payload["description"] = description
        if not payload:
            raise ValueError("At least one collection field must be supplied")
        return self._request(
            "PATCH",
            f"/collections/{collection}",
            json_payload=payload,
        )

    def delete_collection(self, collection_id: Any) -> None:
        collection = self._path_value(collection_id, field_name="collection_id")
        self._request("DELETE", f"/collections/{collection}")

    def upsert_item(
        self,
        collection_id: Any,
        canonical_id: Any,
        *,
        note: Any = _UNSET,
        reading_status: Any = _UNSET,
    ) -> dict[str, Any]:
        collection = self._path_value(collection_id, field_name="collection_id")
        paper = self._path_value(canonical_id, field_name="canonical_id")
        payload: dict[str, Any] = {}
        if note is not _UNSET:
            payload["note"] = note
        if reading_status is not _UNSET:
            payload["reading_status"] = reading_status
        return self._request(
            "PUT",
            f"/collections/{collection}/items/{paper}",
            json_payload=payload,
        )

    def update_item(
        self,
        collection_id: Any,
        canonical_id: Any,
        *,
        note: Any = _UNSET,
        reading_status: Any = _UNSET,
    ) -> dict[str, Any]:
        collection = self._path_value(collection_id, field_name="collection_id")
        paper = self._path_value(canonical_id, field_name="canonical_id")
        payload: dict[str, Any] = {}
        if note is not _UNSET:
            payload["note"] = note
        if reading_status is not _UNSET:
            payload["reading_status"] = reading_status
        if not payload:
            raise ValueError("At least one item field must be supplied")
        return self._request(
            "PATCH",
            f"/collections/{collection}/items/{paper}",
            json_payload=payload,
        )

    def delete_item(self, collection_id: Any, canonical_id: Any) -> None:
        collection = self._path_value(collection_id, field_name="collection_id")
        paper = self._path_value(canonical_id, field_name="canonical_id")
        self._request("DELETE", f"/collections/{collection}/items/{paper}")
