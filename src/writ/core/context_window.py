"""Context window management for API invocations.

When writ invokes a peer via raw LLM API (no CLI agent), it must compose
the system prompt and conversation history within token limits.  This module
handles sliding window + summarization to keep conversations within bounds.

Token estimation uses ``len(text) / 4`` as a fast heuristic (no tokenizer
dependency).  Good enough for deciding when to truncate.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_MAX_TOKENS = 100_000
ATTACHMENT_TRUNCATE_THRESHOLD = 20_000
SUMMARY_TRIGGER_RATIO = 0.6


def estimate_tokens(text: str) -> int:
    """Rough token count: ~4 chars per token for English text."""
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# System prompt composition
# ---------------------------------------------------------------------------

def compose_system_prompt(
    peer_repo_root: Path | None = None,
    *,
    agent_instructions: str = "",
    project_context: str = "",
) -> str:
    """Build a system prompt for API invocation from .writ/ context.

    Includes agent instructions and project context if available.
    Falls back to reading files from the peer repo's .writ/ directory.
    """
    parts: list[str] = []

    if agent_instructions:
        parts.append(agent_instructions)
    elif peer_repo_root:
        agents_dir = peer_repo_root / ".writ" / "agents"
        if agents_dir.is_dir():
            for yaml_file in sorted(agents_dir.glob("*.yaml")):
                content = yaml_file.read_text(encoding="utf-8", errors="replace")
                parts.append(f"# Agent: {yaml_file.stem}\n{content}")

    if project_context:
        parts.append(project_context)
    elif peer_repo_root:
        ctx_file = peer_repo_root / ".writ" / "project-context.md"
        if ctx_file.is_file():
            parts.append(ctx_file.read_text(encoding="utf-8", errors="replace"))

    if not parts:
        return "You are a helpful AI agent."

    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Conversation history windowing
# ---------------------------------------------------------------------------

def truncate_attachment(text: str, max_chars: int = ATTACHMENT_TRUNCATE_THRESHOLD * 4) -> str:
    """Truncate large inline attachments with a note."""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n\n[... file truncated for context window ...]\n\n" + text[-half:]


def _truncate_message_content(content: str) -> str:
    """Shrink <attached> blocks in a message if they're too large."""
    if "<attached" not in content:
        return content

    import re
    def _shrink(m: re.Match) -> str:
        tag = m.group(1)
        body = m.group(2)
        closing = m.group(3)
        body = truncate_attachment(body)
        return f"{tag}{body}{closing}"

    return re.sub(
        r"(<attached[^>]*>)(.*?)(</attached>)",
        _shrink,
        content,
        flags=re.DOTALL,
    )


def sliding_window(
    messages: list[dict[str, str]],
    system_prompt: str = "",
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[dict[str, str]]:
    """Apply a sliding window to keep conversation history within token limits.

    Strategy:
    1. Always keep the most recent message (the one we're responding to)
    2. Truncate large attachments in older messages
    3. Drop oldest messages until we're within budget
    4. If only 1-2 messages remain and we're still over, summarize dropped ones
    """
    if not messages:
        return messages

    system_tokens = estimate_tokens(system_prompt)
    budget = max_tokens - system_tokens
    if budget <= 0:
        budget = max_tokens // 2

    processed = []
    for msg in messages:
        new_content = _truncate_message_content(msg["content"])
        processed.append({**msg, "content": new_content})

    total = sum(estimate_tokens(m["content"]) for m in processed)
    if total <= budget:
        return processed

    result = [processed[-1]]
    remaining_budget = budget - estimate_tokens(result[0]["content"])
    dropped_count = 0

    for msg in reversed(processed[:-1]):
        msg_tokens = estimate_tokens(msg["content"])
        if remaining_budget >= msg_tokens:
            result.insert(0, msg)
            remaining_budget -= msg_tokens
        else:
            dropped_count += 1

    if dropped_count > 0:
        summary_note = {
            "role": "system",
            "content": (
                f"[Context note: {dropped_count} earlier message(s) were omitted "
                f"to fit within context limits. The conversation continues below.]"
            ),
        }
        result.insert(0, summary_note)

    return result


# ---------------------------------------------------------------------------
# Build messages for API invocation
# ---------------------------------------------------------------------------

def build_api_messages(
    conversation_messages: list[dict[str, str]],
    new_message: str,
    *,
    system_prompt: str = "",
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> tuple[str, list[dict[str, str]]]:
    """Prepare system prompt and messages list for an API call.

    Returns ``(system_prompt, messages)`` ready for the provider.
    """
    all_messages = list(conversation_messages)
    all_messages.append({"role": "user", "content": new_message})

    windowed = sliding_window(all_messages, system_prompt, max_tokens=max_tokens)

    return system_prompt, windowed
