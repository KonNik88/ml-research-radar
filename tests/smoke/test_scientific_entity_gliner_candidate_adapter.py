from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

import pytest

from radar_core.contracts.scientific_entity_evidence import (
    ConfidenceKind,
    EntityEvidenceBuildStatus,
    ExtractorKind,
    ScientificEntitySourceField,
    ScientificEntityType,
)
from radar_core.entities.scientific_entity_gliner import (
    GLiNERBackend,
    PreparedText,
    ScientificEntityGLiNERAdapter,
    ScientificEntityGLiNERConfig,
    ScientificEntityGLiNERError,
    build_gliner_extractor_descriptor,
    gliner_config_sha256,
    load_gliner_config,
    pinned_backbone_config_resolution,
)
from scripts.entities.build_scientific_entity_evidence_gliner import (
    REQUIRED_FILES,
    ScientificEntityGLiNERBuildError,
    build_gliner_candidate,
)
import scripts.entities.build_scientific_entity_evidence_gliner as builder_module
from scripts.validation.check_scientific_entity_gliner_build import (
    validate_gliner_build,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "scientific_entity_gliner_candidate_v0.1.yaml"
FIXTURE_INPUT = (
    ROOT
    / "tests"
    / "fixtures"
    / "scientific_entity_gliner_candidate_v0_1"
    / "canonical_documents.jsonl"
)
FIXED_TIME = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)


class FakeGLiNERBackend(GLiNERBackend):
    model_max_tokens = 384
    model_max_width = 12

    TERMS = {
        "BERT": ("model", 0.91),
        "BioBERT": ("model", 0.93),
        "ImageNet": ("dataset", 0.94),
        "BC5CDR": ("dataset", 0.92),
        "classification": ("task", 0.88),
        "Named entity recognition": ("task", 0.89),
        "F1 score": ("metric", 0.87),
        "accuracy": ("metric", 0.86),
        "contrastive learning": ("method", 0.9),
        "medical imaging": ("domain", 0.85),
        "tail method": ("method", 0.82),
    }

    def __init__(self, config: ScientificEntityGLiNERConfig) -> None:
        self.prompt_by_type = {
            item.entity_type.value: item.prompt for item in config.inference.labels
        }

    def prepare_text(self, text: str, labels: Sequence[str]) -> PreparedText:
        del labels
        matches = list(re.finditer(r"\w+|[^\w\s]", text, flags=re.UNICODE))
        return PreparedText(
            tokens=tuple(match.group(0) for match in matches),
            token_starts=tuple(match.start() for match in matches),
            token_ends=tuple(match.end() for match in matches),
        )

    def predict_entities(
        self,
        text: str,
        labels: Sequence[str],
        *,
        threshold: float,
        flat_ner: bool,
        multi_label: bool,
    ) -> Sequence[Mapping[str, Any]]:
        del labels, flat_ner, multi_label
        predictions: list[dict[str, Any]] = []
        for term, (entity_type, score) in self.TERMS.items():
            start = 0
            while True:
                start = text.find(term, start)
                if start < 0:
                    break
                if score >= threshold:
                    predictions.append(
                        {
                            "start": start,
                            "end": start + len(term),
                            "text": term,
                            "label": self.prompt_by_type[entity_type],
                            "score": score,
                        }
                    )
                start += 1
        return predictions


class BrokenBackend(FakeGLiNERBackend):
    def __init__(
        self,
        config: ScientificEntityGLiNERConfig,
        prediction: Mapping[str, Any],
    ) -> None:
        super().__init__(config)
        self.prediction = prediction

    def predict_entities(self, *args: Any, **kwargs: Any) -> Sequence[Mapping[str, Any]]:
        return [self.prediction]


def _descriptor(config: ScientificEntityGLiNERConfig):
    return build_gliner_extractor_descriptor(
        config=config,
        config_sha256=gliner_config_sha256(config),
        environment_sha256="1" * 64,
        code_revision="normalized-source-sha256:" + "2" * 64,
    )


