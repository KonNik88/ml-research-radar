from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from radar_core.artifacts.trusted_links import (
    TRUSTED_LINK_POLICY_VERSION,
    build_trusted_link_rows,
)


DEFAULT_CONFIG_PATH = Path("configs/paper_artifact_graph_builder.yaml")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(value: str | Path) -> str:
    return str(value).replace("\\", "/")


def stable_hash(*parts: Any, length: int = 32) -> str:
    text = "\n".join("" if p is None else str(p) for p in parts)
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:length]


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return payload


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line), line_no
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL: {path} line={line_no}: {exc}") from exc


def load_jsonl(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row, _ in iter_jsonl(path):
        if isinstance(row, dict):
            rows.append(row)
        if limit is not None and len(rows) >= limit:
            break
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_path(raw: Any) -> Path:
    path = Path(str(raw))
    if path.is_absolute():
        return path
    return Path.cwd() / path


def as_str_or_none(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def paper_node_id(canonical_id: str) -> str:
    return f"paper:{canonical_id}"


def artifact_node_id(artifact_id: str) -> str:
    return f"artifact:{artifact_id}"


def provider_node_id(provider: str) -> str:
    return f"provider:{provider}"


def source_family_node_id(source_family: str) -> str:
    return f"source_family:{source_family}"


def topic_cluster_node_id(cluster_id: str) -> str:
    return f"topic_cluster:{cluster_id}"


def make_edge_id(edge_type: str, source_node_id: str, target_node_id: str, relation: str | None = None) -> str:
    return f"edge:{stable_hash(edge_type, source_node_id, target_node_id, relation or '')}"


def get_first(row: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def extract_paper_properties(row: dict[str, Any]) -> dict[str, Any]:
    source_count = row.get("source_count")
    unique_source_count = row.get("unique_source_count")

    sources = row.get("sources")
    if isinstance(sources, list):
        source_count = source_count if source_count is not None else len(sources)
        unique_source_count = unique_source_count if unique_source_count is not None else len(
            {extract_source_family(src) for src in sources if extract_source_family(src)}
        )

    props = {
        "canonical_id": row.get("canonical_id"),
        "title": get_first(row, ["title", "display_title", "normalized_title"]),
        "year": get_first(row, ["year", "publication_year", "published_year"]),
        "doi": get_first(row, ["doi", "external_doi"]),
        "arxiv_id": get_first(row, ["arxiv_id", "external_arxiv_id"]),
        "primary_category": get_first(row, ["primary_category", "category"]),
        "source_count": source_count,
        "unique_source_count": unique_source_count,
    }
    return {k: v for k, v in props.items() if v is not None}


def extract_artifact_properties(row: dict[str, Any]) -> dict[str, Any]:
    props = {
        "artifact_id": row.get("artifact_id"),
        "artifact_type": row.get("artifact_type"),
        "provider": row.get("provider"),
        "normalized_url": row.get("normalized_url"),
        "canonical_url": row.get("canonical_url"),
        "external_id": row.get("external_id"),
        "name": row.get("name"),
    }

    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        # Keep only a compact, non-provider-dump subset in builder v0.1.
        compact_metadata = {
            key: metadata.get(key)
            for key in [
                "source",
                "extraction_stage",
                "license",
                "status",
            ]
            if metadata.get(key) is not None
        }
        if compact_metadata:
            props["metadata"] = compact_metadata

    return {k: v for k, v in props.items() if v is not None}


def extract_source_family(source: Any) -> str | None:
    if isinstance(source, str):
        return source.strip() or None

    if not isinstance(source, dict):
        return None

    for key in ["source_family", "source", "source_name", "name", "family"]:
        value = source.get(key)
        if value:
            return str(value).strip()

    source_id = source.get("source_id")
    if source_id:
        text = str(source_id)
        if ":" in text:
            return text.split(":", 1)[0].strip()

    return None


def resolve_topic_assignments_path(topic_latest_path: Path, latest: dict[str, Any]) -> Path | None:
    raw = latest.get("assignments_path")
    if not raw:
        return None

    path = Path(str(raw))
    if path.is_absolute():
        return path

    # Prefer repo-root relative paths because current latest.json stores project paths.
    repo_relative = Path.cwd() / path
    if repo_relative.exists():
        return repo_relative

    # Fallback for latest files that store run-dir-relative paths.
    return topic_latest_path.parent / path


def extract_topic_assignment(row: dict[str, Any]) -> tuple[str | None, str | None, dict[str, Any]]:
    canonical_id = as_str_or_none(
        get_first(row, ["canonical_id", "paper_id", "doc_id", "id"])
    )

    cluster_id = as_str_or_none(
        get_first(row, ["topic_cluster_id", "cluster_id", "cluster", "topic_id"])
    )

    props = {
        "score": get_first(row, ["score", "similarity", "confidence", "probability"]),
        "distance": row.get("distance"),
        "rank": row.get("rank"),
    }
    props = {k: v for k, v in props.items() if v is not None}

    return canonical_id, cluster_id, props


def build_nodes_and_edges(
    *,
    config: dict[str, Any],
    canonical_docs: list[dict[str, Any]],
    artifact_entities: list[dict[str, Any]],
    artifact_observations: list[dict[str, Any]],
    topic_latest: dict[str, Any] | None,
    topic_assignments: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    nodes_by_id: dict[str, dict[str, Any]] = {}
    edges_by_id: dict[str, dict[str, Any]] = {}

    canonical_ids: set[str] = set()
    artifact_ids: set[str] = set()

    def add_node(node_id: str, node_type: str, label: str, properties: dict[str, Any]) -> None:
        if node_id in nodes_by_id:
            existing_props = nodes_by_id[node_id].setdefault("properties", {})
            existing_props.update({k: v for k, v in properties.items() if v is not None})
            return

        nodes_by_id[node_id] = {
            "node_id": node_id,
            "node_type": node_type,
            "label": label,
            "properties": {k: v for k, v in properties.items() if v is not None},
        }

    def add_edge(
        edge_type: str,
        source_node_id: str,
        target_node_id: str,
        properties: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        relation: str | None = None,
    ) -> None:
        edge_id = make_edge_id(edge_type, source_node_id, target_node_id, relation)
        if edge_id in edges_by_id:
            return

        edges_by_id[edge_id] = {
            "edge_id": edge_id,
            "edge_type": edge_type,
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "properties": properties or {},
            "provenance": provenance or {},
        }

    # Papers and source families.
    for paper in canonical_docs:
        canonical_id = as_str_or_none(paper.get("canonical_id"))
        if not canonical_id:
            continue

        canonical_ids.add(canonical_id)
        title = as_str_or_none(get_first(paper, ["title", "display_title", "normalized_title"])) or canonical_id

        add_node(
            paper_node_id(canonical_id),
            "paper",
            title,
            extract_paper_properties(paper),
        )

        sources = paper.get("sources")
        if isinstance(sources, list):
            for source in sources:
                family = extract_source_family(source)
                if not family:
                    continue

                add_node(
                    source_family_node_id(family),
                    "source_family",
                    family,
                    {"source_family": family},
                )
                add_edge(
                    "paper_observed_in_source_family",
                    paper_node_id(canonical_id),
                    source_family_node_id(family),
                    properties={"source_family": family},
                    provenance={
                        "source_layer": "canonical_documents.sources",
                        "source": "canonical_documents",
                    },
                    relation=family,
                )

    # Artifacts and providers.
    for entity in artifact_entities:
        artifact_id = as_str_or_none(entity.get("artifact_id"))
        if not artifact_id:
            continue

        artifact_ids.add(artifact_id)
        provider = as_str_or_none(entity.get("provider")) or "unknown"
        artifact_type = as_str_or_none(entity.get("artifact_type")) or "artifact"
        label = (
            as_str_or_none(entity.get("name"))
            or as_str_or_none(entity.get("normalized_url"))
            or artifact_id
        )

        add_node(
            artifact_node_id(artifact_id),
            "artifact",
            label,
            extract_artifact_properties(entity),
        )

        add_node(
            provider_node_id(provider),
            "provider",
            provider,
            {"provider": provider},
        )

        add_edge(
            "artifact_from_provider",
            artifact_node_id(artifact_id),
            provider_node_id(provider),
            properties={
                "provider": provider,
                "artifact_type": artifact_type,
            },
            provenance={
                "source_layer": "artifact_entities",
                "source": "artifact_entities_latest",
            },
            relation=provider,
        )

    # Trusted paper-artifact links.
    trusted_links_raw = build_trusted_link_rows(artifact_observations)
    trusted_links: list[dict[str, Any]] = []
    skipped_trusted_links_missing_paper = 0
    skipped_trusted_links_missing_artifact = 0

    for link in trusted_links_raw:
        canonical_id = as_str_or_none(link.get("canonical_id"))
        artifact_id = as_str_or_none(link.get("artifact_id"))
        relation_type = as_str_or_none(link.get("relation_type")) or "artifact"

        if not canonical_id or canonical_id not in canonical_ids:
            skipped_trusted_links_missing_paper += 1
            continue
        if not artifact_id or artifact_id not in artifact_ids:
            skipped_trusted_links_missing_artifact += 1
            continue

        trusted_links.append(link)

        add_edge(
            "paper_has_artifact",
            paper_node_id(canonical_id),
            artifact_node_id(artifact_id),
            properties={
                "link_id": link.get("link_id"),
                "relation_type": relation_type,
                "confidence": link.get("confidence"),
                "evidence_source": link.get("evidence_source"),
                "evidence_url": link.get("evidence_url"),
                "source_field": link.get("source_field"),
                "source_doc_id": link.get("source_doc_id"),
                "metadata": link.get("metadata"),
            },
            provenance={
                "source_layer": "artifact_observations",
                "source": "artifact_links_latest",
                "trusted_link_policy_version": TRUSTED_LINK_POLICY_VERSION,
            },
            relation=relation_type,
        )

    # Topic clusters.
    include_topic_clusters = bool(config.get("features", {}).get("include_topic_clusters"))
    topic_edges_count = 0
    topic_assignments_valid = 0
    topic_assignments_missing_paper = 0
    topic_assignments_missing_cluster = 0

    if include_topic_clusters:
        cluster_build_id = None
        retrieval_build_id = None
        if isinstance(topic_latest, dict):
            cluster_build_id = topic_latest.get("cluster_build_id")
            retrieval_build_id = topic_latest.get("retrieval_build_id")

        for assignment in topic_assignments:
            canonical_id, cluster_id, assignment_props = extract_topic_assignment(assignment)

            if not canonical_id or canonical_id not in canonical_ids:
                topic_assignments_missing_paper += 1
                continue
            if not cluster_id:
                topic_assignments_missing_cluster += 1
                continue

            topic_assignments_valid += 1
            add_node(
                topic_cluster_node_id(cluster_id),
                "topic_cluster",
                f"Topic cluster {cluster_id}",
                {
                    "topic_cluster_id": cluster_id,
                    "cluster_build_id": cluster_build_id,
                    "retrieval_build_id": retrieval_build_id,
                },
            )
            add_edge(
                "paper_assigned_to_topic_cluster",
                paper_node_id(canonical_id),
                topic_cluster_node_id(cluster_id),
                properties={
                    "topic_cluster_id": cluster_id,
                    **assignment_props,
                },
                provenance={
                    "source_layer": "topic_clusters",
                    "source": "topic_assignments",
                    "cluster_build_id": cluster_build_id,
                    "retrieval_build_id": retrieval_build_id,
                },
                relation=cluster_id,
            )
            topic_edges_count += 1

    nodes = sorted(nodes_by_id.values(), key=lambda row: (row["node_type"], row["node_id"]))
    edges = sorted(edges_by_id.values(), key=lambda row: (row["edge_type"], row["edge_id"]))

    node_type_counts = Counter(row["node_type"] for row in nodes)
    edge_type_counts = Counter(row["edge_type"] for row in edges)

    quality = {
        "nodes_count": len(nodes),
        "edges_count": len(edges),
        "node_type_counts": dict(sorted(node_type_counts.items())),
        "edge_type_counts": dict(sorted(edge_type_counts.items())),
        "canonical_papers_loaded": len(canonical_docs),
        "canonical_papers_with_ids": len(canonical_ids),
        "artifact_entities_loaded": len(artifact_entities),
        "artifact_entities_with_ids": len(artifact_ids),
        "artifact_observations_loaded": len(artifact_observations),
        "trusted_links_raw_count": len(trusted_links_raw),
        "trusted_links_used_count": len(trusted_links),
        "skipped_trusted_links_missing_paper": skipped_trusted_links_missing_paper,
        "skipped_trusted_links_missing_artifact": skipped_trusted_links_missing_artifact,
        "topic_assignments_loaded": len(topic_assignments),
        "topic_assignments_valid": topic_assignments_valid,
        "topic_edges_count": topic_edges_count,
        "topic_assignments_missing_paper": topic_assignments_missing_paper,
        "topic_assignments_missing_cluster": topic_assignments_missing_cluster,
    }

    return nodes, edges, quality


def build_graph(
    *,
    config_path: Path,
    output_dir_override: Path | None = None,
    limit_papers: int | None = None,
    limit_artifacts: int | None = None,
    limit_observations: int | None = None,
    limit_topic_assignments: int | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    run_ts = utc_now_ts()
    generated_at_utc = utc_now_iso()

    config = load_yaml(config_path)
    inputs = config.get("inputs", {})
    outputs = dict(config.get("outputs", {}))

    if output_dir_override is not None:
        graph_dir = output_dir_override
        outputs = {
            "graph_dir": normalize_path(graph_dir),
            "nodes_path": normalize_path(graph_dir / "nodes.jsonl"),
            "edges_path": normalize_path(graph_dir / "edges.jsonl"),
            "schema_path": normalize_path(graph_dir / "schema.json"),
            "manifest_path": normalize_path(graph_dir / "manifest.json"),
            "data_quality_summary_path": normalize_path(graph_dir / "data_quality_summary.json"),
            "readme_path": normalize_path(graph_dir / "README.md"),
            "checksums_path": normalize_path(graph_dir / "checksums.txt"),
        }

    graph_dir = resolve_path(outputs["graph_dir"])

    output_paths = {
        key: resolve_path(value)
        for key, value in outputs.items()
        if key.endswith("_path")
    }

    if graph_dir.exists() and any(graph_dir.iterdir()) and not force and not dry_run:
        raise FileExistsError(
            f"Output graph_dir already exists and is not empty: {graph_dir}. "
            "Use --force to overwrite files."
        )

    canonical_path = resolve_path(inputs["canonical_documents_path"])
    artifact_entities_path = resolve_path(inputs["artifact_entities_path"])
    artifact_links_path = resolve_path(inputs["artifact_links_path"])
    topic_latest_path = resolve_path(inputs["topic_clusters_latest_path"])

    canonical_docs = load_jsonl(canonical_path, limit=limit_papers)
    artifact_entities = load_jsonl(artifact_entities_path, limit=limit_artifacts)
    artifact_observations = load_jsonl(artifact_links_path, limit=limit_observations)

    topic_latest = load_json(topic_latest_path)
    topic_assignments_path = resolve_topic_assignments_path(topic_latest_path, topic_latest)
    topic_assignments: list[dict[str, Any]] = []

    if config.get("features", {}).get("include_topic_clusters"):
        if topic_assignments_path is None:
            raise ValueError("include_topic_clusters=true but topic latest has no assignments_path")
        topic_assignments = load_jsonl(topic_assignments_path, limit=limit_topic_assignments)

    nodes, edges, quality = build_nodes_and_edges(
        config=config,
        canonical_docs=canonical_docs,
        artifact_entities=artifact_entities,
        artifact_observations=artifact_observations,
        topic_latest=topic_latest,
        topic_assignments=topic_assignments,
    )

    schema = {
        "schema_version": "paper_artifact_graph_output_schema_v1",
        "graph_name": config.get("graph", {}).get("name"),
        "graph_version": config.get("graph", {}).get("version"),
        "node_schema": {
            "required_fields": ["node_id", "node_type", "label", "properties"],
            "node_types": ["paper", "artifact", "provider", "source_family", "topic_cluster"],
        },
        "edge_schema": {
            "required_fields": ["edge_id", "edge_type", "source_node_id", "target_node_id", "properties", "provenance"],
            "edge_types": [
                "paper_has_artifact",
                "artifact_from_provider",
                "paper_observed_in_source_family",
                "paper_assigned_to_topic_cluster",
            ],
        },
        "identity_policy": {
            "paper": "paper:{canonical_id}",
            "artifact": "artifact:{artifact_id}",
            "provider": "provider:{provider}",
            "source_family": "source_family:{source_family}",
            "topic_cluster": "topic_cluster:{cluster_id}",
        },
    }

    manifest = {
        "schema_version": "paper_artifact_graph_manifest_v1",
        "generated_at_utc": generated_at_utc,
        "run_ts": run_ts,
        "builder": dict(config.get("builder", {})),
        "graph": dict(config.get("graph", {})),
        "contract": dict(config.get("contract", {})),
        "inputs": {
            "canonical_documents_path": normalize_path(canonical_path),
            "artifact_entities_path": normalize_path(artifact_entities_path),
            "artifact_links_path": normalize_path(artifact_links_path),
            "topic_clusters_latest_path": normalize_path(topic_latest_path),
            "topic_assignments_path": normalize_path(topic_assignments_path) if topic_assignments_path else None,
        },
        "outputs": {
            key: normalize_path(path)
            for key, path in output_paths.items()
        },
        "safety": dict(config.get("safety", {})),
        "trusted_links": {
            **dict(config.get("trusted_links", {})),
            "runtime_policy_version": TRUSTED_LINK_POLICY_VERSION,
        },
        "quality_summary": quality,
        "limits": {
            "limit_papers": limit_papers,
            "limit_artifacts": limit_artifacts,
            "limit_observations": limit_observations,
            "limit_topic_assignments": limit_topic_assignments,
        },
        "dry_run": dry_run,
        "publication_ready": False,
        "canonical_truth": False,
        "may_be_used_as_reconcile_input": False,
    }

    data_quality_summary = {
        "schema_version": "paper_artifact_graph_data_quality_summary_v1",
        "generated_at_utc": generated_at_utc,
        "run_ts": run_ts,
        "ok": True,
        "quality": quality,
        "expected_counts": dict(config.get("expected_counts", {})),
    }

    readme = "\n".join(
        [
            "# Paper–Artifact Graph v0.1",
            "",
            "Local derived graph artifact generated from accepted ML Research Radar layers.",
            "",
            "This graph is not canonical truth, not a reconcile input, and not a publication-ready dataset.",
            "",
            "## Files",
            "",
            "- `nodes.jsonl` — graph nodes",
            "- `edges.jsonl` — graph edges",
            "- `schema.json` — output schema",
            "- `manifest.json` — generation manifest",
            "- `data_quality_summary.json` — data quality counters",
            "- `checksums.txt` — SHA256 checksums",
            "",
            "## Safety",
            "",
            "- Does not mutate canonical documents",
            "- Does not mutate artifact inputs",
            "- Does not mutate topic inputs",
            "- Does not use live DB",
            "- Does not create a latest pointer",
            "- Does not create a global `paper_artifact_links_latest.jsonl` bridge",
            "",
        ]
    )

    if dry_run:
        return {
            "schema_version": "paper_artifact_graph_builder_dry_run_v1",
            "generated_at_utc": generated_at_utc,
            "run_ts": run_ts,
            "dry_run": True,
            "would_write": outputs,
            "quality_summary": quality,
        }

    graph_dir.mkdir(parents=True, exist_ok=True)

    write_jsonl(output_paths["nodes_path"], nodes)
    write_jsonl(output_paths["edges_path"], edges)
    write_json(output_paths["schema_path"], schema)
    write_json(output_paths["manifest_path"], manifest)
    write_json(output_paths["data_quality_summary_path"], data_quality_summary)
    output_paths["readme_path"].write_text(readme, encoding="utf-8")

    checksum_rows = []
    for key in [
        "nodes_path",
        "edges_path",
        "schema_path",
        "manifest_path",
        "data_quality_summary_path",
        "readme_path",
    ]:
        path = output_paths[key]
        checksum_rows.append(f"{sha256_file(path)}  {path.name}")

    output_paths["checksums_path"].write_text("\n".join(checksum_rows) + "\n", encoding="utf-8")

    return {
        "schema_version": "paper_artifact_graph_builder_result_v1",
        "generated_at_utc": generated_at_utc,
        "run_ts": run_ts,
        "dry_run": False,
        "graph_dir": normalize_path(graph_dir),
        "outputs": {
            key: normalize_path(path)
            for key, path in output_paths.items()
        },
        "quality_summary": quality,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--limit-papers", type=int, default=None)
    parser.add_argument("--limit-artifacts", type=int, default=None)
    parser.add_argument("--limit-observations", type=int, default=None)
    parser.add_argument("--limit-topic-assignments", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    result = build_graph(
        config_path=args.config_path,
        output_dir_override=args.output_dir,
        limit_papers=args.limit_papers,
        limit_artifacts=args.limit_artifacts,
        limit_observations=args.limit_observations,
        limit_topic_assignments=args.limit_topic_assignments,
        dry_run=args.dry_run,
        force=args.force,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
