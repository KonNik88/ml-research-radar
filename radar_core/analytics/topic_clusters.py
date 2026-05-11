from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import yaml
from sklearn.cluster import MiniBatchKMeans

from radar_core.retrieval.similar import (
    DEFAULT_CANONICAL_PATH,
    DEFAULT_DENSE_DIR,
    DEFAULT_FEATURES_PATH,
    DEFAULT_RETRIEVAL_MANIFEST_PATH,
    DenseBundle,
    load_dense_bundle,
    load_jsonl_by_canonical_id,
    load_latest_retrieval_manifest,
    normalize_embeddings,
    normalize_path,
)

DEFAULT_TOPIC_CLUSTERS_CONFIG_PATH = Path("configs/topic_clusters_v1.yaml")
DEFAULT_TOPIC_CLUSTERS_OUTPUT_DIR = Path("artifacts/clusters/topic")
DEFAULT_TOPIC_CLUSTERS_REPORTS_DIR = Path("artifacts/reports/clusters")

ASSIGNMENT_SCHEMA_VERSION = "topic_cluster_assignment.v1"
SUMMARY_SCHEMA_VERSION = "topic_cluster_run.v1"
LABELS_SCHEMA_VERSION = "topic_cluster_labels.v1"
LATEST_SCHEMA_VERSION = "topic_clusters_latest.v1"


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by", "can",
    "for", "from", "has", "have", "in", "into", "is", "it", "its", "new",
    "of", "on", "or", "our", "paper", "papers", "study", "system", "systems",
    "that", "the", "their", "this", "to", "toward", "towards", "using", "via",
    "we", "with", "without",
    # ML-generic words that usually make poor labels as standalone terms.
    "algorithm", "algorithms", "analysis", "application", "applications",
    "approach", "approaches", "based", "data", "deep", "framework", "learning",
    "method", "methods", "model", "modeling", "models", "network", "networks",
    "neural", "problem", "problems", "results", "task", "tasks", "training",
    # Frequent abstract filler.
    "which", "propose", "proposed", "show", "shows", "shown", "used", "use",
    "such", "these", "different", "performance", "datasets", "dataset",
    "does", "not", "only", "also", "one", "most", "state-of-the-art",
    # URL / paper boilerplate noise.
    "http", "https", "www", "com", "org", "github", "available", "availability",
    "repository", "repositories", "supplementary", "appendix", "extensive",
    "experiments", "experiment", "experimental",
}

# Terms that are useful as raw diagnostics but poor cluster labels.
# They are intentionally filtered only from label candidates, not from summary stats.
BANNED_LABEL_TERMS = {
    "computer science",
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "mathematics",
    "statistics",
    "engineering",
    "biology",
    "physics",
    "philosophy",
    "linguistics",
    "data science",
    "pattern recognition (psychology)",
    "image (mathematics)",
    "feature (linguistics)",
    "object (grammar)",
    "task (project management)",
    "set (abstract data type)",
    "process (computing)",
    "representation (politics)",
    "field (mathematics)",
    "domain (mathematical analysis)",
    "closed captioning",
    "storytelling",
    "transition (genetics)",
    "complement (music)",
    "point (geometry)",
    "taxonomy (biology)",
    "mathematical analysis",
    "programming language",
    "operating system",
}

ARXIV_CATEGORY_RE = re.compile(r"^(cs|stat|eess|math|physics|q-bio|q-fin|econ)\.[a-z]{2}$", re.IGNORECASE)


def is_arxiv_category(term: str) -> bool:
    return bool(ARXIV_CATEGORY_RE.match(term.strip()))


def is_bad_label_term(term: Any) -> bool:
    normalized = normalize_term(term)
    if not normalized:
        return True

    # Keep useful multi-word domain phrases even if they contain generic words like
    # "learning", "model", "models", "neural", "network", or "networks".
    strong_phrase_patterns = [
        "large language model",
        "large language models",
        "language model",
        "language models",
        "graph neural network",
        "graph neural networks",
        "convolutional neural network",
        "convolutional neural networks",
        "reinforcement learning",
        "machine learning",
        "neural machine translation",
        "deep reinforcement learning",
        "natural language processing",
        "automatic speech recognition",
        "knowledge graph",
        "message passing",
    ]
    if any(pattern in normalized for pattern in strong_phrase_patterns):
        if any(noise in normalized for noise in ("github", "https", "xmlns", "mathml")):
            return True
        return False

    if normalized in STOPWORDS:
        return True
    if normalized in BANNED_LABEL_TERMS:
        return True
    if is_arxiv_category(normalized):
        return True
    if len(normalized) < 4:
        return True

    # Avoid labels that are source/URL/report boilerplate or markup artifacts.
    banned_fragments = (
        "github",
        "https",
        "http",
        "available",
        "code available",
        "extensive experiment",
        "experimental result",
        "xmlns",
        "mathml",
        "mml math",
        "math mathml",
    )
    if any(fragment in normalized for fragment in banned_fragments):
        return True

    if normalized in {
        "advanced neural network applications",
        "advanced machine learning",
        "state art",
        "state-of-the-art",
        "recent years",
        "rather than",
        "simple yet effective",
    }:
        return True
    return False


def clean_ranked_terms(
    ranked_terms: Iterable[list[Any] | tuple[Any, Any]],
    *,
    top_n: int | None = None,
) -> list[list[Any]]:
    counter: Counter[str] = Counter()
    for item in ranked_terms:
        if not item:
            continue
        term = normalize_phrase_label(item[0])
        if is_bad_label_term(term):
            continue
        try:
            count = int(item[1])
        except Exception:
            count = 0
        counter[term] += count

    out: list[list[Any]] = []
    for term, count in counter.most_common(top_n):
        out.append([term, int(count)])
    return out


