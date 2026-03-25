"""Tier 2.5: Hybrid LightGBM scores + Qwen feedback via llama-cpp-python.

Architecture:
  1. LightGBM (Tier 2) predicts headline + 6 dimension scores (~1ms)
  2. Qwen 0.8B (GGUF) generates issues + suggestions given instruction + scores
  3. Combined into a single LintScore with tier="local-ai"

Activated via: writ lint --deep-local
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from writ.core.models import DimensionScore, LintResult, LintScore

MODEL_FILENAME = "writ-lint-0.8B-Q4_K_M.gguf"
MODEL_URL = (
    "https://huggingface.co/enwrit/writ-lint-0.8B/resolve/main/"
    + MODEL_FILENAME
)
MODEL_SIZE_MB = 530

MODELS_DIR = Path.home() / ".writ" / "models"

SYSTEM_PROMPT = (
    "You are an instruction quality evaluator. Given an AI agent instruction "
    "and its quality scores, generate specific issues (ERROR/WARNING/INFO) "
    "and actionable improvement suggestions. Focus feedback on the weakest "
    "scoring dimensions."
)

DIMENSION_NAMES = [
    "clarity", "structure", "coverage", "brevity", "examples", "verification",
]

DIMENSION_LABELS = {
    "clarity": "Clarity",
    "structure": "Structure",
    "coverage": "Coverage",
    "brevity": "Brevity",
    "examples": "Examples",
    "verification": "Verification",
}

FEEDBACK_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "string",
                        "enum": ["ERROR", "WARNING", "INFO"],
                    },
                    "message": {"type": "string"},
                },
                "required": ["level", "message"],
            },
            "maxItems": 5,
        },
        "suggestions": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 3,
        },
    },
    "required": ["issues", "suggestions"],
}

SCORE_SUMMARIES = {
    (0, 20): "Needs improvement",
    (20, 40): "Needs improvement",
    (40, 60): "Good",
    (60, 80): "Strong",
    (80, 101): "Excellent",
}


def _import_llama_cpp() -> Any:
    """Import llama_cpp with a descriptive error if missing."""
    try:
        from llama_cpp import Llama
        return Llama
    except ImportError:
        from writ.utils import console

        console.print(
            "\n[red bold]llama-cpp-python is not installed.[/red bold]\n\n"
            "[bold]--deep-local[/bold] requires llama-cpp-python for "
            "local LLM inference.\n\n"
            "[bold]Install options:[/bold]\n\n"
            "  [cyan]pip install enwrit\\[local\\][/cyan]"
            "   (recommended)\n\n"
            "  [cyan]pip install llama-cpp-python[/cyan]"
            "              (manual)\n\n"
            "[dim]Note: llama-cpp-python requires a C++ compiler "
            "(MSVC on Windows, gcc on Linux/macOS).\n"
            "For pre-built wheels (no compiler needed):[/dim]\n\n"
            "  [cyan]pip install llama-cpp-python "
            "--extra-index-url "
            "https://abetlen.github.io/llama-cpp-python/whl/cpu[/cyan]\n\n"
            "[dim]More info: "
            "https://github.com/abetlen/llama-cpp-python/releases[/dim]\n"
        )
        raise SystemExit(1) from None


def _get_model_path() -> Path:
    """Return the path to the GGUF model, downloading if necessary."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / MODEL_FILENAME

    if model_path.exists():
        return model_path

    from writ.utils import console

    console.print(
        f"\n[bold]Downloading Tier 2.5 model ({MODEL_SIZE_MB} MB)...[/bold]"
    )
    console.print(f"[dim]Source: {MODEL_URL}[/dim]")
    console.print(f"[dim]Destination: {model_path}[/dim]\n")

    try:
        import httpx

        with httpx.stream("GET", MODEL_URL, follow_redirects=True, timeout=300) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))

            from rich.progress import Progress

            with Progress() as progress:
                task = progress.add_task(
                    "Downloading...", total=total or None
                )
                tmp_path = model_path.with_suffix(".tmp")
                with open(tmp_path, "wb") as f:
                    for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)
                        progress.advance(task, len(chunk))
                tmp_path.rename(model_path)

        console.print("[green]Model downloaded successfully.[/green]\n")
        return model_path

    except Exception as exc:
        console.print(f"\n[red]Download failed:[/red] {exc}")
        console.print(
            "[dim]You can manually download the model from:[/dim]\n"
            f"  {MODEL_URL}\n"
            f"[dim]Place it at:[/dim] {model_path}\n"
        )
        raise SystemExit(1) from None


