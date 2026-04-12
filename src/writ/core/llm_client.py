"""Unified LLM client for writ AI features (plan review, etc.).

Supports OpenAI-compatible APIs (openai, local), Anthropic, and Gemini.
Reads model config from ~/.writ/config.yaml. Falls back to enwrit.com backend
when no local model is configured.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Generator
from typing import Any

from writ.core import auth, store
from writ.core.models import ModelConfig


class LLMError(Exception):
    """Raised when an LLM call fails."""


def get_model_config() -> ModelConfig | None:
    """Load the user's configured model, or None if not set."""
    config = store.load_global_config()
    return config.model


def _resolve_model(cfg: ModelConfig) -> str:
    """Return the model name to use, applying defaults per provider."""
    if cfg.model_name:
        return cfg.model_name
    defaults = {
        "openai": "gpt-4o",
        "anthropic": "claude-sonnet-4-20250514",
        "gemini": "gemini-2.5-flash",
        "local": "default",
    }
    return defaults.get(cfg.provider, "default")


def _call_openai_compatible(
    cfg: ModelConfig,
    system_prompt: str,
    user_prompt: str,
    *,
    stream: bool = False,
    json_mode: bool = False,
) -> str | Generator[str, None, None]:
    """Call an OpenAI-compatible API (covers openai + local providers)."""
    import httpx

    base_url = (cfg.base_url or "https://api.openai.com/v1").rstrip("/")
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    body: dict[str, Any] = {
        "model": _resolve_model(cfg),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
    }
    if json_mode and cfg.provider != "local":
        body["response_format"] = {"type": "json_object"}
    if stream:
        body["stream"] = True

    url = f"{base_url}/chat/completions"

    if stream:
        return _stream_openai(url, headers, body)

    resp = httpx.post(url, json=body, headers=headers, timeout=120)
    if resp.status_code != 200:
        raise LLMError(f"API error {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _stream_openai(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
) -> Generator[str, None, None]:
    """Stream tokens from an OpenAI-compatible endpoint."""
    import httpx

    with httpx.stream("POST", url, json=body, headers=headers, timeout=120) as resp:
        if resp.status_code != 200:
            raise LLMError(f"API error {resp.status_code}")
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield content
            except json.JSONDecodeError:
                continue


def _call_anthropic(
    cfg: ModelConfig,
    system_prompt: str,
    user_prompt: str,
    *,
    stream: bool = False,
    json_mode: bool = False,
) -> str | Generator[str, None, None]:
    """Call the Anthropic Messages API.

    Anthropic has no native JSON mode flag. When *json_mode* is True we
    append a JSON-only instruction to the system prompt as a workaround.
    """
    import httpx

    if json_mode:
        system_prompt = (
            system_prompt
            + "\n\nIMPORTANT: Respond with valid JSON only."
            " No markdown fences, no explanation outside the JSON structure."
        )

    base_url = (cfg.base_url or "https://api.anthropic.com").rstrip("/")
    headers = {
        "Content-Type": "application/json",
        "x-api-key": cfg.api_key or "",
        "anthropic-version": "2023-06-01",
    }

    body: dict[str, Any] = {
        "model": _resolve_model(cfg),
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
        "temperature": 0.3,
    }

    if stream:
        body["stream"] = True
        return _stream_anthropic(base_url, headers, body)

    resp = httpx.post(
        f"{base_url}/v1/messages", json=body, headers=headers, timeout=120,
    )
    if resp.status_code != 200:
        raise LLMError(f"Anthropic API error {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    return data["content"][0]["text"]


def _stream_anthropic(
    base_url: str,
    headers: dict[str, str],
    body: dict[str, Any],
) -> Generator[str, None, None]:
    """Stream tokens from Anthropic SSE."""
    import httpx

    with httpx.stream(
        "POST", f"{base_url}/v1/messages", json=body, headers=headers, timeout=120,
    ) as resp:
        if resp.status_code != 200:
            raise LLMError(f"Anthropic API error {resp.status_code}")
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            try:
                chunk = json.loads(line[6:])
                if chunk.get("type") == "content_block_delta":
                    text = chunk.get("delta", {}).get("text", "")
                    if text:
                        yield text
            except json.JSONDecodeError:
                continue


def _call_gemini(
    cfg: ModelConfig,
    system_prompt: str,
    user_prompt: str,
    *,
    stream: bool = False,
    json_mode: bool = False,
) -> str | Generator[str, None, None]:
    """Call Google Gemini via the REST API."""
    import httpx

    model = _resolve_model(cfg)
    api_key = cfg.api_key or ""

    body: dict[str, Any] = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.3},
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"

    if stream:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:streamGenerateContent?alt=sse&key={api_key}"
        )
        return _stream_gemini(url, body)

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    resp = httpx.post(url, json=body, timeout=120)
    if resp.status_code != 200:
        raise LLMError(f"Gemini API error {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise LLMError(f"Unexpected Gemini response: {data}") from exc


def _stream_gemini(
    url: str,
    body: dict[str, Any],
) -> Generator[str, None, None]:
    """Stream tokens from Gemini SSE."""
    import httpx

    with httpx.stream("POST", url, json=body, timeout=120) as resp:
        if resp.status_code != 200:
            raise LLMError(f"Gemini API error {resp.status_code}")
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            try:
                chunk = json.loads(line[6:])
                parts = (
                    chunk.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [])
                )
                for part in parts:
                    text = part.get("text", "")
                    if text:
                        yield text
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


def call_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    stream: bool = False,
    json_mode: bool = False,
) -> str | Generator[str, None, None]:
    """Call the user's configured LLM.

    Returns the full response text, or a generator of token chunks if stream=True.
    Raises LLMError on failures. Returns None-guard upstream handles fallback.
    """
    cfg = get_model_config()
    if cfg is None:
        raise LLMError("no_model_configured")

    if cfg.provider in ("openai", "local"):
        return _call_openai_compatible(
            cfg, system_prompt, user_prompt, stream=stream, json_mode=json_mode,
        )
    if cfg.provider == "anthropic":
        return _call_anthropic(
            cfg, system_prompt, user_prompt, stream=stream, json_mode=json_mode,
        )
    if cfg.provider == "gemini":
        return _call_gemini(
            cfg, system_prompt, user_prompt, stream=stream, json_mode=json_mode,
        )
    raise LLMError(f"Unknown provider: {cfg.provider}")


def call_backend_plan_review(
    plan_text: str,
    project_context: str | None,
) -> str:
    """Fall back to enwrit.com backend for plan review (requires login)."""
    import httpx

    token = auth.get_token()
    if not token:
        raise LLMError("not_logged_in")

    config = store.load_global_config()
    base_url = config.registry_url.rstrip("/")

    body: dict[str, Any] = {
        "plan_content": plan_text,
        "source": "cli",
    }
    if project_context:
        body["project_context"] = project_context

    resp = httpx.post(
        f"{base_url}/plan-review",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )
    if resp.status_code == 429:
        raise LLMError(
            "Daily plan review limit reached. "
            "Configure your own model with `writ model set` for unlimited reviews.",
        )
    if resp.status_code != 200:
        raise LLMError(f"Backend error {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    if "feedback" in data or "alternatives" in data or "overall_assessment" in data:
        return data
    return data.get("review", json.dumps(data, indent=2))


def is_interactive() -> bool:
    """Check if stdout is a terminal (not piped or captured by an agent)."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
