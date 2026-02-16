"""writ export -- Export an agent to a specific format."""

from __future__ import annotations

from typing import Annotated

import typer

from writ.core import composer, store
from writ.core.formatter import ALL_FORMAT_NAMES, get_formatter
from writ.utils import console


def export_command(
    name: Annotated[str, typer.Argument(help="Agent name to export.")],
    format: Annotated[str, typer.Argument(help=f"Target format ({', '.join(ALL_FORMAT_NAMES)}).")],
    with_agents: Annotated[
        list[str] | None, typer.Option("--with", help="Additional agents to compose with.")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print output instead of writing to file.")
    ] = False,
) -> None:
    """Export an agent to a specific IDE/CLI format.

    Example: writ export architect cursor
    Example: writ export reviewer claude --with architect
    """
    if not store.is_initialized():
        console.print("[red]Not initialized.[/red] Run [cyan]writ init[/cyan] first.")
        raise typer.Exit(1)

    agent = store.load_agent(name)
    if not agent:
        console.print(f"[red]Agent '{name}' not found.[/red]")
        raise typer.Exit(1)

    # Validate format
    if format not in ALL_FORMAT_NAMES:
        console.print(f"[red]Unknown format '{format}'.[/red] Valid: {', '.join(ALL_FORMAT_NAMES)}")
        raise typer.Exit(1)

    # Compose context
    composed = composer.compose(agent, additional=with_agents or [])

    if dry_run:
        console.print(f"\n[bold]Composed output for '{name}' -> {format}:[/bold]\n")
        console.print(composed)
        return

    # Write to format
    try:
        formatter = get_formatter(format)
        path = formatter.write(agent, composed)
        console.print(f"[green]Exported[/green] '{name}' -> {format} ({path})")
    except KeyError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None
