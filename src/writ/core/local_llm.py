"""Tier 2.5: Hybrid LightGBM scores + local LLM feedback.

Architecture:
  1. LightGBM (Tier 2) predicts headline + 6 dimension scores (~1ms)
  2. Local LLM (0.8B GGUF) generates issues + suggestions
  3. Combined into a single LintScore with tier="local-ai"

LLM backends (tried in order):
  1. llama.cpp binary (auto-downloaded from GitHub releases, GPU via Vulkan)
  2. llama-cpp-python pip package (CPU fallback)

Activated via: writ lint --deep-local
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from writ.core.models import DimensionScore, LintResult, LintScore

# ---------------------------------------------------------------------------
# Model config
# ---------------------------------------------------------------------------
MODEL_FILENAME = "writ-lint-0.8B-Q4_K_M.gguf"
MODEL_URL = (
    "https://huggingface.co/enwrit/writ-lint-0.8B/resolve/main/"
    + MODEL_FILENAME
)
MODEL_SIZE_MB = 530
MODELS_DIR = Path.home() / ".writ" / "models"

# ---------------------------------------------------------------------------
# llama.cpp binary config
# ---------------------------------------------------------------------------
LLAMA_CPP_BUILD = "b8569"
LLAMA_CPP_BASE = (
    f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_CPP_BUILD}"
)
BINARIES_DIR = Path.home() / ".writ" / "bin"

_VARIANT_MAP: dict[tuple[str, str], list[tuple[str, str, int]]] = {
    # (system, machine) -> [(variant, ext, size_mb), ...] in preference order
    ("Windows", "AMD64"): [
        ("win-vulkan-x64", ".zip", 55),
        ("win-cpu-x64", ".zip", 38),
    ],
    ("Windows", "x86_64"): [
        ("win-vulkan-x64", ".zip", 55),
        ("win-cpu-x64", ".zip", 38),
    ],
    ("Darwin", "arm64"): [
        ("macos-arm64", ".tar.gz", 39),  # Metal GPU built-in
    ],
    ("Darwin", "x86_64"): [
        ("macos-x64", ".tar.gz", 98),
    ],
    ("Linux", "x86_64"): [
        ("ubuntu-vulkan-x64", ".tar.gz", 47),
        ("ubuntu-x64", ".tar.gz", 31),
    ],
}

# ---------------------------------------------------------------------------
# Prompt / schema config
# ---------------------------------------------------------------------------
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


# ===================================================================
# Binary management: download and locate llama-cli
# ===================================================================

def _get_variants() -> list[tuple[str, str, int]]:
    """Return llama.cpp binary variants for this platform, best first."""
    system = platform.system()
    machine = platform.machine()
    return _VARIANT_MAP.get((system, machine), [])


def _binary_url(variant: str, ext: str) -> str:
    return f"{LLAMA_CPP_BASE}/llama-{LLAMA_CPP_BUILD}-bin-{variant}{ext}"


def _cli_exe_name() -> str:
    return "llama-cli.exe" if sys.platform == "win32" else "llama-cli"


def _download_file(url: str, dest: Path, label: str, size_mb: int) -> bool:
    """Download a file with Rich progress bar. Returns True on success."""
    from writ.utils import console

    console.print(f"\n[bold]Downloading {label} (~{size_mb} MB)...[/bold]")
    console.print(f"[dim]{url}[/dim]\n")

    try:
        import httpx

        with httpx.stream("GET", url, follow_redirects=True, timeout=300) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))

            from rich.progress import Progress

            with Progress() as progress:
                task = progress.add_task("Downloading...", total=total or None)
                tmp = dest.with_suffix(".tmp")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)
                        progress.advance(task, len(chunk))
                tmp.rename(dest)

        console.print(f"[green]{label} downloaded.[/green]\n")
        return True

    except Exception as exc:
        console.print(f"[red]Download failed:[/red] {exc}\n")
        tmp = dest.with_suffix(".tmp")
        if tmp.exists():
            tmp.unlink()
        return False


def _extract_archive(archive: Path, dest_dir: Path) -> bool:
    """Extract zip or tar.gz into dest_dir. Returns True on success."""
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        if archive.suffix == ".zip":
            import zipfile
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(dest_dir)
        else:
            import tarfile
            with tarfile.open(archive) as tf:
                tf.extractall(dest_dir)
        return True
    except Exception:
        return False


def _get_llama_cli() -> Path | None:
    """Get path to a working llama-cli binary, downloading if needed.

    Tries variants in preference order (GPU first, then CPU).
    Returns None if no binary could be obtained.
    """
    variants = _get_variants()
    if not variants:
        return None

    exe = _cli_exe_name()

    for variant, ext, size_mb in variants:
        cli_dir = BINARIES_DIR / variant
        cli_path = cli_dir / exe

        if cli_path.exists():
            return cli_path

        archive_name = f"llama-{LLAMA_CPP_BUILD}-bin-{variant}{ext}"
        archive_path = BINARIES_DIR / archive_name

        if not archive_path.exists():
            BINARIES_DIR.mkdir(parents=True, exist_ok=True)
            url = _binary_url(variant, ext)
            backend = "Vulkan GPU" if "vulkan" in variant else (
                "Metal GPU" if "macos" in variant else "CPU"
            )
            label = f"llama.cpp ({backend})"
            if not _download_file(url, archive_path, label, size_mb):
                continue

        if not _extract_archive(archive_path, cli_dir):
            continue

        archive_path.unlink(missing_ok=True)

        if sys.platform != "win32":
            cli_path.chmod(cli_path.stat().st_mode | 0o755)

        if cli_path.exists():
            return cli_path

    return None


# ===================================================================
# Persistent server management: start once, reuse across invocations
# ===================================================================

_SERVER_PORT = 18573
_SERVER_STARTUP_TIMEOUT = 15
_PID_FILE = BINARIES_DIR / "server.pid"
_SERVER_NAME = "writ-server"


def _server_url(path: str = "") -> str:
    return f"http://127.0.0.1:{_SERVER_PORT}{path}"


def _is_server_alive() -> bool:
    """Check if an existing llama-server is healthy on our port."""
    try:
        import httpx
        r = httpx.get(_server_url("/health"), timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False


def _read_pid() -> int | None:
    """Read the server PID from the pid file, or None."""
    try:
        return int(_PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def _write_pid(pid: int) -> None:
    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(str(pid))


def _kill_server_pid(pid: int) -> None:
    """Kill a server process by PID."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True, timeout=5,
            )
        else:
            os.kill(pid, 9)
    except Exception:
        pass


