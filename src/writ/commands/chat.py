"""``writ chat`` -- agent-to-agent conversations.

Start, read, send messages to, and manage conversations with peer repos.
Supports both local (filesystem) and remote (backend relay) transport.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from writ.core import messaging, peers, store
from writ.core.models import AutoRespondTier, Conversation, ConversationStatus, PeerConfig
from writ.utils import console, error_console

chat_app = typer.Typer(
    name="chat",
    help="Agent-to-agent conversations with peer repositories.",
    no_args_is_help=True,
)


def _require_init() -> None:
    if not store.is_initialized():
        error_console.print("[red]Project not initialized.[/red] Run [cyan]writ init[/cyan] first.")
        raise typer.Exit(1)


def _estimate_tokens(text: str) -> int:
    """Rough token estimator with a soft fallback for missing deps."""
    try:
        from writ.core.context_window import estimate_tokens
        return estimate_tokens(text)
    except Exception:  # noqa: BLE001
        return max(1, len(text) // 4)


def _pull_remote_messages(
    peer: PeerConfig, conv_path: Path, conv: Conversation,
) -> int:
    """Pull any new messages for a remote conversation from the backend relay.

    Appends only genuinely new messages (those not already in the local file)
    to the conversation file, refreshes ``_latest.md``, and returns the count
    of newly appended messages.  Returns 0 on network error, no new messages,
    unauthenticated user, or non-remote peers -- never raises.
    """
    if peer.transport != "remote":
        return 0

    from writ.core import auth
    if not auth.is_logged_in():
        return 0

    try:
        from writ.integrations.registry import RegistryClient
        client = RegistryClient()
        data = client.pull_conversation(
            conv.id, after_message=len(conv.messages),
        )
    except Exception:  # noqa: BLE001
        return 0

    if not data:
        return 0

    remote_msgs = data.get("messages") or []
    if not remote_msgs:
        return 0

    repo_name = Path.cwd().name
    existing_ids = {m.id for m in conv.messages}
    appended = 0
    for rm in remote_msgs:
        if not isinstance(rm, dict):
            continue
        mid = rm.get("id") or rm.get("message_id")
        if mid and mid in existing_ids:
            continue
        sender_agent = rm.get("agent_name") or rm.get("author_agent") or "agent"
        sender_repo = rm.get("repo_name") or rm.get("author_repo") or peer.name
        if sender_repo == repo_name:
            continue
        content = rm.get("content") or ""
        if not content:
            continue
        raw_attachments = rm.get("attachments") or []
        attach_blocks: list[str] = []
        for a in raw_attachments:
            if isinstance(a, str):
                attach_blocks.append(a)
            elif isinstance(a, dict):
                body = a.get("content") or ""
                path_hint = a.get("path") or a.get("name") or "attachment"
                attach_blocks.append(
                    f'<attached file="{path_hint}">\n{body}\n</attached>'
                )
        try:
            messaging.append_message(
                conv_path,
                agent=sender_agent,
                repo=sender_repo,
                content=content,
            )
            if attach_blocks:
                from writ.core.file_io import atomic_append
                atomic_append(conv_path, "\n".join(attach_blocks) + "\n")
        except Exception:  # noqa: BLE001
            continue
        appended += 1
    return appended


def _pull_all_remote(*, silent: bool = False) -> int:
    """Pull updates for every remote conversation. Returns total appended.

    Silent mode suppresses the dim warning printed on network failure, used
    by list/read commands where noise is undesirable.
    """
    total = 0
    try:
        manifest = peers.load_peers()
    except Exception:  # noqa: BLE001
        return 0
    remote_peer_names = {
        p.name for p in manifest.peers.values() if p.transport == "remote"
    }
    if not remote_peer_names:
        return 0

    for path, conv in messaging.list_conversations():
        peer_match: PeerConfig | None = None
        for participant in conv.participants:
            if participant.repo in remote_peer_names:
                peer_match = manifest.peers.get(participant.repo)
                break
            match = peers.find_peer(participant.repo)
            if match is not None and match.transport == "remote":
                peer_match = match
                break
        if peer_match is None:
            continue
        try:
            appended = _pull_remote_messages(peer_match, path, conv)
            total += appended
        except Exception:  # noqa: BLE001
            if not silent:
                console.print(
                    "[dim]Note: failed to pull remote updates for "
                    f"{conv.id}.[/dim]"
                )
            continue
    return total


def _sync_to_peer(peer: PeerConfig, conv_path: Path, conv: Conversation) -> None:  # noqa: F821
    """Copy conversation file to local peer, or relay through backend."""
    if peer.transport == "local":
        peer_conv_dir = peers.resolve_peer_conversations_dir(peer)
        if peer_conv_dir is not None:
            import shutil
            peer_conv_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(conv_path), str(peer_conv_dir / conv_path.name))
    elif peer.transport == "remote":
        from writ.core import auth
        if auth.is_logged_in():
            from writ.integrations.registry import RegistryClient
            client = RegistryClient()
            if conv.messages:
                last = conv.messages[-1]
                client.relay_message(
                    conv_id=conv.id,
                    agent_name=last.author_agent,
                    repo_name=last.author_repo,
                    content=last.content,
                    attachments=last.attachments,
                    goal=conv.goal,
                )


def _try_invoke_peer(
    peer: PeerConfig, conv_id: str, message: str, conv_path: Path,  # noqa: F821
) -> None:
    """Attempt to invoke the peer's agent so it can respond."""
    if peer.auto_respond == AutoRespondTier.OFF:
        return

    from writ.core.invoker import invoke_peer
    console.print("[dim]Invoking peer agent...[/dim]")

    result = invoke_peer(peer, message, timeout=300)

    if result.success and result.response:
        messaging.append_message(
            conv_path,
            agent=result.agent_name or "agent",
            repo=peer.name,
            content=result.response,
        )
        console.print(
            f"[green]Response from {peer.name}[/green] "
            f"(via {result.method}/{result.agent_name}):"
        )
        console.print(result.response[:500])
        if len(result.response) > 500:
            console.print("[dim]... (truncated)[/dim]")
    elif result.error:
        console.print(f"[yellow]Could not invoke peer:[/yellow] {result.error}")


