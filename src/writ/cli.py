"""writ CLI -- AI instruction management.

Entry point for the `writ` command. Registers all subcommands.
"""

from __future__ import annotations

import typer

from writ import __version__
from writ.commands import (
    agent,
    approvals,
    diff,
    handoff,
    init,
    knowledge,
    library,
    lint,
    login,
    memory,
    publish,
    register,
    search,
    sync,
    upgrade,
)
from writ.commands.chat import chat_app, inbox_command
from writ.commands.connect import connect_command
from writ.commands.docs import docs_app
from writ.commands.hook import hook_app
from writ.commands.mcp import mcp_app
from writ.commands.model import model_app
from writ.commands.peers_cmd import peers_app
from writ.commands.plan import plan_app
from writ.commands.query import query_command
from writ.commands.status import status_command as _status_command
from writ.utils import console

# ---------------------------------------------------------------------------
# Top-level Typer app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="writ",
    help="AI instruction management CLI -- find, install, route, and score instructions.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
)


# ---------------------------------------------------------------------------
# Register command groups (rich_help_panel for --help visual grouping)
# ---------------------------------------------------------------------------

_CORE = "Core"
_QUALITY = "Quality"
_DISCOVERY = "Discovery"
_COMMUNICATION = "Communication"
_SYNC_AUTH = "Sync & Auth"
_ADVANCED = "Advanced"

# -- Core -------------------------------------------------------------------
app.command(name="init", rich_help_panel=_CORE)(init.init_command)
app.command(name="add", rich_help_panel=_CORE)(agent.add)
app.command(name="list", rich_help_panel=_CORE)(agent.list_agents)
app.command(name="remove", rich_help_panel=_CORE)(agent.remove)
app.command(name="save", rich_help_panel=_CORE)(library.save)

# LEGACY alias: `writ install` -> `writ add`
app.command(name="install", hidden=True)(agent.add)

# -- Quality ----------------------------------------------------------------
app.command(name="lint", rich_help_panel=_QUALITY)(lint.lint_command)
app.command(name="diff", rich_help_panel=_QUALITY)(diff.diff_command)
app.add_typer(plan_app, name="plan", rich_help_panel=_QUALITY)
app.add_typer(docs_app, name="docs", rich_help_panel=_QUALITY)
app.add_typer(hook_app, name="hook", rich_help_panel=_QUALITY)

# -- Discovery --------------------------------------------------------------
app.command(name="search", rich_help_panel=_DISCOVERY)(search.search_command)
app.command(name="upgrade", rich_help_panel=_DISCOVERY)(upgrade.upgrade_command)
app.command(name="query", rich_help_panel=_DISCOVERY)(query_command)
app.command(name="status", rich_help_panel=_DISCOVERY)(_status_command)

# -- Communication ----------------------------------------------------------
app.command(name="connect", rich_help_panel=_COMMUNICATION)(connect_command)
app.add_typer(chat_app, name="chat", rich_help_panel=_COMMUNICATION)
app.command(name="inbox", rich_help_panel=_COMMUNICATION)(inbox_command)
app.add_typer(peers_app, name="peers", rich_help_panel=_COMMUNICATION)
app.command(name="review", rich_help_panel=_COMMUNICATION)(knowledge.review_command)
app.add_typer(knowledge.threads_app, name="threads", rich_help_panel=_COMMUNICATION)
app.add_typer(approvals.approvals_app, name="approvals", rich_help_panel=_COMMUNICATION)

# -- Sync & Auth ------------------------------------------------------------
app.command(name="register", rich_help_panel=_SYNC_AUTH)(register.register)
app.command(name="login", rich_help_panel=_SYNC_AUTH)(login.login)
app.command(name="logout", rich_help_panel=_SYNC_AUTH)(login.logout)
app.command(name="sync", rich_help_panel=_SYNC_AUTH)(sync.sync_command)
app.command(name="publish", rich_help_panel=_SYNC_AUTH)(publish.publish_command)
app.command(name="unpublish", rich_help_panel=_SYNC_AUTH)(publish.unpublish_command)

# -- Advanced ---------------------------------------------------------------
app.add_typer(mcp_app, name="mcp", rich_help_panel=_ADVANCED)
memory_app = typer.Typer(
    name="memory",
    help="Cross-project memory sharing.",
    no_args_is_help=True,
)
memory_app.command(name="export")(memory.export_memory)
memory_app.command(name="import")(memory.import_memory)
memory_app.command(name="list")(memory.list_memory)
app.add_typer(memory_app, name="memory", rich_help_panel=_ADVANCED)

handoff_app = typer.Typer(
    name="handoff",
    help="Context handoffs between instructions.",
    no_args_is_help=True,
)
handoff_app.command(name="create")(handoff.create)
handoff_app.command(name="list")(handoff.list_handoffs)
app.add_typer(handoff_app, name="handoff", rich_help_panel=_ADVANCED)

app.add_typer(model_app, name="model", rich_help_panel=_ADVANCED)


# ---------------------------------------------------------------------------
# Standalone commands (version)
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


# ---------------------------------------------------------------------------
# Version callback
# ---------------------------------------------------------------------------

@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit."),
) -> None:
    """writ -- AI instruction management CLI."""
    if version:
        from rich.console import Console
        Console().print(f"writ {__version__}")
        raise typer.Exit()
