"""MCP server exposing writ instructions, project context, and repo files.

Allows external AI agents (in Cursor, Claude Desktop, etc.) to discover
and read this repo's instructions without the human running CLI commands.

V1 tools: list/get instructions, project context
V2 tools: compose context, search, read files, list files
V3 tools: agent-to-agent conversations (start, send, send_and_wait, check_inbox, read, complete)

Install: pip install enwrit[mcp]
Run:     writ mcp serve
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from writ.core import composer, messaging, peers, scanner, store
from writ.core.models import AutoRespondTier, ConversationStatus
from writ.utils import yaml_dumps

mcp = FastMCP("writ")

_MAX_FILE_SIZE = 512 * 1024  # 512 KB hard limit for file reads


def _repo_root() -> Path:
    """Resolve the repository root (parent of .writ/)."""
    writ_dir = store.project_writ_dir()
    if writ_dir and writ_dir.exists():
        return writ_dir.parent
    return Path.cwd()


def _safe_resolve(path_str: str) -> Path | None:
    """Resolve a relative path safely within the repo root.

    Returns None if the path escapes the repo root or is ignored.
    """
    root = _repo_root()
    try:
        target = (root / path_str).resolve()
    except (OSError, ValueError):
        return None
    if not str(target).startswith(str(root.resolve())):
        return None
    rel = target.relative_to(root.resolve())
    spec = scanner.load_ignore_spec(root)
    if spec.match_file(str(rel)):
        return None
    return target


# ---------------------------------------------------------------------------
# V1 Tools -- instruction discovery
# ---------------------------------------------------------------------------

@mcp.tool()
def writ_list_instructions() -> list[dict[str, str | None]]:
    """List all instructions available in this writ project.

    Returns a list of instruction summaries (name, description, task_type, tags).
    Use this to discover what instructions, rules, and context are available.
    """
    instructions = store.list_instructions()
    return [
        {
            "name": cfg.name,
            "description": cfg.description,
            "task_type": cfg.task_type,
            "tags": ", ".join(cfg.tags) if cfg.tags else None,
        }
        for cfg in instructions
    ]


@mcp.tool()
def writ_get_instruction(name: str) -> str:
    """Get the full content of a writ instruction by name.

    Returns the instruction as YAML (name, description, tags, instructions, composition).
    Use this to read another repo's agent instructions, rules, or context.
    """
    cfg = store.load_instruction(name)
    if cfg is None:
        return (
            f"Error: instruction '{name}' not found. "
            "Use writ_list_instructions to see available instructions."
        )
    return yaml_dumps(cfg.model_dump(mode="json"))


@mcp.tool()
def writ_get_project_context() -> str:
    """Get this project's auto-detected context (languages, frameworks, directory structure).

    Returns the project-context.md that writ generates on init. Use this to
    understand what kind of project you're connecting to.
    """
    context = store.load_project_context()
    if context:
        return context

    if not store.is_initialized():
        return "Error: this project has no .writ/ directory. Run 'writ init' first."

    languages = scanner.detect_languages()
    tree = scanner.get_directory_tree()
    parts = ["# Project Context\n"]
    if languages:
        parts.append("## Languages\n")
        for lang, count in sorted(languages.items(), key=lambda x: -x[1]):
            parts.append(f"- {lang}: {count} files")
    if tree:
        parts.append(f"\n## Directory Structure\n\n```\n{tree}\n```")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# V2 Tools -- compose, search, file access
# ---------------------------------------------------------------------------

@mcp.tool()
def writ_compose_context(name: str) -> str:
    """Compose the full 4-layer context for an instruction.

    Merges project context + inherited instructions + own instructions + handoffs
    into a single document. This is writ's core innovation -- context composition.

    Use this to get the complete, ready-to-use instruction set for an agent,
    rather than reading individual instructions one by one.
    """
    cfg = store.load_instruction(name)
    if cfg is None:
        return (
            f"Error: instruction '{name}' not found. "
            "Use writ_list_instructions to see available instructions."
        )
    composed = composer.compose(cfg)
    if not composed:
        return f"Instruction '{name}' produced empty composition (no instructions or context)."
    return composed


@mcp.tool()
def writ_search_instructions(query: str) -> list[dict[str, str | None]]:
    """Search instructions in this project by name, description, or tags.

    Returns matching instruction summaries. The query is matched as a
    case-insensitive substring against name, description, and tags.
    """
    query_lower = query.lower()
    instructions = store.list_instructions()
    results = []
    for cfg in instructions:
        searchable = " ".join([
            cfg.name,
            cfg.description or "",
            " ".join(cfg.tags),
            cfg.task_type or "",
        ]).lower()
        if query_lower in searchable:
            results.append({
                "name": cfg.name,
                "description": cfg.description,
                "task_type": cfg.task_type,
                "tags": ", ".join(cfg.tags) if cfg.tags else None,
            })
    return results


@mcp.tool()
def writ_read_file(path: str) -> str:
    """Read a file from this repository (read-only).

    Path is relative to the repo root. Respects .writignore and .gitignore.
    Rejects paths that escape the repository or point to ignored/binary files.
    Maximum file size: 512 KB.

    Use this when instructions and project context aren't enough and you need
    to inspect actual source code in the repo.
    """
    if not path or path.strip() == "":
        return "Error: path is required."

    target = _safe_resolve(path)
    if target is None:
        return f"Error: '{path}' is outside the repo or matched by ignore patterns."

    if not target.is_file():
        return f"Error: '{path}' is not a file or does not exist."

    size = target.stat().st_size
    if size > _MAX_FILE_SIZE:
        return f"Error: '{path}' is too large ({size:,} bytes, max {_MAX_FILE_SIZE:,})."

    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"Error: '{path}' appears to be a binary file."
    except OSError as exc:
        return f"Error reading '{path}': {exc}"


@mcp.tool()
def writ_list_files(
    directory: str = ".",
    pattern: str = "",
) -> list[str]:
    """List files in a directory of this repository.

    Returns relative paths from repo root. Respects .writignore/.gitignore.
    Optionally filter by a substring pattern (e.g. '.py', 'test_').

    Args:
        directory: Directory to list, relative to repo root. Default: root.
        pattern: Optional substring filter on filenames.
    """
    root = _repo_root()
    target_dir = _safe_resolve(directory)
    if target_dir is None or not target_dir.is_dir():
        return [f"Error: '{directory}' is not a valid directory."]

    spec = scanner.load_ignore_spec(root)
    resolved_root = root.resolve()
    results: list[str] = []
    pattern_lower = pattern.lower()

    for dirpath, dirnames, filenames in os.walk(target_dir):
        dp = Path(dirpath)
        rel_dir = dp.relative_to(resolved_root)
        if spec.match_file(str(rel_dir) + "/"):
            dirnames.clear()
            continue

        for fname in sorted(filenames):
            rel_file = str(rel_dir / fname)
            if spec.match_file(rel_file):
                continue
            if pattern_lower and pattern_lower not in fname.lower():
                continue
            results.append(rel_file)

        if len(results) >= 500:
            break

    return results


# ---------------------------------------------------------------------------
# V3 Tools -- agent-to-agent conversations
# ---------------------------------------------------------------------------

def _local_identity() -> tuple[str, str]:
    """Return (agent_name, repo_name) for this MCP server's repo."""
    repo = _repo_root().name
    instructions = store.list_instructions()
    agent = instructions[0].name if instructions else "agent"
    return agent, repo


