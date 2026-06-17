from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "PyYAML is required for ranking evaluation validation."
    ) from exc


DEFAULT_CONFIG_PATH = Path("configs/ranking_evaluation_v1.yaml")
DEFAULT_REPORT_PATH = Path(
    "artifacts/reports/evaluation/ranking_evaluation_latest.json"
)
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")

SCORE_FIELDS_01 = (
    "retrieval_score_normalized",
    "recency_score",
    "source_support_score",
    "metadata_quality_score",
)

METRIC_NAMES = ("hit", "precision", "recall", "mrr", "ndcg")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a YAML mapping: {path}")
    return payload


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON report not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON report must be an object: {path}")
    return payload


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def all_numbers_finite(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, str)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(all_numbers_finite(item) for item in value)
    if isinstance(value, dict):
        return all(all_numbers_finite(item) for item in value.values())
    return True


def approx_equal(
    left: Any,
    right: Any,
    tolerance: float,
) -> bool:
    return abs(safe_float(left) - safe_float(right)) <= tolerance


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(float(statistics.fmean(values)), 6)


def profile_names(config: dict[str, Any]) -> list[str]:
    return [
        str(profile.get("name") or "")
        for profile in config.get("profiles") or []
    ]


def profile_apply_ranking(config: dict[str, Any]) -> dict[str, bool]:
    return {
        str(profile.get("name") or ""): bool(profile.get("apply_ranking"))
        for profile in config.get("profiles") or []
    }


def permitted_classifications(config: dict[str, Any]) -> set[str]:
    return {
        str(value)
        for value in (
            (config.get("classifications") or {}).get("primary") or []
        )
    }


def permitted_decisions(config: dict[str, Any]) -> set[str]:
    return {
        str(value)
        for value in (
            (config.get("decision_policy") or {}).get("permitted_outcomes")
            or []
        )
    }


def run_key(run: dict[str, Any]) -> tuple[str, int, str]:
    return (
        str(run.get("query_id") or ""),
        safe_int(run.get("candidate_k")),
        str(run.get("profile_name") or ""),
    )


def profile_depth_key(row: dict[str, Any]) -> tuple[str, int]:
    return (
        str(row.get("profile_name") or ""),
        safe_int(row.get("candidate_k")),
    )


def metrics_for_run(
    run: dict[str, Any],
    metric_k: int,
) -> dict[str, Any]:
    return (
        (run.get("metrics_after") or {}).get(str(metric_k))
        or {}
    )


def quality_composite(
    *,
    recall: float,
    ndcg: float,
    mrr: float,
    weights: dict[str, Any],
) -> float:
    return round(
        recall * safe_float(weights.get("recall"), 0.40)
        + ndcg * safe_float(weights.get("ndcg"), 0.40)
        + mrr * safe_float(weights.get("mrr"), 0.20),
        6,
    )


def _append_violation(
    diagnostics: dict[str, list[str]],
    category: str,
    message: str,
    *,
    limit: int = 25,
) -> None:
    bucket = diagnostics.setdefault(category, [])
    if len(bucket) < limit:
        bucket.append(message)


