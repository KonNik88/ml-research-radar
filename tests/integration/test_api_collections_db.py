from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.pool import NullPool

from services.api.db import PostgresConfig, PostgresDocumentStore
from services.api.runtime import ApiRuntime
from services.api.schemas import ErrorResponse
from services.api.workspace.errors import WorkspaceError
from services.api.workspace.router import (
    get_workspace_service,
    router,
)
from services.api.workspace.service import (
    RuntimePaperCatalog,
    WorkspaceService,
)
from services.api.workspace.store import (
    WorkspacePostgresConfig,
    WorkspaceStore,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL_ENV = "ML_RADAR_WORKSPACE_TEST_DATABASE_URL"


@dataclass
class CollectionsApiHarness:
    engine: Engine
    database_url: str
    service: WorkspaceService


def _require_disposable_test_url() -> URL:
    raw_url = os.getenv(TEST_DATABASE_URL_ENV)
    if not raw_url:
        pytest.skip(
            f"{TEST_DATABASE_URL_ENV} is not set; "
            "workspace API database integration test was not requested"
        )

    try:
        url = make_url(raw_url)
    except sa.exc.ArgumentError as exc:
        pytest.fail(f"{TEST_DATABASE_URL_ENV} is invalid: {exc}")

    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    if url.drivername != "postgresql+psycopg":
        pytest.fail(f"{TEST_DATABASE_URL_ENV} must use PostgreSQL with psycopg")

    database = (url.database or "").lower()
    if database == "ml_radar":
        pytest.fail("Refusing to run workspace API tests against ml_radar")
    if not re.search(r"(?:^test_|_test$|_test_)", database):
        pytest.fail(
            "Disposable database name must start with 'test_' or contain/end in '_test'"
        )
    return url


def _alembic_config() -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(PROJECT_ROOT / "store" / "alembic"),
    )
    return config


def _reset_test_state(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql('DROP SCHEMA IF EXISTS "workspace" CASCADE')
        connection.exec_driver_sql("DROP TABLE IF EXISTS public.alembic_version")
        connection.exec_driver_sql("DROP TABLE IF EXISTS public.canonical_documents")


def _create_canonical_fixture(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE public.canonical_documents (
                canonical_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                authors JSONB NOT NULL DEFAULT '[]'::jsonb,
                year INTEGER,
                venue TEXT,
                landing_page_url TEXT,
                pdf_url TEXT
            )
            """
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO public.canonical_documents (
                    canonical_id,
                    title,
                    authors,
                    year,
                    venue
                )
                VALUES (
                    :canonical_id,
                    :title,
                    CAST(:authors AS JSONB),
                    :year,
                    :venue
                )
                """
            ),
            {
                "canonical_id": "paper-api-1",
                "title": "Workspace API Integration",
                "authors": '["Test Author"]',
                "year": 2026,
                "venue": "ML Radar Tests",
            },
        )


def _document_store(url: URL) -> PostgresDocumentStore:
    return PostgresDocumentStore(
        PostgresConfig(
            host=url.host or "127.0.0.1",
            port=url.port or 5432,
            dbname=url.database or "",
            user=url.username or "",
            password=url.password or "",
        )
    )


def _workspace_service(
    *,
    database_url: str,
    url: URL,
) -> WorkspaceService:
    runtime = ApiRuntime(
        backend_mode="db",
        db_store=_document_store(url),
    )
    return WorkspaceService(
        store=WorkspaceStore(WorkspacePostgresConfig(database_url=database_url)),
        paper_catalog=RuntimePaperCatalog(lambda: runtime),
    )


def _test_app(service: WorkspaceService) -> FastAPI:
    api = FastAPI()
    api.include_router(router)
    api.dependency_overrides[get_workspace_service] = lambda: service

    @api.exception_handler(WorkspaceError)
    async def handle_workspace_error(
        _: Request,
        exc: WorkspaceError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error_code=exc.error_code,
                message=exc.message,
                details=exc.details,
            ).model_dump(),
        )

    @api.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error_code="validation_error",
                message="Request validation failed",
                details={"errors": jsonable_encoder(exc.errors())},
            ).model_dump(),
        )

    return api


@pytest.fixture
def collections_api_harness(
    monkeypatch: pytest.MonkeyPatch,
) -> CollectionsApiHarness:
    url = _require_disposable_test_url()
    rendered_url = url.render_as_string(hide_password=False)
    engine = sa.create_engine(url, poolclass=NullPool)

    try:
        with engine.connect() as connection:
            assert connection.scalar(sa.text("SELECT 1")) == 1

        _reset_test_state(engine)
        _create_canonical_fixture(engine)
        monkeypatch.setenv(
            "ML_RADAR_WORKSPACE_DATABASE_URL",
            rendered_url,
        )
        command.upgrade(_alembic_config(), "head")

        yield CollectionsApiHarness(
            engine=engine,
            database_url=rendered_url,
            service=_workspace_service(
                database_url=rendered_url,
                url=url,
            ),
        )
    finally:
        _reset_test_state(engine)
        engine.dispose()


