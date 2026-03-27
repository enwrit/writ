"""SetFit ONNX inference for semantic boolean feature detection.

Provides multi-label boolean predictions (has_verification, has_examples, etc.)
via a distilled SetFit model (all-MiniLM-L6-v2 -> ONNX INT8).

Uses pure-Python WordPiece tokenization (no torch/transformers dependency)
and 512-token chunking with max-pooling for long documents.

Graceful degradation: if onnxruntime is not installed or model files are
missing, predict_boolean_features() returns an empty dict and the caller
(ml_scorer.py) proceeds without SetFit features.
"""
from __future__ import annotations

import json
import logging
import math
import re
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)

LABELS = [
    "has_verification",
    "has_examples",
    "has_actionable_commands",
    "has_closure",
    "has_negative_constraints",
    "has_positive_directives",
    "is_developer_focused",
]

_MAX_SEQ_LENGTH = 512
_STRIDE = 384

_MODELS_DIR = Path.home() / ".writ" / "models"
_ONNX_MODEL_PATH = _MODELS_DIR / "setfit_encoder_int8.onnx"
_HEADS_DIR = _MODELS_DIR / "setfit_heads"
_VOCAB_PATH = Path(__file__).parent.parent / "models" / "tier2" / "vocab.txt"

_ort_session = None
_head_weights: list[tuple] | None = None
_vocab: dict[str, int] | None = None


# ---------------------------------------------------------------------------
# Pure-Python WordPiece tokenizer (matches HuggingFace's BertTokenizer)
# ---------------------------------------------------------------------------

def _load_vocab() -> dict[str, int]:
    """Load vocab.txt into a token->id mapping."""
    global _vocab
    if _vocab is not None:
        return _vocab
    if not _VOCAB_PATH.exists():
        return {}
    vocab: dict[str, int] = {}
    for i, line in enumerate(_VOCAB_PATH.read_text(encoding="utf-8").splitlines()):
        vocab[line.strip()] = i
    _vocab = vocab
    return vocab


def _normalize_text(text: str) -> str:
    """BERT-style text normalization: lowercase, strip accents, clean whitespace."""
    text = text.lower()
    output = []
    for char in text:
        cp = ord(char)
        if cp == 0 or cp == 0xFFFD or _is_control(char):
            continue
        if _is_whitespace(char):
            output.append(" ")
        else:
            output.append(char)
    text = "".join(output)
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text


def _is_whitespace(char: str) -> bool:
    if char in (" ", "\n", "\r", "\t"):
        return True
    return unicodedata.category(char) == "Zs"


def _is_control(char: str) -> bool:
    if char in ("\t", "\n", "\r"):
        return False
    return unicodedata.category(char).startswith("C")


def _is_punctuation(char: str) -> bool:
    cp = ord(char)
    if (33 <= cp <= 47) or (58 <= cp <= 64) or (91 <= cp <= 96) or (123 <= cp <= 126):
        return True
    return unicodedata.category(char).startswith("P")


def _basic_tokenize(text: str) -> list[str]:
    """Split on whitespace and punctuation (BERT-style)."""
    text = _normalize_text(text)
    tokens = []
    for word in text.strip().split():
        current = []
        for char in word:
            if _is_punctuation(char):
                if current:
                    tokens.append("".join(current))
                    current = []
                tokens.append(char)
            else:
                current.append(char)
        if current:
            tokens.append("".join(current))
    return tokens


def _wordpiece_tokenize(token: str, vocab: dict[str, int], max_word_len: int = 200) -> list[str]:
    """WordPiece tokenize a single word."""
    if len(token) > max_word_len:
        return ["[UNK]"]
    sub_tokens: list[str] = []
    start = 0
    while start < len(token):
        end = len(token)
        found = False
        while start < end:
            substr = token[start:end]
            if start > 0:
                substr = "##" + substr
            if substr in vocab:
                sub_tokens.append(substr)
                found = True
                break
            end -= 1
        if not found:
            sub_tokens.append("[UNK]")
            break
        start = end
    return sub_tokens


def tokenize(text: str) -> list[int]:
    """Full tokenization pipeline: normalize -> basic -> wordpiece -> ids."""
    vocab = _load_vocab()
    if not vocab:
        return []
    basic_tokens = _basic_tokenize(text)
    all_ids: list[int] = [vocab.get("[CLS]", 101)]
    for token in basic_tokens:
        for sub in _wordpiece_tokenize(token, vocab):
            tid = vocab.get(sub, vocab.get("[UNK]", 100))
            all_ids.append(tid)
    all_ids.append(vocab.get("[SEP]", 102))
    return all_ids


