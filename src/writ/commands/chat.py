"""``writ chat`` -- agent-to-agent conversations.

Start, read, send messages to, and manage conversations with peer repos.
Supports both local (filesystem) and remote (backend relay) transport.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from writ.core import messaging, peers, store
from writ.core.models import AutoRespondTier, ConversationStatus
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
    goal: str = typer.Option(..., "--goal", help="Goal for this conversation."),
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

@chat_app.command(name="send")
def chat_send(
    conv_id: str = typer.Argument(help="Conversation ID."),
    message: str = typer.Argument(help="Message text."),
    invoke: bool = typer.Option(True, "--invoke/--no-invoke", help="Auto-invoke peer agent."),
) -> None:
    """Send a message in an existing conversation."""
    _require_init()

    result = messaging.find_conversation(conv_id)
    if result is None:
        error_console.print(f"[red]Conversation '{conv_id}' not found.[/red]")
        raise typer.Exit(1)

    path, conv = result
    repo_name = Path.cwd().name

    msg = messaging.append_message(
        path, agent="user", repo=repo_name, content=message,
    )
    console.print(f"[green]Sent[/green] {msg.id} in {conv.id}")

    peer_name = ""
    for p in conv.participants:
        if p.repo != repo_name:
            peer_name = p.repo
            break
    peer = peers.find_peer(peer_name) if peer_name else None

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