# ---------------------------------------------------------------------------
# writ chat start
# ---------------------------------------------------------------------------

@chat_app.command(name="start")
def chat_start(
    with_repo: str = typer.Option(..., "--with", help="Peer repo name (from peers.yaml)."),
    goal: str = typer.Option("General discussion", "--goal", help="Goal for this conversation."),
    message: str = typer.Option("", "--message", "-m", help="Opening message (optional)."),
    invoke: bool = typer.Option(True, "--invoke/--no-invoke", help="Auto-invoke peer agent."),
) -> None:
    """Start a new conversation with a peer repository."""
    _require_init()

    peer = peers.get_peer(with_repo)
    if peer is None:
        error_console.print(
            f"[red]Peer '{with_repo}' not found.[/red] "
            "Run [cyan]writ peers add[/cyan] to register it."
        )
        raise typer.Exit(1)

    repo_name = Path.cwd().name
    conv = messaging.create_conversation(
        peer_repo=with_repo,
        goal=goal,
        local_agent="user",
        local_repo=repo_name,
    )

    conv_path = messaging.conversations_dir() / messaging._conv_filename(with_repo, goal)

    if message:
        messaging.append_message(
            conv_path,
            agent="user",
            repo=repo_name,
            content=message,
        )

    reloaded = messaging.load_conversation(conv_path)
    if reloaded:
        _sync_to_peer(peer, conv_path, reloaded)

    console.print(Panel(
        f"[bold]Conversation started[/bold]\n"
        f"ID: [cyan]{conv.id}[/cyan]\n"
        f"Peer: {with_repo}\n"
        f"Goal: {goal}",
        border_style="green",
    ))

    if message and invoke:
        _try_invoke_peer(peer, conv.id, message, conv_path)


