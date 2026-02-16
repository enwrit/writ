"""writ save/load/library -- Personal agent library management."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from writ.core import store
from writ.utils import console

# ---------------------------------------------------------------------------
# writ save
# ---------------------------------------------------------------------------

def save(
    name: Annotated[str, typer.Argument(help="Agent name to save to your personal library.")],
    alias: Annotated[
        str | None, typer.Option("--as", help="Save under a different name.")
    ] = None,
) -> None:
    """Save an agent from this project to your personal library (~/.writ/agents/).

    Your personal library lets you reuse agents across projects.
    Use 'writ load <name>' in any project to load it back.
    """
    if not store.is_initialized():
        console.print("[red]Not initialized.[/red] Run [cyan]writ init[/cyan] first.")
        raise typer.Exit(1)

    agent = store.load_agent(name)
    if not agent:
        console.print(f"[red]Agent '{name}' not found in this project.[/red]")
        raise typer.Exit(1)

    save_name = alias or name

    # Make the agent portable: ensure project_context will re-detect in new project
    agent.composition.project_context = True

    # Save to local library
    store.init_global_store()
    path = store.save_to_library(agent, alias=save_name)

    console.print(f"[green]Saved[/green] '{save_name}' to personal library ({path})")
    console.print(f"\n  Load in any project: [cyan]writ load {save_name}[/cyan]")


# ---------------------------------------------------------------------------
# writ load
# ---------------------------------------------------------------------------

def load(
    name: Annotated[str, typer.Argument(help="Agent name to load from your personal library.")],
) -> None:
    """Load an agent from your personal library into this project.

    Copies the agent config from ~/.writ/agents/ to .writ/agents/.
    """
    if not store.is_initialized():
        console.print("[red]Not initialized.[/red] Run [cyan]writ init[/cyan] first.")
        raise typer.Exit(1)

    agent = store.load_from_library(name)
    if not agent:
        console.print(f"[red]Agent '{name}' not found in your library.[/red]")
        console.print("Run [cyan]writ library[/cyan] to see available agents.")
        raise typer.Exit(1)

    # Check if already exists in project
    existing = store.load_agent(name)
    if existing:
        overwrite = typer.confirm(f"Agent '{name}' already exists in this project. Overwrite?")
        if not overwrite:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit()

    path = store.save_agent(agent)
    console.print(f"[green]Loaded[/green] '{name}' into project ({path})")
    console.print(f"\n  Activate: [cyan]writ use {name}[/cyan]")


# ---------------------------------------------------------------------------
# writ library
# ---------------------------------------------------------------------------

def library_list() -> None:
    """List all agents in your personal library (~/.writ/agents/)."""
    agents = store.list_library()

    if not agents:
        console.print("[yellow]Your personal library is empty.[/yellow]")
        console.print("Save agents with: [cyan]writ save <name>[/cyan]")
        return

    table = Table(title="Personal Agent Library", show_lines=False)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Description")
    table.add_column("Tags", style="dim")
    table.add_column("Version", justify="center")

    for agent in agents:
        table.add_row(
            agent.name,
            agent.description or "-",
            ", ".join(agent.tags) if agent.tags else "-",
            agent.version,
        )

    console.print(table)
    console.print(f"\n[dim]{len(agents)} agent(s) in library[/dim]")
    console.print("Load into a project: [cyan]writ load <name>[/cyan]")
