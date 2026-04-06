"""writ docs check -- project documentation health diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from writ.utils import console

docs_app = typer.Typer(
    name="docs",
    help="Documentation health diagnostics.",
    no_args_is_help=True,
)


@docs_app.command(name="check")
def check_command(
    path: Annotated[
        str | None,
        typer.Argument(help="Project root path (defaults to current directory)."),
    ] = None,
    output_json: Annotated[
        bool,
        typer.Option("--json", help="Output raw JSON (for agents/scripts)."),
    ] = False,
) -> None:
    """Check documentation health across the project.

    Scans instruction files, rules, README, AGENTS.md, and other documentation
    that affects AI agent behavior. Detects dead file references, treeview
    drift, stale instructions, and contradictions.

    \b
    Examples:
      writ docs check
      writ docs check --json
      writ docs check /path/to/repo
    """
    from writ.core.doc_health import run_health_check

    root = Path(path) if path else Path.cwd()
    if not root.is_dir():
        console.print(f"[red]Not a directory:[/red] {root}")
        raise typer.Exit(1)

    report = run_health_check(root)

    if output_json:
        import json

        data = {
            "health_score": report.health_score,
            "total_issues": report.total_issues,
            "files": [
                {
                    "path": f.path,
                    "freshness": f.freshness,
                    "lint_score": f.lint_score,
                    "issues": [
                        {"kind": i.kind, "message": i.message, "severity": i.severity}
                        for i in f.issues
                    ],
                }
                for f in report.files
            ],
        }
        console.print_json(json.dumps(data))
        return

    _display_report(report)


def _display_report(report) -> None:  # type: ignore[type-arg]
    """Display the health report with Rich formatting."""
    from rich.panel import Panel
    from rich.table import Table

    if not report.files:
        console.print(
            "[dim]No documentation files found.[/dim]\n"
            "Run [cyan]writ init[/cyan] to set up your project.",
        )
        return

    score = report.health_score
    if score >= 80:
        score_style = "green"
    elif score >= 50:
        score_style = "yellow"
    else:
        score_style = "red"

    console.print(Panel(
        f"[{score_style} bold]Project Documentation Health: {score}/100[/{score_style} bold]",
        border_style=score_style,
    ))

    table = Table(show_header=True, header_style="bold")
    table.add_column("File", min_width=35)
    table.add_column("Freshness", justify="center", min_width=10)
    table.add_column("Issues", min_width=40)

    for f in report.files:
        freshness_display = _freshness_label(f.freshness, f.last_commit_ago)

        if f.issues:
            issue_lines = []
            for issue in f.issues[:3]:
                issue_lines.append(issue.message)
            if len(f.issues) > 3:
                issue_lines.append(f"... +{len(f.issues) - 3} more")
            issues_text = "\n".join(issue_lines)
        else:
            issues_text = "[dim]-[/dim]"

        table.add_row(f.path, freshness_display, issues_text)

    console.print(table)

    files_needing_attention = sum(
        1 for f in report.files
        if f.issues or f.freshness in ("stale", "STALE")
    )
    if files_needing_attention > 0:
        console.print(
            f"\n[bold]{files_needing_attention} file(s) need attention.[/bold] "
            "Run your IDE agent with these findings to update them.",
        )
    else:
        console.print("\n[green]All documentation files look healthy.[/green]")


def _freshness_label(freshness: str, commits_ago: int | None) -> str:
    """Format freshness label with color."""
    if freshness == "STALE":
        suffix = f" ({commits_ago} commits ago)" if commits_ago else ""
        return f"[red bold]STALE[/red bold]{suffix}"
    if freshness == "stale":
        suffix = f" ({commits_ago} commits ago)" if commits_ago else ""
        return f"[yellow]stale[/yellow]{suffix}"
    if freshness == "fresh":
        return "[green]fresh[/green]"
    return "[dim]unknown[/dim]"