def validate_run_integrity(
    *,
    run: dict[str, Any],
    expected_apply_ranking: dict[str, bool],
    allowed_classifications: set[str],
    tolerance: float,
    diagnostics: dict[str, list[str]],
) -> dict[str, bool]:
    key = run_key(run)
    label = f"{key[0]}|k={key[1]}|{key[2]}"

    no_error = not bool(run.get("error"))
    if not no_error:
        _append_violation(
            diagnostics,
            "runtime_errors",
            f"{label}: {run.get('error')}",
        )
        return {
            "no_error": False,
            "classification_ok": False,
            "determinism_ok": False,
            "candidate_ids_unique": False,
            "rank_permutations_valid": False,
            "scores_finite": False,
            "score_ranges_valid": False,
            "result_ids_valid": False,
            "apply_ranking_matches_config": False,
        }

    profile_name = key[2]
    apply_ranking = bool(run.get("apply_ranking"))
    expected_apply = expected_apply_ranking.get(profile_name)
    apply_matches = expected_apply is not None and apply_ranking == expected_apply
    if not apply_matches:
        _append_violation(
            diagnostics,
            "apply_ranking_mismatch",
            f"{label}: report={apply_ranking}, config={expected_apply}",
        )

    classification = run.get("effect_classification")
    if apply_ranking:
        classification_ok = str(classification or "") in allowed_classifications
    else:
        classification_ok = classification in (None, "")
    if not classification_ok:
        _append_violation(
            diagnostics,
            "classification_errors",
            f"{label}: classification={classification!r}",
        )

    determinism = run.get("determinism") or {}
    determinism_ok = bool(determinism.get("ok"))
    if not determinism_ok:
        _append_violation(
            diagnostics,
            "determinism_errors",
            label,
        )

    evidence = list(run.get("candidate_evidence") or [])
    candidate_count = safe_int(run.get("candidate_count"))
    evidence_count_ok = len(evidence) == candidate_count
    if not evidence_count_ok:
        _append_violation(
            diagnostics,
            "candidate_evidence_count",
            f"{label}: evidence={len(evidence)}, candidate_count={candidate_count}",
        )

    evidence_ids = [
        str(row.get("canonical_id") or "")
        for row in evidence
    ]
    candidate_ids_unique = (
        bool(evidence_ids)
        and all(evidence_ids)
        and len(evidence_ids) == len(set(evidence_ids))
        and evidence_count_ok
    )
    if not candidate_ids_unique:
        _append_violation(
            diagnostics,
            "candidate_id_errors",
            label,
        )

    rank_before = [safe_int(row.get("rank_before")) for row in evidence]
    rank_after = [safe_int(row.get("rank_after")) for row in evidence]
    expected_ranks = list(range(1, len(evidence) + 1))
    rank_permutations_valid = (
        sorted(rank_before) == expected_ranks
        and sorted(rank_after) == expected_ranks
        and rank_after == expected_ranks
    )
    if not rank_permutations_valid:
        _append_violation(
            diagnostics,
            "rank_permutation_errors",
            label,
        )

    scores_finite = True
    score_ranges_valid = True
    for row in evidence:
        raw_score = row.get("retrieval_score_raw")
        if not is_finite_number(raw_score):
            scores_finite = False

        for field in SCORE_FIELDS_01:
            value = row.get(field)
            if not is_finite_number(value):
                scores_finite = False
                score_ranges_valid = False
                continue
            numeric = safe_float(value)
            if numeric < -tolerance or numeric > 1.0 + tolerance:
                score_ranges_valid = False

        final_score = row.get("final_score")
        if apply_ranking:
            if not is_finite_number(final_score):
                scores_finite = False
                score_ranges_valid = False
            else:
                numeric = safe_float(final_score)
                if numeric < -tolerance or numeric > 1.0 + tolerance:
                    score_ranges_valid = False
        elif final_score is not None:
            score_ranges_valid = False

    if not scores_finite:
        _append_violation(
            diagnostics,
            "non_finite_scores",
            label,
        )
    if not score_ranges_valid:
        _append_violation(
            diagnostics,
            "score_range_errors",
            label,
        )

    before_ids = [
        str(value)
        for value in run.get("result_ids_before") or []
    ]
    after_ids = [
        str(value)
        for value in run.get("result_ids_after") or []
    ]
    evidence_id_set = set(evidence_ids)
    result_ids_valid = (
        len(before_ids) == len(set(before_ids))
        and len(after_ids) == len(set(after_ids))
        and set(before_ids).issubset(evidence_id_set)
        and set(after_ids).issubset(evidence_id_set)
    )
    if not result_ids_valid:
        _append_violation(
            diagnostics,
            "result_id_errors",
            label,
        )

    return {
        "no_error": no_error,
        "classification_ok": classification_ok,
        "determinism_ok": determinism_ok,
        "candidate_ids_unique": candidate_ids_unique,
        "rank_permutations_valid": rank_permutations_valid,
        "scores_finite": scores_finite,
        "score_ranges_valid": score_ranges_valid,
        "result_ids_valid": result_ids_valid,
        "apply_ranking_matches_config": apply_matches,
    }


