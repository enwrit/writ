"""MCP server exposing writ instructions, project context, and agent communication.

Allows external AI agents (in Cursor, Claude Desktop, etc.) to discover
and use this repo's instructions without the human running CLI commands.

Full mode (18 tools -- for MCP-only users via uvx):
  V1: writ_list, writ_get
  V2: writ_compose, writ_search, writ_add
  V3: writ_chat_start, writ_chat_send, writ_chat_send_wait,
      writ_inbox, writ_chat_read, writ_chat_end
  V4: writ_review, writ_threads_list, writ_threads_start,
      writ_threads_post, writ_threads_resolve
  V5: writ_approvals_create, writ_approvals_check

Slim mode (2 tools -- for CLI users via 'writ mcp install'):
  writ_compose, writ_chat_send_wait

Install: pip install enwrit[mcp]
Run:     writ mcp serve
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from writ.core import auth, composer, messaging, peers, store
from writ.core.models import AutoRespondTier, ConversationStatus
from writ.utils import yaml_dumps

mcp = FastMCP("writ")


def _repo_root() -> Path:
    """Resolve the repository root (parent of .writ/)."""
    writ_dir = store.project_writ_dir()
    if writ_dir and writ_dir.exists():
        return writ_dir.parent
    return Path.cwd()


# ---------------------------------------------------------------------------
# V1 Tools -- instruction discovery
# ---------------------------------------------------------------------------

@mcp.tool()
def writ_list() -> list[dict[str, str | None]]:
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
def writ_get(name: str) -> str:
    """Get the full content of a writ instruction by name.

    Returns the instruction as YAML (name, description, tags, instructions, composition).
    Use this to read another repo's agent instructions, rules, or context.
    """
    cfg = store.load_instruction(name)
    if cfg is None:
        return (
            f"Error: instruction '{name}' not found. "
            "Use writ_list to see available instructions."
        )
    data = cfg.model_dump(mode="json")
    data = {k: v for k, v in data.items() if v is not None}
    if "format_overrides" in data:
        overrides = {k: v for k, v in data["format_overrides"].items() if v is not None}
        if overrides:
            data["format_overrides"] = overrides
        else:
            del data["format_overrides"]
    return yaml_dumps(data)


# ---------------------------------------------------------------------------
# V2 Tools -- compose, search, add
# ---------------------------------------------------------------------------

@mcp.tool()
def writ_compose(name: str) -> str:
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
            "Use writ_list to see available instructions."
        )
    composed = composer.compose(cfg)
    if not composed:
        return f"Instruction '{name}' produced empty composition (no instructions or context)."
    return composed


@mcp.tool()
def writ_search(
    query: str,
    scope: str = "local",
) -> list[dict[str, str | None]]:
    """Search instructions by name, description, or tags.

    Returns matching instruction summaries. The query is matched as a
    case-insensitive substring against name, description, and tags.

    Args:
        query: Search text.
        scope: Where to search. "local" = this project only (default),
               "hub" = unified Hub (semantic search: enwrit + PRPM, etc.),
               "all" = both local and Hub.
    """
    results: list[dict[str, str | None]] = []

    if scope in ("local", "all"):
        query_lower = query.lower()
        instructions = store.list_instructions()
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
                    "source": "local",
                })

    if scope in ("hub", "all"):
        try:
            client = _registry_client()
            hub_results = client.hub_search(query, limit=10)
            for item in hub_results:
                name = item.get("name") or ""
                if scope == "all" and any(r["name"] == name for r in results):
                    continue
                tags_raw = item.get("tags")
                if isinstance(tags_raw, list):
                    tags_str = ", ".join(str(t) for t in tags_raw) if tags_raw else None
                elif tags_raw is None:
                    tags_str = None
                else:
                    tags_str = str(tags_raw)
                writ_score = item.get("writ_score")
                score_str = None if writ_score is None else str(writ_score)
                hub_src = item.get("source")
                results.append({
                    "name": name,
                    "description": item.get("description"),
                    "task_type": item.get("task_type"),
                    "tags": tags_str,
                    "author": item.get("author"),
                    "source": hub_src if hub_src else "hub",
                    "writ_score": score_str,
                })
        except Exception:  # noqa: BLE001
            if scope == "hub":
                results.append({
                    "name": "",
                    "description": "Hub search failed (offline or not logged in)",
                    "source": "error",
                })

    return results


@mcp.tool()
def writ_add(name: str) -> dict:
    """Add a public instruction from the enwrit Hub into this project.

    Fetches the instruction by name from enwrit.com and saves it to the local
    .writ/ directory. The instruction is then available for composition,
    export, and use in any supported IDE format.

    Equivalent to: writ add <name>

    Requires .writ/ to be initialized (run 'writ init' first).
    No login required -- public instructions are freely available.

    Args:
        name: Name of the public instruction to add (e.g. 'verification-loop').
    """
    if not store.is_initialized():
        return {"error": "Not initialized. Run 'writ init' first."}

    existing = store.load_instruction(name)
    if existing:
        return {"error": f"'{name}' already exists locally. Remove it first to reinstall."}

    try:
        client = _registry_client()
        entry_source: str | None = None
        data = client.pull_public_agent(name)
        if not data:
            hub_items = client.hub_search(name, limit=20)
            entry: dict | None = None
            name_lower = name.lower()
            for it in hub_items:
                if (it.get("name") or "").lower() == name_lower:
                    entry = it
                    break
            if entry is None and len(hub_items) == 1:
                entry = hub_items[0]
            if entry:
                src = entry.get("source") or "enwrit"
                entry_source = str(src)
                dl_name = entry.get("name") or name
                data = client.hub_download(entry_source, str(dl_name))
        if not data:
            return {"error": f"'{name}' not found on enwrit.com Hub."}

        from writ.core.models import InstructionConfig
        ver = data.get("version", "1.0.0")
        hub_src = data.get("source") or entry_source or "enwrit"
        if hub_src == "enwrit":
            src_label = f"enwrit.com/{data.get('name', name)}@{ver}"
        else:
            src_label = f"hub/{hub_src}/{data.get('name', name)}@{ver}"
        cfg = InstructionConfig(
            name=data.get("name", name),
            description=data.get("description", ""),
            instructions=data.get("instructions", ""),
            tags=data.get("tags", []),
            version=ver,
            task_type=data.get("task_type"),
            source=src_label,
        )
        store.save_instruction(cfg)
        return {
            "status": "installed",
            "name": cfg.name,
            "task_type": cfg.task_type,
            "description": cfg.description,
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Failed to install '{name}': {exc}"}


# ---------------------------------------------------------------------------
# V3 Tools -- agent-to-agent conversations
# ---------------------------------------------------------------------------

def _local_identity() -> tuple[str, str]:
    """Return (agent_name, repo_name) for this MCP server's repo.

    Agent name prefers the first instruction with task_type == "agent",
    falling back to "agent".  Repo name is always the directory name.
    """
    repo = _repo_root().name
    instructions = store.list_instructions()
    for cfg in instructions:
        if cfg.task_type == "agent":
            return cfg.name, repo
    return "agent", repo


def _user_identity() -> str:
    """Return persistent user identity (username or auto-generated)."""
    from writ.core.auth import get_identity
    return get_identity()


def _relay_message(
    conv_id: str, agent: str, repo: str, content: str, *,
    goal: str = "", attachments: list[str] | None = None,
) -> bool:
    """Send a message through the backend relay (for remote peers)."""
    try:
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
    peer = peers.find_peer(peer_name)
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
def writ_peers_add(
    name: str,
    path: str = "",
    remote: str = "",
) -> dict:
    """Register a peer repository for agent-to-agent communication.

    A peer is another repository whose agent you want to talk to via
    writ_chat_start / writ_chat_send.

    For local peers (same machine): provide the filesystem path.
    For remote peers (different machines): provide the writ username
    (requires both sides to be logged in to enwrit.com).

    Args:
        name: Short name for this peer (e.g. 'backend-repo').
        path: Local filesystem path to the peer's repo root.
        remote: Remote writ username (for cross-device relay).
    """
    if not path and not remote:
        return {"error": "Provide either 'path' (local) or 'remote' (enwrit username)."}

    existing = peers.get_peer(name)
    if existing:
        return {"error": f"Peer '{name}' already registered. Remove it first to re-add."}

    peer = peers.add_peer(name, path=path or None, remote=remote or None)
    return {
        "status": "added",
        "name": peer.name,
        "transport": peer.transport,
        "path": peer.path,
        "remote": peer.remote,
    }


@mcp.tool()
def writ_peers_list() -> list[dict]:
    """List all registered peer repositories.

    Shows peers you can communicate with via writ_chat_start.
    """
    manifest = peers.load_peers()
    return [
        {
            "name": p.name,
            "transport": p.transport,
            "path": p.path,
            "remote": p.remote,
        }
        for p in manifest.peers.values()
    ]


@mcp.tool()
def writ_peers_remove(name: str) -> dict:
    """Remove a registered peer repository.

    Args:
        name: Name of the peer to remove.
    """
    if peers.remove_peer(name):
        return {"status": "removed", "name": name}
    return {"error": f"Peer '{name}' not found."}


@mcp.tool()
def writ_chat_start(
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
        return {"error": f"Peer '{to_repo}' not found. Use writ_peers_add to register it first."}

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
    relay_ok = True
    if peer.transport == "remote":
        relay_ok = _relay_message(
            conv.id, agent, repo, message,
            goal=goal, attachments=attach_files,
        )

    out: dict = {
        "conv_id": conv.id,
        "status": "started",
        "file": conv_path.name,
        "identity": _user_identity(),
    }
    if peer.transport == "remote" and not relay_ok:
        out["warning"] = "Message saved locally but relay delivery failed"
    return out


@mcp.tool()
def writ_chat_send(
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
        conv_id: Conversation ID from writ_chat_start.
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

    peer_name = ""
    for p in conv.participants:
        if p.repo != repo:
            peer_name = p.repo
            break
    peer = peers.find_peer(peer_name) if peer_name else None
    if peer and peer.transport == "remote":
        _relay_message(conv.id, agent, repo, message, attachments=attach_files)

    return {"status": "sent", "message_id": msg.id, "message_count": conv.turn_count + 1}


@mcp.tool()
async def writ_chat_send_wait(
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

    peer = peers.find_peer(peer_name) if peer_name else None
    if peer and peer.transport == "remote":
        _relay_message(conv.id, agent, repo, message, attachments=attach_files)

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
def writ_inbox() -> list[dict]:
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
            unread = 0
            for msg in reversed(conv.messages):
                if msg.author_repo == repo:
                    break
                unread += 1
            results.append({
                "conv_id": conv.id,
                "peer": last.author_repo,
                "goal": conv.goal,
                "unread_count": unread,
                "last_message_preview": last.content[:200],
                "status": conv.status.value,
            })
    return results


@mcp.tool()
def writ_chat_read(
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
def writ_chat_end(
    conv_id: str,
    summary: str = "",
) -> dict:
    """Mark a conversation as completed.

    Optionally include a summary of the outcome so both participants and
    human observers can understand what was achieved.

    Args:
        conv_id: Conversation ID.
        summary: Optional brief summary. Defaults to 'Conversation ended'.
    """
    result = messaging.find_conversation(conv_id)
    if result is None:
        return {"error": f"Conversation '{conv_id}' not found."}
    path, _ = result

    final_summary = summary or "Conversation ended"
    messaging.complete_conversation(path, final_summary)
    return {"status": "completed", "summary": final_summary}


# ---------------------------------------------------------------------------
# V4 tools -- Knowledge threads (reviews, threads, community knowledge)
# ---------------------------------------------------------------------------

def _registry_client():
    """Lazy import to avoid circular deps and allow offline usage."""
    from writ.integrations.registry import RegistryClient
    return RegistryClient()


def _agent_identity() -> tuple[str, str]:
    """Return (agent_name, repo_name) for the current project.

    Prefers the first instruction with task_type == "agent".
    Falls back to "agent" (never "unknown" or alphabetically-first).
    """
    repo_name = _repo_root().name
    instructions = store.list_instructions()
    for cfg in instructions:
        if cfg.task_type == "agent":
            return cfg.name, repo_name
    return "agent", repo_name


@mcp.tool()
def writ_review(
    instruction_name: str,
    rating: float,
    summary: str,
    strengths: list[str] | None = None,
    weaknesses: list[str] | None = None,
    context: dict | None = None,
) -> dict:
    """Submit a structured review for a public instruction on enwrit.com.

    Rate an instruction you've used. Your review helps improve instruction
    quality across the community. Requires ``writ login`` first.

    Args:
        instruction_name: Name of the public instruction to review.
        rating: Quality score from 1.0 to 5.0.
        summary: One-sentence overall assessment.
        strengths: List of what the instruction does well.
        weaknesses: List of what could be improved.
        context: Optional metadata (e.g. model, task_type, language).
    """
    if not auth.is_logged_in():
        return {"error": "Not logged in. Run `writ login` first."}
    agent_name, repo_name = _agent_identity()
    client = _registry_client()
    result = client.submit_review(
        instruction_name,
        rating=rating,
        summary=summary,
        strengths=strengths,
        weaknesses=weaknesses,
        context=context,
        author_agent=agent_name,
        author_repo=repo_name,
    )
    if result is None:
        return {"error": "Failed to submit review. Check login status and instruction name."}
    return result


@mcp.tool()
def writ_threads_list(
    query: str | None = None,
    thread_type: str | None = None,
    category: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search knowledge threads on enwrit.com.

    Find research threads, comparisons, best practices, and troubleshooting
    discussions created by AI agents and humans.

    Args:
        query: Search text (matches title and goal).
        thread_type: Filter by type: research, comparison, best_practice, troubleshooting.
        category: Filter by category: coding, testing, architecture, etc.
        status: Filter by status: open, resolved, archived.
        limit: Maximum results (default 20).
    """
    client = _registry_client()
    return client.search_threads(
        q=query,
        thread_type=thread_type,
        category=category,
        status=status,
        limit=limit,
    )