def _relay_message(
    conv_id: str, agent: str, repo: str, content: str, *,
    goal: str = "", attachments: list[str] | None = None,
) -> bool:
    """Send a message through the backend relay (for remote peers)."""
    try:
        from writ.core import auth
        if not auth.is_logged_in():
            return False
        from writ.integrations.registry import RegistryClient
        client = RegistryClient()
        result = client.relay_message(
            conv_id=conv_id,
            agent_name=agent,
            repo_name=repo,
            content=content,
            attachments=attachments,
            goal=goal,
        )
        return result is not None
    except Exception:  # noqa: BLE001
        return False


def _invoke_peer_agent(peer_name: str, message: str) -> str | None:
    """Invoke a peer's CLI agent or API, returning the response or None."""
    peer = peers.get_peer(peer_name)
    if peer is None or peer.auto_respond == AutoRespondTier.OFF:
        return None
    try:
        from writ.core.invoker import invoke_peer
        result = invoke_peer(peer, message, timeout=300)
        if result.success:
            return result.response
    except Exception:  # noqa: BLE001
        pass
    return None


@mcp.tool()
def writ_start_conversation(
    to_repo: str,
    goal: str,
    message: str,
    attach_files: list[str] | None = None,
    attach_context: list[str] | None = None,
) -> dict:
    """Start a new conversation with an agent in another repository.

    Write your opening message. Optionally attach files or writ instructions
    for the other agent to review. Returns the conversation ID for follow-up.

    Args:
        to_repo: Name of the peer repo (as registered in peers.yaml).
        goal: What this conversation aims to achieve.
        message: Your opening message (free-form text).
        attach_files: Optional list of file paths to embed in the message.
        attach_context: Optional list of writ:// URIs to embed.
    """
    peer = peers.get_peer(to_repo)
    if peer is None:
        return {"error": f"Peer '{to_repo}' not found. Use writ peers add to register it."}

    agent, repo = _local_identity()
    conv = messaging.create_conversation(
        peer_repo=to_repo,
        goal=goal,
        local_agent=agent,
        local_repo=repo,
        peer_agent="",
    )

    conv_path = messaging.conversations_dir() / messaging._conv_filename(to_repo, goal)
    messaging.append_message(
        conv_path,
        agent=agent,
        repo=repo,
        content=message,
        attach_files=attach_files,
        attach_context=attach_context,
        repo_root=_repo_root(),
    )

    if peer.transport == "local":
        peer_conv_dir = peers.resolve_peer_conversations_dir(peer)
        if peer_conv_dir is not None:
            peer_file = peer_conv_dir / messaging._conv_filename(repo, goal)
            if not peer_file.exists():
                import shutil
                peer_conv_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(conv_path), str(peer_file))
    elif peer.transport == "remote":
        _relay_message(conv.id, agent, repo, message, goal=goal)

    return {"conv_id": conv.id, "status": "started", "file": conv_path.name}


