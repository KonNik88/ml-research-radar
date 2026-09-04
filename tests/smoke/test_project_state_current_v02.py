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
    assert "docs/scientific_entity_gliner_heldout_evaluation_v0.1.md" in text
    assert "docs/scientific_entity_heldout_error_analysis_v0.1.md" in text
    assert "docs/scientific_entity_semantic_prompt_candidate_v0.2a.md" in text
    assert "docs/scientific_entity_semantic_prompt_threshold_calibration_v0.2b.md" in text
    assert "current scientific entity checkpoint = Scientific Entity Fresh v0.2 Reference Evidence Freeze" in text
    assert "completed 24-paper review" in text


def test_roadmap_advances_after_real_calibration_and_policy_freeze() -> None:
    text = _read("docs/roadmap.md")

    assert "current active direction = Scientific Entity Evidence Layer" in text
    assert (
        "latest completed slice = Scientific Entity Fresh v0.2 Reference Evidence Freeze"
    ) in text
    assert (
        "next authorized slice = Scientific Entity Frozen v0.2c Raw Inference — Exactly Once"
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


def test_scientific_entity_heldout_gate_is_recorded_as_bounded_acceptance() -> None:
    readme = _read("README.md")
    checkpoint = _read("docs/project_state_current_v0.2.md")
    architecture = _read("docs/architecture.md")
    roadmap = _read("docs/roadmap.md")
    heldout = _read("docs/scientific_entity_gliner_heldout_evaluation_v0.1.md")

    assert "Scientific Entity GLiNER Held-Out Evaluation v0.1" in readme
    assert "scientific-entity-heldout-review-v0.1-20260827T092900455472Z" in heldout
    assert "scientific-entity-evaluation-v0.1-20260827T113112815887Z" in heldout
    assert "reference package validator = 4444 / 4444 required checks" in heldout
    assert "raw predictions = 1145" in heldout
    assert "selected predictions = 787" in heldout
    assert "policy build validator = 4762 / 4762 required checks" in heldout
    assert "| Exact | 331 | 456 | 550 | 0.420584 | 0.375709 | 0.396882 |" in heldout
    assert "| Relaxed | 346 | 441 | 535 | 0.439644 | 0.392736 | 0.414868 |" in heldout
    assert "metric | 0.250000 | 0.180851 | 0.209877" in heldout
    assert "domain | 0.280000 | 0.308824 | 0.293707" in heldout
    assert "model -> method = 55" in heldout
    assert "method -> task = 28" in heldout
    assert "candidate_decision = accept_as_bounded_working_extractor_v0.1" in heldout
    assert "production_extractor_selected = false" in heldout
    assert "full_corpus_build_authorized = false" in heldout
    assert "scientific_entity_heldout_generalization_gate = passed" in architecture


def test_scientific_entity_heldout_error_analysis_records_final_diagnosis() -> None:
    readme = _read("README.md")
    checkpoint = _read("docs/project_state_current_v0.2.md")
    roadmap = _read("docs/roadmap.md")
    analysis = _read("docs/scientific_entity_heldout_error_analysis_v0.1.md")

    assert "scientific-entity-heldout-error-analysis-v0.1-20260828T121239202063Z" in analysis
    assert "strict_validator = 398 / 398 required checks" in analysis
    assert "model -> method = 55" in analysis
    assert "method -> task = 28" in analysis
    assert "method_semantic_sink = 94 / 176 type mismatches = 0.534091" in analysis
    assert "uncovered_splitter_token_count = 0" in analysis
    assert "window_exceeds_model_max_len_count = 0" in analysis
    assert "reference_mentions_exceeding_model_max_width_count = 5" in analysis
    assert "markup_like_reference_mention_count = 5" in analysis
    assert "wide_reference_set == markup_like_reference_set = true" in analysis
    assert "Scientific Entity Semantic Prompt Candidate v0.2a" in analysis
    assert "future v0.2 independent acceptance = requires a new disjoint held-out sample" in analysis
    assert "Scientific Entity Held-Out Error Analysis | completed diagnostic decision checkpoint" in checkpoint


def test_scientific_entity_semantic_prompt_v02a_is_closed_without_posthoc_promotion() -> None:
    readme = _read("README.md")
    checkpoint = _read("docs/project_state_current_v0.2.md")
    roadmap = _read("docs/roadmap.md")
    candidate = _read("docs/scientific_entity_semantic_prompt_candidate_v0.2a.md")

    assert "Scientific Entity Semantic Prompt Candidate v0.2a — completed; hard gate failed." in readme
    assert "scientific-entity-semantic-prompt-development-v0.2a-20260829T140201009151Z" in candidate
    assert "scientific-entity-gliner-small-v2.5-v0.1-20260829T141340564165Z" in candidate
    assert "scientific-entity-semantic-prompt-policy-v0.2a-20260829T143901678616Z" in candidate
    assert "scientific-entity-semantic-prompt-comparison-v0.2a-20260829T145954260189Z" in candidate
    assert "reference_mention_count = 1316" in candidate
    assert "candidate_prediction_count = 977" in candidate
    assert "| minimum overall exact F1 | `>= 0.386882` | `0.383706` | **FAIL** |" in candidate
    assert "| maximum `model -> method` | `<= 44` | `31` | PASS |" in candidate
    assert "| maximum `method -> task` | `<= 28` | `21` | PASS |" in candidate
    assert "| maximum total type mismatches | `<= 176` | `125` | PASS |" in candidate
    assert "| maximum method semantic sink | `<= 84` | `54` | PASS |" in candidate
    assert "candidate_promising_for_next_development_slice = false" in candidate
    assert "candidate_accepted = false" in candidate
    assert "production_extractor_selected = false" in candidate
    assert "full_corpus_build_authorized = false" in candidate
    assert "model -> method: 55 -> 31" in candidate
    assert "method -> task: 28 -> 21" in candidate
    assert "all type mismatches: 176 -> 125" in candidate
    assert "method semantic sink: 94 -> 54" in candidate
    assert "Scientific Entity Semantic Prompt Threshold Calibration v0.2b" in candidate
    assert "scientific entity v0.2a decision = hard gate failed" in checkpoint


def test_scientific_entity_semantic_prompt_threshold_v02b_is_closed_without_gate_relaxation() -> None:
    readme = _read("README.md")
    checkpoint = _read("docs/project_state_current_v0.2.md")
    roadmap = _read("docs/roadmap.md")
    calibration = _read(
        "docs/scientific_entity_semantic_prompt_threshold_calibration_v0.2b.md"
    )

    assert (
        "Scientific Entity Semantic Prompt Threshold Calibration v0.2b — "
        "completed; hard gate failed."
    ) in readme
    assert (
        "scientific-entity-semantic-prompt-threshold-calibration-v0.2b-"
        "20260830T093225845167Z"
    ) in calibration
    assert "trials = 35" in calibration
    assert "semantic-safe eligible trials = 10" in calibration
    assert "selected title threshold = 0.50" in calibration
    assert "selected abstract threshold = 0.625" in calibration
    assert "selected combined-72 exact F1 = 0.398654" in calibration
    assert "selected consumed-48 exact F1 = 0.396453" in calibration
    assert "difference = -0.000429" in calibration
    assert "selected model -> method = 32" in calibration
    assert "selected method -> task = 25" in calibration
    assert "selected total type mismatches = 138" in calibration
    assert "selected method semantic sink = 57" in calibration
    assert "raw_input_floor_may_be_binding = true" in calibration
    assert "strict validator = 53 / 53" in calibration
    assert "candidate accepted = false" in calibration
    assert "production_extractor_selected = false" in calibration
    assert "full_corpus_build_authorized = false" in calibration
    assert "| 0.600 | no | 0.400654 | 0.401227" in calibration
    assert "| 0.625 | yes | 0.398654 | 0.396453" in calibration
    assert "method -> task <= 25" in calibration
    assert "Scientific Entity Semantic Prompt Raw-Floor Extension v0.2c" in calibration

    # v0.2b is historical evidence; living current-state may advance independently.
    assert "scientific entity v0.2b decision = hard gate failed" in checkpoint
    assert (
        "57. **Scientific Entity Semantic Prompt Threshold Calibration v0.2b**"
    ) in roadmap

def test_scientific_entity_semantic_prompt_raw_floor_v02c_development_freeze_is_preserved() -> None:
    checkpoint = _read("docs/project_state_current_v0.2.md")
    roadmap = _read("docs/roadmap.md")
    extension = _read("docs/scientific_entity_semantic_prompt_raw_floor_extension_v0.2c.md")
    calibration = _read("docs/scientific_entity_semantic_prompt_raw_floor_calibration_v0.2c.md")
    policy = _read("docs/scientific_entity_semantic_prompt_raw_floor_policy_v0.2c.md")
    comparison = _read("docs/scientific_entity_semantic_prompt_raw_floor_comparison_v0.2c.md")

    assert "raw predictions = 1762" in extension
    assert "strict build validation = 91 / 91" in extension
    assert (
        "calibration_id = scientific-entity-semantic-prompt-raw-floor-calibration-"
        "v0.2c-20260830T104242195583Z"
    ) in calibration
    assert (
        "selected trial = calibration-trial:adcd020d8bce5af1ff157f4303e0b171"
    ) in calibration
    assert "title = 0.45" in calibration
    assert "abstract = 0.625" in calibration
    assert "combined exact F1 = 0.403677" in calibration
    assert "consumed-48 exact F1 = 0.400000" in calibration
    assert "strict validation = 61 / 61" in calibration
    assert (
        "build_id = scientific-entity-semantic-prompt-raw-floor-policy-v0.2c-"
        "20260830T105318817514Z"
    ) in policy
    assert "selected predictions = 1077" in policy
    assert "strict validation = 48 / 48" in policy
    assert (
        "comparison_id = scientific-entity-semantic-prompt-raw-floor-comparison-"
        "v0.2c-20260830T110628936475Z"
    ) in comparison
    assert "old-dev-24 exact F1 = 0.410959" in comparison
    assert "consumed-48 relaxed F1 = 0.422642" in comparison
    assert "candidate_ready_for_development_freeze = true" in comparison
    assert "strict validation = 45 / 45" in comparison
    assert "No production extractor is selected" in comparison
    assert "no full-corpus build is authorized" in comparison

    # v0.2c remains immutable historical evidence after the living checkpoint advances.
    assert "scientific entity v0.2c decision = development gates passed" in checkpoint
    assert (
        "58. **Scientific Entity Semantic Prompt Raw-Floor Candidate v0.2c**"
    ) in roadmap

def test_scientific_entity_fresh_v02_heldout_gate_design_is_preserved() -> None:
    checkpoint = _read("docs/project_state_current_v0.2.md")
    roadmap = _read("docs/roadmap.md")
    gate = _read("docs/scientific_entity_fresh_heldout_gate_v0.2.md")

    assert "sample selected = false" in gate
    assert "fresh held-out consumed = false" in gate
    assert "documents = 48" in gate
    assert "uniform = 24" in gate
    assert "type-enriched = 24" in gate
    assert "development overlap = 0" in gate
    assert "minimum reference mentions per type = 20" in gate
    assert "exact F1 >= 0.396882" in gate
    assert "desirable relaxed F1 >= 0.414868" in gate
    assert "model -> method <= 43" in gate
    assert "method -> task <= 25" in gate
    assert "total type mismatches <= 150" in gate
    assert "production extractor selected = false" in gate
    assert "full-corpus build authorized = false" in gate

    assert "scientific entity fresh v0.2 heldout gate = design frozen" in checkpoint
    assert "59. **Scientific Entity Fresh v0.2 Held-Out Gate Design Freeze**" in roadmap


def test_scientific_entity_fresh_v02_heldout_sample_materialization_is_preserved() -> None:
    readme = _read("README.md")
    checkpoint = _read("docs/project_state_current_v0.2.md")
    roadmap = _read("docs/roadmap.md")
    sample = _read("docs/scientific_entity_fresh_heldout_sample_v0.2.md")


    assert "status = materialized and strictly validated" in sample
    assert "sample_id = scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z" in sample
    assert "review_id = scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z" in sample
    assert "canonical input rows = 61075" in sample
    assert "eligible non-development documents = 60997" in sample
    assert "excluded consumed development documents = 72 / 72" in sample
    assert "held-out/development overlap = 0" in sample
    assert "uniform documents = 24" in sample
    assert "type-enriched documents = 24" in sample
    assert "selected documents = 48" in sample
    assert "annotation rows = 96" in sample
    assert "selected canonical IDs SHA-256 = 0c4bf55fa47192d8523a5ccd0d89b3326562ff6b464f108d330d87286feb7d7a" in sample
    assert "strict independent validation = 43 / 43" in sample
    assert "required failures = 0" in sample
    assert "prediction blind = true" in sample
    assert "candidate predictions read during sampling = false" in sample
    assert "model inference executed = false" in sample
    assert "evaluation executed = false" in sample
    assert "fresh held-out reference consumed = false" in sample
    assert "production extractor selected = false" in sample
    assert "full-corpus build authorized = false" in sample

def test_scientific_entity_fresh_v02_reference_evidence_freeze_is_current() -> None:
    readme = _read("README.md")
    checkpoint = _read("docs/project_state_current_v0.2.md")
    roadmap = _read("docs/roadmap.md")
    reference = _read("docs/scientific_entity_fresh_heldout_reference_freeze_v0.2.md")

    assert "current scientific entity checkpoint = Scientific Entity Fresh v0.2 Reference Evidence Freeze" in readme
    assert "current_extension = Scientific Entity Fresh v0.2 Reference Evidence Freeze" in checkpoint
    assert "latest completed slice = Scientific Entity Fresh v0.2 Reference Evidence Freeze" in roadmap
    assert "next authorized slice = Scientific Entity Frozen v0.2c Raw Inference — Exactly Once" in roadmap
    assert "next entity slice = Scientific Entity Frozen v0.2c Raw Inference — Exactly Once" in checkpoint

    assert "status = reference evidence frozen and strictly validated" in reference
    assert "sample_id = scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z" in reference
    assert "review_id = scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z" in reference
    assert "selected canonical IDs SHA-256 = 0c4bf55fa47192d8523a5ccd0d89b3326562ff6b464f108d330d87286feb7d7a" in reference
    assert "documents = 48" in reference
    assert "annotation rows = 96" in reference
    assert "completed annotation rows = 96" in reference
    assert "reference mentions = 944" in reference
    assert "uncertain reference mentions = 0" in reference
    assert "minimum reference mentions per type = 20" in reference
    assert "task = 150" in reference
    assert "method = 279" in reference
    assert "dataset = 66" in reference
    assert "metric = 86" in reference
    assert "model = 280" in reference
    assert "domain = 83" in reference
    assert "reference adequacy = passed" in reference
    assert "strict reference validator = 44 / 44" in reference
    assert "required failures = 0" in reference
    assert "prediction blind = true" in reference
    assert "candidate predictions visible during annotation = false" in reference
    assert "model inference executed = false" in reference
    assert "candidate evaluation executed = false" in reference
    assert "production extractor selected = false" in reference
    assert "full-corpus build authorized = false" in reference
    assert "next = run_frozen_v02c_raw_inference_once" in reference

    assert "61. **Scientific Entity Fresh v0.2 Prediction-Blind Reference Freeze Tooling**" in roadmap
    assert "62. **Scientific Entity Fresh v0.2 Reference Evidence Freeze**" in roadmap

