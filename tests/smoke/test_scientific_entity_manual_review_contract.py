from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from radar_core.contracts.scientific_entity_manual_review import (
    BLIND_ANNOTATION_SCHEMA_VERSION,
    SAMPLE_ASSIGNMENT_SCHEMA_VERSION,
    ScientificEntityBlindAnnotationMention,
    ScientificEntityBlindAnnotationRow,
    ScientificEntitySampleAssignment,
    ScientificEntitySampleStratum,
    build_selection_score,
)
from radar_core.entities.scientific_entity_manual_review import (
    document_matches_enrichment_type,
    load_manual_review_config,
    manual_review_config_sha256,
)
from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntityType,
    sha256_text,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs" / "scientific_entity_manual_review_evidence_v0.1.yaml"
REVIEW_ID = "scientific-entity-manual-review-fixture-v0.1"


def _annotation_payload() -> dict[str, object]:
    source_text = "BERT classification"
    return {
        "schema_version": BLIND_ANNOTATION_SCHEMA_VERSION,
        "review_id": REVIEW_ID,
        "canonical_id": "synthetic-contract-001",
        "sample_stratum": "type_enriched",
        "enrichment_entity_type": "model",
        "source_field": "title",
        "source_text_sha256": sha256_text(source_text),
        "source_text": source_text,
        "annotation_complete": True,
        "mentions": [
            {
                "entity_type": "model",
                "char_start": 0,
                "char_end": 4,
                "surface_text": "BERT",
                "uncertain": False,
                "reviewer_note": None,
            }
        ],
        "reviewer_note": None,
    }


def test_default_manual_review_config_is_valid_and_bounded() -> None:
    config = load_manual_review_config(CONFIG_PATH)

    assert config.schema_version == "scientific_entity_manual_review_evidence_config_v0.1"
    assert config.sampling.total_document_count == 24
    assert config.safety.hard_max_selected_documents == 32
    assert config.safety.full_corpus_entity_extraction_allowed is False
    assert config.safety.predictions_visible_during_annotation is False
    assert config.safety.publication_allowed is False


def test_config_semantic_fingerprint_is_stable() -> None:
    first = load_manual_review_config(CONFIG_PATH)
    second = load_manual_review_config(CONFIG_PATH)

    assert manual_review_config_sha256(first) == manual_review_config_sha256(second)
    assert len(manual_review_config_sha256(first)) == 64


def test_selection_score_is_stable_and_stratum_specific() -> None:
    uniform = build_selection_score(
        seed="seed",
        stratum="uniform",
        canonical_id="paper-1",
    )
    repeated = build_selection_score(
        seed="seed",
        stratum="uniform",
        canonical_id="paper-1",
    )
    enriched = build_selection_score(
        seed="seed",
        stratum="type_enriched",
        enrichment_entity_type="model",
        canonical_id="paper-1",
    )

    assert uniform == repeated
    assert uniform != enriched


def test_uniform_assignment_forbids_enrichment_type() -> None:
    with pytest.raises(ValidationError):
        ScientificEntitySampleAssignment(
            schema_version=SAMPLE_ASSIGNMENT_SCHEMA_VERSION,
            review_id=REVIEW_ID,
            canonical_id="paper-1",
            sample_stratum=ScientificEntitySampleStratum.UNIFORM,
            enrichment_entity_type="model",
            selection_score="0" * 64,
            stratum_rank=1,
        )


def test_type_enriched_assignment_requires_entity_type() -> None:
    with pytest.raises(ValidationError):
        ScientificEntitySampleAssignment(
            schema_version=SAMPLE_ASSIGNMENT_SCHEMA_VERSION,
            review_id=REVIEW_ID,
            canonical_id="paper-1",
            sample_stratum=ScientificEntitySampleStratum.TYPE_ENRICHED,
            enrichment_entity_type=None,
            selection_score="0" * 64,
            stratum_rank=1,
        )


def test_blind_annotation_contract_accepts_exact_half_open_span() -> None:
    row = ScientificEntityBlindAnnotationRow.model_validate(_annotation_payload())

    assert row.mentions[0].surface_text == "BERT"
    assert row.source_text[row.mentions[0].char_start : row.mentions[0].char_end] == "BERT"


def test_blind_annotation_rejects_prediction_leakage_field() -> None:
    payload = _annotation_payload()
    payload["prediction_evidence_id"] = "forbidden"

    with pytest.raises(ValidationError):
        ScientificEntityBlindAnnotationRow.model_validate(payload)


def test_blind_annotation_rejects_source_hash_drift() -> None:
    payload = _annotation_payload()
    payload["source_text_sha256"] = "0" * 64

    with pytest.raises(ValidationError):
        ScientificEntityBlindAnnotationRow.model_validate(payload)


def test_blind_annotation_rejects_surface_span_drift() -> None:
    payload = _annotation_payload()
    payload["mentions"][0]["char_end"] = 5  # type: ignore[index]

    with pytest.raises(ValidationError):
        ScientificEntityBlindAnnotationRow.model_validate(payload)


def test_blind_annotation_rejects_duplicate_typed_span() -> None:
    payload = _annotation_payload()
    payload["mentions"].append(dict(payload["mentions"][0]))  # type: ignore[union-attr,index]

    with pytest.raises(ValidationError):
        ScientificEntityBlindAnnotationRow.model_validate(payload)


def test_enrichment_matching_uses_unicode_word_boundaries_case_insensitively() -> None:
    config = load_manual_review_config(CONFIG_PATH)
    document = CanonicalDocument(
        canonical_id="paper-1",
        title="A BERT study",
        abstract="No additional signal.",
        reconciliation_key="paper-1",
    )
    embedded = CanonicalDocument(
        canonical_id="paper-2",
        title="ABERTX study",
        abstract="No additional signal.",
        reconciliation_key="paper-2",
    )

    assert document_matches_enrichment_type(
        document,
        entity_type=ScientificEntityType.MODEL,
        config=config,
    )
    assert not document_matches_enrichment_type(
        embedded,
        entity_type=ScientificEntityType.MODEL,
        config=config,
    )


def test_annotation_mention_rejects_blank_reviewer_note() -> None:
    with pytest.raises(ValidationError):
        ScientificEntityBlindAnnotationMention(
            entity_type="model",
            char_start=0,
            char_end=4,
            surface_text="BERT",
            uncertain=True,
            reviewer_note="   ",
        )
