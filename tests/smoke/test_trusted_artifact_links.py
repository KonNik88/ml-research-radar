from __future__ import annotations

from radar_core.artifacts.trusted_links import (
    TRUSTED_LINK_POLICY_VERSION,
    build_trusted_link_rows,
    is_trusted_observation,
)


def base_observation(**overrides):
    row = {
        "observation_id": "obs_1",
        "artifact_id": "artifact_1",
        "artifact_type": "github_repository",
        "provider": "github",
        "raw_url": "https://github.com/example/repo",
        "normalized_url": "https://github.com/example/repo",
        "canonical_id": "paper_1",
        "source_layer": "canonical",
        "source_name": "arxiv",
        "source_doc_id": "arxiv:1234.5678",
        "source_field": "code_links",
        "relation_type": "code",
        "confidence": 0.9,
    }
    row.update(overrides)
    return row


def test_provider_specific_trusted_type_with_sufficient_confidence_is_trusted():
    obs = base_observation(artifact_type="github_repository", provider="github", confidence=0.65)

    assert is_trusted_observation(obs) is True


def test_provider_specific_trusted_type_with_low_confidence_is_untrusted():
    obs = base_observation(artifact_type="github_repository", provider="github", confidence=0.64)

    assert is_trusted_observation(obs) is False


def test_generic_trusted_field_with_high_confidence_is_trusted():
    obs = base_observation(
        artifact_type="generic_code_url",
        provider="generic",
        source_field="code_links",
        normalized_url="https://example.org/project",
        confidence=0.9,
    )

    assert is_trusted_observation(obs) is True


def test_generic_abstract_field_is_untrusted_even_with_high_confidence():
    obs = base_observation(
        artifact_type="generic_code_url",
        provider="generic",
        source_field="abstract",
        normalized_url="https://example.org/project",
        confidence=0.99,
    )

    assert is_trusted_observation(obs) is False


def test_generic_bibliographic_domain_is_untrusted():
    obs = base_observation(
        artifact_type="generic_code_url",
        provider="generic",
        source_field="code_links",
        normalized_url="https://doi.org/10.1234/example",
        confidence=0.99,
    )

    assert is_trusted_observation(obs) is False


def test_missing_canonical_id_is_untrusted():
    obs = base_observation(canonical_id=None)

    assert is_trusted_observation(obs) is False


def test_missing_artifact_id_is_untrusted():
    obs = base_observation(artifact_id=None)

    assert is_trusted_observation(obs) is False


def test_unknown_relation_type_is_untrusted():
    obs = base_observation(relation_type="unknown")

    assert is_trusted_observation(obs) is False


def test_technical_noise_domain_is_untrusted():
    obs = base_observation(
        artifact_type="generic_code_url",
        provider="generic",
        source_field="code_links",
        normalized_url="https://www.w3.org/TR/example",
        confidence=0.99,
    )

    assert is_trusted_observation(obs) is False


def test_build_trusted_link_rows_dedupes_by_paper_artifact_relation_and_keeps_evidence():
    first = base_observation(
        observation_id="obs_1",
        confidence=0.7,
        source_field="repo_url",
        source_doc_id="doc_1",
    )
    second = base_observation(
        observation_id="obs_2",
        confidence=0.95,
        source_field="code_links",
        source_doc_id="doc_2",
    )

    rows = build_trusted_link_rows([first, second])

    assert len(rows) == 1
    row = rows[0]
    assert row["canonical_id"] == "paper_1"
    assert row["artifact_id"] == "artifact_1"
    assert row["relation_type"] == "code"
    assert row["confidence"] == 0.95
    assert row["source_field"] == "code_links"
    assert row["source_doc_id"] == "doc_2"
    assert row["metadata"]["observation_ids"] == ["obs_1", "obs_2"]
    assert len(row["metadata"]["evidence"]) == 2
    assert row["metadata"]["trusted_link_policy_version"] == TRUSTED_LINK_POLICY_VERSION


def test_build_trusted_link_rows_excludes_untrusted_observations():
    trusted = base_observation(observation_id="trusted_obs")
    untrusted = base_observation(
        observation_id="untrusted_obs",
        artifact_type="generic_code_url",
        provider="generic",
        source_field="abstract",
        normalized_url="https://example.org/project",
        confidence=0.99,
    )

    rows = build_trusted_link_rows([trusted, untrusted])

    assert len(rows) == 1
    assert rows[0]["metadata"]["observation_ids"] == ["trusted_obs"]
