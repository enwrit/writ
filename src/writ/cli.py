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
# Register command groups
# ---------------------------------------------------------------------------

# Core commands
app.command(name="init")(init.init_command)
app.command(name="add")(agent.add)
app.command(name="list")(agent.list_agents)
app.command(name="remove")(agent.remove)

# Hidden alias: `writ install` -> `writ add` (backward compat)
app.command(name="install", hidden=True)(agent.add)

# Library: save to personal library
app.command(name="save")(library.save)

# Search & discovery
app.command(name="search")(search.search_command)

# Auth commands (register/login/logout)
app.command(name="register")(register.register)
app.command(name="login")(login.login)
app.command(name="logout")(login.logout)

# Sync command (bulk library sync)
app.command(name="sync")(sync.sync_command)

# Lint command
app.command(name="lint")(lint.lint_command)

# Diff: lint score vs git revision
app.command(name="diff")(diff.diff_command)

# Upgrade: pull latest versions from source
app.command(name="upgrade")(upgrade.upgrade_command)

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
    help="Context handoffs between instructions.",
    no_args_is_help=True,
)
handoff_app.command(name="create")(handoff.create)
handoff_app.command(name="list")(handoff.list_handoffs)
app.add_typer(handoff_app, name="handoff")

# MCP sub-group
app.add_typer(mcp_app, name="mcp")

# Chat sub-group (agent-to-agent conversations)
app.add_typer(chat_app, name="chat")
app.command(name="inbox")(inbox_command)

# Peers sub-group (connected repositories)
app.add_typer(peers_app, name="peers")

# Connect wizard (interactive peer setup)
app.command(name="connect")(connect_command)

# Knowledge: review + threads
app.command(name="review")(knowledge.review_command)
app.add_typer(knowledge.threads_app, name="threads")

# Approvals (human-in-the-loop for agent actions)
app.add_typer(approvals.approvals_app, name="approvals")

# Model configuration (AI model for plan review)
app.add_typer(model_app, name="model")

# Plan review
app.add_typer(plan_app, name="plan")

# Documentation health
app.add_typer(docs_app, name="docs")

# Pre-commit hook
app.add_typer(hook_app, name="hook")

# Query: documentation index navigation
app.command(name="query")(query_command)

# Status: project status + knowledge health + recent activity
app.command(name="status")(_status_command)


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