# ---------------------------------------------------------------------------
# writ chat list
# ---------------------------------------------------------------------------

@chat_app.command(name="list")
def chat_list() -> None:
    """List all conversations."""
    _require_init()

    _pull_all_remote(silent=True)
    convs = messaging.list_conversations()
    if not convs:
        console.print("[dim]No conversations found.[/dim]")
        return

    table = Table(title="Conversations", border_style="cyan")
    table.add_column("ID", style="cyan")
    table.add_column("Peer")
    table.add_column("Goal")
    table.add_column("Status")
    table.add_column("Msgs", justify="right")

    for _, conv in convs:
        peer_name = conv.participants[1].repo if len(conv.participants) > 1 else "?"
        status_style = {
            ConversationStatus.ACTIVE: "green",
            ConversationStatus.WAITING: "yellow",
            ConversationStatus.COMPLETED: "dim",
            ConversationStatus.FAILED: "red",
            ConversationStatus.PAUSED: "yellow",
        }.get(conv.status, "")
        table.add_row(
            conv.id,
            peer_name,
            conv.goal[:50],
            f"[{status_style}]{conv.status.value}[/{status_style}]",
            str(len(conv.messages)),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# writ chat read
# ---------------------------------------------------------------------------

@chat_app.command(name="read")
def chat_read(
    conv_id: str = typer.Argument(help="Conversation ID."),
    last_n: int = typer.Option(0, "--last", "-n", help="Show only last N messages."),
) -> None:
    """Read a conversation's full history."""
    _require_init()

    result = messaging.find_conversation(conv_id)
    if result is None:
        error_console.print(f"[red]Conversation '{conv_id}' not found.[/red]")
        raise typer.Exit(1)

    path, conv = result
    peer_name = ""
    for p in conv.participants:
        if p.repo != Path.cwd().name:
            peer_name = p.repo
            break
    peer = peers.find_peer(peer_name) if peer_name else None
    if peer and peer.transport == "remote":
        try:
            appended = _pull_remote_messages(peer, path, conv)
            if appended:
                refreshed = messaging.load_conversation(path)
                if refreshed is not None:
                    conv = refreshed
        except Exception:  # noqa: BLE001
            console.print(
                "[dim]Note: failed to pull remote updates (showing local state).[/dim]"
            )
    text = path.read_text(encoding="utf-8")

    if last_n > 0 and conv.messages:
        console.print(f"[dim]Showing last {last_n} of {len(conv.messages)} messages[/dim]\n")
        for msg in conv.messages[-last_n:]:
            console.print(f"[bold cyan]{msg.author_agent}[/bold cyan] . {msg.author_repo} "
                          f"[dim]@ {messaging._fmt_ts(msg.timestamp)}[/dim]")
            console.print(msg.content)
            if msg.attachments:
                console.print(f"[dim]({len(msg.attachments)} attachment(s))[/dim]")
            console.print("---")
    else:
        console.print(text)


# ---------------------------------------------------------------------------
# writ chat send
# ---------------------------------------------------------------------------

def _get_git_diff(max_chars: int = 8000) -> str | None:
    """Get git diff output, truncated to max_chars."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "diff", "--stat", "--patch", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=str(Path.cwd()),
        )
        if result.returncode != 0 or not result.stdout.strip():
            result = subprocess.run(
                ["git", "diff", "--stat", "--patch"],
                capture_output=True, text=True, timeout=10,
                cwd=str(Path.cwd()),
            )
        diff = result.stdout.strip()
        if not diff:
            return None
        if len(diff) > max_chars:
            diff = diff[:max_chars] + f"\n\n... (truncated, {len(diff)} chars total)"
        return diff
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


@chat_app.command(name="send")
def chat_send(
    conv_id: str = typer.Argument(help="Conversation ID."),
    message: str = typer.Argument(help="Message text."),
    with_diff: bool = typer.Option(
        False, "--with-diff",
        help="Attach git diff to the message (auto-truncated at 8KB).",
    ),
    files: Annotated[
        list[Path] | None,
        typer.Option("--file", "-f", help="Attach file(s) to the message."),
    ] = None,
    invoke: bool = typer.Option(True, "--invoke/--no-invoke", help="Auto-invoke peer agent."),
    force: bool = typer.Option(
        False, "--force",
        help="Bypass peer max_context_tokens limit and send as-is.",
    ),
    truncate: bool = typer.Option(
        False, "--truncate",
        help="Truncate the message at the peer's max_context_tokens limit.",
    ),
) -> None:
    """Send a message in an existing conversation."""
    _require_init()

    result = messaging.find_conversation(conv_id)
    if result is None:
        error_console.print(f"[red]Conversation '{conv_id}' not found.[/red]")
        raise typer.Exit(1)

    path, conv = result
    repo_name = Path.cwd().name

    full_message = message
    if with_diff:
        diff = _get_git_diff()
        if diff:
            full_message = (
                f"{message}\n\n"
                "## Recent Changes (git diff)\n\n"
                f"```diff\n{diff}\n```"
            )
            console.print(f"[dim]Attached diff ({len(diff)} chars)[/dim]")
        else:
            console.print("[dim]No diff found (clean working tree)[/dim]")

    peer_name_for_limits = ""
    for p in conv.participants:
        if p.repo != repo_name:
            peer_name_for_limits = p.repo
            break
    peer_cfg = peers.find_peer(peer_name_for_limits) if peer_name_for_limits else None

    if peer_cfg is not None:
        turn_count = len(conv.messages)
        max_turns = getattr(peer_cfg, "max_turns", 50) or 50
        if turn_count >= max_turns:
            error_console.print(
                f"[red]Conversation capacity reached[/red] "
                f"({turn_count}/{max_turns} turns). "
                f"Start a new chat with "
                f"[cyan]writ chat start --with {peer_name_for_limits}[/cyan] "
                f"or raise [cyan]max_turns[/cyan] in peers.yaml."
            )
            raise typer.Exit(1)

        max_tokens = getattr(peer_cfg, "max_context_tokens", 200_000) or 200_000
        outgoing = full_message
        if files:
            for fp in files:
                try:
                    outgoing += "\n" + Path(fp).read_text(
                        encoding="utf-8", errors="replace",
                    )
                except OSError:
                    continue
        estimated = _estimate_tokens(outgoing)
        if estimated > max_tokens:
            if truncate:
                budget_chars = max_tokens * 4
                marker = f"\n\n[... truncated ~{estimated - max_tokens} tokens ...]"
                full_message = full_message[: budget_chars - len(marker)] + marker
                console.print(
                    f"[yellow]Truncated message "
                    f"from ~{estimated} to ~{max_tokens} tokens[/yellow]"
                )
            elif not force:
                error_console.print(
                    f"[yellow]Message size ~{estimated} tokens exceeds "
                    f"peer limit of {max_tokens}.[/yellow] "
                    f"Use [cyan]--truncate[/cyan] to auto-trim or "
                    f"[cyan]--force[/cyan] to send as-is."
                )
                raise typer.Exit(1)

    attach = [str(f) for f in files] if files else None
    msg = messaging.append_message(
        path,
        agent="user",
        repo=repo_name,
        content=full_message,
        attach_files=attach,
    )
    console.print(f"[green]Sent[/green] {msg.id} in {conv.id}")
    if files:
        console.print(f"[dim]Attached {len(files)} file(s)[/dim]")

    peer = peer_cfg

    if peer:
        reloaded = messaging.load_conversation(path)
        if reloaded:
            _sync_to_peer(peer, path, reloaded)
        if invoke:
            _try_invoke_peer(peer, conv.id, message, path)


# ---------------------------------------------------------------------------
# writ chat end
# ---------------------------------------------------------------------------

@chat_app.command(name="end")
def chat_end(
    conv_id: str = typer.Argument(help="Conversation ID."),
    summary: str = typer.Option("", "--summary", "-s", help="Outcome summary."),
) -> None:
    """Mark a conversation as completed."""
    _require_init()

    result = messaging.find_conversation(conv_id)
    if result is None:
        error_console.print(f"[red]Conversation '{conv_id}' not found.[/red]")
        raise typer.Exit(1)

    path, _ = result
    messaging.complete_conversation(path, summary or "Conversation ended.")
    console.print(f"[green]Completed[/green] {conv_id}")


# ---------------------------------------------------------------------------
# writ chat resume
# ---------------------------------------------------------------------------

@chat_app.command(name="resume")
def chat_resume(
    conv_id: str = typer.Argument(help="Conversation ID."),
) -> None:
    """Resume a paused conversation (resets the turn counter)."""
    _require_init()

    result = messaging.find_conversation(conv_id)
    if result is None:
        error_console.print(f"[red]Conversation '{conv_id}' not found.[/red]")
        raise typer.Exit(1)

    path, conv = result
    peer_name = ""
    for p in conv.participants:
        if p.repo != Path.cwd().name:
            peer_name = p.repo
            break
    peer = peers.find_peer(peer_name) if peer_name else None
    if peer and peer.transport == "remote":
        try:
            _pull_remote_messages(peer, path, conv)
        except Exception:  # noqa: BLE001
            pass
    if conv.status != ConversationStatus.PAUSED:
        error_console.print(f"[yellow]Conversation is {conv.status.value}, not paused.[/yellow]")
        raise typer.Exit(1)

    messaging.update_status(path, ConversationStatus.ACTIVE)
    console.print(f"[green]Resumed[/green] {conv_id}")


# ---------------------------------------------------------------------------
# writ chat gc
# ---------------------------------------------------------------------------

@chat_app.command(name="gc")
def chat_gc() -> None:
    """Garbage-collect completed and stale conversations."""
    _require_init()

    removed = 0
    for path, conv in messaging.list_conversations():
        if conv.status in (ConversationStatus.COMPLETED, ConversationStatus.FAILED):
            path.unlink(missing_ok=True)
            lock = path.with_suffix(path.suffix + ".lock")
            lock.unlink(missing_ok=True)
            removed += 1

    console.print(f"[green]Removed {removed} completed/failed conversation(s).[/green]")


# ---------------------------------------------------------------------------
# writ inbox  (alias -- shows only conversations with unread messages)
# ---------------------------------------------------------------------------

def inbox_command() -> None:
    """Show conversations with unread messages."""
    if not store.is_initialized():
        error_console.print("[red]Project not initialized.[/red]")
        raise typer.Exit(1)

    _pull_all_remote(silent=True)

    repo_name = Path.cwd().name
    unread: list[tuple[str, str, str, str]] = []

    for _, conv in messaging.list_conversations():
        if conv.status in (ConversationStatus.COMPLETED, ConversationStatus.FAILED):
            continue
        if not conv.messages:
            continue
        last = conv.messages[-1]
        if last.author_repo != repo_name:
            unread.append((
                conv.id,
                last.author_repo,
                conv.goal[:50],
                last.content[:80],
            ))

    if not unread:
        console.print("[dim]No unread messages.[/dim]")
        return

    table = Table(title="Inbox", border_style="cyan")
    table.add_column("Conv ID", style="cyan")
    table.add_column("From")
    table.add_column("Goal")
    table.add_column("Preview")

    for cid, peer, goal, preview in unread:
        table.add_row(cid, peer, goal, preview)

    console.print(table)
