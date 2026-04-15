"""writ query -- return documentation index to stdout for agent navigation."""

from __future__ import annotations

from typing import Annotated

import typer

from writ.utils import console


def query_command(
    query: Annotated[
        str | None,
        typer.Argument(help="Search string to filter the documentation index."),
    ] = None,
) -> None:
    """Search the documentation index for agent navigation.

    Without a query, returns the full docs index. With a query string,
    filters to lines matching the query and shows relevant file paths
    the agent can read.

    \\b
    Examples:
      writ query                    # show full index
      writ query "frontend"         # filter index by keyword
      writ query "where is auth"    # find relevant docs
    """
    from writ.core import store

    cfg = store.load_instruction("writ-docs-index")
    if cfg is None:
        console.print(
            "[yellow]No documentation index found.[/yellow] "
            "Run [cyan]writ docs init[/cyan] to create one."
        )
        raise typer.Exit(1)

    content = cfg.instructions or ""

    if not query:
        console.print(content)
        return

    query_lower = query.lower()
    lines = content.splitlines()
    matched: list[str] = []
    file_paths: list[str] = []

    for line in lines:
        if query_lower in line.lower():
            matched.append(line)
            stripped = line.strip().lstrip("- ").strip("`")
            if "/" in stripped or "\\" in stripped or stripped.endswith((".md", ".mdc")):
                path = stripped.split(" ")[0].strip("`")
                if path and not path.startswith("#"):
                    file_paths.append(path)

    if not matched:
        console.print(
            f"[yellow]No matches for '{query}'.[/yellow] "
            "Showing full index.\n",
        )
        console.print(content)
        return

    console.print(f"[dim]Matches for '{query}':[/dim]\n")
    for line in matched:
        highlighted = line.replace(
            query, f"[bold yellow]{query}[/bold yellow]",
        )
        console.print(highlighted)

    if file_paths:
        console.print("\n[dim]Relevant files:[/dim]")
        for fp in dict.fromkeys(file_paths):
            console.print(f"  {fp}")
