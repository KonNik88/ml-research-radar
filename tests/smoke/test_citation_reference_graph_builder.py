from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = ROOT / "scripts" / "export" / "build_citation_reference_graph.py"
VALIDATOR_PATH = ROOT / "scripts" / "validation" / "check_citation_reference_graph_output.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


builder = _load_module(BUILDER_PATH, "build_citation_reference_graph")
validator = _load_module(VALIDATOR_PATH, "check_citation_reference_graph_output_for_builder_tests")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@pytest.fixture()
def fixture_project(tmp_path: Path) -> dict[str, Path]:
    canonical_path = tmp_path / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
    config_path = tmp_path / "configs" / "citation_reference_graph.yaml"
    output_dir = tmp_path / "data" / "graphs" / "citation_reference_graph" / "v0.1"

    docs = [
        {
            "canonical_id": "paper_a",
            "title": "Paper A",
            "year": 2024,
            "doi": "10.1234/a",
            "arxiv_id": "2401.00001",
            "sources": ["arxiv", "openalex_alignment"],
            "referenced_dois": ["https://doi.org/10.1234/b"],
            "referenced_arxiv_ids": ["2401.00003v2"],
            "referenced_ids": ["external-x", {"type": "openalex_id", "id": "W12345"}],
            "references_count": 4,
        },
        {
            "canonical_id": "paper_b",
            "title": "Paper B",
            "year": 2023,
            "doi": "10.1234/b",
            "sources": ["semantic_scholar_alignment"],
            "referenced_ids": ["paper_a"],
            "references_count": 1,
        },
        {
            "canonical_id": "paper_c",
            "title": "Paper C",
            "year": 2022,
            "arxiv_id": "2401.00003",
            "external_ids": {"openalex_id": "https://openalex.org/W12345"},
            "sources": ["crossref_alignment"],
            "references_count": 0,
        },
    ]
    _write_jsonl(canonical_path, docs)

    config = {
        "schema_version": "citation_reference_graph_config_v1",
        "graph": {"name": "citation_reference_graph", "version": "v0.1", "status": "contract_only"},
        "source_checkpoint": {
            "canonical_corpus_path": str(canonical_path),
            "expected_canonical_doc_count": 3,
            "retrieval_manifest_path": "artifacts/retrieval/manifests/latest.json",
        },
        "outputs": {
            "expected_future_output_dir": str(output_dir),
        },
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return {"canonical_path": canonical_path, "config_path": config_path, "output_dir": output_dir}


def test_openalex_url_reference_id_is_not_misclassified_as_doi() -> None:
    assert builder._infer_reference_type("https://openalex.org/W2194775991") == "openalex_id"
    assert builder._normalize_reference_value("https://openalex.org/W2194775991", "openalex_id") == "W2194775991"
    assert builder._normalize_doi("https://openalex.org/W2194775991") is None


def test_referenced_ids_openalex_url_resolves_to_canonical(tmp_path: Path) -> None:
    canonical_path = tmp_path / "canonical_documents.jsonl"
    output_dir = tmp_path / "graph"
    config_path = tmp_path / "citation_reference_graph.yaml"
    _write_jsonl(
        canonical_path,
        [
            {
                "canonical_id": "source",
                "title": "Source",
                "year": 2024,
                "sources": ["openalex_alignment"],
                "referenced_ids": ["https://openalex.org/W2194775991"],
                "references_count": 1,
            },
            {
                "canonical_id": "target",
                "title": "Target",
                "year": 2023,
                "openalex_id": "https://openalex.org/W2194775991",
                "sources": ["openalex_alignment"],
            },
        ],
    )
    config = {
        "schema_version": "citation_reference_graph_config_v1",
        "source_checkpoint": {"canonical_corpus_path": str(canonical_path), "expected_canonical_doc_count": 2},
        "outputs": {"expected_future_output_dir": str(output_dir)},
    }
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = builder.build_graph(config_path=config_path, canonical_path=canonical_path, output_dir=output_dir)

    assert result["counts"]["paper_references_paper_edges_count"] == 1
    assert result["counts"]["paper_references_external_edges_count"] == 0
    edges = _read_jsonl(output_dir / "edges.jsonl")
    assert any(
        edge["edge_type"] == "paper_references_paper"
        and edge["reference_type"] == "openalex_id"
        and edge["reference_value"] == "W2194775991"
        for edge in edges
    )


def test_builder_writes_expected_graph_files(fixture_project: dict[str, Path]) -> None:
    result = builder.build_graph(
        config_path=fixture_project["config_path"],
        canonical_path=fixture_project["canonical_path"],
        output_dir=fixture_project["output_dir"],
    )

    assert result["ok"] is True
    assert result["counts"]["paper_nodes_count"] == 3
    assert result["counts"]["paper_references_paper_edges_count"] == 4
    assert result["counts"]["paper_references_external_edges_count"] == 1
    assert result["counts"]["paper_has_reference_source_family_edges_count"] == 3

    for name in ["nodes.jsonl", "edges.jsonl", "schema.json", "manifest.json", "README.md", "data_quality_summary.json", "checksums.txt"]:
        assert (fixture_project["output_dir"] / name).exists()

    nodes = _read_jsonl(fixture_project["output_dir"] / "nodes.jsonl")
    edges = _read_jsonl(fixture_project["output_dir"] / "edges.jsonl")
    assert any(node["node_type"] == "external_reference" and node["normalized_value"] == "external-x" for node in nodes)
    assert any(edge["edge_type"] == "paper_references_paper" for edge in edges)
    assert any(edge["edge_type"] == "paper_references_external" for edge in edges)


def test_builder_dry_run_does_not_write_files(fixture_project: dict[str, Path]) -> None:
    result = builder.build_graph(
        config_path=fixture_project["config_path"],
        canonical_path=fixture_project["canonical_path"],
        output_dir=fixture_project["output_dir"],
        dry_run=True,
    )

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert not fixture_project["output_dir"].exists()


def test_builder_refuses_existing_output_without_force(fixture_project: dict[str, Path]) -> None:
    builder.build_graph(
        config_path=fixture_project["config_path"],
        canonical_path=fixture_project["canonical_path"],
        output_dir=fixture_project["output_dir"],
    )

    with pytest.raises(FileExistsError):
        builder.build_graph(
            config_path=fixture_project["config_path"],
            canonical_path=fixture_project["canonical_path"],
            output_dir=fixture_project["output_dir"],
        )


def test_builder_force_replaces_existing_output(fixture_project: dict[str, Path]) -> None:
    builder.build_graph(
        config_path=fixture_project["config_path"],
        canonical_path=fixture_project["canonical_path"],
        output_dir=fixture_project["output_dir"],
    )
    marker = fixture_project["output_dir"] / "extra.tmp"
    marker.write_text("remove me", encoding="utf-8")

    builder.build_graph(
        config_path=fixture_project["config_path"],
        canonical_path=fixture_project["canonical_path"],
        output_dir=fixture_project["output_dir"],
        force=True,
    )
    assert not marker.exists()


def test_output_validator_passes_on_builder_output(fixture_project: dict[str, Path]) -> None:
    builder.build_graph(
        config_path=fixture_project["config_path"],
        canonical_path=fixture_project["canonical_path"],
        output_dir=fixture_project["output_dir"],
    )
    report = validator.validate_output(
        config_path=fixture_project["config_path"],
        output_dir=fixture_project["output_dir"],
        strict=True,
        write_reports=False,
    )

    assert report["summary"]["ok"] is True
    assert report["summary"]["required_failed_count"] == 0
    assert report["counts"]["node_type_counts"]["paper"] == 3


def test_output_validator_writes_reports(fixture_project: dict[str, Path], tmp_path: Path) -> None:
    builder.build_graph(
        config_path=fixture_project["config_path"],
        canonical_path=fixture_project["canonical_path"],
        output_dir=fixture_project["output_dir"],
    )
    report_dir = tmp_path / "reports"
    report = validator.validate_output(
        config_path=fixture_project["config_path"],
        output_dir=fixture_project["output_dir"],
        strict=True,
        write_reports=True,
        report_dir=report_dir,
    )

    assert report["summary"]["ok"] is True
    assert (report_dir / "citation_reference_graph_output_latest.json").exists()
    assert (report_dir / "citation_reference_graph_output_latest.md").exists()
    assert list((report_dir / "history").glob("citation_reference_graph_output_*.json"))


def test_output_validator_fails_when_required_file_missing(fixture_project: dict[str, Path]) -> None:
    builder.build_graph(
        config_path=fixture_project["config_path"],
        canonical_path=fixture_project["canonical_path"],
        output_dir=fixture_project["output_dir"],
    )
    (fixture_project["output_dir"] / "edges.jsonl").unlink()

    report = validator.validate_output(
        config_path=fixture_project["config_path"],
        output_dir=fixture_project["output_dir"],
        strict=True,
        write_reports=False,
    )
    assert report["summary"]["ok"] is False
    assert "required_file_exists:edges.jsonl" in report["required_failed_checks"]


def test_output_validator_fails_on_checksum_mismatch(fixture_project: dict[str, Path]) -> None:
    builder.build_graph(
        config_path=fixture_project["config_path"],
        canonical_path=fixture_project["canonical_path"],
        output_dir=fixture_project["output_dir"],
    )
    with (fixture_project["output_dir"] / "README.md").open("a", encoding="utf-8") as f:
        f.write("\nchanged\n")

    report = validator.validate_output(
        config_path=fixture_project["config_path"],
        output_dir=fixture_project["output_dir"],
        strict=True,
        write_reports=False,
    )
    assert report["summary"]["ok"] is False
    assert "checksums_match" in report["required_failed_checks"]
