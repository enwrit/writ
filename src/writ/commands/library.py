"""writ save/load/library -- Personal agent library management.

Saves locally to ~/.writ/agents/ and syncs to the enwrit backend when logged in.
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from writ.core import auth, store
from writ.core.models import InstructionConfig
from writ.integrations.registry import RegistryClient
from writ.utils import console

# ---------------------------------------------------------------------------
# writ save
# ---------------------------------------------------------------------------

def save(
    name: Annotated[str, typer.Argument(help="Agent name to save to your personal library.")],
    alias: Annotated[
        str | None, typer.Option("--as", help="Save under a different name.")
    ] = None,
) -> None:
    """Save an agent from this project to your personal library (~/.writ/agents/).

    Your personal library lets you reuse agents across projects.
    Use 'writ load <name>' in any project to load it back.

    If you are logged in (writ login), the agent is also synced to enwrit.com
    so you can access it from any device.
    """
    if not store.is_initialized():
        console.print("[red]Not initialized.[/red] Run [cyan]writ init[/cyan] first.")
        raise typer.Exit(1)

    agent = store.load_instruction(name)
    if not agent:
        console.print(f"[red]Agent '{name}' not found in this project.[/red]")
        raise typer.Exit(1)

    save_name = alias or name

    # Make the agent portable: ensure project_context will re-detect in new project
    agent.composition.project_context = True

    # Save to local library
    store.init_global_store()
    path = store.save_to_library(agent, alias=save_name)

    console.print(f"[green]Saved[/green] '{save_name}' to personal library ({path})")

    # Sync to remote if logged in
    if auth.is_logged_in():
        client = RegistryClient()
        if client.push_to_library(save_name, agent):
            console.print("[dim]  Synced to enwrit.com[/dim]")
        else:
            console.print("[dim]  Local save only (remote sync failed)[/dim]")

    console.print(f"\n  Load in any project: [cyan]writ load {save_name}[/cyan]")


# ---------------------------------------------------------------------------
# writ load
# ---------------------------------------------------------------------------

def load(
    name: Annotated[str, typer.Argument(help="Agent name to load from your personal library.")],
) -> None:
    """Load an agent from your personal library into this project.

    Checks local library first, then the remote backend if logged in.
    Copies the agent config into .writ/agents/.
    """
    if not store.is_initialized():
        console.print("[red]Not initialized.[/red] Run [cyan]writ init[/cyan] first.")
        raise typer.Exit(1)

    source = "local"
    agent = store.load_from_library(name)

    # Fall back to remote if not found locally
    if not agent and auth.is_logged_in():
        client = RegistryClient()
        remote_data = client.pull_from_library(name)
        if remote_data:
            agent = _agent_from_remote(remote_data)
            source = "remote"

    if not agent:
        console.print(f"[red]Agent '{name}' not found in your library.[/red]")
        if not auth.is_logged_in():
            console.print(
                "[dim]Tip: run [cyan]writ login[/cyan] to access"
                " agents synced to enwrit.com[/dim]"
            )
        else:
            console.print("Run [cyan]writ library[/cyan] to see available agents.")
        raise typer.Exit(1)

    # Check if already exists in project
    existing = store.load_instruction(name)
    if existing:
        overwrite = typer.confirm(f"Agent '{name}' already exists in this project. Overwrite?")
        if not overwrite:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit()

    path = store.save_instruction(agent)
    if source == "remote":
        console.print(f"[green]Loaded[/green] '{name}' from enwrit.com into project ({path})")
        # Also cache locally so future loads don't need the network
        store.save_to_library(agent)
    else:
        console.print(f"[green]Loaded[/green] '{name}' into project ({path})")
    console.print(f"\n  Activate: [cyan]writ use {name}[/cyan]")


def _agent_from_remote(data: dict) -> InstructionConfig | None:
    """Build an InstructionConfig from a remote API response dict.

    Returns None if the data is missing required fields so the caller
    can handle it gracefully instead of crashing on KeyError.
    """
    name = data.get("name")
    if not name:
        return None
    try:
        return InstructionConfig(
            name=name,
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            tags=data.get("tags", []),
            instructions=data.get("instructions", ""),
        )
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# writ library
# ---------------------------------------------------------------------------

def library_list() -> None:
    """List all agents in your personal library (~/.writ/agents/).

    If logged in, also shows agents stored remotely and their sync status.
    """
    local_agents = store.list_library()
    local_names = {a.name for a in local_agents}

    # Fetch remote agents if logged in
    remote_list: list[dict] = []
    remote_names: set[str] = set()
    if auth.is_logged_in():
        client = RegistryClient()
        remote_list = [a for a in client.list_library() if "name" in a]
        remote_names = {a["name"] for a in remote_list}

    all_names = sorted(local_names | remote_names)

    if not all_names:
        console.print("[yellow]Your personal library is empty.[/yellow]")
        console.print("Save agents with: [cyan]writ save <name>[/cyan]")
        return

    # Build lookups for description/tags
    local_map = {a.name: a for a in local_agents}
    remote_map = {a["name"]: a for a in remote_list}

    table = Table(title="Personal Agent Library", show_lines=False)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Description")
    table.add_column("Version", justify="center")
    if auth.is_logged_in():
        table.add_column("Local", justify="center")
        table.add_column("Remote", justify="center")

    for name in all_names:
        local_agent = local_map.get(name)
        is_local = name in local_names
        is_remote = name in remote_names

        remote_info = remote_map.get(name, {})
        desc = (local_agent.description if local_agent else remote_info.get("description")) or "-"
        ver = (local_agent.version if local_agent else remote_info.get("version")) or "-"

        if auth.is_logged_in():
            table.add_row(
                name,
                desc,
                ver,
                "[green]yes[/green]" if is_local else "[dim]no[/dim]",
                "[green]yes[/green]" if is_remote else "[dim]no[/dim]",
            )
        else:
            table.add_row(name, desc, ver)

    console.print(table)
    console.print(f"\n[dim]{len(all_names)} agent(s) in library[/dim]")
    console.print("Load into a project: [cyan]writ load <name>[/cyan]")
