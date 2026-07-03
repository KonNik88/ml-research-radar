from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

CONFIG_PATH = Path("configs/citation_reference_graph.yaml")
DEFAULT_OUTPUT_DIR = Path("data/graphs/citation_reference_graph/v0.1")
GRAPH_NAME = "citation_reference_graph"
GRAPH_VERSION = "v0.1"
SCHEMA_VERSION = "citation_reference_graph_schema_v1"
MANIFEST_SCHEMA_VERSION = "citation_reference_graph_manifest_v1"
DATA_QUALITY_SCHEMA_VERSION = "citation_reference_graph_data_quality_summary_v1"

DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
DOI_VALUE_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
ARXIV_PREFIX_RE = re.compile(r"^(?:https?://arxiv\.org/(?:abs|pdf)/|arxiv:\s*)", re.IGNORECASE)
ARXIV_VERSION_RE = re.compile(r"v\d+$", re.IGNORECASE)
OPENALEX_RE = re.compile(r"(?:https?://openalex\.org/)?(W\d+)$", re.IGNORECASE)
SEMANTIC_SCHOLAR_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
ARXIV_ID_RE = re.compile(r"^(?:\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?$", re.IGNORECASE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be an object: {path}")
    return data


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row must be an object at {path}:{line_no}")
            docs.append(row)
    return docs


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return [value]


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_present(doc: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in doc and doc.get(key) not in (None, ""):
            return doc.get(key)
    return None


def _paper_node_id(canonical_id: str) -> str:
    return f"paper:{canonical_id}"


def _source_family_node_id(source_family: str) -> str:
    return f"source_family:{source_family}"


def _external_reference_node_id(reference_key: str) -> str:
    return f"external_reference:{_sha1_text(reference_key)[:16]}"


def _edge_id(edge_type: str, source_node_id: str, target_node_id: str, extra_key: str = "") -> str:
    raw = "|".join([edge_type, source_node_id, target_node_id, extra_key])
    return f"edge:{edge_type}:{_sha1_text(raw)[:20]}"


def _normalize_doi(value: Any) -> str | None:
    text = _string_or_none(value)
    if not text:
        return None
    text = DOI_PREFIX_RE.sub("", text.strip())
    text = text.strip().strip(" .;,").lower()
    if not text or not DOI_VALUE_RE.match(text):
        return None
    return text


def _normalize_arxiv_id(value: Any) -> str | None:
    text = _string_or_none(value)
    if not text:
        return None
    text = ARXIV_PREFIX_RE.sub("", text.strip())
    text = text.replace(".pdf", "")
    text = text.strip().strip(" .;,")
    text = ARXIV_VERSION_RE.sub("", text)
    if not text:
        return None
    return text.lower()


def _normalize_openalex_id(value: Any) -> str | None:
    text = _string_or_none(value)
    if not text:
        return None
    match = OPENALEX_RE.search(text.strip())
    return match.group(1).upper() if match else None


def _normalize_semantic_scholar_id(value: Any) -> str | None:
    text = _string_or_none(value)
    if not text:
        return None
    text = text.strip().lower()
    return text if SEMANTIC_SCHOLAR_RE.match(text) else None


def _normalize_raw_external_id(value: Any) -> str | None:
    text = _string_or_none(value)
    if not text:
        return None
    return text.strip()


def _infer_reference_type(value: Any, explicit_type: Any = None) -> str:
    explicit = _string_or_none(explicit_type)
    if explicit:
        normalized = explicit.lower().replace("-", "_").replace(" ", "_")
        if normalized in {"doi", "arxiv_id", "openalex_id", "semantic_scholar_id", "raw_external_id"}:
            return normalized
        if normalized in {"arxiv", "arxivid"}:
            return "arxiv_id"
        if normalized in {"openalex", "openalex_work"}:
            return "openalex_id"
        if normalized in {"semanticscholar", "semantic_scholar", "s2", "corpusid"}:
            return "semantic_scholar_id"
    text = _string_or_none(value) or ""
    if _normalize_openalex_id(text):
        return "openalex_id"
    if _normalize_semantic_scholar_id(text):
        return "semantic_scholar_id"
    if _normalize_arxiv_id(text) and ARXIV_ID_RE.match(text.strip().replace("arXiv:", "")):
        return "arxiv_id"
    if _normalize_doi(text):
        return "doi"
    return "raw_external_id"


def _normalize_reference_value(value: Any, reference_type: str) -> str | None:
    if reference_type == "doi":
        return _normalize_doi(value)
    if reference_type == "arxiv_id":
        return _normalize_arxiv_id(value)
    if reference_type == "openalex_id":
        return _normalize_openalex_id(value)
    if reference_type == "semantic_scholar_id":
        return _normalize_semantic_scholar_id(value)
    return _normalize_raw_external_id(value)


def _extract_external_ids(doc: dict[str, Any]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = defaultdict(list)

    doi = _normalize_doi(_first_present(doc, ["doi", "external_doi"]))
    if doi:
        values["doi"].append(doi)

    arxiv_id = _normalize_arxiv_id(_first_present(doc, ["arxiv_id", "external_arxiv_id", "arxiv"]))
    if arxiv_id:
        values["arxiv_id"].append(arxiv_id)

    for key in ["openalex_id", "openalex_work_id"]:
        openalex_id = _normalize_openalex_id(doc.get(key))
        if openalex_id:
            values["openalex_id"].append(openalex_id)

    for key in ["semantic_scholar_id", "s2_id", "corpus_id", "corpusid"]:
        s2_id = _normalize_semantic_scholar_id(doc.get(key))
        if s2_id:
            values["semantic_scholar_id"].append(s2_id)

    external_ids = doc.get("external_ids")
    if isinstance(external_ids, dict):
        for key, raw in external_ids.items():
            key_norm = str(key).lower().replace("-", "_").replace(" ", "_")
            for item in _as_list(raw):
                ref_type = _infer_reference_type(item, key_norm)
                normalized = _normalize_reference_value(item, ref_type)
                if normalized:
                    values[ref_type].append(normalized)

    return {key: sorted(set(items)) for key, items in values.items()}


def _build_unique_index(docs: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    candidates: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    canonical_ids = {str(doc.get("canonical_id")) for doc in docs if doc.get("canonical_id")}

    for canonical_id in canonical_ids:
        candidates["canonical_id"][canonical_id].add(canonical_id)

    for doc in docs:
        canonical_id = _string_or_none(doc.get("canonical_id"))
        if not canonical_id:
            continue
        for ref_type, values in _extract_external_ids(doc).items():
            for value in values:
                candidates[ref_type][value].add(canonical_id)

    unique: dict[str, dict[str, str]] = defaultdict(dict)
    for ref_type, mapping in candidates.items():
        for value, ids in mapping.items():
            if len(ids) == 1:
                unique[ref_type][value] = next(iter(ids))
    return {key: dict(value) for key, value in unique.items()}


def _extract_year(doc: dict[str, Any]) -> int | None:
    raw = _first_present(doc, ["year", "publication_year", "published_year", "original_publication_year"])
    if raw is None:
        return None
    try:
        year = int(raw)
    except Exception:
        return None
    return year if 1900 <= year <= 2100 else None


def _source_families(doc: dict[str, Any]) -> list[str]:
    raw_sources = doc.get("sources") or doc.get("source_families") or []
    families: set[str] = set()
    for item in _as_list(raw_sources):
        raw: Any = item
        if isinstance(item, dict):
            raw = item.get("source_family") or item.get("source") or item.get("name") or item.get("provider")
        text = _string_or_none(raw)
        if not text:
            continue
        normalized = text.strip().lower().replace(" ", "_")
        families.add(normalized)
    return sorted(families)


def _reference_candidates(doc: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []

    for raw in _as_list(doc.get("referenced_dois")):
        normalized = _normalize_doi(raw)
        if normalized:
            refs.append({"reference_field": "referenced_dois", "reference_type": "doi", "normalized_value": normalized})

    for raw in _as_list(doc.get("referenced_arxiv_ids")):
        normalized = _normalize_arxiv_id(raw)
        if normalized:
            refs.append({"reference_field": "referenced_arxiv_ids", "reference_type": "arxiv_id", "normalized_value": normalized})

    for raw in _as_list(doc.get("referenced_ids")):
        explicit_type: Any = None
        value: Any = raw
        if isinstance(raw, dict):
            explicit_type = raw.get("type") or raw.get("id_type") or raw.get("reference_type")
            value = raw.get("value") or raw.get("id") or raw.get("identifier") or raw.get("doi") or raw.get("arxiv_id")
        reference_type = _infer_reference_type(value, explicit_type)
        normalized = _normalize_reference_value(value, reference_type)
        if normalized:
            refs.append({"reference_field": "referenced_ids", "reference_type": reference_type, "normalized_value": normalized})

    dedup: dict[tuple[str, str, str], dict[str, str]] = {}
    for ref in refs:
        key = (ref["reference_field"], ref["reference_type"], ref["normalized_value"])
        dedup[key] = ref
    return list(dedup.values())


def _positive_int(value: Any) -> bool:
    try:
        return int(value) > 0
    except Exception:
        return False


def _reference_bearing(doc: dict[str, Any], refs: list[dict[str, str]]) -> bool:
    return bool(refs) or _positive_int(doc.get("references_count"))


def _make_paper_node(doc: dict[str, Any], canonical_id: str) -> dict[str, Any]:
    return {
        "node_id": _paper_node_id(canonical_id),
        "node_type": "paper",
        "canonical_id": canonical_id,
        "title": _string_or_none(doc.get("title")),
        "year": _extract_year(doc),
        "doi": _normalize_doi(_first_present(doc, ["doi", "external_doi"])),
        "arxiv_id": _normalize_arxiv_id(_first_present(doc, ["arxiv_id", "external_arxiv_id", "arxiv"])),
        "source_layer": "canonical_documents",
    }


def _make_external_reference_node(reference_type: str, normalized_value: str, resolved_to: str | None = None) -> dict[str, Any]:
    reference_key = f"{reference_type}:{normalized_value}"
    return {
        "node_id": _external_reference_node_id(reference_key),
        "node_type": "external_reference",
        "reference_key": reference_key,
        "reference_type": reference_type,
        "normalized_value": normalized_value,
        "resolution_status": "resolved_to_canonical" if resolved_to else "unresolved_external",
        "resolved_canonical_id": resolved_to,
        "source_layer": "canonical_reference_fields",
    }


def _make_source_family_node(source_family: str) -> dict[str, Any]:
    return {
        "node_id": _source_family_node_id(source_family),
        "node_type": "source_family",
        "source_family": source_family,
        "source_layer": "source_provenance",
    }


def build_graph(
    *,
    config_path: Path = CONFIG_PATH,
    canonical_path: Path | None = None,
    output_dir: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    config = _read_yaml(config_path)
    source_checkpoint = config.get("source_checkpoint") if isinstance(config.get("source_checkpoint"), dict) else {}
    outputs_cfg = config.get("outputs") if isinstance(config.get("outputs"), dict) else {}

    canonical_path = canonical_path or Path(str(source_checkpoint.get("canonical_corpus_path", "data/analytics/reconciled/canonical_documents.jsonl")))
    output_dir = output_dir or Path(str(outputs_cfg.get("expected_future_output_dir", DEFAULT_OUTPUT_DIR)))

    docs = _read_jsonl(canonical_path)
    if limit is not None:
        docs = docs[:limit]

    unique_index = _build_unique_index(docs)

    nodes_by_id: dict[str, dict[str, Any]] = {}
    edges_by_id: dict[str, dict[str, Any]] = {}
    stats = Counter()
    ref_type_counts = Counter()
    source_family_counts = Counter()

    docs_by_canonical_id: dict[str, dict[str, Any]] = {}
    for doc in docs:
        canonical_id = _string_or_none(doc.get("canonical_id"))
        if not canonical_id:
            stats["skipped_docs_missing_canonical_id"] += 1
            continue
        docs_by_canonical_id[canonical_id] = doc
        node = _make_paper_node(doc, canonical_id)
        nodes_by_id[node["node_id"]] = node

    duplicate_edges_skipped = 0
    self_edges_skipped = 0

    for canonical_id, doc in docs_by_canonical_id.items():
        source_node_id = _paper_node_id(canonical_id)
        refs = _reference_candidates(doc)
        stats["reference_candidates_count"] += len(refs)

        for ref in refs:
            ref_type = ref["reference_type"]
            normalized_value = ref["normalized_value"]
            reference_field = ref["reference_field"]
            ref_type_counts[ref_type] += 1

            target_canonical_id = unique_index.get(ref_type, {}).get(normalized_value)
            if ref_type == "raw_external_id":
                target_canonical_id = unique_index.get("canonical_id", {}).get(normalized_value, target_canonical_id)

            if target_canonical_id and target_canonical_id in docs_by_canonical_id:
                if target_canonical_id == canonical_id:
                    self_edges_skipped += 1
                    continue
                target_node_id = _paper_node_id(target_canonical_id)
                edge = {
                    "edge_id": _edge_id("paper_references_paper", source_node_id, target_node_id, f"{ref_type}:{normalized_value}"),
                    "edge_type": "paper_references_paper",
                    "source_node_id": source_node_id,
                    "target_node_id": target_node_id,
                    "source_canonical_id": canonical_id,
                    "target_canonical_id": target_canonical_id,
                    "reference_type": ref_type,
                    "reference_value": normalized_value,
                    "reference_field": reference_field,
                    "resolution_status": "resolved_to_canonical",
                    "provenance_kind": "canonical_reference",
                    "source_layer": "canonical_reference_fields",
                    "confidence": 1.0,
                }
                if edge["edge_id"] in edges_by_id:
                    duplicate_edges_skipped += 1
                edges_by_id[edge["edge_id"]] = edge
                stats["resolved_reference_edges_count"] += 1
            else:
                reference_key = f"{ref_type}:{normalized_value}"
                external_node = _make_external_reference_node(ref_type, normalized_value)
                nodes_by_id[external_node["node_id"]] = external_node
                target_node_id = external_node["node_id"]
                edge = {
                    "edge_id": _edge_id("paper_references_external", source_node_id, target_node_id, reference_key),
                    "edge_type": "paper_references_external",
                    "source_node_id": source_node_id,
                    "target_node_id": target_node_id,
                    "source_canonical_id": canonical_id,
                    "target_reference_key": reference_key,
                    "reference_type": ref_type,
                    "reference_value": normalized_value,
                    "reference_field": reference_field,
                    "resolution_status": "unresolved_external",
                    "provenance_kind": "external_identifier_reference",
                    "source_layer": "canonical_reference_fields",
                    "confidence": 0.8,
                }
                if edge["edge_id"] in edges_by_id:
                    duplicate_edges_skipped += 1
                edges_by_id[edge["edge_id"]] = edge
                stats["unresolved_reference_edges_count"] += 1

        if _reference_bearing(doc, refs):
            for source_family in _source_families(doc):
                family_node = _make_source_family_node(source_family)
                nodes_by_id[family_node["node_id"]] = family_node
                source_family_counts[source_family] += 1
                target_node_id = family_node["node_id"]
                edge = {
                    "edge_id": _edge_id("paper_has_reference_source_family", source_node_id, target_node_id),
                    "edge_type": "paper_has_reference_source_family",
                    "source_node_id": source_node_id,
                    "target_node_id": target_node_id,
                    "source_canonical_id": canonical_id,
                    "source_family": source_family,
                    "provenance_kind": "source_family_reference",
                    "source_layer": "source_provenance",
                    "confidence": 1.0,
                }
                if edge["edge_id"] in edges_by_id:
                    duplicate_edges_skipped += 1
                edges_by_id[edge["edge_id"]] = edge

    stats["duplicate_edges_skipped"] = duplicate_edges_skipped
    stats["self_reference_edges_skipped"] = self_edges_skipped

    node_type_counts = Counter(str(node.get("node_type")) for node in nodes_by_id.values())
    edge_type_counts = Counter(str(edge.get("edge_type")) for edge in edges_by_id.values())

    nodes = sorted(nodes_by_id.values(), key=lambda item: item["node_id"])
    edges = sorted(edges_by_id.values(), key=lambda item: item["edge_id"])

    counts = {
        "nodes_count": len(nodes),
        "edges_count": len(edges),
        "node_type_counts": dict(sorted(node_type_counts.items())),
        "edge_type_counts": dict(sorted(edge_type_counts.items())),
        "paper_nodes_count": node_type_counts.get("paper", 0),
        "external_reference_nodes_count": node_type_counts.get("external_reference", 0),
        "source_family_nodes_count": node_type_counts.get("source_family", 0),
        "paper_references_paper_edges_count": edge_type_counts.get("paper_references_paper", 0),
        "paper_references_external_edges_count": edge_type_counts.get("paper_references_external", 0),
        "paper_has_reference_source_family_edges_count": edge_type_counts.get("paper_has_reference_source_family", 0),
    }

    expected_doc_count = source_checkpoint.get("expected_canonical_doc_count")
    expected_doc_count_int = int(expected_doc_count) if expected_doc_count is not None else None

    quality = {
        "ok": True,
        "expected_canonical_doc_count": expected_doc_count_int,
        "canonical_docs_read_count": len(docs),
        "paper_nodes_match_docs_read": counts["paper_nodes_count"] == len(docs) - stats["skipped_docs_missing_canonical_id"],
        "paper_nodes_match_expected": None if expected_doc_count_int is None or limit is not None else counts["paper_nodes_count"] == expected_doc_count_int,
        "stats": dict(sorted(stats.items())),
        "reference_type_counts": dict(sorted(ref_type_counts.items())),
        "source_family_reference_paper_counts": dict(sorted(source_family_counts.items())),
    }
    if quality["paper_nodes_match_expected"] is False:
        quality["ok"] = False
    if stats["skipped_docs_missing_canonical_id"] > 0:
        quality["ok"] = False

    schema = {
        "schema_version": SCHEMA_VERSION,
        "graph": {"name": GRAPH_NAME, "version": GRAPH_VERSION},
        "node_types": {
            "paper": {"required_fields": ["node_id", "node_type", "canonical_id", "title", "year", "doi", "arxiv_id"]},
            "external_reference": {"required_fields": ["node_id", "node_type", "reference_key", "reference_type", "normalized_value", "resolution_status"]},
            "source_family": {"required_fields": ["node_id", "node_type", "source_family"]},
        },
        "edge_types": {
            "paper_references_paper": {"source_node_type": "paper", "target_node_type": "paper"},
            "paper_references_external": {"source_node_type": "paper", "target_node_type": "external_reference"},
            "paper_has_reference_source_family": {"source_node_type": "paper", "target_node_type": "source_family"},
        },
        "edge_common_required_fields": ["edge_id", "edge_type", "source_node_id", "target_node_id", "provenance_kind", "source_layer", "confidence"],
    }

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "graph": {"name": GRAPH_NAME, "version": GRAPH_VERSION, "status": "local_derived_output"},
        "generated_at": _now_iso(),
        "builder": {
            "script": "scripts/export/build_citation_reference_graph.py",
            "input_mode": "file",
            "live_db_dependency": False,
            "limit": limit,
        },
        "source": {
            "canonical_corpus_path": str(canonical_path),
            "config_path": str(config_path),
            "expected_canonical_doc_count": expected_doc_count_int,
            "canonical_docs_read_count": len(docs),
        },
        "counts": counts,
        "quality": quality,
        "safety": {
            "canonical_truth_impact": "none",
            "may_overwrite_operational_latest": False,
            "may_be_used_as_reconcile_input": False,
            "may_change_db_schema": False,
            "may_change_api_behavior": False,
            "may_change_streamlit_behavior": False,
            "may_change_retrieval_behavior": False,
            "may_change_qdrant_behavior": False,
            "may_change_ranking_behavior": False,
            "may_require_graph_runtime": False,
            "may_publish_without_manual_review": False,
        },
    }

    data_quality_summary = {
        "schema_version": DATA_QUALITY_SCHEMA_VERSION,
        "summary": {"ok": bool(quality["ok"]), **counts},
        "quality": quality,
        "boundaries": manifest["safety"],
    }

    readme = f"""# Citation / Reference Graph v0.1 local output\n\nThis directory contains a local derived citation/reference graph built from `canonical_documents.jsonl`.\n\nIt is not canonical truth, not a reconcile input, not a DB source, not a runtime graph, and not a public API/UI artifact.\n\nGenerated at: `{manifest['generated_at']}`\n\n## Files\n\n- `nodes.jsonl`\n- `edges.jsonl`\n- `schema.json`\n- `manifest.json`\n- `data_quality_summary.json`\n- `checksums.txt`\n\n## Counts\n\n```text\nnodes_count={counts['nodes_count']}\nedges_count={counts['edges_count']}\npaper_nodes_count={counts['paper_nodes_count']}\nexternal_reference_nodes_count={counts['external_reference_nodes_count']}\nsource_family_nodes_count={counts['source_family_nodes_count']}\npaper_references_paper_edges_count={counts['paper_references_paper_edges_count']}\npaper_references_external_edges_count={counts['paper_references_external_edges_count']}\npaper_has_reference_source_family_edges_count={counts['paper_has_reference_source_family_edges_count']}\n```\n"""

    if dry_run:
        return {
            "ok": bool(quality["ok"]),
            "dry_run": True,
            "output_dir": str(output_dir),
            "counts": counts,
            "quality": quality,
            "would_write_files": [
                "nodes.jsonl",
                "edges.jsonl",
                "schema.json",
                "manifest.json",
                "README.md",
                "data_quality_summary.json",
                "checksums.txt",
            ],
        }

    if output_dir.exists():
        if not force:
            raise FileExistsError(f"Output directory already exists; use --force to replace: {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    _write_jsonl(output_dir / "nodes.jsonl", nodes)
    _write_jsonl(output_dir / "edges.jsonl", edges)
    _write_json(output_dir / "schema.json", schema)
    _write_json(output_dir / "manifest.json", manifest)
    _write_json(output_dir / "data_quality_summary.json", data_quality_summary)
    (output_dir / "README.md").write_text(readme, encoding="utf-8")

    checksums = []
    for name in ["nodes.jsonl", "edges.jsonl", "schema.json", "manifest.json", "data_quality_summary.json", "README.md"]:
        checksums.append(f"{_sha256_file(output_dir / name)}  {name}")
    (output_dir / "checksums.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")

    return {
        "ok": bool(quality["ok"]),
        "dry_run": False,
        "output_dir": str(output_dir),
        "counts": counts,
        "quality": quality,
        "written_files": ["nodes.jsonl", "edges.jsonl", "schema.json", "manifest.json", "README.md", "data_quality_summary.json", "checksums.txt"],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build local derived Citation / Reference Graph v0.1 output.")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Path to citation/reference graph contract config.")
    parser.add_argument("--canonical-path", default=None, help="Override canonical JSONL input path.")
    parser.add_argument("--output-dir", default=None, help="Override graph output directory.")
    parser.add_argument("--force", action="store_true", help="Replace the output directory if it already exists.")
    parser.add_argument("--dry-run", action="store_true", help="Compute graph summary without writing files.")
    parser.add_argument("--limit", type=int, default=None, help="Optional debug row limit for local smoke/debug runs.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = build_graph(
        config_path=Path(args.config),
        canonical_path=Path(args.canonical_path) if args.canonical_path else None,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        force=args.force,
        dry_run=args.dry_run,
        limit=args.limit,
    )
    summary = {
        "ok": result.get("ok"),
        "dry_run": result.get("dry_run"),
        "output_dir": result.get("output_dir"),
        **result.get("counts", {}),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
