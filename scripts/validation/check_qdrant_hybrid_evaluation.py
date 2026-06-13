"""Validate Qdrant Hybrid Evaluation v1 evidence.

The validator checks that the report represents a controlled,
evaluation-only comparison between file and Qdrant dense backends.

Strict mode additionally requires:

- the complete configured Golden Set;
- every configured scenario for every query;
- zero errors and blocking classifications;
- deterministic repeated results;
- configured overlap thresholds;
- a green source verdict.

The validator does not require Qdrant to be faster and does not perform
or authorize public promotion.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "PyYAML is required for Qdrant hybrid "
        "evaluation validation."
    ) from exc


QUALITY_SCHEMA_VERSION = (
    "qdrant_hybrid_evaluation_quality_v1"
)
INPUT_SCHEMA_VERSION = (
    "qdrant_hybrid_evaluation_v1"
)

DEFAULT_CONFIG_PATH = Path(
    "configs/qdrant_hybrid_evaluation_v1.yaml"
)
DEFAULT_REPORT_PATH = Path(
    "artifacts/reports/evaluation/"
    "qdrant_hybrid_evaluation_latest.json"
)
DEFAULT_OUTPUT_DIR = Path(
    "artifacts/reports/validation"
)


def utc_now_ts() -> str:
    return datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def normalize_path(
    path: Path | str | None,
) -> str | None:
    if path is None:
        return None

    return str(path).replace("\\", "/")


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(
        path.read_text(encoding="utf-8")
    ) or {}

    if not isinstance(payload, dict):
        raise ValueError(
            f"Config must be a mapping: {path}"
        )

    return payload


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(encoding="utf-8")
    )

    if not isinstance(payload, dict):
        raise ValueError(
            f"Report must be an object: {path}"
        )

    return payload


def dump_json(
    path: Path,
    payload: Mapping[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def dump_text(
    path: Path,
    text: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        text,
        encoding="utf-8",
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return (
        value
        if isinstance(value, Mapping)
        else {}
    )


def _list(value: Any) -> list[Any]:
    return (
        list(value)
        if isinstance(value, list)
        else []
    )


def _positive_int(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value > 0
    )


def _non_negative_int(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _finite_non_negative(value: Any) -> bool:
    return (
        _finite(value)
        and float(value) >= 0.0
    )


def _in_unit_interval(value: Any) -> bool:
    return (
        _finite(value)
        and 0.0 <= float(value) <= 1.0
    )


def _sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(
            character
            in "0123456789abcdef"
            for character in value
        )
    )


def _unique_strings(
    values: Any,
) -> bool:
    if not isinstance(values, list):
        return False

    parsed = [
        str(value)
        for value in values
    ]

    return (
        all(parsed)
        and len(parsed) == len(set(parsed))
    )


def all_numbers_finite(value: Any) -> bool:
    if isinstance(value, bool):
        return True

    if isinstance(value, float):
        return math.isfinite(value)

    if isinstance(value, int):
        return True

    if isinstance(value, list):
        return all(
            all_numbers_finite(item)
            for item in value
        )

    if isinstance(value, Mapping):
        return all(
            all_numbers_finite(item)
            for item in value.values()
        )

    return True


def valid_query_vector(
    payload: Any,
) -> bool:
    value = _mapping(payload)

    return (
        _positive_int(value.get("dimension"))
        and value.get("dtype") == "float32"
        and value.get("all_finite") is True
        and _finite(value.get("norm"))
        and abs(
            float(value.get("norm")) - 1.0
        )
        <= 1e-4
        and _sha256(value.get("sha256"))
    )


def valid_lexical_evidence(
    payload: Any,
) -> bool:
    value = _mapping(payload)

    return (
        _non_negative_int(value.get("count"))
        and _sha256(value.get("ids_digest"))
        and _sha256(
            value.get(
                "ids_and_scores_sha256"
            )
        )
    )


def valid_timing_map(
    payload: Any,
) -> bool:
    value = _mapping(payload)

    required = (
        "dense_wall_ms",
        "backend_search_ms",
        "merge_ms",
        "hydrate_ms",
        "rank_ms",
    )

    return all(
        _finite_non_negative(value.get(name))
        for name in required
    )


def valid_metrics(
    payload: Any,
) -> bool:
    value = _mapping(payload)

    return all(
        _finite(value.get(name))
        for name in (
            "hit",
            "precision",
            "recall",
            "mrr",
            "ndcg",
        )
    )


def valid_comparison(
    payload: Any,
    *,
    reference_ids: list[str],
    candidate_ids: list[str],
) -> bool:
    value = _mapping(payload)

    if not (
        _non_negative_int(
            value.get("overlap_count")
        )
        and _in_unit_interval(
            value.get("overlap_ratio")
        )
        and isinstance(
            value.get("same_set"),
            bool,
        )
        and isinstance(
            value.get("exact_same_order"),
            bool,
        )
        and _sha256(
            value.get("reference_digest")
        )
        and _sha256(
            value.get("candidate_digest")
        )
    ):
        return False

    expected_exact = (
        reference_ids == candidate_ids
    )
    expected_same_set = (
        set(reference_ids)
        == set(candidate_ids)
    )

    return (
        value.get("exact_same_order")
        is expected_exact
        and value.get("same_set")
        is expected_same_set
    )


def valid_determinism_summary(
    payload: Any,
) -> bool:
    value = _mapping(payload)

    run_count = value.get("run_count")
    run_digests = value.get("run_digests")
    mismatch_runs = value.get(
        "mismatch_run_numbers"
    )

    return (
        _positive_int(run_count)
        and isinstance(
            value.get("stable"),
            bool,
        )
        and _sha256(
            value.get("reference_digest")
        )
        and _positive_int(
            value.get("unique_digest_count")
        )
        and isinstance(run_digests, list)
        and len(run_digests) == run_count
        and all(
            _sha256(digest)
            for digest in run_digests
        )
        and isinstance(mismatch_runs, list)
        and all(
            _positive_int(number)
            for number in mismatch_runs
        )
    )


def expected_scenario_ids(
    scenario_matrix: Sequence[Any],
) -> set[str]:
    result: set[str] = set()

    for row in scenario_matrix:
        scenario = _mapping(row)
        scenario_id = str(
            scenario.get("scenario_id")
            or ""
        )

        if scenario_id:
            result.add(scenario_id)

    return result


def evaluate_report(
    source: Mapping[str, Any],
    *,
    config: Mapping[str, Any],
    strict: bool,
    report_exists: bool = True,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    problems: list[str] = []

    quality_config = _mapping(
        config.get("quality")
    )
    configured_qdrant = _mapping(
        config.get("qdrant")
    )
    configured_profile = _mapping(
        configured_qdrant.get("profile")
    )
    configured_evaluation = _mapping(
        config.get("evaluation")
    )

    safety = _mapping(
        source.get("safety")
    )
    runtime = _mapping(
        source.get("runtime")
    )
    qdrant = _mapping(
        source.get("qdrant")
    )
    qdrant_profile = _mapping(
        qdrant.get("profile")
    )
    summary = _mapping(
        source.get("summary")
    )
    verdict = _mapping(
        source.get("verdict")
    )
    scenario_matrix = _list(
        source.get("scenario_matrix")
    )
    query_results = _list(
        source.get("query_results")
    )
    errors = _list(
        source.get("errors")
    )

    expected_enabled_count = int(
        quality_config.get(
            "expected_enabled_query_count",
            0,
        )
        or 0
    )

    scenario_ids = expected_scenario_ids(
        scenario_matrix
    )
    scenario_count = len(scenario_matrix)

    checks["report_exists"] = bool(
        report_exists
    )
    checks["input_schema_version_ok"] = (
        source.get("schema_version")
        == INPUT_SCHEMA_VERSION
    )
    checks["report_name_ok"] = (
        source.get("report_name")
        == "qdrant_hybrid_evaluation"
    )
    checks["generated_at_present"] = bool(
        source.get("generated_at_utc")
    )
    checks["embedded_config_present"] = (
        isinstance(source.get("config"), Mapping)
    )

    checks["safety_evaluation_only"] = (
        safety.get("evaluation_only") is True
    )
    checks[
        "safety_production_default_unchanged"
    ] = (
        safety.get(
            "production_default_changed"
        )
        is False
    )
    checks[
        "safety_public_qdrant_not_promoted"
    ] = (
        safety.get(
            "public_qdrant_promoted"
        )
        is False
    )
    checks["safety_no_fallback"] = (
        safety.get("fallback_used") is False
    )
    checks["safety_canonical_unchanged"] = (
        safety.get(
            "canonical_data_changed"
        )
        is False
    )
    checks[
        "safety_retrieval_build_unchanged"
    ] = (
        safety.get(
            "retrieval_build_changed"
        )
        is False
    )
    checks[
        "safety_collection_not_mutated"
    ] = (
        safety.get(
            "qdrant_collection_mutated"
        )
        is False
    )

    embedding_shape = _list(
        runtime.get("embedding_shape")
    )

    checks["runtime_file_ready"] = (
        runtime.get("backend_mode") == "file"
        and runtime.get("ready") is True
    )
    checks["runtime_build_id_present"] = bool(
        runtime.get("build_id")
    )
    checks["runtime_corpus_count_valid"] = (
        _positive_int(
            runtime.get("corpus_doc_count")
        )
    )
    checks["runtime_embedding_valid"] = (
        bool(runtime.get(
            "embedding_model_name"
        ))
        and len(embedding_shape) == 2
        and all(
            _positive_int(value)
            for value in embedding_shape
        )
        and embedding_shape[0]
        == runtime.get("corpus_doc_count")
    )

    checks["qdrant_collection_matches"] = (
        qdrant.get("collection_name")
        == configured_qdrant.get(
            "collection_name"
        )
    )
    checks["qdrant_transport_matches"] = (
        qdrant.get("transport")
        == (
            "grpc"
            if configured_qdrant.get(
                "prefer_grpc"
            )
            else "rest"
        )
    )
    checks["qdrant_profile_matches"] = (
        qdrant_profile.get("name")
        == configured_profile.get("name")
        and qdrant_profile.get("exact")
        == configured_profile.get("exact")
        and qdrant_profile.get("hnsw_ef")
        == configured_profile.get("hnsw_ef")
    )

    checks["scenario_matrix_valid"] = (
        scenario_count > 0
        and len(scenario_ids)
        == scenario_count
        and all(
            _positive_int(
                _mapping(row).get("top_k")
            )
            and _positive_int(
                _mapping(row).get(
                    "candidate_k"
                )
            )
            and isinstance(
                _mapping(row).get("rank"),
                bool,
            )
            for row in scenario_matrix
        )
    )

    enabled_count = summary.get(
        "enabled_query_count"
    )
    selected_count = summary.get(
        "selected_query_count"
    )
    scenarios_per_query = summary.get(
        "scenario_count_per_query"
    )
    expected_scenarios = summary.get(
        "expected_scenario_count"
    )
    successful_scenarios = summary.get(
        "successful_scenario_count"
    )
    error_count = summary.get(
        "error_count"
    )

    checks["summary_counts_valid"] = (
        _positive_int(enabled_count)
        and _positive_int(selected_count)
        and _positive_int(
            scenarios_per_query
        )
        and _positive_int(
            expected_scenarios
        )
        and _non_negative_int(
            successful_scenarios
        )
        and _non_negative_int(error_count)
        and scenarios_per_query
        == scenario_count
        and expected_scenarios
        == selected_count * scenario_count
        and successful_scenarios
        + error_count
        == expected_scenarios
    )

    checks[
        "enabled_query_count_expected"
    ] = (
        expected_enabled_count > 0
        and enabled_count
        == expected_enabled_count
    )

    checks["full_query_set_selected"] = (
        selected_count == enabled_count
        and configured_evaluation.get(
            "max_queries"
        )
        is None
    )

    checks["query_results_count_valid"] = (
        len(query_results)
        == selected_count
    )

    query_ids = [
        str(
            _mapping(row).get(
                "query_id"
            )
            or ""
        )
        for row in query_results
    ]

    checks["query_ids_unique"] = (
        all(query_ids)
        and len(query_ids)
        == len(set(query_ids))
    )

    scenario_coverage_ok = True
    shared_evidence_ok = True
    backend_evidence_ok = True
    result_ids_ok = True
    comparisons_ok = True
    metrics_ok = True
    timings_ok = True
    determinism_ok = True
    classifications_ok = True

    for query_row_raw in query_results:
        query_row = _mapping(
            query_row_raw
        )
        query_id = str(
            query_row.get("query_id")
            or ""
        )
        scenarios = _list(
            query_row.get("scenarios")
        )

        found_ids = {
            str(
                _mapping(scenario).get(
                    "scenario_id"
                )
                or ""
            )
            for scenario in scenarios
        }

        if found_ids != scenario_ids:
            scenario_coverage_ok = False
            problems.append(
                f"{query_id}:scenario_coverage"
            )

        vector_fingerprints: list[
            Mapping[str, Any]
        ] = []
        lexical_by_candidate_k: dict[
            int,
            Mapping[str, Any],
        ] = {}

        for scenario_raw in scenarios:
            scenario = _mapping(
                scenario_raw
            )
            scenario_id = str(
                scenario.get("scenario_id")
                or ""
            )

            if scenario.get("error") is not None:
                scenario_coverage_ok = False
                problems.append(
                    f"{query_id}:{scenario_id}:"
                    "scenario_error"
                )
                continue

            shared = _mapping(
                scenario.get("shared")
            )
            vector = _mapping(
                shared.get("query_vector")
            )
            lexical = _mapping(
                shared.get("lexical")
            )

            if not valid_query_vector(vector):
                shared_evidence_ok = False
                problems.append(
                    f"{query_id}:{scenario_id}:"
                    "invalid_query_vector"
                )

            if not valid_lexical_evidence(
                lexical
            ):
                shared_evidence_ok = False
                problems.append(
                    f"{query_id}:{scenario_id}:"
                    "invalid_lexical_evidence"
                )

            vector_fingerprints.append(
                vector
            )

            candidate_k = scenario.get(
                "candidate_k"
            )
            if _positive_int(candidate_k):
                previous = (
                    lexical_by_candidate_k.get(
                        int(candidate_k)
                    )
                )
                if (
                    previous is not None
                    and dict(previous)
                    != dict(lexical)
                ):
                    shared_evidence_ok = False
                    problems.append(
                        f"{query_id}:candidate"
                        f"{candidate_k}:"
                        "lexical_evidence_mismatch"
                    )
                lexical_by_candidate_k[
                    int(candidate_k)
                ] = lexical

            file_branch = _mapping(
                scenario.get("file")
            )
            qdrant_branch = _mapping(
                scenario.get("qdrant")
            )

            for backend_name, branch in (
                ("file", file_branch),
                ("qdrant", qdrant_branch),
            ):
                backend = _mapping(
                    branch.get("backend")
                )

                if not (
                    backend.get("name")
                    == backend_name
                    and bool(
                        backend.get(
                            "implementation"
                        )
                    )
                    and backend.get("ready")
                    is True
                    and backend.get(
                        "build_id"
                    )
                    == runtime.get(
                        "build_id"
                    )
                ):
                    backend_evidence_ok = False
                    problems.append(
                        f"{query_id}:{scenario_id}:"
                        f"{backend_name}:"
                        "invalid_backend_evidence"
                    )

                dense_ids = branch.get(
                    "dense_ids"
                )
                final_ids = branch.get(
                    "final_ids"
                )

                if not (
                    _unique_strings(dense_ids)
                    and _unique_strings(final_ids)
                    and len(dense_ids)
                    == scenario.get(
                        "candidate_k"
                    )
                    and len(final_ids)
                    == scenario.get("top_k")
                ):
                    result_ids_ok = False
                    problems.append(
                        f"{query_id}:{scenario_id}:"
                        f"{backend_name}:"
                        "invalid_result_ids"
                    )

                if not valid_metrics(
                    branch.get("metrics")
                ):
                    metrics_ok = False
                    problems.append(
                        f"{query_id}:{scenario_id}:"
                        f"{backend_name}:"
                        "invalid_metrics"
                    )

                if not valid_timing_map(
                    branch.get("timing_ms")
                ):
                    timings_ok = False
                    problems.append(
                        f"{query_id}:{scenario_id}:"
                        f"{backend_name}:"
                        "invalid_timings"
                    )

            file_dense_ids = _list(
                file_branch.get("dense_ids")
            )
            qdrant_dense_ids = _list(
                qdrant_branch.get(
                    "dense_ids"
                )
            )
            file_final_ids = _list(
                file_branch.get("final_ids")
            )
            qdrant_final_ids = _list(
                qdrant_branch.get(
                    "final_ids"
                )
            )

            comparison = _mapping(
                scenario.get("comparison")
            )

            if not valid_comparison(
                comparison.get("dense"),
                reference_ids=[
                    str(value)
                    for value in file_dense_ids
                ],
                candidate_ids=[
                    str(value)
                    for value in qdrant_dense_ids
                ],
            ):
                comparisons_ok = False
                problems.append(
                    f"{query_id}:{scenario_id}:"
                    "invalid_dense_comparison"
                )

            if not valid_comparison(
                comparison.get("final"),
                reference_ids=[
                    str(value)
                    for value in file_final_ids
                ],
                candidate_ids=[
                    str(value)
                    for value in qdrant_final_ids
                ],
            ):
                comparisons_ok = False
                problems.append(
                    f"{query_id}:{scenario_id}:"
                    "invalid_final_comparison"
                )

            metric_deltas = _mapping(
                comparison.get(
                    "metric_deltas"
                )
            )
            if not all(
                _finite(
                    metric_deltas.get(name)
                )
                for name in (
                    "hit",
                    "precision",
                    "recall",
                    "mrr",
                    "ndcg",
                )
            ):
                metrics_ok = False
                problems.append(
                    f"{query_id}:{scenario_id}:"
                    "invalid_metric_deltas"
                )

            classification = str(
                comparison.get(
                    "classification"
                )
                or ""
            )
            blocking = comparison.get(
                "blocking"
            )

            if not (
                classification
                and isinstance(blocking, bool)
                and bool(
                    comparison.get("reason")
                )
            ):
                classifications_ok = False
                problems.append(
                    f"{query_id}:{scenario_id}:"
                    "invalid_classification"
                )

            determinism = _mapping(
                scenario.get("determinism")
            )

            if not (
                isinstance(
                    determinism.get("stable"),
                    bool,
                )
                and all(
                    valid_determinism_summary(
                        determinism.get(name)
                    )
                    for name in (
                        "file_dense",
                        "qdrant_dense",
                        "file_final",
                        "qdrant_final",
                    )
                )
            ):
                determinism_ok = False
                problems.append(
                    f"{query_id}:{scenario_id}:"
                    "invalid_determinism"
                )

        if (
            vector_fingerprints
            and any(
                dict(value)
                != dict(
                    vector_fingerprints[0]
                )
                for value
                in vector_fingerprints[1:]
            )
        ):
            shared_evidence_ok = False
            problems.append(
                f"{query_id}:query_vector_mismatch"
            )

    checks["scenario_coverage_valid"] = (
        scenario_coverage_ok
    )
    checks["shared_evidence_valid"] = (
        shared_evidence_ok
    )
    checks["backend_evidence_valid"] = (
        backend_evidence_ok
    )
    checks["result_ids_valid"] = (
        result_ids_ok
    )
    checks["comparisons_valid"] = (
        comparisons_ok
    )
    checks["metrics_valid"] = metrics_ok
    checks["timings_valid"] = timings_ok
    checks["determinism_records_valid"] = (
        determinism_ok
    )
    checks["classifications_valid"] = (
        classifications_ok
    )

    checks["errors_coherent"] = (
        len(errors) == error_count
    )
    checks["source_complete"] = (
        summary.get("complete") is True
    )
    checks["source_quality_ok"] = (
        summary.get("quality_ok") is True
    )
    checks["source_verdict_ok"] = (
        verdict.get("ok") is True
    )
    checks["no_errors"] = (
        error_count == 0
        and errors == []
    )
    checks["all_scenarios_successful"] = (
        successful_scenarios
        == expected_scenarios
    )
    checks["no_blocking_classifications"] = (
        summary.get(
            "blocking_classification_count"
        )
        == 0
        and _list(
            summary.get(
                "blocking_classifications"
            )
        )
        == []
    )
    checks["deterministic_results"] = (
        summary.get(
            "determinism_failure_count"
        )
        == 0
        and _list(
            summary.get(
                "determinism_failures"
            )
        )
        == []
    )

    final_overlap = _mapping(
        summary.get("final_overlap")
    )
    mean_overlap = final_overlap.get("mean")
    min_overlap = final_overlap.get("min")

    checks["overlap_policy_met"] = (
        _in_unit_interval(mean_overlap)
        and _in_unit_interval(min_overlap)
        and float(mean_overlap)
        >= float(
            quality_config.get(
                "min_mean_final_overlap_at_k",
                0.99,
            )
        )
        and float(min_overlap)
        >= float(
            quality_config.get(
                "min_query_final_overlap_at_k",
                0.95,
            )
        )
    )

    classification_counts = _mapping(
        summary.get(
            "classification_counts"
        )
    )
    checks[
        "classification_counts_coherent"
    ] = (
        all(
            _non_negative_int(value)
            for value in (
                classification_counts.values()
            )
        )
        and sum(
            int(value)
            for value in (
                classification_counts.values()
            )
        )
        == successful_scenarios
    )

    checks["all_numbers_finite"] = (
        all_numbers_finite(source)
    )

    required = [
        "report_exists",
        "input_schema_version_ok",
        "report_name_ok",
        "generated_at_present",
        "embedded_config_present",
        "safety_evaluation_only",
        "safety_production_default_unchanged",
        "safety_public_qdrant_not_promoted",
        "safety_no_fallback",
        "safety_canonical_unchanged",
        "safety_retrieval_build_unchanged",
        "safety_collection_not_mutated",
        "runtime_file_ready",
        "runtime_build_id_present",
        "runtime_corpus_count_valid",
        "runtime_embedding_valid",
        "qdrant_collection_matches",
        "qdrant_transport_matches",
        "qdrant_profile_matches",
        "scenario_matrix_valid",
        "summary_counts_valid",
        "query_results_count_valid",
        "query_ids_unique",
        "scenario_coverage_valid",
        "shared_evidence_valid",
        "backend_evidence_valid",
        "result_ids_valid",
        "comparisons_valid",
        "metrics_valid",
        "timings_valid",
        "determinism_records_valid",
        "classifications_valid",
        "errors_coherent",
        "classification_counts_coherent",
        "all_numbers_finite",
    ]

    if strict:
        required.extend(
            [
                "enabled_query_count_expected",
                "full_query_set_selected",
                "source_complete",
                "source_quality_ok",
                "source_verdict_ok",
                "no_errors",
                "all_scenarios_successful",
                "no_blocking_classifications",
                "deterministic_results",
                "overlap_policy_met",
            ]
        )

    required_failed = [
        name
        for name in required
        if checks.get(name) is not True
    ]

    return {
        "checks": checks,
        "problems": problems,
        "required_checks": required,
        "required_failed_checks": (
            required_failed
        ),
        "ok": not required_failed,
    }


def build_markdown(
    report: Mapping[str, Any],
) -> str:
    verdict = _mapping(
        report.get("verdict")
    )
    summary = _mapping(
        report.get("summary")
    )

    lines = [
        "# Qdrant Hybrid Evaluation Quality",
        "",
        (
            f"- schema_version: "
            f"`{report.get('schema_version')}`"
        ),
        (
            f"- input_schema_version: "
            f"`{summary.get('input_schema_version')}`"
        ),
        (
            f"- strict: "
            f"`{verdict.get('strict')}`"
        ),
        (
            f"- ok: "
            f"**{verdict.get('ok')}**"
        ),
        (
            f"- required_failed_count: "
            f"`{verdict.get('required_failed_count')}`"
        ),
        "",
        "## Summary",
        "",
        (
            f"- build_id: "
            f"`{summary.get('build_id')}`"
        ),
        (
            f"- collection_name: "
            f"`{summary.get('collection_name')}`"
        ),
        (
            f"- transport: "
            f"`{summary.get('transport')}`"
        ),
        (
            f"- profile_name: "
            f"`{summary.get('profile_name')}`"
        ),
        (
            f"- enabled_query_count: "
            f"`{summary.get('enabled_query_count')}`"
        ),
        (
            f"- selected_query_count: "
            f"`{summary.get('selected_query_count')}`"
        ),
        (
            f"- expected_scenario_count: "
            f"`{summary.get('expected_scenario_count')}`"
        ),
        (
            f"- error_count: "
            f"`{summary.get('error_count')}`"
        ),
        (
            f"- mean_final_overlap: "
            f"`{summary.get('mean_final_overlap')}`"
        ),
        (
            f"- min_final_overlap: "
            f"`{summary.get('min_final_overlap')}`"
        ),
        "",
        "## Checks",
        "",
    ]

    for name, value in _mapping(
        report.get("checks")
    ).items():
        icon = "✅" if value else "❌"
        lines.append(
            f"- {icon} `{name}` = `{value}`"
        )

    problems = _list(
        report.get("problems")
    )
    if problems:
        lines.extend(
            [
                "",
                "## Problems",
                "",
            ]
        )
        lines.extend(
            f"- `{problem}`"
            for problem in problems[:200]
        )

    lines.append("")
    return "\n".join(lines)


def main(
    argv: Sequence[str] | None = None,
) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_PATH,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument(
        "--strict",
        action="store_true",
    )
    args = parser.parse_args(argv)

    run_ts = utc_now_ts()
    report_exists = (
        args.report_path.exists()
    )

    config = load_yaml(args.config_path)

    source = (
        load_json(args.report_path)
        if report_exists
        else {}
    )

    evaluation = evaluate_report(
        source,
        config=config,
        strict=bool(args.strict),
        report_exists=report_exists,
    )

    source_summary = _mapping(
        source.get("summary")
    )
    runtime = _mapping(
        source.get("runtime")
    )
    qdrant = _mapping(
        source.get("qdrant")
    )
    profile = _mapping(
        qdrant.get("profile")
    )
    final_overlap = _mapping(
        source_summary.get(
            "final_overlap"
        )
    )

    summary = {
        "input_schema_version": (
            source.get("schema_version")
        ),
        "build_id": runtime.get(
            "build_id"
        ),
        "corpus_doc_count": runtime.get(
            "corpus_doc_count"
        ),
        "collection_name": qdrant.get(
            "collection_name"
        ),
        "transport": qdrant.get(
            "transport"
        ),
        "profile_name": profile.get(
            "name"
        ),
        "enabled_query_count": (
            source_summary.get(
                "enabled_query_count"
            )
        ),
        "selected_query_count": (
            source_summary.get(
                "selected_query_count"
            )
        ),
        "expected_scenario_count": (
            source_summary.get(
                "expected_scenario_count"
            )
        ),
        "successful_scenario_count": (
            source_summary.get(
                "successful_scenario_count"
            )
        ),
        "error_count": source_summary.get(
            "error_count"
        ),
        "mean_final_overlap": (
            final_overlap.get("mean")
        ),
        "min_final_overlap": (
            final_overlap.get("min")
        ),
        "blocking_classification_count": (
            source_summary.get(
                "blocking_classification_count"
            )
        ),
        "determinism_failure_count": (
            source_summary.get(
                "determinism_failure_count"
            )
        ),
    }

    verdict = {
        "ok": bool(evaluation["ok"]),
        "strict": bool(args.strict),
        "required_failed_count": len(
            evaluation[
                "required_failed_checks"
            ]
        ),
        "required_failed_checks": list(
            evaluation[
                "required_failed_checks"
            ]
        ),
    }

    quality_report = {
        "schema_version": (
            QUALITY_SCHEMA_VERSION
        ),
        "report_name": (
            "check_qdrant_hybrid_evaluation"
        ),
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "inputs": {
            "config_path": normalize_path(
                args.config_path
            ),
            "report_path": normalize_path(
                args.report_path
            ),
        },
        "summary": summary,
        "checks": evaluation["checks"],
        "problems": evaluation["problems"],
        "verdict": verdict,
    }

    latest_json = (
        args.output_dir
        / (
            "qdrant_hybrid_evaluation_"
            "quality_latest.json"
        )
    )
    latest_md = (
        args.output_dir
        / (
            "qdrant_hybrid_evaluation_"
            "quality_latest.md"
        )
    )
    history_json = (
        args.output_dir
        / "history"
        / (
            "qdrant_hybrid_evaluation_"
            f"quality_{run_ts}.json"
        )
    )
    history_md = (
        args.output_dir
        / "history"
        / (
            "qdrant_hybrid_evaluation_"
            f"quality_{run_ts}.md"
        )
    )

    markdown = build_markdown(
        quality_report
    )

    dump_json(
        latest_json,
        quality_report,
    )
    dump_text(
        latest_md,
        markdown,
    )
    dump_json(
        history_json,
        quality_report,
    )
    dump_text(
        history_md,
        markdown,
    )

    print(
        f"[OK] report_path="
        f"{args.report_path}"
    )
    print(
        f"[OK] schema_version="
        f"{QUALITY_SCHEMA_VERSION}"
    )
    print(
        f"[OK] input_schema_version="
        f"{summary['input_schema_version']}"
    )
    print(
        f"[OK] strict={args.strict}"
    )
    print(
        f"[OK] build_id="
        f"{summary['build_id']}"
    )
    print(
        f"[OK] selected_query_count="
        f"{summary['selected_query_count']}"
    )
    print(
        f"[OK] expected_scenario_count="
        f"{summary['expected_scenario_count']}"
    )
    print(
        "[OK] required_failed_count="
        f"{verdict['required_failed_count']}"
    )
    print(
        f"[OK] latest JSON: {latest_json}"
    )
    print(
        f"[OK] latest Markdown: {latest_md}"
    )

    if args.strict and not verdict["ok"]:
        print(
            "[FAIL] required_failed_checks:"
        )
        for name in verdict[
            "required_failed_checks"
        ]:
            print(f"  - {name}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()