def _adapter(
    config: ScientificEntityGLiNERConfig | None = None,
    backend: GLiNERBackend | None = None,
) -> ScientificEntityGLiNERAdapter:
    selected = config or load_gliner_config(CONFIG_PATH)
    return ScientificEntityGLiNERAdapter(
        config=selected,
        descriptor=_descriptor(selected),
        backend=backend or FakeGLiNERBackend(selected),
    )


def _execute(tmp_path: Path, *, build_id: str = "gliner-fixture-test-v0.1"):
    config = load_gliner_config(CONFIG_PATH)
    report = build_gliner_candidate(
        output_root=tmp_path,
        build_id=build_id,
        execute=True,
        generated_at_utc=FIXED_TIME,
        backend=FakeGLiNERBackend(config),
    )
    return report, tmp_path / build_id


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _check_map(report: dict[str, Any]) -> dict[str, bool]:
    return {row["name"]: row["ok"] for row in report["checks"]}


def test_config_pins_model_revision_artifact_and_runtime() -> None:
    config = load_gliner_config(CONFIG_PATH)

    assert config.model.repository == "gliner-community/gliner_small-v2.5"
    assert config.model.revision == "f227d3cd637bd4e6757ae143935316d062393341"
    assert config.model.artifact_sha256 == (
        "d444ff406b27affc07e3165b454c3adc9f25f228c81ede197a7b806f49d12c74"
    )
    assert config.model.library_version == "0.2.28"
    assert config.model.backbone_config.repository == "microsoft/deberta-v3-small"
    assert config.model.backbone_config.revision == (
        "a36c739020e01763fe789b4b85e2df55d6180012"
    )
    assert config.model.backbone_config.artifact_size_bytes == 578
    assert config.model.backbone_config.artifact_sha256 == (
        "b0bb1caf90a50aa67d1085130508dfbf8646ac5a11928305e280b07a36e100ae"
    )
    assert config.model.backbone_config.resolution_policy == (
        "verified_local_config_injection"
    )
    assert config.safety.hard_max_documents == 100
    assert config.safety.accepted_status_may_be_emitted is False


def test_pinned_backbone_config_resolution_injects_verified_payload_and_restores() -> None:
    calls: list[dict[str, Any]] = []

    class OriginalAutoConfig:
        @staticmethod
        def from_pretrained(*args: Any, **kwargs: Any) -> None:
            raise AssertionError((args, kwargs))

    class FakeBackboneConfig:
        @classmethod
        def from_dict(cls, payload: dict[str, Any]) -> dict[str, Any]:
            calls.append(payload)
            return {"loaded": payload}

    encoder_module = SimpleNamespace(AutoConfig=OriginalAutoConfig)
    payload = {"model_type": "deberta-v2", "hidden_size": 768}

    with pinned_backbone_config_resolution(
        gliner_encoder_module=encoder_module,
        backbone_config_class=FakeBackboneConfig,
        repository="microsoft/deberta-v3-small",
        payload=payload,
    ) as state:
        resolved = encoder_module.AutoConfig.from_pretrained(
            "microsoft/deberta-v3-small",
            cache_dir="ignored-by-injected-resolution",
        )

    assert resolved == {"loaded": payload}
    assert calls == [payload]
    assert state["resolution_count"] == 1
    assert encoder_module.AutoConfig is OriginalAutoConfig


@pytest.mark.parametrize(
    "repository,kwargs,match",
    [
        ("unpinned/backbone", {}, "unpinned backbone"),
        ("microsoft/deberta-v3-small", {"revision": "floating"}, "Unexpected"),
    ],
)
def test_pinned_backbone_config_resolution_fails_closed_and_restores(
    repository: str,
    kwargs: dict[str, Any],
    match: str,
) -> None:
    class OriginalAutoConfig:
        @staticmethod
        def from_pretrained(*args: Any, **kwargs: Any) -> None:
            raise AssertionError((args, kwargs))

    class FakeBackboneConfig:
        @classmethod
        def from_dict(cls, payload: dict[str, Any]) -> dict[str, Any]:
            return payload

    encoder_module = SimpleNamespace(AutoConfig=OriginalAutoConfig)
    with pinned_backbone_config_resolution(
        gliner_encoder_module=encoder_module,
        backbone_config_class=FakeBackboneConfig,
        repository="microsoft/deberta-v3-small",
        payload={"model_type": "deberta-v2"},
    ):
        with pytest.raises(ScientificEntityGLiNERError, match=match):
            encoder_module.AutoConfig.from_pretrained(repository, **kwargs)

    assert encoder_module.AutoConfig is OriginalAutoConfig


