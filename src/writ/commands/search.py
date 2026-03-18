"""writ search -- Browse and discover agents from registries."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from writ.utils import console


def search_command(
    query: Annotated[
        str,
        typer.Argument(help="Search query (e.g. 'react typescript')."),
    ],
    source: Annotated[
        str | None,
        typer.Option(
            "--from",
            help="Search specific source: enwrit, prpm, skills. Default: all.",
        ),
    ] = None,
    limit: Annotated[
        int, typer.Option("--limit", "-n", help="Max results to show."),
    ] = 20,
) -> None:
    """Search for agents across registries.

    Searches the enwrit registry, PRPM (7,500+ packages),
    and Agent Skills CLI (175K+ skills).

    Examples:
        writ search "react typescript"
        writ search "python fastapi" --from enwrit
        writ search "code review" --from prpm
        writ search "linting" --limit 5
    """
    results: list[dict] = []
    searched: list[str] = []

    if source is None or source in ("enwrit", "registry"):
        results.extend(_search_registry(query, limit))
        searched.append("enwrit")

    if source is None or source == "prpm":
        results.extend(_search_prpm(query, limit))
        searched.append("prpm")

    if source is None or source == "skills":
        results.extend(_search_skills(query, limit))
        searched.append("skills")

    if not results:
        console.print(f"[yellow]No results found for '{query}'.[/yellow]")
        console.print(f"[dim]Searched: {', '.join(searched)}[/dim]")
        console.print(
            "\nTip: install directly if you know the package name:\n"
            "  [cyan]writ install <name>[/cyan]"
        )
        return

    table = Table(
        title=f"Search results for '{query}'", show_lines=False,
    )
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Source", style="dim")
    table.add_column("Score", justify="right")
    table.add_column("Description")
    table.add_column("Tags", style="dim")

    for item in results[:limit]:
        score = item.get("writ_score")
        if score is not None:
            if score >= 70:
                score_str = f"[green]{score}[/green]"
            elif score >= 50:
                score_str = f"[yellow]{score}[/yellow]"
            else:
                score_str = f"[red]{score}[/red]"
        else:
            score_str = "[dim]--[/dim]"
        table.add_row(
            item.get("name", "?"),
            item.get("source", "?"),
            score_str,
            item.get("description", "")[:60],
            ", ".join(item.get("tags", []))[:40],
        )

    console.print(table)
    console.print(f"\n[dim]{len(results)} result(s)[/dim]")
    console.print(
        "Install with: [cyan]writ install <name>[/cyan]"
    )


def _search_registry(query: str, limit: int) -> list[dict]:
    """Search the enwrit public registry."""
    try:
        from writ.integrations.registry import RegistryClient

        client = RegistryClient()
        raw = client.search(query, limit=limit)
        return [
            {
                "name": r.get("name", "?"),
                "source": "enwrit",
                "description": r.get("description", ""),
                "tags": r.get("tags", []),
                "writ_score": r.get("writ_score"),
            }
            for r in raw[:limit]
        ]
    except Exception:  # noqa: BLE001
        console.print("[dim]enwrit registry: unavailable[/dim]")
        return []


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
    except FileNotFoundError:
        console.print(
            "[dim]PRPM CLI not installed "
            "(https://github.com/AbanteAI/prpm)[/dim]"
        )
        return []
    except Exception:  # noqa: BLE001
        console.print("[dim]PRPM search failed[/dim]")
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
    except FileNotFoundError:
        console.print(
            "[dim]Agent Skills CLI not installed "
            "(https://github.com/CopilotKit/agent-skills-cli)[/dim]"
        )
        return []
    except Exception:  # noqa: BLE001
        console.print("[dim]Agent Skills search failed[/dim]")
        return []
