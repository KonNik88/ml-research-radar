from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from scripts.export.export_public_dataset import export_public_dataset
from scripts.validation.check_dataset_release_output import validate_release_output


def tiny_docs() -> list[dict]:
    return [
        {
            "canonical_id": "paper-c",
            "title": "C Paper",
            "abstract": None,
            "authors": ["Carol"],
            "year": 2026,
            "doi": None,
            "arxiv_id": "2601.00003",
            "openalex_id": None,
            "primary_category": "cs.LG",
            "categories": ["cs.LG"],
            "concepts": ["machine learning"],
            "venue": None,
            "journal": None,
            "conference": None,
            "publisher": None,
            "publication_type": "preprint",
            "language": "en",
            "landing_page_url": "https://arxiv.org/abs/2601.00003",
            "pdf_url": "https://arxiv.org/pdf/2601.00003",
            "open_access": True,
            "source_count": 1,
            "unique_source_count": 1,
            "sources": [{"source": "arxiv", "source_record_id": "2601.00003"}],
            "metadata_completeness_score": 0.7,
            "is_preprint": True,
            "is_review": False,
            "is_survey": False,
            "is_withdrawn": False,
            "keywords": [],
            "tags": ["ml"],
            "cited_by_count": None,
            "references_count": None,
            "source_ids": {"arxiv": "2601.00003"},
            "external_ids": {},
        },
        {
            "canonical_id": "paper-a",
            "title": "A Paper",
            "abstract": "A compact abstract.",
            "authors": ["Alice", "Bob"],
            "year": 2024,
            "doi": "10.0000/a",
            "arxiv_id": "2401.00001",
            "openalex_id": "W1",
            "primary_category": "cs.AI",
            "categories": ["cs.AI", "cs.LG"],
            "concepts": ["artificial intelligence", "retrieval"],
            "venue": "TestConf",
            "journal": None,
            "conference": "TestConf",
            "publisher": "Example Publisher",
            "publication_type": "conference-paper",
            "language": "en",
            "landing_page_url": "https://example.org/a",
            "pdf_url": "https://example.org/a.pdf",
            "open_access": True,
            "source_count": 3,
            "unique_source_count": 3,
            "sources": [
                {"source": "arxiv", "source_record_id": "2401.00001"},
                {"source": "openalex_alignment", "source_record_id": "W1"},
                {"source": "crossref_alignment", "source_record_id": "10.0000/a"},
            ],
            "metadata_completeness_score": 0.95,
            "is_preprint": False,
            "is_review": False,
            "is_survey": True,
            "is_withdrawn": False,
            "keywords": ["retrieval"],
            "tags": ["search"],
            "cited_by_count": 12,
            "references_count": 30,
            "source_ids": {"arxiv": "2401.00001", "openalex": "W1"},
            "external_ids": {"doi": "10.0000/a"},
        },
        {
            "canonical_id": "paper-b",
            "title": "B Paper",
            "abstract": "B abstract.",
            "authors": [],
            "year": 2014,
            "doi": None,
            "arxiv_id": None,
            "openalex_id": None,
            "primary_category": None,
            "categories": [],
            "concepts": [],
            "venue": None,
            "journal": None,
            "conference": None,
            "publisher": None,
            "publication_type": None,
            "language": "en",
            "landing_page_url": None,
            "pdf_url": None,
            "open_access": None,
            "source_count": 1,
            "unique_source_count": 1,
            "sources": [{"source": "acl_anthology", "source_record_id": "b"}],
            "metadata_completeness_score": 0.3,
            "is_preprint": None,
            "is_review": False,
            "is_survey": False,
            "is_withdrawn": False,
            "keywords": [],
            "tags": [],
            "cited_by_count": 0,
            "references_count": 0,
            "source_ids": {},
            "external_ids": {},
        },
    ]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def make_config(tmp_path: Path) -> tuple[dict, Path]:
    config = yaml.safe_load(Path("configs/dataset_release.yaml").read_text(encoding="utf-8"))
    canonical_rel = "data/analytics/reconciled/canonical_documents.jsonl"
    config["source_checkpoint"]["canonical_corpus_path"] = canonical_rel
    config["source_checkpoint"]["expected_canonical_doc_count"] = 3
    config["source_checkpoint"]["retrieval_corpus_doc_count"] = 3
    config["export"]["output_root"] = "data/datasets_release"
    config["export"]["max_rows"] = None

    config_path = tmp_path / "configs" / "dataset_release.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    policy_source = Path("configs/public_metadata_release_policy_v0.1.yaml")
    policy_target = tmp_path / config["public_release_policy"]["path"]
    policy_target.parent.mkdir(parents=True, exist_ok=True)
    policy_target.write_text(policy_source.read_text(encoding="utf-8"), encoding="utf-8")
    write_jsonl(tmp_path / canonical_rel, tiny_docs())
    return config, config_path


