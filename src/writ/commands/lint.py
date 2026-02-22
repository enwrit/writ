"""writ lint -- Validate agent config quality."""

from __future__ import annotations

from typing import Annotated

import typer

from writ.core import linter as lint_engine
from writ.core import store
from writ.utils import console

LEVEL_STYLES = {
    "error": "[bold red]ERROR[/bold red]",
    "warning": "[yellow]WARN[/yellow]",
    "info": "[dim]INFO[/dim]",
}


def lint_command(
    name: Annotated[
        str | None, typer.Argument(help="Agent name to lint (or omit to lint all).")
    ] = None,
) -> None:
    """Validate agent config quality.

    Checks for: instruction length, contradictions, missing descriptions,
    broken composition references, and more.

    Example:
        writ lint              # lint all agents
        writ lint reviewer     # lint a specific agent
    """
    if not store.is_initialized():
        console.print("[red]Not initialized.[/red] Run [cyan]writ init[/cyan] first.")
        raise typer.Exit(1)

    if name:
        agent = store.load_agent(name)
        if not agent:
            console.print(
                f"[red]Agent '{name}' not found.[/red] "
                "Run [cyan]writ list[/cyan] to see available agents."
            )
            raise typer.Exit(1)
        agents = [agent]
    else:
        agents = store.list_agents()
        if not agents:
            console.print("[yellow]No agents to lint.[/yellow]")
            return

    total_errors = 0
    total_warnings = 0

    for agent in agents:
        results = lint_engine.lint(agent)
        if not results:
            console.print(f"[green]  {agent.name}[/green] -- all checks passed")
            continue

        console.print(f"\n[bold]{agent.name}[/bold]:")
        for r in results:
            style = LEVEL_STYLES.get(r.level, r.level)
            rule_str = f" [{r.rule}]" if r.rule else ""
            console.print(f"  {style}{rule_str} {r.message}")
            if r.level == "error":
                total_errors += 1
            elif r.level == "warning":
                total_warnings += 1

    # Summary
    console.print()
    if total_errors:
        console.print(f"[bold red]{total_errors} error(s)[/bold red], {total_warnings} warning(s)")
    elif total_warnings:
        console.print(f"[yellow]{total_warnings} warning(s)[/yellow], no errors")
    else:
        console.print("[green]All checks passed![/green]")
