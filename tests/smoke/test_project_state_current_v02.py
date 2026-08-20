from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_current_state_checkpoint_pins_current_and_historical_counts() -> None:
    text = _read("docs/project_state_current_v0.2.md")

    assert "pre_promotion_baseline_doc_count = 60,954" in text
    assert "current_canonical_latest_doc_count = 61,075" in text
    assert "canonical_multisource_docs = 9,226" in text
    assert "retrieval_build_id = 20260818T105227Z" in text


def test_current_state_checkpoint_preserves_truth_and_publication_boundaries() -> None:
    text = _read("docs/project_state_current_v0.2.md")

    assert "No derived identity may redefine `canonical_id`." in text
    assert "Dataset publication remains paused pending explicit redistribution guidance." in text
    assert "Qdrant/graph/dataset outputs at 60,954 = previous build-scoped candidates" in text
    assert "no entity fields added to canonical documents" in text


def test_readme_points_to_the_current_checkpoint_and_scopes_old_outputs() -> None:
    text = _read("README.md")

    assert "docs/project_state_current_v0.2.md" in text
    assert "current canonical latest = 61,075" in text
    assert "retrieval build = 20260818T105227Z" in text
    assert "synchronized to current canonical = false" in text
    assert "recorded local collection currently belongs to the previous 60,954-paper build" in text
    assert "assignments = 61,075" in text


def test_roadmap_selects_contract_first_entity_evidence_direction() -> None:
    text = _read("docs/roadmap.md")

    assert "current active direction = Scientific Entity Evidence Layer" in text
    assert "latest completed slice = Scientific Entity Evidence Contract v0.1" in text
    assert "next authorized slice = Bounded Scientific Entity Extractor Baseline v0.1" in text
    assert "Scientific Entity Evidence Contract v0.1" in text
    assert "no full-corpus entity extraction" in text
    assert "The local phase-based refresh runner is already implemented" in text
    assert "Prior retrieval-serving green checkpoint (60,954 build)" in text


def test_architecture_distinguishes_current_and_build_scoped_layers() -> None:
    text = _read("docs/architecture.md")

    assert "current_canonical_latest_documents = 61075" in text
    assert "retrieval_build_id = 20260818T105227Z" in text
    assert "embeddings_20260818T105227Z.npy" in text
    assert "qdrant_points_count = 60954" in text
    assert "qdrant_baseline_scope = previous experimental build" in text
    assert "refresh_operational_orchestration = implemented_v0.1" in text
    assert "scheduler orchestration / Airflow" in text


def test_docs_do_not_reassert_an_unverified_current_source_document_count() -> None:
    checkpoint = _read("docs/project_state_current_v0.2.md")
    architecture = _read("docs/architecture.md")

    assert "current source_documents count = not reasserted" in checkpoint
    assert "current_source_documents_count = not reasserted" in architecture