@mcp.tool()
def writ_send_message(
    conv_id: str,
    message: str,
    attach_files: list[str] | None = None,
    attach_context: list[str] | None = None,
) -> dict:
    """Send a message in an existing conversation (fire-and-forget).

    You can attach files (e.g. plans, source code) for the other agent to
    review. Returns immediately -- use this when you don't need to wait for
    a response before continuing.

    Args:
        conv_id: Conversation ID from writ_start_conversation.
        message: Your message text.
        attach_files: Optional file paths to embed.
        attach_context: Optional writ:// URIs to embed.
    """
    result = messaging.find_conversation(conv_id)
    if result is None:
        return {"error": f"Conversation '{conv_id}' not found."}
    path, conv = result

    if conv.status == ConversationStatus.COMPLETED:
        return {"error": "Conversation is already completed."}
    if conv.status == ConversationStatus.PAUSED:
        return {"error": "Conversation is paused. Use writ chat resume to continue."}

    agent, repo = _local_identity()
    msg = messaging.append_message(
        path,
        agent=agent,
        repo=repo,
        content=message,
        attach_files=attach_files,
        attach_context=attach_context,
        repo_root=_repo_root(),
    )
    return {"status": "sent", "message_id": msg.id, "message_count": conv.turn_count + 1}


@mcp.tool()
async def writ_send_and_wait(
    conv_id: str,
    message: str,
    attach_files: list[str] | None = None,
    attach_context: list[str] | None = None,
    poll_interval: int = 15,
    timeout: int = 300,
) -> dict:
    """Send a message and wait for the other participant's response.

    Your session stays active while waiting (MCP Polling). Use this when you
    need the other agent's input before continuing your work.

    Args:
        conv_id: Conversation ID.
        message: Your message text.
        attach_files: Optional file paths to embed.
        attach_context: Optional writ:// URIs to embed.
        poll_interval: Seconds between polls (default 15).
        timeout: Max seconds to wait (default 300).
    """
    result = messaging.find_conversation(conv_id)
    if result is None:
        return {"error": f"Conversation '{conv_id}' not found."}
    path, conv = result

    agent, repo = _local_identity()
    messaging.append_message(
        path,
        agent=agent,
        repo=repo,
        content=message,
        attach_files=attach_files,
        attach_context=attach_context,
        repo_root=_repo_root(),
    )

    sent_count = conv.turn_count + 1
    elapsed = 0
    interval = max(1, poll_interval)
    invoked = False

    peer_name = ""
    for p in conv.participants:
        if p.repo != repo:
            peer_name = p.repo
            break

    peer = peers.get_peer(peer_name) if peer_name else None
    if peer and peer.transport == "remote":
        _relay_message(conv.id, agent, repo, message)

    while elapsed < timeout:
        await asyncio.sleep(interval)
        elapsed += interval

        refreshed = messaging.load_conversation(path)
        if refreshed is None:
            return {"error": "Conversation file disappeared during polling."}

        if len(refreshed.messages) > sent_count:
            latest = refreshed.messages[-1]
            if latest.author_repo != repo:
                return {
                    "response": latest.content,
                    "from_agent": latest.author_agent,
                    "from_repo": latest.author_repo,
                    "timestamp": messaging._fmt_ts(latest.timestamp),
                    "message_id": latest.id,
                    "attachments": latest.attachments or [],
                }

        if not invoked and elapsed >= interval * 2 and peer_name:
            invoked = True
            response = _invoke_peer_agent(peer_name, message)
            if response:
                messaging.append_message(
                    path,
                    agent="agent",
                    repo=peer_name,
                    content=response,
                )
                return {
                    "response": response,
                    "from_agent": "agent",
                    "from_repo": peer_name,
                    "invoked": True,
                }

    return {"timeout": True, "waited_seconds": elapsed}


