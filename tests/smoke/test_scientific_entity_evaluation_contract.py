from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from radar_core.contracts.scientific_entity_evaluation import (
    METRICS_SCHEMA_VERSION,
    PER_TYPE_METRICS_SCHEMA_VERSION,
    REFERENCE_MENTION_SCHEMA_VERSION,
    ScientificEntityAnnotationMethod,
    ScientificEntityDataSufficiency,
    ScientificEntityEvaluationErrorKind,
    ScientificEntityEvaluationMetrics,
    ScientificEntityMatchingMetrics,
    ScientificEntityMetricCounts,
    ScientificEntityPerTypeMetrics,
    ScientificEntityReferenceMention,
    ScientificEntityReviewManifest,
    ScientificEntityReviewStatus,
    build_reference_id,
)
from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntitySourceField,
    ScientificEntityType,
)
from radar_core.entities.scientific_entity_evaluation import (
    ScientificEntityEvaluationConfig,
    ScientificEntityEvaluationErrorBase,
    evaluation_config_sha256,
    load_evaluation_config,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "scientific_entity_evaluation_v0.1.yaml"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "scientific_entity_evaluation_v0_1"


def _json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _first_reference() -> dict[str, object]:
    return json.loads(
        (FIXTURE_DIR / "reference_mentions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )


def _zero_counts() -> ScientificEntityMetricCounts:
    return ScientificEntityMetricCounts(
        true_positive=0,
        false_positive=0,
        false_negative=0,
        reference_support=0,
        prediction_support=0,
        precision_denominator=0,
        recall_denominator=0,
        precision=None,
        recall=None,
        f1=None,
    )


def test_evaluation_config_is_bounded_and_descriptive_only() -> None:
    config = load_evaluation_config(CONFIG_PATH)

    assert config.layer.status == "evaluation_harness"
    assert config.matching.relaxed_min_char_iou == 0.5
    assert config.safety.default_max_documents == 32
    assert config.safety.hard_max_documents == 100
    assert config.safety.full_corpus_build_authorized is False
    assert config.metrics.promotion_verdict_allowed is False
    assert config.metrics.metrics_are_descriptive_only is True


def test_evaluation_config_covers_exact_taxonomy_and_fields() -> None:
    config = load_evaluation_config(CONFIG_PATH)

    assert config.metrics.entity_types == list(ScientificEntityType)
    assert config.metrics.source_fields == list(ScientificEntitySourceField)
    assert set(config.manual_error_labels)
    assert len(config.manual_error_labels) == 10


def test_config_fingerprint_is_semantic_and_deterministic() -> None:
    config = load_evaluation_config(CONFIG_PATH)
    reparsed = ScientificEntityEvaluationConfig.model_validate(
        config.model_dump(mode="json")
    )

    assert evaluation_config_sha256(config) == evaluation_config_sha256(reparsed)
    assert len(evaluation_config_sha256(config)) == 64


def test_reference_identity_is_extractor_independent_and_deterministic() -> None:
    row = _first_reference()
    parsed = ScientificEntityReferenceMention.model_validate(row)

    assert parsed.schema_version == REFERENCE_MENTION_SCHEMA_VERSION
    assert parsed.reference_id == build_reference_id(
        review_id=parsed.review_id,
        mention_id=parsed.mention_id,
        annotation_method=parsed.annotation_method,
        annotation_pass=parsed.annotation_pass,
    )
    assert "extractor" not in parsed.model_dump(mode="json")


def test_reference_identity_tampering_fails_closed() -> None:
    row = _first_reference()
    row["char_end"] = int(row["char_end"]) + 1

    with pytest.raises(ValidationError, match="mention_id"):
        ScientificEntityReferenceMention.model_validate(row)


def test_synthetic_review_manifest_cannot_claim_human_annotators() -> None:
    payload = _json(FIXTURE_DIR / "review_manifest.json")
    payload["annotator_ids"] = ["reviewer:synthetic"]

    with pytest.raises(ValidationError, match="must not claim human"):
        ScientificEntityReviewManifest.model_validate(payload)


def test_manual_review_requires_prediction_blind_annotator() -> None:
    payload = _json(FIXTURE_DIR / "review_manifest.json")
    payload["status"] = ScientificEntityReviewStatus.REVIEWED_CANDIDATE.value
    payload["annotation_method"] = ScientificEntityAnnotationMethod.MANUAL_INDEPENDENT.value
    payload["prediction_blind"] = False
    payload["annotator_ids"] = ["reviewer:001"]

    with pytest.raises(ValidationError, match="prediction blind"):
        ScientificEntityReviewManifest.model_validate(payload)


def test_metric_nullability_is_explicit_for_zero_denominators() -> None:
    counts = _zero_counts()

    assert counts.precision is None
    assert counts.recall is None
    assert counts.f1 is None


def test_metric_denominator_mismatch_fails_closed() -> None:
    with pytest.raises(ValidationError, match="precision_denominator"):
        ScientificEntityMetricCounts(
            true_positive=1,
            false_positive=1,
            false_negative=0,
            reference_support=1,
            prediction_support=2,
            precision_denominator=1,
            recall_denominator=1,
            precision=1.0,
            recall=1.0,
            f1=1.0,
        )


def test_per_type_metrics_requires_all_six_types_in_enum_order() -> None:
    payload = {
        "schema_version": PER_TYPE_METRICS_SCHEMA_VERSION,
        "evaluation_id": "evaluation-fixture-v0.1",
        "minimum_reference_mentions_per_type": 20,
        "rows": [],
    }

    with pytest.raises(ValidationError, match="all entity types"):
        ScientificEntityPerTypeMetrics.model_validate(payload)


def test_metrics_requires_complete_error_taxonomy() -> None:
    matching = ScientificEntityMatchingMetrics(exact=_zero_counts(), relaxed=_zero_counts())
    config = load_evaluation_config(CONFIG_PATH)
    payload = {
        "schema_version": METRICS_SCHEMA_VERSION,
        "evaluation_id": "evaluation-fixture-v0.1",
        "document_count": 1,
        "reference_mention_count": 0,
        "prediction_mention_count": 0,
        "matching_policy": config.matching.contract_policy().model_dump(mode="json"),
        "micro": matching.model_dump(mode="json"),
        "by_source_field": {
            field.value: matching.model_dump(mode="json")
            for field in ScientificEntitySourceField
        },
        "exact_match_count": 0,
        "relaxed_only_match_count": 0,
        "error_count_by_kind": {
            ScientificEntityEvaluationErrorKind.FALSE_POSITIVE.value: 0
        },
        "data_sufficiency": ScientificEntityDataSufficiency(
            minimum_document_count=32,
            minimum_reference_mentions_per_type=20,
            document_count_sufficient=False,
            per_type_support_sufficient={
                entity_type: False for entity_type in ScientificEntityType
            },
            promotion_sample_sufficient=False,
            metrics_are_descriptive_only=True,
        ).model_dump(mode="json"),
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "canonical_truth_mutated": False,
        "publication_ready": False,
    }

    with pytest.raises(ValidationError, match="all automatic error kinds"):
        ScientificEntityEvaluationMetrics.model_validate(payload)


def test_duplicate_yaml_keys_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text(
        CONFIG_PATH.read_text(encoding="utf-8") + "\nmatching: {}\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ScientificEntityEvaluationErrorBase, match="duplicate key"):
        load_evaluation_config(path)


def test_evaluation_jsonl_fixtures_are_pinned_to_lf() -> None:
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert (
        "tests/fixtures/scientific_entity_evaluation_v0_1/*.jsonl text eol=lf"
        in attributes
    )
    assert (
        "tests/fixtures/scientific_entity_evaluation_v0_1/"
        "prediction_build/*.jsonl text eol=lf"
        in attributes
    )
    for path in sorted(FIXTURE_DIR.rglob("*.jsonl")):
        raw = path.read_bytes()
        assert b"\r" not in raw
        assert raw.endswith(b"\n")
