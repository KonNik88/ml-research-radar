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
    assert "docs/scientific_entity_literal_baseline_pilot_evaluation_v0.1.md" in text
    assert "docs/scientific_entity_gliner_candidate_adapter_v0.1.md" in text
    assert "docs/scientific_entity_gliner_pilot_comparison_v0.1.md" in text
    assert "docs/scientific_entity_gliner_dev_calibration_v0.1.md" in text
    assert "docs/scientific_entity_gliner_dev_policy_review_v0.1.md" in text
    assert "completed 24-paper review" in text


def test_roadmap_advances_after_real_calibration_and_policy_freeze() -> None:
    text = _read("docs/roadmap.md")

    assert "current active direction = Scientific Entity Evidence Layer" in text
    assert (
        "latest completed slice = Scientific Entity GLiNER Dev Policy Review v0.1"
    ) in text
    assert (
        "next authorized slice = materialize frozen GLiNER dev policy as a new "
        "immutable candidate build and evaluation"
    ) in text
    assert "Scientific Entity Evidence Contract v0.1" in text
    assert "hard max documents = 100" in text
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
    assert "Scientific Entity Evaluation Harness v0.1" in text
    assert "Bounded Scientific Entity Manual Review Evidence v0.1" in text
    assert "scientific_entity_real_review_complete = true_bounded_local_pilot" in text
    assert (
        "scientific_entity_pilot_evaluation_id = "
        "scientific-entity-evaluation-v0.1-20260822T114935748579Z"
    ) in text
    assert "scheduler orchestration / Airflow" in text


def test_bounded_entity_baseline_is_documented_without_runtime_promotion() -> None:
    readme = _read("README.md")
    checkpoint = _read("docs/project_state_current_v0.2.md")
    baseline = _read("docs/scientific_entity_extractor_baseline_v0.1.md")

    assert "scientific entity status = bounded literal control" in readme
    assert "Bounded Scientific Entity Extractor Baseline | implemented" in checkpoint
    assert "default_max_documents = 32" in baseline
    assert "hard_max_documents = 100" in baseline
    assert "full_corpus_authorized = false" in baseline
    assert "production_model_selected = false" in baseline


def test_scientific_entity_evaluation_harness_is_descriptive_and_bounded() -> None:
    readme = _read("README.md")
    checkpoint = _read("docs/project_state_current_v0.2.md")
    evaluation = _read("docs/scientific_entity_evaluation_harness_v0.1.md")

    assert "Scientific Entity Evaluation Harness v0.1 — implemented." in readme
    assert "Scientific Entity Evaluation Harness | implemented" in checkpoint
    assert "minimum character IoU = 0.5" in evaluation
    assert "promotion_sample_sufficient = false" in evaluation
    assert "production_extractor_selected = false" in evaluation
    assert "full_corpus_build_authorized = false" in evaluation
    assert "Bounded Scientific Entity Manual Review Evidence v0.1" in evaluation


def test_manual_review_fixture_is_distinguished_from_completed_real_pilot() -> None:
    readme = _read("README.md")
    checkpoint = _read("docs/project_state_current_v0.2.md")
    contract = _read("docs/scientific_entity_manual_review_evidence_v0.1.md")
    config = _read("configs/scientific_entity_manual_review_evidence_v0.1.yaml")

    assert (
        "Bounded Scientific Entity Manual Review Evidence v0.1 — implemented."
        in readme
    )
    assert "Bounded Scientific Entity Manual Review Evidence | implemented" in checkpoint
    assert "real_paper_review_complete = false" in contract
    assert "prediction_blind = true" in contract
    assert "fixture reference mentions = 6" in contract
    assert "independent completed-package checks = 118 / 118" in contract
    assert "uniform_document_count: 12" in config
    assert "type_enriched_documents_per_type: 2" in config
    assert "automatic_review_approval_allowed: false" in config
    assert "full_corpus_entity_extraction_allowed: false" in config
    assert (
        "scientific entity real review complete = true (bounded local pilot/dev evidence)"
        in checkpoint
    )
    assert "scientific entity production model selected = false" in checkpoint


def test_docs_do_not_reassert_an_unverified_current_source_document_count() -> None:
    checkpoint = _read("docs/project_state_current_v0.2.md")
    architecture = _read("docs/architecture.md")

    assert "current source_documents count = not reasserted" in checkpoint
    assert "current_source_documents_count = not reasserted" in architecture


