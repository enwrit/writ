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

    Exposes this project's instructions, context, and files as MCP tools
    and resources that external AI agents can discover and read.

    \b
    Tools provided (V1 -- instruction discovery):
      writ_list_instructions    -- list all instructions in this project
      writ_get_instruction      -- read a specific instruction by name
      writ_get_project_context  -- get auto-detected project context

    \b
    Tools provided (V2 -- Hub access + file access):
      writ_compose_context      -- compose full 4-layer context for an agent
      writ_search_instructions  -- search local + Hub (scope: local/hub/all)
      writ_install_instruction  -- install from Hub into this project
      writ_read_file            -- read a repo file (respects .writignore)
      writ_list_files           -- list files in a directory (with filter)

    \b
    Tools provided (V3 -- agent-to-agent communication):
      writ_start_conversation   -- start a conversation with a peer repo
      writ_send_message         -- send a message (fire-and-forget)
      writ_send_and_wait        -- send and poll for response (MCP Polling)
      writ_check_inbox          -- check for unread messages
      writ_read_conversation    -- read conversation history
      writ_complete_conversation -- mark conversation as completed

    \b
    Tools provided (V4 -- knowledge threads):
      writ_review_instruction   -- submit a review for a public instruction
      writ_search_threads       -- search knowledge threads
      writ_start_thread         -- create a new knowledge thread
      writ_post_to_thread       -- post a message to a thread
      writ_resolve_thread       -- resolve a thread with a conclusion

    \b
    Tools provided (V5 -- approval workflow):
      writ_request_approval     -- request human approval for an action
      writ_check_approval       -- check approval status

    \b
    Resources provided:
      writ://instructions/{name}  -- instruction content
      writ://project-context      -- project context
      writ://files/{path}         -- repo file content (read-only)

    \b
    Setup (add to .cursor/mcp.json or equivalent):
      {"mcpServers": {"writ": {"command": "writ", "args": ["mcp", "serve"]}}}

    \b
    Or with uvx (no pip install needed):
      {"mcpServers": {"writ": {"command": "uvx", "args": ["enwrit", "mcp", "serve"]}}}
    """
    try:
        from writ.integrations.mcp_server import run_server
    except ImportError:
        import subprocess
        import sys

        console.print("[dim]Installing MCP dependencies...[/dim]")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "enwrit[mcp]", "-q"],
                check=True,
            )
        except subprocess.CalledProcessError:
            console.print(
                "[red]Failed to install MCP dependencies.[/red]\n\n"
                "Run manually: [cyan]pip install enwrit\\[mcp][/cyan]\n"
            )
            raise typer.Exit(1) from None
        from writ.integrations.mcp_server import run_server

    from writ.core import store

    if not store.is_initialized():
        console.print(
            "[yellow]Warning:[/yellow] No .writ/ directory found. "
            "Run [cyan]writ init[/cyan] first for full functionality.\n"
        )

    run_server()
