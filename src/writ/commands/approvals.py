"""CLI commands for managing approval requests from AI agents."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from writ.core import auth
from writ.utils import console

approvals_app = typer.Typer(
    help="Manage approval requests from AI agents.",
    no_args_is_help=True,
)


def _require_login() -> None:
    if not auth.is_logged_in():
        console.print(
            "[red]Not logged in.[/red] "
            "Run [cyan]writ login[/cyan] to authenticate with enwrit.com."
        )
        raise typer.Exit(1)


@approvals_app.command(name="list")
def list_approvals(
    status: Annotated[
        str | None,
        typer.Option(help="Filter by status: pending, approved, denied, expired"),
    ] = None,
) -> None:
    """List your approval requests."""
    _require_login()

    from writ.integrations.registry import RegistryClient

    client = RegistryClient()
    data = client.list_approvals(status=status or "")
    if "error" in data:
        console.print(f"[red]Error: {data['error']}[/red]")
        raise typer.Exit(1)

    approvals = data.get("approvals", [])
    if not approvals:
        console.print("[dim]No approval requests found.[/dim]")
        return

    table = Table(title="Approval Requests")
    table.add_column("ID", style="dim", max_width=16)
    table.add_column("Action")
    table.add_column("Description")
    table.add_column("Urgency")
    table.add_column("Status")
    table.add_column("Agent")

    for a in approvals:
        urgency_style = {
            "critical": "bold red",
            "high": "red",
            "normal": "yellow",
            "low": "dim",
        }.get(a.get("urgency", "normal"), "")

        status_style = {
            "pending": "bold yellow",
            "approved": "green",
            "denied": "red",
            "expired": "dim",
        }.get(a.get("status", ""), "")

        table.add_row(
            a.get("id", "")[:16],
            a.get("action_type", ""),
            a.get("description", "")[:50],
            f"[{urgency_style}]{a.get('urgency', '')}[/{urgency_style}]",
            f"[{status_style}]{a.get('status', '')}[/{status_style}]",
            a.get("agent_name", ""),
        )

    console.print(table)


@approvals_app.command()
def approve(
    approval_id: Annotated[str, typer.Argument(help="Approval request ID")],
) -> None:
    """Approve a pending request."""
    _require_login()

    from writ.integrations.registry import RegistryClient

    client = RegistryClient()
    result = client.resolve_approval(approval_id, decision="approved")
    if "error" in result:
        console.print(f"[red]Error: {result['error']}[/red]")
        raise typer.Exit(1)
    console.print(
        Panel(
            f"[green]Approved[/green]: {result.get('description', '')}",
            title="Approval",
        )
    )


@approvals_app.command()
def deny(
    approval_id: Annotated[str, typer.Argument(help="Approval request ID")],
    reason: Annotated[
        str | None,
        typer.Option("--reason", "-r", help="Reason for denial"),
    ] = None,
) -> None:
    """Deny a pending request."""
    _require_login()

    from writ.integrations.registry import RegistryClient

    client = RegistryClient()
    result = client.resolve_approval(
        approval_id, decision="denied", reason=reason or "",
    )
    if "error" in result:
        console.print(f"[red]Error: {result['error']}[/red]")
        raise typer.Exit(1)
    console.print(
        Panel(
            f"[red]Denied[/red]: {result.get('description', '')}",
            title="Approval",
        )
    )