def _detect_gpu_layers() -> int:
    """Auto-detect GPU availability for llama.cpp offloading.

    Returns -1 (offload all layers) if CUDA/Metal is available, 0 otherwise.
    """
    try:
        from llama_cpp import llama_supports_gpu_offload
        if llama_supports_gpu_offload():
            return -1
    except (ImportError, AttributeError):
        pass
    return 0


@lru_cache(maxsize=1)
def _load_model(model_path: str) -> Any:
    """Load the GGUF model (cached for repeated calls in same process)."""
    import atexit

    llama_cls = _import_llama_cpp()
    n_gpu = _detect_gpu_layers()
    model = llama_cls(
        model_path=model_path,
        n_ctx=8192,
        n_threads=4,
        n_gpu_layers=n_gpu,
        verbose=False,
    )
    atexit.register(model.close)
    return model


def _score_summary(score: int) -> str:
    """Return a summary string for a dimension score."""
    for (lo, hi), summary in SCORE_SUMMARIES.items():
        if lo <= score < hi:
            return summary
    return ""


def _build_qwen_prompt(instruction_text: str, ml_score: LintScore) -> str:
    """Build user prompt with instruction + LightGBM predicted scores."""
    dims = {d.name: d.score for d in ml_score.dimensions}
    return (
        f"## Instruction\n{instruction_text}\n\n"
        f"## Quality Scores\n"
        f"Headline: {ml_score.score}/100\n"
        f"Clarity: {dims.get('clarity', 50)}/100  |  "
        f"Structure: {dims.get('structure', 50)}/100\n"
        f"Coverage: {dims.get('coverage', 50)}/100  |  "
        f"Brevity: {dims.get('brevity', 50)}/100\n"
        f"Examples: {dims.get('examples', 50)}/100  |  "
        f"Verification: {dims.get('verification', 50)}/100"
    )


def _run_qwen_feedback(
    model: Any, instruction_text: str, ml_score: LintScore,
) -> dict:
    """Run Qwen to generate feedback-only JSON (issues + suggestions)."""
    user_prompt = _build_qwen_prompt(instruction_text, ml_score)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    result = model.create_chat_completion(
        messages=messages,
        response_format={
            "type": "json_object",
            "schema": FEEDBACK_SCHEMA,
        },
        temperature=0.1,
        max_tokens=1024,
    )

    content = result["choices"][0]["message"]["content"]
    return json.loads(content)


def compute_score_local(
    instruction_text: str,
    tier1_issues: list[LintResult] | None = None,
) -> LintScore:
    """Run Tier 2.5 hybrid scoring: LightGBM scores + Qwen feedback.

    Step 1: LightGBM (Tier 2) predicts headline + 6 dimension scores
    Step 2: Qwen generates issues + suggestions using instruction + scores
    Step 3: Combined into final LintScore

    Args:
        instruction_text: The raw instruction content.
        tier1_issues: Optional Tier 1 issues to include in result.

    Returns:
        LintScore with tier="local-ai".
    """
    _import_llama_cpp()

    # Step 1: LightGBM scores (fast, ~1ms)
    try:
        from writ.core.linter import compute_score, lint
        from writ.core.ml_scorer import compute_score_ml
        from writ.core.models import InstructionConfig

        agent = InstructionConfig(name="lint-input", instructions=instruction_text)
        results = lint(agent, source_path=None)
        tier1_score = compute_score(agent, results)
        ml_score = compute_score_ml(tier1_score, instruction_text=instruction_text)
    except ImportError:
        from writ.core.linter import compute_score, lint
        from writ.core.models import InstructionConfig

        agent = InstructionConfig(name="lint-input", instructions=instruction_text)
        results = lint(agent, source_path=None)
        ml_score = compute_score(agent, results)

    # Step 2: Qwen feedback (instruction + ML scores -> issues + suggestions)
    model_path = _get_model_path()
    model = _load_model(str(model_path))
    qwen_result = _run_qwen_feedback(model, instruction_text, ml_score)

    # Step 3: Combine
    dimensions = []
    for d in ml_score.dimensions:
        dimensions.append(DimensionScore(
            name=d.name,
            label=DIMENSION_LABELS.get(d.name, d.name.title()),
            score=d.score,
            summary=_score_summary(d.score),
        ))

    issues: list[LintResult] = []
    if tier1_issues:
        issues.extend(tier1_issues)

    for item in qwen_result.get("issues", []):
        level = item.get("level", "INFO").lower()
        if level not in ("error", "warning", "info"):
            level = "info"
        issues.append(LintResult(
            level=level,
            rule="local-ai",
            message=item.get("message", ""),
        ))

    suggestions = qwen_result.get("suggestions", [])[:3]

    return LintScore(
        score=ml_score.score,
        dimensions=dimensions,
        issues=issues,
        suggestions=suggestions,
        tier="local-ai",
    )
