"""writ login/logout -- Authenticate with the enwrit platform."""

from __future__ import annotations

from typing import Annotated

import typer

from writ.core import auth, store
from writ.utils import console


def login(
    token: Annotated[
        str | None,
        typer.Option(
            "--token", "-t",
            help="API key (e.g. sk_abc123). If omitted, prompts interactively.",
        ),
    ] = None,
) -> None:
    """Log in with an existing enwrit.com API key.

    If you don't have an account yet, run [cyan]writ register[/cyan] instead.

    \b
    Examples:
      writ login                    # interactive prompt
      writ login --token sk_abc123  # non-interactive (for scripting)
    """
    if token is None:
        token = typer.prompt("Enter your enwrit API key", hide_input=True)

    if not token or not token.strip():
        console.print("[red]API key cannot be empty.[/red]")
        raise typer.Exit(1)

    token = token.strip()

    store.init_global_store()
    auth.save_token(token)

    from writ.utils import global_writ_dir

    config_path = global_writ_dir() / "config.yaml"
    console.print("[green]Logged in.[/green] Your agents will now sync to enwrit.com.")
    console.print(f"[dim]Token saved to {config_path}[/dim]")


def logout() -> None:
    """Remove the stored API key and stop syncing with enwrit.com."""
    if not auth.is_logged_in():
        console.print("[dim]Not logged in.[/dim]")
        return

    auth.clear_token()
    console.print("[green]Logged out.[/green] Agents will no longer sync to enwrit.com.")
    console.print("[dim]Local library is unchanged.[/dim]")
