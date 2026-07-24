from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.contracts.document import NormalizedDocument
from radar_core.normalize.reconcile import (
    MAX_REASONABLE_FUTURE_YEAR,
    SOURCE_PRIORITY_ARTIFACTS,
    SOURCE_PRIORITY_BIBLIO,
    SOURCE_PRIORITY_COMMENT,
    SOURCE_PRIORITY_DEFAULT,
    SOURCE_PRIORITY_LICENSE,
    SOURCE_PRIORITY_VENUE,
    build_canonical_id,
    build_reconciliation_groups,
    build_source_links,
    choose_best_abstract,
    choose_best_arxiv_id,
    choose_best_doi,
    choose_best_landing_page_url,
    choose_best_license,
    choose_best_openalex_id,
    choose_best_pdf_url,
    choose_best_primary_category,
    choose_best_publication_date,
    choose_best_publication_type,
    choose_best_published_at,
    choose_best_repo_url,
    choose_best_title,
    choose_best_updated_at,
    choose_best_year,
    choose_canonical_is_open_access,
    choose_canonical_is_preprint,
    choose_canonical_open_access,
    choose_first_nonempty_string,
    choose_max_int,
    choose_preferred_string,
    compute_metadata_completeness_score,
    dedupe_preserve_order,
    merge_external_ids,
    merge_source_ids,
    merge_unique_strings,
    normalize_license_value,
    normalize_venue_fields,
    sort_documents_by_priority,
)
from radar_core.utils.ids import stable_hash
from radar_core.utils.source_observation_identity import (
    build_source_observation_identity_from_mapping,
)
from scripts.validation.check_field_level_canonical_provenance_contract import (
    FIELD_STRATEGIES,
)


REPORT_NAME = "field_level_canonical_provenance_evidence_builder_v01"
SCHEMA_VERSION = "field_level_canonical_provenance_evidence_v0.1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = (
    PROJECT_ROOT
    / "artifacts"
    / "audit"
    / "field_level_canonical_provenance_evidence_v0.1"
)
REQUIRED_AUDIT_FILES = (
    "manifest.json",
    "data_slice/canonical_documents.sample.jsonl",
    "data_slice/source_documents.sample.jsonl",
    "data_slice/canonical_source_links.sample.jsonl",
    "data_slice/unmatched_canonical_source_links.jsonl",
)
RUNTIME_DEFAULT_FIELDS = {"created_at", "updated_record_at"}


class EvidenceBuildError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def ts_slug() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def normalize_path(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, Path):
        return normalize_path(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_value(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        json_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_value(payload), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(json_value(dict(row)), ensure_ascii=False, sort_keys=True)
                + "\n"
            )
            count += 1
    return count


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EvidenceBuildError(f"Expected JSON object: {path}")
    return payload


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            text = raw.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise EvidenceBuildError(
                    f"Expected JSON object in {path}:{line_no}"
                )
            rows.append(payload)
    return rows


def _resolve_audit_root(path: Path) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    path = path.resolve()
    temp: tempfile.TemporaryDirectory[str] | None = None
    if path.is_file() and path.suffix.lower() == ".zip":
        temp = tempfile.TemporaryDirectory(prefix="ml_radar_field_provenance_")
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise EvidenceBuildError(f"Invalid ZIP: {path}")
            archive.extractall(temp.name)
        path = Path(temp.name)
    if not path.is_dir():
        raise FileNotFoundError(path)
    if (path / "manifest.json").is_file():
        root = path
    else:
        children = [child for child in path.iterdir() if child.is_dir()]
        roots = [child for child in children if (child / "manifest.json").is_file()]
        if len(roots) != 1:
            raise EvidenceBuildError(
                f"Could not resolve one audit package root beneath: {path}"
            )
        root = roots[0]
    missing = [name for name in REQUIRED_AUDIT_FILES if not (root / name).is_file()]
    if missing:
        raise EvidenceBuildError(f"Audit package is missing files: {missing}")
    return root, temp


def _clean_source_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(k): v for k, v in row.items() if not str(k).startswith("_audit_")}


def _observation_id_from_row(row: Mapping[str, Any]) -> str:
    return build_source_observation_identity_from_mapping(row).source_observation_id