def _kill_stale_server() -> None:
    """Kill a stale server process if its PID file exists but it's not alive."""
    pid = _read_pid()
    if pid is None:
        return
    _kill_server_pid(pid)
    _PID_FILE.unlink(missing_ok=True)


def _ensure_server(
    cli_path: Path, model_path: Path,
) -> bool:
    """Ensure llama-server is running. Returns True if server is healthy.

    Reuses an existing server if alive. Starts a new one if needed.
    """
    if _is_server_alive():
        return True

    _kill_stale_server()

    import shutil
    import time

    ext = ".exe" if sys.platform == "win32" else ""
    original = cli_path.parent / f"llama-server{ext}"
    branded = cli_path.parent / f"{_SERVER_NAME}{ext}"

    if not branded.exists():
        if not original.exists():
            return False
        shutil.copy2(original, branded)

    server_exe = branded

    n_threads = min(os.cpu_count() or 4, 8)
    cmd = [
        str(server_exe),
        "-m", str(model_path),
        "-ngl", "99",
        "-c", "4096",
        "-t", str(n_threads),
        "--port", str(_SERVER_PORT),
        "--log-disable",
    ]

    env = os.environ.copy()
    env["GGML_LOG_LEVEL"] = "none"

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            cwd=str(server_exe.parent),
        )
    except OSError:
        return False

    _write_pid(proc.pid)

    import httpx

    deadline = time.monotonic() + _SERVER_STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            _PID_FILE.unlink(missing_ok=True)
            return False
        try:
            r = httpx.get(_server_url("/health"), timeout=1)
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.3)

    proc.kill()
    _PID_FILE.unlink(missing_ok=True)
    return False


def stop_server() -> bool:
    """Stop the persistent llama-server. Returns True if a server was stopped."""
    pid = _read_pid()
    if pid is None:
        return False
    _kill_server_pid(pid)
    _PID_FILE.unlink(missing_ok=True)
    return True


