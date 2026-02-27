"""writ compose -- Preview composed context (dry run)."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.markdown import Markdown
from rich.panel import Panel

from writ.core import composer, store
from writ.utils import console


def compose_command(
    name: Annotated[str, typer.Argument(help="Agent name to compose context for.")],
    with_agents: Annotated[
        list[str] | None, typer.Option("--with", help="Additional agents to compose with.")
    ] = None,
    no_project: Annotated[
        bool, typer.Option("--no-project", help="Exclude project context (Layer 1).")
    ] = False,
    no_handoffs: Annotated[
        bool, typer.Option("--no-handoffs", help="Exclude handoff context (Layer 4).")
    ] = False,
    raw: Annotated[
        bool, typer.Option("--raw", help="Show raw text instead of rendered markdown.")
    ] = False,
) -> None:
    """Preview the composed context for an agent (dry run).

    Shows exactly what would be written to IDE files when you run 'writ use'.
    Useful for debugging composition layers.
    """
    if not store.is_initialized():
        console.print("[red]Not initialized.[/red] Run [cyan]writ init[/cyan] first.")
        raise typer.Exit(1)

    agent = store.load_instruction(name)
    if not agent:
        console.print(
            f"[red]Agent '{name}' not found.[/red] "
            "Run [cyan]writ list[/cyan] to see available agents."
        )
        raise typer.Exit(1)

    # Compose with specified options
    composed = composer.compose(
        agent,
        additional=with_agents or [],
        include_project=not no_project,
        include_handoffs=not no_handoffs,
    )

    # Display composed output
    title = f"Composed context for: {name}"
    if with_agents:
        title += f" (with: {', '.join(with_agents)})"

    word_count = len(composed.split())
    char_count = len(composed)

    content = composed if raw else Markdown(composed)

    console.print()
    console.print(Panel(
        content,
        title=title,
        subtitle=f"{word_count} words, {char_count} chars",
        border_style="cyan",
    ))