def load_audit_inputs(audit_path: Path) -> dict[str, Any]:
    root, temp = _resolve_audit_root(audit_path)
    try:
        audit_manifest = load_json(root / "manifest.json")
        canonical_rows = load_jsonl(
            root / "data_slice" / "canonical_documents.sample.jsonl"
        )
        source_rows_raw = load_jsonl(
            root / "data_slice" / "source_documents.sample.jsonl"
        )
        link_rows = load_jsonl(
            root / "data_slice" / "canonical_source_links.sample.jsonl"
        )
        unmatched_rows = load_jsonl(
            root / "data_slice" / "unmatched_canonical_source_links.jsonl"
        )

        if unmatched_rows:
            raise EvidenceBuildError(
                f"Audit package has {len(unmatched_rows)} unmatched canonical source links"
            )

        canonical_models: dict[str, CanonicalDocument] = {}
        canonical_payloads: dict[str, dict[str, Any]] = {}
        for row in canonical_rows:
            model = CanonicalDocument.model_validate(row)
            if model.canonical_id in canonical_models:
                raise EvidenceBuildError(f"Duplicate canonical_id: {model.canonical_id}")
            canonical_models[model.canonical_id] = model
            canonical_payloads[model.canonical_id] = model.model_dump(mode="json")

        source_by_observation_id: dict[str, NormalizedDocument] = {}
        source_raw_by_observation_id: dict[str, dict[str, Any]] = {}
        audit_canonical_ids_by_observation_id: dict[str, set[str]] = {}
        for raw in source_rows_raw:
            clean = _clean_source_row(raw)
            model = NormalizedDocument.model_validate(clean)
            observation_id = _observation_id_from_row(clean)
            previous = source_raw_by_observation_id.get(observation_id)
            if previous is not None and previous != clean:
                raise EvidenceBuildError(
                    f"Conflicting source rows for source_observation_id={observation_id}"
                )
            source_by_observation_id[observation_id] = model
            source_raw_by_observation_id[observation_id] = clean
            audit_canonical_ids_by_observation_id[observation_id] = {
                str(value)
                for value in raw.get("_audit_canonical_ids", [])
                if str(value).strip()
            }

        docs_by_canonical_id: dict[str, list[NormalizedDocument]] = {}
        observation_ids_by_canonical_id: dict[str, list[str]] = {}
        for canonical_id, canonical in canonical_models.items():
            docs: list[NormalizedDocument] = []
            observation_ids: list[str] = []
            for source_link in canonical.sources:
                link_payload = source_link.model_dump(mode="json")
                observation_id = _observation_id_from_row(link_payload)
                source_doc = source_by_observation_id.get(observation_id)
                if source_doc is None:
                    raise EvidenceBuildError(
                        "Contributing source observation not found in audit data slice: "
                        f"canonical_id={canonical_id}, source_observation_id={observation_id}"
                    )
                declared = audit_canonical_ids_by_observation_id.get(observation_id, set())
                if declared and canonical_id not in declared:
                    raise EvidenceBuildError(
                        "Audit source row does not declare the canonical relationship: "
                        f"canonical_id={canonical_id}, source_observation_id={observation_id}"
                    )
                docs.append(source_doc)
                observation_ids.append(observation_id)
            if not docs:
                raise EvidenceBuildError(
                    f"Canonical sample row has no contributing observations: {canonical_id}"
                )
            docs_by_canonical_id[canonical_id] = docs
            observation_ids_by_canonical_id[canonical_id] = observation_ids

        matched_link_count = sum(bool(row.get("matched")) for row in link_rows)
        expected_link_count = sum(len(model.sources) for model in canonical_models.values())
        if matched_link_count != expected_link_count:
            raise EvidenceBuildError(
                "Audit link count does not match canonical provenance rows: "
                f"matched={matched_link_count}, expected={expected_link_count}"
            )

        return {
            "audit_root": normalize_path(root),
            "audit_manifest": audit_manifest,
            "canonical_models": canonical_models,
            "canonical_payloads": canonical_payloads,
            "docs_by_canonical_id": docs_by_canonical_id,
            "observation_ids_by_canonical_id": observation_ids_by_canonical_id,
            "source_raw_by_observation_id": source_raw_by_observation_id,
            "link_rows": link_rows,
        }
    finally:
        if temp is not None:
            temp.cleanup()


