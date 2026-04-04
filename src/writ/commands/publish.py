"""writ publish / unpublish -- Make instructions publicly discoverable."""

from __future__ import annotations

from typing import Annotated

import typer

from writ.core import auth, store
from writ.utils import console


def _require_init() -> None:
    if not store.is_initialized():
        console.print(
            "[red]Not initialized.[/red] Run [cyan]writ init[/cyan] first."
        )
        raise typer.Exit(1)


def _require_login() -> None:
    if not auth.is_logged_in():
        console.print(
            "[red]Not logged in.[/red] "
            "Run [cyan]writ login[/cyan] to authenticate with enwrit.com."
        )
        raise typer.Exit(1)


def publish_command(
    name: Annotated[str, typer.Argument(help="Instruction name to publish.")],
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt."),
    ] = False,
) -> None:
    """Publish an instruction to enwrit.com (publicly discoverable).

    The instruction will be searchable and installable by anyone.

    Examples:
        writ publish reviewer
        writ publish reviewer --yes
    """
    _require_init()
    _require_login()

    inst = store.load_instruction(name)
    if not inst:
        console.print(
            f"[red]'{name}' not found.[/red] "
            "Run [cyan]writ list[/cyan] to see available instructions."
        )
        raise typer.Exit(1)

    if not yes:
        confirm = typer.confirm(
            f"Publish '{name}' to enwrit.com? "
            "It will be publicly visible."
        )
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)

    from writ.integrations.registry import RegistryClient

    client = RegistryClient()
    ok = client.push_to_library(name, inst, is_public=True)
    if ok:
        console.print(f"\n[green]Published '{name}' to enwrit.com[/green]\n")
        console.print(
            f"  Browse:  [cyan]https://enwrit.com/hub/enwrit/{name}[/cyan]"
        )
        console.print(
            f"  Add:     [cyan]writ add {name}[/cyan]"
        )
    else:
        console.print(
            f"[red]Failed to publish '{name}'.[/red] "
            "Check your connection and try again."
        )
        raise typer.Exit(1)


def unpublish_command(
    name: Annotated[str, typer.Argument(help="Instruction name to unpublish.")],
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt."),
    ] = False,
) -> None:
    """Make a published instruction private again.

    The instruction remains in your personal library but is no longer
    publicly discoverable or searchable.

    Examples:
        writ unpublish reviewer
        writ unpublish reviewer --yes
    """
    _require_init()
    _require_login()

    inst = store.load_instruction(name)
    if not inst:
        console.print(
            f"[red]'{name}' not found.[/red] "
            "Run [cyan]writ list[/cyan] to see available instructions."
        )
        raise typer.Exit(1)

    if not yes:
        confirm = typer.confirm(
            f"Unpublish '{name}'? "
            "It will no longer be publicly visible."
        )
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)

    from writ.integrations.registry import RegistryClient

    client = RegistryClient()
    ok = client.push_to_library(name, inst, is_public=False)
    if ok:
        console.print(
            f"[green]'{name}' is now private.[/green] "
            "It remains in your personal library."
        )
    else:
        console.print(
            f"[red]Failed to unpublish '{name}'.[/red] "
            "Check your connection and try again."
        )
        raise typer.Exit(1)
