"""Run controlled FileDenseBackend-vs-QdrantDenseBackend hybrid evaluation.

The runner is evaluation-only. It does not:

- mutate the canonical corpus;
- rebuild retrieval artifacts;
- create or update a Qdrant collection;
- change the public /search backend;
- use fallback;
- promote Qdrant.

For every selected Golden Set query it:

1. encodes the query once;
2. executes lexical retrieval once;
3. runs paired file/Qdrant dense retrieval;
4. applies the shared hybrid merge;
5. strictly hydrates both branches;
6. optionally applies the same ranking;
7. calculates relevance and parity metrics;
8. repeats scenarios for determinism evidence;
9. writes latest and historical JSON/Markdown reports.
"""

from __future__ import annotations

import argparse
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from radar_core.retrieval.artifacts import (
    read_manifest,
)
from radar_core.retrieval.dense_backend import (
    FileDenseBackend,
    QdrantDenseBackend,
    QdrantSearchProfile,
)
from radar_core.retrieval.qdrant_store import (
    QdrantRetrievalStore,
)
from scripts.evaluation.qdrant_hybrid_evaluation import (
    REPORT_SCHEMA_VERSION,
    build_scenario_matrix,
    classify_hybrid_difference,
    determinism_summary,
    run_paired_hybrid_scenario,
    validate_hybrid_evaluation_config,
    validate_public_scoring_contract,
)
from scripts.evaluation.run_retrieval_eval import (
    dump_json,
    dump_text,
    load_jsonl,
    load_yaml,
    normalize_path,
    utc_now_iso,
    utc_now_ts,
)
from services.api.runtime import (
    ApiRuntime,
    get_runtime,
)


DEFAULT_CONFIG_PATH = Path(
    "configs/qdrant_hybrid_evaluation_v1.yaml"
)
DEFAULT_OUTPUT_DIR = Path(
    "artifacts/reports/evaluation"
)


