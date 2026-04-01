"""writ search -- Browse and discover instructions from registries."""

from __future__ import annotations

from typing import Annotated

import typer

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
    ] = 5,
) -> None:
    """Search for instructions across 6,000+ in the Hub.

    Uses semantic search to rank results by relevance and quality score.
    Falls back to keyword search when the Hub is unavailable.

    Examples:
        writ search "react typescript"
        writ search "code review" --limit 10
        writ search "python fastapi" --from enwrit
        writ search "linting" --from prpm
    """
    if source in ("prpm", "skills"):
        results = _search_legacy(query, source, limit)
    else:
        results = _search_hub(query, limit=limit, source=source)
        if not results:
            results = _search_legacy_all(query, limit)

    if not results:
        console.print(f"[yellow]No results found for '{query}'.[/yellow]")
        console.print(
            "\nTip: add directly if you know the name:\n"
            "  [cyan]writ add <name>[/cyan]"
        )
        return

    _display_results(query, results, limit)


def _search_hub(
    query: str,
    *,
    limit: int = 5,
    source: str | None = None,
) -> list[dict]:
    """Search via the unified Hub API (enwrit + PRPM, semantic ranking)."""
    try:
        from writ.integrations.registry import RegistryClient

        client = RegistryClient()
        return client.hub_search(
            query, limit=limit, source=source, semantic=True,
        )
    except Exception:  # noqa: BLE001
        return []


def _display_results(query: str, results: list[dict], limit: int) -> None:
    """Rich CLI output -- numbered results with score, description, and install command."""
    total = len(results)
    shown = results[:limit]

    console.print(
        f"\n  [bold]Search:[/bold] \"{query}\" "
        f"({len(shown)} of {total}+ results, ranked by relevance)\n"
    )

    for i, item in enumerate(shown, 1):
        name = item.get("name", "?")
        source = item.get("source", "")
        desc = item.get("description", "") or ""
        score = item.get("writ_score")

        score_str = _format_score(score)
        source_badge = f"[dim]\\[{source}][/dim]" if source else ""

        console.print(
            f"  [bold cyan]{i}[/bold cyan]  [cyan]{name:<40s}[/cyan] "
            f"Score: {score_str}  {source_badge}"
        )
        if desc:
            safe_desc = desc[:100].encode("ascii", errors="replace").decode("ascii")
            console.print(f"     {safe_desc}")

        add_cmd = f"writ add {name}"
        if source and source != "enwrit":
            add_cmd += f" --from {source}"
        console.print(f"     [dim]{add_cmd}[/dim]\n")


def _format_score(score: int | None) -> str:
    if score is None:
        return "[dim]--[/dim]"
    if score >= 70:
        return f"[green]{score}[/green]"
    if score >= 50:
        return f"[yellow]{score}[/yellow]"
    return f"[red]{score}[/red]"


# ---------------------------------------------------------------------------
# Legacy direct-API fallbacks (used when Hub is unavailable or --from prpm/skills)
# ---------------------------------------------------------------------------

def _search_legacy(query: str, source: str, limit: int) -> list[dict]:
    """Search a single legacy source directly."""
    if source == "prpm":
        return _search_prpm(query, limit)
    if source == "skills":
        return _search_skills(query, limit)
    return []


def _search_legacy_all(query: str, limit: int) -> list[dict]:
    """Fallback: query enwrit + PRPM + Skills individually."""
    results: list[dict] = []
    results.extend(_search_registry(query, limit))
    results.extend(_search_prpm(query, limit))
    results.extend(_search_skills(query, limit))
    return results[:limit]


def _search_registry(query: str, limit: int) -> list[dict]:
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
        return []


def _search_prpm(query: str, limit: int) -> list[dict]:
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
