"""Tier 2 ML scoring: LightGBM-predicted scores + kNN-retrieved suggestions.

This module is loaded lazily -- only when Tier 2 models are available.
The score models are pure Python (m2cgen-generated, zero deps).
Suggestion retrieval uses numpy for kNN distance calculation.

v2 hybrid: IDF-weighted relevance filtering + auto-mined template fallback.
v3 tfidf: blended structural + topical neighbor finding via TF-IDF cosine.
"""
from __future__ import annotations

import importlib
import json
import logging
import math
import pickle
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from writ.core.models import DimensionScore, LintScore

logger = logging.getLogger(__name__)

TIER2_DIR = Path(__file__).parent.parent / "models" / "tier2"

DIMENSION_NAMES = [
    "clarity", "structure", "coverage", "brevity", "examples", "verification",
]
DIMENSION_LABELS = {
    "clarity": "Clarity", "structure": "Structure", "coverage": "Coverage",
    "brevity": "Brevity", "examples": "Examples", "verification": "Verification",
}


# ---------------------------------------------------------------------------
# Lazy model loading
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_feature_config() -> dict:
    config_path = TIER2_DIR / "feature_config.json"
    with open(config_path) as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _load_shap_weights() -> dict:
    shap_path = TIER2_DIR / "shap_weights.json"
    with open(shap_path) as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _load_tfidf_config() -> dict | None:
    path = TIER2_DIR / "tfidf_config.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def _load_scorer(target: str):
    """Dynamically import a m2cgen-generated scorer module."""
    module_name = f"writ.models.tier2.scorer_{target}"
    return importlib.import_module(module_name)


@lru_cache(maxsize=1)
def _load_suggestion_index() -> dict | None:
    """Load the suggestion retrieval index (pickle)."""
    for name in ("suggestion_index.pkl", "suggestion_index.npz"):
        path = TIER2_DIR / name
        if path.exists():
            with open(path, "rb") as f:
                return pickle.load(f)
    return None


@lru_cache(maxsize=1)
def _load_suggestion_templates() -> dict[str, list[dict]] | None:
    """Load auto-mined suggestion templates (JSON) -- v1 format."""
    path = TIER2_DIR / "suggestion_templates.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


@lru_cache(maxsize=1)
def _load_suggestion_templates_v2() -> dict[str, list[dict]] | None:
    """Load label-driven suggestion templates (v2) -- replaces kNN retrieval."""
    path = TIER2_DIR / "suggestion_templates_v2.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


# ---------------------------------------------------------------------------
# Context extraction (for template slot-filling)
# ---------------------------------------------------------------------------

_BACKTICK_RE = re.compile(r"`([^`]+)`")
_HEADING_RE = re.compile(r"^#+\s+(.+)", re.MULTILINE)
_VAGUE_WORDS = {"good", "nice", "great", "proper", "appropriate", "better",
                "well", "correct", "should", "maybe", "possibly", "consider"}