def validate_retrieval_only_invariant(
    *,
    runs: list[dict[str, Any]],
    tolerance: float,
    diagnostics: dict[str, list[str]],
) -> bool:
    by_key = {
        run_key(run): run
        for run in runs
        if not run.get("error")
    }

    unranked_keys = [
        key
        for key in by_key
        if key[2] == "unranked"
    ]

    ok = True
    for query_id, candidate_k, _ in unranked_keys:
        unranked = by_key[(query_id, candidate_k, "unranked")]
        retrieval_only = by_key.get(
            (query_id, candidate_k, "retrieval_only")
        )
        label = f"{query_id}|k={candidate_k}"

        if retrieval_only is None:
            ok = False
            _append_violation(
                diagnostics,
                "retrieval_only_invariant",
                f"{label}: retrieval_only run missing",
            )
            continue

        if (
            unranked.get("result_ids_after")
            != retrieval_only.get("result_ids_after")
        ):
            ok = False
            _append_violation(
                diagnostics,
                "retrieval_only_invariant",
                f"{label}: result order differs",
            )

        unranked_metrics = unranked.get("metrics_after") or {}
        retrieval_metrics = retrieval_only.get("metrics_after") or {}
        for k in set(unranked_metrics) | set(retrieval_metrics):
            for metric in METRIC_NAMES:
                if not approx_equal(
                    (unranked_metrics.get(k) or {}).get(metric),
                    (retrieval_metrics.get(k) or {}).get(metric),
                    tolerance,
                ):
                    ok = False
                    _append_violation(
                        diagnostics,
                        "retrieval_only_invariant",
                        f"{label}: {metric}@{k} differs",
                    )

    return ok


def validate_profile_summary_consistency(
    *,
    config: dict[str, Any],
    report: dict[str, Any],
    tolerance: float,
    diagnostics: dict[str, list[str]],
) -> bool:
    runs = [
        run
        for run in report.get("runs") or []
        if not run.get("error")
    ]
    rows = list(report.get("profile_summary") or [])
    rows_by_name = {
        str(row.get("profile_name") or ""): row
        for row in rows
    }

    expected_profiles = profile_names(config)
    metric_k_values = [
        safe_int(value)
        for value in (
            (config.get("defaults") or {}).get("metric_k_values")
            or []
        )
    ]
    primary_k = safe_int(
        (config.get("defaults") or {}).get("primary_k"),
        10,
    )
    quality_weights = (
        (config.get("analysis") or {}).get("quality_composite_weights")
        or {}
    )

    if set(rows_by_name) != set(expected_profiles):
        _append_violation(
            diagnostics,
            "profile_summary",
            (
                f"profile set differs: report={sorted(rows_by_name)}, "
                f"config={sorted(expected_profiles)}"
            ),
        )
        return False

    ok = True
    for profile_name in expected_profiles:
        selected = [
            run
            for run in runs
            if str(run.get("profile_name") or "") == profile_name
        ]
        row = rows_by_name[profile_name]

        if safe_int(row.get("runs_count")) != len(selected):
            ok = False
            _append_violation(
                diagnostics,
                "profile_summary",
                f"{profile_name}: runs_count mismatch",
            )

        expected_removed = sum(
            len(run.get("relevant_removed_from_top_k") or [])
            for run in selected
        )
        expected_added = sum(
            len(run.get("relevant_added_to_top_k") or [])
            for run in selected
        )
        if safe_int(row.get("relevant_removed_from_top_k_count")) != expected_removed:
            ok = False
            _append_violation(
                diagnostics,
                "profile_summary",
                f"{profile_name}: relevant_removed count mismatch",
            )
        if safe_int(row.get("relevant_added_to_top_k_count")) != expected_added:
            ok = False
            _append_violation(
                diagnostics,
                "profile_summary",
                f"{profile_name}: relevant_added count mismatch",
            )

        expected_mean_moved = mean(
            [
                safe_float(run.get("moved_candidate_count"))
                for run in selected
            ]
        )
        if not approx_equal(
            row.get("mean_moved_candidate_count"),
            expected_mean_moved,
            tolerance,
        ):
            ok = False
            _append_violation(
                diagnostics,
                "profile_summary",
                f"{profile_name}: mean_moved mismatch",
            )

        for metric_k in metric_k_values:
            metric_rows = [
                metrics_for_run(run, metric_k)
                for run in selected
            ]
            for metric in METRIC_NAMES:
                expected_value = mean(
                    [
                        safe_float(metric_row.get(metric))
                        for metric_row in metric_rows
                    ]
                )
                field = f"{metric}_at_{metric_k}"
                if not approx_equal(
                    row.get(field),
                    expected_value,
                    tolerance,
                ):
                    ok = False
                    _append_violation(
                        diagnostics,
                        "profile_summary",
                        f"{profile_name}: {field} mismatch",
                    )

        expected_quality = quality_composite(
            recall=safe_float(row.get(f"recall_at_{primary_k}")),
            ndcg=safe_float(row.get(f"ndcg_at_{primary_k}")),
            mrr=safe_float(row.get(f"mrr_at_{primary_k}")),
            weights=quality_weights,
        )
        if not approx_equal(
            row.get("quality_composite"),
            expected_quality,
            tolerance,
        ):
            ok = False
            _append_violation(
                diagnostics,
                "profile_summary",
                f"{profile_name}: quality_composite mismatch",
            )

        expected_classifications = Counter(
            str(run.get("effect_classification"))
            for run in selected
            if run.get("effect_classification")
        )
        if dict(expected_classifications) != (
            row.get("classification_counts") or {}
        ):
            ok = False
            _append_violation(
                diagnostics,
                "profile_summary",
                f"{profile_name}: classification_counts mismatch",
            )

    return ok


