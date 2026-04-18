from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from radar_core.retrieval.similarity import DEFAULT_CANONICAL_PATH, load_canonical_map


DEFAULT_CLUSTER_LATEST = Path("artifacts/clusters/abstract/latest.json")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/analytics")
DEFAULT_OUTPUT_DIR = Path("artifacts/clusters/abstract")
DEFAULT_OVERRIDES_PATH = Path("configs/cluster_label_overrides.json")


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "based", "by", "for", "from", "in", "into",
    "is", "of", "on", "or", "the", "to", "using", "via", "with", "without",
    "study", "towards", "toward", "new", "learning", "models", "model", "approach",
    "methods", "analysis", "method", "problem", "problems", "system", "systems",
    "paper", "papers", "network", "networks", "task", "tasks", "data",
    "algorithm", "algorithms", "results", "applications", "application",
    "based", "deep", "neural",
}


def load_json(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: str | Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def iter_jsonl(path: str | Path):
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def normalize_term(text: str) -> str:
    return " ".join(text.lower().split()).strip()


def slugify_label(text: str) -> str:
    text = normalize_term(text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s\-_]", " ", text)
    text = re.sub(r"\s+", "_", text).strip("_")
    return text or "cluster_unlabeled"


def tokenize_title(text: str) -> list[str]:
    text = normalize_term(text)
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", text)
    return [t for t in tokens if t not in STOPWORDS]


def top_title_terms(rows: list[dict[str, Any]], top_n: int = 15) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for row in rows:
        title = str(row.get("title") or "")
        for tok in tokenize_title(title):
            counter[tok] += 1
    return counter.most_common(top_n)


def top_categories(rows: list[dict[str, Any]], top_n: int = 12) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for row in rows:
        for item in row.get("categories") or []:
            if item:
                counter[normalize_term(str(item))] += 1
        for item in row.get("tags") or []:
            if item:
                counter[normalize_term(str(item))] += 1
    return counter.most_common(top_n)


def top_years(rows: list[dict[str, Any]], top_n: int = 10) -> list[tuple[int, int]]:
    counter: Counter[int] = Counter()
    for row in rows:
        year = row.get("year")
        if year is not None:
            try:
                counter[int(year)] += 1
            except Exception:
                pass
    return counter.most_common(top_n)


def load_overrides(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}

    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError("Overrides file must be a JSON object mapping cluster_id -> override object")

    out: dict[str, dict[str, str]] = {}
    for cluster_id, payload in data.items():
        if isinstance(payload, str):
            out[str(cluster_id)] = {"label": payload, "reason": ""}
            continue

        if not isinstance(payload, dict):
            raise ValueError("Each override must be either a string or an object with label/reason")

        label = str(payload.get("label", "")).strip()
        reason = str(payload.get("reason", "")).strip()

        if not label:
            raise ValueError(f"Override for cluster {cluster_id} must contain non-empty 'label'")

        out[str(cluster_id)] = {
            "label": label,
            "reason": reason,
        }

    return out


def get_category_weight(category_counts: list[tuple[str, int]], key: str) -> int:
    key = normalize_term(key)
    for cat, count in category_counts:
        if cat == key:
            return int(count)
    return 0


def title_term_present(title_counts: list[tuple[str, int]], *terms: str) -> bool:
    title_keys = {term for term, _ in title_counts}
    return any(t in title_keys for t in terms)


def infer_auto_label(
    category_counts: list[tuple[str, int]],
    title_counts: list[tuple[str, int]],
) -> tuple[str, str, str]:
    """
    Returns:
      auto_label, confidence, rationale
    """

    w_cv = get_category_weight(category_counts, "cs.cv")
    w_lg = get_category_weight(category_counts, "cs.lg")
    w_statml = get_category_weight(category_counts, "stat.ml")
    w_ai = get_category_weight(category_counts, "cs.ai")
    w_ne = get_category_weight(category_counts, "cs.ne")
    w_lo = get_category_weight(category_counts, "cs.lo")
    w_cl = get_category_weight(category_counts, "cs.cl")
    w_ir = get_category_weight(category_counts, "cs.ir")
    w_mm = get_category_weight(category_counts, "cs.mm")
    w_hc = get_category_weight(category_counts, "cs.hc")
    w_si = get_category_weight(category_counts, "cs.si")
    w_mathoc = get_category_weight(category_counts, "math.oc")
    w_cc = get_category_weight(category_counts, "cs.cc")
    w_ds = get_category_weight(category_counts, "cs.ds")
    w_gt = get_category_weight(category_counts, "cs.gt")

    has_object = title_term_present(title_counts, "object", "detection", "segmentation", "visual", "image", "recognition")
    has_bayes = title_term_present(title_counts, "bayesian", "posterior", "variational", "gibbs", "gaussian", "probabilistic", "graphical")
    has_logic = title_term_present(title_counts, "logic", "reasoning", "semantics", "entailment", "stable", "answer", "proof")
    has_constraint = title_term_present(title_counts, "constraint", "constraints", "sat", "maxsat", "satisfaction", "propagation")
    has_graph = title_term_present(title_counts, "graph", "graphs", "community", "communities", "spectral", "block", "stochastic")
    has_opt = title_term_present(title_counts, "optimization", "evolutionary", "genetic", "swarm", "fitness", "multi-objective")
    has_kernel = title_term_present(title_counts, "kernel", "kernels", "metric", "regression", "classification", "margin", "svm")
    has_bandit = title_term_present(title_counts, "bandit", "bandits", "regret", "online", "feedback", "exploration")
    has_hci = title_term_present(title_counts, "user", "users", "interface", "interactive", "usability", "collaborative", "mobile", "design")
    has_nlp = title_term_present(title_counts, "language", "translation", "text", "speech", "parsing")
    has_cv_retrieval = title_term_present(title_counts, "video", "videos", "multimedia", "retrieval", "browsing")

    if w_cv >= 200 and has_object:
        return "computer_vision_deep_learning", "high", "dominant cs.cv + strong visual/object/image terms"

    if w_cv >= 300:
        return "computer_vision", "high", "strong cs.cv dominance"

    if (w_lo >= 80 or get_category_weight(category_counts, "logic, reasoning, and knowledge") >= 80) and has_logic:
        return "logic_and_knowledge_representation", "high", "logic-heavy categories + reasoning/semantics title terms"

    if has_constraint and (w_ai >= 100 or w_cc >= 50 or w_ds >= 50):
        return "constraint_satisfaction_and_search", "high", "constraint/sat title terms + combinatorial categories"

    if has_bayes and (
        get_category_weight(category_counts, "bayesian modeling and causal inference") >= 20
        or w_statml >= 150
        or w_ai >= 150
    ):
        if title_term_present(title_counts, "variational", "posterior", "gibbs", "gaussian"):
            return "variational_bayesian_inference", "medium", "bayesian/variational title terms + probabilistic categories"
        return "bayesian_probabilistic_graphical_models", "medium", "bayesian/probabilistic title terms"

    if has_graph and (w_si >= 80 or get_category_weight(category_counts, "physics.soc-ph") >= 50 or w_ir >= 50):
        return "graph_and_network_science", "high", "graph/community/spectral title terms + network categories"

    if (w_hc >= 80 or w_mm >= 50) and has_hci:
        return "human_computer_interaction_collaborative_systems", "high", "hci-heavy categories + user/interface/collaborative terms"

    if (w_ir >= 50 or w_mm >= 50) and has_cv_retrieval:
        return "multimedia_video_retrieval", "high", "ir/mm categories + video/retrieval title terms"

    if has_opt and (w_ne >= 80 or w_mathoc >= 50):
        return "optimization_metaheuristics", "high", "optimization/evolutionary title terms + optimization categories"

    if has_bandit and (w_lg >= 100 or w_statml >= 100 or w_gt >= 50):
        return "bandits_and_online_learning", "high", "bandit/regret/online title terms"

    if has_kernel and (w_lg >= 150 or w_statml >= 150):
        return "kernel_methods_and_classical_machine_learning", "high", "kernel/classification/regression title terms"

    if w_cl >= 100 and has_nlp:
        return "natural_language_processing", "medium", "cs.cl + language/text title terms"

    if w_ne >= 100 and w_lg >= 100:
        return "deep_learning_and_neural_methods", "medium", "mixed cs.ne + cs.lg cluster"

    if (w_lg >= 150 or w_statml >= 150) and title_term_present(
        title_counts, "bounds", "complexity", "sample", "statistical", "estimation", "testing"
    ):
        return "statistical_learning_theory", "medium", "learning-theory style title terms + stat.ml/cs.lg"

    if category_counts:
        top_cat = category_counts[0][0]
        return f"cluster_{slugify_label(top_cat)}", "low", "fallback from dominant category"

    return "cluster_unlabeled", "low", "no strong evidence"


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Cluster label candidates")
    lines.append("")
    lines.append(f"- cluster_run_ts: `{report['cluster_run_ts']}`")
    lines.append(f"- candidate_count: `{report['candidate_count']}`")
    lines.append(f"- overrides_applied: `{report['overrides_applied']}`")
    lines.append("")

    for item in report["candidates"]:
        lines.append(f"## Cluster {item['cluster_id']}")
        lines.append(f"- auto_label: `{item['auto_label']}`")
        lines.append(f"- curated_label: `{item['curated_label']}`")
        lines.append(f"- label_source: `{item['label_source']}`")
        lines.append(f"- confidence: `{item['confidence']}`")
        lines.append(f"- rationale: `{item['rationale']}`")
        lines.append(f"- override_reason: `{item['override_reason']}`")
        lines.append(f"- cluster_size: `{item['cluster_size']}`")
        lines.append(f"- top_categories: `{item['top_categories']}`")
        lines.append(f"- top_title_terms: `{item['top_title_terms']}`")
        lines.append(f"- top_years: `{item['top_years']}`")
        lines.append("- example_titles:")
        for title in item["example_titles"]:
            lines.append(f"  - {title}")
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate semi-automatic label candidates for abstract clusters."
    )
    parser.add_argument("--cluster-latest", type=Path, default=DEFAULT_CLUSTER_LATEST)
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--top-clusters", type=int, default=15)
    parser.add_argument("--examples-per-cluster", type=int, default=5)
    parser.add_argument("--overrides-path", type=Path, default=DEFAULT_OVERRIDES_PATH)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    latest = load_json(args.cluster_latest)
    assignments_path = Path(latest["assignments_path"])
    canonical_map = load_canonical_map(args.canonical_path)
    overrides = load_overrides(args.overrides_path)

    grouped_ids: dict[int, list[str]] = defaultdict(list)
    for row in iter_jsonl(assignments_path):
        grouped_ids[int(row["cluster_id"])].append(str(row["canonical_id"]))

    cluster_sizes = {cid: len(ids) for cid, ids in grouped_ids.items()}
    top_cluster_ids = [
        cid for cid, _ in sorted(cluster_sizes.items(), key=lambda x: x[1], reverse=True)[: args.top_clusters]
    ]

    candidates: list[dict[str, Any]] = []
    overrides_applied = 0

    for cluster_id in top_cluster_ids:
        rows = [canonical_map[cid] for cid in grouped_ids[cluster_id] if cid in canonical_map]

        cat_terms = top_categories(rows, top_n=12)
        title_terms = top_title_terms(rows[: min(len(rows), 400)], top_n=15)
        years = top_years(rows, top_n=10)

        auto_label, confidence, rationale = infer_auto_label(cat_terms, title_terms)

        cluster_id_str = str(cluster_id)
        override_reason = ""

        if cluster_id_str in overrides:
            curated_label = overrides[cluster_id_str]["label"]
            override_reason = overrides[cluster_id_str].get("reason", "")
            label_source = "override"
            overrides_applied += 1
        else:
            curated_label = auto_label
            label_source = "auto"

        example_titles = [
            str(row.get("title") or "")
            for row in rows[: args.examples_per_cluster]
        ]

        candidates.append(
            {
                "cluster_id": cluster_id,
                "cluster_size": len(rows),
                "auto_label": auto_label,
                "curated_label": curated_label,
                "label_source": label_source,
                "confidence": confidence,
                "rationale": rationale,
                "override_reason": override_reason,
                "top_categories": cat_terms,
                "top_title_terms": title_terms,
                "top_years": years,
                "example_titles": example_titles,
            }
        )

    report = {
        "cluster_run_ts": latest.get("run_ts"),
        "algorithm": latest.get("algorithm"),
        "model_name": latest.get("model_name"),
        "text_builder": latest.get("text_builder"),
        "normalize_embeddings": latest.get("normalize_embeddings"),
        "candidate_count": len(candidates),
        "overrides_path": str(args.overrides_path).replace("\\", "/"),
        "overrides_applied": overrides_applied,
        "candidates": candidates,
    }

    output_json = args.output_dir / "label_candidates_latest.json"
    report_json = args.reports_dir / "cluster_label_candidates_latest.json"
    report_md = args.reports_dir / "cluster_label_candidates_latest.md"

    dump_json(output_json, report)
    dump_json(report_json, report)
    Path(report_md).parent.mkdir(parents=True, exist_ok=True)
    Path(report_md).write_text(build_markdown(report), encoding="utf-8")

    print(f"[OK] candidate_count={len(candidates)}")
    print(f"[OK] overrides_applied={overrides_applied}")
    for item in candidates[:10]:
        print(
            f"[OK] cluster={item['cluster_id']} | size={item['cluster_size']} | "
            f"auto={item['auto_label']} | curated={item['curated_label']} | "
            f"source={item['label_source']} | confidence={item['confidence']}"
        )
    print(f"[OK] output_json={output_json}")
    print(f"[OK] report_json={report_json}")
    print(f"[OK] report_md={report_md}")


if __name__ == "__main__":
    main()