def label_specificity_score(term: str) -> int:
    """Conservative specificity score for human-readable topic labels.

    This is intentionally modest. We do not want an expert-system-like boost layer
    to override cluster evidence; the score only helps complete/specific phrases beat
    short parent fragments.
    """
    normalized = normalize_term(term)
    token_count = len(normalized.split())

    score = token_count * 8

    preferred_exact = {
        # Computer vision.
        "object detection": 45,
        "image classification": 40,
        "computer vision": 30,
        "semantic segmentation": 40,
        "convolutional neural networks": 45,
        "visual recognition": 30,
        # Classical ML / tabular / anomaly.
        "random forest": 45,
        "anomaly detection": 45,
        "feature selection": 40,
        "support vector machine": 40,
        "decision trees": 30,
        "decision tree": 30,
        "concept drift": 35,
        "logistic regression": 25,
        "gradient boosting": 30,
        "time series": 25,
        # NLP / MT.
        "machine translation": 45,
        "neural machine translation": 50,
        "multilingual machine translation": 50,
        "low-resource machine translation": 45,
        "low-resource languages": 35,
        "natural language processing": 35,
        "automatic speech recognition": 35,
        "named entity recognition": 30,
        # LLM / reasoning.
        "large language models": 50,
        "large language model reasoning": 55,
        "mathematical reasoning": 45,
        "question answering": 40,
        "multi-hop question answering": 40,
        "chain-of-thought reasoning": 45,
        "reasoning capabilities": 30,
        "complex reasoning": 35,
        # Graph learning.
        "graph neural networks": 55,
        "graph convolutional networks": 50,
        "node classification": 45,
        "link prediction": 45,
        "message passing": 35,
        "graph representation learning": 45,
        "knowledge graph completion": 40,
        "graph contrastive learning": 35,
        # Reinforcement learning.
        "reinforcement learning": 50,
        "deep reinforcement learning": 50,
        "multi-agent reinforcement learning": 55,
        "offline reinforcement learning": 45,
        "inverse reinforcement learning": 40,
        "policy optimization": 40,
        "policy gradient": 35,
        "sample efficiency": 35,
        "reward function": 35,
        "reward functions": 35,
        "value function": 30,
        # Evolutionary / optimization.
        "evolutionary algorithms": 45,
        "evolutionary algorithm": 40,
        "genetic algorithm": 45,
        "genetic programming": 35,
        "particle swarm optimization": 45,
        "multi-objective optimization": 40,
        "combinatorial optimization": 40,
        "traveling salesman problem": 35,
        "swarm optimization": 35,
        "local search": 30,
    }
    score += preferred_exact.get(normalized, 0)

    # Penalize weak parent/partial labels. These are still allowed only when no
    # better alternatives exist, but should not dominate top labels.
    weak_exact = {
        "machine learning": -120,
        "machine learning models": -120,
        "machine learning model": -120,
        "machine learning methods": -120,
        "machine learning algorithms": -120,
        "machine learning techniques": -120,
        "machine learning and data classification": -120,
        "learning algorithms": -100,
        "learning models": -100,
        "neural networks": -120,
        "deep neural networks": -100,
        "neural network": -100,
        "neural networks cnns": -140,
        "networks cnns": -140,
        "language models": -100,
        "language model": -80,
        "large language": -130,
        "models llms": -150,
        "language models llms": -150,
        "graph": -150,
        "graph neural": -150,
        "networks gnns": -150,
        "neural networks gnns": -150,
        "convolutional neural": -150,
        "deep neural": -140,
        "deep reinforcement": -130,
        "multi-agent reinforcement": -130,
        "natural language": -100,
        "optimization problems": -100,
        "optimization problem": -100,
        "optimization algorithms": -100,
        "mathematical optimization": -80,
        "metaheuristic optimization algorithms research": -140,
        "evolutionary algorithms and applications": -100,
        "natural language processing techniques": -80,
        "domain adaptation and few-shot learning": -80,
        "theoretical computer science": -100,
        "representation learning": -70,
        "reasoning tasks": -70,
    }
    score += weak_exact.get(normalized, 0)

    return score

def label_family(term: str) -> str:
    """Coarse family used to avoid five near-duplicate labels in one cluster."""
    normalized = normalize_term(term)

    if any(x in normalized for x in ("large language", "language model", "llm", "llms")):
        return "large_language_models"
    if any(x in normalized for x in ("machine translation", "translation nmt")):
        return "machine_translation"
    if "natural language processing" in normalized:
        return "natural_language_processing"
    if any(x in normalized for x in ("graph neural", "graph convolutional", "message passing", "node classification", "link prediction", "graph representation", "knowledge graph")):
        return "graph_learning"
    if "reinforcement learning" in normalized or normalized in {"policy optimization", "sample efficiency", "reward function", "reward functions", "value function", "policy gradient"}:
        return "reinforcement_learning"
    if any(x in normalized for x in ("object detection", "image classification", "computer vision", "semantic segmentation", "convolutional neural", "visual recognition")):
        return "computer_vision"
    if any(x in normalized for x in ("random forest", "anomaly detection", "feature selection", "support vector", "decision tree", "decision trees", "concept drift", "logistic regression", "gradient boosting")):
        return "classical_ml"
    if any(x in normalized for x in ("genetic algorithm", "evolutionary algorithm", "evolutionary algorithms", "particle swarm", "multi-objective optimization", "combinatorial optimization", "traveling salesman")):
        return "evolutionary_optimization"
    return normalized.split()[0] if normalized.split() else "unknown"


def is_partial_or_redundant_label(candidate: str, selected: list[str]) -> bool:
    """Drop parent/partial labels when stronger labels are already selected."""
    normalized = normalize_term(candidate)
    selected_norm = [normalize_term(item) for item in selected]

    hard_partial_terms = {
        "large language",
        "language models llms",
        "models llms",
        "graph",
        "graph neural",
        "neural networks",
        "deep neural networks",
        "neural networks cnns",
        "networks cnns",
        "neural networks gnns",
        "networks gnns",
        "convolutional neural",
        "deep neural",
        "deep reinforcement",
        "multi-agent reinforcement",
        "machine learning",
        "machine learning models",
        "machine learning model",
        "machine learning methods",
        "machine learning algorithms",
        "machine learning techniques",
        "machine learning and data classification",
        "learning algorithms",
        "learning models",
        "natural language",
        "optimization problems",
        "optimization problem",
        "optimization algorithms",
        "mathematical optimization",
        "metaheuristic optimization algorithms research",
        "evolutionary algorithms and applications",
        "natural language processing techniques",
        "domain adaptation and few-shot learning",
        "theoretical computer science",
        "representation learning",
        "reasoning tasks",
    }
    if normalized in hard_partial_terms:
        return True

    for existing in selected_norm:
        if normalized == existing:
            return True

        # If a candidate is a short substring of a stronger selected phrase, drop it.
        if len(normalized.split()) <= 2 and normalized in existing:
            return True

        # Common ontology-like parent labels.
        if normalized == "language models" and "large language models" in existing:
            return True
        if normalized == "neural network" and (
            "graph neural networks" in existing
            or "convolutional neural networks" in existing
            or "deep neural networks" in existing
        ):
            return True
        if normalized == "graph convolutional network" and "graph convolutional networks" in existing:
            return True
        if normalized == "graph neural network" and "graph neural networks" in existing:
            return True
        if normalized == "convolutional neural network" and "convolutional neural networks" in existing:
            return True
        if normalized == "evolutionary algorithm" and "evolutionary algorithms" in existing:
            return True

    return False

