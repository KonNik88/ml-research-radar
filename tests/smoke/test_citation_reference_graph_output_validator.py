from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

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


builder = _load_module(BUILDER_PATH, "build_citation_reference_graph_for_output_validator_tests")
validator = _load_module(VALIDATOR_PATH, "check_citation_reference_graph_output")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _make_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    canonical_path = tmp_path / "canonical_documents.jsonl"
    output_dir = tmp_path / "graph"
    config_path = tmp_path / "citation_reference_graph.yaml"
    _write_jsonl(
        canonical_path,
        [
            {"canonical_id": "a", "title": "A", "year": 2024, "doi": "10.1/a", "sources": ["arxiv"], "referenced_dois": ["10.1/b"], "references_count": 1},
            {"canonical_id": "b", "title": "B", "year": 2024, "doi": "10.1/b", "sources": ["openalex_alignment"], "referenced_ids": ["external-y"], "references_count": 1},
        ],
    )
    config = {
        "schema_version": "citation_reference_graph_config_v1",
        "source_checkpoint": {"canonical_corpus_path": str(canonical_path), "expected_canonical_doc_count": 2},
        "outputs": {"expected_future_output_dir": str(output_dir)},
    }
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    builder.build_graph(config_path=config_path, canonical_path=canonical_path, output_dir=output_dir)
    return config_path, canonical_path, output_dir


def test_validator_detects_duplicate_node_ids(tmp_path: Path) -> None:
    config_path, _, output_dir = _make_fixture(tmp_path)
    nodes_path = output_dir / "nodes.jsonl"
    first_line = nodes_path.read_text(encoding="utf-8").splitlines()[0]
    with nodes_path.open("a", encoding="utf-8") as f:
        f.write(first_line + "\n")

    report = validator.validate_output(config_path=config_path, output_dir=output_dir, write_reports=False)
    assert report["summary"]["ok"] is False
    assert "node_ids_unique" in report["required_failed_checks"]


def test_validator_detects_dangling_edge(tmp_path: Path) -> None:
    config_path, _, output_dir = _make_fixture(tmp_path)
    edges_path = output_dir / "edges.jsonl"
    rows = [json.loads(line) for line in edges_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows[0]["target_node_id"] = "paper:missing"
    _write_jsonl(edges_path, rows)

    report = validator.validate_output(config_path=config_path, output_dir=output_dir, write_reports=False)
    assert report["summary"]["ok"] is False
    assert "edges_reference_existing_nodes" in report["required_failed_checks"]


def test_validator_detects_manifest_safety_violation(tmp_path: Path) -> None:
    config_path, _, output_dir = _make_fixture(tmp_path)
    manifest_path = output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["safety"]["may_change_db_schema"] = True
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = validator.validate_output(config_path=config_path, output_dir=output_dir, write_reports=False)
    assert report["summary"]["ok"] is False
    assert "manifest_safety_flags_false" in report["required_failed_checks"]
