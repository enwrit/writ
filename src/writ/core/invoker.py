"""Invoke agents in peer repos that don't have an active session.

Mechanism 2 from the architecture doc: when the other side's agent isn't in
an active MCP/IDE session, writ can wake it up by invoking a CLI agent
(preferred -- full context) or falling back to a raw LLM API call (partial
context).

CLI agent invocation is preferred because the CLI agent loads its own rules,
RAG, tools, and memory.  A raw API call only gets what writ manually composes.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from writ.core.models import AutoRespondTier, PeerConfig

# ---------------------------------------------------------------------------
# CLI agent detection
# ---------------------------------------------------------------------------

@dataclass
class CLIAgent:
    """A detected CLI agent binary."""
    name: str
    binary: str
    version_flag: str = "--version"

    def build_command(
        self,
        message: str,
        cwd: str,
        tier: AutoRespondTier = AutoRespondTier.FULL,
    ) -> list[str]:
        """Build the invocation command respecting the auto_respond tier.

        Tier mapping for Cursor CLI (``agent``):
          read_only       -> --mode ask  (read-only, no writes)
          full            -> --approve-mcps  (MCP tools only, no shell)
          dangerous_full  -> --force  (unrestricted shell access)

        Other CLI agents don't yet have granular tier support; they receive
        the message and rely on their own sandbox/approval mechanisms.
        """
        if self.name == "cursor":
            cmd = [
                self.binary, "-p",
                "--output-format", "text",
                "--trust",
                "--workspace", cwd,
            ]
            if tier == AutoRespondTier.READ_ONLY:
                cmd.extend(["--mode", "ask"])
            elif tier == AutoRespondTier.DANGEROUS_FULL:
                cmd.append("--force")
            else:
                cmd.append("--approve-mcps")
            cmd.append(message)
            return cmd
        if self.name == "claude":
            return [self.binary, "--print", "--message", message, "--cwd", cwd]
        if self.name == "gemini":
            return [self.binary, "--message", message, "--cwd", cwd]
        if self.name == "codex":
            return [self.binary, "--message", message, "--cwd", cwd]
        return [self.binary, "--message", message, "--cwd", cwd]


_KNOWN_AGENTS = [
    CLIAgent(name="cursor", binary="agent"),
    CLIAgent(name="claude", binary="claude"),
    CLIAgent(name="gemini", binary="gemini"),
    CLIAgent(name="codex", binary="codex"),
    CLIAgent(name="aider", binary="aider"),
]


def detect_cli_agents() -> list[CLIAgent]:
    """Find CLI agents available in PATH.

    Resolves the full binary path so subprocess.run works reliably on
    Windows where .CMD/.BAT wrappers aren't found without shell=True.
    """
    found: list[CLIAgent] = []
    for agent in _KNOWN_AGENTS:
        resolved = shutil.which(agent.binary)
        if resolved:
            found.append(CLIAgent(
                name=agent.name,
                binary=resolved,
                version_flag=agent.version_flag,
            ))
    return found


def preferred_cli_agent() -> CLIAgent | None:
    """Return the best available CLI agent (first detected wins)."""
    agents = detect_cli_agents()
    return agents[0] if agents else None


# ---------------------------------------------------------------------------
# CLI agent invocation
# ---------------------------------------------------------------------------

@dataclass
class InvocationResult:
    """Result from invoking an agent."""
    success: bool
    response: str
    method: str  # "cli" or "api"
    agent_name: str = ""
    error: str = ""


def invoke_cli_agent(
    peer: PeerConfig,
    message: str,
    *,
    agent: CLIAgent | None = None,
    tier: AutoRespondTier = AutoRespondTier.FULL,
    timeout: int = 300,
) -> InvocationResult:
    """Invoke a CLI agent in the peer repo's directory.

    The CLI agent loads the peer repo's rules, RAG, tools, and memory --
    full context.  This is much richer than a raw API call.

    The *tier* controls how much autonomy the CLI agent gets:
      read_only       -- read-only analysis (no writes)
      full            -- respond via MCP tools (no shell)
      dangerous_full  -- unrestricted shell access
    """
    cli = agent or preferred_cli_agent()
    if cli is None:
        return InvocationResult(
            success=False,
            response="",
            method="cli",
            error="No CLI agent found in PATH (tried: cursor/agent, claude, gemini, codex, aider).",
        )

    if not peer.path:
        return InvocationResult(
            success=False,
            response="",
            method="cli",
            error=f"Peer '{peer.name}' has no local path -- CLI invocation requires a local repo.",
        )

    cwd = peer.path
    if not Path(cwd).is_dir():
        return InvocationResult(
            success=False,
            response="",
            method="cli",
            error=f"Peer directory does not exist: {cwd}",
        )

    cmd = cli.build_command(message, cwd, tier=tier)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        if result.returncode == 0:
            return InvocationResult(
                success=True,
                response=result.stdout.strip(),
                method="cli",
                agent_name=cli.name,
            )
        return InvocationResult(
            success=False,
            response=result.stdout.strip(),
            method="cli",
            agent_name=cli.name,
            error=result.stderr.strip() or f"Exit code {result.returncode}",
        )
    except subprocess.TimeoutExpired:
        return InvocationResult(
            success=False, response="", method="cli",
            agent_name=cli.name, error=f"CLI agent timed out after {timeout}s.",
        )
    except FileNotFoundError:
        return InvocationResult(
            success=False, response="", method="cli",
            agent_name=cli.name, error=f"Binary '{cli.binary}' not found.",
        )
    except OSError as exc:
        return InvocationResult(
            success=False, response="", method="cli",
            agent_name=cli.name, error=str(exc),
        )


# ---------------------------------------------------------------------------
# Raw LLM API invocation (fallback)
# ---------------------------------------------------------------------------

def invoke_api(
    peer: PeerConfig,
    message: str,
    *,
    system_prompt: str = "",
    conversation_history: list[dict[str, str]] | None = None,
    provider: str = "anthropic",
    model: str = "",
    api_key: str = "",
    timeout: int = 120,
) -> InvocationResult:
    """Call an LLM API directly as a fallback when no CLI agent is available.

    The agent only gets what writ manually composes: .writ/ instructions +
    conversation history.  No RAG, no tools, no file access.
    """
    if not api_key:
        return InvocationResult(
            success=False, response="", method="api",
            error="No API key configured. Set llm.api_key in .writ/config.yaml.",
        )

    messages = []
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({"role": "user", "content": message})

    try:
        if provider in ("anthropic", "claude"):
            return _call_anthropic(
                system_prompt=system_prompt,
                messages=messages,
                model=model or "claude-sonnet-4-20250514",
                api_key=api_key,
                timeout=timeout,
            )
        if provider in ("openai", "gpt"):
            return _call_openai(
                system_prompt=system_prompt,
                messages=messages,
                model=model or "gpt-4o",
                api_key=api_key,
                timeout=timeout,
            )
        return InvocationResult(
            success=False, response="", method="api",
            error=f"Unsupported LLM provider: {provider}",
        )
    except Exception as exc:  # noqa: BLE001
        return InvocationResult(
            success=False, response="", method="api",
            error=f"API call failed: {exc}",
        )


def _call_anthropic(
    *,
    system_prompt: str,
    messages: list[dict[str, str]],
    model: str,
    api_key: str,
    timeout: int,
) -> InvocationResult:
    """Call Anthropic's Messages API."""
    import httpx

    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": messages,
        },
        timeout=timeout,
    )
    if resp.status_code != 200:
        return InvocationResult(
            success=False, response="", method="api",
            error=f"Anthropic API error {resp.status_code}: {resp.text[:300]}",
        )
    data = resp.json()
    text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text += block.get("text", "")
    return InvocationResult(success=True, response=text.strip(), method="api", agent_name=model)


