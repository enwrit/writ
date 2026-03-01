"""``writ peers`` -- manage connected peer repositories."""

from __future__ import annotations

import typer
from rich.table import Table

from writ.core import peers, store
from writ.core.models import AutoRespondTier
from writ.utils import console, error_console

peers_app = typer.Typer(
    name="peers",
    help="Manage connected peer repositories for agent-to-agent chat.",
    no_args_is_help=True,
)


def _require_init() -> None:
    if not store.is_initialized():
        error_console.print("[red]Project not initialized.[/red] Run [cyan]writ init[/cyan] first.")
        raise typer.Exit(1)


@peers_app.command(name="list")
def peers_list() -> None:
    """List all registered peer repositories."""
    _require_init()

    manifest = peers.load_peers()
    if not manifest.peers:
        console.print(
            "[dim]No peers registered.[/dim] "
            "Run [cyan]writ peers add[/cyan] to connect a repo."
        )
        return

    table = Table(title="Peer Repositories", border_style="cyan")
    table.add_column("Name", style="cyan")
    table.add_column("Path / Remote")
    table.add_column("Transport")
    table.add_column("Auto-respond")
    table.add_column("Max turns", justify="right")

    for name, peer in manifest.peers.items():
        location = peer.path or peer.remote or "?"
        table.add_row(
            name,
            location,
            peer.transport,
            peer.auto_respond.value,
            str(peer.max_turns),
        )

    console.print(table)


@peers_app.command(name="add")
def peers_add(
    name: str = typer.Argument(help="Short name for this peer (e.g. 'research-repo')."),
    path: str = typer.Option(None, "--path", "-p", help="Local filesystem path to the peer repo."),
    remote: str = typer.Option(None, "--remote", "-r", help="Remote API URL for the peer."),
    auto_respond: str = typer.Option("off", "--auto-respond", help="off, read_only, or full."),
    max_turns: int = typer.Option(10, "--max-turns", help="Safety limit per conversation."),
) -> None:
    """Register a new peer repository."""
    _require_init()

    if not path and not remote:
        error_console.print("[red]Provide --path (local) or --remote (API URL).[/red]")
        raise typer.Exit(1)

    try:
        tier = AutoRespondTier(auto_respond)
    except ValueError:
        error_console.print(
            f"[red]Invalid auto-respond tier: {auto_respond}[/red] "
            "(use off, read_only, or full)"
        )
        raise typer.Exit(1) from None

    peer = peers.add_peer(
        name, path=path, remote=remote, auto_respond=tier, max_turns=max_turns,
    )
    console.print(f"[green]Added peer[/green] [cyan]{name}[/cyan] ({peer.transport})")


@peers_app.command(name="remove")
def peers_remove(
    name: str = typer.Argument(help="Peer name to remove."),
) -> None:
    """Remove a peer repository."""
    _require_init()

    if peers.remove_peer(name):
        console.print(f"[green]Removed peer[/green] [cyan]{name}[/cyan]")
    else:
        error_console.print(f"[red]Peer '{name}' not found.[/red]")
        raise typer.Exit(1)