def recompute_canonical_document(
    documents: Sequence[NormalizedDocument],
    reference: CanonicalDocument,
) -> CanonicalDocument:
    docs = list(documents)
    groups = build_reconciliation_groups(docs)
    if len(groups) != 1:
        raise EvidenceBuildError(
            f"Contributing observations recompute into {len(groups)} groups for "
            f"canonical_id={reference.canonical_id}"
        )
    reconciliation_key, grouped_docs = next(iter(groups.items()))
    if len(grouped_docs) != len(docs):
        raise EvidenceBuildError("Reconciliation grouping lost contributing observations")

    docs_biblio = sort_documents_by_priority(docs, SOURCE_PRIORITY_BIBLIO)
    publication_type = choose_best_publication_type(docs)
    venue = choose_preferred_string(
        docs, "venue", source_priority=SOURCE_PRIORITY_VENUE, prefer_longer=False
    )
    journal = choose_preferred_string(
        docs, "journal", source_priority=SOURCE_PRIORITY_VENUE, prefer_longer=False
    )
    conference = choose_preferred_string(
        docs, "conference", source_priority=SOURCE_PRIORITY_VENUE, prefer_longer=False
    )
    venue, journal, conference = normalize_venue_fields(
        publication_type, venue, journal, conference
    )
    code_links = merge_unique_strings([doc.code_links for doc in docs])
    dataset_links = merge_unique_strings([doc.dataset_links for doc in docs])
    model_links = merge_unique_strings([doc.model_links for doc in docs])

    return CanonicalDocument(
        canonical_id=build_canonical_id(reconciliation_key),
        doc_ids=dedupe_preserve_order([doc.doc_id for doc in docs if doc.doc_id]),
        doi=choose_best_doi(docs),
        arxiv_id=choose_best_arxiv_id(docs),
        openalex_id=choose_best_openalex_id(docs),
        source_ids=merge_source_ids(docs),
        external_ids=merge_external_ids(docs),
        pmid=choose_first_nonempty_string(docs, "pmid"),
        pmcid=choose_first_nonempty_string(docs, "pmcid"),
        semantic_scholar_id=choose_first_nonempty_string(
            docs, "semantic_scholar_id"
        ),
        dblp_id=choose_first_nonempty_string(docs, "dblp_id"),
        mag_id=choose_first_nonempty_string(docs, "mag_id"),
        title=choose_best_title(docs),
        abstract=choose_best_abstract(docs),
        authors=merge_unique_strings([doc.authors for doc in docs]),
        published_at=choose_best_published_at(docs),
        publication_date=choose_best_publication_date(docs),
        updated_at=choose_best_updated_at(docs),
        year=choose_best_year(docs),
        landing_page_url=choose_best_landing_page_url(docs),
        pdf_url=choose_best_pdf_url(docs),
        repo_url=choose_best_repo_url(docs),
        license=choose_best_license(docs),
        open_access=choose_canonical_open_access(docs),
        primary_category=choose_best_primary_category(docs),
        categories=merge_unique_strings([doc.categories for doc in docs]),
        concepts=merge_unique_strings([doc.concepts for doc in docs]),
        keywords=merge_unique_strings([doc.keywords for doc in docs]),
        tags=merge_unique_strings([doc.tags for doc in docs]),
        comment=choose_preferred_string(
            docs,
            "comment",
            source_priority=SOURCE_PRIORITY_COMMENT,
            prefer_longer=True,
        ),
        journal_ref=choose_preferred_string(
            docs,
            "journal_ref",
            source_priority=SOURCE_PRIORITY_COMMENT,
            prefer_longer=True,
        ),
        venue=venue,
        journal=journal,
        conference=conference,
        publisher=choose_preferred_string(
            docs,
            "publisher",
            source_priority=SOURCE_PRIORITY_BIBLIO,
            prefer_longer=False,
        ),
        publication_type=publication_type,
        language=choose_preferred_string(
            docs,
            "language",
            source_priority=SOURCE_PRIORITY_DEFAULT,
            prefer_longer=False,
        ),
        cited_by_count=choose_max_int(docs, "cited_by_count"),
        references_count=choose_max_int(docs, "references_count"),
        referenced_ids=merge_unique_strings(
            [doc.referenced_ids for doc in docs_biblio]
        ),
        referenced_dois=merge_unique_strings(
            [doc.referenced_dois for doc in docs_biblio]
        ),
        referenced_arxiv_ids=merge_unique_strings(
            [doc.referenced_arxiv_ids for doc in docs_biblio]
        ),
        citation_graph_available=any(doc.citation_graph_available for doc in docs),
        has_code_link=(
            any(bool(doc.has_code_link) for doc in docs)
            or bool(code_links)
            or any(bool(doc.repo_url) for doc in docs)
        ),
        code_links=code_links,
        dataset_links=dataset_links,
        model_links=model_links,
        has_dataset_link=(
            any(bool(doc.has_dataset_link) for doc in docs) or bool(dataset_links)
        ),
        has_model_link=(
            any(bool(doc.has_model_link) for doc in docs) or bool(model_links)
        ),
        sources=build_source_links(docs),
        source_count=len(docs),
        unique_source_count=len({doc.source for doc in docs if doc.source}),
        metadata_completeness_score=compute_metadata_completeness_score(docs),
        is_open_access=choose_canonical_is_open_access(docs),
        is_preprint=choose_canonical_is_preprint(docs, publication_type),
        is_review=any(bool(doc.is_review) for doc in docs),
        is_survey=any(bool(doc.is_survey) for doc in docs),
        is_withdrawn=any(bool(doc.is_withdrawn) for doc in docs),
        reconciliation_key=reconciliation_key,
        created_at=reference.created_at,
        updated_record_at=reference.updated_record_at,
    )


def _source_priority_for_field(field_name: str) -> dict[str, int]:
    if field_name in {"comment", "journal_ref"}:
        return SOURCE_PRIORITY_COMMENT
    if field_name in {"venue", "journal", "conference"}:
        return SOURCE_PRIORITY_VENUE
    if field_name in {"publisher", "publication_type"}:
        return SOURCE_PRIORITY_BIBLIO
    if field_name == "license":
        return SOURCE_PRIORITY_LICENSE
    if field_name == "repo_url":
        return SOURCE_PRIORITY_ARTIFACTS
    return SOURCE_PRIORITY_DEFAULT


