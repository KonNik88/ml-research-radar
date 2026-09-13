from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

from radar_core.contracts.scientific_entity_typing_diagnostics import TypingCase
from radar_core.contracts.scientific_entity_typing_root_cause_review import (
    ScientificEntityTypingRootCauseReviewConfig,
    WorkingReviewRow,
)
from radar_core.entities.scientific_entity_typing_diagnostics import (
    validate_typing_diagnostics,
)


REPORT_NAME = "scientific_entity_typing_root_cause_review_v03"
WORKING_FILES = (
    "working_manifest.json",
    "review_working.jsonl",
    "REVIEW_GUIDE.md",
)
FINAL_FILES = (
    "manifest.json",
    "summary.json",
    "reviewed_cases.jsonl",
    "root_cause_breakdown.json",
    "README.md",
    "checksums.txt",
)

FACTUAL_FIELDS = (
    "diagnostic_case_id",
    "error_id",
    "evaluation_id",
    "canonical_id",
    "source_field",
    "reference_id",
    "prediction_evidence_id",
    "reference_entity_type",
    "prediction_entity_type",
    "confusion_pair",
    "pair_count",
    "pair_rank",
    "reference_char_start",
    "reference_char_end",
    "prediction_char_start",
    "prediction_char_end",
    "char_iou",
    "same_span",
    "reference_surface",
    "prediction_surface",
    "source_excerpt",
    "prediction_confidence_score",
    "high_confidence_at_0_8",
    "high_confidence_at_0_9",
)


