from __future__ import annotations

import hashlib
import json
import math
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Literal, Mapping, Protocol, Sequence

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import (
    EXTRACTOR_SCHEMA_VERSION,
    ExtractorKind,
    ScientificEntityExtractorDescriptor,
    ScientificEntitySourceField,
    ScientificEntityType,
    sha256_text,
)
from radar_core.entities.scientific_entity_baseline import (
    CODE_REVISION_PREFIX,
    DATA_QUALITY_SCHEMA_VERSION,
    OUTPUT_SCHEMA_VERSION,
    canonical_semantic_json,
)


GLINER_CONFIG_SCHEMA_VERSION = "scientific_entity_gliner_candidate_config_v0.1"
GLINER_QUALITY_SCHEMA_VERSION = "scientific_entity_gliner_quality_v0.1"
GLINER_CODE_REVISION_FILES = (
    "radar_core/contracts/scientific_entity_evidence.py",
    "radar_core/entities/scientific_entity_gliner.py",
    "scripts/entities/build_scientific_entity_evidence_gliner.py",
)
_BACKBONE_CONFIG_INJECTION_LOCK = RLock()


class ScientificEntityGLiNERError(ValueError):
    """Raised when GLiNER configuration, loading, or inference fails closed."""


class GLiNERLayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["bounded_scientific_entity_gliner_candidate_adapter"]
    version: Literal["v0.1"]
    status: Literal["experimental_candidate"]
    layer_kind: Literal["derived_candidate_mention_evidence"]
    description: str = Field(min_length=1)


class GLiNERExtractorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    kind: Literal["statistical_model"]
    environment_lock_path: Literal[
        "requirements/requirements.entities_gliner.lock.txt"
    ]
    code_revision_policy: Literal["normalized_source_bundle_sha256"]
    config_fingerprint_policy: Literal["sha256_of_canonical_semantic_json"]
    confidence_kind: Literal["model_score"]


class GLiNERBackboneConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: Literal["microsoft/deberta-v3-small"]
    revision: Literal["a36c739020e01763fe789b4b85e2df55d6180012"]
    artifact_filename: Literal["config.json"]
    artifact_sha256: Literal[
        "b0bb1caf90a50aa67d1085130508dfbf8646ac5a11928305e280b07a36e100ae"
    ]
    artifact_size_bytes: Literal[578]
    model_type: Literal["deberta-v2"]
    resolution_policy: Literal["verified_local_config_injection"]


class GLiNERModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: Literal["gliner-community/gliner_small-v2.5"]
    revision: Literal["f227d3cd637bd4e6757ae143935316d062393341"]
    variant: Literal["fp16"]
    artifact_filename: Literal["model.fp16.safetensors"]
    artifact_sha256: Literal[
        "d444ff406b27affc07e3165b454c3adc9f25f228c81ede197a7b806f49d12c74"
    ]
    artifact_size_bytes: Literal[332065392]
    license: Literal["Apache-2.0"]
    library: Literal["gliner"]
    library_version: Literal["0.2.28"]
    required_snapshot_files: list[str] = Field(min_length=1)
    backbone_config: GLiNERBackboneConfig

    @model_validator(mode="after")
    def validate_snapshot_files(self) -> "GLiNERModelConfig":
        required = {
            "added_tokens.json",
            "gliner_config.json",
            "model.fp16.safetensors",
            "special_tokens_map.json",
            "spm.model",
            "tokenizer.json",
            "tokenizer_config.json",
        }
        if set(self.required_snapshot_files) != required:
            raise ValueError("required_snapshot_files must match the pinned v0.1 set")
        if len(set(self.required_snapshot_files)) != len(self.required_snapshot_files):
            raise ValueError("required_snapshot_files must not contain duplicates")
        return self


class GLiNERLabelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: ScientificEntityType
    prompt: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_prompt(self) -> "GLiNERLabelConfig":
        if self.prompt != self.prompt.strip() or not self.prompt.strip():
            raise ValueError("label prompt must be non-blank and trimmed")
        return self


class GLiNERInferenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_fields: list[ScientificEntitySourceField] = Field(min_length=2, max_length=2)
    threshold: float = Field(ge=0.0, le=1.0)
    flat_ner: Literal[False]
    multi_label: Literal[False]
    window_size_tokens: int = Field(ge=32, le=384)
    window_overlap_tokens: int = Field(ge=0)
    batch_size: Literal[1]
    device: Literal["cpu", "cuda"]
    seed: int = Field(ge=0)
    normalization_before_offsets: Literal["forbidden"]
    surface_from_exact_source_slice: Literal[True]
    overlap_reconciliation: Literal["highest_score_per_exact_span_and_type"]
    labels: list[GLiNERLabelConfig] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_inference_contract(self) -> "GLiNERInferenceConfig":
        if set(self.source_fields) != set(ScientificEntitySourceField):
            raise ValueError("source_fields must be exactly title and abstract")
        if len(set(self.source_fields)) != len(self.source_fields):
            raise ValueError("source_fields must not contain duplicates")
        if self.window_overlap_tokens >= self.window_size_tokens:
            raise ValueError("window overlap must be smaller than window size")
        entity_types = [label.entity_type for label in self.labels]
        prompts = [label.prompt.casefold() for label in self.labels]
        if set(entity_types) != set(ScientificEntityType) or len(set(entity_types)) != 6:
            raise ValueError("labels must cover each scientific entity type once")
        if len(set(prompts)) != len(prompts):
            raise ValueError("label prompts must be unique")
        return self


class GLiNERSafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_max_documents: Literal[32]
    hard_max_documents: Literal[100]
    fail_if_input_exceeds_limit: Literal[True]
    truncation_allowed: Literal[False]
    forbid_current_canonical_input: Literal[True]
    current_canonical_path: Literal[
        "data/analytics/reconciled/canonical_documents.jsonl"
    ]
    allowed_build_statuses: list[Literal["fixture", "candidate"]] = Field(
        min_length=2, max_length=2
    )
    accepted_status_may_be_emitted: Literal[False]
    execute_required_for_writes: Literal[True]
    overwrite_allowed: Literal[False]
    model_download_requires_explicit_flag: Literal[True]
    provider_api_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    publication_allowed: Literal[False]

    @model_validator(mode="after")
    def validate_safety(self) -> "GLiNERSafetyConfig":
        if set(self.allowed_build_statuses) != {"fixture", "candidate"}:
            raise ValueError("allowed statuses must be fixture and candidate")
        return self


class GLiNEROutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root: str = Field(min_length=1)
    immutable_build_directory: Literal[True]
    mutable_latest_pointer: Literal[False]
    encoding: Literal["utf-8"]
    line_ending: Literal["lf"]
    required_files: list[str] = Field(min_length=6, max_length=6)


class GLiNERValidationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_dir: str = Field(min_length=1)
    require_independent_output_validator: Literal[True]
    require_exact_spans: Literal[True]
    require_deterministic_order: Literal[True]
    require_identity_recomputation: Literal[True]
    require_checksums: Literal[True]
    require_lf_outputs: Literal[True]
    require_bounded_input: Literal[True]
    require_model_artifact_hash: Literal[True]
    require_backbone_config_hash: Literal[True]
    require_no_silent_truncation: Literal[True]


class GLiNERFixturesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_input_path: Literal[
        "tests/fixtures/scientific_entity_gliner_candidate_v0_1/"
        "canonical_documents.jsonl"
    ]
    synthetic_only: Literal[True]


class ScientificEntityGLiNERConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[GLINER_CONFIG_SCHEMA_VERSION]
    layer: GLiNERLayerConfig
    extractor: GLiNERExtractorConfig
    model: GLiNERModelConfig
    inference: GLiNERInferenceConfig
    safety: GLiNERSafetyConfig
    outputs: GLiNEROutputsConfig
    validation: GLiNERValidationConfig
    fixtures: GLiNERFixturesConfig

    @model_validator(mode="after")
    def validate_output_layout(self) -> "ScientificEntityGLiNERConfig":
        expected = {
            "mentions.jsonl",
            "manifest.json",
            "schema.json",
            "data_quality_summary.json",
            "README.md",
            "checksums.txt",
        }
        if set(self.outputs.required_files) != expected:
            raise ValueError("outputs.required_files does not match v0.1 layout")
        if len(set(self.outputs.required_files)) != len(self.outputs.required_files):
            raise ValueError("outputs.required_files must not contain duplicates")
        return self


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key: {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_gliner_config(path: Path) -> ScientificEntityGLiNERConfig:
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError as exc:
        raise ScientificEntityGLiNERError(f"Invalid YAML config {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ScientificEntityGLiNERError(f"Expected YAML object: {path}")
    return ScientificEntityGLiNERConfig.model_validate(payload)


def gliner_config_sha256(config: ScientificEntityGLiNERConfig) -> str:
    return sha256_text(canonical_semantic_json(config.model_dump(mode="json")))


def normalized_text_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return sha256_text(text.replace("\r\n", "\n").replace("\r", "\n"))


def normalized_source_bundle_revision(project_root: Path) -> str:
    digest = hashlib.sha256()
    for relative_path in sorted(GLINER_CODE_REVISION_FILES):
        path = project_root / relative_path
        if not path.is_file():
            raise ScientificEntityGLiNERError(f"Code revision file is missing: {path}")
        text = path.read_text(encoding="utf-8")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(normalized.encode("utf-8"))
        digest.update(b"\0")
    return f"{CODE_REVISION_PREFIX}{digest.hexdigest()}"


def build_gliner_extractor_descriptor(
    *,
    config: ScientificEntityGLiNERConfig,
    config_sha256: str,
    environment_sha256: str,
    code_revision: str,
) -> ScientificEntityExtractorDescriptor:
    return ScientificEntityExtractorDescriptor(
        schema_version=EXTRACTOR_SCHEMA_VERSION,
        name=config.extractor.name,
        version=config.extractor.version,
        kind=ExtractorKind.STATISTICAL_MODEL,
        code_revision=code_revision,
        config_sha256=config_sha256,
        environment_sha256=environment_sha256,
        model_name=config.model.repository,
        model_revision=config.model.revision,
        model_artifact_sha256=config.model.artifact_sha256,
        model_license=config.model.license,
    )


@dataclass(frozen=True, slots=True)
class PreparedText:
    tokens: tuple[str, ...]
    token_starts: tuple[int, ...]
    token_ends: tuple[int, ...]


class GLiNERBackend(Protocol):
    model_max_tokens: int
    model_max_width: int

    def prepare_text(self, text: str, labels: Sequence[str]) -> PreparedText: ...

    def predict_entities(
        self,
        text: str,
        labels: Sequence[str],
        *,
        threshold: float,
        flat_ner: bool,
        multi_label: bool,
    ) -> Sequence[Mapping[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class GLiNERMentionCandidate:
    entity_type: ScientificEntityType
    char_start: int
    char_end: int
    score: float


@dataclass(frozen=True, slots=True)
class GLiNERExtractionResult:
    candidates: tuple[GLiNERMentionCandidate, ...]
    splitter_token_count: int
    window_count: int
    windowed: bool


@dataclass(frozen=True, slots=True)
class LoadedGLiNERBackend:
    backend: "NativeGLiNERBackend"
    snapshot_path: Path
    backbone_config_path: Path
    model_artifact_verified: bool
    backbone_config_verified: bool
    model_weights_downloaded: bool
    backbone_config_downloaded: bool
    backbone_config_injected: bool


class NativeGLiNERBackend:
    def __init__(self, model: Any) -> None:
        self._model = model
        self.model_max_tokens = int(model.config.max_len)
        self.model_max_width = int(model.config.max_width)

    def prepare_text(self, text: str, labels: Sequence[str]) -> PreparedText:
        payload = self._model.prepare_batch(text, list(labels))
        token_rows = payload.get("tokens") or []
        start_rows = payload.get("start_token_map") or []
        end_rows = payload.get("end_token_map") or []
        if not token_rows:
            return PreparedText(tokens=(), token_starts=(), token_ends=())
        if len(token_rows) != 1 or len(start_rows) != 1 or len(end_rows) != 1:
            raise ScientificEntityGLiNERError("prepare_batch returned an unexpected batch")
        tokens = tuple(str(value) for value in token_rows[0])
        starts = tuple(int(value) for value in start_rows[0])
        ends = tuple(int(value) for value in end_rows[0])
        if not (len(tokens) == len(starts) == len(ends)):
            raise ScientificEntityGLiNERError("prepare_batch token maps have unequal lengths")
        return PreparedText(tokens=tokens, token_starts=starts, token_ends=ends)

    def predict_entities(
        self,
        text: str,
        labels: Sequence[str],
        *,
        threshold: float,
        flat_ner: bool,
        multi_label: bool,
    ) -> Sequence[Mapping[str, Any]]:
        import torch

        with torch.inference_mode():
            result = self._model.predict_entities(
                text,
                list(labels),
                threshold=threshold,
                flat_ner=flat_ner,
                multi_label=multi_label,
            )
        if not isinstance(result, list):
            raise ScientificEntityGLiNERError("predict_entities returned a non-list result")
        return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_verified_backbone_config_payload(
    *,
    path: Path,
    config: GLiNERBackboneConfig,
) -> dict[str, Any]:
    if not path.is_file():
        raise ScientificEntityGLiNERError(
            f"Pinned backbone config artifact is missing: {path}"
        )
    if path.stat().st_size != config.artifact_size_bytes:
        raise ScientificEntityGLiNERError(
            "Pinned backbone config artifact size does not match config"
        )
    if _sha256_file(path) != config.artifact_sha256:
        raise ScientificEntityGLiNERError(
            "Pinned backbone config artifact SHA-256 does not match config"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScientificEntityGLiNERError(
            f"Pinned backbone config artifact is invalid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ScientificEntityGLiNERError(
            "Pinned backbone config artifact must contain a JSON object"
        )
    if payload.get("model_type") != config.model_type:
        raise ScientificEntityGLiNERError(
            "Pinned backbone config model_type does not match config"
        )
    return payload


@contextmanager
def pinned_backbone_config_resolution(
    *,
    gliner_encoder_module: Any,
    backbone_config_class: Any,
    repository: str,
    payload: Mapping[str, Any],
):
    """Inject one verified local encoder config into GLiNER v0.2.28.

    GLiNER constructs its encoder from ``config.model_name`` and, when the
    checkpoint does not embed ``encoder_config``, resolves that name through
    ``AutoConfig.from_pretrained``.  The pinned adapter replaces only the
    module-local resolver while the model graph is constructed, returns a new
    config object from verified bytes, and restores the upstream resolver even
    when model construction fails.
    """

    frozen_payload = dict(payload)
    state = {"resolution_count": 0}

    class _PinnedAutoConfig:
        @staticmethod
        def from_pretrained(
            pretrained_model_name_or_path: Any,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            if args:
                raise ScientificEntityGLiNERError(
                    "Unexpected positional arguments in GLiNER backbone resolution"
                )
            if str(pretrained_model_name_or_path) != repository:
                raise ScientificEntityGLiNERError(
                    "GLiNER requested an unpinned backbone config repository: "
                    f"{pretrained_model_name_or_path!r}"
                )
            unexpected = set(kwargs) - {"cache_dir"}
            if unexpected:
                raise ScientificEntityGLiNERError(
                    "Unexpected GLiNER backbone config resolver arguments: "
                    f"{sorted(unexpected)}"
                )
            state["resolution_count"] += 1
            return backbone_config_class.from_dict(dict(frozen_payload))

    with _BACKBONE_CONFIG_INJECTION_LOCK:
        original_auto_config = getattr(gliner_encoder_module, "AutoConfig", None)
        if original_auto_config is None or not hasattr(
            original_auto_config, "from_pretrained"
        ):
            raise ScientificEntityGLiNERError(
                "GLiNER encoder AutoConfig hook is unavailable for pinned injection"
            )
        gliner_encoder_module.AutoConfig = _PinnedAutoConfig
        try:
            yield state
        finally:
            gliner_encoder_module.AutoConfig = original_auto_config


def load_native_gliner_backend(
    *,
    config: ScientificEntityGLiNERConfig,
    allow_model_download: bool,
    cache_dir: Path | None = None,
) -> LoadedGLiNERBackend:
    """Load the exact pinned snapshot; network use requires an explicit flag."""

    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except ImportError as exc:
        raise ScientificEntityGLiNERError(
            "huggingface_hub is required to resolve the pinned model snapshot"
        ) from exc

    cache_value = str(cache_dir.resolve()) if cache_dir is not None else None
    artifact_was_cached = True
    try:
        hf_hub_download(
            repo_id=config.model.repository,
            filename=config.model.artifact_filename,
            revision=config.model.revision,
            cache_dir=cache_value,
            local_files_only=True,
        )
    except Exception:
        artifact_was_cached = False

    backbone_config_was_cached = True
    try:
        hf_hub_download(
            repo_id=config.model.backbone_config.repository,
            filename=config.model.backbone_config.artifact_filename,
            revision=config.model.backbone_config.revision,
            cache_dir=cache_value,
            local_files_only=True,
        )
    except Exception:
        backbone_config_was_cached = False

    try:
        snapshot = Path(
            snapshot_download(
                repo_id=config.model.repository,
                revision=config.model.revision,
                cache_dir=cache_value,
                allow_patterns=list(config.model.required_snapshot_files),
                local_files_only=not allow_model_download,
            )
        ).resolve()
    except Exception as exc:
        boundary = "explicit download permitted" if allow_model_download else "offline-only"
        raise ScientificEntityGLiNERError(
            f"Pinned GLiNER snapshot is unavailable ({boundary}): {exc}"
        ) from exc

    try:
        backbone_config_path = Path(
            hf_hub_download(
                repo_id=config.model.backbone_config.repository,
                filename=config.model.backbone_config.artifact_filename,
                revision=config.model.backbone_config.revision,
                cache_dir=cache_value,
                local_files_only=not allow_model_download,
            )
        ).resolve()
    except Exception as exc:
        boundary = "explicit download permitted" if allow_model_download else "offline-only"
        raise ScientificEntityGLiNERError(
            f"Pinned backbone config is unavailable ({boundary}): {exc}"
        ) from exc

    artifact = snapshot / config.model.artifact_filename
    if not artifact.is_file():
        raise ScientificEntityGLiNERError(f"Pinned model artifact is missing: {artifact}")
    if artifact.stat().st_size != config.model.artifact_size_bytes:
        raise ScientificEntityGLiNERError("Pinned model artifact size does not match config")
    if _sha256_file(artifact) != config.model.artifact_sha256:
        raise ScientificEntityGLiNERError("Pinned model artifact SHA-256 does not match config")
    for filename in config.model.required_snapshot_files:
        if not (snapshot / filename).is_file():
            raise ScientificEntityGLiNERError(
                f"Pinned model snapshot file is missing: {filename}"
            )
    backbone_config_payload = _load_verified_backbone_config_payload(
        path=backbone_config_path,
        config=config.model.backbone_config,
    )

    try:
        import torch
        from gliner import GLiNER
        from gliner.modeling import encoder as gliner_encoder_module
        from transformers import DebertaV2Config
    except ImportError as exc:
        raise ScientificEntityGLiNERError(
            "Install the exact bounded GLiNER runtime lock before real inference"
        ) from exc

    if config.inference.device == "cuda" and not torch.cuda.is_available():
        raise ScientificEntityGLiNERError("CUDA is required by config but is unavailable")
    torch.manual_seed(config.inference.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config.inference.seed)

    with pinned_backbone_config_resolution(
        gliner_encoder_module=gliner_encoder_module,
        backbone_config_class=DebertaV2Config,
        repository=config.model.backbone_config.repository,
        payload=backbone_config_payload,
    ) as backbone_resolution:
        model = GLiNER.from_pretrained(
            str(snapshot),
            local_files_only=True,
            variant=config.model.variant,
            map_location="cpu",
            load_tokenizer=True,
            low_cpu_mem_usage=True,
        )
    if backbone_resolution["resolution_count"] < 1:
        raise ScientificEntityGLiNERError(
            "GLiNER did not consume the verified pinned backbone config"
        )
    model = model.to(config.inference.device)
    model.eval()
    backend = NativeGLiNERBackend(model)
    if config.inference.window_size_tokens > backend.model_max_tokens:
        raise ScientificEntityGLiNERError(
            "Configured window size exceeds loaded model.config.max_len"
        )
    if config.inference.window_overlap_tokens < backend.model_max_width - 1:
        raise ScientificEntityGLiNERError(
            "Window overlap is too small to preserve max-width candidate spans"
        )
    return LoadedGLiNERBackend(
        backend=backend,
        snapshot_path=snapshot,
        backbone_config_path=backbone_config_path,
        model_artifact_verified=True,
        backbone_config_verified=True,
        model_weights_downloaded=allow_model_download and not artifact_was_cached,
        backbone_config_downloaded=(
            allow_model_download and not backbone_config_was_cached
        ),
        backbone_config_injected=True,
    )


class ScientificEntityGLiNERAdapter:
    """Contract adapter with deterministic splitter-token windowing and dedupe."""

    def __init__(
        self,
        *,
        config: ScientificEntityGLiNERConfig,
        descriptor: ScientificEntityExtractorDescriptor,
        backend: GLiNERBackend,
    ) -> None:
        if descriptor.kind != ExtractorKind.STATISTICAL_MODEL:
            raise ScientificEntityGLiNERError("GLiNER adapter requires statistical_model")
        if config.inference.window_size_tokens > backend.model_max_tokens:
            raise ScientificEntityGLiNERError("window size exceeds backend max tokens")
        if config.inference.window_overlap_tokens < backend.model_max_width - 1:
            raise ScientificEntityGLiNERError("window overlap is below max_width - 1")
        self.config = config
        self.descriptor = descriptor
        self.backend = backend
        self._prompts = tuple(label.prompt for label in config.inference.labels)
        self._type_by_prompt = {
            label.prompt.casefold(): label.entity_type for label in config.inference.labels
        }

    def extract(
        self,
        *,
        canonical_id: str,
        source_field: ScientificEntitySourceField,
        source_text: str,
    ) -> GLiNERExtractionResult:
        del canonical_id
        if source_field not in self.config.inference.source_fields:
            raise ScientificEntityGLiNERError(f"Unsupported source field: {source_field}")
        if not source_text:
            return GLiNERExtractionResult((), 0, 0, False)

        prepared = self.backend.prepare_text(source_text, self._prompts)
        if not prepared.tokens:
            return GLiNERExtractionResult((), 0, 0, False)
        if not (
            len(prepared.tokens)
            == len(prepared.token_starts)
            == len(prepared.token_ends)
        ):
            raise ScientificEntityGLiNERError("prepared token maps have unequal lengths")
        previous_end = 0
        for start, end in zip(prepared.token_starts, prepared.token_ends):
            if start < previous_end or end <= start or end > len(source_text):
                raise ScientificEntityGLiNERError("prepared token offsets are invalid")
            previous_end = end

        size = self.config.inference.window_size_tokens
        overlap = self.config.inference.window_overlap_tokens
        step = size - overlap
        deduped: dict[tuple[str, int, int], GLiNERMentionCandidate] = {}
        window_count = 0
        for first in range(0, len(prepared.tokens), step):
            last = min(first + size, len(prepared.tokens))
            window_char_start = prepared.token_starts[first]
            window_char_end = prepared.token_ends[last - 1]
            window_text = source_text[window_char_start:window_char_end]
            window_prepared = self.backend.prepare_text(window_text, self._prompts)
            if len(window_prepared.tokens) > self.backend.model_max_tokens:
                raise ScientificEntityGLiNERError("window would be silently truncated")
            predictions = self.backend.predict_entities(
                window_text,
                self._prompts,
                threshold=self.config.inference.threshold,
                flat_ner=self.config.inference.flat_ner,
                multi_label=self.config.inference.multi_label,
            )
            window_count += 1
            for prediction in predictions:
                candidate = self._prediction_to_candidate(
                    prediction=prediction,
                    window_text=window_text,
                    window_char_start=window_char_start,
                    source_text=source_text,
                )
                key = (
                    candidate.entity_type.value,
                    candidate.char_start,
                    candidate.char_end,
                )
                previous = deduped.get(key)
                if previous is None or candidate.score > previous.score:
                    deduped[key] = candidate
            if last == len(prepared.tokens):
                break

        candidates = tuple(
            sorted(
                deduped.values(),
                key=lambda item: (
                    item.char_start,
                    item.char_end,
                    item.entity_type.value,
                    -item.score,
                ),
            )
        )
        return GLiNERExtractionResult(
            candidates=candidates,
            splitter_token_count=len(prepared.tokens),
            window_count=window_count,
            windowed=window_count > 1,
        )

    def _prediction_to_candidate(
        self,
        *,
        prediction: Mapping[str, Any],
        window_text: str,
        window_char_start: int,
        source_text: str,
    ) -> GLiNERMentionCandidate:
        try:
            local_start = int(prediction["start"])
            local_end = int(prediction["end"])
            label = str(prediction["label"]).strip().casefold()
            score = float(prediction["score"])
            surface = str(prediction["text"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ScientificEntityGLiNERError(
                f"Malformed GLiNER prediction: {prediction!r}"
            ) from exc
        entity_type = self._type_by_prompt.get(label)
        if entity_type is None:
            raise ScientificEntityGLiNERError(f"Unknown GLiNER label: {label!r}")
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ScientificEntityGLiNERError("GLiNER score must be finite in [0, 1]")
        if score < self.config.inference.threshold:
            raise ScientificEntityGLiNERError("GLiNER returned a score below threshold")
        if local_start < 0 or local_end <= local_start or local_end > len(window_text):
            raise ScientificEntityGLiNERError("GLiNER returned invalid window offsets")
        if window_text[local_start:local_end] != surface:
            raise ScientificEntityGLiNERError("GLiNER surface does not match exact source slice")
        start = window_char_start + local_start
        end = window_char_start + local_end
        if source_text[start:end] != surface:
            raise ScientificEntityGLiNERError("Shifted GLiNER span does not match source")
        return GLiNERMentionCandidate(
            entity_type=entity_type,
            char_start=start,
            char_end=end,
            score=score,
        )


__all__ = [
    "CODE_REVISION_PREFIX",
    "DATA_QUALITY_SCHEMA_VERSION",
    "GLINER_CODE_REVISION_FILES",
    "GLINER_CONFIG_SCHEMA_VERSION",
    "GLINER_QUALITY_SCHEMA_VERSION",
    "OUTPUT_SCHEMA_VERSION",
    "GLiNERBackend",
    "GLiNERBackboneConfig",
    "GLiNERExtractionResult",
    "GLiNERMentionCandidate",
    "LoadedGLiNERBackend",
    "NativeGLiNERBackend",
    "PreparedText",
    "ScientificEntityGLiNERAdapter",
    "ScientificEntityGLiNERConfig",
    "ScientificEntityGLiNERError",
    "build_gliner_extractor_descriptor",
    "gliner_config_sha256",
    "load_gliner_config",
    "load_native_gliner_backend",
    "normalized_source_bundle_revision",
    "normalized_text_sha256",
    "pinned_backbone_config_resolution",
]