def _direct_source_attr(field_name: str) -> str | None:
    return {
        "doc_ids": "doc_id",
        "updated_at": "updated_source_at",
    }.get(field_name, field_name if field_name in NormalizedDocument.model_fields else None)


def _raw_candidate_value(doc: NormalizedDocument, field_name: str) -> Any:
    attr = _direct_source_attr(field_name)
    if attr is None:
        return None
    return getattr(doc, attr, None)


def _candidate_rows(
    docs: Sequence[NormalizedDocument],
    observation_ids: Sequence[str],
    field_name: str,
) -> list[dict[str, Any]]:
    priority = _source_priority_for_field(field_name)
    rows: list[dict[str, Any]] = []
    for position, (doc, observation_id) in enumerate(zip(docs, observation_ids)):
        raw = _raw_candidate_value(doc, field_name)
        normalized = raw
        if field_name == "license":
            normalized = normalize_license_value(raw)
        rows.append(
            {
                "source_observation_id": observation_id,
                "source": doc.source,
                "input_position": position,
                "raw_value": json_value(raw),
                "normalized_value": json_value(normalized),
                "source_priority": priority.get(doc.source or "", 0),
                "eligible": raw is not None and raw != "" and raw != [],
                "selected": False,
            }
        )
    return rows


def _winner_indices(
    docs: Sequence[NormalizedDocument], field_name: str, recomputed_value: Any
) -> list[int]:
    if field_name in {"title", "abstract"}:
        eligible = [
            i
            for i, doc in enumerate(docs)
            if getattr(doc, field_name, None)
        ]
        if not eligible:
            return []
        return [
            sorted(
                eligible,
                key=lambda i: (
                    len(str(getattr(docs[i], field_name) or "")),
                    docs[i].source == "openalex",
                ),
                reverse=True,
            )[0]
        ]
    if field_name == "doi":
        for i, doc in enumerate(docs):
            if doc.doi:
                return [i]
        for i, doc in enumerate(docs):
            if doc.external_ids.get("doi"):
                return [i]
        return []
    if field_name == "arxiv_id":
        for i, doc in enumerate(docs):
            if doc.source == "arxiv" and doc.arxiv_id:
                return [i]
        for i, doc in enumerate(docs):
            if doc.arxiv_id:
                return [i]
        for key in ("arxiv", "ArXiv", "arxiv_id", "arxiv_base"):
            for i, doc in enumerate(docs):
                if doc.external_ids.get(key):
                    return [i]
        return []
    if field_name == "openalex_id":
        for i, doc in enumerate(docs):
            if doc.openalex_id:
                return [i]
        for i, doc in enumerate(docs):
            if doc.external_ids.get("openalex"):
                return [i]
        return []
    if field_name in {
        "pmid",
        "pmcid",
        "semantic_scholar_id",
        "dblp_id",
        "mag_id",
        "landing_page_url",
        "pdf_url",
        "primary_category",
    }:
        attr = field_name
        for i, doc in enumerate(docs):
            value = getattr(doc, attr, None)
            if value is not None and str(value).strip():
                return [i]
        return []
    if field_name == "repo_url":
        eligible = [i for i, doc in enumerate(docs) if doc.repo_url]
        if not eligible:
            return []
        return [
            sorted(
                eligible,
                key=lambda i: (
                    SOURCE_PRIORITY_ARTIFACTS.get(docs[i].source or "", 0),
                    len(str(docs[i].repo_url or "")),
                ),
                reverse=True,
            )[0]
        ]
    if field_name == "license":
        candidates: list[tuple[int, int, str, int]] = []
        for i, doc in enumerate(docs):
            normalized = normalize_license_value(doc.license)
            if not normalized:
                continue
            quality = 0
            if normalized.startswith("cc-") or normalized == "cc0":
                quality = 100
            elif normalized == "publisher-tdm-policy":
                quality = 30
            elif normalized == "publisher-license-page":
                quality = 20
            elif normalized == "publisher-copyright-policy":
                quality = 10
            candidates.append(
                (
                    quality,
                    SOURCE_PRIORITY_LICENSE.get(doc.source or "", 0),
                    normalized,
                    i,
                )
            )
        return [sorted(candidates, reverse=True)[0][3]] if candidates else []
    if field_name == "publication_type":
        eligible_docs = [
            i
            for i, doc in enumerate(docs)
            if doc.publication_type and not bool(doc.is_preprint)
        ]
        if not eligible_docs:
            eligible_docs = [i for i, doc in enumerate(docs) if doc.publication_type]
        if not eligible_docs:
            return []
        return [
            sorted(
                eligible_docs,
                key=lambda i: (
                    SOURCE_PRIORITY_BIBLIO.get(docs[i].source or "", 0),
                    0,
                    str(docs[i].publication_type).strip(),
                ),
                reverse=True,
            )[0]
        ]
    if field_name in {
        "comment",
        "journal_ref",
        "venue",
        "journal",
        "conference",
        "publisher",
        "language",
    }:
        priority = _source_priority_for_field(field_name)
        prefer_longer = field_name in {"comment", "journal_ref"}

        def preferred_index(source_field: str) -> list[int]:
            candidates: list[tuple[int, int, str, int]] = []
            for i, doc in enumerate(docs):
                raw = getattr(doc, source_field, None)
                if raw is None or not str(raw).strip():
                    continue
                value = str(raw).strip()
                candidates.append(
                    (
                        priority.get(doc.source or "", 0),
                        len(value) if prefer_longer else 0,
                        value,
                        i,
                    )
                )
            return [sorted(candidates, reverse=True)[0][3]] if candidates else []

        direct = preferred_index(field_name)
        if direct:
            return direct
        if field_name == "conference" and recomputed_value is not None:
            return preferred_index("venue")
        return []
    if field_name in {"published_at", "publication_date", "updated_at", "year"}:
        attr = "updated_source_at" if field_name == "updated_at" else field_name
        values: list[tuple[int, Any]] = []
        for i, doc in enumerate(docs):
            value = getattr(doc, attr, None)
            if field_name == "year" and value is not None:
                if not (1900 <= value <= MAX_REASONABLE_FUTURE_YEAR):
                    continue
            if value is not None:
                values.append((i, json_value(value)))
        target = json_value(recomputed_value)
        return [i for i, value in values if value == target]
    if field_name in {"cited_by_count", "references_count"}:
        return [
            i
            for i, doc in enumerate(docs)
            if getattr(doc, field_name, None) == recomputed_value
            and recomputed_value is not None
        ]
    return []