def validate_profile_depth_summary(
    *,
    config: dict[str, Any],
    report: dict[str, Any],
    diagnostics: dict[str, list[str]],
) -> bool:
    rows = list(report.get("profile_depth_summary") or [])
    actual_keys = {
        profile_depth_key(row)
        for row in rows
    }
    expected_keys = {
        (profile, candidate_k)
        for profile in profile_names(config)
        for candidate_k in (
            (config.get("defaults") or {}).get("candidate_k_values")
            or []
        )
    }

    ok = (
        len(rows) == len(actual_keys)
        and actual_keys == expected_keys
    )
    if not ok:
        _append_violation(
            diagnostics,
            "profile_depth_summary",
            (
                f"actual={sorted(actual_keys)}, "
                f"expected={sorted(expected_keys)}"
            ),
        )
    return ok


def validate_sensitivity(
    *,
    config: dict[str, Any],
    report: dict[str, Any],
    diagnostics: dict[str, list[str]],
) -> bool:
    rows = list(report.get("candidate_pool_sensitivity") or [])
    defaults = config.get("defaults") or {}
    candidate_depths = sorted(
        safe_int(value)
        for value in defaults.get("candidate_k_values") or []
    )
    query_count = safe_int(
        (report.get("summary") or {}).get("enabled_cases_count")
    )
    expected_rows = (
        query_count
        * len(profile_names(config))
        * max(0, len(candidate_depths) - 1)
    )

    keys: list[tuple[str, str, int, int]] = []
    values_valid = True

    for row in rows:
        key = (
            str(row.get("query_id") or ""),
            str(row.get("profile_name") or ""),
            safe_int(row.get("smaller_candidate_k")),
            safe_int(row.get("larger_candidate_k")),
        )
        keys.append(key)

        overlap_ratio = row.get("top_k_overlap_ratio")
        if (
            not is_finite_number(overlap_ratio)
            or safe_float(overlap_ratio) < 0.0
            or safe_float(overlap_ratio) > 1.0
        ):
            values_valid = False

        if safe_int(row.get("shared_candidate_count")) < 0:
            values_valid = False

        if not all_numbers_finite(row.get("component_changes") or {}):
            values_valid = False

        if not all_numbers_finite(row.get("metric_deltas") or {}):
            values_valid = False

    ok = (
        len(rows) == expected_rows
        and len(keys) == len(set(keys))
        and values_valid
    )
    if not ok:
        _append_violation(
            diagnostics,
            "candidate_pool_sensitivity",
            (
                f"rows={len(rows)}, expected={expected_rows}, "
                f"unique_keys={len(set(keys))}, values_valid={values_valid}"
            ),
        )
    return ok


