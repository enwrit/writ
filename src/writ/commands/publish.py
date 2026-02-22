"""writ publish / unpublish -- Make agents publicly discoverable."""

from __future__ import annotations

from typing import Annotated

import typer

from writ.core import auth, store
from writ.utils import console


def _require_init() -> None:
    if not store.is_initialized():
        console.print(
            "[red]Not initialized.[/red] Run [cyan]writ init[/cyan] first."
        )
        raise typer.Exit(1)


def _require_login() -> None:
    if not auth.is_logged_in():
        console.print(
            "[red]Not logged in.[/red] "
            "Run [cyan]writ login[/cyan] to authenticate with enwrit.com."
        )
        raise typer.Exit(1)


def publish_command(
    name: Annotated[str, typer.Argument(help="Agent name to publish.")],
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt."),
    ] = False,
) -> None:
    """Publish an agent to enwrit.com (publicly discoverable).

    The agent will be searchable and installable by anyone.

    Examples:
        writ publish reviewer
        writ publish reviewer --yes
    """
    _require_init()
    _require_login()

    agent = store.load_agent(name)
    if not agent:
        console.print(
            f"[red]Agent '{name}' not found.[/red] "
            "Run [cyan]writ list[/cyan] to see available agents."
        )
        raise typer.Exit(1)

    if not yes:
        confirm = typer.confirm(
            f"Publish '{name}' to enwrit.com? "
            "It will be publicly visible."
        )
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)

    from writ.integrations.registry import RegistryClient

    client = RegistryClient()
    ok = client.push_to_library(name, agent, is_public=True)
    if ok:
        console.print(f"\n[green]Published '{name}' to enwrit.com[/green]\n")
        console.print(
            f"  Agent Card: [cyan]https://api.enwrit.com/agents/{name}/card[/cyan]"
        )
        console.print(
            f"  Browse:     [cyan]https://enwrit.com/agents/{name}[/cyan]"
        )
        console.print(
            f"  Install:    [cyan]writ install {name}[/cyan]"
        )
    else:
        console.print(
            f"[red]Failed to publish '{name}'.[/red] "
            "Check your connection and try again."
        )
        raise typer.Exit(1)


def unpublish_command(
    name: Annotated[str, typer.Argument(help="Agent name to unpublish.")],
) -> None:
    """Make a published agent private again.

    The agent remains in your personal library but is no longer
    publicly discoverable or searchable.

    Examples:
        writ unpublish reviewer
    """
    _require_init()
    _require_login()

    agent = store.load_agent(name)
    if not agent:
        console.print(
            f"[red]Agent '{name}' not found.[/red] "
            "Run [cyan]writ list[/cyan] to see available agents."
        )
        raise typer.Exit(1)

    from writ.integrations.registry import RegistryClient

    client = RegistryClient()
    ok = client.push_to_library(name, agent, is_public=False)
    if ok:
        console.print(
            f"[green]Agent '{name}' is now private.[/green] "
            "It remains in your personal library."
        )
    else:
        console.print(
            f"[red]Failed to unpublish '{name}'.[/red] "
            "Check your connection and try again."
        )
        raise typer.Exit(1)