def _union_source_lists(
    docs: Sequence[NormalizedDocument], field_name: str
) -> tuple[list[list[Any]], Sequence[NormalizedDocument]]:
    ordered_docs: Sequence[NormalizedDocument] = docs
    if field_name in {"referenced_ids", "referenced_dois", "referenced_arxiv_ids"}:
        ordered_docs = sort_documents_by_priority(list(docs), SOURCE_PRIORITY_BIBLIO)
    if field_name == "doc_ids":
        return [[doc.doc_id] for doc in ordered_docs], ordered_docs
    return [list(getattr(doc, field_name, []) or []) for doc in ordered_docs], ordered_docs


def _union_elements(
    docs: Sequence[NormalizedDocument],
    observation_id_by_object: Mapping[int, str],
    field_name: str,
) -> list[dict[str, Any]]:
    groups, ordered_docs = _union_source_lists(docs, field_name)
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for doc, values in zip(ordered_docs, groups):
        observation_id = observation_id_by_object[id(doc)]
        for value in values:
            text = str(value).strip()
            if not text:
                continue
            key = text.lower()
            if key not in by_key:
                by_key[key] = {
                    "value": text,
                    "normalized_key": key,
                    "first_source_observation_id": observation_id,
                    "contributing_source_observation_ids": [observation_id],
                    "occurrence_count": 1,
                }
                order.append(key)
            else:
                item = by_key[key]
                item["occurrence_count"] += 1
                if observation_id not in item["contributing_source_observation_ids"]:
                    item["contributing_source_observation_ids"].append(observation_id)
    return [by_key[key] for key in order]


def _map_elements(
    docs: Sequence[NormalizedDocument],
    observation_ids: Sequence[str],
    field_name: str,
) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for doc, observation_id in zip(docs, observation_ids):
        mapping = getattr(doc, field_name, {}) or {}
        for key, value in mapping.items():
            if key in result or not value:
                continue
            result[str(key)] = {
                "key": str(key),
                "value": str(value),
                "first_source_observation_id": observation_id,
            }
    return [result[key] for key in sorted(result)]