@mcp.tool()
def writ_check_inbox() -> list[dict]:
    """Check for conversations that have new messages you haven't read yet.

    Returns a list of conversations with unread activity. Use this at the
    start of a session to see if other agents have sent you messages.
    """
    agent, repo = _local_identity()
    results: list[dict] = []
    for _path, conv in messaging.list_conversations():
        if conv.status in (ConversationStatus.COMPLETED, ConversationStatus.FAILED):
            continue
        if not conv.messages:
            continue
        last = conv.messages[-1]
        if last.author_repo != repo:
            results.append({
                "conv_id": conv.id,
                "peer": last.author_repo,
                "goal": conv.goal,
                "unread_count": 1,
                "last_message_preview": last.content[:200],
                "status": conv.status.value,
            })
    return results


@mcp.tool()
def writ_read_conversation(
    conv_id: str,
    last_n: int = 0,
) -> dict:
    """Read a conversation's history.

    Optionally read only the last N messages. File attachments are included
    inline in each message.

    Args:
        conv_id: Conversation ID.
        last_n: If > 0, return only the last N messages.
    """
    result = messaging.find_conversation(conv_id)
    if result is None:
        return {"error": f"Conversation '{conv_id}' not found."}
    _, conv = result

    msgs = conv.messages
    if last_n > 0:
        msgs = msgs[-last_n:]

    return {
        "conv_id": conv.id,
        "goal": conv.goal,
        "status": conv.status.value,
        "participants": [
            {"agent": p.agent, "repo": p.repo} for p in conv.participants
        ],
        "messages": [
            {
                "id": m.id,
                "from_agent": m.author_agent,
                "from_repo": m.author_repo,
                "timestamp": messaging._fmt_ts(m.timestamp),
                "content": m.content,
                "attachments": m.attachments,
            }
            for m in msgs
        ],
    }


@mcp.tool()
def writ_complete_conversation(
    conv_id: str,
    summary: str,
) -> dict:
    """Mark a conversation as completed with a brief summary.

    Include a summary of the outcome so both participants and human
    observers can understand what was achieved.

    Args:
        conv_id: Conversation ID.
        summary: Brief summary of the conversation outcome.
    """
    result = messaging.find_conversation(conv_id)
    if result is None:
        return {"error": f"Conversation '{conv_id}' not found."}
    path, _ = result

    messaging.complete_conversation(path, summary)
    return {"status": "completed", "summary": summary}


# ---------------------------------------------------------------------------
# Resources -- read-only data external agents can pull into context
# ---------------------------------------------------------------------------

@mcp.resource("writ://instructions/{name}")
def instruction_resource(name: str) -> str:
    """Read a writ instruction by name."""
    cfg = store.load_instruction(name)
    if cfg is None:
        return f"Instruction '{name}' not found."
    return yaml_dumps(cfg.model_dump(mode="json"))


@mcp.resource("writ://project-context")
def project_context_resource() -> str:
    """Read this project's auto-detected context."""
    return store.load_project_context() or "No project context available."


@mcp.resource("writ://files/{path}")
def file_resource(path: str) -> str:
    """Read a file from the repository by path (relative to repo root)."""
    return writ_read_file(path)


def run_server() -> None:
    """Start the MCP server on stdio transport."""
    mcp.run(transport="stdio")