def postprocess_label_candidates(
    ranked_candidates: Iterable[tuple[str, int | float]],
    *,
    max_labels: int,
) -> list[str]:
    """Final conservative human-readable label cleaner.

    The strategy is intentionally simple:
    - use evidence, but log-scale it so generic high-count phrases do not dominate;
    - add modest specificity scoring;
    - remove partial/parent labels;
    - keep limited diversity without forcing unrelated topic families.
    """
    scored: list[tuple[str, float]] = []
    seen: set[str] = set()

    for term, raw_score in ranked_candidates:
        normalized = normalize_phrase_label(term)
        if is_bad_label_term(normalized):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)

        try:
            raw_value = float(raw_score)
        except Exception:
            raw_value = 0.0

        score = math.log1p(max(raw_value, 0.0)) * 30.0
        score += label_specificity_score(normalized)
        scored.append((normalized, score))

    scored.sort(key=lambda item: (item[1], label_specificity_score(item[0]), len(item[0])), reverse=True)

    selected: list[str] = []
    family_counts: Counter[str] = Counter()

    # First pass: avoid duplicates from the same phrase family, but allow two labels
    # from the same family because a cluster can legitimately be e.g. MT + LLMs.
    for term, _score in scored:
        family = label_family(term)
        if family_counts[family] >= 2:
            continue
        if is_partial_or_redundant_label(term, selected):
            continue
        selected.append(term)
        family_counts[family] += 1
        if len(selected) >= max_labels:
            return selected

    # Second pass: fill remaining slots conservatively.
    for term, _score in scored:
        if term in selected:
            continue
        if is_partial_or_redundant_label(term, selected):
            continue
        selected.append(term)
        if len(selected) >= max_labels:
            break

    return selected

@dataclass(frozen=True)
class TopicClusterPaths:
    output_dir: Path
    reports_dir: Path
    run_dir: Path
    assignments_path: Path
    summary_path: Path
    label_candidates_path: Path
    latest_path: Path
    latest_report_json_path: Path
    latest_report_md_path: Path
    history_report_json_path: Path
    history_report_md_path: Path


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            f.write("\n")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Topic clusters config not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Topic clusters config must be a YAML object: {path}")
    return payload


def stable_json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_config_hash(config: dict[str, Any]) -> str:
    return hashlib.sha256(stable_json_dumps(config).encode("utf-8")).hexdigest()[:16]


def apply_cli_overrides(
    config: dict[str, Any],
    *,
    n_clusters: int | None = None,
    write_latest: bool | None = None,
) -> dict[str, Any]:
    copied = json.loads(json.dumps(config))

    if n_clusters is not None:
        copied.setdefault("method", {}).setdefault("params", {})["n_clusters"] = int(n_clusters)

    if write_latest is not None:
        copied.setdefault("outputs", {})["write_latest"] = bool(write_latest)

    return copied