def _require_mapping(
    value: Any,
    *,
    name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(
            f"{name} must be a mapping"
        )
    return value


def _positive_int(
    value: Any,
    *,
    name: str,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValueError(
            f"{name} must be a positive integer"
        )

    return int(value)


def _mean(
    values: Sequence[float],
) -> float | None:
    if not values:
        return None

    return round(
        float(statistics.mean(values)),
        6,
    )


def _minimum(
    values: Sequence[float],
) -> float | None:
    if not values:
        return None

    return round(float(min(values)), 6)


def _maximum(
    values: Sequence[float],
) -> float | None:
    if not values:
        return None

    return round(float(max(values)), 6)


def select_enabled_cases(
    rows: Sequence[Mapping[str, Any]],
    *,
    max_queries: int | None,
) -> list[dict[str, Any]]:
    """Select enabled Golden Set cases in stable file order."""

    selected: list[dict[str, Any]] = []

    for row_number, raw_row in enumerate(
        rows,
        start=1,
    ):
        if not isinstance(raw_row, Mapping):
            raise ValueError(
                "Golden query row must be a mapping: "
                f"row={row_number}"
            )

        if raw_row.get("enabled", True) is not True:
            continue

        row = dict(raw_row)

        query_id = str(
            row.get("query_id") or ""
        ).strip()
        query_text = str(
            row.get("query") or ""
        ).strip()

        if not query_id:
            raise ValueError(
                "Enabled Golden query has empty "
                f"query_id at row={row_number}"
            )

        if not query_text:
            raise ValueError(
                "Enabled Golden query has empty "
                f"query text: query_id={query_id}"
            )

        selected.append(row)

    if max_queries is not None:
        selected = selected[:max_queries]

    return selected


def encode_query_once(
    runtime: ApiRuntime,
    *,
    query: str,
) -> tuple[np.ndarray, float]:
    """Encode one normalized query exactly once."""

    if runtime.embedding_model is None:
        raise RuntimeError(
            "Embedding model is not loaded"
        )

    started = time.perf_counter()

    vector = runtime.embedding_model.encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )[0].astype(np.float32)

    elapsed_ms = (
        time.perf_counter() - started
    ) * 1000.0

    if vector.ndim != 1:
        raise RuntimeError(
            "Encoded query vector must be "
            f"one-dimensional: shape={vector.shape}"
        )

    if not np.all(np.isfinite(vector)):
        raise RuntimeError(
            "Encoded query vector contains "
            "non-finite values"
        )

    return vector, elapsed_ms


def run_lexical_once(
    runtime: ApiRuntime,
    *,
    query: str,
    top_k: int,
) -> tuple[list[dict[str, Any]], float]:
    """Execute the common lexical branch once per query."""

    if runtime.lexical_artifacts is None:
        raise RuntimeError(
            "Lexical artifacts are not loaded"
        )

    started = time.perf_counter()

    raw_results = (
        runtime.lexical_artifacts.index.search(
            query=query,
            top_k=top_k,
        )
    )

    elapsed_ms = (
        time.perf_counter() - started
    ) * 1000.0

    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for rank, result in enumerate(
        raw_results,
        start=1,
    ):
        canonical_id = str(
            result.canonical_id or ""
        ).strip()

        if not canonical_id:
            raise RuntimeError(
                "Lexical result has empty "
                f"canonical_id at rank={rank}"
            )

        if canonical_id in seen_ids:
            raise RuntimeError(
                "Duplicate lexical canonical_id: "
                f"{canonical_id}"
            )

        seen_ids.add(canonical_id)

        score = float(result.score)

        if not np.isfinite(score):
            raise RuntimeError(
                "Lexical result has non-finite "
                f"score at rank={rank}"
            )

        candidates.append(
            {
                "canonical_id": canonical_id,
                "score": score,
                "rank": rank,
            }
        )

    return candidates, elapsed_ms


def build_file_backend(
    runtime: ApiRuntime,
) -> FileDenseBackend:
    if runtime.manifest is None:
        raise RuntimeError(
            "Retrieval manifest is not loaded"
        )

    if runtime.dense_artifacts is None:
        raise RuntimeError(
            "Dense artifacts are not loaded"
        )

    return FileDenseBackend(
        embeddings=(
            runtime.dense_artifacts.embeddings
        ),
        ids=runtime.dense_artifacts.ids,
        build_id=runtime.manifest.build_id,
        normalized=(
            runtime.dense_artifacts.meta.get(
                "normalized"
            )
            is True
        ),
    )


def build_qdrant_backend(
    runtime: ApiRuntime,
    *,
    qdrant_config: Mapping[str, Any],
) -> tuple[
    QdrantDenseBackend,
    QdrantRetrievalStore,
]:
    if runtime.manifest is None:
        raise RuntimeError(
            "Retrieval manifest is not loaded"
        )

    if runtime.dense_artifacts is None:
        raise RuntimeError(
            "Dense artifacts are not loaded"
        )

    embeddings = (
        runtime.dense_artifacts.embeddings
    )

    if embeddings.ndim != 2:
        raise RuntimeError(
            "Dense embeddings must be "
            f"two-dimensional: shape={embeddings.shape}"
        )

    profile_config = _require_mapping(
        qdrant_config.get("profile"),
        name="qdrant.profile",
    )

    store = QdrantRetrievalStore(
        host=str(qdrant_config["host"]),
        port=int(qdrant_config["port"]),
        grpc_port=int(
            qdrant_config["grpc_port"]
        ),
        prefer_grpc=bool(
            qdrant_config["prefer_grpc"]
        ),
        collection_name=str(
            qdrant_config["collection_name"]
        ),
        timeout_sec=float(
            qdrant_config["timeout_sec"]
        ),
        check_compatibility=bool(
            qdrant_config[
                "check_compatibility"
            ]
        ),
    )

    profile = QdrantSearchProfile(
        name=str(profile_config["name"]),
        exact=bool(profile_config["exact"]),
        hnsw_ef=int(
            profile_config["hnsw_ef"]
        ),
    )

    backend = QdrantDenseBackend(
        store=store,
        profile=profile,
        expected_build_id=(
            runtime.manifest.build_id
        ),
        expected_corpus_count=(
            runtime.manifest.corpus_doc_count
        ),
        expected_vector_size=int(
            embeddings.shape[1]
        ),
        expected_distance="Cosine",
        dense_ids=(
            runtime.dense_artifacts.ids
        ),
        require_point_id_equals_dense_index=True,
    )

    return backend, store


def compact_repeat_timings(
    runs: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for run_number, run in enumerate(
        runs,
        start=1,
    ):
        rows.append(
            {
                "run_number": run_number,
                "file": dict(
                    (
                        run.get("file") or {}
                    ).get("timing_ms") or {}
                ),
                "qdrant": dict(
                    (
                        run.get("qdrant") or {}
                    ).get("timing_ms") or {}
                ),
            }
        )

    return rows


def apply_repeat_evidence(
    runs: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Attach deterministic-repeat evidence to the primary run."""

    if not runs:
        raise ValueError(
            "Scenario runs must not be empty"
        )

    primary = dict(runs[0])

    file_dense = determinism_summary(
        [
            run["file"]["dense_ids"]
            for run in runs
        ]
    )
    qdrant_dense = determinism_summary(
        [
            run["qdrant"]["dense_ids"]
            for run in runs
        ]
    )
    file_final = determinism_summary(
        [
            run["file"]["final_ids"]
            for run in runs
        ]
    )
    qdrant_final = determinism_summary(
        [
            run["qdrant"]["final_ids"]
            for run in runs
        ]
    )

    stable = all(
        summary["stable"]
        for summary in (
            file_dense,
            qdrant_dense,
            file_final,
            qdrant_final,
        )
    )

    classification = classify_hybrid_difference(
        dense_comparison=(
            primary["comparison"]["dense"]
        ),
        final_comparison=(
            primary["comparison"]["final"]
        ),
        deterministic=stable,
    )

    primary["comparison"].update(
        classification
    )
    primary["determinism"] = {
        "stable": stable,
        "file_dense": file_dense,
        "qdrant_dense": qdrant_dense,
        "file_final": file_final,
        "qdrant_final": qdrant_final,
    }
    primary["repeat_count"] = len(runs)
    primary["repeat_timings"] = (
        compact_repeat_timings(runs)
    )

    return primary


def run_scenario_with_repeats(
    *,
    case: Mapping[str, Any],
    query_vector: np.ndarray,
    lexical_candidates: Sequence[
        Mapping[str, Any]
    ],
    file_backend: FileDenseBackend,
    qdrant_backend: QdrantDenseBackend,
    documents_by_id: Mapping[str, Any],
    scenario: Mapping[str, Any],
    scoring_params: Mapping[str, Any],
    repeated_runs: int,
    mismatch_repeated_runs: int,
) -> dict[str, Any]:
    """Run a scenario and expand repeats only for mismatches."""

    first = run_paired_hybrid_scenario(
        case=case,
        query_vector=query_vector,
        lexical_candidates=lexical_candidates,
        file_backend=file_backend,
        qdrant_backend=qdrant_backend,
        documents_by_id=documents_by_id,
        scenario=scenario,
        scoring_params=scoring_params,
    )

    initial_classification = str(
        first["comparison"].get(
            "classification"
        )
        or ""
    )

    target_runs = (
        mismatch_repeated_runs
        if initial_classification
        != "exact_match"
        else repeated_runs
    )

    runs = [first]

    for _ in range(1, target_runs):
        runs.append(
            run_paired_hybrid_scenario(
                case=case,
                query_vector=query_vector,
                lexical_candidates=(
                    lexical_candidates
                ),
                file_backend=file_backend,
                qdrant_backend=qdrant_backend,
                documents_by_id=(
                    documents_by_id
                ),
                scenario=scenario,
                scoring_params=scoring_params,
            )
        )

    return apply_repeat_evidence(runs)


def summarize_results(
    *,
    query_results: Sequence[Mapping[str, Any]],
    errors: Sequence[Mapping[str, Any]],
    expected_scenario_count: int,
    quality_config: Mapping[str, Any],
) -> dict[str, Any]:
    successful: list[Mapping[str, Any]] = []

    for query_row in query_results:
        for scenario in (
            query_row.get("scenarios") or []
        ):
            if scenario.get("error"):
                continue
            successful.append(scenario)

    dense_overlaps = [
        float(
            scenario["comparison"]["dense"][
                "overlap_ratio"
            ]
        )
        for scenario in successful
    ]
    final_overlaps = [
        float(
            scenario["comparison"]["final"][
                "overlap_ratio"
            ]
        )
        for scenario in successful
    ]

    classifications = Counter(
        str(
            scenario["comparison"].get(
                "classification"
            )
            or "unclassified_difference"
        )
        for scenario in successful
    )

    blocking = [
        {
            "query_id": query_row.get(
                "query_id"
            ),
            "scenario_id": scenario.get(
                "scenario_id"
            ),
            "classification": (
                scenario["comparison"].get(
                    "classification"
                )
            ),
            "reason": (
                scenario["comparison"].get(
                    "reason"
                )
            ),
        }
        for query_row in query_results
        for scenario in (
            query_row.get("scenarios") or []
        )
        if (
            not scenario.get("error")
            and bool(
                scenario["comparison"].get(
                    "blocking"
                )
            )
        )
    ]

    determinism_failures = [
        {
            "query_id": query_row.get(
                "query_id"
            ),
            "scenario_id": scenario.get(
                "scenario_id"
            ),
        }
        for query_row in query_results
        for scenario in (
            query_row.get("scenarios") or []
        )
        if (
            not scenario.get("error")
            and not bool(
                (
                    scenario.get(
                        "determinism"
                    )
                    or {}
                ).get("stable")
            )
        )
    ]

    metric_names = (
        "hit",
        "precision",
        "recall",
        "mrr",
        "ndcg",
    )

    metric_delta_summary: dict[
        str,
        dict[str, float | None],
    ] = {}

    for metric_name in metric_names:
        values = [
            float(
                scenario["comparison"][
                    "metric_deltas"
                ][metric_name]
            )
            for scenario in successful
        ]

        metric_delta_summary[metric_name] = {
            "mean": _mean(values),
            "min": _minimum(values),
            "max": _maximum(values),
        }

    mean_final_overlap = _mean(
        final_overlaps
    )
    min_final_overlap = _minimum(
        final_overlaps
    )

    max_error_count = int(
        quality_config.get(
            "max_error_count",
            0,
        )
    )
    min_mean_overlap = float(
        quality_config.get(
            "min_mean_final_overlap_at_k",
            0.99,
        )
    )
    min_query_overlap = float(
        quality_config.get(
            "min_query_final_overlap_at_k",
            0.95,
        )
    )

    complete = (
        len(successful) + len(errors)
        == expected_scenario_count
    )

    quality_ok = (
        complete
        and len(errors) <= max_error_count
        and bool(successful)
        and mean_final_overlap is not None
        and mean_final_overlap
        >= min_mean_overlap
        and min_final_overlap is not None
        and min_final_overlap
        >= min_query_overlap
        and (
            not quality_config.get(
                "require_no_blocking_classifications",
                True,
            )
            or not blocking
        )
        and (
            not quality_config.get(
                "require_deterministic_results",
                True,
            )
            or not determinism_failures
        )
    )

    return {
        "expected_scenario_count": (
            expected_scenario_count
        ),
        "successful_scenario_count": (
            len(successful)
        ),
        "error_count": len(errors),
        "complete": complete,
        "dense_overlap": {
            "mean": _mean(dense_overlaps),
            "min": _minimum(dense_overlaps),
        },
        "final_overlap": {
            "mean": mean_final_overlap,
            "min": min_final_overlap,
        },
        "exact_dense_order_count": sum(
            bool(
                scenario["comparison"][
                    "dense"
                ]["exact_same_order"]
            )
            for scenario in successful
        ),
        "exact_final_order_count": sum(
            bool(
                scenario["comparison"][
                    "final"
                ]["exact_same_order"]
            )
            for scenario in successful
        ),
        "classification_counts": dict(
            sorted(classifications.items())
        ),
        "blocking_classification_count": (
            len(blocking)
        ),
        "blocking_classifications": blocking,
        "determinism_failure_count": (
            len(determinism_failures)
        ),
        "determinism_failures": (
            determinism_failures
        ),
        "metric_delta_summary": (
            metric_delta_summary
        ),
        "quality_ok": quality_ok,
    }


def build_markdown(
    report: Mapping[str, Any],
) -> str:
    summary = report["summary"]
    verdict = report["verdict"]

    lines = [
        "# Qdrant Hybrid Evaluation v1",
        "",
        "## Safety",
        "",
        (
            f"- Evaluation only: "
            f"**{report['safety']['evaluation_only']}**"
        ),
        (
            f"- Production default changed: "
            f"**{report['safety']['production_default_changed']}**"
        ),
        (
            f"- Public Qdrant promoted: "
            f"**{report['safety']['public_qdrant_promoted']}**"
        ),
        (
            f"- Fallback used: "
            f"**{report['safety']['fallback_used']}**"
        ),
        "",
        "## Runtime",
        "",
        (
            f"- Build ID: "
            f"**{report['runtime']['build_id']}**"
        ),
        (
            f"- Corpus documents: "
            f"**{report['runtime']['corpus_doc_count']}**"
        ),
        (
            f"- Embedding model: "
            f"**{report['runtime']['embedding_model_name']}**"
        ),
        (
            f"- Collection: "
            f"**{report['qdrant']['collection_name']}**"
        ),
        (
            f"- Transport: "
            f"**{report['qdrant']['transport']}**"
        ),
        (
            f"- Profile: "
            f"**{report['qdrant']['profile']['name']}**"
        ),
        "",
        "## Coverage",
        "",
        (
            f"- Enabled queries: "
            f"**{summary['enabled_query_count']}**"
        ),
        (
            f"- Selected queries: "
            f"**{summary['selected_query_count']}**"
        ),
        (
            f"- Scenarios per query: "
            f"**{summary['scenario_count_per_query']}**"
        ),
        (
            f"- Expected scenarios: "
            f"**{summary['expected_scenario_count']}**"
        ),
        (
            f"- Successful scenarios: "
            f"**{summary['successful_scenario_count']}**"
        ),
        (
            f"- Errors: "
            f"**{summary['error_count']}**"
        ),
        "",
        "## Parity",
        "",
        (
            f"- Mean dense overlap: "
            f"**{summary['dense_overlap']['mean']}**"
        ),
        (
            f"- Minimum dense overlap: "
            f"**{summary['dense_overlap']['min']}**"
        ),
        (
            f"- Mean final overlap: "
            f"**{summary['final_overlap']['mean']}**"
        ),
        (
            f"- Minimum final overlap: "
            f"**{summary['final_overlap']['min']}**"
        ),
        (
            f"- Exact dense order: "
            f"**{summary['exact_dense_order_count']}**"
        ),
        (
            f"- Exact final order: "
            f"**{summary['exact_final_order_count']}**"
        ),
        (
            f"- Blocking classifications: "
            f"**{summary['blocking_classification_count']}**"
        ),
        (
            f"- Determinism failures: "
            f"**{summary['determinism_failure_count']}**"
        ),
        "",
        "## Classifications",
        "",
    ]

    classifications = (
        summary.get(
            "classification_counts"
        )
        or {}
    )

    if classifications:
        for name, count in classifications.items():
            lines.append(
                f"- `{name}`: **{count}**"
            )
    else:
        lines.append("- No successful classifications.")

    lines.extend(
        [
            "",
            "## Verdict",
            "",
            (
                f"- Quality OK: "
                f"**{verdict['ok']}**"
            ),
            (
                f"- Error count: "
                f"**{verdict['error_count']}**"
            ),
            (
                f"- Blocking count: "
                f"**{verdict['blocking_classification_count']}**"
            ),
            "",
            (
                "This report does not perform or imply "
                "public Qdrant promotion."
            ),
            "",
        ]
    )

    return "\n".join(lines)


def save_report(
    *,
    report: dict[str, Any],
    output_dir: Path,
    run_ts: str,
) -> dict[str, str]:
    latest_json = (
        output_dir
        / "qdrant_hybrid_evaluation_latest.json"
    )
    latest_md = (
        output_dir
        / "qdrant_hybrid_evaluation_latest.md"
    )
    history_json = (
        output_dir
        / "history"
        / (
            "qdrant_hybrid_evaluation_"
            f"{run_ts}.json"
        )
    )
    history_md = (
        output_dir
        / "history"
        / (
            "qdrant_hybrid_evaluation_"
            f"{run_ts}.md"
        )
    )

    paths = {
        "latest_json": normalize_path(
            latest_json
        ),
        "latest_md": normalize_path(
            latest_md
        ),
        "history_json": normalize_path(
            history_json
        ),
        "history_md": normalize_path(
            history_md
        ),
    }

    report["report_paths"] = paths

    markdown = build_markdown(report)

    dump_json(latest_json, report)
    dump_text(latest_md, markdown)
    dump_json(history_json, report)
    dump_text(history_md, markdown)

    return paths


def run_evaluation(
    *,
    config_path: Path,
    output_dir_override: Path | None,
    max_queries_override: int | None,
) -> dict[str, Any]:
    config = load_yaml(config_path)
    validate_hybrid_evaluation_config(config)

    retrieval_config = _require_mapping(
        config.get("retrieval"),
        name="retrieval",
    )
    evaluation_config = _require_mapping(
        config.get("evaluation"),
        name="evaluation",
    )
    qdrant_config = _require_mapping(
        config.get("qdrant"),
        name="qdrant",
    )
    quality_config = _require_mapping(
        config.get("quality"),
        name="quality",
    )
    output_config = _require_mapping(
        config.get("output"),
        name="output",
    )

    manifest_path = Path(
        str(retrieval_config["manifest_path"])
    )
    golden_queries_path = Path(
        str(
            retrieval_config[
                "golden_queries_path"
            ]
        )
    )
    scoring_config_path = Path(
        str(
            retrieval_config[
                "scoring_config_path"
            ]
        )
    )

    configured_manifest = read_manifest(
        manifest_path
    )
    scoring_config = load_yaml(
        scoring_config_path
    )
    scoring_params = (
        validate_public_scoring_contract(
            config,
            scoring_config,
        )
    )

    runtime = get_runtime()
    runtime.load()

    if runtime.backend_mode != "file":
        raise RuntimeError(
            "Qdrant hybrid evaluation requires "
            "ML_RADAR_SEARCH_BACKEND=file"
        )

    if not runtime.is_ready():
        raise RuntimeError(
            "File API runtime is not ready"
        )

    if runtime.manifest is None:
        raise RuntimeError(
            "Runtime manifest is not loaded"
        )

    if (
        runtime.manifest.build_id
        != configured_manifest.build_id
    ):
        raise RuntimeError(
            "Configured manifest and runtime "
            "build IDs differ: "
            f"configured={configured_manifest.build_id}, "
            f"runtime={runtime.manifest.build_id}"
        )

    if (
        runtime.manifest.corpus_doc_count
        != configured_manifest.corpus_doc_count
    ):
        raise RuntimeError(
            "Configured manifest and runtime "
            "corpus counts differ"
        )

    file_backend = build_file_backend(runtime)
    qdrant_backend, store = (
        build_qdrant_backend(
            runtime,
            qdrant_config=qdrant_config,
        )
    )

    collection_info = (
        store.get_collection_info()
    )
    collection_info["count_points_exact"] = (
        store.count_points(exact=True)
    )

    golden_rows = load_jsonl(
        golden_queries_path
    )
    all_enabled_cases = select_enabled_cases(
        golden_rows,
        max_queries=None,
    )

    configured_max_queries = (
        evaluation_config.get("max_queries")
    )
    max_queries = (
        max_queries_override
        if max_queries_override is not None
        else configured_max_queries
    )

    if max_queries is not None:
        max_queries = _positive_int(
            max_queries,
            name="max_queries",
        )

    selected_cases = select_enabled_cases(
        golden_rows,
        max_queries=max_queries,
    )

    scenarios = build_scenario_matrix(
        config,
        corpus_size=len(runtime.documents),
    )

    max_candidate_k = max(
        int(scenario["candidate_k"])
        for scenario in scenarios
    )

    determinism_config = _require_mapping(
        evaluation_config.get(
            "determinism"
        ),
        name="evaluation.determinism",
    )
    repeated_runs = _positive_int(
        determinism_config[
            "repeated_runs"
        ],
        name="repeated_runs",
    )
    mismatch_repeated_runs = _positive_int(
        determinism_config[
            "mismatch_repeated_runs"
        ],
        name="mismatch_repeated_runs",
    )

    documents_by_id = {
        document.canonical_id: document
        for document in runtime.documents
    }

    query_results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for case in selected_cases:
        query_id = str(case["query_id"])
        query_text = str(case["query"]).strip()

        query_row: dict[str, Any] = {
            "query_id": query_id,
            "query": query_text,
            "group": str(
                case.get("group")
                or "ungrouped"
            ),
            "intent": case.get("intent"),
            "scenarios": [],
            "error": None,
        }

        try:
            query_vector, encode_ms = (
                encode_query_once(
                    runtime,
                    query=query_text,
                )
            )
            lexical_candidates, lexical_ms = (
                run_lexical_once(
                    runtime,
                    query=query_text,
                    top_k=max_candidate_k,
                )
            )

            query_row["shared_preparation"] = {
                "encode_ms": encode_ms,
                "lexical_ms": lexical_ms,
                "lexical_candidate_count": (
                    len(lexical_candidates)
                ),
                "max_candidate_k": (
                    max_candidate_k
                ),
            }

            for scenario in scenarios:
                scenario_id = str(
                    scenario["scenario_id"]
                )

                try:
                    result = (
                        run_scenario_with_repeats(
                            case=case,
                            query_vector=query_vector,
                            lexical_candidates=(
                                lexical_candidates
                            ),
                            file_backend=file_backend,
                            qdrant_backend=(
                                qdrant_backend
                            ),
                            documents_by_id=(
                                documents_by_id
                            ),
                            scenario=scenario,
                            scoring_params=(
                                scoring_params
                            ),
                            repeated_runs=(
                                repeated_runs
                            ),
                            mismatch_repeated_runs=(
                                mismatch_repeated_runs
                            ),
                        )
                    )
                    result["error"] = None
                    query_row["scenarios"].append(
                        result
                    )

                except Exception as exc:
                    error = {
                        "query_id": query_id,
                        "scenario_id": scenario_id,
                        "stage": "scenario",
                        "error_type": (
                            type(exc).__name__
                        ),
                        "error": repr(exc),
                    }
                    errors.append(error)
                    query_row[
                        "scenarios"
                    ].append(
                        {
                            "scenario_id": (
                                scenario_id
                            ),
                            "error": error,
                        }
                    )

        except Exception as exc:
            error = {
                "query_id": query_id,
                "scenario_id": None,
                "stage": "query_preparation",
                "error_type": (
                    type(exc).__name__
                ),
                "error": repr(exc),
            }
            errors.append(error)
            query_row["error"] = error

        query_results.append(query_row)

    expected_scenario_count = (
        len(selected_cases)
        * len(scenarios)
    )

    summary = summarize_results(
        query_results=query_results,
        errors=errors,
        expected_scenario_count=(
            expected_scenario_count
        ),
        quality_config=quality_config,
    )

    summary.update(
        {
            "enabled_query_count": (
                len(all_enabled_cases)
            ),
            "selected_query_count": (
                len(selected_cases)
            ),
            "scenario_count_per_query": (
                len(scenarios)
            ),
        }
    )

    run_ts = utc_now_ts()
    output_dir = (
        output_dir_override
        or Path(
            str(
                output_config.get(
                    "output_dir"
                )
                or DEFAULT_OUTPUT_DIR
            )
        )
    )

    safety = dict(config["safety"])

    report: dict[str, Any] = {
        "schema_version": (
            REPORT_SCHEMA_VERSION
        ),
        "report_name": (
            "qdrant_hybrid_evaluation"
        ),
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "config_path": normalize_path(
            config_path
        ),
        "config": config,
        "safety": safety,
        "inputs": {
            "manifest_path": normalize_path(
                manifest_path
            ),
            "golden_queries_path": (
                normalize_path(
                    golden_queries_path
                )
            ),
            "scoring_config_path": (
                normalize_path(
                    scoring_config_path
                )
            ),
        },
        "runtime": {
            "backend_mode": (
                runtime.backend_mode
            ),
            "ready": runtime.is_ready(),
            "build_id": (
                runtime.manifest.build_id
            ),
            "corpus_doc_count": (
                len(runtime.documents)
            ),
            "embedding_model_name": (
                runtime.current_model_name
            ),
            "embedding_shape": list(
                runtime.dense_artifacts
                .embeddings.shape
            ),
        },
        "qdrant": {
            "collection_name": (
                store.collection_name
            ),
            "transport": store.transport,
            "host": store.host,
            "rest_port": store.port,
            "grpc_port": store.grpc_port,
            "profile": dict(
                qdrant_config["profile"]
            ),
            "collection": collection_info,
            "backend_info": (
                qdrant_backend.info()
                .diagnostics
            ),
        },
        "scoring": dict(scoring_params),
        "scenario_matrix": scenarios,
        "summary": summary,
        "quality_policy": dict(
            quality_config
        ),
        "query_results": query_results,
        "errors": errors,
        "verdict": {
            "ok": bool(
                summary["quality_ok"]
            ),
            "error_count": len(errors),
            "blocking_classification_count": (
                summary[
                    "blocking_classification_count"
                ]
            ),
            "determinism_failure_count": (
                summary[
                    "determinism_failure_count"
                ]
            ),
        },
    }

    paths = save_report(
        report=report,
        output_dir=output_dir,
        run_ts=run_ts,
    )

    print(
        f"[OK] schema_version="
        f"{REPORT_SCHEMA_VERSION}"
    )
    print(
        f"[OK] build_id="
        f"{runtime.manifest.build_id}"
    )
    print(
        f"[OK] collection="
        f"{store.collection_name}"
    )
    print(
        f"[OK] transport="
        f"{store.transport}"
    )
    print(
        f"[OK] selected_queries="
        f"{len(selected_cases)}"
    )
    print(
        f"[OK] expected_scenarios="
        f"{expected_scenario_count}"
    )
    print(
        f"[OK] successful_scenarios="
        f"{summary['successful_scenario_count']}"
    )
    print(
        f"[OK] error_count="
        f"{len(errors)}"
    )
    print(
        f"[OK] quality_ok="
        f"{summary['quality_ok']}"
    )
    print(
        f"[OK] latest_json="
        f"{paths['latest_json']}"
    )
    print(
        f"[OK] latest_md="
        f"{paths['latest_md']}"
    )

    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=None,
        help=(
            "Temporarily limit enabled Golden "
            "queries for a smoke run."
        ),
    )

    return parser


def main(
    argv: list[str] | None = None,
) -> None:
    args = build_parser().parse_args(argv)

    report = run_evaluation(
        config_path=args.config_path,
        output_dir_override=args.output_dir,
        max_queries_override=args.max_queries,
    )

    if report["verdict"]["ok"] is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()