def build_checks(
    *,
    config: dict[str, Any],
    report: dict[str, Any],
    report_path: Path,
) -> tuple[dict[str, bool], dict[str, list[str]], dict[str, Any]]:
    diagnostics: dict[str, list[str]] = {}
    thresholds = config.get("thresholds") or {}
    defaults = config.get("defaults") or {}
    summary = report.get("summary") or {}
    runs = list(report.get("runs") or [])
    profiles = list(report.get("profiles") or [])
    decision = report.get("decision") or {}

    tolerance = max(
        safe_float(defaults.get("numeric_tolerance"), 1e-12),
        1e-12,
    )

    config_profiles = profile_names(config)
    report_profile_names = [
        str(profile.get("name") or "")
        for profile in profiles
    ]
    candidate_depths = [
        safe_int(value)
        for value in defaults.get("candidate_k_values") or []
    ]

    query_ids = [
        str(row.get("query_id") or "")
        for row in report.get("query_cache_meta") or []
    ]
    expected_run_keys = {
        (query_id, candidate_k, profile_name)
        for query_id in query_ids
        for candidate_k in candidate_depths
        for profile_name in config_profiles
    }
    actual_run_keys = [run_key(run) for run in runs]

    allowed_classifications = permitted_classifications(config)
    expected_apply = profile_apply_ranking(config)

    run_integrity_results = [
        validate_run_integrity(
            run=run,
            expected_apply_ranking=expected_apply,
            allowed_classifications=allowed_classifications,
            tolerance=tolerance,
            diagnostics=diagnostics,
        )
        for run in runs
    ]

    deep_checks = {
        name: all(result.get(name, False) for result in run_integrity_results)
        if run_integrity_results
        else False
        for name in (
            "no_error",
            "classification_ok",
            "determinism_ok",
            "candidate_ids_unique",
            "rank_permutations_valid",
            "scores_finite",
            "score_ranges_valid",
            "result_ids_valid",
            "apply_ranking_matches_config",
        )
    }

    ranked_runs = [
        run
        for run in runs
        if bool(run.get("apply_ranking"))
    ]
    classified_ranked_runs = [
        run
        for run in ranked_runs
        if str(run.get("effect_classification") or "")
        in allowed_classifications
    ]

    sensitivity_rows = list(
        report.get("candidate_pool_sensitivity") or []
    )
    profile_summary = list(report.get("profile_summary") or [])
    profile_depth_summary = list(
        report.get("profile_depth_summary") or []
    )

    checks: dict[str, bool] = {
        "report_path_exists": report_path.exists(),
        "schema_version_ok": (
            report.get("schema_version") == "ranking_evaluation_v1"
        ),
        "report_name_ok": (
            report.get("report_name") == "ranking_evaluation"
        ),
        "runtime_ready": bool((report.get("runtime") or {}).get("ready")),
        "backend_mode_file": (
            (report.get("runtime") or {}).get("backend_mode") == "file"
        ),
        "public_behavior_change_disabled": (
            not bool(
                (config.get("metadata") or {}).get(
                    "public_behavior_change"
                )
            )
            and not bool(
                (config.get("decision_policy") or {}).get(
                    "change_public_default_during_evaluation"
                )
            )
            and not bool(decision.get("automatic_public_change_allowed"))
        ),
        "enabled_cases_min_met": (
            safe_int(summary.get("enabled_cases_count"))
            >= safe_int(thresholds.get("min_enabled_cases"), 1)
        ),
        "profiles_count_matches_config": (
            safe_int(summary.get("profiles_count"))
            == len(config_profiles)
            == safe_int(
                thresholds.get(
                    "expected_profiles_count",
                    len(config_profiles),
                )
            )
            and report_profile_names == config_profiles
        ),
        "candidate_depths_count_matches_config": (
            safe_int(summary.get("candidate_depths_count"))
            == len(candidate_depths)
            == safe_int(
                thresholds.get(
                    "expected_candidate_depths_count",
                    len(candidate_depths),
                )
            )
        ),
        "query_cache_count_matches_enabled_cases": (
            len(query_ids)
            == len(set(query_ids))
            == safe_int(summary.get("enabled_cases_count"))
        ),
        "runs_count_matches_expected": (
            len(runs)
            == len(actual_run_keys)
            == len(set(actual_run_keys))
            == len(expected_run_keys)
            == safe_int(summary.get("runs_count"))
            == safe_int(summary.get("expected_runs_count"))
            and set(actual_run_keys) == expected_run_keys
        ),
        "summary_error_count_zero": (
            safe_int(summary.get("error_count")) == 0
        ),
        "summary_determinism_failure_count_zero": (
            safe_int(summary.get("determinism_failure_count")) == 0
        ),
        "ranked_comparisons_count_matches": (
            safe_int(summary.get("ranked_comparisons_count"))
            == len(ranked_runs)
        ),
        "all_ranked_comparisons_classified": (
            len(ranked_runs)
            == len(classified_ranked_runs)
            and sum(
                safe_int(value)
                for value in (
                    summary.get("classification_counts") or {}
                ).values()
            )
            == len(ranked_runs)
        ),
        "runs_present": bool(runs),
        "profile_summary_present": bool(profile_summary),
        "profile_depth_summary_present": bool(profile_depth_summary),
        "candidate_pool_sensitivity_present": bool(sensitivity_rows),
        "decision_present": bool(decision),
        "decision_outcome_permitted": (
            str(decision.get("recommended_outcome") or "")
            in permitted_decisions(config)
        ),
        "decision_requires_review_and_validator": (
            bool(decision.get("requires_manual_review"))
            and bool(decision.get("requires_strict_validator"))
        ),
        "report_numbers_finite": all_numbers_finite(report),
        "run_no_errors": deep_checks["no_error"],
        "run_classifications_valid": deep_checks["classification_ok"],
        "run_determinism_valid": deep_checks["determinism_ok"],
        "run_candidate_ids_unique": deep_checks["candidate_ids_unique"],
        "run_rank_permutations_valid": deep_checks["rank_permutations_valid"],
        "run_scores_finite": deep_checks["scores_finite"],
        "run_score_ranges_valid": deep_checks["score_ranges_valid"],
        "run_result_ids_valid": deep_checks["result_ids_valid"],
        "run_apply_ranking_matches_config": deep_checks[
            "apply_ranking_matches_config"
        ],
        "retrieval_only_matches_unranked": (
            validate_retrieval_only_invariant(
                runs=runs,
                tolerance=tolerance,
                diagnostics=diagnostics,
            )
        ),
        "profile_summary_consistent": (
            validate_profile_summary_consistency(
                config=config,
                report=report,
                tolerance=max(tolerance, 1e-6),
                diagnostics=diagnostics,
            )
        ),
        "profile_depth_summary_complete": (
            validate_profile_depth_summary(
                config=config,
                report=report,
                diagnostics=diagnostics,
            )
        ),
        "candidate_pool_sensitivity_consistent": (
            validate_sensitivity(
                config=config,
                report=report,
                diagnostics=diagnostics,
            )
        ),
    }

    extracted = {
        "evaluation_schema_version": report.get("schema_version"),
        "backend_mode": (report.get("runtime") or {}).get("backend_mode"),
        "build_id": (report.get("runtime") or {}).get("build_id"),
        "corpus_doc_count": (report.get("runtime") or {}).get(
            "corpus_doc_count"
        ),
        "enabled_cases_count": summary.get("enabled_cases_count"),
        "profiles_count": summary.get("profiles_count"),
        "candidate_depths_count": summary.get(
            "candidate_depths_count"
        ),
        "expected_runs_count": summary.get("expected_runs_count"),
        "runs_count": summary.get("runs_count"),
        "error_count": summary.get("error_count"),
        "ranked_comparisons_count": summary.get(
            "ranked_comparisons_count"
        ),
        "determinism_failure_count": summary.get(
            "determinism_failure_count"
        ),
        "candidate_pool_sensitivity_rows_count": summary.get(
            "candidate_pool_sensitivity_rows_count"
        ),
        "classification_counts": summary.get(
            "classification_counts"
        ),
        "recommended_outcome": decision.get("recommended_outcome"),
        "best_ranked_profile": decision.get("best_ranked_profile"),
        "unranked_quality_composite": decision.get(
            "unranked_quality_composite"
        ),
        "current_quality_composite": decision.get(
            "current_quality_composite"
        ),
        "best_ranked_quality_composite": decision.get(
            "best_ranked_quality_composite"
        ),
        "current_relevant_removed_from_top_k_count": decision.get(
            "current_relevant_removed_from_top_k_count"
        ),
    }

    return checks, diagnostics, extracted


