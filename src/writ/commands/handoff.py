"""writ handoff -- Context handoffs between agents."""

from __future__ import annotations

from datetime import date
from typing import Annotated

import typer
from rich.table import Table

from writ.core import store
from writ.utils import console, project_writ_dir

# ---------------------------------------------------------------------------
# writ handoff create
# ---------------------------------------------------------------------------

def create(
    from_agent: Annotated[str, typer.Argument(help="Source agent name.")],
    to_agent: Annotated[str, typer.Argument(help="Target agent name.")],
    summary: Annotated[
        str | None, typer.Option("--summary", "-s", help="Handoff summary content.")
    ] = None,
    file: Annotated[
        str | None, typer.Option("--file", "-f", help="Read handoff content from file.")
    ] = None,
) -> None:
    """Create a context handoff from one agent to another.

    The handoff summary becomes part of the target agent's composed context (Layer 4).

    Examples:
        writ handoff create renderer physics --summary "Renderer done. API: ..."
        writ handoff create architect implementer --file handoff-notes.md
    """
    if not store.is_initialized():
        console.print("[red]Not initialized.[/red] Run [cyan]writ init[/cyan] first.")
        raise typer.Exit(1)

    # Validate agents exist
    if not store.load_instruction(from_agent):
        console.print(f"[red]Source agent '{from_agent}' not found.[/red]")
        raise typer.Exit(1)
    if not store.load_instruction(to_agent):
        console.print(f"[red]Target agent '{to_agent}' not found.[/red]")
        raise typer.Exit(1)

    # Get content
    if file:
        from pathlib import Path
        file_path = Path(file)
        if not file_path.exists():
            console.print(f"[red]File not found:[/red] {file}")
            raise typer.Exit(1)
        content = file_path.read_text(encoding="utf-8")
    elif summary:
        content = summary
    else:
        console.print("[red]Provide --summary or --file for handoff content.[/red]")
        raise typer.Exit(1)

    # Add metadata
    header = f"# Handoff: {from_agent} -> {to_agent}\n\n*Date: {date.today()}*\n\n"
    store.save_handoff(from_agent, to_agent, header + content)

    console.print(f"[green]Created[/green] handoff: {from_agent} -> {to_agent}")
    console.print(f"\n  This will be included when you run: [cyan]writ use {to_agent}[/cyan]")


# ---------------------------------------------------------------------------
# writ handoff list
# ---------------------------------------------------------------------------

def list_handoffs() -> None:
    """List all handoffs in this project."""
    if not store.is_initialized():
        console.print("[red]Not initialized.[/red] Run [cyan]writ init[/cyan] first.")
        raise typer.Exit(1)

    handoffs_dir = project_writ_dir() / "handoffs"
    if not handoffs_dir.exists() or not list(handoffs_dir.glob("*.md")):
        console.print("[yellow]No handoffs found.[/yellow]")
        console.print("Create one: [cyan]writ handoff create <from> <to> --summary '...'[/cyan]")
        return

    table = Table(title="Context Handoffs", show_lines=False)
    table.add_column("From", style="cyan", no_wrap=True)
    table.add_column("To", style="cyan", no_wrap=True)
    table.add_column("File", style="dim")

    for path in sorted(handoffs_dir.glob("*.md")):
        # Parse filename: from-to-to.md
        parts = path.stem.split("-to-", 1)
        if len(parts) == 2:
            table.add_row(parts[0], parts[1], path.name)
        else:
            table.add_row("-", "-", path.name)

    console.print(table)
