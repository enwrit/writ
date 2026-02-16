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
    memory,
    search,
)

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

# Library commands (save/load/library/sync)
app.command(name="save")(library.save)
app.command(name="load")(library.load)
app.command(name="library")(library.library_list)

# Lint command
app.command(name="lint")(lint.lint_command)

# Install + Search commands
app.command(name="install")(install.install_command)
app.command(name="search")(search.search_command)

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