def test_pinned_backbone_config_resolution_restores_after_model_load_failure() -> None:
    class OriginalAutoConfig:
        @staticmethod
        def from_pretrained(*args: Any, **kwargs: Any) -> None:
            raise AssertionError((args, kwargs))

    class FakeBackboneConfig:
        @classmethod
        def from_dict(cls, payload: dict[str, Any]) -> dict[str, Any]:
            return payload

    encoder_module = SimpleNamespace(AutoConfig=OriginalAutoConfig)
    with pytest.raises(RuntimeError, match="model construction failed"):
        with pinned_backbone_config_resolution(
            gliner_encoder_module=encoder_module,
            backbone_config_class=FakeBackboneConfig,
            repository="microsoft/deberta-v3-small",
            payload={"model_type": "deberta-v2"},
        ):
            raise RuntimeError("model construction failed")

    assert encoder_module.AutoConfig is OriginalAutoConfig


def test_config_has_exact_six_contract_labels() -> None:
    config = load_gliner_config(CONFIG_PATH)

    assert {item.entity_type for item in config.inference.labels} == set(
        ScientificEntityType
    )
    assert config.inference.flat_ner is False
    assert config.inference.multi_label is False


def test_descriptor_has_complete_model_provenance() -> None:
    config = load_gliner_config(CONFIG_PATH)
    descriptor = _descriptor(config)

    assert descriptor.kind == ExtractorKind.STATISTICAL_MODEL
    assert descriptor.model_name == config.model.repository
    assert descriptor.model_revision == config.model.revision
    assert descriptor.model_artifact_sha256 == config.model.artifact_sha256
    assert descriptor.model_license == "Apache-2.0"


def test_adapter_returns_exact_scored_spans() -> None:
    text = "BERT uses contrastive learning on ImageNet with F1 score."
    result = _adapter().extract(
        canonical_id="synthetic",
        source_field=ScientificEntitySourceField.ABSTRACT,
        source_text=text,
    )

    semantic = {
        (item.entity_type.value, text[item.char_start : item.char_end], item.score)
        for item in result.candidates
    }
    assert semantic == {
        ("model", "BERT", 0.91),
        ("method", "contrastive learning", 0.9),
        ("dataset", "ImageNet", 0.94),
        ("metric", "F1 score", 0.87),
    }


def test_adapter_windows_long_text_without_losing_tail() -> None:
    payload = load_gliner_config(CONFIG_PATH).model_dump(mode="json")
    payload["inference"]["window_size_tokens"] = 32
    payload["inference"]["window_overlap_tokens"] = 8
    config = ScientificEntityGLiNERConfig.model_validate(payload)
    backend = FakeGLiNERBackend(config)
    backend.model_max_tokens = 32
    backend.model_max_width = 4
    text = " ".join([f"token{i}" for i in range(50)]) + " tail method"

    result = _adapter(config, backend).extract(
        canonical_id="synthetic",
        source_field=ScientificEntitySourceField.ABSTRACT,
        source_text=text,
    )

    assert result.windowed is True
    assert result.window_count == 2
    assert [text[item.char_start : item.char_end] for item in result.candidates] == [
        "tail method"
    ]


def test_adapter_reconciles_overlap_duplicates_by_exact_identity() -> None:
    payload = load_gliner_config(CONFIG_PATH).model_dump(mode="json")
    payload["inference"]["window_size_tokens"] = 32
    payload["inference"]["window_overlap_tokens"] = 16
    config = ScientificEntityGLiNERConfig.model_validate(payload)
    backend = FakeGLiNERBackend(config)
    backend.model_max_tokens = 32
    backend.model_max_width = 4
    text = " ".join([f"token{i}" for i in range(20)]) + " tail method " + " ".join(
        [f"suffix{i}" for i in range(20)]
    )

    result = _adapter(config, backend).extract(
        canonical_id="synthetic",
        source_field=ScientificEntitySourceField.ABSTRACT,
        source_text=text,
    )

    assert len(result.candidates) == 1
    assert result.candidates[0].score == 0.82


