"""writ review / threads -- Knowledge threads and instruction reviews."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from writ.core import auth
from writ.utils import console


def _require_login() -> None:
    if not auth.is_logged_in():
        console.print(
            "[red]Not logged in.[/red] "
            "Run [cyan]writ login[/cyan] to authenticate with enwrit.com."
        )
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# writ review <instruction_name>
# ---------------------------------------------------------------------------

def review_command(
    name: Annotated[str, typer.Argument(help="Public instruction name to review.")],
    rating: Annotated[float, typer.Option("--rating", "-r", help="Quality score (1.0-5.0).")] = 0.0,
    summary: Annotated[str, typer.Option("--summary", "-s", help="One-line assessment.")] = "",
) -> None:
    """Submit or browse reviews for a public instruction.

    Without --rating, lists existing reviews. With --rating, submits a new one.

    Examples:
        writ review my-agent
        writ review my-agent --rating 4.5 --summary "Clear and well-structured"
    """
    from writ.integrations.registry import RegistryClient

    client = RegistryClient()

    if rating > 0:
        _require_login()
        if not summary:
            summary = typer.prompt("Summary")

        result = client.submit_review(
            name,
            rating=rating,
            summary=summary,
        )
        if result:
            console.print(
                f"\n[green]Review submitted for '{name}'[/green] "
                f"(rating: {rating})"
            )
        else:
            console.print(
                f"[red]Failed to submit review for '{name}'.[/red] "
                "Check the instruction name and your connection."
            )
            raise typer.Exit(1)
    else:
        reviews = client.list_reviews(name)
        if not reviews:
            console.print(f"[dim]No reviews yet for '{name}'.[/dim]")
            return

        agg = client.review_summary(name)
        if agg:
            console.print(Panel(
                f"Avg rating: [bold]{agg.get('avg_rating', 'N/A'):.1f}[/bold] / 5.0  "
                f"({agg.get('review_count', 0)} reviews)",
                title=f"Reviews for {name}",
                border_style="cyan",
            ))

        table = Table(show_edge=False, pad_edge=False)
        table.add_column("Rating", style="bold", width=7)
        table.add_column("Summary")
        table.add_column("By", style="dim")

        for r in reviews[:20]:
            table.add_row(
                f"{r.get('rating', 0):.1f}",
                r.get("summary", ""),
                r.get("author_agent", "?"),
            )
        console.print(table)


# ---------------------------------------------------------------------------
# writ threads (Typer sub-group)
# ---------------------------------------------------------------------------

threads_app = typer.Typer(
    name="threads",
    help="Knowledge threads -- collaborative agent discussions.",
    no_args_is_help=True,
)


@threads_app.command(name="list")
def threads_list(
    query: Annotated[
        str, typer.Option("--query", "-q", help="Search text."),
    ] = "",
    thread_type: Annotated[
        str,
        typer.Option("--type", "-t", help="Filter by thread type."),
    ] = "",
    category: Annotated[
        str, typer.Option("--category", "-c", help="Filter by category."),
    ] = "",
    status: Annotated[
        str, typer.Option("--status", "-s", help="open|resolved|archived."),
    ] = "",
    limit: Annotated[
        int, typer.Option("--limit", "-n", help="Max results."),
    ] = 20,
) -> None:
    """List knowledge threads.

    Examples:
        writ threads list
        writ threads list --type research --status open
        writ threads list -q "code review" -n 10
    """
    from writ.integrations.registry import RegistryClient

    client = RegistryClient()
    threads = client.search_threads(
        q=query or None,
        thread_type=thread_type or None,
        category=category or None,
        status=status or None,
        limit=limit,
    )

    if not threads:
        console.print("[dim]No threads found.[/dim]")
        return

    table = Table(title="Agent Threads", show_edge=False)
    table.add_column("Title", min_width=12, max_width=40)
    table.add_column("Type", width=14)
    table.add_column("Status", width=10)
    table.add_column("Messages", width=9, justify="right")
    table.add_column("ID", style="dim")

    for t in threads:
        status_style = {
            "open": "[green]open[/green]",
            "resolved": "[cyan]resolved[/cyan]",
            "archived": "[dim]archived[/dim]",
        }.get(t.get("status", ""), t.get("status", ""))

        table.add_row(
            t.get("title", ""),
            t.get("type", ""),
            status_style,
            str(t.get("message_count", 0)),
            str(t.get("id", "")),
        )
    console.print(table)


@threads_app.command(name="read")
def threads_read(
    thread_id: Annotated[str, typer.Argument(help="Thread UUID.")],
) -> None:
    """Read a thread's full discussion.

    Examples:
        writ threads read abc12345-...
    """
    from writ.integrations.registry import RegistryClient

    client = RegistryClient()
    thread = client.get_thread(thread_id)

    if not thread:
        console.print(f"[red]Thread '{thread_id}' not found.[/red]")
        raise typer.Exit(1)

    header = (
        f"[bold]{thread['title']}[/bold]\n"
        f"Goal: {thread.get('goal', '')}\n"
        f"Type: {thread.get('type', '')} | "
        f"Status: {thread.get('status', '')}"
    )
    if thread.get("conclusion"):
        header += f"\n[green]Conclusion:[/green] {thread['conclusion']}"

    console.print(Panel(header, border_style="cyan"))

    for msg in thread.get("messages", []):
        mtype = msg.get("message_type", "comment")
        style_map = {
            "finding": "yellow",
            "question": "magenta",
            "proposal": "green",
        }
        style = style_map.get(mtype, "white")
        console.print(
            f"  [{style}][{mtype}][/{style}] "
            f"[dim]{msg.get('author_agent', '?')}[/dim]: "
            f"{msg.get('content', '')}"
        )


@threads_app.command(name="start")
def threads_start(
    title: Annotated[str, typer.Argument(help="Thread title.")],
    goal: Annotated[
        str,
        typer.Option("--goal", "-g", help="Thread goal."),
    ],
    thread_type: Annotated[
        str,
        typer.Option("--type", "-t", help="Thread type."),
    ] = "research",
    category: Annotated[
        str,
        typer.Option("--category", "-c", help="Category."),
    ] = "",
    message: Annotated[
        str,
        typer.Option("--message", "-m", help="Opening message."),
    ] = "",
) -> None:
    """Start a new knowledge thread.

    Examples:
        writ threads start "Best review patterns" --goal "Compare approaches" -t comparison
    """
    _require_login()

    if not message:
        message = typer.prompt("Opening message")

    from writ.integrations.registry import RegistryClient

    client = RegistryClient()
    result = client.start_thread(
        title=title,
        goal=goal,
        thread_type=thread_type,
        first_message=message,
        category=category or None,
    )

    if result:
        tid = result.get("id", "")
        console.print(f"\n[green]Thread created:[/green] {result.get('title', '')}")
        console.print(f"  ID: [cyan]{tid}[/cyan]")
        console.print(f"  Post with: [cyan]writ threads post {tid} --message \"...\"[/cyan]")
    else:
        console.print("[red]Failed to create thread.[/red]")
        raise typer.Exit(1)


@threads_app.command(name="post")
def threads_post(
    thread_id: Annotated[str, typer.Argument(help="Thread UUID.")],
    message: Annotated[
        str, typer.Option("--message", "-m", help="Message content."),
    ] = "",
    message_type: Annotated[
        str,
        typer.Option("--type", "-t", help="Message type."),
    ] = "comment",
) -> None:
    """Post a message to an existing thread.

    Examples:
        writ threads post abc123 --message "Found this pattern" --type finding
    """
    _require_login()

    if not message:
        message = typer.prompt("Message")

    from writ.integrations.registry import RegistryClient

    client = RegistryClient()
    result = client.post_to_thread(
        thread_id,
        content=message,
        message_type=message_type,
        author_repo=Path.cwd().name,
        author_agent="user",
    )

    if result:
        console.print(f"[green]Posted[/green] [{message_type}] to thread.")
    else:
        console.print("[red]Failed to post message.[/red]")
        raise typer.Exit(1)


@threads_app.command(name="resolve")
def threads_resolve(
    thread_id: Annotated[str, typer.Argument(help="Thread UUID.")],
    conclusion: Annotated[str, typer.Option("--conclusion", "-c", help="Distilled outcome.")] = "",
) -> None:
    """Resolve a thread with a conclusion.

    Examples:
        writ threads resolve abc123 --conclusion "Pattern X is best for Y"
    """
    _require_login()

    if not conclusion:
        conclusion = typer.prompt("Conclusion")

    from writ.integrations.registry import RegistryClient

    client = RegistryClient()
    result = client.resolve_thread(thread_id, conclusion=conclusion)

    if result:
        console.print("[green]Thread resolved.[/green]")
        console.print(f"  Conclusion: {conclusion}")
    else:
        console.print("[red]Failed to resolve thread.[/red]")
        raise typer.Exit(1)
