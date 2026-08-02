# Runtime Service Contract v0.1

status: implemented
contract: runtime_services_v0.1
scope: FastAPI runtime status, Streamlit status sidebar, validation gates

## Purpose

This contract makes runtime capabilities explicit without promoting any optional
or experimental subsystem into canonical truth.

The API has several serving surfaces:

- file retrieval runtime;
- PostgreSQL document/artifact runtime;
- workspace collections;
- optional Qdrant experimental dense search;
- optional citation/reference graph local-inspection surface.

Before this contract, those surfaces were discoverable only by trying endpoint
calls or reading feature-specific docs. `GET /runtime` now exposes a unified
machine-readable `service_status` block.

## Non-goals

This layer does not:

- merge file and DB storage into one physical backend;
- promote Qdrant to the public `/search` backend;
- promote the citation/reference graph to canonical truth;
- require workspace PostgreSQL, Qdrant, or citation graph artifacts for API
  health;
- mutate retrieval artifacts, canonical documents, Postgres schema, or Qdrant.

## Endpoint

`GET /runtime` includes:

```json
{
  "service_status": {
    "schema_version": "runtime_services_v0.1",
    "overall_status": "ready",
    "backend_mode": "db",
    "services": {},
    "counts": {},
    "caveats": []
  }
}
```

Existing `/runtime` fields remain unchanged.

## Service States

Each service row has:

| Field | Meaning |
| --- | --- |
| `status` | One of `available`, `unavailable`, `not_configured`, `unsupported`, `unknown`. |
| `available` | `true`, `false`, or `null` when endpoint-local probing owns the answer. |
| `configured` | Whether the service is configured for the current runtime mode. |
| `required` | Whether the service is required for this backend mode. |
| `health_blocking` | Whether failure should make `/health` fail. |
| `reason` | Human-readable status detail. |
| `backend_mode` | Current API backend mode. |
| `endpoints` | Representative API endpoints for the service. |
| `caveats` | Safety/interpretation caveats. |
| `metadata` | Small service-specific metadata. |

## Service Keys

Required health-blocking services:

| Service | File backend | DB backend |
| --- | --- | --- |
| `api_runtime` | Required | Required |
| `file_retrieval_runtime` | Required | Not configured |
| `postgres_document_runtime` | Not configured | Required |
| `search_lexical` | Required | Required |

Optional services:

| Service | File backend | DB backend |
| --- | --- | --- |
| `search_dense` | Available when dense artifacts and embedding model are loaded | Unsupported in DB backend v1 |
| `search_hybrid` | Available when dense artifacts and embedding model are loaded | Unsupported in DB backend v1 |
| `artifact_api` | Not configured | Available when DB runtime is connected |
| `workspace_collections` | Unknown unless DB runtime proves shared Postgres availability | Available when DB runtime is connected |
| `qdrant_experimental` | Optional; unavailable does not affect `/health` | Unsupported |
| `citation_graph` | Optional; disabled by default | Optional; disabled by default |

## Health Boundary

`overall_status = ready` means all health-blocking services for the selected
backend mode are available.

Optional unavailable services are reported through their own rows and through
`counts.optional_unavailable_count`, but they do not make `/health` fail.

This preserves the project boundary:

canonical truth -> derived retrieval/search/workspace/graph surfaces

Qdrant and citation graph remain derived, optional, and explicitly caveated.

## UI

Streamlit renders the service contract in the sidebar:

- compact required-service readiness;
- contract version;
- backend mode;
- required/optional counts;
- one row per service;
- caveats.

Feature tabs may still show endpoint-specific diagnostics. The sidebar contract
is the high-level service map.

Feature-level actions should use `service_status.services[*]` as the capability
decision source before calling optional or mode-specific endpoints. In v0.2
hardening, the UI gates:

- dense/hybrid search mode actions through `search_dense` and `search_hybrid`;
- experimental Qdrant search through `qdrant_experimental`;
- citation graph traversal and diagnostics through `citation_graph`.

Endpoint-specific diagnostics may still be rendered after a service is available,
but UI availability should not be inferred by triggering endpoint errors.

## Validation

Smoke coverage:

```bash
python -m pytest tests/smoke/test_runtime_service_status.py -q
python -m pytest tests/smoke/test_streamlit_discovery_ui.py -q
python -m scripts.validation.check_streamlit_discovery_ui --strict --check-api
```

The validator checks:

- `/runtime` is reachable;
- `service_status.schema_version == runtime_services_v0.1`;
- `overall_status == ready`;
- required service count equals required available count;
- expected service rows are present;
- Qdrant service availability matches `/runtime.qdrant`;
- citation graph service availability matches `/citation-graph/status`;
- Streamlit feature actions include `GET /runtime.service_status` capability
  gating markers.