def required_check_names(*, strict: bool) -> list[str]:
    base = [
        "report_path_exists",
        "schema_version_ok",
        "report_name_ok",
        "runtime_ready",
        "backend_mode_file",
        "public_behavior_change_disabled",
        "enabled_cases_min_met",
        "profiles_count_matches_config",
        "candidate_depths_count_matches_config",
        "query_cache_count_matches_enabled_cases",
        "runs_count_matches_expected",
        "summary_error_count_zero",
        "summary_determinism_failure_count_zero",
        "ranked_comparisons_count_matches",
        "all_ranked_comparisons_classified",
        "runs_present",
        "profile_summary_present",
        "profile_depth_summary_present",
        "candidate_pool_sensitivity_present",
        "decision_present",
        "decision_outcome_permitted",
        "decision_requires_review_and_validator",
        "report_numbers_finite",
    ]

    if strict:
        base.extend(
            [
                "run_no_errors",
                "run_classifications_valid",
                "run_determinism_valid",
                "run_candidate_ids_unique",
                "run_rank_permutations_valid",
                "run_scores_finite",
                "run_score_ranges_valid",
                "run_result_ids_valid",
                "run_apply_ranking_matches_config",
                "retrieval_only_matches_unranked",
                "profile_summary_consistent",
                "profile_depth_summary_complete",
                "candidate_pool_sensitivity_consistent",
            ]
        )

    return base


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Ranking evaluation quality check")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Strict: `{report['strict']}`")
    lines.append(f"- OK: **{report['ok']}**")
    lines.append("")

    lines.append("## Inputs")
    for key, value in report["inputs"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Extracted values")
    for key, value in report["extracted_values"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Checks")
    for key, value in report["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    if report["required_failed_checks"]:
        lines.append("## Required failures")
        for item in report["required_failed_checks"]:
            lines.append(f"- `{item}`")
        lines.append("")

    if report["diagnostics"]:
        lines.append("## Diagnostics")
        for category, messages in report["diagnostics"].items():
            lines.append(f"### {category}")
            for message in messages:
                lines.append(f"- `{message}`")
            lines.append("")

    lines.append("## Validation semantics")
    lines.append("")
    lines.append(
        "A valid report is not required to recommend a ranking profile. "
        "`reject_heuristic_reranking` is a permitted evidence outcome."
    )
    lines.append("")
    lines.append(
        "The validator checks report integrity, determinism, score/rank "
        "contracts, aggregate consistency, and explicit decision semantics. "
        "It does not change public search behavior."
    )
    lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the latest ranking evaluation report."
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
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_ts = utc_now_ts()

    config = load_yaml(args.config_path)
    report = load_json(args.report_path)

    checks, diagnostics, extracted = build_checks(
        config=config,
        report=report,
        report_path=args.report_path,
    )
    required = required_check_names(strict=args.strict)
    required_failed = [
        name
        for name in required
        if not checks.get(name, False)
    ]

    quality_report = {
        "schema_version": "ranking_evaluation_quality_v1",
        "report_name": "check_ranking_evaluation",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            "config_path": normalize_path(args.config_path),
            "report_path": normalize_path(args.report_path),
        },
        "extracted_values": extracted,
        "checks": checks,
        "required_checks": required,
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
        "diagnostics": diagnostics,
        "ok": len(required_failed) == 0,
    }

    output_dir = args.output_dir
    latest_json = (
        output_dir / "ranking_evaluation_quality_latest.json"
    )
    latest_md = (
        output_dir / "ranking_evaluation_quality_latest.md"
    )
    history_json = (
        output_dir
        / "history"
        / f"ranking_evaluation_quality_{run_ts}.json"
    )
    history_md = (
        output_dir
        / "history"
        / f"ranking_evaluation_quality_{run_ts}.md"
    )

    dump_json(latest_json, quality_report)
    dump_text(latest_md, build_markdown(quality_report))
    dump_json(history_json, quality_report)
    dump_text(history_md, build_markdown(quality_report))

    print(f"[OK] report_path={args.report_path}")
    print(f"[OK] schema_version={report.get('schema_version')}")
    print(f"[OK] strict={args.strict}")
    print(f"[OK] required_failed_count={len(required_failed)}")
    print(
        "[OK] recommended_outcome="
        f"{extracted.get('recommended_outcome')}"
    )
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history Markdown: {history_md}")

    if required_failed:
        print("[FAIL] required_failed_checks:")
        for name in required_failed:
            print(f"  - {name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