@mcp.tool()
def writ_threads_start(
    title: str,
    goal: str,
    thread_type: str,
    first_message: str,
    category: str | None = None,
    first_message_type: str = "comment",
) -> dict:
    """Start a new knowledge thread on enwrit.com.

    Create a goal-oriented discussion. Threads are collaborative --
    other agents and humans can participate.

    Args:
        title: Thread title (concise, descriptive).
        goal: What this thread aims to achieve.
        thread_type: One of: research, comparison, best_practice, troubleshooting.
        first_message: The opening message content.
        category: Optional category: coding, testing, architecture, etc.
        first_message_type: Type of opening message: comment, finding, question, proposal.
    """
    if not auth.is_logged_in():
        return {"error": "Not logged in. Run `writ login` first."}
    agent_name, repo_name = _agent_identity()
    client = _registry_client()
    result = client.start_thread(
        title=title,
        goal=goal,
        thread_type=thread_type,
        first_message=first_message,
        category=category,
        first_message_type=first_message_type,
        author_agent=agent_name,
        author_repo=repo_name,
    )
    if result is None:
        return {"error": "Failed to create thread. Check login status."}
    return result


@mcp.tool()
def writ_threads_post(
    thread_id: str,
    content: str,
    message_type: str = "comment",
) -> dict:
    """Post a message to an existing knowledge thread.

    Contribute findings, questions, or proposals to a thread.

    Args:
        thread_id: UUID of the thread to post to.
        content: Message content.
        message_type: One of: comment, finding, question, proposal.
    """
    if not auth.is_logged_in():
        return {"error": "Not logged in. Run `writ login` first."}
    agent_name, repo_name = _agent_identity()
    client = _registry_client()
    result = client.post_to_thread(
        thread_id,
        content=content,
        message_type=message_type,
        author_agent=agent_name,
        author_repo=repo_name,
    )
    if result is None:
        return {"error": "Failed to post message. Check thread ID and login."}
    return result


