"""writ mcp -- MCP server setup and management.

writ mcp install   -- auto-configure MCP in detected IDEs (slim mode)
writ mcp uninstall -- remove writ MCP config from detected IDEs
writ mcp serve     -- start the stdio server (called by IDEs, not by users)

Supports: Cursor, VS Code/Copilot, Claude Code, Kiro, Windsurf.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Annotated

import typer

from writ.utils import console

mcp_app = typer.Typer(
    name="mcp",
    help="MCP server -- install, uninstall, or serve.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Shared: command resolution + config read/write
# ---------------------------------------------------------------------------

def _resolve_writ_command(slim: bool = True) -> dict:
    """Build the MCP server entry for IDE config files.

    Resolves the correct command so the IDE can spawn the MCP server process.
    When running inside a venv, always uses the venv's Python to ensure
    the IDE finds writ and its dependencies correctly.
    Sets ``disabled: false`` so Cursor auto-enables on next full restart.
    """
    args_suffix = ["mcp", "serve"]
    if slim:
        args_suffix.append("--slim")

    def _in_venv() -> bool:
        if sys.prefix != sys.base_prefix:
            return True
        if os.environ.get("VIRTUAL_ENV"):
            return True
        parts = [p.lower() for p in Path(sys.executable).parts]
        return any(v in parts for v in ("venv", ".venv", "env", ".env", "virtualenv"))

    if _in_venv():
        return {"command": sys.executable, "args": ["-m", "writ", *args_suffix], "disabled": False}

    if shutil.which("uvx"):
        return {"command": "uvx", "args": ["enwrit", *args_suffix], "disabled": False}

    if shutil.which("writ"):
        return {"command": "writ", "args": args_suffix, "disabled": False}

    return {"command": sys.executable, "args": ["-m", "writ", *args_suffix], "disabled": False}


def _merge_mcp_json(
    path: Path, servers_key: str, writ_entry: dict,
) -> Path:
    """Write writ server entry into a JSON config, preserving other servers."""
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    servers = existing.get(servers_key, {})
    servers["writ"] = writ_entry
    existing[servers_key] = servers

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    return path


def _remove_from_mcp_json(path: Path, servers_key: str) -> bool:
    """Remove the 'writ' entry from a JSON config. Returns True if removed."""
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False

    servers = data.get(servers_key, {})
    if "writ" not in servers:
        return False

    del servers["writ"]
    data[servers_key] = servers
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


def _detect_ide_configs(root: Path) -> list[tuple[str, Path, str]]:
    """Detect IDE config files. Returns [(ide_name, config_path, servers_key)].

    Uses IDE_PATHS.mcp for tools that declare MCP config paths.
    VS Code is handled specially (it's an editor, not in IDE_PATHS).
    """
    from writ.core.formatter import IDE_PATHS

    configs: list[tuple[str, Path, str]] = []

    for _key, cfg in IDE_PATHS.items():
        if cfg.mcp and (root / cfg.detect).exists():
            mcp_path, servers_key = cfg.mcp
            configs.append((cfg.name, root / mcp_path, servers_key))

    if (root / ".vscode").is_dir():
        configs.append(("VS Code", root / ".vscode" / "mcp.json", "servers"))
    elif (root / ".github").is_dir() and not any(n == "GitHub Copilot" for n, _, _ in configs):
        vscode_dir = root / ".vscode"
        vscode_dir.mkdir(exist_ok=True)
        configs.append(("GitHub Copilot (VS Code)", vscode_dir / "mcp.json", "servers"))

    return configs


def install_mcp_configs(
    root: Path | None = None, *, full: bool = False,
) -> list[tuple[str, Path]]:
    """Detect IDEs and write MCP server config to each one.

    Merges with existing configs -- never overwrites other MCP servers.
    Returns list of (ide_name, config_path) tuples for each file written.

    full=False (default): slim mode -- only MCP-exclusive tools.
    full=True: all 18 tools (for MCP-only users or E2E testing).
    """
    root = root or Path.cwd()
    written: list[tuple[str, Path]] = []
    entry = _resolve_writ_command(slim=not full)

    for ide_name, config_path, servers_key in _detect_ide_configs(root):
        ide_entry = entry.copy()
        if servers_key == "servers":
            ide_entry = {**entry, "type": "stdio"}
        _merge_mcp_json(config_path, servers_key, ide_entry)
        written.append((ide_name, config_path))

    return written


def uninstall_mcp_configs(root: Path | None = None) -> list[tuple[str, Path]]:
    """Remove writ MCP server entry from all detected IDE configs.

    Preserves all other MCP servers. Returns list of (ide_name, config_path)
    for each file where writ was removed.
    """
    root = root or Path.cwd()
    removed: list[tuple[str, Path]] = []

    for ide_name, config_path, servers_key in _detect_ide_configs(root):
        if _remove_from_mcp_json(config_path, servers_key):
            removed.append((ide_name, config_path))

    return removed


# ---------------------------------------------------------------------------
# writ mcp install
# ---------------------------------------------------------------------------

@mcp_app.command(name="install")
def install_cmd(
    full: Annotated[
        bool,
        typer.Option(
            "--full",
            help="Full mode: expose all 18 MCP tools (for MCP-only users or testing).",
        ),
    ] = False,
) -> None:
    """Auto-configure writ MCP server in all detected IDEs.

    Detects Cursor, VS Code, Claude Code, Kiro, and Windsurf, then writes
    the writ MCP server entry to each IDE's config file. Existing MCP
    servers are preserved -- only the "writ" entry is added or updated.

    \b
    Default (slim mode): only MCP-exclusive tools (writ_compose,
    writ_chat_send_wait). The CLI already provides everything else
    with less token overhead.

    \b
    --full: expose all 18 tools. Use this if you don't have the CLI
    in your agent's context, or for end-to-end testing.

    """
    from writ.core import store

    if not store.is_initialized():
        console.print(
            "[yellow]Warning:[/yellow] No .writ/ directory found. "
            "Run [cyan]writ init[/cyan] first.\n"
        )

    written = install_mcp_configs(full=full)

    if not written:
        console.print(
            "[yellow]No IDE directories detected.[/yellow]\n"
            "Looked for: .cursor/, .vscode/, .claude/, .kiro/, .windsurfrules\n\n"
            "You can manually add the writ MCP server to your IDE config:\n"
            '  [cyan]{"mcpServers": {"writ": {"command": "uvx", '
            '"args": ["enwrit", "mcp", "serve"]}}}[/cyan]\n'
        )
        return

    mode_label = "full" if full else "slim"
    console.print("[green]MCP server configured for:[/green]\n")
    for ide_name, path in written:
        console.print(f"  [cyan]{ide_name}[/cyan] -> {path}")

    if full:
        console.print(
            f"\n  Uses [bold]{mode_label} mode[/bold]: all 18 MCP tools exposed."
        )
    else:
        console.print(
            f"\n  Uses [bold]{mode_label} mode[/bold]: only MCP-exclusive tools "
            "(writ_compose, writ_chat_send_wait)."
        )
        console.print(
            "  The CLI already provides all other tools with less token overhead."
        )
        console.print(
            "  Use [cyan]writ mcp install --full[/cyan] for all 18 tools."
        )

    console.print(
        "\n[dim]If the server shows as disabled, toggle it in your MCP settings "
        "or restart your editor.[/dim]\n"
    )


# ---------------------------------------------------------------------------
# writ mcp uninstall
# ---------------------------------------------------------------------------

@mcp_app.command(name="uninstall")
def uninstall_cmd() -> None:
    """Remove writ MCP server from all detected IDEs.

    Removes the "writ" entry from each IDE's MCP config file.
    Other MCP servers are preserved.
    """
    removed = uninstall_mcp_configs()

    if not removed:
        console.print("[dim]No writ MCP configs found to remove.[/dim]")
        return

    console.print("[green]Removed writ MCP server from:[/green]\n")
    for ide_name, path in removed:
        console.print(f"  [cyan]{ide_name}[/cyan] -> {path}")
    console.print()


# ---------------------------------------------------------------------------
# writ mcp serve
# ---------------------------------------------------------------------------

@mcp_app.command(name="serve")
def serve(
    slim: Annotated[
        bool,
        typer.Option(
            "--slim",
            help="Slim mode: only expose MCP-exclusive tools (compose, send_wait).",
        ),
    ] = False,
) -> None:
    """Start the writ MCP server (stdio transport).

    This command is called by your IDE -- not by you directly.
    Run [cyan]writ mcp install[/cyan] to set up the connection.

    \b
    Full mode (default for MCP-only users via uvx):
      All 18 tools across instruction management, Hub access, chat,
      knowledge threads, and approvals.

    \b
    Slim mode (--slim, default when installed via 'writ mcp install'):
      Only tools the CLI cannot provide: writ_compose, writ_chat_send_wait.
      Prevents token bloat when the agent already has the CLI.
    """
    try:
        from writ.integrations.mcp_server import run_server
    except ImportError:
        import subprocess

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

    run_server(slim=slim)
