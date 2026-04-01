"""writ save -- Personal instruction library management.

Saves locally to ~/.writ/ and syncs to the enwrit backend when logged in.
"""

from __future__ import annotations

from typing import Annotated

import typer

from writ.core import auth, store
from writ.integrations.registry import RegistryClient
from writ.utils import console

# ---------------------------------------------------------------------------
# writ save
# ---------------------------------------------------------------------------

def save(
    name: Annotated[str, typer.Argument(help="Instruction name to save to your personal library.")],
    alias: Annotated[
        str | None, typer.Option("--as", help="Save under a different name.")
    ] = None,
) -> None:
    """Save an instruction from this project to your personal library (~/.writ/).

    Your personal library lets you reuse instructions across projects.
    Use 'writ add <name>' in any project to pull it back.

    If you are logged in (writ login), the instruction is also synced to enwrit.com
    so you can access it from any device.
    """
    if not store.is_initialized():
        console.print("[red]Not initialized.[/red] Run [cyan]writ init[/cyan] first.")
        raise typer.Exit(1)

    inst = store.load_instruction(name)
    if not inst:
        console.print(f"[red]'{name}' not found in this project.[/red]")
        raise typer.Exit(1)

    save_name = alias or name

    inst.composition.project_context = True

    store.init_global_store()
    path = store.save_to_library(inst, alias=save_name)

    console.print(f"[green]Saved[/green] '{save_name}' to personal library ({path})")

    if auth.is_logged_in():
        client = RegistryClient()
        if client.push_to_library(save_name, inst):
            console.print("[dim]  Synced to enwrit.com[/dim]")
        else:
            console.print("[dim]  Local save only (remote sync failed)[/dim]")

    console.print(f"\n  Add to any project: [cyan]writ add {save_name}[/cyan]")
