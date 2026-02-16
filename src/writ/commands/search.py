"""writ search -- Browse and discover agents from registries."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from writ.utils import console


def search_command(
    query: Annotated[str, typer.Argument(help="Search query (e.g. 'react typescript').")],
    source: Annotated[
        str | None,
        typer.Option(
            "--from", help="Search specific source: prpm, skills. Default: all.",
        ),
    ] = None,
    limit: Annotated[
        int, typer.Option("--limit", "-n", help="Max results to show."),
    ] = 20,
) -> None:
    """Search for agents across registries.

    Browse PRPM (7,500+ packages), Agent Skills CLI (175K+ skills),
    and our own registry (coming soon).

    Examples:
        writ search "react typescript"
        writ search "python fastapi" --from prpm
        writ search "code review" --from skills
    """
    results: list[dict] = []

    if source is None or source == "prpm":
        results.extend(_search_prpm(query, limit))

    if source is None or source == "skills":
        results.extend(_search_skills(query, limit))

    if not results:
        console.print(f"[yellow]No results found for '{query}'.[/yellow]")
        if source:
            console.print(f"[dim]Searched: {source}[/dim]")
        else:
            console.print("[dim]Searched: prpm, skills[/dim]")
        console.print(
            "\nTip: install directly if you know the package name:\n"
            "  [cyan]writ install <name> --from prpm[/cyan]"
        )
        return

    # Display results
    table = Table(
        title=f"Search results for '{query}'", show_lines=False,
    )
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Source", style="dim")
    table.add_column("Description")
    table.add_column("Tags", style="dim")

    for item in results[:limit]:
        table.add_row(
            item.get("name", "?"),
            item.get("source", "?"),
            item.get("description", "")[:60],
            ", ".join(item.get("tags", []))[:40],
        )

    console.print(table)
    console.print(f"\n[dim]{len(results)} result(s)[/dim]")
    console.print(
        "Install with: [cyan]writ install <name> --from <source>[/cyan]"
    )


def _search_prpm(query: str, limit: int) -> list[dict]:
    """Search PRPM registry."""
    try:
        from writ.integrations.prpm import PRPMIntegration
        prpm = PRPMIntegration()
        raw = prpm.search(query)
        return [
            {
                "name": r.get("name", "?"),
                "source": "prpm",
                "description": r.get("description", ""),
                "tags": r.get("tags", []),
            }
            for r in raw[:limit]
        ]
    except Exception:  # noqa: BLE001
        return []


def _search_skills(query: str, limit: int) -> list[dict]:
    """Search Agent Skills CLI."""
    try:
        from writ.integrations.skills import SkillsIntegration
        skills = SkillsIntegration()
        raw = skills.search(query)
        return [
            {
                "name": r.get("name", "?"),
                "source": "skills",
                "description": r.get("description", ""),
                "tags": r.get("tags", []),
            }
            for r in raw[:limit]
        ]
    except Exception:  # noqa: BLE001
        return []
