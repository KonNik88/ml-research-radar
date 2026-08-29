from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.contracts.scientific_entity_evaluation import (
    ScientificEntityEvaluationError,
    ScientificEntityEvaluationErrorKind,
    ScientificEntityEvaluationManifest,
    ScientificEntityEvaluationMetrics,
    ScientificEntityPerTypeMetrics,
    ScientificEntityReferenceMention,
    validate_reference_mention,
)
from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntityEvidenceManifest,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    ScientificEntityType,
    validate_mention_evidence,
)
from radar_core.contracts.scientific_entity_semantic_prompt_comparison import (
    COMPARISON_MANIFEST_SCHEMA_VERSION,
    SemanticPromptComparisonConfig,
    SemanticPromptComparisonError,
    load_semantic_prompt_comparison_config,
)
from radar_core.contracts.scientific_entity_semantic_prompt_policy import (
    SemanticPromptPolicyDerivationManifest,
)
from radar_core.entities.scientific_entity_evaluation import (
    ScientificEntityEvaluationConfig,
    evaluate_mentions,
    load_evaluation_config,
)
from radar_core.entities.scientific_entity_semantic_prompt_development import (
    validate_semantic_prompt_development_package,
)
from radar_core.entities.scientific_entity_semantic_prompt_policy import (
    validate_semantic_prompt_policy_build,
)
from radar_core.contracts.scientific_entity_semantic_prompt_candidate import (
    SemanticPromptCandidateConfig,
    load_semantic_prompt_candidate_config,
)


REPORT_NAME = "scientific_entity_semantic_prompt_comparison_v02a"
COMPARISON_SCHEMA_VERSION = "scientific_entity_semantic_prompt_comparison_output_v0.2a"
DIAGNOSTICS_SCHEMA_VERSION = "scientific_entity_semantic_prompt_comparison_diagnostics_v0.2a"
GATE_SCHEMA_VERSION = "scientific_entity_semantic_prompt_gate_decision_v0.2a"
DEFAULT_CONFIG_PATH = Path("configs/scientific_entity_semantic_prompt_comparison_v0.2a.yaml")
REQUIRED_FILES = (
    "manifest.json",
    "comparison.json",
    "diagnostics.json",
    "gate_decision.json",
    "README.md",
    "checksums.txt",
)


class SemanticPromptComparisonBuildError(RuntimeError):
    """Raised when the v0.2a controlled comparison cannot be reproduced safely."""


@dataclass(frozen=True)
class SourceBaseline:
    split: str
    evaluation_dir: Path
    manifest: ScientificEntityEvaluationManifest
    metrics: ScientificEntityEvaluationMetrics
    per_type_metrics: ScientificEntityPerTypeMetrics
    errors: tuple[ScientificEntityEvaluationError, ...]
    references: tuple[ScientificEntityReferenceMention, ...]


@dataclass(frozen=True)
class PreparedComparison:
    report: dict[str, Any]
    manifest: dict[str, Any]
    comparison: dict[str, Any]
    diagnostics: dict[str, Any]
    gate_decision: dict[str, Any]
    readme: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SemanticPromptComparisonBuildError(f"Invalid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SemanticPromptComparisonBuildError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise SemanticPromptComparisonBuildError(
                    f"Blank JSONL line is forbidden: {path}:{line_number}"
                )
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise SemanticPromptComparisonBuildError(
                    f"Invalid JSONL: {path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise SemanticPromptComparisonBuildError(
                    f"Expected JSON object: {path}:{line_number}"
                )
            rows.append(payload)
    return rows


