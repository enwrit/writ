"""Tier 2 ML scoring: LightGBM-predicted scores + kNN-retrieved suggestions.

This module is loaded lazily -- only when Tier 2 models are available.
The score models are pure Python (m2cgen-generated, zero deps).
Suggestion retrieval uses numpy for kNN distance calculation.
"""
from __future__ import annotations

import importlib
import json
import logging
import pickle
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


# ---------------------------------------------------------------------------
# Feature vector construction
# ---------------------------------------------------------------------------

def _build_feature_vector(
    raw_signals: dict[str, Any],
    tier1_score: int,
    tier1_dimensions: dict[str, int],
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

    # Derived features
    token_count = raw_signals.get("token_count", 0) or 1
    import math
    values["derived_log_token_count"] = math.log2(max(token_count, 1))

    tier1_dim_vals = [values.get(f"tier1_{d}", 50) for d in DIMENSION_NAMES]
    values["derived_dim_spread"] = max(tier1_dim_vals) - min(tier1_dim_vals)

    dataset_mean = 45.0  # approximate; exact value from training
    values["derived_tier1_centered"] = values.get("tier1_headline", 45) - dataset_mean

    return [values.get(name, 0.0) for name in feature_names]


# ---------------------------------------------------------------------------
# Suggestion retrieval
# ---------------------------------------------------------------------------

def _retrieve_suggestions(
    raw_signals: dict[str, Any],
    predicted_dim_scores: dict[str, int],
    k: int = 10,
    top_n: int = 3,
) -> list[str]:
    """Retrieve suggestions from similar instructions via SHAP-weighted kNN."""
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

    # Build query signal vector
    query = np.zeros(len(signal_features), dtype=np.float32)
    for i, feat in enumerate(signal_features):
        signal_name = feat[4:] if feat.startswith("sig_") else feat
        val = raw_signals.get(signal_name, raw_signals.get(feat, 0))
        if isinstance(val, (bool, int, float)):
            query[i] = float(val)

    # Normalize
    denom = sig_max - sig_min
    denom[denom == 0] = 1.0
    q_norm = (query - sig_min) / denom

    # SHAP-weighted Euclidean distance
    signals_matrix = index["signals"]
    diff = signals_matrix - q_norm
    distances = np.sqrt(np.sum(shap_w * diff ** 2, axis=1))
    neighbor_ids = np.argsort(distances)[:k]

    # Pool suggestions with scoring
    weak_dims = [
        d for d in DIMENSION_NAMES
        if predicted_dim_scores.get(d, 100) < 50
    ]

    candidates: list[tuple[str, float]] = []
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

            # Dimension alignment boost
            dim_boost = 1.0
            if weak_dims and dim_tags:
                overlap = len(set(weak_dims) & set(dim_tags))
                dim_boost = 1.0 + 0.5 * overlap

            candidates.append((text, sim * dim_boost))

    # Deduplicate by string similarity (simple: exact + prefix overlap)
    seen: list[str] = []
    unique: list[tuple[str, float]] = []
    for text, score in sorted(candidates, key=lambda x: -x[1]):
        text_lower = text.lower().strip()
        is_dup = False
        for s in seen:
            if text_lower == s or (len(text_lower) > 20 and text_lower[:20] == s[:20]):
                is_dup = True
                break
        if not is_dup:
            unique.append((text, score))
            seen.append(text_lower)

    return [text for text, _ in unique[:top_n]]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_score_ml(
    tier1_score: LintScore,
) -> LintScore:
    """Tier 2: ML-predicted scores + retrieved suggestions.

    Takes a Tier 1 LintScore (from compute_score()) and returns a new
    LintScore with ML-predicted headline/dimension scores, Tier 1 issues
    (unchanged), and kNN-retrieved suggestions.
    """
    raw_signals = tier1_score.raw_signals or {}
    tier1_dims = {d.name: d.score for d in tier1_score.dimensions}

    # Build feature vector
    features = _build_feature_vector(raw_signals, tier1_score.score, tier1_dims)

    # Predict scores
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

    # Build dimension scores with ML predictions
    dims = []
    for dim in DIMENSION_NAMES:
        score = predicted_scores.get(dim, tier1_dims.get(dim, 50))
        dims.append(DimensionScore(
            name=dim,
            label=DIMENSION_LABELS[dim],
            score=score,
            summary=_ml_dim_summary(dim, score),
        ))

    # Retrieve suggestions
    suggestions = _retrieve_suggestions(raw_signals, predicted_scores)
    if not suggestions:
        suggestions = tier1_score.suggestions

    return LintScore(
        score=headline,
        dimensions=dims,
        issues=tier1_score.issues,
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