def test_collections_api_full_crud_and_restart_persistence(
    collections_api_harness: CollectionsApiHarness,
) -> None:
    harness = collections_api_harness
    api = _test_app(harness.service)

    with TestClient(api) as client:
        create_response = client.post(
            "/collections",
            json={
                "name": "  API papers  ",
                "description": "Persistent test collection",
            },
        )
        assert create_response.status_code == 201
        collection = create_response.json()
        collection_id = collection["collection_id"]
        assert collection["name"] == "API papers"
        assert collection["item_count"] == 0

        conflict_response = client.post(
            "/collections",
            json={"name": "api PAPERS"},
        )
        assert conflict_response.status_code == 409
        assert conflict_response.json()["error_code"] == "collection_name_conflict"

        missing_paper_response = client.put(
            f"/collections/{collection_id}/items/missing-paper",
            json={},
        )
        assert missing_paper_response.status_code == 404
        assert missing_paper_response.json()["error_code"] == "paper_not_found"

        save_response = client.put(
            f"/collections/{collection_id}/items/paper-api-1",
            json={
                "note": "Keep this note",
                "reading_status": "reading",
            },
        )
        assert save_response.status_code == 200
        saved = save_response.json()
        assert saved["canonical_id"] == "paper-api-1"
        assert saved["note"] == "Keep this note"
        assert saved["reading_status"] == "reading"
        assert saved["orphaned"] is False
        assert saved["paper"]["title"] == "Workspace API Integration"
        added_at = saved["added_at"]

        repeated_response = client.put(
            f"/collections/{collection_id}/items/paper-api-1",
            json={},
        )
        assert repeated_response.status_code == 200
        repeated = repeated_response.json()
        assert repeated["added_at"] == added_at
        assert repeated["note"] == "Keep this note"
        assert repeated["reading_status"] == "reading"

        rename_response = client.patch(
            f"/collections/{collection_id}",
            json={
                "name": "Renamed API papers",
                "description": None,
            },
        )
        assert rename_response.status_code == 200
        renamed = rename_response.json()
        assert renamed["name"] == "Renamed API papers"
        assert renamed["description"] is None
        assert renamed["item_count"] == 1

        list_response = client.get("/collections")
        assert list_response.status_code == 200
        listing = list_response.json()
        assert listing["total"] == 1
        assert listing["results"][0]["collection_id"] == collection_id
        assert listing["results"][0]["item_count"] == 1

        invalid_patch = client.patch(
            f"/collections/{collection_id}/items/paper-api-1",
            json={},
        )
        assert invalid_patch.status_code == 422
        assert invalid_patch.json()["error_code"] == "validation_error"

    # Recreate both the store and the API surface: rows must not depend on
    # process-local state.
    url = _require_disposable_test_url()
    restarted_service = _workspace_service(
        database_url=harness.database_url,
        url=url,
    )
    restarted_api = _test_app(restarted_service)

    with TestClient(restarted_api) as client:
        detail_response = client.get(f"/collections/{collection_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert detail["item_count"] == 1
        assert detail["items"][0]["note"] == "Keep this note"
        assert detail["items"][0]["reading_status"] == "reading"

        with harness.engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    DELETE FROM public.canonical_documents
                    WHERE canonical_id = :canonical_id
                    """
                ),
                {"canonical_id": "paper-api-1"},
            )

        orphan_response = client.get(f"/collections/{collection_id}")
        assert orphan_response.status_code == 200
        orphan = orphan_response.json()["items"][0]
        assert orphan["orphaned"] is True
        assert orphan["paper"] is None
        assert orphan["note"] == "Keep this note"

        orphan_patch = client.patch(
            f"/collections/{collection_id}/items/paper-api-1",
            json={"note": None, "reading_status": "read"},
        )
        assert orphan_patch.status_code == 200
        assert orphan_patch.json()["orphaned"] is True
        assert orphan_patch.json()["note"] is None
        assert orphan_patch.json()["reading_status"] == "read"

        delete_item = client.delete(f"/collections/{collection_id}/items/paper-api-1")
        assert delete_item.status_code == 204

        missing_item = client.delete(f"/collections/{collection_id}/items/paper-api-1")
        assert missing_item.status_code == 404
        assert missing_item.json()["error_code"] == "collection_item_not_found"

        delete_collection = client.delete(f"/collections/{collection_id}")
        assert delete_collection.status_code == 204

        missing_collection = client.get(f"/collections/{collection_id}")
        assert missing_collection.status_code == 404
        assert missing_collection.json()["error_code"] == "collection_not_found"
