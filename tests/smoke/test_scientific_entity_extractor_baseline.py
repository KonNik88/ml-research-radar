from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntitySourceField,
    ScientificEntityType,
)
from radar_core.entities.scientific_entity_baseline import (
    CODE_REVISION_PREFIX,
    LiteralScientificEntityExtractor,
    ScientificEntityBaselineError,
    ScientificEntityLiteralBaselineConfig,
    baseline_config_sha256,
    build_rule_extractor_descriptor,
    load_baseline_config,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "scientific_entity_extractor_baseline_v0.1.yaml"
FIXTURE_DIR = (
    ROOT / "tests" / "fixtures" / "scientific_entity_extractor_baseline_v0_1"
)
ZERO_SHA = "0" * 64
ONE_SHA = "1" * 64


def _config() -> ScientificEntityLiteralBaselineConfig:
    return load_baseline_config(CONFIG_PATH)


def _extractor(
    config: ScientificEntityLiteralBaselineConfig | None = None,
) -> LiteralScientificEntityExtractor:
    selected = config or _config()
    descriptor = build_rule_extractor_descriptor(
        config=selected,
        config_sha256=baseline_config_sha256(selected),
        environment_sha256=ZERO_SHA,
        code_revision=f"{CODE_REVISION_PREFIX}{ONE_SHA}",
    )
    return LiteralScientificEntityExtractor(
        config=selected,
        descriptor=descriptor,
    )


def _rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _semantic_candidates() -> list[dict[str, object]]:
    extractor = _extractor()
    actual: list[dict[str, object]] = []
    for document in _rows(FIXTURE_DIR / "canonical_documents.jsonl"):
        for field in ScientificEntitySourceField:
            text = document[field.value]
            if not isinstance(text, str) or not text:
                continue
            candidates = extractor.extract(
                canonical_id=str(document["canonical_id"]),
                source_field=field,
                source_text=text,
            )
            for candidate in candidates:
                actual.append(
                    {
                        "canonical_id": document["canonical_id"],
                        "source_field": field.value,
                        "entity_type": candidate.entity_type.value,
                        "char_start": candidate.char_start,
                        "char_end": candidate.char_end,
                        "surface_text": text[candidate.char_start : candidate.char_end],
                    }
                )
    return actual


def _config_with_rules(rules: list[dict[str, object]]) -> ScientificEntityLiteralBaselineConfig:
    payload = _config().model_dump(mode="json")
    payload["rules"] = rules
    return ScientificEntityLiteralBaselineConfig.model_validate(payload)


def test_default_config_is_reference_baseline_and_covers_all_types() -> None:
    config = _config()

    assert config.layer.status == "reference_baseline"
    assert {rule.entity_type for rule in config.rules} == set(ScientificEntityType)
    assert config.safety.default_max_documents == 32
    assert config.safety.hard_max_documents == 100
    assert config.safety.forbid_current_canonical_input is True
    assert config.safety.accepted_status_may_be_emitted is False


def test_config_fingerprint_is_semantic_and_deterministic() -> None:
    config = _config()
    reparsed = ScientificEntityLiteralBaselineConfig.model_validate(
        config.model_dump(mode="json")
    )

    assert baseline_config_sha256(config) == baseline_config_sha256(reparsed)
    assert len(baseline_config_sha256(config)) == 64


def test_descriptor_is_rule_based_and_contains_no_model_provenance() -> None:
    descriptor = _extractor().descriptor

    assert descriptor.kind.value == "rule_based"
    assert descriptor.model_name is None
    assert descriptor.model_revision is None
    assert descriptor.model_artifact_sha256 is None
    assert descriptor.model_license is None


def test_synthetic_fixture_matches_exact_expected_spans() -> None:
    expected = _rows(FIXTURE_DIR / "expected_spans.jsonl")

    assert _semantic_candidates() == expected
    assert {row["entity_type"] for row in expected} == {
        entity_type.value for entity_type in ScientificEntityType
    }


def test_baseline_jsonl_fixtures_are_pinned_to_lf() -> None:
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    expected_rule = (
        "tests/fixtures/scientific_entity_extractor_baseline_v0_1/"
        "*.jsonl text eol=lf"
    )

    assert expected_rule in attributes
    for path in sorted(FIXTURE_DIR.glob("*.jsonl")):
        raw = path.read_bytes()
        assert b"\r" not in raw
        assert raw.endswith(b"\n")


def test_unicode_offsets_are_python_codepoint_offsets() -> None:
    extractor = _extractor()
    text = "метод β-VAE для classification"
    candidates = extractor.extract(
        canonical_id="unicode-paper",
        source_field=ScientificEntitySourceField.TITLE,
        source_text=text,
    )
    by_type = {candidate.entity_type: candidate for candidate in candidates}

    model = by_type[ScientificEntityType.MODEL]
    task = by_type[ScientificEntityType.TASK]
    assert text[model.char_start : model.char_end] == "β-VAE"
    assert model.char_start == text.index("β-VAE")
    assert text[task.char_start : task.char_end] == "classification"


def test_unicode_word_boundary_rejects_substrings() -> None:
    extractor = _extractor()
    candidates = extractor.extract(
        canonical_id="boundary-paper",
        source_field=ScientificEntitySourceField.TITLE,
        source_text="BioBERTology ImageNetX preclassification",
    )

    assert candidates == ()


def test_unicode_word_boundary_accepts_hyphen_delimited_term() -> None:
    extractor = _extractor()
    text = "BERT-based transfer learning"
    candidates = extractor.extract(
        canonical_id="hyphen-paper",
        source_field=ScientificEntitySourceField.TITLE,
        source_text=text,
    )

    assert [text[item.char_start : item.char_end] for item in candidates] == [
        "BERT",
        "transfer learning",
    ]


def test_case_sensitive_and_case_insensitive_rules_are_explicit() -> None:
    extractor = _extractor()
    text = "bert and NAIVE BAYES"
    candidates = extractor.extract(
        canonical_id="case-paper",
        source_field=ScientificEntitySourceField.ABSTRACT,
        source_text=text,
    )

    assert len(candidates) == 1
    assert candidates[0].entity_type == ScientificEntityType.METHOD
    assert text[candidates[0].char_start : candidates[0].char_end] == "NAIVE BAYES"


def test_overlapping_mentions_are_preserved() -> None:
    rules = _config().model_dump(mode="json")["rules"]
    rules.append({"entity_type": "metric", "term": "F1"})
    extractor = _extractor(_config_with_rules(rules))
    text = "F1 score"

    candidates = extractor.extract(
        canonical_id="overlap-paper",
        source_field=ScientificEntitySourceField.TITLE,
        source_text=text,
    )

    assert [(item.char_start, item.char_end) for item in candidates] == [(0, 2), (0, 8)]


def test_same_span_multiple_types_are_preserved() -> None:
    rules = _config().model_dump(mode="json")["rules"]
    rules.append({"entity_type": "domain", "term": "classification"})
    extractor = _extractor(_config_with_rules(rules))

    candidates = extractor.extract(
        canonical_id="multi-type-paper",
        source_field=ScientificEntitySourceField.TITLE,
        source_text="classification",
    )

    assert {item.entity_type for item in candidates} == {
        ScientificEntityType.TASK,
        ScientificEntityType.DOMAIN,
    }
    assert {(item.char_start, item.char_end) for item in candidates} == {(0, 14)}


def test_duplicate_rules_fail_closed() -> None:
    rules = _config().model_dump(mode="json")["rules"]
    rules.append({"entity_type": "model", "term": "BERT"})

    with pytest.raises(ValidationError, match="duplicate literal rule"):
        _config_with_rules(rules)


def test_missing_entity_type_coverage_fails_closed() -> None:
    rules = [
        rule
        for rule in _config().model_dump(mode="json")["rules"]
        if rule["entity_type"] != "domain"
    ]

    with pytest.raises(ValidationError, match="cover all six"):
        _config_with_rules(rules)


def test_rule_terms_with_outer_whitespace_fail_closed() -> None:
    rules = _config().model_dump(mode="json")["rules"]
    rules.append({"entity_type": "model", "term": " BERT"})

    with pytest.raises(ValidationError, match="leading or trailing"):
        _config_with_rules(rules)


def test_duplicate_yaml_keys_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text(
        CONFIG_PATH.read_text(encoding="utf-8") + "\nrules: []\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ScientificEntityBaselineError, match="duplicate key"):
        load_baseline_config(path)