@pytest.mark.parametrize(
    "prediction,match",
    [
        (
            {"start": 0, "end": 4, "text": "wrong", "label": "model architecture or named system", "score": 0.9},
            "surface",
        ),
        (
            {"start": 0, "end": 4, "text": "BERT", "label": "unknown", "score": 0.9},
            "Unknown",
        ),
        (
            {"start": 0, "end": 4, "text": "BERT", "label": "model architecture or named system", "score": float("nan")},
            "finite",
        ),
    ],
)
def test_adapter_fails_closed_on_malformed_prediction(
    prediction: Mapping[str, Any],
    match: str,
) -> None:
    config = load_gliner_config(CONFIG_PATH)
    with pytest.raises(ScientificEntityGLiNERError, match=match):
        _adapter(config, BrokenBackend(config, prediction)).extract(
            canonical_id="synthetic",
            source_field=ScientificEntitySourceField.TITLE,
            source_text="BERT",
        )


def test_plan_mode_with_injected_fixture_backend_writes_nothing(tmp_path: Path) -> None:
    config = load_gliner_config(CONFIG_PATH)
    output_root = tmp_path / "plan"

    report = build_gliner_candidate(
        output_root=output_root,
        build_id="gliner-plan-v0.1",
        generated_at_utc=FIXED_TIME,
        backend=FakeGLiNERBackend(config),
    )

    assert report["mode"] == "plan"
    assert report["phase_complete"] is False
    assert report["input_document_count"] == 2
    assert report["mention_count"] > 0
    assert report["model_weights_downloaded"] is False
    assert report["backbone_config_verified"] is False
    assert report["backbone_config_injected"] is False
    assert not output_root.exists()


@pytest.mark.parametrize("allow_download", [False, True])
def test_model_download_permission_is_forwarded_only_when_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    allow_download: bool,
) -> None:
    captured: dict[str, Any] = {}

    class LoaderReached(RuntimeError):
        pass

    def fake_loader(
        *,
        config: ScientificEntityGLiNERConfig,
        allow_model_download: bool,
        cache_dir: Path | None,
    ) -> None:
        del config, cache_dir
        captured["allow_model_download"] = allow_model_download
        raise LoaderReached

    monkeypatch.setattr(builder_module, "load_native_gliner_backend", fake_loader)
    with pytest.raises(LoaderReached):
        build_gliner_candidate(
            output_root=tmp_path,
            build_id="download-boundary-v0.1",
            allow_model_download=allow_download,
            generated_at_utc=FIXED_TIME,
        )

    assert captured["allow_model_download"] is allow_download
    assert list(tmp_path.iterdir()) == []


def test_execute_creates_exact_immutable_layout_and_model_scores(tmp_path: Path) -> None:
    report, build_dir = _execute(tmp_path)
    records = _read_jsonl(build_dir / "mentions.jsonl")

    assert report["phase_complete"] is True
    assert {path.name for path in build_dir.iterdir()} == set(REQUIRED_FILES)
    assert all(row["confidence_kind"] == ConfidenceKind.MODEL_SCORE.value for row in records)
    assert all(0.5 <= row["confidence_score"] <= 1.0 for row in records)


def test_independent_validator_accepts_injected_tracked_fixture(tmp_path: Path) -> None:
    _, build_dir = _execute(tmp_path)

    report = validate_gliner_build(build_dir=build_dir, write_reports=False)

    assert report["summary"]["ok"] is True
    assert report["summary"]["required_failed_count"] == 0
    assert _check_map(report)["code_revision_matches_current_source"] is True
    assert report["verdict"]["production_extractor_selected"] is False
    assert report["verdict"]["full_corpus_build_authorized"] is False