def required_failures(checks) -> set[str]:
    return {check.name for check in checks if check.severity == "required" and not check.ok}


def test_export_creates_valid_local_candidate_release(tmp_path: Path) -> None:
    config, config_path = make_config(tmp_path)

    summary = export_public_dataset(config_path=config_path)
    release_dir = Path(summary["release_dir"])

    assert summary["ok"] is True
    assert summary["row_count"] == 3
    assert (release_dir / "data.parquet").exists()
    assert (release_dir / "schema.json").exists()
    assert (release_dir / "manifest.json").exists()
    assert (release_dir / "README.md").exists()
    assert (release_dir / "DATASET_CARD.md").exists()
    assert (release_dir / "ATTRIBUTION.md").exists()
    assert (release_dir / "field_release_policy.json").exists()
    assert (release_dir / "source_attribution.json").exists()
    assert (release_dir / "kaggle_metadata.template.json").exists()
    assert (release_dir / "data_quality_summary.json").exists()
    assert (release_dir / "checksums.txt").exists()

    frame = pd.read_parquet(release_dir / "data.parquet")
    assert frame["canonical_id"].tolist() == ["paper-a", "paper-b", "paper-c"]
    assert frame.loc[1, "abstract"] is None
    assert "embedding_vector" not in frame.columns
    assert "raw_provider_payload" not in frame.columns
    assert list(frame.loc[0, "source_families"]) == [
        "arxiv",
        "crossref_alignment",
        "openalex_alignment",
    ]
    assert isinstance(frame.loc[0, "provenance_summary"], str)
    assert isinstance(frame.loc[0, "external_ids_summary"], str)

    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["publication_status"] == "not_published"
    assert manifest["manual_review_required_before_publication"] is True
    assert manifest["safety"]["canonical_truth_impact"] == "none"
    assert manifest["source_checkpoint"]["actual_exported_row_count"] == 3
    assert manifest["schema_version"] == "dataset_release_manifest_v2"
    assert manifest["public_release_policy"]["publication_action_in_scope"] is False
    assert manifest["files"]["data_quality_summary"] == "data_quality_summary.json"

    quality_summary = json.loads((release_dir / "data_quality_summary.json").read_text(encoding="utf-8"))
    assert quality_summary["schema_version"] == "dataset_release_data_quality_summary_v1"
    assert quality_summary["row_count"] == 3
    assert quality_summary["column_count"] == len(frame.columns)
    assert quality_summary["canonical_id"]["unique_count"] == 3
    assert quality_summary["canonical_id"]["duplicate_count"] == 0
    assert quality_summary["field_coverage"]["abstract"]["non_empty_count"] == 1
    assert quality_summary["public_release_policy"]["field_transformations"]["abstract_excluded_by_policy_count"] == 1
    assert quality_summary["year_range"] == {"min": 2014, "max": 2026}
    assert quality_summary["source_family_counts"]["arxiv"] == 2

    checks = validate_release_output(config, config_path=config_path, release_dir=release_dir)
    assert required_failures(checks) == set()


def test_export_refuses_to_overwrite_non_empty_release_dir_without_force(tmp_path: Path) -> None:
    _config, config_path = make_config(tmp_path)
    export_public_dataset(config_path=config_path)

    with pytest.raises(FileExistsError):
        export_public_dataset(config_path=config_path)


def test_export_force_rewrites_existing_release_dir(tmp_path: Path) -> None:
    _config, config_path = make_config(tmp_path)
    summary = export_public_dataset(config_path=config_path)
    release_dir = Path(summary["release_dir"])
    extra_file = release_dir / "temporary.txt"
    extra_file.write_text("stale", encoding="utf-8")

    export_public_dataset(config_path=config_path, force=True)

    assert not extra_file.exists()
    assert (release_dir / "data.parquet").exists()