def _resolve(root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def _project_path(root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(resolved).replace("\\", "/")


def _source_text(document: CanonicalDocument, field: ScientificEntitySourceField) -> str:
    value = document.title if field == ScientificEntitySourceField.TITLE else document.abstract
    if not value:
        raise SemanticPromptComparisonBuildError(
            f"Blank source text for {document.canonical_id}:{field.value}"
        )
    return value


def _load_canonical(package_dir: Path) -> tuple[dict[str, CanonicalDocument], dict[str, str]]:
    documents: dict[str, CanonicalDocument] = {}
    for row in _read_jsonl(package_dir / "canonical_documents.jsonl"):
        document = CanonicalDocument.model_validate(row)
        if document.canonical_id in documents:
            raise SemanticPromptComparisonBuildError(
                f"Duplicate canonical_id in development package: {document.canonical_id}"
            )
        documents[document.canonical_id] = document
    membership: dict[str, str] = {}
    for row in _read_jsonl(package_dir / "split_membership.jsonl"):
        canonical_id = str(row.get("canonical_id"))
        split = str(row.get("split"))
        if split not in {"old_dev_24", "consumed_v01_heldout_48"}:
            raise SemanticPromptComparisonBuildError(f"Unexpected split membership: {split}")
        if canonical_id in membership:
            raise SemanticPromptComparisonBuildError(
                f"Duplicate split membership: {canonical_id}"
            )
        membership[canonical_id] = split
    if set(documents) != set(membership):
        raise SemanticPromptComparisonBuildError(
            "Development canonical ids and split membership ids differ"
        )
    return documents, membership


def _verify_sha(path: Path, expected: str, label: str) -> None:
    actual = _sha256_file(path)
    if actual != expected:
        raise SemanticPromptComparisonBuildError(
            f"{label} SHA-256 mismatch: expected={expected} actual={actual}"
        )


def _load_source_baseline(
    *,
    root: Path,
    source_descriptor: Mapping[str, Any],
    documents: Mapping[str, CanonicalDocument],
    expected_ids: set[str],
) -> SourceBaseline:
    split = str(source_descriptor["split"])
    evaluation_dir = _resolve(root, str(source_descriptor["evaluation_dir"]))
    manifest_path = evaluation_dir / "manifest.json"
    manifest = ScientificEntityEvaluationManifest.model_validate(_read_json(manifest_path))
    _verify_sha(
        manifest_path,
        str(source_descriptor["evaluation_manifest_sha256"]),
        f"{split} evaluation manifest",
    )
    if manifest.evaluation_id != source_descriptor["evaluation_id"]:
        raise SemanticPromptComparisonBuildError(f"{split} evaluation_id drifted")

    metrics_path = evaluation_dir / manifest.metrics_file
    per_type_path = evaluation_dir / manifest.per_type_metrics_file
    errors_path = evaluation_dir / manifest.errors_file
    _verify_sha(metrics_path, manifest.metrics_sha256, f"{split} metrics")
    _verify_sha(per_type_path, manifest.per_type_metrics_sha256, f"{split} per-type metrics")
    _verify_sha(errors_path, manifest.errors_sha256, f"{split} errors")

    metrics = ScientificEntityEvaluationMetrics.model_validate(_read_json(metrics_path))
    per_type = ScientificEntityPerTypeMetrics.model_validate(_read_json(per_type_path))
    if metrics.evaluation_id != manifest.evaluation_id or per_type.evaluation_id != manifest.evaluation_id:
        raise SemanticPromptComparisonBuildError(f"{split} metric evaluation_id drifted")

    errors = tuple(
        ScientificEntityEvaluationError.model_validate(row) for row in _read_jsonl(errors_path)
    )
    if len(errors) != manifest.error_count:
        raise SemanticPromptComparisonBuildError(f"{split} error count drifted")

    reference_path = _resolve(root, str(source_descriptor["reference_mentions_path"]))
    _verify_sha(
        reference_path,
        str(source_descriptor["reference_mentions_sha256"]),
        f"{split} references",
    )
    references: list[ScientificEntityReferenceMention] = []
    for row in _read_jsonl(reference_path):
        reference = ScientificEntityReferenceMention.model_validate(row)
        if reference.canonical_id not in expected_ids:
            raise SemanticPromptComparisonBuildError(
                f"{split} reference points outside split: {reference.canonical_id}"
            )
        document = documents[reference.canonical_id]
        references.append(
            validate_reference_mention(
                reference,
                source_text=_source_text(document, reference.source_field),
                review_id=manifest.review.review_id,
            )
        )
    if len(references) != manifest.review.reference_mention_count:
        raise SemanticPromptComparisonBuildError(f"{split} reference count drifted")

    return SourceBaseline(
        split=split,
        evaluation_dir=evaluation_dir,
        manifest=manifest,
        metrics=metrics,
        per_type_metrics=per_type,
        errors=errors,
        references=tuple(references),
    )


def _load_policy_predictions(
    *,
    policy_build_dir: Path,
    documents: Mapping[str, CanonicalDocument],
) -> tuple[ScientificEntityEvidenceManifest, SemanticPromptPolicyDerivationManifest, tuple[ScientificEntityMentionEvidence, ...]]:
    manifest = ScientificEntityEvidenceManifest.model_validate(
        _read_json(policy_build_dir / "manifest.json")
    )
    derivation = SemanticPromptPolicyDerivationManifest.model_validate(
        _read_json(policy_build_dir / "derivation_manifest.json")
    )
    mentions_path = policy_build_dir / manifest.mentions_file
    _verify_sha(mentions_path, manifest.mentions_sha256, "policy mentions")
    mentions: list[ScientificEntityMentionEvidence] = []
    for row in _read_jsonl(mentions_path):
        prediction = ScientificEntityMentionEvidence.model_validate(row)
        document = documents.get(prediction.canonical_id)
        if document is None:
            raise SemanticPromptComparisonBuildError(
                f"Policy prediction outside development package: {prediction.canonical_id}"
            )
        mentions.append(
            validate_mention_evidence(
                prediction,
                source_text=_source_text(document, prediction.source_field),
                extractor=manifest.extractor,
                manifest=manifest,
            )
        )
    if len(mentions) != manifest.mention_count:
        raise SemanticPromptComparisonBuildError("Policy mention count drifted")
    if manifest.build_id != derivation.build_id:
        raise SemanticPromptComparisonBuildError("Policy build/derivation build_id mismatch")
    return manifest, derivation, tuple(mentions)


def _metric_dict(counts: Any) -> dict[str, Any]:
    return {
        "true_positive": counts.true_positive,
        "false_positive": counts.false_positive,
        "false_negative": counts.false_negative,
        "reference_support": counts.reference_support,
        "prediction_support": counts.prediction_support,
        "precision": counts.precision,
        "recall": counts.recall,
        "f1": counts.f1,
    }


def _summary_from_result(result: Any) -> dict[str, Any]:
    per_type: dict[str, Any] = {}
    for row in result.per_type_metrics.rows:
        per_type[row.entity_type.value] = {
            "exact": _metric_dict(row.metrics.exact),
            "relaxed": _metric_dict(row.metrics.relaxed),
        }
    return {
        "document_count": result.metrics.document_count,
        "reference_mention_count": result.metrics.reference_mention_count,
        "prediction_mention_count": result.metrics.prediction_mention_count,
        "overall": {
            "exact": _metric_dict(result.metrics.micro.exact),
            "relaxed": _metric_dict(result.metrics.micro.relaxed),
        },
        "per_type": per_type,
        "error_count_by_kind": {
            key.value: value for key, value in result.metrics.error_count_by_kind.items()
        },
    }


def _summary_from_baseline(source: SourceBaseline) -> dict[str, Any]:
    per_type: dict[str, Any] = {}
    for row in source.per_type_metrics.rows:
        per_type[row.entity_type.value] = {
            "exact": _metric_dict(row.metrics.exact),
            "relaxed": _metric_dict(row.metrics.relaxed),
        }
    return {
        "document_count": source.metrics.document_count,
        "reference_mention_count": source.metrics.reference_mention_count,
        "prediction_mention_count": source.metrics.prediction_mention_count,
        "overall": {
            "exact": _metric_dict(source.metrics.micro.exact),
            "relaxed": _metric_dict(source.metrics.micro.relaxed),
        },
        "per_type": per_type,
        "error_count_by_kind": {
            key.value: value for key, value in source.metrics.error_count_by_kind.items()
        },
    }


def _round_metric(tp: int, fp: int, fn: int) -> dict[str, Any]:
    precision = None if tp + fp == 0 else round(tp / (tp + fp), 6)
    recall = None if tp + fn == 0 else round(tp / (tp + fn), 6)
    f1 = None
    if precision is not None and recall is not None:
        f1 = 0.0 if precision + recall == 0 else round(2 * precision * recall / (precision + recall), 6)
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "reference_support": tp + fn,
        "prediction_support": tp + fp,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _aggregate_metric_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return _round_metric(
        sum(int(row["true_positive"]) for row in rows),
        sum(int(row["false_positive"]) for row in rows),
        sum(int(row["false_negative"]) for row in rows),
    )


def _aggregate_baselines(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    per_type: dict[str, Any] = {}
    for entity_type in [item.value for item in ScientificEntityType]:
        per_type[entity_type] = {
            match_kind: _aggregate_metric_rows(
                [left["per_type"][entity_type][match_kind], right["per_type"][entity_type][match_kind]]
            )
            for match_kind in ("exact", "relaxed")
        }
    errors = {
        kind.value: int(left["error_count_by_kind"].get(kind.value, 0))
        + int(right["error_count_by_kind"].get(kind.value, 0))
        for kind in ScientificEntityEvaluationErrorKind
    }
    return {
        "document_count": int(left["document_count"]) + int(right["document_count"]),
        "reference_mention_count": int(left["reference_mention_count"]) + int(right["reference_mention_count"]),
        "prediction_mention_count": int(left["prediction_mention_count"]) + int(right["prediction_mention_count"]),
        "overall": {
            match_kind: _aggregate_metric_rows(
                [left["overall"][match_kind], right["overall"][match_kind]]
            )
            for match_kind in ("exact", "relaxed")
        },
        "per_type": per_type,
        "error_count_by_kind": errors,
    }


def _diagnostics(errors: Sequence[ScientificEntityEvaluationError]) -> dict[str, Any]:
    confusion = Counter()
    predicted_sinks = Counter()
    false_positive = Counter()
    false_negative = Counter()
    for error in errors:
        if error.error_kind == ScientificEntityEvaluationErrorKind.TYPE_MISMATCH:
            if error.reference_entity_type is None or error.prediction_entity_type is None:
                raise SemanticPromptComparisonBuildError("type mismatch missing entity types")
            confusion[f"{error.reference_entity_type.value}->{error.prediction_entity_type.value}"] += 1
            predicted_sinks[error.prediction_entity_type.value] += 1
        elif error.error_kind == ScientificEntityEvaluationErrorKind.FALSE_POSITIVE:
            if error.prediction_entity_type is not None:
                false_positive[error.prediction_entity_type.value] += 1
        elif error.error_kind == ScientificEntityEvaluationErrorKind.FALSE_NEGATIVE:
            if error.reference_entity_type is not None:
                false_negative[error.reference_entity_type.value] += 1
    return {
        "type_mismatch_total": sum(confusion.values()),
        "type_confusions": dict(sorted(confusion.items())),
        "predicted_type_mismatch_sinks": {
            entity_type.value: predicted_sinks[entity_type.value]
            for entity_type in ScientificEntityType
        },
        "false_positive_by_type": {
            entity_type.value: false_positive[entity_type.value]
            for entity_type in ScientificEntityType
        },
        "false_negative_by_type": {
            entity_type.value: false_negative[entity_type.value]
            for entity_type in ScientificEntityType
        },
        "boundary_mismatch_count": sum(
            1 for error in errors if error.error_kind == ScientificEntityEvaluationErrorKind.BOUNDARY_MISMATCH
        ),
    }


def _merge_diagnostics(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    confusion_keys = set(left["type_confusions"]) | set(right["type_confusions"])
    return {
        "type_mismatch_total": int(left["type_mismatch_total"]) + int(right["type_mismatch_total"]),
        "type_confusions": {
            key: int(left["type_confusions"].get(key, 0)) + int(right["type_confusions"].get(key, 0))
            for key in sorted(confusion_keys)
        },
        "predicted_type_mismatch_sinks": {
            entity_type.value: int(left["predicted_type_mismatch_sinks"].get(entity_type.value, 0))
            + int(right["predicted_type_mismatch_sinks"].get(entity_type.value, 0))
            for entity_type in ScientificEntityType
        },
        "false_positive_by_type": {
            entity_type.value: int(left["false_positive_by_type"].get(entity_type.value, 0))
            + int(right["false_positive_by_type"].get(entity_type.value, 0))
            for entity_type in ScientificEntityType
        },
        "false_negative_by_type": {
            entity_type.value: int(left["false_negative_by_type"].get(entity_type.value, 0))
            + int(right["false_negative_by_type"].get(entity_type.value, 0))
            for entity_type in ScientificEntityType
        },
        "boundary_mismatch_count": int(left["boundary_mismatch_count"]) + int(right["boundary_mismatch_count"]),
    }


def _metric_delta(candidate: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("precision", "recall", "f1"):
        left = candidate.get(key)
        right = baseline.get(key)
        result[key] = None if left is None or right is None else round(float(left) - float(right), 6)
    result["true_positive"] = int(candidate["true_positive"]) - int(baseline["true_positive"])
    result["false_positive"] = int(candidate["false_positive"]) - int(baseline["false_positive"])
    result["false_negative"] = int(candidate["false_negative"]) - int(baseline["false_negative"])
    return result


def _split_delta(candidate: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "overall": {
            kind: _metric_delta(candidate["overall"][kind], baseline["overall"][kind])
            for kind in ("exact", "relaxed")
        },
        "per_type": {
            entity_type.value: {
                kind: _metric_delta(
                    candidate["per_type"][entity_type.value][kind],
                    baseline["per_type"][entity_type.value][kind],
                )
                for kind in ("exact", "relaxed")
            }
            for entity_type in ScientificEntityType
        },
        "prediction_mention_count": int(candidate["prediction_mention_count"])
        - int(baseline["prediction_mention_count"]),
    }


def _validate_frozen_heldout_baseline(
    *,
    design: SemanticPromptCandidateConfig,
    summary: Mapping[str, Any],
    diagnostics: Mapping[str, Any],
) -> None:
    frozen = design.controlled_comparison.consumed_v01_heldout_baseline
    checks = {
        "exact_f1": summary["overall"]["exact"]["f1"],
        "relaxed_f1": summary["overall"]["relaxed"]["f1"],
        "total_type_mismatch_count": diagnostics["type_mismatch_total"],
        "model_to_method_count": diagnostics["type_confusions"].get("model->method", 0),
        "method_to_task_count": diagnostics["type_confusions"].get("method->task", 0),
        "method_semantic_sink_count": diagnostics["predicted_type_mismatch_sinks"].get("method", 0),
        "metric_exact_f1": summary["per_type"]["metric"]["exact"]["f1"],
        "domain_exact_f1": summary["per_type"]["domain"]["exact"]["f1"],
        "task_exact_recall": summary["per_type"]["task"]["exact"]["recall"],
        "model_exact_f1": summary["per_type"]["model"]["exact"]["f1"],
    }
    expected = frozen.model_dump(mode="json")
    if checks != expected:
        raise SemanticPromptComparisonBuildError(
            f"Consumed v0.1 held-out baseline drifted from frozen design: {checks!r}"
        )


def evaluate_development_gate(
    *,
    design: SemanticPromptCandidateConfig,
    candidate_summary: Mapping[str, Any],
    candidate_diagnostics: Mapping[str, Any],
) -> dict[str, Any]:
    hard = design.controlled_comparison.decision_gates.hard_guardrails
    exact_f1 = candidate_summary["overall"]["exact"]["f1"]
    if exact_f1 is None:
        raise SemanticPromptComparisonBuildError("Candidate exact F1 is undefined")
    sinks = candidate_diagnostics["predicted_type_mismatch_sinks"]
    max_sink = max(int(value) for value in sinks.values()) if sinks else 0
    observations = {
        "minimum_overall_exact_f1": (float(exact_f1), float(hard.minimum_overall_exact_f1), float(exact_f1) >= float(hard.minimum_overall_exact_f1)),
        "maximum_model_to_method_count": (int(candidate_diagnostics["type_confusions"].get("model->method", 0)), int(hard.maximum_model_to_method_count), int(candidate_diagnostics["type_confusions"].get("model->method", 0)) <= int(hard.maximum_model_to_method_count)),
        "maximum_method_to_task_count": (int(candidate_diagnostics["type_confusions"].get("method->task", 0)), int(hard.maximum_method_to_task_count), int(candidate_diagnostics["type_confusions"].get("method->task", 0)) <= int(hard.maximum_method_to_task_count)),
        "maximum_total_type_mismatch_count": (int(candidate_diagnostics["type_mismatch_total"]), int(hard.maximum_total_type_mismatch_count), int(candidate_diagnostics["type_mismatch_total"]) <= int(hard.maximum_total_type_mismatch_count)),
        "maximum_method_semantic_sink_count": (int(sinks.get("method", 0)), int(hard.maximum_method_semantic_sink_count), int(sinks.get("method", 0)) <= int(hard.maximum_method_semantic_sink_count)),
        "maximum_any_predicted_type_mismatch_sink_count": (max_sink, int(hard.maximum_any_predicted_type_mismatch_sink_count), max_sink <= int(hard.maximum_any_predicted_type_mismatch_sink_count)),
    }
    hard_rows = {
        name: {"observed": observed, "threshold": threshold, "passed": passed}
        for name, (observed, threshold, passed) in observations.items()
    }
    hard_passed = all(row["passed"] for row in hard_rows.values())

    baseline = design.controlled_comparison.consumed_v01_heldout_baseline
    desirable_specs = {
        "metric_exact_f1": (
            candidate_summary["per_type"]["metric"]["exact"]["f1"],
            float(baseline.metric_exact_f1),
            "increase",
        ),
        "domain_exact_f1": (
            candidate_summary["per_type"]["domain"]["exact"]["f1"],
            float(baseline.domain_exact_f1),
            "increase",
        ),
        "task_exact_recall": (
            candidate_summary["per_type"]["task"]["exact"]["recall"],
            float(baseline.task_exact_recall),
            "increase",
        ),
        "model_exact_f1": (
            candidate_summary["per_type"]["model"]["exact"]["f1"],
            float(baseline.model_exact_f1),
            "increase",
        ),
        "overall_relaxed_f1": (
            candidate_summary["overall"]["relaxed"]["f1"],
            float(baseline.relaxed_f1),
            "nondecrease",
        ),
    }
    desirable: dict[str, Any] = {}
    for name, (value, baseline_value, direction) in desirable_specs.items():
        passed = False if value is None else (
            float(value) > baseline_value if direction == "increase" else float(value) >= baseline_value
        )
        desirable[name] = {
            "observed": value,
            "baseline": baseline_value,
            "direction": direction,
            "passed": passed,
            "delta": None if value is None else round(float(value) - baseline_value, 6),
        }

    return {
        "schema_version": GATE_SCHEMA_VERSION,
        "evaluation_role": design.controlled_comparison.decision_gates.evaluation_role,
        "hard_guardrails": hard_rows,
        "all_hard_guardrails_passed": hard_passed,
        "candidate_promising_for_next_development_slice": hard_passed,
        "desirable_directional_signals": desirable,
        "production_acceptance": False,
        "independent_v02_acceptance": False,
        "full_corpus_build_authorized": False,
        "future_v02_acceptance_requires_new_disjoint_heldout": True,
        "next_slice": (
            design.next_steps.if_promising if hard_passed else design.next_steps.if_not_promising
        ),
    }


def _prepare(
    *,
    project_root: Path,
    config_path: Path,
    development_package_dir: Path,
    policy_build_dir: Path,
    parent_raw_build_dir: Path,
    comparison_id: str,
    generated_at_utc: datetime,
) -> PreparedComparison:
    root = project_root.resolve()
    config = load_semantic_prompt_comparison_config(config_path.resolve())
    design_path = _resolve(root, config.candidate.design_config_path)
    policy_config_path = _resolve(root, config.candidate.policy_config_path)
    evaluation_config_path = _resolve(root, config.candidate.evaluation_config_path)
    design = load_semantic_prompt_candidate_config(design_path)
    evaluation_config: ScientificEntityEvaluationConfig = load_evaluation_config(evaluation_config_path)

    package_validation = validate_semantic_prompt_development_package(
        project_root=root,
        design_config_path=design_path,
        package_dir=development_package_dir,
    )
    policy_validation = validate_semantic_prompt_policy_build(
        build_dir=policy_build_dir,
        parent_build_dir=parent_raw_build_dir,
        development_package_dir=development_package_dir,
        config_path=policy_config_path,
    )
    if package_validation["combined_document_count"] != config.candidate.expected_document_count:
        raise SemanticPromptComparisonBuildError("Development package document count drifted")
    if policy_validation["selected_prediction_count"] != config.candidate.expected_selected_prediction_count:
        raise SemanticPromptComparisonBuildError(
            "Policy selected_prediction_count does not match the frozen real v0.2a run"
        )

    package_manifest = _read_json(development_package_dir / "manifest.json")
    policy_manifest, derivation, predictions = _load_policy_predictions(
        policy_build_dir=policy_build_dir,
        documents=_load_canonical(development_package_dir)[0],
    )
    documents, membership = _load_canonical(development_package_dir)
    if policy_manifest.canonical_input.sha256 != package_manifest["canonical_documents_sha256"]:
        raise SemanticPromptComparisonBuildError("Policy canonical input SHA does not match package")
    if policy_manifest.canonical_input.document_count != 72:
        raise SemanticPromptComparisonBuildError("Policy canonical document count must remain 72")
    if derivation.development_package_id != package_manifest["package_id"]:
        raise SemanticPromptComparisonBuildError("Policy derivation package lineage drifted")
    if derivation.candidate_id != config.candidate.candidate_id:
        raise SemanticPromptComparisonBuildError("Policy derivation candidate_id drifted")

    source_rows = package_manifest.get("sources")
    if not isinstance(source_rows, list) or len(source_rows) != 2:
        raise SemanticPromptComparisonBuildError("Development package sources drifted")
    source_by_split = {str(row["split"]): row for row in source_rows}
    split_ids = {
        split: {canonical_id for canonical_id, member_split in membership.items() if member_split == split}
        for split in ("old_dev_24", "consumed_v01_heldout_48")
    }
    baselines = {
        split: _load_source_baseline(
            root=root,
            source_descriptor=source_by_split[split],
            documents=documents,
            expected_ids=split_ids[split],
        )
        for split in ("old_dev_24", "consumed_v01_heldout_48")
    }

    predictions_by_split = {
        split: tuple(row for row in predictions if row.canonical_id in split_ids[split])
        for split in ("old_dev_24", "consumed_v01_heldout_48")
    }
    if len(predictions_by_split["old_dev_24"]) + len(predictions_by_split["consumed_v01_heldout_48"]) != len(predictions):
        raise SemanticPromptComparisonBuildError("Policy predictions do not partition into 24 / 48")

    timestamp = generated_at_utc.strftime("%Y%m%dT%H%M%S%fZ")
    candidate_results = {}
    candidate_summaries = {}
    candidate_diagnostics = {}
    baseline_summaries = {}
    baseline_diagnostics = {}
    for split in ("old_dev_24", "consumed_v01_heldout_48"):
        result = evaluate_mentions(
            evaluation_id=f"semantic-prompt-v02a-{split}-{timestamp}",
            document_count=len(split_ids[split]),
            references=baselines[split].references,
            predictions=predictions_by_split[split],
            config=evaluation_config,
        )
        candidate_results[split] = result
        candidate_summaries[split] = _summary_from_result(result)
        candidate_diagnostics[split] = _diagnostics(result.errors)
        baseline_summaries[split] = _summary_from_baseline(baselines[split])
        baseline_diagnostics[split] = _diagnostics(baselines[split].errors)

    combined_refs = baselines["old_dev_24"].references + baselines["consumed_v01_heldout_48"].references
    combined_result = evaluate_mentions(
        evaluation_id=f"semantic-prompt-v02a-combined-dev-72-{timestamp}",
        document_count=72,
        references=combined_refs,
        predictions=predictions,
        config=evaluation_config,
    )
    candidate_summaries["combined_dev_72"] = _summary_from_result(combined_result)
    candidate_diagnostics["combined_dev_72"] = _diagnostics(combined_result.errors)
    baseline_summaries["combined_dev_72"] = _aggregate_baselines(
        baseline_summaries["old_dev_24"], baseline_summaries["consumed_v01_heldout_48"]
    )
    baseline_diagnostics["combined_dev_72"] = _merge_diagnostics(
        baseline_diagnostics["old_dev_24"], baseline_diagnostics["consumed_v01_heldout_48"]
    )

    # Disjoint split aggregation must reproduce the direct combined candidate evaluation.
    aggregate_candidate = _aggregate_baselines(
        candidate_summaries["old_dev_24"], candidate_summaries["consumed_v01_heldout_48"]
    )
    if aggregate_candidate != candidate_summaries["combined_dev_72"]:
        raise SemanticPromptComparisonBuildError(
            "Direct combined candidate metrics differ from disjoint split aggregation"
        )
    aggregate_diag = _merge_diagnostics(
        candidate_diagnostics["old_dev_24"], candidate_diagnostics["consumed_v01_heldout_48"]
    )
    if aggregate_diag != candidate_diagnostics["combined_dev_72"]:
        raise SemanticPromptComparisonBuildError(
            "Direct combined candidate diagnostics differ from split aggregation"
        )

    _validate_frozen_heldout_baseline(
        design=design,
        summary=baseline_summaries["consumed_v01_heldout_48"],
        diagnostics=baseline_diagnostics["consumed_v01_heldout_48"],
    )
    gate = evaluate_development_gate(
        design=design,
        candidate_summary=candidate_summaries["consumed_v01_heldout_48"],
        candidate_diagnostics=candidate_diagnostics["consumed_v01_heldout_48"],
    )

    comparison = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "comparison_id": comparison_id,
        "candidate_id": config.candidate.candidate_id,
        "evaluation_role": "development_candidate_gate_not_independent_acceptance",
        "splits": {
            split: {
                "baseline": baseline_summaries[split],
                "candidate": candidate_summaries[split],
                "delta": _split_delta(candidate_summaries[split], baseline_summaries[split]),
            }
            for split in config.candidate.compare_splits
        },
    }
    diagnostics = {
        "schema_version": DIAGNOSTICS_SCHEMA_VERSION,
        "comparison_id": comparison_id,
        "splits": {
            split: {
                "baseline": baseline_diagnostics[split],
                "candidate": candidate_diagnostics[split],
                "delta": {
                    "type_mismatch_total": candidate_diagnostics[split]["type_mismatch_total"]
                    - baseline_diagnostics[split]["type_mismatch_total"],
                    "model_to_method": candidate_diagnostics[split]["type_confusions"].get("model->method", 0)
                    - baseline_diagnostics[split]["type_confusions"].get("model->method", 0),
                    "method_to_task": candidate_diagnostics[split]["type_confusions"].get("method->task", 0)
                    - baseline_diagnostics[split]["type_confusions"].get("method->task", 0),
                    "method_semantic_sink": candidate_diagnostics[split]["predicted_type_mismatch_sinks"].get("method", 0)
                    - baseline_diagnostics[split]["predicted_type_mismatch_sinks"].get("method", 0),
                },
            }
            for split in config.candidate.compare_splits
        },
    }

    held_candidate = candidate_summaries["consumed_v01_heldout_48"]
    held_diag = candidate_diagnostics["consumed_v01_heldout_48"]
    comparison_bytes = _json_bytes(comparison)
    diagnostics_bytes = _json_bytes(diagnostics)
    gate_bytes = _json_bytes(gate)
    manifest = {
        "schema_version": COMPARISON_MANIFEST_SCHEMA_VERSION,
        "comparison_id": comparison_id,
        "candidate_id": config.candidate.candidate_id,
        "generated_at_utc": generated_at_utc.isoformat().replace("+00:00", "Z"),
        "config_path": _project_path(root, config_path),
        "config_sha256": _sha256_file(config_path),
        "design_config_path": _project_path(root, design_path),
        "design_config_sha256": _sha256_file(design_path),
        "evaluation_config_path": _project_path(root, evaluation_config_path),
        "evaluation_config_sha256": _sha256_file(evaluation_config_path),
        "development_package_id": package_manifest["package_id"],
        "development_package_manifest_sha256": _sha256_file(development_package_dir / "manifest.json"),
        "policy_build_id": policy_manifest.build_id,
        "policy_manifest_sha256": _sha256_file(policy_build_dir / "manifest.json"),
        "policy_derivation_manifest_sha256": _sha256_file(policy_build_dir / "derivation_manifest.json"),
        "policy_selected_prediction_count": len(predictions),
        "split_document_counts": {"old_dev_24": 24, "consumed_v01_heldout_48": 48, "combined_dev_72": 72},
        "split_reference_counts": {
            "old_dev_24": len(baselines["old_dev_24"].references),
            "consumed_v01_heldout_48": len(baselines["consumed_v01_heldout_48"].references),
            "combined_dev_72": len(combined_refs),
        },
        "split_candidate_prediction_counts": {
            "old_dev_24": len(predictions_by_split["old_dev_24"]),
            "consumed_v01_heldout_48": len(predictions_by_split["consumed_v01_heldout_48"]),
            "combined_dev_72": len(predictions),
        },
        "comparison_file": "comparison.json",
        "comparison_sha256": hashlib.sha256(comparison_bytes).hexdigest(),
        "diagnostics_file": "diagnostics.json",
        "diagnostics_sha256": hashlib.sha256(diagnostics_bytes).hexdigest(),
        "gate_decision_file": "gate_decision.json",
        "gate_decision_sha256": hashlib.sha256(gate_bytes).hexdigest(),
        "candidate_promising_for_next_development_slice": gate["candidate_promising_for_next_development_slice"],
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "canonical_truth_mutated": False,
        "may_be_used_as_reconcile_input": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "publication_ready": False,
        "current_48_is_independent_heldout_for_v02": False,
        "future_v02_acceptance_requires_new_disjoint_heldout": True,
        "next_slice": gate["next_slice"],
    }
    readme = "\n".join(
        [
            "# Scientific Entity Semantic Prompt Controlled Comparison v0.2a",
            "",
            f"comparison_id = `{comparison_id}`",
            f"policy_build_id = `{policy_manifest.build_id}`",
            "",
            "This immutable artifact compares frozen v0.1 baseline evidence against the",
            "v0.2a semantic-prompt candidate on three development views: 24 / 48 / 72 papers.",
            "",
            "The current 48-paper package is consumed development evidence for v0.2 and",
            "must not be described as an independent v0.2 held-out gate.",
            "",
            f"consumed_48_candidate_exact_f1 = `{held_candidate['overall']['exact']['f1']}`",
            f"consumed_48_candidate_relaxed_f1 = `{held_candidate['overall']['relaxed']['f1']}`",
            f"consumed_48_model_to_method = `{held_diag['type_confusions'].get('model->method', 0)}`",
            f"consumed_48_method_to_task = `{held_diag['type_confusions'].get('method->task', 0)}`",
            f"consumed_48_method_semantic_sink = `{held_diag['predicted_type_mismatch_sinks'].get('method', 0)}`",
            f"all_hard_guardrails_passed = `{str(gate['all_hard_guardrails_passed']).lower()}`",
            f"next_slice = `{gate['next_slice']}`",
            "",
            "No model inference, threshold tuning, canonical mutation, production selection,",
            "or full-corpus authorization occurs in this comparison layer.",
            "",
        ]
    )
    report = {
        "report": REPORT_NAME,
        "ok": True,
        "comparison_id": comparison_id,
        "candidate_id": config.candidate.candidate_id,
        "development_document_count": 72,
        "reference_mention_count": len(combined_refs),
        "candidate_prediction_count": len(predictions),
        "consumed_heldout_candidate_exact_f1": held_candidate["overall"]["exact"]["f1"],
        "consumed_heldout_candidate_relaxed_f1": held_candidate["overall"]["relaxed"]["f1"],
        "consumed_heldout_model_to_method_count": held_diag["type_confusions"].get("model->method", 0),
        "consumed_heldout_method_to_task_count": held_diag["type_confusions"].get("method->task", 0),
        "consumed_heldout_total_type_mismatch_count": held_diag["type_mismatch_total"],
        "consumed_heldout_method_semantic_sink_count": held_diag["predicted_type_mismatch_sinks"].get("method", 0),
        "all_hard_guardrails_passed": gate["all_hard_guardrails_passed"],
        "candidate_promising_for_next_development_slice": gate["candidate_promising_for_next_development_slice"],
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "canonical_truth_mutated": False,
        "full_corpus_build_authorized": False,
        "production_extractor_selected": False,
        "next_slice": gate["next_slice"],
    }
    return PreparedComparison(
        report=report,
        manifest=manifest,
        comparison=comparison,
        diagnostics=diagnostics,
        gate_decision=gate,
        readme=readme,
    )


def _comparison_id(generated_at_utc: datetime) -> str:
    timestamp = generated_at_utc.strftime("%Y%m%dT%H%M%S%fZ")
    return f"scientific-entity-semantic-prompt-comparison-v0.2a-{timestamp}"


def build_semantic_prompt_comparison(
    *,
    project_root: Path,
    development_package_dir: Path,
    policy_build_dir: Path,
    parent_raw_build_dir: Path,
    config_path: Path | None = None,
    output_root: Path | None = None,
    comparison_id: str | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    selected_config = _resolve(root, config_path or DEFAULT_CONFIG_PATH)
    config = load_semantic_prompt_comparison_config(selected_config)
    now = generated_at_utc or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(now):
        raise SemanticPromptComparisonBuildError("generated_at_utc must be timezone-aware UTC")
    selected_id = comparison_id or _comparison_id(now)
    selected_output_root = _resolve(root, output_root or config.outputs.root)
    output_dir = selected_output_root / selected_id
    if execute and output_dir.exists():
        raise FileExistsError(
            f"Immutable comparison already exists; overwrite is forbidden: {output_dir}"
        )

    prepared = _prepare(
        project_root=root,
        config_path=selected_config,
        development_package_dir=development_package_dir.resolve(),
        policy_build_dir=policy_build_dir.resolve(),
        parent_raw_build_dir=parent_raw_build_dir.resolve(),
        comparison_id=selected_id,
        generated_at_utc=now,
    )
    written_files: list[str] = []
    if execute:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{selected_id}.tmp-", dir=output_dir.parent))
        try:
            (staging / "comparison.json").write_bytes(_json_bytes(prepared.comparison))
            (staging / "diagnostics.json").write_bytes(_json_bytes(prepared.diagnostics))
            (staging / "gate_decision.json").write_bytes(_json_bytes(prepared.gate_decision))
            (staging / "manifest.json").write_bytes(_json_bytes(prepared.manifest))
            (staging / "README.md").write_text(prepared.readme, encoding="utf-8", newline="\n")
            checksum_lines = [
                f"{_sha256_file(staging / filename)}  {filename}"
                for filename in REQUIRED_FILES[:-1]
            ]
            (staging / "checksums.txt").write_text(
                "\n".join(checksum_lines) + "\n", encoding="utf-8", newline="\n"
            )
            staging.rename(output_dir)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
        written_files = list(REQUIRED_FILES)

    report = dict(prepared.report)
    report.update(
        mode="execute" if execute else "plan",
        phase_complete=execute,
        output_dir=str(output_dir).replace("\\", "/"),
        written_files=written_files,
    )
    return report


def validate_semantic_prompt_comparison(
    *,
    project_root: Path,
    comparison_dir: Path,
    development_package_dir: Path,
    policy_build_dir: Path,
    parent_raw_build_dir: Path,
    config_path: Path | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    comparison_dir = comparison_dir.resolve()
    for filename in REQUIRED_FILES:
        if not (comparison_dir / filename).is_file():
            raise FileNotFoundError(comparison_dir / filename)

    checksums: dict[str, str] = {}
    for line in (comparison_dir / "checksums.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        sha, filename = line.split("  ", 1)
        checksums[filename] = sha
    if set(checksums) != set(REQUIRED_FILES[:-1]):
        raise SemanticPromptComparisonBuildError("checksums.txt coverage mismatch")
    for filename, expected in checksums.items():
        if _sha256_file(comparison_dir / filename) != expected:
            raise SemanticPromptComparisonBuildError(f"Checksum mismatch: {filename}")

    manifest = _read_json(comparison_dir / "manifest.json")
    if manifest.get("schema_version") != COMPARISON_MANIFEST_SCHEMA_VERSION:
        raise SemanticPromptComparisonBuildError("Unexpected comparison manifest schema")
    if comparison_dir.name != manifest.get("comparison_id"):
        raise SemanticPromptComparisonBuildError("comparison directory/id mismatch")
    generated_at = datetime.fromisoformat(str(manifest["generated_at_utc"]).replace("Z", "+00:00"))
    selected_config = _resolve(root, config_path or DEFAULT_CONFIG_PATH)
    prepared = _prepare(
        project_root=root,
        config_path=selected_config,
        development_package_dir=development_package_dir.resolve(),
        policy_build_dir=policy_build_dir.resolve(),
        parent_raw_build_dir=parent_raw_build_dir.resolve(),
        comparison_id=str(manifest["comparison_id"]),
        generated_at_utc=generated_at,
    )
    expected_files = {
        "manifest.json": _json_bytes(prepared.manifest),
        "comparison.json": _json_bytes(prepared.comparison),
        "diagnostics.json": _json_bytes(prepared.diagnostics),
        "gate_decision.json": _json_bytes(prepared.gate_decision),
        "README.md": prepared.readme.encode("utf-8"),
    }
    for filename, expected in expected_files.items():
        if (comparison_dir / filename).read_bytes() != expected:
            raise SemanticPromptComparisonBuildError(
                f"Comparison artifact does not reproduce byte-for-byte: {filename}"
            )

    report = dict(prepared.report)
    report.update(required_failed_count=0)
    return report