def _infer_server(
    system_prompt: str,
    user_prompt: str,
    schema: dict,
) -> dict | None:
    """Send a /completion request to the running llama-server.

    Uses raw completion with a hand-crafted Qwen chat template to bypass
    the model's thinking phase, giving direct JSON output at full GPU speed.
    """
    prompt = (
        f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )

    body = {
        "prompt": prompt,
        "n_predict": 1024,
        "temperature": 0.1,
        "json_schema": schema,
        "stop": ["<|im_end|>", "<|end_of_text|>"],
    }

    try:
        import httpx

        r = httpx.post(
            _server_url("/completion"), json=body, timeout=60,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        content = data.get("content", "")
        return _extract_json(content)

    except Exception:
        return None


def _extract_json(text: str) -> dict | None:
    """Extract a JSON object from text that may contain surrounding noise."""
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


# ===================================================================
# llama-cpp-python fallback (CPU)
# ===================================================================

def _has_llama_cpp_python() -> bool:
    try:
        import llama_cpp  # noqa: F401
        return True
    except ImportError:
        return False


def _infer_python(
    model_path: Path,
    system_prompt: str,
    user_prompt: str,
    schema: dict,
) -> dict | None:
    """Inference via llama-cpp-python (CPU). Returns dict or None."""
    try:
        from functools import lru_cache

        @lru_cache(maxsize=1)
        def _load(path: str) -> Any:
            import atexit

            from llama_cpp import Llama

            old_stderr = sys.stderr
            try:
                sys.stderr = open(os.devnull, "w")
                model = Llama(
                    model_path=path,
                    n_ctx=4096,
                    n_threads=min(os.cpu_count() or 4, 8),
                    n_gpu_layers=0,
                    verbose=False,
                )
            finally:
                sys.stderr.close()
                sys.stderr = old_stderr
            atexit.register(model.close)
            return model

        model = _load(str(model_path))
        result = model.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object", "schema": schema},
            temperature=0.1,
            max_tokens=1024,
        )
        content = result["choices"][0]["message"]["content"]
        return json.loads(content)

    except Exception:
        return None


# ===================================================================
# Shared helpers
# ===================================================================

def _get_model_path() -> Path:
    """Return the path to the GGUF model, downloading if necessary."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / MODEL_FILENAME

    if model_path.exists():
        return model_path

    if not _download_file(
        MODEL_URL, model_path, f"Tier 2.5 model ({MODEL_SIZE_MB} MB)",
        MODEL_SIZE_MB,
    ):
        from writ.utils import console
        console.print(
            "[dim]You can manually download from:[/dim]\n"
            f"  {MODEL_URL}\n"
            f"[dim]Place it at:[/dim] {model_path}\n"
        )
        raise SystemExit(1)

    return model_path


def _score_summary(score: int) -> str:
    for (lo, hi), summary in SCORE_SUMMARIES.items():
        if lo <= score < hi:
            return summary
    return ""


def _build_qwen_prompt(instruction_text: str, ml_score: LintScore) -> str:
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


# ===================================================================
# Public API
# ===================================================================

def compute_score_local(
    instruction_text: str,
    tier1_issues: list[LintResult] | None = None,
) -> LintScore:
    """Run Tier 2.5 hybrid scoring: LightGBM scores + local LLM feedback.

    Tries llama.cpp binary (GPU) first, falls back to llama-cpp-python (CPU).
    """
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

    # Step 2: local LLM feedback
    model_path = _get_model_path()
    user_prompt = _build_qwen_prompt(instruction_text, ml_score)
    qwen_result: dict | None = None

    # 2a: Try llama-server (GPU-accelerated via Vulkan/Metal, persistent)
    cli_path = _get_llama_cli()
    if cli_path:
        from writ.utils import console
        backend = "Vulkan" if "vulkan" in str(cli_path) else (
            "Metal" if "macos" in str(cli_path) else "CPU"
        )
        console.print(f"  [dim]llama.cpp ({backend})[/dim]")
        if _ensure_server(cli_path, model_path):
            qwen_result = _infer_server(
                SYSTEM_PROMPT, user_prompt, FEEDBACK_SCHEMA,
            )

    # 2b: Fallback to llama-cpp-python
    if qwen_result is None and _has_llama_cpp_python():
        from writ.utils import console
        console.print("  [dim]llama-cpp-python (CPU)[/dim]")
        qwen_result = _infer_python(
            model_path, SYSTEM_PROMPT, user_prompt, FEEDBACK_SCHEMA,
        )

    # 2c: No backend available
    if qwen_result is None:
        from writ.utils import console
        console.print(
            "\n[red bold]No local LLM backend available.[/red bold]\n"
            "[dim]--deep-local will download llama.cpp automatically on "
            "first run.\nIf download fails, install llama-cpp-python:[/dim]\n"
            "  [cyan]pip install llama-cpp-python[/cyan]\n"
        )
        raise SystemExit(1)

    # Step 3: Combine ML scores + LLM feedback
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
