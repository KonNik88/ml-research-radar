from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from radar_core.contracts.scientific_entity_evidence import ScientificEntityType
from radar_core.contracts.scientific_entity_semantic_typer_candidate import (
    SemanticTyperDevelopmentCase,
    SemanticTyperPrediction,
    load_semantic_typer_config,
    semantic_typer_config_sha256,
)
from radar_core.entities.scientific_entity_gliner import PreparedText
from radar_core.entities.scientific_entity_semantic_typer import semantic_typer_fingerprint
from radar_core.entities.scientific_entity_semantic_typer_candidate_inference import (
    plan_or_execute_semantic_typer_candidate_inference,
    validate_semantic_typer_candidate_predictions,
)
from radar_core.entities.scientific_entity_semantic_typer_evaluation import (
    evaluate_candidate,
    plan_or_execute_semantic_typer_development_evaluation,
    validate_semantic_typer_development_evaluation,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_candidate_v0.3.yaml"


class FakeBackend:
    model_max_tokens = 384
    model_max_width = 12

    def prepare_text(self, text: str, labels: Sequence[str]) -> PreparedText:
        del labels
        matches = list(re.finditer(r"\w+|[^\w\s]", text, flags=re.UNICODE))
        return PreparedText(
            tokens=tuple(match.group(0) for match in matches),
            token_starts=tuple(match.start() for match in matches),
            token_ends=tuple(match.end() for match in matches),
        )

    def predict_entities(self, text: str, labels: Sequence[str], *, threshold: float, flat_ner: bool, multi_label: bool) -> Sequence[Mapping[str, Any]]:
        assert threshold == 0.0 and flat_ner is False and multi_label is True
        start = len("Target entity: ")
        end = text.index("\n", start)
        surface = text[start:end]
        # Frozen canonical prompt order: task, method, dataset, metric, model, domain.
        scores = [0.10, 0.20, 0.15, 0.12, 0.95, 0.11]
        return [
            {"start": start, "end": end, "text": surface, "label": label, "score": score}
            for label, score in zip(labels, scores)
        ]


def _case(index: int, *, reference: ScientificEntityType = ScientificEntityType.MODEL, baseline: ScientificEntityType = ScientificEntityType.METHOD, eligible: bool = True) -> SemanticTyperDevelopmentCase:
    return SemanticTyperDevelopmentCase(
        case_id=f"semantic-typer-dev-case:{index}",
        evaluation_id="scientific-entity-evaluation-fresh-v0.2c-20260901T130232963026Z",
        canonical_id=f"paper-{index}",
        source_field="abstract",
        source_text_sha256=f"{index % 10}" * 64,
        reference_id=f"reference:{index}",
        baseline_prediction_evidence_id=f"evidence:{index}",
        char_start=0,
        char_end=4,
        surface_text="BERT",
        reference_entity_type=reference,
        baseline_entity_type=baseline,
        baseline_correct=reference == baseline,
        baseline_confidence_score=0.9,
        left_context="We use ",
        right_context=" for classification.",
        root_cause=None if reference == baseline else "clear_semantic_mistyping",
        ambiguity_level=None if reference == baseline else "none",
        reference_type_confirmed=True,
        primary_metric_eligible=eligible,
    )


def _prediction(case: SemanticTyperDevelopmentCase, predicted: ScientificEntityType, *, fallback: bool = False) -> SemanticTyperPrediction:
    if fallback:
        return SemanticTyperPrediction(
            case_id=case.case_id,
            candidate_id="scientific-entity-semantic-typer-candidate-v0.3-h1",
            predicted_entity_type=predicted,
            used_baseline_fallback=True,
            selected_score=None,
            second_best_entity_type=None,
            second_best_score=None,
            score_margin=None,
            scored_type_count=0,
            per_type_scores={},
            synthetic_text_sha256="a" * 64,
            context_trimmed=False,
        )
    return SemanticTyperPrediction(
        case_id=case.case_id,
        candidate_id="scientific-entity-semantic-typer-candidate-v0.3-h1",
        predicted_entity_type=predicted,
        used_baseline_fallback=False,
        selected_score=0.9,
        second_best_entity_type=ScientificEntityType.METHOD if predicted != ScientificEntityType.METHOD else ScientificEntityType.MODEL,
        second_best_score=0.2,
        score_margin=0.7,
        scored_type_count=1,
        per_type_scores={predicted: 0.9},
        synthetic_text_sha256="a" * 64,
        context_trimmed=False,
    )


def _write_dev_package(path: Path, cases: Sequence[SemanticTyperDevelopmentCase]) -> None:
    path.mkdir(parents=True)
    data = "".join(json.dumps(row.model_dump(mode="json"), separators=(",", ":")) + "\n" for row in cases).encode()
    (path / "development_cases.jsonl").write_bytes(data)
    config = load_semantic_typer_config(CONFIG)
    manifest = {
        "package_id": "scientific-entity-semantic-typer-development-v0.3-fixture",
        "semantic_typer_candidate_id": config.candidate.candidate_id,
        "semantic_typer_config_sha256": semantic_typer_config_sha256(config),
        "semantic_typer_fingerprint": semantic_typer_fingerprint(config),
        "development_case_count": len(cases),
        "development_cases_sha256": hashlib.sha256(data).hexdigest(),
        "model_inference_executed": False,
    }
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_inference_plan_is_non_writing_and_does_not_load_backend(tmp_path: Path) -> None:
    package = tmp_path / "dev"
    _write_dev_package(package, [_case(1)])
    report = plan_or_execute_semantic_typer_candidate_inference(
        project_root=ROOT,
        config_path=CONFIG,
        package_dir=package,
        output_root=tmp_path / "predictions",
        prediction_id="pred-fixture",
        execute=False,
    )
    assert report["phase_complete"] is False
    assert report["model_inference_executed"] is False
    assert report["case_count"] == 1
    assert not (tmp_path / "predictions" / "pred-fixture").exists()


def test_inference_execute_and_strict_validator_roundtrip(tmp_path: Path) -> None:
    package = tmp_path / "dev"
    _write_dev_package(package, [_case(1)])
    report = plan_or_execute_semantic_typer_candidate_inference(
        project_root=ROOT,
        config_path=CONFIG,
        package_dir=package,
        output_root=tmp_path / "predictions",
        prediction_id="pred-fixture",
        execute=True,
        backend=FakeBackend(),
        generated_at_utc=datetime(2026, 9, 16, tzinfo=timezone.utc),
    )
    assert report["phase_complete"] is True
    assert report["model_inference_executed"] is True
    assert report["typer_coverage"] == 1.0
    prediction_dir = tmp_path / "predictions" / "pred-fixture"
    checks, summary = validate_semantic_typer_candidate_predictions(
        project_root=ROOT,
        config_path=CONFIG,
        package_dir=package,
        prediction_dir=prediction_dir,
    )
    assert summary["required_failed_count"] == 0, [row for row in checks if not row[1]]


def test_development_decision_freezes_only_when_all_predeclared_gates_pass() -> None:
    config = load_semantic_typer_config(CONFIG)
    entity_types = list(ScientificEntityType)
    cases = []
    predictions = []
    for index, reference in enumerate(entity_types, start=1):
        baseline = ScientificEntityType.METHOD if reference != ScientificEntityType.METHOD else ScientificEntityType.TASK
        case = _case(index, reference=reference, baseline=baseline)
        cases.append(case)
        predictions.append(_prediction(case, reference))
    summary, _, _ = evaluate_candidate(cases, predictions, config)
    assert summary["net_corrected_cases"] == 6
    assert summary["decision"]["all_gates_passed"] is True
    assert summary["decision"]["decision"] == "freeze_for_independent_acceptance"


def test_development_decision_revises_positive_but_under_gate_candidate() -> None:
    config = load_semantic_typer_config(CONFIG)
    cases = [_case(1), _case(2, reference=ScientificEntityType.DATASET, baseline=ScientificEntityType.METHOD)]
    predictions = [_prediction(cases[0], ScientificEntityType.MODEL), _prediction(cases[1], ScientificEntityType.METHOD)]
    summary, _, _ = evaluate_candidate(cases, predictions, config)
    assert summary["net_corrected_cases"] == 1
    assert summary["decision"]["all_gates_passed"] is False
    assert summary["decision"]["decision"] == "revise_candidate"


def test_development_decision_rejects_candidate_without_positive_net_improvement() -> None:
    config = load_semantic_typer_config(CONFIG)
    case = _case(1)
    summary, _, _ = evaluate_candidate([case], [_prediction(case, ScientificEntityType.METHOD)], config)
    assert summary["net_corrected_cases"] == 0
    assert summary["decision"]["decision"] == "reject_candidate"


def test_evaluation_plan_hides_quality_metrics_and_execute_revalidates(tmp_path: Path) -> None:
    package = tmp_path / "dev"
    cases = [_case(1)]
    _write_dev_package(package, cases)
    plan_or_execute_semantic_typer_candidate_inference(
        project_root=ROOT, config_path=CONFIG, package_dir=package,
        output_root=tmp_path / "predictions", prediction_id="pred-fixture", execute=True,
        backend=FakeBackend(), generated_at_utc=datetime(2026, 9, 16, tzinfo=timezone.utc),
    )
    prediction_dir = tmp_path / "predictions" / "pred-fixture"
    plan = plan_or_execute_semantic_typer_development_evaluation(
        project_root=ROOT, config_path=CONFIG, package_dir=package, prediction_dir=prediction_dir,
        output_root=tmp_path / "eval", evaluation_id="eval-fixture", execute=False,
    )
    assert plan["quality_metrics_exposed_in_plan"] is False
    assert "same_span_accuracy_delta" not in plan
    assert plan["development_decision_made"] is False
    report = plan_or_execute_semantic_typer_development_evaluation(
        project_root=ROOT, config_path=CONFIG, package_dir=package, prediction_dir=prediction_dir,
        output_root=tmp_path / "eval", evaluation_id="eval-fixture", execute=True,
        generated_at_utc=datetime(2026, 9, 16, tzinfo=timezone.utc),
    )
    assert report["phase_complete"] is True
    evaluation_dir = tmp_path / "eval" / "eval-fixture"
    checks, summary = validate_semantic_typer_development_evaluation(
        project_root=ROOT, config_path=CONFIG, package_dir=package,
        prediction_dir=prediction_dir, evaluation_dir=evaluation_dir,
    )
    assert summary["required_failed_count"] == 0, [row for row in checks if not row[1]]
