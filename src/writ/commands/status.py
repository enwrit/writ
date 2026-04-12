"""writ status -- project status with knowledge health and recent activity."""

from __future__ import annotations

from pathlib import Path

import typer

from writ.utils import console


def status_command(
    show_all: bool = typer.Option(False, "--all", "-a", help="Show full log history."),
) -> None:
    """Show project status, health score, and recent activity.

    Combines connectivity diagnostics with documentation health score
    and recent entries from the knowledge log.

    \\b
    Examples:
      writ status
      writ status --all
    """
    from rich.panel import Panel
    from rich.table import Table

    from writ.core import auth, store

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value")

    initialized = store.is_initialized()
    if initialized:
        init_val = "[green]yes[/green]"
    else:
        init_val = "[red]no[/red]  (run [cyan]writ init[/cyan])"
    table.add_row("Project initialized", init_val)

    if initialized:
        instructions = store.list_instructions()
        table.add_row("Instructions in project", str(len(instructions)))
        config = store.load_config()
        table.add_row("Active formats", ", ".join(config.formats))

    logged_in = auth.is_logged_in()
    table.add_row("Logged in", "[green]yes[/green]" if logged_in else "[dim]no[/dim]")

    lib_items = store.list_library()
    table.add_row("Library instructions", str(len(lib_items)))

    if initialized:
        health_str = _quick_health()
        table.add_row("Documentation health", health_str)

    backend_status = _check_backend()
    table.add_row("Backend (api.enwrit.com)", backend_status)

    console.print(Panel(table, title="writ status", border_style="cyan"))

    if initialized:
        _show_recent_log(show_all=show_all)


def _quick_health() -> str:
    """Run a quick health check and return a formatted score string."""
    try:
        from writ.core.doc_health import run_health_check

        report = run_health_check(Path.cwd())
        score = report.health_score
        if score >= 80:
            return f"[green]{score}/100[/green]"
        if score >= 50:
            return f"[yellow]{score}/100[/yellow]"
        return f"[red]{score}/100[/red]"
    except Exception:  # noqa: BLE001
        return "[dim]unavailable[/dim]"


def _show_recent_log(*, show_all: bool = False) -> None:
    """Display recent entries from the writ-log instruction."""
    from writ.core import store

    cfg = store.load_instruction("writ-log")
    if cfg is None or not cfg.instructions:
        return

    text = cfg.instructions

    entries = [line for line in text.splitlines() if line.startswith("- [")]
    if not entries:
        return

    if not show_all:
        entries = entries[-10:]

    console.print()
    console.print("[bold]Recent activity:[/bold]")
    for entry in entries:
        console.print(f"  {entry}")


def _check_backend() -> str:
    """Quick health check against the backend."""
    try:
        import httpx

        resp = httpx.get("https://api.enwrit.com/health", timeout=5.0)
        if resp.status_code == 200:
            return "[green]reachable[/green]"
        return f"[yellow]HTTP {resp.status_code}[/yellow]"
    except Exception:  # noqa: BLE001
        return "[red]unreachable[/red]"