def require_mapping(payload: Any, *, name: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be a mapping/object")
    return payload


def as_path(value: Any, *, name: str) -> Path:
    if not value:
        raise ValueError(f"Missing required path: {name}")
    return Path(str(value))


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def finite_float(value: float, digits: int = 6) -> float:
    if not math.isfinite(float(value)):
        raise ValueError(f"Non-finite numeric value: {value}")
    return round(float(value), digits)


def tokenize_text(text: Any) -> list[str]:
    """Tokenization for standalone term diagnostics.

    This intentionally removes very generic ML words such as "model", "learning",
    "network", etc. Such words are weak labels by themselves.
    """
    raw = str(text or "").lower()
    tokens = re.findall(r"[a-z][a-z0-9\-]{2,}", raw)
    return [tok for tok in tokens if tok not in STOPWORDS and not tok.isdigit()]


def tokenize_phrase_text(text: Any) -> list[str]:
    """Tokenization for phrase labels.

    Phrase labels need domain words that are bad standalone labels:
    "large language models", "graph neural networks", "reinforcement learning",
    "convolutional neural networks", etc. Therefore this uses a smaller stoplist.
    """
    raw = str(text or "").lower()
    tokens = re.findall(r"[a-z][a-z0-9\-]{2,}", raw)

    phrase_stopwords = {
        # Function words.
        "a", "an", "and", "are", "as", "at", "be", "been", "being", "by", "can",
        "for", "from", "has", "have", "in", "into", "is", "it", "its", "new",
        "of", "on", "or", "our", "paper", "papers", "study", "system", "systems",
        "that", "the", "their", "this", "to", "toward", "towards", "using", "via",
        "we", "with", "without",
        # Abstract/report boilerplate.
        "which", "propose", "proposed", "show", "shows", "shown", "used", "use",
        "such", "these", "different", "performance", "datasets", "dataset",
        "does", "not", "only", "also", "one", "most", "state-of-the-art",
        "available", "availability", "extensive", "experiments", "experiment",
        "experimental", "results", "result",
        # URL / markup / boilerplate noise.
        "http", "https", "www", "com", "org", "github", "repository",
        "repositories", "supplementary", "appendix", "xmlns", "mml", "mathml",
    }

    return [tok for tok in tokens if tok not in phrase_stopwords and not tok.isdigit()]


PHRASE_REWRITES = {
    "large language llms": "large language models",
    "large language llm": "large language models",
    "language llms": "large language models",
    "language llm": "large language models",
    "multimodal large language": "multimodal large language models",
    "reasoning large language": "large language model reasoning",
    "large language reasoning": "large language model reasoning",
    "graph gnns": "graph neural networks",
    "graph convolutional gcns": "graph convolutional networks",
    "graph convolutional gcn": "graph convolutional networks",
    "convolutional cnns": "convolutional neural networks",
    "convolutional cnn": "convolutional neural networks",
    "reinforcement drl": "deep reinforcement learning",
    "multi-agent reinforcement marl": "multi-agent reinforcement learning",
    "reinforcement human feedback": "reinforcement learning from human feedback",
    "human feedback rlhf": "reinforcement learning from human feedback",
    "machine translation nmt": "neural machine translation",
    "translation nmt": "neural machine translation",
    "speech recognition asr": "automatic speech recognition",
}


def normalize_phrase_label(term: Any) -> str:
    normalized = normalize_term(term)
    return PHRASE_REWRITES.get(normalized, normalized)


def top_unigrams_from_texts(texts: Iterable[Any], *, top_n: int) -> list[list[Any]]:
    counter: Counter[str] = Counter()
    for text in texts:
        counter.update(tokenize_text(text))
    return [[term, int(count)] for term, count in counter.most_common(top_n)]


def top_bigrams_from_texts(texts: Iterable[Any], *, top_n: int) -> list[list[Any]]:
    counter: Counter[str] = Counter()
    for text in texts:
        tokens = tokenize_phrase_text(text)
        for left, right in zip(tokens, tokens[1:]):
            if left != right:
                phrase = normalize_phrase_label(f"{left} {right}")
                if not is_bad_label_term(phrase):
                    counter[phrase] += 1
    return [[term, int(count)] for term, count in counter.most_common(top_n)]


def top_trigrams_from_texts(texts: Iterable[Any], *, top_n: int) -> list[list[Any]]:
    counter: Counter[str] = Counter()
    for text in texts:
        tokens = tokenize_phrase_text(text)
        for first, second, third in zip(tokens, tokens[1:], tokens[2:]):
            if len({first, second, third}) >= 2:
                phrase = normalize_phrase_label(f"{first} {second} {third}")
                if not is_bad_label_term(phrase):
                    counter[phrase] += 1
    return [[term, int(count)] for term, count in counter.most_common(top_n)]


def normalize_term(value: Any) -> str:
    return " ".join(str(value or "").lower().split()).strip()



def top_list_terms(rows: Iterable[dict[str, Any]], field: str, *, top_n: int) -> list[list[Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = row.get(field)
        if isinstance(value, list):
            for item in value:
                term = normalize_term(item)
                if term and term not in STOPWORDS:
                    counter[term] += 1
        elif value:
            term = normalize_term(value)
            if term and term not in STOPWORDS:
                counter[term] += 1
    return [[term, int(count)] for term, count in counter.most_common(top_n)]


def top_years(rows: Iterable[dict[str, Any]], *, top_n: int) -> list[list[Any]]:
    counter: Counter[int] = Counter()
    for row in rows:
        year = row.get("year")
        if year is not None:
            try:
                counter[int(year)] += 1
            except Exception:
                pass
    return [[int(year), int(count)] for year, count in counter.most_common(top_n)]


def top_source_families(rows: Iterable[dict[str, Any]], *, top_n: int) -> list[list[Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = row.get("source_families") or []
        if isinstance(value, list):
            for source in value:
                if source:
                    counter[str(source)] += 1
    return [[term, int(count)] for term, count in counter.most_common(top_n)]


def mean_or_zero(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(float(sum(values) / len(values)), 6)


def load_dense_bundle_strict(
    *,
    dense_dir: Path,
    manifest_path: Path,
) -> tuple[dict[str, Any], DenseBundle]:
    manifest = load_latest_retrieval_manifest(manifest_path)
    if not manifest:
        raise FileNotFoundError(f"Retrieval manifest is missing or empty: {manifest_path}")

    missing = [
        key for key in ("dense_embeddings_path", "dense_ids_path", "dense_meta_path")
        if not manifest.get(key)
    ]
    if missing:
        raise ValueError(
            "Retrieval manifest is missing dense path fields: "
            + ", ".join(missing)
        )

    embedding_path = Path(str(manifest["dense_embeddings_path"]))
    ids_path = Path(str(manifest["dense_ids_path"]))
    meta_path = Path(str(manifest["dense_meta_path"]))

    for path, label in [
        (embedding_path, "dense_embeddings_path"),
        (ids_path, "dense_ids_path"),
        (meta_path, "dense_meta_path"),
    ]:
        if not path.exists():
            raise FileNotFoundError(f"{label} does not exist: {path}")

    bundle = load_dense_bundle(
        dense_dir=dense_dir,
        manifest_path=manifest_path,
        embedding_path=embedding_path,
        ids_path=ids_path,
        meta_path=meta_path,
    )
    return manifest, bundle


def resolve_paths(
    *,
    config: dict[str, Any],
    cluster_build_id: str,
) -> TopicClusterPaths:
    outputs = require_mapping(config.get("outputs") or {}, name="outputs")
    output_dir = Path(str(outputs.get("output_dir") or DEFAULT_TOPIC_CLUSTERS_OUTPUT_DIR))
    reports_dir = Path(str(outputs.get("reports_dir") or DEFAULT_TOPIC_CLUSTERS_REPORTS_DIR))

    run_dir = output_dir / "runs" / cluster_build_id

    return TopicClusterPaths(
        output_dir=output_dir,
        reports_dir=reports_dir,
        run_dir=run_dir,
        assignments_path=run_dir / "assignments.jsonl",
        summary_path=run_dir / "summary.json",
        label_candidates_path=run_dir / "label_candidates.json",
        latest_path=output_dir / "latest.json",
        latest_report_json_path=reports_dir / "topic_clusters_latest.json",
        latest_report_md_path=reports_dir / "topic_clusters_latest.md",
        history_report_json_path=reports_dir / "history" / f"topic_clusters_{cluster_build_id}.json",
        history_report_md_path=reports_dir / "history" / f"topic_clusters_{cluster_build_id}.md",
    )


def build_assignment_base_row(
    *,
    canonical_id: str,
    cluster_build_id: str,
    retrieval_build_id: str,
    cluster_id: int,
    distance_to_centroid: float,
    similarity_to_centroid: float,
    dense_index: int,
    features_by_id: dict[str, dict[str, Any]],
    canonical_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    features = features_by_id.get(canonical_id) or {}
    canonical = canonical_by_id.get(canonical_id) or {}

    return {
        "schema_version": ASSIGNMENT_SCHEMA_VERSION,
        "cluster_build_id": cluster_build_id,
        "retrieval_build_id": retrieval_build_id,
        "canonical_id": canonical_id,
        "dense_index": int(dense_index),
        "cluster_id": int(cluster_id),
        "distance_to_centroid": finite_float(distance_to_centroid),
        "similarity_to_centroid": finite_float(similarity_to_centroid),
        "rank_within_cluster": None,
        "title": features.get("title") or canonical.get("title"),
        "year": features.get("year") or canonical.get("year"),
        "radar_score": safe_float(features.get("radar_score"), 0.0),
        "implementation_readiness_score": safe_float(
            features.get("implementation_readiness_score"), 0.0
        ),
        "source_confidence_score": safe_float(features.get("source_confidence_score"), 0.0),
        "citation_signal_score": safe_float(features.get("citation_signal_score"), 0.0),
        "recency_score": safe_float(features.get("recency_score"), 0.0),
        "source_families": features.get("source_families") or [],
        "has_code_artifact": bool(features.get("has_code_artifact", False)),
        "has_dataset_artifact": bool(features.get("has_dataset_artifact", False)),
        "has_model_artifact": bool(features.get("has_model_artifact", False)),
        "has_demo_artifact": bool(features.get("has_demo_artifact", False)),
        "trusted_artifact_links_count": safe_int(features.get("trusted_artifact_links_count"), 0),
        "trusted_code_links_count": safe_int(features.get("trusted_code_links_count"), 0),
        "trusted_dataset_links_count": safe_int(features.get("trusted_dataset_links_count"), 0),
        "trusted_model_links_count": safe_int(features.get("trusted_model_links_count"), 0),
        "trusted_demo_links_count": safe_int(features.get("trusted_demo_links_count"), 0),
        "github_found_repo_count": safe_int(features.get("github_found_repo_count"), 0),
        "hf_found_count": safe_int(features.get("hf_found_count"), 0),
    }


def fit_minibatch_kmeans(
    embeddings: np.ndarray,
    *,
    params: dict[str, Any],
) -> MiniBatchKMeans:
    n_clusters = int(params.get("n_clusters", 80))
    if n_clusters <= 1:
        raise ValueError("method.params.n_clusters must be > 1")
    if n_clusters >= embeddings.shape[0]:
        raise ValueError("method.params.n_clusters must be smaller than row count")

    model = MiniBatchKMeans(
        n_clusters=n_clusters,
        random_state=int(params.get("random_state", 42)),
        batch_size=int(params.get("batch_size", 4096)),
        max_iter=int(params.get("max_iter", 100)),
        n_init=int(params.get("n_init", 3)),
        reassignment_ratio=float(params.get("reassignment_ratio", 0.01)),
    )
    model.fit(embeddings)
    return model


def build_assignments(
    *,
    embeddings: np.ndarray,
    ids: list[str],
    labels: np.ndarray,
    centers: np.ndarray,
    cluster_build_id: str,
    retrieval_build_id: str,
    features_by_id: dict[str, dict[str, Any]],
    canonical_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    centers_for_rows = centers[labels]
    distances = np.linalg.norm(embeddings - centers_for_rows, axis=1)

    center_norms = np.linalg.norm(centers, axis=1)
    safe_center_norms = np.where(center_norms > 0.0, center_norms, 1.0).astype(np.float32)
    normalized_centers = centers / safe_center_norms[:, None]
    similarities = np.sum(embeddings * normalized_centers[labels], axis=1)

    rows: list[dict[str, Any]] = []
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for dense_index, (canonical_id, cluster_id, dist, sim) in enumerate(
        zip(ids, labels.tolist(), distances.tolist(), similarities.tolist())
    ):
        row = build_assignment_base_row(
            canonical_id=str(canonical_id),
            cluster_build_id=cluster_build_id,
            retrieval_build_id=retrieval_build_id,
            cluster_id=int(cluster_id),
            distance_to_centroid=float(dist),
            similarity_to_centroid=float(sim),
            dense_index=dense_index,
            features_by_id=features_by_id,
            canonical_by_id=canonical_by_id,
        )
        rows.append(row)
        grouped[int(cluster_id)].append(row)

    for cluster_id, cluster_rows in grouped.items():
        cluster_rows.sort(key=lambda item: item["distance_to_centroid"])
        for rank, row in enumerate(cluster_rows, start=1):
            row["rank_within_cluster"] = rank

    # Keep output deterministic and convenient for streaming/inspection.
    rows.sort(key=lambda item: (int(item["cluster_id"]), int(item["rank_within_cluster"])))
    return rows, grouped


def representative_papers(
    rows: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    out = []
    for row in sorted(rows, key=lambda item: item["distance_to_centroid"])[:limit]:
        out.append(
            {
                "canonical_id": row["canonical_id"],
                "title": row.get("title"),
                "year": row.get("year"),
                "distance_to_centroid": row.get("distance_to_centroid"),
                "similarity_to_centroid": row.get("similarity_to_centroid"),
                "radar_score": row.get("radar_score"),
                "implementation_readiness_score": row.get("implementation_readiness_score"),
                "source_families": row.get("source_families") or [],
                "has_code_artifact": row.get("has_code_artifact"),
                "has_dataset_artifact": row.get("has_dataset_artifact"),
                "has_model_artifact": row.get("has_model_artifact"),
                "has_demo_artifact": row.get("has_demo_artifact"),
            }
        )
    return out


def canonical_rows_for_cluster(
    cluster_rows: list[dict[str, Any]],
    canonical_by_id: dict[str, dict[str, Any]],
    *,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    ids = [row["canonical_id"] for row in sorted(cluster_rows, key=lambda item: item["rank_within_cluster"])]
    if max_rows is not None:
        ids = ids[:max_rows]
    return [canonical_by_id[cid] for cid in ids if cid in canonical_by_id]


def build_label_candidates_for_cluster(
    *,
    cluster_id: int,
    assignment_rows: list[dict[str, Any]],
    canonical_rows: list[dict[str, Any]],
    labels_config: dict[str, Any],
) -> dict[str, Any]:
    top_title_terms_n = int(labels_config.get("top_title_terms", 20))
    top_abstract_terms_n = int(labels_config.get("top_abstract_terms", 20))
    top_categories_n = int(labels_config.get("top_categories", 20))
    top_concepts_n = int(labels_config.get("top_concepts", 20))
    top_keywords_n = int(labels_config.get("top_keywords", 20))
    label_candidates_n = int(labels_config.get("label_candidates_per_cluster", 5))

    title_texts = [row.get("title") for row in canonical_rows]
    abstract_texts = [row.get("abstract") for row in canonical_rows]

    title_trigrams = top_trigrams_from_texts(title_texts, top_n=top_title_terms_n)
    title_bigrams = top_bigrams_from_texts(title_texts, top_n=top_title_terms_n)
    title_terms = top_unigrams_from_texts(title_texts, top_n=top_title_terms_n)
    abstract_trigrams = top_trigrams_from_texts(abstract_texts, top_n=top_abstract_terms_n)
    abstract_bigrams = top_bigrams_from_texts(abstract_texts, top_n=top_abstract_terms_n)
    abstract_terms = top_unigrams_from_texts(abstract_texts, top_n=top_abstract_terms_n)

    categories = top_list_terms(canonical_rows, "categories", top_n=top_categories_n)
    concepts = top_list_terms(canonical_rows, "concepts", top_n=top_concepts_n)
    keywords = top_list_terms(canonical_rows, "keywords", top_n=top_keywords_n)
    tags = top_list_terms(canonical_rows, "tags", top_n=top_keywords_n)

    clean_title_trigrams = clean_ranked_terms(title_trigrams, top_n=top_title_terms_n)
    clean_title_bigrams = clean_ranked_terms(title_bigrams, top_n=top_title_terms_n)
    clean_abstract_trigrams = clean_ranked_terms(abstract_trigrams, top_n=top_abstract_terms_n)
    clean_abstract_bigrams = clean_ranked_terms(abstract_bigrams, top_n=top_abstract_terms_n)
    clean_title_terms = clean_ranked_terms(title_terms, top_n=top_title_terms_n)
    clean_abstract_terms = clean_ranked_terms(abstract_terms, top_n=top_abstract_terms_n)
    clean_categories = clean_ranked_terms(categories, top_n=top_categories_n)
    clean_concepts = clean_ranked_terms(concepts, top_n=top_concepts_n)
    clean_keywords = clean_ranked_terms(keywords, top_n=top_keywords_n)
    clean_tags = clean_ranked_terms(tags, top_n=top_keywords_n)

    candidate_counter: Counter[str] = Counter()

    def add_ranked_terms(
        ranked: Iterable[list[Any] | tuple[Any, Any]],
        *,
        weight: float,
        min_count: int = 1,
    ) -> None:
        for term, count in ranked:
            try:
                value = int(count)
            except Exception:
                value = 0
            if value < min_count:
                continue
            normalized = normalize_phrase_label(term)
            if is_bad_label_term(normalized):
                continue
            candidate_counter[normalized] += int(round(weight * value))

    # Conservative evidence order:
    # title phrases > abstract phrases > keywords/concepts.
    # Categories are kept as diagnostics and only used as a last fallback because
    # they often contain broad taxonomy buckets rather than clean topic labels.
    add_ranked_terms(clean_title_trigrams[:20], weight=14.0, min_count=2)
    add_ranked_terms(clean_title_bigrams[:20], weight=10.0, min_count=2)
    add_ranked_terms(clean_abstract_trigrams[:20], weight=5.0, min_count=3)
    add_ranked_terms(clean_abstract_bigrams[:20], weight=3.5, min_count=3)
    add_ranked_terms(clean_keywords[:20], weight=2.0, min_count=2)
    add_ranked_terms(clean_concepts[:20], weight=1.5, min_count=2)

    # Standalone title terms are only weak fallback signals.
    add_ranked_terms(clean_title_terms[:15], weight=0.5, min_count=3)

    label_candidates = postprocess_label_candidates(
        candidate_counter.most_common(),
        max_labels=label_candidates_n,
    )

    # Last fallback: include categories/tags if phrase evidence was too weak.
    if not label_candidates:
        fallback_counter: Counter[str] = Counter()
        for ranked, weight in (
            (clean_title_trigrams, 10.0),
            (clean_title_bigrams, 8.0),
            (clean_abstract_trigrams, 4.0),
            (clean_abstract_bigrams, 3.0),
            (clean_keywords, 2.0),
            (clean_concepts, 1.5),
            (clean_categories, 0.5),
            (clean_tags, 0.5),
            (clean_title_terms, 0.5),
        ):
            for term, count in ranked:
                try:
                    fallback_counter[term] += int(round(weight * int(count)))
                except Exception:
                    continue
        label_candidates = postprocess_label_candidates(
            fallback_counter.most_common(),
            max_labels=label_candidates_n,
        )

    representative_titles = [
        str(row.get("title") or "")
        for row in sorted(assignment_rows, key=lambda item: item["distance_to_centroid"])[:5]
        if row.get("title")
    ]

    return {
        "cluster_id": int(cluster_id),
        "size": len(assignment_rows),
        "method": labels_config.get("method", "heuristic_terms_v1"),
        "use_llm_labels": bool(labels_config.get("use_llm_labels", False)),
        "label_candidates": label_candidates,
        "label_candidate_families": [[label, label_family(label)] for label in label_candidates],
        "clean_title_trigrams": clean_title_trigrams,
        "clean_title_bigrams": clean_title_bigrams,
        "clean_abstract_trigrams": clean_abstract_trigrams,
        "clean_abstract_bigrams": clean_abstract_bigrams,
        "clean_title_terms": clean_title_terms,
        "clean_abstract_terms": clean_abstract_terms,
        "clean_categories": clean_categories,
        "clean_concepts": clean_concepts,
        "clean_keywords": clean_keywords,
        "clean_tags": clean_tags,
        # Raw diagnostics are kept because they are useful for audits, even if they are noisy.
        "top_title_terms": title_terms,
        "top_title_bigrams": title_bigrams,
        "top_title_trigrams": title_trigrams,
        "top_abstract_terms": abstract_terms,
        "top_abstract_bigrams": abstract_bigrams,
        "top_abstract_trigrams": abstract_trigrams,
        "top_categories": categories,
        "top_concepts": concepts,
        "top_keywords": keywords,
        "top_tags": tags,
        "representative_titles": representative_titles,
    }

def build_cluster_summary(
    *,
    cluster_id: int,
    assignment_rows: list[dict[str, Any]],
    canonical_rows: list[dict[str, Any]],
    summary_config: dict[str, Any],
) -> dict[str, Any]:
    rep_n = int(summary_config.get("representative_papers_per_cluster", 10))
    top_years_n = int(summary_config.get("top_years_per_cluster", 10))
    top_sources_n = int(summary_config.get("top_source_families_per_cluster", 10))
    top_terms_n = int(summary_config.get("top_terms_per_cluster", 20))
    top_categories_n = int(summary_config.get("top_categories_per_cluster", 15))
    top_concepts_n = int(summary_config.get("top_concepts_per_cluster", 15))
    top_keywords_n = int(summary_config.get("top_keywords_per_cluster", 15))

    radar_scores = [safe_float(row.get("radar_score"), 0.0) for row in assignment_rows]
    impl_scores = [safe_float(row.get("implementation_readiness_score"), 0.0) for row in assignment_rows]
    source_scores = [safe_float(row.get("source_confidence_score"), 0.0) for row in assignment_rows]
    citation_scores = [safe_float(row.get("citation_signal_score"), 0.0) for row in assignment_rows]

    title_texts = [row.get("title") for row in canonical_rows]
    abstract_texts = [row.get("abstract") for row in canonical_rows]
    title_terms = top_unigrams_from_texts(title_texts, top_n=top_terms_n)
    abstract_terms = top_unigrams_from_texts(abstract_texts, top_n=top_terms_n)
    title_bigrams = top_bigrams_from_texts(title_texts, top_n=top_terms_n)
    abstract_bigrams = top_bigrams_from_texts(abstract_texts, top_n=top_terms_n)
    title_trigrams = top_trigrams_from_texts(title_texts, top_n=top_terms_n)
    abstract_trigrams = top_trigrams_from_texts(abstract_texts, top_n=top_terms_n)

    return {
        "cluster_id": int(cluster_id),
        "size": len(assignment_rows),
        "mean_radar_score": mean_or_zero(radar_scores),
        "mean_implementation_readiness_score": mean_or_zero(impl_scores),
        "mean_source_confidence_score": mean_or_zero(source_scores),
        "mean_citation_signal_score": mean_or_zero(citation_scores),
        "artifact_ready_count": int(sum(bool(row.get("has_code_artifact")) or bool(row.get("has_dataset_artifact")) or bool(row.get("has_model_artifact")) or bool(row.get("has_demo_artifact")) for row in assignment_rows)),
        "code_artifact_count": int(sum(bool(row.get("has_code_artifact")) for row in assignment_rows)),
        "dataset_artifact_count": int(sum(bool(row.get("has_dataset_artifact")) for row in assignment_rows)),
        "model_artifact_count": int(sum(bool(row.get("has_model_artifact")) for row in assignment_rows)),
        "demo_artifact_count": int(sum(bool(row.get("has_demo_artifact")) for row in assignment_rows)),
        "github_found_paper_count": int(sum(safe_int(row.get("github_found_repo_count"), 0) > 0 for row in assignment_rows)),
        "hf_found_paper_count": int(sum(safe_int(row.get("hf_found_count"), 0) > 0 for row in assignment_rows)),
        "top_years": top_years(assignment_rows, top_n=top_years_n),
        "top_source_families": top_source_families(assignment_rows, top_n=top_sources_n),
        "label_candidates": [],
        "top_title_terms": title_terms,
        "top_title_bigrams": title_bigrams,
        "top_title_trigrams": title_trigrams,
        "top_abstract_terms": abstract_terms,
        "top_abstract_bigrams": abstract_bigrams,
        "top_abstract_trigrams": abstract_trigrams,
        "top_categories": top_list_terms(canonical_rows, "categories", top_n=top_categories_n),
        "top_concepts": top_list_terms(canonical_rows, "concepts", top_n=top_concepts_n),
        "top_keywords": top_list_terms(canonical_rows, "keywords", top_n=top_keywords_n),
        "representative_papers": representative_papers(assignment_rows, limit=rep_n),
    }


def build_topic_cluster_run(
    *,
    config_path: Path = DEFAULT_TOPIC_CLUSTERS_CONFIG_PATH,
    n_clusters_override: int | None = None,
    write_latest_override: bool | None = None,
) -> dict[str, Any]:
    raw_config = load_yaml(config_path)
    config = apply_cli_overrides(
        raw_config,
        n_clusters=n_clusters_override,
        write_latest=write_latest_override,
    )
    config_hash = build_config_hash(config)
    cluster_build_id = utc_now_ts()

    inputs = require_mapping(config.get("inputs") or {}, name="inputs")
    outputs = require_mapping(config.get("outputs") or {}, name="outputs")
    method = require_mapping(config.get("method") or {}, name="method")
    params = require_mapping(method.get("params") or {}, name="method.params")
    scope = require_mapping(config.get("scope") or {}, name="scope")
    projection = require_mapping(config.get("projection") or {}, name="projection")
    summary_config = require_mapping(config.get("summary") or {}, name="summary")
    labels_config = require_mapping(config.get("labels") or {}, name="labels")

    algorithm = str(method.get("algorithm") or "").strip().lower()
    if algorithm != "minibatch_kmeans":
        raise ValueError(
            f"Unsupported topic clustering algorithm for v1: {algorithm!r}. "
            "Only 'minibatch_kmeans' is implemented."
        )

    if str(scope.get("type", "global")) != "global":
        raise ValueError("Topic clusters v1 only supports scope.type='global'")

    if bool(projection.get("enabled", False)):
        raise ValueError("Projection artifacts are intentionally disabled in topic clusters v1")

    retrieval_manifest_path = as_path(
        inputs.get("retrieval_manifest_path") or DEFAULT_RETRIEVAL_MANIFEST_PATH,
        name="inputs.retrieval_manifest_path",
    )
    dense_dir = as_path(inputs.get("dense_dir") or DEFAULT_DENSE_DIR, name="inputs.dense_dir")
    features_path = as_path(
        inputs.get("paper_features_path") or DEFAULT_FEATURES_PATH,
        name="inputs.paper_features_path",
    )
    canonical_path = as_path(
        inputs.get("canonical_path") or DEFAULT_CANONICAL_PATH,
        name="inputs.canonical_path",
    )

    paths = resolve_paths(config=config, cluster_build_id=cluster_build_id)

    manifest, bundle = load_dense_bundle_strict(
        dense_dir=dense_dir,
        manifest_path=retrieval_manifest_path,
    )
    retrieval_build_id = str(manifest.get("build_id") or "")
    if not retrieval_build_id:
        raise ValueError("Retrieval manifest has no build_id")

    embeddings = bundle.embeddings.astype(np.float32, copy=False)
    if bool((config.get("embeddings") or {}).get("normalize", True)):
        embeddings = normalize_embeddings(embeddings).astype(np.float32, copy=False)

    if len(bundle.ids) != int(embeddings.shape[0]):
        raise ValueError(
            f"Dense ids count mismatch: ids={len(bundle.ids)} embeddings_rows={embeddings.shape[0]}"
        )

    manifest_doc_count = int(manifest.get("corpus_doc_count") or 0)
    if manifest_doc_count and manifest_doc_count != int(embeddings.shape[0]):
        raise ValueError(
            f"Manifest corpus_doc_count mismatch: manifest={manifest_doc_count} "
            f"embeddings_rows={embeddings.shape[0]}"
        )

    features_by_id = load_jsonl_by_canonical_id(features_path, optional=False)
    canonical_by_id = load_jsonl_by_canonical_id(canonical_path, optional=False)

    model = fit_minibatch_kmeans(embeddings, params=params)
    labels = model.labels_.astype(np.int32, copy=False)

    assignments, grouped = build_assignments(
        embeddings=embeddings,
        ids=bundle.ids,
        labels=labels,
        centers=model.cluster_centers_.astype(np.float32, copy=False),
        cluster_build_id=cluster_build_id,
        retrieval_build_id=retrieval_build_id,
        features_by_id=features_by_id,
        canonical_by_id=canonical_by_id,
    )

    expected_cluster_count = int(params.get("n_clusters", 80))
    cluster_sizes = {cid: len(rows) for cid, rows in grouped.items()}
    empty_cluster_ids = [
        cid for cid in range(expected_cluster_count)
        if cid not in cluster_sizes
    ]

    clusters: list[dict[str, Any]] = []
    label_clusters: list[dict[str, Any]] = []

    for cluster_id in sorted(grouped.keys()):
        assignment_rows = grouped[cluster_id]
        canonical_rows = canonical_rows_for_cluster(
            assignment_rows,
            canonical_by_id,
            max_rows=None,
        )

        label_rows = canonical_rows_for_cluster(
            assignment_rows,
            canonical_by_id,
            max_rows=int(labels_config.get("max_docs_per_cluster", 1000)),
        )
        label_payload = build_label_candidates_for_cluster(
            cluster_id=cluster_id,
            assignment_rows=assignment_rows,
            canonical_rows=label_rows,
            labels_config=labels_config,
        )

        cluster_summary = build_cluster_summary(
            cluster_id=cluster_id,
            assignment_rows=assignment_rows,
            canonical_rows=canonical_rows,
            summary_config=summary_config,
        )
        cluster_summary["label_candidates"] = label_payload.get("label_candidates") or []

        clusters.append(cluster_summary)
        label_clusters.append(label_payload)

    clusters.sort(key=lambda item: item["size"], reverse=True)

    largest_cluster_size = max(cluster_sizes.values()) if cluster_sizes else 0
    smallest_cluster_size = min(cluster_sizes.values()) if cluster_sizes else 0
    total_rows = int(embeddings.shape[0])

    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "cluster_build_id": cluster_build_id,
        "retrieval_build_id": retrieval_build_id,
        "cluster_config_hash": config_hash,
        "created_at": utc_now_iso(),
        "scope": scope,
        "projection": projection,
        "inputs": {
            "config_path": normalize_path(config_path),
            "retrieval_manifest_path": normalize_path(retrieval_manifest_path),
            "dense_dir": normalize_path(dense_dir),
            "dense_embeddings_path": normalize_path(bundle.embedding_path),
            "dense_ids_path": normalize_path(bundle.ids_path),
            "dense_meta_path": normalize_path(bundle.meta_path),
            "paper_features_path": normalize_path(features_path),
            "canonical_path": normalize_path(canonical_path),
        },
        "method": {
            "algorithm": algorithm,
            "params": params,
        },
        "embedding": {
            "model_name": manifest.get("embedding_model_name"),
            "shape": [int(embeddings.shape[0]), int(embeddings.shape[1])],
            "normalized_for_clustering": bool((config.get("embeddings") or {}).get("normalize", True)),
            "text_fields": manifest.get("text_fields") or [],
        },
        "counts": {
            "input_rows_count": total_rows,
            "assigned_rows_count": len(assignments),
            "dense_ids_count": len(bundle.ids),
            "manifest_corpus_doc_count": manifest_doc_count,
            "features_rows_count": len(features_by_id),
            "canonical_rows_count": len(canonical_by_id),
            "cluster_count": len(cluster_sizes),
            "expected_cluster_count": expected_cluster_count,
            "empty_cluster_count": len(empty_cluster_ids),
        },
        "global_metrics": {
            "inertia": float(model.inertia_),
            "largest_cluster_size": int(largest_cluster_size),
            "smallest_cluster_size": int(smallest_cluster_size),
            "largest_cluster_ratio": round(largest_cluster_size / total_rows, 6) if total_rows else 0.0,
        },
        "empty_cluster_ids": empty_cluster_ids,
        "clusters": clusters,
    }

    labels_payload = {
        "schema_version": LABELS_SCHEMA_VERSION,
        "cluster_build_id": cluster_build_id,
        "retrieval_build_id": retrieval_build_id,
        "cluster_config_hash": config_hash,
        "created_at": utc_now_iso(),
        "method": labels_config.get("method", "heuristic_terms_v1"),
        "use_llm_labels": bool(labels_config.get("use_llm_labels", False)),
        "cluster_count": len(label_clusters),
        "clusters": sorted(label_clusters, key=lambda item: item["cluster_id"]),
    }

    latest = {
        "schema_version": LATEST_SCHEMA_VERSION,
        "cluster_build_id": cluster_build_id,
        "retrieval_build_id": retrieval_build_id,
        "cluster_config_hash": config_hash,
        "created_at": utc_now_iso(),
        "run_dir": normalize_path(paths.run_dir),
        "assignments_path": normalize_path(paths.assignments_path),
        "summary_path": normalize_path(paths.summary_path),
        "label_candidates_path": normalize_path(paths.label_candidates_path),
        "algorithm": algorithm,
        "algorithm_params": params,
        "embedding_model_name": manifest.get("embedding_model_name"),
        "embedding_shape": [int(embeddings.shape[0]), int(embeddings.shape[1])],
        "scope": scope,
        "projection": projection,
    }

    report = {
        "report_name": "topic_clusters",
        "generated_at_utc": utc_now_iso(),
        "cluster_build_id": cluster_build_id,
        "retrieval_build_id": retrieval_build_id,
        "cluster_config_hash": config_hash,
        "summary": summary,
        "latest": latest,
    }

    paths.run_dir.mkdir(parents=True, exist_ok=True)
    dump_jsonl(paths.assignments_path, assignments)
    dump_json(paths.summary_path, summary)
    dump_json(paths.label_candidates_path, labels_payload)

    write_latest = bool(outputs.get("write_latest", True))
    if write_latest:
        dump_json(paths.latest_path, latest)
        dump_json(paths.latest_report_json_path, report)
        dump_text(paths.latest_report_md_path, build_markdown_report(report))

    dump_json(paths.history_report_json_path, report)
    dump_text(paths.history_report_md_path, build_markdown_report(report))

    return {
        "ok": True,
        "paths": {
            "run_dir": normalize_path(paths.run_dir),
            "assignments_path": normalize_path(paths.assignments_path),
            "summary_path": normalize_path(paths.summary_path),
            "label_candidates_path": normalize_path(paths.label_candidates_path),
            "latest_path": normalize_path(paths.latest_path) if write_latest else None,
            "latest_report_json_path": normalize_path(paths.latest_report_json_path) if write_latest else None,
            "latest_report_md_path": normalize_path(paths.latest_report_md_path) if write_latest else None,
            "history_report_json_path": normalize_path(paths.history_report_json_path),
            "history_report_md_path": normalize_path(paths.history_report_md_path),
        },
        "summary": summary,
        "latest": latest,
        "write_latest": write_latest,
    }


def build_markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    counts = summary["counts"]
    metrics = summary["global_metrics"]
    method = summary["method"]
    embedding = summary["embedding"]

    lines: list[str] = []
    lines.append("# Topic clusters report")
    lines.append("")
    lines.append(f"- cluster_build_id: `{summary['cluster_build_id']}`")
    lines.append(f"- retrieval_build_id: `{summary['retrieval_build_id']}`")
    lines.append(f"- cluster_config_hash: `{summary['cluster_config_hash']}`")
    lines.append(f"- algorithm: `{method['algorithm']}`")
    lines.append(f"- params: `{method['params']}`")
    lines.append(f"- embedding_model: `{embedding.get('model_name')}`")
    lines.append(f"- embedding_shape: `{embedding.get('shape')}`")
    lines.append("")
    lines.append("## Counts")
    for key, value in counts.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## Global metrics")
    for key, value in metrics.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## Largest clusters")
    lines.append("| cluster_id | size | mean_radar | artifact_ready | top label-ish terms | representative title |")
    lines.append("|---:|---:|---:|---:|---|---|")
    for cluster in summary.get("clusters", [])[:20]:
        top_terms = [str(term) for term in (cluster.get("label_candidates") or [])[:5]]
        if not top_terms:
            for field in ("top_title_trigrams", "top_title_bigrams", "top_abstract_trigrams", "top_abstract_bigrams", "top_keywords", "top_concepts", "top_title_terms"):
                for term, _count in cluster.get(field) or []:
                    if is_bad_label_term(term):
                        continue
                    if term not in top_terms:
                        top_terms.append(str(term))
                    if len(top_terms) >= 5:
                        break
                if len(top_terms) >= 5:
                    break
        reps = cluster.get("representative_papers") or []
        rep_title = (reps[0].get("title") if reps else "") or ""
        rep_title = str(rep_title).replace("|", "\\|")[:120]
        lines.append(
            f"| {cluster['cluster_id']} | {cluster['size']} | "
            f"{cluster.get('mean_radar_score')} | {cluster.get('artifact_ready_count')} | "
            f"{', '.join(top_terms).replace('|', '/')} | {rep_title} |"
        )
    lines.append("")
    return "\n".join(lines)
