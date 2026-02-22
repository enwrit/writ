"""writ CLI -- Agent instruction management.

Entry point for the `writ` command. Registers all subcommands.
"""

from __future__ import annotations

import typer

from writ import __version__
from writ.commands import (
    agent,
    compose,
    export,
    handoff,
    init,
    install,
    library,
    lint,
    login,
    memory,
    publish,
    search,
)
from writ.utils import console

# ---------------------------------------------------------------------------
# Top-level Typer app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="writ",
    help="Agent instruction management CLI -- compose, port, and score AI agent configs.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
)


# ---------------------------------------------------------------------------
# Register command groups
# ---------------------------------------------------------------------------

# Direct commands (no sub-group)
app.command(name="init")(init.init_command)
app.command(name="add")(agent.add)
app.command(name="list")(agent.list_agents)
app.command(name="use")(agent.use)
app.command(name="edit")(agent.edit)
app.command(name="remove")(agent.remove)
app.command(name="export")(export.export_command)
app.command(name="compose")(compose.compose_command)

# Library commands (save/load/library)
app.command(name="save")(library.save)
app.command(name="load")(library.load)
app.command(name="library")(library.library_list)

# Auth commands (login/logout)
app.command(name="login")(login.login)
app.command(name="logout")(login.logout)

# Lint command
app.command(name="lint")(lint.lint_command)

# Install + Search commands
app.command(name="install")(install.install_command)
app.command(name="search")(search.search_command)

# Publish commands
app.command(name="publish")(publish.publish_command)
app.command(name="unpublish")(publish.unpublish_command)

# Memory sub-group
memory_app = typer.Typer(
    name="memory",
    help="Cross-project memory sharing.",
    no_args_is_help=True,
)
memory_app.command(name="export")(memory.export_memory)
memory_app.command(name="import")(memory.import_memory)
memory_app.command(name="list")(memory.list_memory)
app.add_typer(memory_app, name="memory")

# Handoff sub-group
handoff_app = typer.Typer(
    name="handoff",
    help="Context handoffs between agents.",
    no_args_is_help=True,
)
handoff_app.command(name="create")(handoff.create)
handoff_app.command(name="list")(handoff.list_handoffs)
app.add_typer(handoff_app, name="handoff")


# ---------------------------------------------------------------------------
# Standalone commands (version, status)
# ---------------------------------------------------------------------------

@app.command(name="version")
def version_command() -> None:
    """Show writ version and environment info."""
    import sys

    from rich.panel import Panel

    console.print(Panel(
        f"[bold]writ[/bold] {__version__}\n"
        f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}\n"
        f"Platform: {sys.platform}",
        title="writ",
        border_style="cyan",
    ))


@app.command(name="status")
def status_command() -> None:
    """Show project status, diagnostics, and connectivity."""
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
        agents = store.list_agents()
        table.add_row("Agents in project", str(len(agents)))
        config = store.load_config()
        table.add_row("Active formats", ", ".join(config.formats))

    logged_in = auth.is_logged_in()
    table.add_row("Logged in", "[green]yes[/green]" if logged_in else "[dim]no[/dim]")

    global_agents = store.list_library()
    table.add_row("Library agents", str(len(global_agents)))

    backend_status = _check_backend()
    table.add_row("Backend (api.enwrit.com)", backend_status)

    console.print(Panel(table, title="writ status", border_style="cyan"))


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


# ---------------------------------------------------------------------------
# Version callback
# ---------------------------------------------------------------------------

@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit."),
) -> None:
    """writ -- Agent instruction management CLI."""
    if version:
        from rich.console import Console
        Console().print(f"writ {__version__}")
        raise typer.Exit()
