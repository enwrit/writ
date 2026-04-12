"""writ query -- return documentation index to stdout for agent navigation."""

from __future__ import annotations

from typing import Annotated

import typer

from writ.utils import console


def query_command(
    query: Annotated[
        str | None,
        typer.Argument(help="Search query (reserved for future filtering)."),
    ] = None,
) -> None:
    """Show the documentation index for agent navigation.

    Returns the full contents of writ-docs-index to stdout. Agents use
    this to understand what documentation exists and where it lives.

    \\b
    Examples:
      writ query
      writ query "architecture"
    """
    from writ.core import store

    cfg = store.load_instruction("writ-docs-index")
    if cfg is None:
        console.print(
            "[yellow]No documentation index found.[/yellow] "
            "Run [cyan]writ docs init[/cyan] to create one."
        )
        raise typer.Exit(1)

    if query:
        console.print(f"[dim]Filtering by '{query}' coming soon -- showing full index.[/dim]")
        console.print()

    console.print(cfg.instructions)