@mcp.tool()
def writ_threads_resolve(
    thread_id: str,
    conclusion: str,
) -> dict:
    """Resolve a knowledge thread with a conclusion.

    Mark a thread as resolved and record the distilled outcome.
    The conclusion becomes community knowledge.

    Args:
        thread_id: UUID of the thread to resolve.
        conclusion: The distilled conclusion/outcome of the thread.
    """
    if not auth.is_logged_in():
        return {"error": "Not logged in. Run `writ login` first."}
    client = _registry_client()
    result = client.resolve_thread(thread_id, conclusion=conclusion)
    if result is None:
        return {"error": "Failed to resolve thread. Check thread ID and login."}
    return result


# ---------------------------------------------------------------------------
# V5 tools -- Approval workflow (human-in-the-loop for elevated actions)
# ---------------------------------------------------------------------------

@mcp.tool()
def writ_approvals_create(
    action_type: str,
    description: str,
    reasoning: str = "",
    context: str = "{}",
    urgency: str = "normal",
    conv_id: str = "",
    session_id: str = "",
) -> dict:
    """Request human approval for an action. The human reviews and approves/denies
    via the Enwrit Console (enwrit.com/console) or CLI.

    action_type: shell_command, file_write, file_delete, deploy, install, or custom
    urgency: low (24h), normal (4h), high (1h), critical (15min)
    reasoning: explain WHY you want to do this (helps the human approve confidently)
    context: JSON string with action details (e.g. {"command": "npm install express"})

    Returns: {approval_id, status, expires_at, console_url}

    IMPORTANT: Always provide reasoning. Tell the user the approval_url before waiting.
    There is no writ_resolve_approval tool -- only humans can approve/deny.
    """
    import json as _json

    try:
        ctx = _json.loads(context) if context else {}
    except Exception:  # noqa: BLE001
        ctx = {"raw": context}

    from writ.core import auth as _auth
    if not _auth.is_logged_in():
        return {"error": "Not logged in. Run `writ login` first."}

    agent_name, repo_name = _agent_identity()
    client = _registry_client()
    result = client.create_approval(
        action_type=action_type,
        description=description,
        reasoning=reasoning,
        context=ctx,
        urgency=urgency,
        conv_id=conv_id,
        session_id=session_id,
        agent_name=agent_name,
        repo_name=repo_name,
    )
    if "id" in result:
        result["console_url"] = f"https://enwrit.com/console?approval={result['id']}"
    return result


@mcp.tool()
def writ_approvals_check(approval_id: str) -> dict:
    """Check the status of an approval request.

    Returns: {status, resolved_at, deny_reason}
    status is one of: pending, approved, denied, expired

    If pending, the human hasn't responded yet. Wait and check again later.
    If expired, the timeout was reached. Stop the blocked action.
    """
    from writ.core import auth as _auth
    if not _auth.is_logged_in():
        return {"error": "Not logged in. Run `writ login` first."}

    client = _registry_client()
    return client.get_approval(approval_id)


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


def run_server(slim: bool = False) -> None:
    """Start the MCP server on stdio transport.

    slim=True: only expose writ_compose and writ_chat_send_wait (2 tools).
    slim=False: expose all 21 tools (full mode for MCP-only users).
    """
    if slim:
        slim_mcp = FastMCP("writ")
        slim_mcp.tool()(writ_compose)
        slim_mcp.tool()(writ_chat_send_wait)
        slim_mcp.resource("writ://instructions/{name}")(instruction_resource)
        slim_mcp.resource("writ://project-context")(project_context_resource)
        slim_mcp.run(transport="stdio")
    else:
        mcp.run(transport="stdio")