def build_field_record(
    *,
    canonical: CanonicalDocument,
    recomputed: CanonicalDocument,
    docs: Sequence[NormalizedDocument],
    observation_ids: Sequence[str],
    field_name: str,
) -> dict[str, Any]:
    strategy = FIELD_STRATEGIES[field_name]
    canonical_payload = canonical.model_dump(mode="json")
    recomputed_payload = recomputed.model_dump(mode="json")
    canonical_value = canonical_payload[field_name]
    recomputed_value = recomputed_payload[field_name]
    candidates = _candidate_rows(docs, observation_ids, field_name)
    selected_ids: list[str] = []
    contributing_ids: list[str] = []
    elements: list[dict[str, Any]] = []
    transformations: list[dict[str, Any]] = []
    caveats: list[str] = []
    selection_reason = strategy

    observation_id_by_object = {
        id(doc): observation_id for doc, observation_id in zip(docs, observation_ids)
    }

    if strategy in {
        "winner",
        "winner_with_normalization",
        "winner_with_quality_rank",
        "ordered_first",
        "aggregate_min",
        "aggregate_max",
    }:
        winner_indices = _winner_indices(docs, field_name, recomputed_value)
        selected_ids = [observation_ids[index] for index in winner_indices]
        contributing_ids = list(selected_ids)
        for index in winner_indices:
            candidates[index]["selected"] = True
        if field_name in {"venue", "journal", "conference"}:
            transformations.append(
                {
                    "name": "normalize_venue_fields",
                    "publication_type": recomputed_payload["publication_type"],
                    "output_value": recomputed_value,
                }
            )
        if field_name == "publication_type":
            transformations.append(
                {
                    "name": "non_preprint_semantic_override_then_source_priority",
                    "output_value": recomputed_value,
                }
            )
        if field_name == "license":
            transformations.append(
                {"name": "normalize_license_value", "output_value": recomputed_value}
            )
        if field_name in {"published_at", "publication_date", "year"}:
            selection_reason = "minimum eligible value; equal minima are co-winners"
        elif field_name in {"updated_at", "cited_by_count", "references_count"}:
            selection_reason = "maximum eligible value; equal maxima are co-winners"
    elif strategy == "ordered_union":
        elements = _union_elements(
            docs, observation_id_by_object, field_name
        )
        contributing_ids = dedupe_preserve_order(
            [
                observation_id
                for element in elements
                for observation_id in element["contributing_source_observation_ids"]
            ]
        )
        selected_ids = dedupe_preserve_order(
            [element["first_source_observation_id"] for element in elements]
        )
        selection_reason = "ordered union with case-insensitive deduplication"
    elif strategy == "merged_identifier_map":
        elements = _map_elements(docs, observation_ids, field_name)
        selected_ids = dedupe_preserve_order(
            [item["first_source_observation_id"] for item in elements]
        )
        contributing_ids = list(selected_ids)
        selection_reason = "first non-empty value per identifier key"
    elif strategy == "boolean_evidence":
        def has_boolean_evidence(doc: NormalizedDocument) -> bool:
            if field_name == "is_open_access":
                return doc.source != "arxiv" and (
                    doc.is_open_access is not None or doc.open_access is not None
                )
            if field_name == "is_preprint":
                return doc.is_preprint is not None or bool(doc.publication_type)
            if field_name in {
                "citation_graph_available",
                "is_review",
                "is_survey",
                "is_withdrawn",
            }:
                return True
            return getattr(doc, field_name, None) is not None

        contributing_ids = [
            observation_id
            for doc, observation_id in zip(docs, observation_ids)
            if has_boolean_evidence(doc)
        ]
        selected_ids = list(contributing_ids)
        selection_reason = "boolean evidence and field-specific override semantics"
        if field_name == "is_open_access":
            caveats.append("arxiv-only openness is not bibliographic OA confirmation")
        if field_name == "is_preprint":
            caveats.append("explicit non-preprint publication evidence overrides preprint flags")
    elif strategy == "derived_flag":
        component_fields = {
            "has_code_link": ["has_code_link", "code_links", "repo_url"],
            "has_dataset_link": ["has_dataset_link", "dataset_links"],
            "has_model_link": ["has_model_link", "model_links"],
        }[field_name]
        contributing_ids = [
            observation_id
            for doc, observation_id in zip(docs, observation_ids)
            if any(bool(getattr(doc, name, None)) for name in component_fields)
        ]
        selected_ids = list(contributing_ids)
        transformations.append(
            {"name": "boolean_or", "components": component_fields, "output_value": recomputed_value}
        )
        selection_reason = "OR over explicit flags and merged link presence"
    elif strategy == "derived_score":
        contributing_ids = list(observation_ids)
        selected_ids = list(observation_ids)
        transformations.append(
            {
                "name": "compute_metadata_completeness_score",
                "component_count": 12,
                "output_value": recomputed_value,
            }
        )
        selection_reason = "recomputed 12-component merged-record heuristic"
    elif strategy == "row_level_provenance":
        contributing_ids = list(observation_ids)
        selected_ids = list(observation_ids)
        selection_reason = "derived from all contributing provenance rows"
    elif strategy == "identity_derived":
        contributing_ids = list(observation_ids)
        selected_ids = list(observation_ids)
        transformations.append(
            {
                "name": "reconciliation_identity",
                "reconciliation_key": recomputed_payload["reconciliation_key"],
                "hash_length": 32,
            }
        )
        selection_reason = "derived from conservative reconciliation grouping"
    elif strategy == "runtime_default":
        candidates = []
        caveats.append("value is created by the CanonicalDocument runtime default")
        selection_reason = "runtime model default; not source-reconstructable"

    comparison_status = (
        "not_applicable"
        if field_name in RUNTIME_DEFAULT_FIELDS
        else ("match" if canonical_value == recomputed_value else "mismatch")
    )
    reconstructability = (
        "not_source_reconstructable"
        if field_name in RUNTIME_DEFAULT_FIELDS
        else "exact"
    )

    record_id = stable_hash(
        json.dumps(
            [SCHEMA_VERSION, canonical.canonical_id, field_name],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        length=32,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": record_id,
        "canonical_id": canonical.canonical_id,
        "field_name": field_name,
        "strategy_kind": strategy,
        "canonical_value": canonical_value,
        "recomputed_value": recomputed_value,
        "comparison_status": comparison_status,
        "reconstructability": reconstructability,
        "candidate_count": sum(1 for item in candidates if item["eligible"]),
        "selected_source_observation_ids": selected_ids,
        "contributing_source_observation_ids": contributing_ids,
        "candidates": candidates,
        "elements": elements,
        "transformations": transformations,
        "selection_reason": selection_reason,
        "caveats": caveats,
    }


def build_evidence(
    *,
    canonical_models: Mapping[str, CanonicalDocument],
    docs_by_canonical_id: Mapping[str, Sequence[NormalizedDocument]],
    observation_ids_by_canonical_id: Mapping[str, Sequence[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    paper_summaries: list[dict[str, Any]] = []
    strategy_counts: dict[str, int] = defaultdict(int)
    mismatch_fields: list[dict[str, Any]] = []

    for canonical_id in sorted(canonical_models):
        canonical = canonical_models[canonical_id]
        docs = list(docs_by_canonical_id[canonical_id])
        observation_ids = list(observation_ids_by_canonical_id[canonical_id])
        recomputed = recompute_canonical_document(docs, canonical)
        paper_records: list[dict[str, Any]] = []
        for field_name in sorted(FIELD_STRATEGIES):
            record = build_field_record(
                canonical=canonical,
                recomputed=recomputed,
                docs=docs,
                observation_ids=observation_ids,
                field_name=field_name,
            )
            paper_records.append(record)
            strategy_counts[record["strategy_kind"]] += 1
            if record["comparison_status"] == "mismatch":
                mismatch_fields.append(
                    {
                        "canonical_id": canonical_id,
                        "field_name": field_name,
                        "canonical_value": record["canonical_value"],
                        "recomputed_value": record["recomputed_value"],
                    }
                )
        records.extend(paper_records)
        paper_summaries.append(
            {
                "canonical_id": canonical_id,
                "title": canonical.title,
                "contributing_observation_count": len(observation_ids),
                "contributing_source_observation_ids": observation_ids,
                "field_record_count": len(paper_records),
                "match_count": sum(
                    record["comparison_status"] == "match" for record in paper_records
                ),
                "not_applicable_count": sum(
                    record["comparison_status"] == "not_applicable"
                    for record in paper_records
                ),
                "mismatch_count": sum(
                    record["comparison_status"] == "mismatch"
                    for record in paper_records
                ),
            }
        )

    records.sort(key=lambda row: (row["canonical_id"], row["field_name"]))
    paper_summaries.sort(key=lambda row: row["canonical_id"])
    quality = {
        "canonical_paper_count": len(canonical_models),
        "canonical_field_count": len(FIELD_STRATEGIES),
        "field_evidence_record_count": len(records),
        "runtime_default_record_count": sum(
            row["field_name"] in RUNTIME_DEFAULT_FIELDS for row in records
        ),
        "comparison_match_count": sum(
            row["comparison_status"] == "match" for row in records
        ),
        "comparison_not_applicable_count": sum(
            row["comparison_status"] == "not_applicable" for row in records
        ),
        "comparison_mismatch_count": len(mismatch_fields),
        "strategy_counts": dict(sorted(strategy_counts.items())),
        "mismatch_samples": mismatch_fields[:20],
    }
    return records, paper_summaries, quality


def build_readme(manifest: Mapping[str, Any]) -> str:
    counts = manifest["counts"]
    return f"""# Field-Level Canonical Provenance Evidence v0.1\n\nThis directory contains bounded, derived, read-only evidence explaining current canonical field selection.\n\n```text\ncanonical_truth = false\nmay_be_used_as_reconcile_input = false\nreconciliation_behavior_changed = false\npostgres_mutated = false\nprovider_api_called = false\npublication_ready = false\n```\n\n## Counts\n\n```text\ncanonical_papers = {counts['canonical_paper_count']}\ncanonical_fields = {counts['canonical_field_count']}\nfield_evidence_records = {counts['field_evidence_record_count']}\ncontributing_source_observations = {counts['contributing_source_observation_count']}\ncomparison_mismatches = {counts['comparison_mismatch_count']}\n```\n\n## Files\n\n- `field_evidence.jsonl`\n- `paper_summary.jsonl`\n- `data_quality_summary.json`\n- `manifest.json`\n- `README.md`\n- `checksums.txt`\n\nThe evidence is explanatory and bounded to the supplied reconciliation audit package. It does not replace canonical truth.\n"""


def build_package(
    *,
    audit_path: Path,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    run_ts: str | None = None,
    strict: bool = False,
    create_zip: bool = True,
) -> dict[str, Any]:
    run_ts = run_ts or ts_slug()
    inputs = load_audit_inputs(audit_path)
    records, paper_summaries, quality = build_evidence(
        canonical_models=inputs["canonical_models"],
        docs_by_canonical_id=inputs["docs_by_canonical_id"],
        observation_ids_by_canonical_id=inputs["observation_ids_by_canonical_id"],
    )

    run_name = f"field_level_canonical_provenance_evidence_v0.1_{run_ts}"
    run_dir = output_root / run_name
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)

    field_path = run_dir / "field_evidence.jsonl"
    paper_path = run_dir / "paper_summary.jsonl"
    quality_path = run_dir / "data_quality_summary.json"
    manifest_path = run_dir / "manifest.json"
    readme_path = run_dir / "README.md"
    checksum_path = run_dir / "checksums.txt"

    write_jsonl(field_path, records)
    write_jsonl(paper_path, paper_summaries)
    write_json(quality_path, quality)

    unique_observation_ids = {
        observation_id
        for values in inputs["observation_ids_by_canonical_id"].values()
        for observation_id in values
    }
    counts = {
        **quality,
        "contributing_source_observation_count": len(unique_observation_ids),
        "canonical_source_link_count": len(inputs["link_rows"]),
        "unmatched_source_link_count": 0,
    }
    manifest = {
        "report_name": REPORT_NAME,
        "schema_version": SCHEMA_VERSION,
        "package_name": run_name,
        "generated_at_utc": utc_now_iso(),
        "status": "bounded_derived_explanatory_evidence",
        "canonical_truth": False,
        "may_be_used_as_reconcile_input": False,
        "manual_review_required": True,
        "publication_ready": False,
        "safety": {
            "reconciliation_behavior_changed": False,
            "canonical_document_schema_changed": False,
            "postgres_mutated": False,
            "retrieval_mutated": False,
            "qdrant_mutated": False,
            "graph_mutated": False,
            "api_mutated": False,
            "ui_mutated": False,
            "provider_api_called": False,
        },
        "inputs": {
            "audit_path": normalize_path(audit_path),
            "audit_root": inputs["audit_root"],
            "audit_package_name": inputs["audit_manifest"].get("package_name"),
        },
        "counts": counts,
        "content_files": {},
        "verdict": {
            "ok": quality["comparison_mismatch_count"] == 0,
            "required_failed_count": quality["comparison_mismatch_count"],
            "field_values_match_current_canonical_sample": (
                quality["comparison_mismatch_count"] == 0
            ),
            "next_slice": "field_level_canonical_provenance_evidence_validation_v0.1",
        },
    }
    write_text = build_readme(manifest)
    readme_path.write_text(write_text, encoding="utf-8", newline="\n")

    for path in (field_path, paper_path, quality_path, readme_path):
        manifest["content_files"][path.name] = {
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    write_json(manifest_path, manifest)

    checksum_lines = []
    for path in (field_path, paper_path, quality_path, manifest_path, readme_path):
        checksum_lines.append(f"{sha256_file(path)}  {path.name}")
    checksum_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8", newline="\n")

    latest = {
        "schema_version": SCHEMA_VERSION,
        "run_dir": normalize_path(run_dir.resolve()),
        "manifest_path": normalize_path(manifest_path.resolve()),
        "field_evidence_path": normalize_path(field_path.resolve()),
        "generated_at_utc": manifest["generated_at_utc"],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "latest.json", latest)

    zip_path: Path | None = None
    if create_zip:
        zip_path = output_root / f"{run_name}.zip"
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(run_dir.iterdir()):
                archive.write(path, arcname=f"{run_name}/{path.name}")
        with zipfile.ZipFile(zip_path) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise EvidenceBuildError(f"ZIP integrity failure: {bad}")

    if strict and not manifest["verdict"]["ok"]:
        raise EvidenceBuildError(
            f"Field evidence contains {quality['comparison_mismatch_count']} mismatches"
        )

    return {
        "ok": manifest["verdict"]["ok"],
        "run_dir": normalize_path(run_dir),
        "manifest_path": normalize_path(manifest_path),
        "zip_path": normalize_path(zip_path) if zip_path else None,
        "counts": counts,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build bounded field-level canonical provenance evidence."
    )
    parser.add_argument(
        "--audit-path",
        "--audit-dir",
        dest="audit_path",
        type=Path,
        required=True,
        help="Reconciliation audit staging directory or ZIP package.",
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-ts", default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-zip", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_package(
        audit_path=args.audit_path,
        output_root=args.output_root,
        run_ts=args.run_ts,
        strict=args.strict,
        create_zip=not args.no_zip,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
