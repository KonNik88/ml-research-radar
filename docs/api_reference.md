# API Reference

## Purpose

This document describes the current public API surface of ML Research Radar.

The API currently supports two backend modes:

- `file` backend — retrieval-oriented runtime using local retrieval artifacts
- `db` backend — storage-backed runtime using Postgres for browse/filter and lexical search v1

The two backends intentionally expose the same top-level API shape where possible, but they are **not fully symmetric** in current capabilities.

---

## Backend Modes

### File backend

Current characteristics:

- uses retrieval artifacts from local files
- loads canonical corpus from JSONL
- supports:
  - lexical search
  - dense search
  - hybrid search

### DB backend

Current characteristics:

- uses Postgres as materialized serving layer
- supports:
  - `/documents` browse/filter access
  - `/search` with `mode=lexical` only

Not supported in DB backend v1:

- `mode=dense`
- `mode=hybrid`

These unsupported modes return `400 Bad Request`.

---

## Error Response

All structured API errors use the following shape:

```json
{
  "error_code": "bad_request",
  "message": "human-readable error message",
  "details": null
}