def _extract_instruction_context(
    instruction_text: str,
    issues: list[dict[str, Any]] | None = None,
    raw_signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse instruction text into a slot-filling context dict."""
    headings = _HEADING_RE.findall(instruction_text)
    backtick_terms = _BACKTICK_RE.findall(instruction_text)

    # Topic: from first heading or first sentence
    topic = headings[0] if headings else instruction_text.split(".")[0][:60]

    # Detected tools: backtick-wrapped terms that look like commands/tools
    detected_tools = [
        t for t in backtick_terms
        if len(t) < 40 and not t.startswith("/") and " " not in t[:20]
    ][:5]

    # Vague terms from the instruction
    words = set(re.findall(r"\b[a-z]+\b", instruction_text.lower()))
    vague_found = sorted(words & _VAGUE_WORDS)

    # Issues from Tier 1 lint (if provided)
    weak_language_terms: list[str] = []
    if issues:
        for issue in issues:
            if isinstance(issue, dict) and issue.get("rule") == "weak-language":
                msg = issue.get("message", "")
                match = re.search(r"'([^']+)'", msg)
                if match:
                    weak_language_terms.append(match.group(1))

    return {
        "topic": topic.strip(),
        "heading_names": headings[:10],
        "detected_tools": detected_tools,
        "vague_terms": vague_found + weak_language_terms,
        "char_count": len(instruction_text),
        "code_block_count": raw_signals.get("code_fence_count", 0) if raw_signals else 0,
        "has_verify_section": bool(re.search(
            r"(?i)^#+\s*(verif|test|check|validat)", instruction_text, re.MULTILINE,
        )),
    }


# ---------------------------------------------------------------------------
# IDF-weighted relevance scoring
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Simple whitespace + punctuation tokenizer, lowercase, min length 3."""
    return set(re.findall(r"[a-z]{3,}", text.lower()))


def _idf_relevance(
    suggestion: str,
    instruction_text: str,
    idf_vocab: dict[str, float] | None = None,
) -> float:
    """IDF-weighted word overlap between suggestion and instruction.

    Returns value in [0, 1]. Higher = more relevant.
    Falls back to simple Jaccard if no IDF vocabulary is available.
    """
    sug_words = _tokenize(suggestion)
    instr_words = _tokenize(instruction_text)

    if not sug_words:
        return 0.0

    if idf_vocab:
        overlap_score = sum(idf_vocab.get(w, 1.0) for w in sug_words & instr_words)
        total_score = sum(idf_vocab.get(w, 1.0) for w in sug_words)
        return overlap_score / total_score if total_score > 0 else 0.0

    overlap = sug_words & instr_words
    return len(overlap) / len(sug_words)


# ---------------------------------------------------------------------------
# Template filling
# ---------------------------------------------------------------------------

def _fill_templates(
    predicted_dim_scores: dict[str, int],
    context: dict[str, Any],
    templates_by_dim: dict[str, list[dict]] | None = None,
    top_n: int = 5,
) -> list[str]:
    """Generate suggestions by filling templates for weak dimensions."""
    if templates_by_dim is None:
        templates_by_dim = _load_suggestion_templates()
    if not templates_by_dim:
        return []

    weak_dims = sorted(
        [(d, s) for d, s in predicted_dim_scores.items()
         if d in DIMENSION_NAMES and s < 60],
        key=lambda x: x[1],
    )

    if not weak_dims:
        weak_dims = sorted(
            [(d, s) for d, s in predicted_dim_scores.items() if d in DIMENSION_NAMES],
            key=lambda x: x[1],
        )[:2]

    slot_values = {
        "tool": context.get("detected_tools", [""])[0] if context.get("detected_tools") else "",
        "command": "",
        "file_path": "",
        "threshold": "",
        "language": "",
        "topic": context.get("topic", "this project"),
    }
    for t in context.get("detected_tools", []):
        if " " in t or len(t) > 20:
            continue
        if not slot_values["command"]:
            slot_values["command"] = t
        if not slot_values["tool"]:
            slot_values["tool"] = t

    filled: list[str] = []
    seen_prefixes: set[str] = set()

    for dim, _score in weak_dims:
        dim_templates = templates_by_dim.get(dim, [])
        for tmpl in dim_templates:
            text = tmpl.get("template", "")
            slots = tmpl.get("slots", [])

            # Fill slots with context values
            for slot in slots:
                val = slot_values.get(slot, "")
                if val:
                    text = text.replace(f"{{{slot}}}", val)
                else:
                    text = text.replace(f"{{{slot}}}", f"relevant {slot}")

            prefix = text[:40].lower()
            if prefix in seen_prefixes:
                continue
            seen_prefixes.add(prefix)
            filled.append(text)

            if len(filled) >= top_n:
                break
        if len(filled) >= top_n:
            break

    return filled


# ---------------------------------------------------------------------------
# TF-IDF computation (pure Python, no sklearn dependency)
# ---------------------------------------------------------------------------

_WORD_TOKEN_RE = re.compile(r"\b\w\w+\b")


def _word_ngrams(text: str, ngram_range: tuple[int, int] = (1, 2)) -> list[str]:
    """Generate word n-grams matching sklearn's default tokenizer."""
    words = _WORD_TOKEN_RE.findall(text.lower())
    tokens: list[str] = []
    min_n, max_n = ngram_range
    for n in range(min_n, max_n + 1):
        for i in range(len(words) - n + 1):
            tokens.append(" ".join(words[i:i + n]))
    return tokens


def _char_wb_ngrams(text: str, ngram_range: tuple[int, int] = (3, 5)) -> list[str]:
    """Generate char_wb n-grams matching sklearn's char_wb analyzer."""
    text_lower = text.lower()
    words = text_lower.split()
    tokens: list[str] = []
    min_n, max_n = ngram_range
    for word in words:
        padded = f" {word} "
        for n in range(min_n, max_n + 1):
            for i in range(len(padded) - n + 1):
                tokens.append(padded[i:i + n])
    return tokens


def _compute_tfidf_segment(
    text: str,
    word_vocab: dict[str, int],
    word_idf: list[float],
    char_vocab: dict[str, int],
    char_idf: list[float],
    n_word: int,
    word_ngram: tuple[int, int],
    char_ngram: tuple[int, int],
) -> list[float]:
    """Compute raw TF-IDF vector for one text segment."""
    word_tokens = _word_ngrams(text, word_ngram)
    word_tf: dict[str, int] = {}
    for t in word_tokens:
        word_tf[t] = word_tf.get(t, 0) + 1

    char_tokens = _char_wb_ngrams(text, char_ngram)
    char_tf: dict[str, int] = {}
    for t in char_tokens:
        char_tf[t] = char_tf.get(t, 0) + 1

    n_total = n_word + len(char_vocab)
    vec = [0.0] * n_total
    for term, count in word_tf.items():
        idx = word_vocab.get(term)
        if idx is not None:
            vec[idx] = (1.0 + math.log(count)) * word_idf[idx]
    for term, count in char_tf.items():
        idx = char_vocab.get(term)
        if idx is not None:
            vec[n_word + idx] = (1.0 + math.log(count)) * char_idf[idx]

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _compute_tfidf_features(instruction_text: str) -> dict[str, float]:
    """Compute TF-IDF feature values using the saved vocabulary and IDF weights.

    Supports both single-segment (legacy) and multi-segment (positional) configs.
    Returns a dict mapping tfidf feature names to their values.
    """
    cfg = _load_tfidf_config()
    if cfg is None:
        return {}

    chi2_mask: list[bool] = cfg["chi2_mask"]
    selected_names: list[str] = cfg["selected_feature_names"]
    word_ngram = tuple(cfg.get("word_ngram", [1, 2]))
    char_ngram = tuple(cfg.get("char_ngram", [3, 5]))

    # New multi-segment format
    if "segments" in cfg:
        positional = cfg.get("positional", "full")
        segments_cfg = cfg["segments"]
        texts: dict[str, str] = {"full": instruction_text}
        if "first" in positional:
            texts["first"] = instruction_text[:max(1, len(instruction_text) // 5)]
        if "last" in positional:
            texts["last"] = instruction_text[-max(1, len(instruction_text) // 5):]

        full_vector: list[float] = []
        for seg_name in segments_cfg:
            seg = segments_cfg[seg_name]
            seg_text = texts.get(seg_name, instruction_text)
            vec = _compute_tfidf_segment(
                seg_text,
                seg["word_vocabulary"], seg["word_idf"],
                seg["char_vocabulary"], seg["char_idf"],
                seg["n_word_features"], word_ngram, char_ngram,
            )
            full_vector.extend(vec)
    else:
        # Legacy single-segment format
        full_vector = _compute_tfidf_segment(
            instruction_text,
            cfg["word_vocabulary"], cfg["word_idf"],
            cfg["char_vocabulary"], cfg["char_idf"],
            cfg["n_word_features"], word_ngram, char_ngram,
        )

    result: dict[str, float] = {}
    j = 0
    for i, is_selected in enumerate(chi2_mask):
        if is_selected:
            if j < len(selected_names):
                result[selected_names[j]] = full_vector[i] if i < len(full_vector) else 0.0
            j += 1

    return result


# ---------------------------------------------------------------------------
# Feature vector construction
# ---------------------------------------------------------------------------

def _build_feature_vector(
    raw_signals: dict[str, Any],
    tier1_score: int,
    tier1_dimensions: dict[str, int],
    instruction_text: str = "",
) -> list[float]:
    """Build the feature vector in the same order as training."""
    config = _load_feature_config()
    feature_names = config["feature_names"]

    values: dict[str, float] = {}

    # Raw signal features (sig_*)
    for key in feature_names:
        if key.startswith("sig_"):
            signal_name = key[4:]
            val = raw_signals.get(signal_name, raw_signals.get(key, 0))
            if isinstance(val, bool):
                val = float(val)
            elif isinstance(val, (int, float)):
                val = float(val)
            else:
                val = 0.0
            values[key] = val

    # Tier 1 baseline features
    values["tier1_headline"] = float(tier1_score)
    for dim in DIMENSION_NAMES:
        values[f"tier1_{dim}"] = float(tier1_dimensions.get(dim, 50))

    # SetFit boolean features (setfit_*) -- threshold to binary to match training
    # Training data has binary 0/1 labels; inference produces continuous probabilities.
    # Without thresholding, LightGBM tree splits (at ~0) misinterpret 0.005 as "present".
    for key in feature_names:
        if key.startswith("setfit_"):
            val = raw_signals.get(key, 0.0)
            val = float(val) if isinstance(val, (int, float, bool)) else 0.0
            values[key] = 1.0 if val >= 0.5 else 0.0

    # Derived features
    token_count = raw_signals.get("token_count", 0) or 1
    values["derived_log_token_count"] = math.log2(max(token_count, 1))

    char_count = raw_signals.get("char_count", 0)
    if char_count:
        values["derived_log_char_count"] = math.log2(max(char_count, 1))
        values["derived_short_flag"] = 1.0 if char_count < 300 else 0.0

    verif_level = raw_signals.get("verification_level", 0) or 0
    if char_count:
        values["derived_verif_signal"] = verif_level * char_count / 1000.0

    setfit_verif = raw_signals.get("setfit_has_verification", 0.0)
    tier1_verif = tier1_dimensions.get("verification", 50)
    setfit_val = 1.0 if (isinstance(setfit_verif, (int, float)) and setfit_verif >= 0.5) else 0.0
    values["derived_label_score_mismatch"] = setfit_val - tier1_verif / 100.0

    tier1_dim_vals = [values.get(f"tier1_{d}", 50) for d in DIMENSION_NAMES]
    values["derived_dim_spread"] = max(tier1_dim_vals) - min(tier1_dim_vals)

    dataset_mean = 45.0
    values["derived_tier1_centered"] = values.get("tier1_headline", 45) - dataset_mean

    # New Track 1d interaction features
    info_density = values.get("sig_information_density_v2", 0.0)
    if char_count and info_density:
        values["derived_density_x_length"] = info_density * math.log2(max(char_count, 1))
    code_ratio = values.get("sig_code_to_text_ratio", 0.0)
    values["derived_code_heavy"] = 1.0 if code_ratio > 0.3 else 0.0
    prose_ratio = values.get("sig_prose_ratio", 0.0)
    dup_ratio = values.get("sig_duplicate_ratio", 0.0)
    values["derived_brevity_signal"] = prose_ratio * (1.0 - dup_ratio)

    # TF-IDF features (if model includes them)
    if instruction_text and config.get("has_tfidf", False):
        tfidf_vals = _compute_tfidf_features(instruction_text)
        values.update(tfidf_vals)

    return [values.get(name, 0.0) for name in feature_names]


# ---------------------------------------------------------------------------
# Suggestion retrieval (v1: baseline SHAP-weighted kNN)
# ---------------------------------------------------------------------------

def _knn_retrieve(
    raw_signals: dict[str, Any],
    predicted_dim_scores: dict[str, int],
    k: int = 10,
) -> list[tuple[str, float, list[str]]]:
    """Retrieve kNN candidate suggestions. Returns (text, score, dim_tags)."""
    try:
        import numpy as np
    except ImportError:
        return []

    index = _load_suggestion_index()
    if index is None:
        return []

    config = _load_feature_config()
    signal_features = config["signal_features"]
    sig_min = np.array(config["signal_min"], dtype=np.float32)
    sig_max = np.array(config["signal_max"], dtype=np.float32)

    shap_weights = _load_shap_weights()
    shap_w = np.array(
        [shap_weights.get(f, 0.01) for f in signal_features],
        dtype=np.float32,
    )

    query = np.zeros(len(signal_features), dtype=np.float32)
    for i, feat in enumerate(signal_features):
        signal_name = feat[4:] if feat.startswith("sig_") else feat
        val = raw_signals.get(signal_name, raw_signals.get(feat, 0))
        if isinstance(val, (bool, int, float)):
            query[i] = float(val)

    denom = sig_max - sig_min
    denom[denom == 0] = 1.0
    q_norm = (query - sig_min) / denom

    signals_matrix = index["signals"]
    if signals_matrix.shape[1] != len(q_norm):
        logger.debug("kNN index shape mismatch: index=%d, query=%d",
                      signals_matrix.shape[1], len(q_norm))
        return []
    diff = signals_matrix - q_norm
    distances = np.sqrt(np.sum(shap_w * diff ** 2, axis=1))
    neighbor_ids = np.argsort(distances)[:k]

    weak_dims = [d for d in DIMENSION_NAMES if predicted_dim_scores.get(d, 100) < 50]

    candidates: list[tuple[str, float, list[str]]] = []
    for nid in neighbor_ids:
        sim = 1.0 / (1.0 + float(distances[nid]))
        entry_suggestions = index["suggestions"][nid]
        for item in entry_suggestions:
            if isinstance(item, tuple) and len(item) == 2:
                text, dim_tags = item
            elif isinstance(item, str):
                text, dim_tags = item, []
            else:
                continue

            dim_boost = 1.0
            if weak_dims and dim_tags:
                overlap = len(set(weak_dims) & set(dim_tags))
                dim_boost = 1.0 + 0.5 * overlap

            candidates.append((text, sim * dim_boost, dim_tags))

    return candidates


def _is_duplicate(text: str, existing: list[str], prefix_len: int = 20) -> bool:
    """Check if text duplicates any existing suggestion by prefix overlap."""
    tl = text.lower().strip()
    for s in existing:
        sl = s.lower().strip()
        if tl == sl:
            return True
        if len(tl) > prefix_len and len(sl) > prefix_len and tl[:prefix_len] == sl[:prefix_len]:
            return True
    return False


def _retrieve_suggestions_v1(
    raw_signals: dict[str, Any],
    predicted_dim_scores: dict[str, int],
    top_n: int = 3,
) -> list[str]:
    """v1 baseline: SHAP-weighted kNN, no relevance filtering."""
    candidates = _knn_retrieve(raw_signals, predicted_dim_scores)

    seen: list[str] = []
    unique: list[tuple[str, float]] = []
    for text, score, _ in sorted(candidates, key=lambda x: -x[1]):
        if not _is_duplicate(text, seen):
            unique.append((text, score))
            seen.append(text)

    return [text for text, _ in unique[:top_n]]


# ---------------------------------------------------------------------------
# Suggestion retrieval (v2: IDF relevance filter + template fallback)
# ---------------------------------------------------------------------------

def _retrieve_suggestions_v2(
    raw_signals: dict[str, Any],
    predicted_dim_scores: dict[str, int],
    instruction_text: str,
    issues: list[dict[str, Any]] | None = None,
    top_n: int = 3,
) -> list[str]:
    """v2 hybrid: relevant kNN first, fill remaining with auto-mined templates."""
    index = _load_suggestion_index()
    idf_vocab = index.get("idf_vocabulary") if index else None

    # 1. kNN candidates
    knn_candidates = _knn_retrieve(raw_signals, predicted_dim_scores, k=10)

    # 2. Filter by IDF-weighted relevance
    relevant: list[tuple[str, float]] = []
    for text, score, _dim_tags in knn_candidates:
        rel = _idf_relevance(text, instruction_text, idf_vocab)
        if rel >= 0.02:
            relevant.append((text, score * (0.5 + rel)))

    # 3. Template candidates for weak dimensions
    context = _extract_instruction_context(instruction_text, issues, raw_signals)
    template_candidates = _fill_templates(predicted_dim_scores, context)

    # 4. Merge: prefer relevant kNN (richer), fill with templates (always relevant)
    final: list[str] = []
    for text, _ in sorted(relevant, key=lambda x: -x[1]):
        if len(final) >= top_n:
            break
        if not _is_duplicate(text, final):
            final.append(text)

    for text in template_candidates:
        if len(final) >= top_n:
            break
        if not _is_duplicate(text, final):
            final.append(text)

    return final


# ---------------------------------------------------------------------------
# Suggestion retrieval (v3: TF-IDF blended neighbor finding)
# ---------------------------------------------------------------------------

def _tfidf_query_vector(
    instruction_text: str,
    vocab: dict[str, int],
    idf: Any,
) -> Any:
    """Compute L2-normalized TF-IDF vector for a query instruction.

    Returns a dense numpy array of shape (vocab_size,).
    """
    from collections import Counter as _Counter

    import numpy as np

    tokens = list(_tokenize(instruction_text))
    tf = _Counter(tokens)
    vec = np.zeros(len(vocab), dtype=np.float32)
    for term, count in tf.items():
        if term in vocab:
            col = vocab[term]
            vec[col] = (1 + math.log(count)) * float(idf[col])
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


def _tfidf_cosine_similarities(
    query_vec: Any,
    data: Any,
    indices: Any,
    indptr: Any,
    n_docs: int,
) -> Any:
    """Compute cosine similarity between query and all stored docs (CSR format).

    Returns numpy array of shape (n_docs,) with cosine similarities in [0, 1].
    """
    import numpy as np
    sims = np.zeros(n_docs, dtype=np.float32)
    for i in range(n_docs):
        s, e = int(indptr[i]), int(indptr[i + 1])
        if s < e:
            doc_idx = indices[s:e]
            doc_val = data[s:e]
            sims[i] = np.dot(query_vec[doc_idx], doc_val)
    return np.clip(sims, 0.0, 1.0)


def _knn_retrieve_blended(
    raw_signals: dict[str, Any],
    predicted_dim_scores: dict[str, int],
    instruction_text: str,
    k: int = 10,
) -> list[tuple[str, float, list[str]]]:
    """Find neighbors by blending structural + topical distance.

    Uses TF-IDF cosine similarity if tfidf_* keys exist in the index,
    otherwise falls back to pure structural distance (same as v1/v2).
    """
    try:
        import numpy as np
    except ImportError:
        return []

    index = _load_suggestion_index()
    if index is None:
        return []

    config = _load_feature_config()
    signal_features = config["signal_features"]
    sig_min = np.array(config["signal_min"], dtype=np.float32)
    sig_max = np.array(config["signal_max"], dtype=np.float32)

    shap_weights = _load_shap_weights()
    shap_w = np.array(
        [shap_weights.get(f, 0.01) for f in signal_features],
        dtype=np.float32,
    )

    # Structural distance (same as v1/v2)
    query = np.zeros(len(signal_features), dtype=np.float32)
    for i, feat in enumerate(signal_features):
        signal_name = feat[4:] if feat.startswith("sig_") else feat
        val = raw_signals.get(signal_name, raw_signals.get(feat, 0))
        if isinstance(val, (bool, int, float)):
            query[i] = float(val)
    denom = sig_max - sig_min
    denom[denom == 0] = 1.0
    q_norm = (query - sig_min) / denom

    signals_matrix = index["signals"]
    if signals_matrix.shape[1] != len(q_norm):
        logger.debug("kNN index shape mismatch (blended): index=%d, query=%d",
                      signals_matrix.shape[1], len(q_norm))
        return []
    diff = signals_matrix - q_norm
    struct_distances = np.sqrt(np.sum(shap_w * diff ** 2, axis=1))

    # Normalize structural distances to [0, 1]
    sd_max = struct_distances.max()
    if sd_max > 0:
        struct_norm = struct_distances / sd_max
    else:
        struct_norm = struct_distances

    # TF-IDF topical distance
    tfidf_vocab = index.get("tfidf_vocab")
    tfidf_idf = index.get("tfidf_idf")
    tfidf_data = index.get("tfidf_data")
    tfidf_indices = index.get("tfidf_indices")
    tfidf_indptr = index.get("tfidf_indptr")

    alpha = index.get("tfidf_alpha", 0.4)

    tfidf_ready = all(
        x is not None for x in [tfidf_vocab, tfidf_idf, tfidf_data, tfidf_indices, tfidf_indptr]
    )
    if tfidf_ready:
        query_tfidf = _tfidf_query_vector(instruction_text, tfidf_vocab, tfidf_idf)
        cosine_sims = _tfidf_cosine_similarities(
            query_tfidf, tfidf_data, tfidf_indices, tfidf_indptr,
            len(signals_matrix),
        )
        topical_dist = 1.0 - cosine_sims
        blended = (1 - alpha) * struct_norm + alpha * topical_dist
    else:
        blended = struct_norm

    neighbor_ids = np.argsort(blended)[:k]
    weak_dims = [d for d in DIMENSION_NAMES if predicted_dim_scores.get(d, 100) < 50]

    candidates: list[tuple[str, float, list[str]]] = []
    for nid in neighbor_ids:
        sim = 1.0 / (1.0 + float(blended[nid]))
        entry_suggestions = index["suggestions"][nid]
        for item in entry_suggestions:
            if isinstance(item, tuple) and len(item) == 2:
                text, dim_tags = item
            elif isinstance(item, str):
                text, dim_tags = item, []
            else:
                continue
            dim_boost = 1.0
            if weak_dims and dim_tags:
                overlap = len(set(weak_dims) & set(dim_tags))
                dim_boost = 1.0 + 0.5 * overlap
            candidates.append((text, sim * dim_boost, dim_tags))

    return candidates


def _retrieve_suggestions_v3(
    raw_signals: dict[str, Any],
    predicted_dim_scores: dict[str, int],
    instruction_text: str,
    issues: list[dict[str, Any]] | None = None,
    top_n: int = 3,
) -> list[str]:
    """v3 tfidf: topically-aware neighbors + IDF filter + template fallback.

    Same post-processing as v2 (IDF relevance filter, template merge),
    but neighbors are found using blended structural + topical distance.
    """
    index = _load_suggestion_index()
    idf_vocab = index.get("idf_vocabulary") if index else None

    knn_candidates = _knn_retrieve_blended(
        raw_signals, predicted_dim_scores, instruction_text, k=10,
    )

    relevant: list[tuple[str, float]] = []
    for text, score, _dim_tags in knn_candidates:
        rel = _idf_relevance(text, instruction_text, idf_vocab)
        if rel >= 0.02:
            relevant.append((text, score * (0.5 + rel)))

    context = _extract_instruction_context(instruction_text, issues, raw_signals)
    template_candidates = _fill_templates(predicted_dim_scores, context)

    final: list[str] = []
    for text, _ in sorted(relevant, key=lambda x: -x[1]):
        if len(final) >= top_n:
            break
        if not _is_duplicate(text, final):
            final.append(text)

    for text in template_candidates:
        if len(final) >= top_n:
            break
        if not _is_duplicate(text, final):
            final.append(text)

    return final


# ---------------------------------------------------------------------------
# Template-based suggestions (v4) -- replaces kNN retrieval
# ---------------------------------------------------------------------------

_DIM_PRIORITY = ["verification", "examples", "coverage", "clarity", "structure", "brevity"]

_LABEL_TO_DIM_MAP: dict[str, str] = {
    "setfit_has_verification": "verification",
    "setfit_has_actionable_commands": "verification",
    "setfit_has_examples": "examples",
    "setfit_has_closure": "coverage",
    "setfit_has_negative_constraints": "coverage",
    "setfit_has_positive_directives": "clarity",
}


def _generate_suggestions_from_templates(
    raw_signals: dict[str, Any],
    predicted_dim_scores: dict[str, int],
    top_n: int = 3,
) -> list[str]:
    """Generate suggestions from label-driven templates.

    Identifies missing quality dimensions via label probabilities AND dim scores,
    then selects the most relevant templates in priority order.
    """
    templates_by_dim = _load_suggestion_templates_v2()
    if not templates_by_dim:
        return []

    # Identify weak dimensions: label probability < 0.5 AND dim score < 50
    weak_dims: list[tuple[str, int]] = []
    for dim in _DIM_PRIORITY:
        score = predicted_dim_scores.get(dim, 50)
        if score < 50:
            weak_dims.append((dim, score))

    # If nothing is weak by score, take the 2 lowest dimensions
    if not weak_dims:
        scored = [(d, predicted_dim_scores.get(d, 50)) for d in _DIM_PRIORITY]
        scored.sort(key=lambda x: x[1])
        weak_dims = scored[:2]

    suggestions: list[str] = []
    seen_prefixes: set[str] = set()

    for dim, _score in weak_dims:
        dim_templates = templates_by_dim.get(dim, [])
        for tmpl in sorted(dim_templates, key=lambda t: t.get("priority", 99)):
            text = tmpl.get("template", "")
            cond = tmpl.get("condition", {})

            # Check label condition
            label_key = cond.get("label")
            if label_key:
                threshold = cond.get("threshold", 0.5)
                prob = raw_signals.get(label_key, 0.0)
                if isinstance(prob, (int, float)) and prob >= threshold:
                    continue  # label says feature IS present, skip

            # Check dim score condition
            dim_threshold = cond.get("dim_score")
            if dim_threshold and _score >= dim_threshold:
                continue

            prefix = text[:50].lower()
            if prefix in seen_prefixes:
                continue
            seen_prefixes.add(prefix)
            suggestions.append(text)

            if len(suggestions) >= top_n:
                return suggestions

    return suggestions


# ---------------------------------------------------------------------------
# Issue gating -- suppress Tier 1 issues when ML scores are high
# ---------------------------------------------------------------------------

_RULE_TO_DIMENSION: dict[str, str] = {
    "no-verification": "verification",
    "has-commands": "verification",
    "has-examples": "examples",
    "excessive-examples": "examples",
    "has-boundaries": "coverage",
    "instruction-bloat": "brevity",
    "instructions-long": "brevity",
    "wall-of-text": "structure",
    "long-without-structure": "structure",
}

_ALWAYS_KEEP_RULES: frozenset[str] = frozenset({
    "weak-language",
    "contradiction",
    "dead-content",
    "general-knowledge",
    "expert-preamble",
    "name-format",
    "name-required",
    "missing-metadata",
    "empty-globs",
    "instructions-empty",
    "instructions-short",
    "mixed-concerns",
})

_ML_GATE_THRESHOLD = 60
_LABEL_GATE_THRESHOLD = 0.5

_RULE_TO_LABEL: dict[str, str] = {
    "no-verification": "setfit_has_verification",
    "has-commands": "setfit_has_actionable_commands",
    "has-examples": "setfit_has_examples",
}


def _gate_tier1_issues(
    issues: list,
    predicted_scores: dict[str, int],
    label_probs: dict[str, float] | None = None,
) -> list:
    """Filter Tier 1 issues against ML-predicted dimension scores.

    Dimension-mapped issues are suppressed when the corresponding ML
    score is >= 60, indicating the model already detects quality in
    that dimension. Always-keep rules pass through unconditionally.

    Label classifier veto: if the label classifier says a quality aspect
    is absent (prob < 0.5), the corresponding issue is never suppressed,
    regardless of ML dim score.
    """
    filtered = []
    for issue in issues:
        rule = issue.rule
        if rule in _ALWAYS_KEEP_RULES:
            filtered.append(issue)
            continue
        dim = _RULE_TO_DIMENSION.get(rule)
        if dim is None:
            filtered.append(issue)
            continue

        # Label classifier veto: if label says "absent", keep the issue
        if label_probs and rule in _RULE_TO_LABEL:
            label_key = _RULE_TO_LABEL[rule]
            prob = label_probs.get(label_key, 0.0)
            if isinstance(prob, (int, float)) and prob < _LABEL_GATE_THRESHOLD:
                filtered.append(issue)
                continue

        ml_score = predicted_scores.get(dim, 0)
        if ml_score < _ML_GATE_THRESHOLD:
            filtered.append(issue)
    return filtered


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_score_ml(
    tier1_score: LintScore,
    instruction_text: str = "",
) -> LintScore:
    """Tier 2: ML-predicted scores + retrieved suggestions.

    Takes a Tier 1 LintScore (from compute_score()) and returns a new
    LintScore with ML-predicted headline/dimension scores, Tier 1 issues
    (unchanged), and hybrid-retrieved suggestions (v2 if instruction_text
    is provided, v1 fallback otherwise).
    """
    raw_signals = tier1_score.raw_signals or {}
    tier1_dims = {d.name: d.score for d in tier1_score.dimensions}

    if instruction_text:
        try:
            from writ.core.label_scorer import predict_label_probabilities
            label_preds = predict_label_probabilities(instruction_text)
            if label_preds:
                raw_signals = {**raw_signals, **label_preds}
        except Exception as e:
            logger.debug("Label classifier features unavailable: %s", e)

    features = _build_feature_vector(raw_signals, tier1_score.score, tier1_dims, instruction_text)

    predicted_scores: dict[str, int] = {}
    for target in ["headline"] + DIMENSION_NAMES:
        try:
            scorer = _load_scorer(target)
            raw_pred = scorer.score(features)
            predicted_scores[target] = int(max(10, min(100, round(raw_pred))))
        except (ImportError, AttributeError, Exception) as e:
            logger.debug("ML scorer for %s unavailable: %s", target, e)
            if target == "headline":
                predicted_scores[target] = tier1_score.score
            else:
                predicted_scores[target] = tier1_dims.get(target, 50)

    headline = predicted_scores["headline"]

    dims = []
    for dim in DIMENSION_NAMES:
        score = predicted_scores.get(dim, tier1_dims.get(dim, 50))
        dims.append(DimensionScore(
            name=dim,
            label=DIMENSION_LABELS[dim],
            score=score,
            summary=_ml_dim_summary(dim, score),
        ))

    # Suggestions: label-driven templates (v4) -- replaces kNN retrieval
    suggestions = _generate_suggestions_from_templates(
        raw_signals, predicted_scores,
    )
    if not suggestions:
        suggestions = tier1_score.suggestions

    filtered_issues = _gate_tier1_issues(tier1_score.issues, predicted_scores, raw_signals)

    return LintScore(
        score=headline,
        dimensions=dims,
        issues=filtered_issues,
        suggestions=suggestions,
        raw_signals=raw_signals,
        tier="ml",
    )


def _ml_dim_summary(dim: str, score: int) -> str:
    """Generate a brief summary for ML-predicted dimension scores."""
    if score >= 80:
        return "Strong"
    if score >= 60:
        return "Good"
    if score >= 40:
        return "Moderate"
    if score >= 20:
        return "Needs improvement"
    return "Critical"
