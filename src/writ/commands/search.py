"""writ search -- Browse and discover instructions from registries."""

from __future__ import annotations

from typing import Annotated

import typer

from writ.utils import console


def _apply_search_filters(
    results: list[dict],
    *,
    min_score: int | None,
    task_type: str | None,
) -> list[dict]:
    """Drop items below min_score or mismatched task_type (client-side)."""
    if min_score is not None:
        results = [r for r in results if (r.get("writ_score") or 0) >= min_score]
    if task_type is not None:
        results = [r for r in results if r.get("task_type") == task_type]
    return results


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
    min_score: Annotated[
        int | None,
        typer.Option("--min-score", help="Minimum quality score (0-100)."),
    ] = None,
    task_type: Annotated[
        str | None,
        typer.Option(
            "--type",
            help="Filter by type: agent, rule, program, skill, context.",
        ),
    ] = None,
) -> None:
    """Search for instructions across 6,000+ in the Hub.

    Uses semantic search to rank results by relevance and quality score.
    Falls back to keyword search when the Hub is unavailable.

    Examples:
        writ search "react typescript"
        writ search "code review" --limit 10
        writ search "python fastapi" --from enwrit
        writ search "linting" --from prpm
        writ search "typescript" --min-score 70
        writ search "api design" --type agent
    """
    if source in ("prpm", "skills"):
        results = _search_legacy(
            query, source, limit, min_score=min_score, task_type=task_type,
        )
    else:
        results = _search_hub(
            query, limit=limit, source=source, task_type=task_type,
        )
        if not results:
            results = _search_legacy_all(
                query, limit, min_score=min_score, task_type=task_type,
            )
        else:
            results = _apply_search_filters(
                results, min_score=min_score, task_type=task_type,
            )

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
    task_type: str | None = None,
) -> list[dict]:
    """Search via the unified Hub API (enwrit + PRPM, semantic ranking)."""
    try:
        from writ.integrations.registry import RegistryClient

        client = RegistryClient()
        return client.hub_search(
            query,
            limit=limit,
            source=source,
            task_type=task_type,
            semantic=True,
        )
    except Exception:  # noqa: BLE001
        return []


def _display_results(query: str, results: list[dict], limit: int) -> None:
    """Rich CLI output -- numbered results with score, description, and install command."""
    shown = results[:limit]
    hub_total = None
    if results:
        hub_total = results[0].get("_hub_total")
    total_str = str(hub_total) if hub_total is not None else f"{len(results)}+"

    console.print(
        f"\n  [bold]Search:[/bold] \"{query}\" "
        f"({len(shown)} of {total_str} results, ranked by relevance)\n"
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

        if source and source != "enwrit":
            console.print(
                f"     [dim]writ add {name}[/dim]"
                f"  [dim](from Hub)[/dim]"
            )
            console.print(
                f"     [dim]writ add {name}"
                f" --from {source}[/dim]"
                f"  [dim](latest from {source})[/dim]\n"
            )
        else:
            console.print(f"     [dim]writ add {name}[/dim]\n")


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

def _search_legacy(
    query: str,
    source: str,
    limit: int,
    *,
    min_score: int | None = None,
    task_type: str | None = None,
) -> list[dict]:
    """Search a single legacy source directly."""
    if source == "prpm":
        raw = _search_prpm(query, limit)
    elif source == "skills":
        raw = _search_skills(query, limit)
    else:
        raw = []
    return _apply_search_filters(
        raw, min_score=min_score, task_type=task_type,
    )[:limit]


def _search_legacy_all(
    query: str,
    limit: int,
    *,
    min_score: int | None = None,
    task_type: str | None = None,
) -> list[dict]:
    """Fallback: query enwrit + PRPM + Skills individually."""
    results: list[dict] = []
    results.extend(_search_registry(query, limit))
    results.extend(_search_prpm(query, limit))
    results.extend(_search_skills(query, limit))
    filtered = _apply_search_filters(
        results, min_score=min_score, task_type=task_type,
    )
    return filtered[:limit]


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
                "task_type": r.get("task_type"),
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
                "writ_score": r.get("writ_score"),
                "task_type": r.get("task_type"),
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
                "writ_score": r.get("writ_score"),
                "task_type": r.get("task_type"),
            }
            for r in raw[:limit]
        ]
    except Exception:  # noqa: BLE001
        return []