def tokenize_into_chunks(
    text: str,
    max_length: int = _MAX_SEQ_LENGTH,
    stride: int = _STRIDE,
) -> list[tuple[list[int], list[int]]]:
    """Tokenize text into overlapping chunks for long documents.

    Returns list of (input_ids, attention_mask) tuples, each of length max_length.
    """
    all_ids = tokenize(text)
    if not all_ids:
        return []

    cls_id = all_ids[0]
    sep_id = all_ids[-1]
    inner_ids = all_ids[1:-1]

    usable_length = max_length - 2
    chunks: list[tuple[list[int], list[int]]] = []

    if len(inner_ids) <= usable_length:
        ids = [cls_id] + inner_ids + [sep_id]
        pad_len = max_length - len(ids)
        input_ids = ids + [0] * pad_len
        attention_mask = [1] * len(ids) + [0] * pad_len
        chunks.append((input_ids, attention_mask))
    else:
        start = 0
        while start < len(inner_ids):
            end = min(start + usable_length, len(inner_ids))
            chunk_inner = inner_ids[start:end]
            ids = [cls_id] + chunk_inner + [sep_id]
            pad_len = max_length - len(ids)
            input_ids = ids + [0] * pad_len
            attention_mask = [1] * len(ids) + [0] * pad_len
            chunks.append((input_ids, attention_mask))
            if end >= len(inner_ids):
                break
            start += stride

    return chunks


# ---------------------------------------------------------------------------
# ONNX inference
# ---------------------------------------------------------------------------

def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ez = math.exp(x)
    return ez / (1.0 + ez)


def _load_onnx_session():
    """Load ONNX encoder model (lazy, cached)."""
    global _ort_session
    if _ort_session is not None:
        return _ort_session
    try:
        import onnxruntime as ort
    except ImportError:
        logger.debug("onnxruntime not installed; SetFit features unavailable")
        return None

    if not _ONNX_MODEL_PATH.exists():
        logger.debug("ONNX model not found at %s", _ONNX_MODEL_PATH)
        return None

    _ort_session = ort.InferenceSession(
        str(_ONNX_MODEL_PATH),
        providers=["CPUExecutionProvider"],
    )
    return _ort_session


def _load_head_weights() -> list[tuple] | None:
    """Load classification head weights (lazy, cached)."""
    global _head_weights
    if _head_weights is not None:
        return _head_weights

    if not _HEADS_DIR.exists():
        return None

    metadata_path = _HEADS_DIR / "metadata.json"
    if not metadata_path.exists():
        return None

    weights = []
    for label in LABELS:
        head_path = _HEADS_DIR / f"head_{label}.npz"
        if head_path.exists():
            import numpy as np
            data = np.load(str(head_path))
            weights.append((data["coef"], data["intercept"]))
        else:
            return None

    _head_weights = weights
    return weights


def _run_encoder(input_ids: list[int], attention_mask: list[int]) -> list[float] | None:
    """Run ONNX encoder on a single chunk, return embedding vector."""
    session = _load_onnx_session()
    if session is None:
        return None

    import numpy as np

    ids_arr = np.array([input_ids], dtype=np.int64)
    mask_arr = np.array([attention_mask], dtype=np.int64)
    token_type = np.zeros_like(ids_arr)

    outputs = session.run(
        None,
        {"input_ids": ids_arr, "attention_mask": mask_arr, "token_type_ids": token_type},
    )

    mask_expanded = mask_arr.astype(np.float32)[:, :, None]
    token_embeddings = outputs[0]
    summed = (token_embeddings * mask_expanded).sum(axis=1)
    counts = mask_expanded.sum(axis=1).clip(min=1e-9)
    mean_pooled = (summed / counts)[0]

    return mean_pooled.tolist()


def _apply_heads(embedding: list[float]) -> list[float]:
    """Apply classification heads to get per-label logits."""
    heads = _load_head_weights()
    if heads is None:
        return []

    import numpy as np
    emb = np.array(embedding)

    logits = []
    for coef, intercept in heads:
        logit = float(emb @ coef.T + intercept)
        logits.append(logit)
    return logits


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def predict_boolean_features(text: str) -> dict[str, float]:
    """Run SetFit ONNX model with chunking, return multi-label probabilities.

    Returns dict like {"setfit_has_verification": 0.87, ...}.
    Returns empty dict if model is unavailable (graceful degradation).
    """
    if not text or not text.strip():
        return {}

    chunks = tokenize_into_chunks(text)
    if not chunks:
        return {}

    session = _load_onnx_session()
    if session is None:
        return {}

    all_probs: list[dict[str, float]] = []
    for input_ids, attention_mask in chunks:
        embedding = _run_encoder(input_ids, attention_mask)
        if embedding is None:
            return {}
        logits = _apply_heads(embedding)
        if not logits:
            return {}
        probs = {
            f"setfit_{label}": _sigmoid(logit)
            for label, logit in zip(LABELS, logits)
        }
        all_probs.append(probs)

    if not all_probs:
        return {}

    result = {}
    for key in all_probs[0]:
        result[key] = max(p[key] for p in all_probs)

    return result
