"""CLI commands for managing approval requests from AI agents."""

from __future__ import annotations

from pathlib import Path
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


@approvals_app.command(name="create")
def create_approval(
    action_type: Annotated[
        str,
        typer.Argument(
            help="Action type (deploy, install, refactor, "
            "file_write, file_delete, shell_command, custom)",
        ),
    ],
    description: Annotated[str, typer.Argument(help="What the agent wants to do")],
    reasoning: Annotated[
        str, typer.Option("--reasoning", "-r", help="Why this action is needed"),
    ] = "",
    urgency: Annotated[
        str, typer.Option("--urgency", "-u", help="low|normal|high|critical"),
    ] = "normal",
) -> None:
    """Create an approval request for a human to review.

    Use this when an AI agent needs explicit human permission before
    proceeding with a significant action.

    Examples:
        writ approvals create deploy "Deploy v2.0 to production"
        writ approvals create delete "Remove legacy auth module" --urgency high
    """
    _require_login()

    from writ.integrations.registry import RegistryClient

    client = RegistryClient()
    result = client.create_approval(
        action_type=action_type,
        description=description,
        reasoning=reasoning,
        urgency=urgency,
        repo_name=str(Path.cwd().name),
    )
    if "error" in result:
        console.print(f"[red]Error: {result['error']}[/red]")
        raise typer.Exit(1)

    approval_id = result.get("id", "")
    console.print(
        Panel(
            f"[bold]Action:[/bold] {action_type}\n"
            f"[bold]Description:[/bold] {description}\n"
            f"[bold]Urgency:[/bold] {urgency}\n"
            f"[bold]Status:[/bold] [yellow]pending[/yellow]\n"
            f"\nApproval ID: [cyan]{approval_id}[/cyan]",
            title="Approval Request Created",
            border_style="green",
        )
    )
    console.print("\n  Check status: [cyan]writ approvals list[/cyan]")


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