def test_execute_never_overwrites_existing_build(tmp_path: Path) -> None:
    _, build_dir = _execute(tmp_path)
    before = (build_dir / "manifest.json").read_bytes()

    with pytest.raises(FileExistsError, match="overwrite is forbidden"):
        _execute(tmp_path)

    assert (build_dir / "manifest.json").read_bytes() == before


def test_fixed_fixture_builds_are_byte_deterministic(tmp_path: Path) -> None:
    config = load_gliner_config(CONFIG_PATH)
    build_id = "deterministic-gliner-fixture-v0.1"
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    for root in (first_root, second_root):
        build_gliner_candidate(
            output_root=root,
            build_id=build_id,
            execute=True,
            generated_at_utc=FIXED_TIME,
            backend=FakeGLiNERBackend(config),
        )

    first = first_root / build_id
    second = second_root / build_id
    assert {name: (first / name).read_bytes() for name in REQUIRED_FILES} == {
        name: (second / name).read_bytes() for name in REQUIRED_FILES
    }


def test_accepted_status_is_forbidden(tmp_path: Path) -> None:
    config = load_gliner_config(CONFIG_PATH)
    with pytest.raises(ScientificEntityGLiNERBuildError, match="accepted"):
        build_gliner_candidate(
            output_root=tmp_path,
            status=EntityEvidenceBuildStatus.ACCEPTED,
            backend=FakeGLiNERBackend(config),
        )


def test_hard_document_limit_is_enforced(tmp_path: Path) -> None:
    config = load_gliner_config(CONFIG_PATH)
    with pytest.raises(ScientificEntityGLiNERBuildError, match="hard limit"):
        build_gliner_candidate(
            output_root=tmp_path,
            max_documents=101,
            backend=FakeGLiNERBackend(config),
        )


def test_current_canonical_input_is_forbidden(tmp_path: Path) -> None:
    config = load_gliner_config(CONFIG_PATH)
    with pytest.raises(ScientificEntityGLiNERBuildError, match="canonical corpus"):
        build_gliner_candidate(
            input_path=ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl",
            output_root=tmp_path,
            status="candidate",
            backend=FakeGLiNERBackend(config),
        )


def test_injected_backend_cannot_emit_candidate_build(tmp_path: Path) -> None:
    config = load_gliner_config(CONFIG_PATH)
    candidate = tmp_path / "candidate.jsonl"
    candidate.write_bytes(FIXTURE_INPUT.read_bytes())

    with pytest.raises(ScientificEntityGLiNERBuildError, match="Injected test backends"):
        build_gliner_candidate(
            input_path=candidate,
            output_root=tmp_path / "output",
            status="candidate",
            backend=FakeGLiNERBackend(config),
        )


def test_validator_rejects_corrupt_model_score(tmp_path: Path) -> None:
    _, build_dir = _execute(tmp_path)
    mention_path = build_dir / "mentions.jsonl"
    rows = _read_jsonl(mention_path)
    rows[0]["confidence_score"] = None
    mention_path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )

    report = validate_gliner_build(build_dir=build_dir, write_reports=False)

    assert report["summary"]["ok"] is False
    assert _check_map(report)["mention_records_schema_valid"] is False


def test_validator_rejects_corrupt_backbone_config_provenance(
    tmp_path: Path,
) -> None:
    _, build_dir = _execute(tmp_path)
    quality_path = build_dir / "data_quality_summary.json"
    quality = _read_json(quality_path)
    quality["backbone_config_revision"] = "floating"
    quality_path.write_text(
        json.dumps(quality, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    report = validate_gliner_build(build_dir=build_dir, write_reports=False)

    assert report["summary"]["ok"] is False
    assert _check_map(report)["quality_backbone_config_provenance"] is False


def test_all_generated_files_are_utf8_lf(tmp_path: Path) -> None:
    _, build_dir = _execute(tmp_path)
    for filename in REQUIRED_FILES:
        raw = (build_dir / filename).read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert b"\r" not in raw
        assert raw.endswith(b"\n")
        raw.decode("utf-8")