class ScientificEntityTypingRootCauseReviewError(ValueError):
    pass


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ScientificEntityTypingRootCauseReviewError(f"Expected JSON object: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ScientificEntityTypingRootCauseReviewError(
                f"Expected JSON object at {path}:{line_no}"
            )
        rows.append(value)
    return rows


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, rows: Sequence[Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            if hasattr(row, "model_dump"):
                row = row.model_dump(mode="json")
            fh.write(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _semantic_config_sha(
    config: ScientificEntityTypingRootCauseReviewConfig,
) -> str:
    payload = json.dumps(
        config.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_root_cause_review_config(
    path: Path,
) -> ScientificEntityTypingRootCauseReviewConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ScientificEntityTypingRootCauseReviewConfig.model_validate(raw)


def _validate_parent_package(
    *,
    diagnostics_dir: Path,
    config: ScientificEntityTypingRootCauseReviewConfig,
) -> tuple[dict[str, Any], dict[str, Any], list[TypingCase], list[dict[str, Any]]]:
    diagnostics_dir = diagnostics_dir.resolve()
    if not diagnostics_dir.is_dir():
        raise FileNotFoundError(diagnostics_dir)

    required = {
        "manifest": diagnostics_dir / "manifest.json",
        "summary": diagnostics_dir / "summary.json",
        "typing_cases": diagnostics_dir / "typing_cases.jsonl",
        "review_template": diagnostics_dir / "review_template.jsonl",
    }
    for path in required.values():
        if not path.is_file():
            raise FileNotFoundError(path)

    pinned = {
        "manifest": config.parent.diagnostic_manifest_sha256,
        "summary": config.parent.diagnostic_summary_sha256,
        "typing_cases": config.parent.typing_cases_sha256,
        "review_template": config.parent.review_template_sha256,
    }
    for name, path in required.items():
        observed = _sha256_file(path)
        if observed != pinned[name]:
            raise ScientificEntityTypingRootCauseReviewError(
                f"{name} SHA drifted: {observed}"
            )

    checks, validation_summary = validate_typing_diagnostics(
        analysis_dir=diagnostics_dir
    )
    if validation_summary.get("required_failed_count") != 0:
        failed = [name for name, ok, _ in checks if not ok]
        raise ScientificEntityTypingRootCauseReviewError(
            f"parent diagnostics strict validation failed: {failed}"
        )

    manifest = _json(required["manifest"])
    summary = _json(required["summary"])
    cases = [
        TypingCase.model_validate(row)
        for row in _jsonl(required["typing_cases"])
    ]
    template = _jsonl(required["review_template"])

    if manifest.get("analysis_id") != config.parent.analysis_id:
        raise ScientificEntityTypingRootCauseReviewError("parent analysis_id drifted")
    if manifest.get("evaluation_id") != config.parent.evaluation_id:
        raise ScientificEntityTypingRootCauseReviewError("parent evaluation_id drifted")
    if manifest.get("decision_id") != config.parent.decision_id:
        raise ScientificEntityTypingRootCauseReviewError("parent decision_id drifted")

    expected_pairs = {
        "type_mismatch_count": config.parent.type_mismatch_count,
        "same_span_type_mismatch_count": config.parent.same_span_type_mismatch_count,
        "model_to_method_count": config.parent.model_to_method_count,
        "method_to_task_count": config.parent.method_to_task_count,
        "method_sink_count": config.parent.method_sink_count,
    }
    for key, expected in expected_pairs.items():
        if summary.get(key) != expected:
            raise ScientificEntityTypingRootCauseReviewError(
                f"parent summary drifted for {key}: {summary.get(key)} != {expected}"
            )

    if len(cases) != config.parent.type_mismatch_count:
        raise ScientificEntityTypingRootCauseReviewError("typing case count drifted")
    if len(template) != len(cases):
        raise ScientificEntityTypingRootCauseReviewError(
            "review template row count differs from typing cases"
        )

    case_ids = [row.diagnostic_case_id for row in cases]
    template_ids = [str(row.get("diagnostic_case_id") or "") for row in template]
    if template_ids != case_ids:
        raise ScientificEntityTypingRootCauseReviewError(
            "review template ordering/case IDs drifted"
        )

    template_fields = (
        "error_id",
        "confusion_pair",
        "reference_surface",
        "prediction_surface",
        "source_excerpt",
        "reference_entity_type",
        "prediction_entity_type",
        "prediction_confidence_score",
    )
    for case, review_row in zip(cases, template):
        dumped = case.model_dump(mode="json")
        for field in template_fields:
            if review_row.get(field) != dumped[field]:
                raise ScientificEntityTypingRootCauseReviewError(
                    f"review template factual field drifted for "
                    f"{case.diagnostic_case_id}: {field}"
                )
        if review_row.get("review_status") != "pending":
            raise ScientificEntityTypingRootCauseReviewError(
                "parent review template must be unreviewed"
            )
        for field in (
            "root_cause",
            "reference_type_confirmed",
            "prediction_type_plausible",
            "ambiguity_level",
            "recommended_action",
            "review_notes",
        ):
            if review_row.get(field) is not None:
                raise ScientificEntityTypingRootCauseReviewError(
                    "parent review template already contains human review values"
                )

    return manifest, summary, cases, template


def _working_rows(cases: Sequence[TypingCase]) -> list[WorkingReviewRow]:
    rows: list[WorkingReviewRow] = []
    for case in cases:
        factual = case.model_dump(mode="json")
        factual.pop("schema_version", None)
        rows.append(WorkingReviewRow(**factual))
    return rows


def _guide(config: ScientificEntityTypingRootCauseReviewConfig) -> str:
    return """# Scientific Entity Typing Root-Cause Review v0.3 — Working Guide

This mutable working copy is for human adjudication of the 166 already-materialized
fresh-v0.2c type-mismatch cases. It does not create a new held-out sample and it
must not trigger model inference, threshold tuning, policy reapplication, or
evaluation recomputation.

## How to mark a row complete

Set:

- `review_status = "complete"`
- `root_cause`
- `reference_type_confirmed`
- `prediction_type_plausible`
- `ambiguity_level`
- `recommended_action`

`review_notes` is optional except when either `root_cause` or
`recommended_action` is `other`.

A `pending` row must keep all review fields null.

## Root-cause vocabulary

- `clear_semantic_mistyping`: reference typing is accepted, context is adequate,
  and the model selected the wrong semantic type.
- `taxonomy_boundary_ambiguity`: the mention reasonably lies near a boundary
  between two or more canonical entity types.
- `annotation_reference_issue`: the frozen reference typing itself appears
  questionable or incorrect. Record the issue; do not mutate the frozen parent.
- `compound_or_nested_entity`: the mismatch is materially driven by a compound,
  nested, or mixed-role span.
- `insufficient_context`: the available title/abstract excerpt is not sufficient
  for confident adjudication.
- `other`: none of the frozen categories is adequate; explain in `review_notes`.

## Ambiguity levels

- `none`: essentially unambiguous under the current six-type ontology.
- `low`: a secondary interpretation exists but the preferred type is clear.
- `medium`: more than one type is reasonably defensible.
- `high`: ontology/context does not support a stable single-type judgment.

## Recommended-action vocabulary

- `prompt_or_label_definition`
- `second_stage_typer`
- `ambiguity_rejection`
- `annotation_guideline`
- `span_handling`
- `no_change`
- `other`

These are per-case diagnostics, not an automatic v0.3 architecture decision.

## Immutable factual fields

All factual fields copied from `typing_cases.jsonl` are locked. Finalization
fails if any factual value, case ID, row count, or row order changes.

The 48-paper fresh held-out is consumed development/diagnostic evidence.
Any future v0.3 candidate influenced by this review requires a new disjoint
prediction-blind held-out for independent acceptance.
"""


def prepare_working_copy(
    *,
    project_root: Path,
    config_path: Path,
    diagnostics_dir: Path,
    review_id: str | None = None,
    working_root: Path | None = None,
    execute: bool = False,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = load_root_cause_review_config(config_path.resolve())
    parent_manifest, parent_summary, cases, _ = _validate_parent_package(
        diagnostics_dir=diagnostics_dir,
        config=config,
    )
    if review_id is None:
        review_id = (
            "scientific-entity-typing-root-cause-review-v0.3-"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        )

    root = (
        working_root.resolve()
        if working_root
        else (project_root / config.output.working_root).resolve()
    )
    output_dir = root / review_id

    report = {
        "report": REPORT_NAME,
        "phase": "prepare",
        "mode": "execute" if execute else "plan",
        "phase_complete": bool(execute),
        "review_id": review_id,
        "parent_analysis_id": config.parent.analysis_id,
        "evaluation_id": config.parent.evaluation_id,
        "type_mismatch_count": len(cases),
        "same_span_type_mismatch_count": parent_summary["same_span_type_mismatch_count"],
        "model_to_method_count": parent_summary["model_to_method_count"],
        "method_to_task_count": parent_summary["method_to_task_count"],
        "method_sink_count": parent_summary["method_sink_count"],
        "working_complete_count": 0,
        "working_pending_count": len(cases),
        "human_review_only": True,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "policy_reapplied": False,
        "evaluation_recomputed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "automatic_root_cause_assignment_executed": False,
        "automatic_candidate_selection_executed": False,
        "output_dir": str(output_dir),
        "next_slice": (
            config.next_steps["after_prepare"]
            if execute
            else "execute_prepare_root_cause_review_working_copy_once"
        ),
    }

    if output_dir.exists():
        raise ScientificEntityTypingRootCauseReviewError(
            f"working output already exists: {output_dir}"
        )
    if not execute:
        return report

    root.mkdir(parents=True, exist_ok=True)
    staging = root / f".{review_id}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    try:
        working_manifest = {
            "schema_version": "scientific_entity_typing_root_cause_review_working_manifest_v0.3",
            "review_id": review_id,
            "generated_at_utc": generated_at_utc
            or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "parent_analysis_id": config.parent.analysis_id,
            "evaluation_id": config.parent.evaluation_id,
            "decision_id": config.parent.decision_id,
            "config_semantic_sha256": _semantic_config_sha(config),
            "diagnostics_dir": str(diagnostics_dir.resolve()),
            "parent_file_sha256": {
                "manifest.json": config.parent.diagnostic_manifest_sha256,
                "summary.json": config.parent.diagnostic_summary_sha256,
                "typing_cases.jsonl": config.parent.typing_cases_sha256,
                "review_template.jsonl": config.parent.review_template_sha256,
            },
            "type_mismatch_count": len(cases),
            "mutable_file": "review_working.jsonl",
            "immutable_factual_fields": list(FACTUAL_FIELDS),
            "human_review_only": True,
            "future_candidate_requires_new_independent_heldout": True,
            "model_inference_executed": False,
            "threshold_tuning_executed": False,
            "policy_reapplied": False,
            "evaluation_recomputed": False,
            "canonical_truth_mutated": False,
            "production_extractor_selected": False,
            "full_corpus_build_authorized": False,
            "automatic_root_cause_assignment_executed": False,
            "automatic_candidate_selection_executed": False,
        }
        _write_json(staging / "working_manifest.json", working_manifest)
        _write_jsonl(staging / "review_working.jsonl", _working_rows(cases))
        (staging / "REVIEW_GUIDE.md").write_text(
            _guide(config), encoding="utf-8", newline="\n"
        )
        staging.rename(output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return report


def _validate_working_rows_against_parent(
    *,
    rows: Sequence[WorkingReviewRow],
    cases: Sequence[TypingCase],
) -> list[str]:
    failures: list[str] = []
    if len(rows) != len(cases):
        failures.append(f"row_count:{len(rows)}!={len(cases)}")
        return failures

    for idx, (row, case) in enumerate(zip(rows, cases), start=1):
        rd = row.model_dump(mode="json")
        cd = case.model_dump(mode="json")
        for field in FACTUAL_FIELDS:
            if rd[field] != cd[field]:
                failures.append(
                    f"factual_drift:row={idx}:case={case.diagnostic_case_id}:field={field}"
                )
    return failures


def validate_working_copy(
    *,
    working_dir: Path,
    config_path: Path,
    diagnostics_dir: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    config = load_root_cause_review_config(config_path.resolve())
    _, _, cases, _ = _validate_parent_package(
        diagnostics_dir=diagnostics_dir,
        config=config,
    )
    working_dir = working_dir.resolve()
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    add("working_dir_exists", working_dir.is_dir(), working_dir)
    if not working_dir.is_dir():
        return checks, {
            "report": REPORT_NAME,
            "validation_scope": "working",
            "total_checks": len(checks),
            "required_failed_count": 1,
        }

    expected_names = sorted(WORKING_FILES)
    observed_names = sorted(
        p.name for p in working_dir.iterdir() if p.is_file()
    )
    add("working_file_set_exact", observed_names == expected_names, observed_names)

    manifest_path = working_dir / "working_manifest.json"
    rows_path = working_dir / "review_working.jsonl"
    guide_path = working_dir / "REVIEW_GUIDE.md"
    for path in (manifest_path, rows_path, guide_path):
        add(f"file_exists::{path.name}", path.is_file(), path)

    if not all(path.is_file() for path in (manifest_path, rows_path, guide_path)):
        failed = [name for name, ok, _ in checks if not ok]
        return checks, {
            "report": REPORT_NAME,
            "validation_scope": "working",
            "total_checks": len(checks),
            "required_failed_count": len(failed),
        }

    manifest = _json(manifest_path)
    add(
        "parent_analysis_id_pinned",
        manifest.get("parent_analysis_id") == config.parent.analysis_id,
        manifest.get("parent_analysis_id"),
    )
    add(
        "evaluation_id_pinned",
        manifest.get("evaluation_id") == config.parent.evaluation_id,
        manifest.get("evaluation_id"),
    )
    add(
        "decision_id_pinned",
        manifest.get("decision_id") == config.parent.decision_id,
        manifest.get("decision_id"),
    )
    add(
        "working_manifest_case_count",
        manifest.get("type_mismatch_count") == len(cases),
        manifest.get("type_mismatch_count"),
    )
    add(
        "future_heldout_guard",
        manifest.get("future_candidate_requires_new_independent_heldout") is True,
        "",
    )
    for key in (
        "model_inference_executed",
        "threshold_tuning_executed",
        "policy_reapplied",
        "evaluation_recomputed",
        "canonical_truth_mutated",
        "production_extractor_selected",
        "full_corpus_build_authorized",
        "automatic_root_cause_assignment_executed",
        "automatic_candidate_selection_executed",
    ):
        add(f"safety::{key}", manifest.get(key) is False, "")

    parsed_rows: list[WorkingReviewRow] = []
    parse_failures: list[str] = []
    for idx, raw in enumerate(_jsonl(rows_path), start=1):
        try:
            parsed_rows.append(WorkingReviewRow.model_validate(raw))
        except Exception as exc:
            parse_failures.append(f"row={idx}:{exc}")
    add("working_rows_schema_valid", not parse_failures, parse_failures[:3])

    if not parse_failures:
        add("working_row_count", len(parsed_rows) == len(cases), len(parsed_rows))
        ids = [row.diagnostic_case_id for row in parsed_rows]
        add("working_case_ids_unique", len(set(ids)) == len(ids), len(ids))
        factual_failures = _validate_working_rows_against_parent(
            rows=parsed_rows, cases=cases
        )
        add("working_factual_fields_locked", not factual_failures, factual_failures[:5])

        complete = sum(row.review_status == "complete" for row in parsed_rows)
        pending = len(parsed_rows) - complete
    else:
        complete = 0
        pending = len(cases)

    failed = [name for name, ok, _ in checks if not ok]
    summary = {
        "report": REPORT_NAME,
        "validation_scope": "working",
        "review_id": manifest.get("review_id"),
        "type_mismatch_count": len(cases),
        "complete_count": complete,
        "pending_count": pending,
        "review_complete": complete == len(cases) and not failed,
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "next_slice": (
            "finalize_completed_root_cause_review"
            if complete == len(cases) and not failed
            else "continue_human_root_cause_review"
        ),
    }
    return checks, summary


def _breakdown(rows: Sequence[WorkingReviewRow]) -> dict[str, Any]:
    root_causes = Counter(row.root_cause for row in rows)
    actions = Counter(row.recommended_action for row in rows)
    ambiguity = Counter(row.ambiguity_level for row in rows)
    by_pair: dict[str, Counter[str]] = defaultdict(Counter)
    by_sink: dict[str, Counter[str]] = defaultdict(Counter)
    same_span: dict[str, Counter[str]] = defaultdict(Counter)
    high_08 = Counter()
    high_09 = Counter()

    for row in rows:
        assert row.root_cause is not None
        by_pair[row.confusion_pair][row.root_cause] += 1
        by_sink[row.prediction_entity_type][row.root_cause] += 1
        same_span[
            "same_span" if row.same_span else "different_span"
        ][row.root_cause] += 1
        if row.high_confidence_at_0_8:
            high_08[row.root_cause] += 1
        if row.high_confidence_at_0_9:
            high_09[row.root_cause] += 1

    return {
        "schema_version": "scientific_entity_typing_root_cause_breakdown_v0.3",
        "root_cause_counts": dict(sorted(root_causes.items())),
        "recommended_action_counts": dict(sorted(actions.items())),
        "ambiguity_level_counts": dict(sorted(ambiguity.items())),
        "reference_type_not_confirmed_count": sum(
            row.reference_type_confirmed is False for row in rows
        ),
        "prediction_type_plausible_count": sum(
            row.prediction_type_plausible is True for row in rows
        ),
        "root_cause_by_confusion_pair": {
            pair: dict(sorted(counter.items()))
            for pair, counter in sorted(by_pair.items())
        },
        "root_cause_by_predicted_type_sink": {
            sink: dict(sorted(counter.items()))
            for sink, counter in sorted(by_sink.items())
        },
        "root_cause_by_same_span_status": {
            status: dict(sorted(counter.items()))
            for status, counter in sorted(same_span.items())
        },
        "root_cause_high_confidence_at_0_8": dict(sorted(high_08.items())),
        "root_cause_high_confidence_at_0_9": dict(sorted(high_09.items())),
    }


def _final_readme(summary: Mapping[str, Any]) -> str:
    return f"""# Scientific Entity Typing Root-Cause Review v0.3

Human root-cause review over the `{summary['reviewed_case_count']}` immutable
fresh-v0.2c typing-mismatch cases.

This package records human adjudication only. It does not automatically select a
v0.3 architecture, run a model, tune thresholds, reapply policy, recompute
evaluation, mutate canonical truth, or authorize production/full-corpus use.

The reviewed fresh-heldout evidence is development/diagnostic evidence.
Any future v0.3 candidate informed by this review requires a new disjoint
prediction-blind held-out for independent acceptance.

Next: inspect the aggregate root-cause evidence and choose exactly one bounded
v0.3 typing hypothesis for controlled development.
"""


def finalize_review(
    *,
    project_root: Path,
    config_path: Path,
    diagnostics_dir: Path,
    working_dir: Path,
    final_root: Path | None = None,
    execute: bool = False,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = load_root_cause_review_config(config_path.resolve())
    _, _, cases, _ = _validate_parent_package(
        diagnostics_dir=diagnostics_dir,
        config=config,
    )

    checks, working_summary = validate_working_copy(
        working_dir=working_dir,
        config_path=config_path,
        diagnostics_dir=diagnostics_dir,
    )
    if working_summary.get("required_failed_count") != 0:
        failed = [name for name, ok, _ in checks if not ok]
        raise ScientificEntityTypingRootCauseReviewError(
            f"working review validation failed: {failed}"
        )
    if working_summary.get("complete_count") != len(cases):
        raise ScientificEntityTypingRootCauseReviewError(
            f"review incomplete: {working_summary.get('complete_count')}/{len(cases)}"
        )

    working_manifest = _json(working_dir.resolve() / "working_manifest.json")
    review_id = str(working_manifest["review_id"])
    rows = [
        WorkingReviewRow.model_validate(row)
        for row in _jsonl(working_dir.resolve() / "review_working.jsonl")
    ]
    factual_failures = _validate_working_rows_against_parent(rows=rows, cases=cases)
    if factual_failures:
        raise ScientificEntityTypingRootCauseReviewError(
            f"factual fields drifted: {factual_failures[:5]}"
        )

    root = (
        final_root.resolve()
        if final_root
        else (project_root / config.output.final_root).resolve()
    )
    output_dir = root / review_id
    if output_dir.exists():
        raise ScientificEntityTypingRootCauseReviewError(
            f"final output already exists: {output_dir}"
        )

    breakdown = _breakdown(rows)
    summary = {
        "schema_version": "scientific_entity_typing_root_cause_review_summary_v0.3",
        "review_id": review_id,
        "parent_analysis_id": config.parent.analysis_id,
        "evaluation_id": config.parent.evaluation_id,
        "decision_id": config.parent.decision_id,
        "reviewed_case_count": len(rows),
        "pending_count": 0,
        "review_complete": True,
        "root_causes_assigned": True,
        "root_cause_counts": breakdown["root_cause_counts"],
        "recommended_action_counts": breakdown["recommended_action_counts"],
        "ambiguity_level_counts": breakdown["ambiguity_level_counts"],
        "reference_type_not_confirmed_count": breakdown[
            "reference_type_not_confirmed_count"
        ],
        "prediction_type_plausible_count": breakdown[
            "prediction_type_plausible_count"
        ],
        "human_review_only": True,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "policy_reapplied": False,
        "evaluation_recomputed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "automatic_root_cause_assignment_executed": False,
        "automatic_candidate_selection_executed": False,
        "future_candidate_requires_new_independent_heldout": True,
        "next_slice": config.next_steps["after_finalize"],
    }

    report = {
        "report": REPORT_NAME,
        "phase": "finalize",
        "mode": "execute" if execute else "plan",
        "phase_complete": bool(execute),
        "review_id": review_id,
        "parent_analysis_id": config.parent.analysis_id,
        "reviewed_case_count": len(rows),
        "pending_count": 0,
        "root_causes_assigned": True,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "policy_reapplied": False,
        "evaluation_recomputed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "automatic_root_cause_assignment_executed": False,
        "automatic_candidate_selection_executed": False,
        "output_dir": str(output_dir),
        "next_slice": (
            config.next_steps["after_finalize"]
            if execute
            else "execute_finalize_root_cause_review_once"
        ),
    }
    if not execute:
        return report

    root.mkdir(parents=True, exist_ok=True)
    staging = root / f".{review_id}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    try:
        manifest = {
            "schema_version": "scientific_entity_typing_root_cause_review_manifest_v0.3",
            "review_id": review_id,
            "generated_at_utc": generated_at_utc
            or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "parent_analysis_id": config.parent.analysis_id,
            "evaluation_id": config.parent.evaluation_id,
            "decision_id": config.parent.decision_id,
            "config_semantic_sha256": _semantic_config_sha(config),
            "parent_file_sha256": working_manifest["parent_file_sha256"],
            "working_manifest_sha256": _sha256_file(
                working_dir.resolve() / "working_manifest.json"
            ),
            "completed_working_review_sha256": _sha256_file(
                working_dir.resolve() / "review_working.jsonl"
            ),
            "output_files": list(FINAL_FILES),
            "human_review_only": True,
            "future_candidate_requires_new_independent_heldout": True,
            "model_inference_executed": False,
            "threshold_tuning_executed": False,
            "policy_reapplied": False,
            "evaluation_recomputed": False,
            "canonical_truth_mutated": False,
            "production_extractor_selected": False,
            "full_corpus_build_authorized": False,
            "automatic_root_cause_assignment_executed": False,
            "automatic_candidate_selection_executed": False,
        }
        _write_json(staging / "manifest.json", manifest)
        _write_json(staging / "summary.json", summary)
        _write_jsonl(staging / "reviewed_cases.jsonl", rows)
        _write_json(staging / "root_cause_breakdown.json", breakdown)
        (staging / "README.md").write_text(
            _final_readme(summary), encoding="utf-8", newline="\n"
        )
        checksum_lines = []
        for name in FINAL_FILES[:-1]:
            checksum_lines.append(f"{_sha256_file(staging / name)}  {name}\n")
        (staging / "checksums.txt").write_text(
            "".join(checksum_lines), encoding="utf-8", newline="\n"
        )
        staging.rename(output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return report


def validate_final_review(
    *,
    review_dir: Path,
    config_path: Path,
    diagnostics_dir: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    config = load_root_cause_review_config(config_path.resolve())
    _, _, cases, _ = _validate_parent_package(
        diagnostics_dir=diagnostics_dir,
        config=config,
    )
    review_dir = review_dir.resolve()
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    add("review_dir_exists", review_dir.is_dir(), review_dir)
    if not review_dir.is_dir():
        return checks, {
            "report": REPORT_NAME,
            "validation_scope": "final",
            "total_checks": len(checks),
            "required_failed_count": 1,
        }

    observed_names = sorted(p.name for p in review_dir.iterdir() if p.is_file())
    add("final_file_set_exact", observed_names == sorted(FINAL_FILES), observed_names)
    for name in FINAL_FILES:
        add(f"file_exists::{name}", (review_dir / name).is_file(), name)
    if not all((review_dir / name).is_file() for name in FINAL_FILES):
        failed = [name for name, ok, _ in checks if not ok]
        return checks, {
            "report": REPORT_NAME,
            "validation_scope": "final",
            "total_checks": len(checks),
            "required_failed_count": len(failed),
        }

    expected_checksums: dict[str, str] = {}
    for line in (review_dir / "checksums.txt").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        expected_checksums[name] = digest
    for name in FINAL_FILES[:-1]:
        add(
            f"checksum_matches::{name}",
            expected_checksums.get(name) == _sha256_file(review_dir / name),
            name,
        )

    manifest = _json(review_dir / "manifest.json")
    summary = _json(review_dir / "summary.json")
    breakdown = _json(review_dir / "root_cause_breakdown.json")
    parsed_rows: list[WorkingReviewRow] = []
    parse_failures: list[str] = []
    for idx, raw in enumerate(_jsonl(review_dir / "reviewed_cases.jsonl"), start=1):
        try:
            parsed_rows.append(WorkingReviewRow.model_validate(raw))
        except Exception as exc:
            parse_failures.append(f"row={idx}:{exc}")
    add("reviewed_rows_schema_valid", not parse_failures, parse_failures[:3])

    if not parse_failures:
        add("reviewed_row_count", len(parsed_rows) == len(cases), len(parsed_rows))
        add(
            "all_rows_complete",
            all(row.review_status == "complete" for row in parsed_rows),
            "",
        )
        factual_failures = _validate_working_rows_against_parent(
            rows=parsed_rows, cases=cases
        )
        add("reviewed_factual_fields_locked", not factual_failures, factual_failures[:5])
        recomputed = _breakdown(parsed_rows)
        add(
            "breakdown_recomputed_exactly",
            breakdown == recomputed,
            "",
        )
        add(
            "summary_root_cause_counts_recomputed",
            summary.get("root_cause_counts") == recomputed["root_cause_counts"],
            "",
        )
        add(
            "summary_action_counts_recomputed",
            summary.get("recommended_action_counts")
            == recomputed["recommended_action_counts"],
            "",
        )
        add(
            "summary_ambiguity_counts_recomputed",
            summary.get("ambiguity_level_counts")
            == recomputed["ambiguity_level_counts"],
            "",
        )
    else:
        recomputed = {}

    add(
        "review_id_consistent",
        manifest.get("review_id") == summary.get("review_id"),
        "",
    )
    add(
        "parent_analysis_id_consistent",
        manifest.get("parent_analysis_id") == config.parent.analysis_id
        and summary.get("parent_analysis_id") == config.parent.analysis_id,
        "",
    )
    add(
        "root_causes_assigned",
        summary.get("root_causes_assigned") is True,
        "",
    )
    add(
        "future_heldout_guard",
        manifest.get("future_candidate_requires_new_independent_heldout") is True
        and summary.get("future_candidate_requires_new_independent_heldout") is True,
        "",
    )
    for key in (
        "model_inference_executed",
        "threshold_tuning_executed",
        "policy_reapplied",
        "evaluation_recomputed",
        "canonical_truth_mutated",
        "production_extractor_selected",
        "full_corpus_build_authorized",
        "automatic_root_cause_assignment_executed",
        "automatic_candidate_selection_executed",
    ):
        add(
            f"safety::{key}",
            manifest.get(key) is False and summary.get(key) is False,
            "",
        )

    failed = [name for name, ok, _ in checks if not ok]
    validation_summary = {
        "report": REPORT_NAME,
        "validation_scope": "final",
        "review_id": manifest.get("review_id"),
        "parent_analysis_id": manifest.get("parent_analysis_id"),
        "reviewed_case_count": len(parsed_rows),
        "root_causes_assigned": summary.get("root_causes_assigned"),
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "next_slice": config.next_steps["after_finalize"],
    }
    return checks, validation_summary