def _call_openai(
    *,
    system_prompt: str,
    messages: list[dict[str, str]],
    model: str,
    api_key: str,
    timeout: int,
) -> InvocationResult:
    """Call OpenAI's Chat Completions API."""
    import httpx

    api_messages = []
    if system_prompt:
        api_messages.append({"role": "system", "content": system_prompt})
    api_messages.extend(messages)

    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"model": model, "messages": api_messages, "max_tokens": 4096},
        timeout=timeout,
    )
    if resp.status_code != 200:
        return InvocationResult(
            success=False, response="", method="api",
            error=f"OpenAI API error {resp.status_code}: {resp.text[:300]}",
        )
    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    return InvocationResult(success=True, response=text.strip(), method="api", agent_name=model)


# ---------------------------------------------------------------------------
# Smart invocation (auto-select method)
# ---------------------------------------------------------------------------

def invoke_peer(
    peer: PeerConfig,
    message: str,
    *,
    system_prompt: str = "",
    conversation_history: list[dict[str, str]] | None = None,
    llm_config: dict | None = None,
    timeout: int = 300,
) -> InvocationResult:
    """Invoke a peer's agent using the best available method.

    Respects the peer's ``auto_respond`` tier:
      off             -> refuse to invoke (user must handle manually)
      read_only       -> CLI agent in read-only mode
      full            -> CLI agent with MCP tools (safe default)
      dangerous_full  -> CLI agent with unrestricted shell access

    Priority when tier allows invocation:
      1. CLI agent invocation (full context)
      2. Raw API call (partial context, fallback)
    """
    tier = peer.auto_respond

    if tier == AutoRespondTier.OFF:
        return InvocationResult(
            success=False, response="", method="none",
            error=(
                f"Peer '{peer.name}' has auto_respond: off. "
                "Set to read_only, full, or dangerous_full in peers.yaml to enable invocation."
            ),
        )

    if peer.transport == "local" and peer.path:
        cli = preferred_cli_agent()
        if cli is not None:
            return invoke_cli_agent(
                peer, message, agent=cli, tier=tier, timeout=timeout,
            )

    cfg = llm_config or {}
    api_key = cfg.get("api_key", "")
    provider = cfg.get("provider", "anthropic")
    model = cfg.get("model", "")

    if api_key:
        return invoke_api(
            peer, message,
            system_prompt=system_prompt,
            conversation_history=conversation_history,
            provider=provider,
            model=model,
            api_key=api_key,
            timeout=timeout,
        )

    return InvocationResult(
        success=False, response="", method="none",
        error=(
            "Cannot reach peer: no CLI agent in PATH and no LLM API key configured. "
            "Install a CLI agent (cursor, claude, gemini, codex) or set "
            "llm.api_key in .writ/config.yaml."
        ),
    )
