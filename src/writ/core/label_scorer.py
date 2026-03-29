"""Label classifier: predict boolean instruction features using TF-IDF + LightGBM.

Uses bundled m2cgen-exported LightGBM models trained on positional TF-IDF
(full/first-20%/last-20%/char-ngrams) + structural features.

Dependencies: none beyond stdlib (m2cgen scorers are pure Python).
Optional numpy speeds up the feature vector construction.

Integration: called from ml_scorer.compute_score_ml() to provide boolean
features (has_verification, has_closure, etc.) as raw_signals.
"""
from __future__ import annotations

import importlib
import json
import logging
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

LABELS_DIR = Path(__file__).parent.parent / "models" / "tier2" / "labels"

LABEL_NAMES = [
    "has_verification", "has_examples", "has_actionable_commands",
    "has_closure", "has_negative_constraints", "has_positive_directives",
    "is_developer_focused",
]

# ---------------------------------------------------------------------------
# Regex patterns for structural features (same as training pipeline)
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)", re.MULTILINE)
_CODE_BLOCK_RE = re.compile(r"^```", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*[-*+]\s", re.MULTILINE)
_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
_INLINE_CMD_RE = re.compile(r"`[a-zA-Z][\w\-]*(?:\s+[\w\-./]+)*`")

_VERIFICATION_WORDS = re.compile(
    r"\b(pytest|npm\s+test|cargo\s+test|ruff|jest|mocha|unittest|"
    r"verify|validate|check\s+that|test\s+suite|CI|run\s+the\s+tests|"
    r"ensure.*pass|assert|expect\(|\.toEqual|\.toBe)\b",
    re.IGNORECASE,
)
_CLOSURE_WORDS = re.compile(
    r"\b(done\s+when|definition\s+of\s+done|complete\s+when|"
    r"stop\s+when|finished\s+when|acceptance\s+criteria|exit\s+criteria|"
    r"task\s+is\s+complete|ready\s+when|merge\s+when|ship\s+when|"
    r"all\s+tests\s+pass|DoD)\b",
    re.IGNORECASE,
)
_NEGATIVE_WORDS = re.compile(
    r"\b(never|do\s+not|must\s+not|avoid|don'?t|forbidden|"
    r"prohibited|shall\s+not|NEVER|DO\s+NOT)\b",
)
_POSITIVE_WORDS = re.compile(
    r"\b(always|must|required|ensure\s+that|shall|MUST|ALWAYS|"
    r"every\s+\w+\s+must|required\s+to)\b",
)
_EXAMPLE_MARKERS = re.compile(
    r"\b(example|for\s+instance|e\.g\.|such\s+as|sample|demo|illustration)\b",
    re.IGNORECASE,
)
_COMMAND_PATTERN = re.compile(
    r"`(npm|pip|cargo|git|docker|make|yarn|pnpm|pytest|ruff|"
    r"python|node|go|rustc|gcc|mvn|gradle)\b[^`]*`",
)


# ---------------------------------------------------------------------------
# Lazy artifact loading
# ---------------------------------------------------------------------------

def labels_available() -> bool:
    """Check if label classifier artifacts are bundled."""
    return (
        (LABELS_DIR / "label_vocab.json").exists()
        and (LABELS_DIR / "label_thresholds.json").exists()
        and (LABELS_DIR / "label_has_verification.py").exists()
    )


@lru_cache(maxsize=1)
def _load_vocab() -> dict:
    with open(LABELS_DIR / "label_vocab.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _load_thresholds() -> list[float]:
    with open(LABELS_DIR / "label_thresholds.json", encoding="utf-8") as f:
        data = json.load(f)
    return data["thresholds"]


def _load_label_scorer(label_name: str):
    module_name = f"writ.models.tier2.labels.label_{label_name}"
    return importlib.import_module(module_name)


# ---------------------------------------------------------------------------
# Tokenization (matches sklearn TfidfVectorizer defaults)
# ---------------------------------------------------------------------------

_WORD_TOKEN_RE = re.compile(r"(?u)\b\w\w+\b")


def _word_tokenize(text: str) -> list[str]:
    """Tokenize matching sklearn's default token_pattern."""
    return _WORD_TOKEN_RE.findall(text.lower())


def _char_wb_ngrams(text: str, min_n: int = 3, max_n: int = 5) -> list[str]:
    """Character n-grams at word boundaries (matches analyzer='char_wb')."""
    ngrams = []
    for word in text.lower().split():
        padded = f" {word} "
        for n in range(min_n, max_n + 1):
            for i in range(len(padded) - n + 1):
                ngrams.append(padded[i:i + n])
    return ngrams


# ---------------------------------------------------------------------------
# Feature vector construction
# ---------------------------------------------------------------------------

def _compute_tfidf(tokens: list[str], term_to_idx: dict, idf_by_idx: dict) -> dict[int, float]:
    """Compute sublinear TF-IDF for matched vocabulary terms.

    Returns sparse dict: {feature_index: tfidf_value}.
    """
    tf = Counter(tokens)
    result = {}
    for term, count in tf.items():
        if term in term_to_idx:
            idx = term_to_idx[term]
            idf = idf_by_idx[idx]
            result[idx] = (1 + math.log(count)) * idf
    return result


def _extract_structural_features(text: str, struct_names: list[str]) -> list[float]:
    """Extract structural features in the same order as training."""
    n = len(text)
    lines = text.split("\n")
    non_empty_lines = [ln for ln in lines if ln.strip()]

    headings = _HEADING_RE.findall(text)
    heading_texts = [h[1] for h in headings]
    heading_count = len(headings)
    max_nesting = max((len(h[0]) for h in headings), default=0)

    code_blocks_starts = _CODE_BLOCK_RE.findall(text)
    code_block_count = len(code_blocks_starts) // 2

    bullet_count = len(_BULLET_RE.findall(text))
    numbered_count = len(_NUMBERED_RE.findall(text))
    inline_cmd_count = len(_INLINE_CMD_RE.findall(text))

    has_frontmatter = 1.0 if text.strip().startswith("---") else 0.0

    verification_hits_full = len(_VERIFICATION_WORDS.findall(text))
    verification_hits_last20 = len(_VERIFICATION_WORDS.findall(text[int(n * 0.8):]))

    closure_hits_full = len(_CLOSURE_WORDS.findall(text))
    closure_hits_last20 = len(_CLOSURE_WORDS.findall(text[int(n * 0.8):]))

    negative_hits = len(_NEGATIVE_WORDS.findall(text))
    positive_hits = len(_POSITIVE_WORDS.findall(text))
    example_hits = len(_EXAMPLE_MARKERS.findall(text))
    command_hits = len(_COMMAND_PATTERN.findall(text))

    last_heading = heading_texts[-1].lower() if heading_texts else ""
    has_done_heading = 1.0 if any(
        re.search(r"(done|complete|criteria|finish|deliverables|output|"
                  r"acceptance|definition of done|exit|success)", h.lower())
        for h in heading_texts
    ) else 0.0

    has_testing_heading = 1.0 if any(
        re.search(r"(test|verif|QA|quality|check|validat)", h.lower())
        for h in heading_texts
    ) else 0.0

    if n < 1000:
        doc_length_bucket = 0
    elif n < 3000:
        doc_length_bucket = 1
    elif n < 8000:
        doc_length_bucket = 2
    elif n < 20000:
        doc_length_bucket = 3
    else:
        doc_length_bucket = 4

    words = text.split()
    word_count = len(words)
    unique_words = len(set(w.lower() for w in words))
    lexical_diversity = unique_words / max(word_count, 1)

    table_count = text.count("|---") + text.count("| ---")

    values = {
        "char_count": float(n),
        "line_count": float(len(lines)),
        "non_empty_line_count": float(len(non_empty_lines)),
        "word_count": float(word_count),
        "heading_count": float(heading_count),
        "max_nesting_depth": float(max_nesting),
        "code_block_count": float(code_block_count),
        "bullet_count": float(bullet_count),
        "numbered_count": float(numbered_count),
        "inline_cmd_count": float(inline_cmd_count),
        "has_frontmatter": has_frontmatter,
        "verification_hits_full": float(verification_hits_full),
        "verification_hits_last20": float(verification_hits_last20),
        "closure_hits_full": float(closure_hits_full),
        "closure_hits_last20": float(closure_hits_last20),
        "negative_hits": float(negative_hits),
        "positive_hits": float(positive_hits),
        "example_hits": float(example_hits),
        "command_hits": float(command_hits),
        "has_done_heading": has_done_heading,
        "has_testing_heading": has_testing_heading,
        "doc_length_bucket": float(doc_length_bucket),
        "lexical_diversity": round(lexical_diversity, 4),
        "table_count": float(table_count),
        "last_heading_has_closure_kw": 1.0 if re.search(
            r"(done|complete|criteria|output|deliverables|exit|summary|"
            r"conclusion|wrap|final)", last_heading
        ) else 0.0,
        "last_heading_has_test_kw": 1.0 if re.search(
            r"(test|verif|check|QA|validat)", last_heading
        ) else 0.0,
    }

    return [values.get(name, 0.0) for name in struct_names]


def build_feature_vector(text: str) -> list[float]:
    """Build the full feature vector for label prediction.

    Returns a dense list of floats, length = n_total_features from vocab config.
    """
    vocab = _load_vocab()
    n_tfidf = vocab["n_tfidf_features"]
    n_total = vocab["n_total_features"]
    struct_names = vocab["structural_feature_names"]
    features_map = vocab["features"]

    # Group features by segment for efficient tokenization
    segment_terms: dict[str, dict[str, tuple[int, float]]] = {
        "full": {}, "first": {}, "last": {}, "char": {},
    }
    for idx_str, info in features_map.items():
        idx = int(idx_str)
        seg = info["segment"]
        term = info["term"]
        idf = info["idf"]
        segment_terms[seg][term] = (idx, idf)

    # Split document into positional segments
    n = len(text)
    cut1 = int(n * 0.2)
    cut2 = int(n * 0.8)
    segments = {
        "full": text,
        "first": text[:cut1],
        "last": text[cut2:],
    }

    # Compute TF-IDF for word-based segments
    tfidf_values: dict[int, float] = {}
    for seg_name in ["full", "first", "last"]:
        tokens = _word_tokenize(segments[seg_name])
        tf = Counter(tokens)
        for term, (idx, idf) in segment_terms[seg_name].items():
            if term in tf:
                tfidf_values[idx] = (1 + math.log(tf[term])) * idf

    # Compute TF-IDF for char n-gram segment
    char_ngrams = _char_wb_ngrams(text)
    char_tf = Counter(char_ngrams)
    for term, (idx, idf) in segment_terms["char"].items():
        if term in char_tf:
            tfidf_values[idx] = (1 + math.log(char_tf[term])) * idf

    # Build dense vector: TF-IDF features + structural features
    vec = [0.0] * n_total
    for idx, val in tfidf_values.items():
        if idx < n_tfidf:
            vec[idx] = val

    struct_values = _extract_structural_features(text, struct_names)
    for i, val in enumerate(struct_values):
        vec[n_tfidf + i] = val

    return vec


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def predict_labels(text: str) -> dict[str, bool]:
    """Predict boolean labels for an instruction text.

    Returns dict like {"has_verification": True, "has_closure": False, ...}.
    """
    if not labels_available():
        return {}

    try:
        features = build_feature_vector(text)
        thresholds = _load_thresholds()
        results = {}

        for j, name in enumerate(LABEL_NAMES):
            try:
                scorer = _load_label_scorer(name)
                output = scorer.score(features)
                prob = output[1] if isinstance(output, list) else output
                results[name] = prob >= thresholds[j]
            except (ImportError, AttributeError) as e:
                logger.debug("Label scorer for %s unavailable: %s", name, e)
                results[name] = False

        return results
    except Exception as e:
        logger.debug("Label prediction failed: %s", e)
        return {}


def predict_label_probabilities(text: str) -> dict[str, float]:
    """Predict label probabilities (for use as ML features).

    Returns dict like {"setfit_has_verification": 0.85, ...} with the
    setfit_ prefix for backward compatibility with existing feature pipeline.
    """
    if not labels_available():
        return {}

    try:
        features = build_feature_vector(text)
        results = {}

        for name in LABEL_NAMES:
            try:
                scorer = _load_label_scorer(name)
                output = scorer.score(features)
                prob = output[1] if isinstance(output, list) else output
                results[f"setfit_{name}"] = round(prob, 4)
            except (ImportError, AttributeError) as e:
                logger.debug("Label scorer for %s unavailable: %s", name, e)

        return results
    except Exception as e:
        logger.debug("Label probability prediction failed: %s", e)
        return {}