def test_gliner_candidate_is_pinned_bounded_and_not_promoted() -> None:
    readme = _read("README.md")
    checkpoint = _read("docs/project_state_current_v0.2.md")
    architecture = _read("docs/architecture.md")
    adapter = _read("docs/scientific_entity_gliner_candidate_adapter_v0.1.md")
    config = _read("configs/scientific_entity_gliner_candidate_v0.1.yaml")

    assert "Bounded GLiNER Candidate Extractor Adapter v0.1 — implemented" in readme
    assert "Bounded Scientific Entity GLiNER Candidate Adapter | implemented" in checkpoint
    assert (
        "scientific_entity_gliner_adapter_status = "
        "implemented_bounded_candidate_build_validated"
    ) in architecture
    assert "gliner-community/gliner_small-v2.5" in adapter
    assert "f227d3cd637bd4e6757ae143935316d062393341" in adapter
    assert "d444ff406b27affc07e3165b454c3adc9f25f228c81ede197a7b806f49d12c74" in adapter
    assert "microsoft/deberta-v3-small" in adapter
    assert "a36c739020e01763fe789b4b85e2df55d6180012" in adapter
    assert "b0bb1caf90a50aa67d1085130508dfbf8646ac5a11928305e280b07a36e100ae" in adapter
    assert "verified local config injection" in adapter
    assert "scientific-entity-gliner-small-v2.5-v0.1-20260822T143405630144Z" in adapter
    assert "mentions = 546" in adapter
    assert "independent build validation = 91 / 91 required checks" in adapter
    assert "hard maximum documents = 100" in adapter
    assert "production extractor selected = false" in adapter
    assert "model_download_requires_explicit_flag: true" in config
    assert "require_backbone_config_hash: true" in config
    assert "accepted_status_may_be_emitted: false" in config


def test_gliner_comparison_is_recorded_without_promotion() -> None:
    readme = _read("README.md")
    checkpoint = _read("docs/project_state_current_v0.2.md")
    architecture = _read("docs/architecture.md")
    comparison = _read("docs/scientific_entity_gliner_pilot_comparison_v0.1.md")

    assert "Scientific Entity GLiNER Pilot Comparison v0.1 — completed." in readme
    assert "Scientific Entity GLiNER Pilot Comparison | completed" in checkpoint
    assert (
        "scientific_entity_gliner_comparison_status = "
        "completed_descriptive_pilot_dev_checkpoint"
    ) in architecture
    assert (
        "gliner_evaluation_id = "
        "scientific-entity-evaluation-v0.1-20260823T124036780234Z"
    ) in comparison
    assert (
        "| GLiNER v0.1 | Exact | 176 | 370 | 259 | 0.322344 | 0.404598 | "
        "0.358817 |"
    ) in comparison
    assert (
        "| GLiNER v0.1 | Relaxed | 195 | 351 | 240 | 0.357143 | 0.448276 | "
        "0.397554 |"
    ) in comparison
    assert "production_extractor_selected = false" in comparison
    assert "full_corpus_build_authorized = false" in comparison


def test_gliner_dev_calibration_is_bounded_and_not_probabilistic() -> None:
    readme = _read("README.md")
    checkpoint = _read("docs/project_state_current_v0.2.md")
    architecture = _read("docs/architecture.md")
    calibration = _read("docs/scientific_entity_gliner_dev_calibration_v0.1.md")
    config = _read("configs/scientific_entity_gliner_dev_calibration_v0.1.yaml")

    assert (
        "Bounded Scientific Entity GLiNER Dev Calibration v0.1 — implemented and "
        "real candidate execution validated."
    ) in readme
    assert (
        "Bounded Scientific Entity GLiNER Dev Calibration | real candidate execution "
        "complete; strict validation green"
        in checkpoint
    )
    assert (
        "scientific_entity_gliner_calibration_tooling_status = "
        "implemented_fixture_validated"
    ) in architecture
    assert "exactly 127 trials" in calibration
    assert "confidence_kind = model_score" in calibration
    assert "calibration_id = null" in calibration
    assert "full source_field × entity_type Cartesian policy search" in calibration
    assert "real 24-paper candidate execution = complete" in calibration
    assert "real calibration strict validation = 53 / 53 required checks" in calibration
    assert "dev policy review = complete / balanced_f1 selected" in calibration
    assert "docs/scientific_entity_gliner_dev_policy_review_v0.1.md" in calibration
    assert "model_inference_allowed: false" in config
    assert "combined_type_specific_policy_selection_allowed: false" in config
    assert "full_source_field_by_type_cartesian_search_allowed: false" in config
    assert "promotion_verdict_allowed: false" in config
    assert "full_corpus_build_authorized: false" in config


def test_gliner_dev_policy_review_freezes_one_bounded_policy() -> None:
    review = _read("docs/scientific_entity_gliner_dev_policy_review_v0.1.md")
    checkpoint = _read("docs/project_state_current_v0.2.md")
    architecture = _read("docs/architecture.md")

    assert "calibration_id = scientific-entity-gliner-dev-calibration-v0.1-20260823T152930597192Z" in review
    assert "strict_validator = 53 / 53 required checks" in review
    assert "selected_profile = balanced_f1" in review
    assert "selected_trial_id = calibration-trial:1172aea9d875d59f3b39cc21488dec8f" in review
    assert "selected_title_threshold = 0.55 inclusive" in review
    assert "selected_abstract_threshold = 0.65 inclusive" in review
    assert "selected_entity_type_thresholds = none" in review
    assert "selected_dev_policy_frozen = true" in review
    assert "production_extractor_selected = false" in review
    assert "full_corpus_build_authorized = false" in review
    assert "current_24_paper_dev_set_becomes_held_out = false" in review
    assert "exact F1 from `0.358817` to `0.380146`" in review
    assert "scientific entity GLiNER frozen dev policy = balanced_f1 / title 0.55 / abstract 0.65 / no type overrides" in checkpoint
    assert "scientific_entity_gliner_dev_policy_frozen = true" in architecture
