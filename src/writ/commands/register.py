"""writ register -- Create an enwrit.com account from the CLI."""

from __future__ import annotations

from typing import Annotated

import typer

from writ.core import auth, store
from writ.utils import console


def register(
    username: Annotated[
        str | None,
        typer.Option(
            "--username", "-u",
            help="Display name (shown as publisher in the Hub).",
        ),
    ] = None,
    email: Annotated[
        str | None,
        typer.Option(
            "--email", "-e",
            help="Email address (optional, for account recovery).",
        ),
    ] = None,
) -> None:
    """Create an enwrit.com account and log in automatically.

    Your username becomes your publisher name in the Hub.
    The API key is generated once and saved locally -- you won't
    need to copy-paste anything.

    \b
    Examples:
      writ register                          # interactive prompts
      writ register -u "myname"              # set username, prompt for email
      writ register -u "myname" -e "a@b.com" # fully non-interactive
    """
    if auth.is_logged_in():
        console.print(
            "[yellow]Already logged in.[/yellow] "
            "Run [cyan]writ logout[/cyan] first if you want to register a new account."
        )
        raise typer.Exit(0)

    console.print()
    console.print("[bold]Create your enwrit.com account[/bold]")
    console.print(
        "[dim]This takes 10 seconds. Your username appears as the publisher name in the Hub.[/dim]"
    )
    console.print()

    if username is None:
        username = typer.prompt("Username (displayed publicly)")

    if not username or not username.strip():
        console.print("[red]Username cannot be empty.[/red]")
        raise typer.Exit(1)
    username = username.strip()

    if email is None:
        email = typer.prompt(
            "Email (optional, for account recovery)", default="", show_default=False
        )
    email = email.strip() if email else None

    import httpx

    global_config = store.load_global_config()
    base_url = global_config.registry_url.rstrip("/")

    payload: dict[str, str] = {"github_username": username}
    if email:
        payload["email"] = email

    console.print()
    console.print("[dim]Registering...[/dim]")

    try:
        resp = httpx.post(
            f"{base_url}/auth/register",
            json=payload,
            timeout=15.0,
        )
    except httpx.ConnectError as err:
        console.print("[red]Could not reach api.enwrit.com.[/red] Check your internet connection.")
        raise typer.Exit(1) from err
    except Exception as err:  # noqa: BLE001
        console.print("[red]Network error.[/red] Try again in a moment.")
        raise typer.Exit(1) from err

    if resp.status_code == 200:
        data = resp.json()
        api_key = data.get("api_key", "")

        store.init_global_store()
        auth.save_token(api_key)

        console.print()
        console.print("[green]Account created and logged in![/green]")
        console.print()
        console.print(f"  Username:  [bold]{username}[/bold]")
        if email:
            console.print(f"  Email:     {email}")
        from writ.utils import global_writ_dir

        config_path = global_writ_dir() / "config.yaml"
        console.print(f"  API key:   [dim]{api_key[:12]}...[/dim] (saved to {config_path})")
        console.print()
        console.print("You're ready to go. Try:")
        console.print("  [cyan]writ save <name>[/cyan]    -- sync agents to the cloud")
        console.print("  [cyan]writ publish <name>[/cyan]  -- share with the community")
        console.print()
    elif resp.status_code == 422:
        detail = resp.json().get("detail", "Validation error")
        console.print(f"[red]Registration failed:[/red] {detail}")
        raise typer.Exit(1)
    elif resp.status_code == 409:
        console.print(
            "[yellow]An account with that username or email already exists.[/yellow]\n"
            "If this is your account, run [cyan]writ login[/cyan] with your API key."
        )
        raise typer.Exit(1)
    else:
        console.print(f"[red]Registration failed (HTTP {resp.status_code}).[/red] Try again later.")
        raise typer.Exit(1)
