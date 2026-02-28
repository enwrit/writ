"""writ mcp serve -- Expose instructions and project context via MCP.

Allows external AI agents (Cursor, Claude Desktop, etc.) to discover and read
this repo's instructions without running CLI commands manually.

Requires: pip install enwrit[mcp]
"""

from __future__ import annotations

import typer

from writ.utils import console

mcp_app = typer.Typer(
    name="mcp",
    help="MCP server for cross-repo agent communication.",
    no_args_is_help=True,
)


@mcp_app.command(name="serve")
def serve() -> None:
    """Start the writ MCP server (stdio transport).

    Exposes this project's instructions, rules, and context as MCP tools
    and resources that external AI agents can discover and read.

    \b
    Tools provided:
      writ_list_instructions   -- list all instructions in this project
      writ_get_instruction     -- read a specific instruction by name
      writ_get_project_context -- get auto-detected project context

    \b
    Resources provided:
      writ://instructions/{name}  -- instruction content
      writ://project-context      -- project context

    \b
    Configure your IDE to connect:
      writ export <name> cursor-mcp   -- generate Cursor mcp.json config
    """
    try:
        from writ.integrations.mcp_server import run_server
    except ImportError:
        console.print(
            "[red]MCP dependencies not installed.[/red]\n\n"
            "Run: [cyan]pip install enwrit\\[mcp][/cyan]\n"
        )
        raise typer.Exit(1) from None

    from writ.core import store

    if not store.is_initialized():
        console.print(
            "[yellow]Warning:[/yellow] No .writ/ directory found. "
            "Run [cyan]writ init[/cyan] first for full functionality.\n"
        )

    run_server()
