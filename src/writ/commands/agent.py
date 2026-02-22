"""writ add/list/use/edit/remove -- Local agent management."""

from __future__ import annotations

import os
import subprocess
from typing import Annotated

import typer
from rich.table import Table

from writ.core import composer, store
from writ.core.formatter import get_formatter
from writ.core.models import AgentConfig, CompositionConfig
from writ.utils import console, yaml_load


def _require_init() -> None:
    """Ensure .writ/ is initialized."""
    if not store.is_initialized():
        console.print("[red]Not initialized.[/red] Run [cyan]writ init[/cyan] first.")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# writ add
# ---------------------------------------------------------------------------

def add(
    name: Annotated[
        str | None, typer.Argument(help="Agent name (lowercase, hyphens allowed).")
    ] = None,
    description: Annotated[
        str, typer.Option("--description", "-d", help="Short description.")
    ] = "",
    instructions: Annotated[
        str | None,
        typer.Option(
            "--instructions", "-i",
            help="Instructions (or use --edit to open editor).",
        ),
    ] = None,
    tags: Annotated[
        str | None, typer.Option("--tags", help="Comma-separated tags.")
    ] = None,
    inherits_from: Annotated[
        str | None,
        typer.Option("--inherits-from", help="Comma-separated parent agent names."),
    ] = None,
    template: Annotated[
        str | None,
        typer.Option(
            "--template", "-t",
            help="Load agents from a built-in template (e.g. default, fullstack).",
        ),
    ] = None,
    edit_flag: Annotated[
        bool, typer.Option("--edit", "-e", help="Open in $EDITOR after creating.")
    ] = False,
) -> None:
    """Create a new agent in this project.

    To load a set of agents from a template:
        writ add --template fullstack
    """
    _require_init()

    # Template mode: load agents from built-in template
    if template:
        from writ.commands.init import load_template
        load_template(template)
        return

    # Normal mode: create single agent
    if not name:
        console.print("[red]Provide an agent name or use --template.[/red]")
        raise typer.Exit(1)

    # Check if agent already exists
    if store.load_agent(name):
        console.print(
            f"[red]Agent '{name}' already exists.[/red] "
            f"Use [cyan]writ edit {name}[/cyan] to modify."
        )
        raise typer.Exit(1)

    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    inherit_list = (
        [i.strip() for i in inherits_from.split(",")]
        if inherits_from
        else []
    )

    agent = AgentConfig(
        name=name,
        description=description,
        instructions=instructions or "",
        tags=tag_list,
        composition=CompositionConfig(
            inherits_from=inherit_list,
            project_context=True,
        ),
    )

    path = store.save_agent(agent)
    console.print(f"[green]Created[/green] agent: {name} ({path})")

    if edit_flag or not instructions:
        _open_in_editor(path)

    console.print(f"\nNext: [cyan]writ use {name}[/cyan] to activate this agent.")


# ---------------------------------------------------------------------------
# writ list
# ---------------------------------------------------------------------------

def list_agents() -> None:
    """List all agents in this project."""
    _require_init()

    agents = store.list_agents()
    if not agents:
        console.print(
            "[yellow]No agents found.[/yellow] Run [cyan]writ add <name>[/cyan] to create one."
        )
        return

    table = Table(title="Project Agents", show_lines=False)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Description")
    table.add_column("Tags", style="dim")
    table.add_column("Version", justify="center")
    table.add_column("Inherits", style="dim")

    for agent in agents:
        table.add_row(
            agent.name,
            agent.description or "-",
            ", ".join(agent.tags) if agent.tags else "-",
            agent.version,
            ", ".join(agent.composition.inherits_from) if agent.composition.inherits_from else "-",
        )

    console.print(table)
    console.print(f"\n[dim]{len(agents)} agent(s) total[/dim]")


# ---------------------------------------------------------------------------
# writ use
# ---------------------------------------------------------------------------

def use(
    name: Annotated[str, typer.Argument(help="Agent name to activate.")],
    with_agents: Annotated[
        list[str] | None, typer.Option("--with", help="Additional agents to compose with.")
    ] = None,
    formats: Annotated[
        list[str] | None, typer.Option("--format", "-f", help="Override output formats.")
    ] = None,
) -> None:
    """Activate an agent -- compose context and write to IDE/CLI native files."""
    _require_init()

    agent = store.load_agent(name)
    if not agent:
        console.print(
            f"[red]Agent '{name}' not found.[/red] "
            "Run [cyan]writ list[/cyan] to see available agents."
        )
        raise typer.Exit(1)

    # Compose context (all 4 layers)
    composed = composer.compose(agent, additional=with_agents or [])

    # Determine output formats
    config = store.load_config()
    target_formats = formats or config.formats

    # Write to each format
    written_paths: list[str] = []
    for fmt in target_formats:
        try:
            formatter = get_formatter(fmt)
            path = formatter.write(agent, composed)
            written_paths.append(str(path))
            console.print(f"  [green]Wrote[/green] {fmt} -> {path}")
        except KeyError as e:
            console.print(f"  [red]Unknown format:[/red] {e}")

    if with_agents:
        console.print(f"\n[green]Activated[/green] '{name}' with {', '.join(with_agents)}")
    else:
        console.print(f"\n[green]Activated[/green] '{name}'")

    if written_paths:
        console.print(f"[dim]Wrote to {len(written_paths)} format(s)[/dim]")


# ---------------------------------------------------------------------------
# writ edit
# ---------------------------------------------------------------------------

def edit(
    name: Annotated[str, typer.Argument(help="Agent name to edit.")],
) -> None:
    """Open an agent's YAML config in your $EDITOR."""
    _require_init()

    agent = store.load_agent(name)
    if not agent:
        console.print(
            f"[red]Agent '{name}' not found.[/red] "
            "Run [cyan]writ list[/cyan] to see available agents."
        )
        raise typer.Exit(1)

    path = store.project_writ_dir() / "agents" / f"{name}.yaml"
    _open_in_editor(path)

    # Reload and validate
    try:
        data = yaml_load(path)
        AgentConfig(**data)
        console.print(f"[green]Saved[/green] changes to '{name}'.")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Warning:[/red] Config may be invalid: {e}")


# ---------------------------------------------------------------------------
# writ remove
# ---------------------------------------------------------------------------

def remove(
    name: Annotated[str, typer.Argument(help="Agent name to remove.")],
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip confirmation.")
    ] = False,
) -> None:
    """Remove an agent from this project."""
    _require_init()

    agent = store.load_agent(name)
    if not agent:
        console.print(
            f"[red]Agent '{name}' not found.[/red] "
            "Run [cyan]writ list[/cyan] to see available agents."
        )
        raise typer.Exit(1)

    if not yes:
        confirm = typer.confirm(f"Remove agent '{name}'?")
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit()

    store.remove_agent(name)
    console.print(f"[green]Removed[/green] agent: {name}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _open_in_editor(path) -> None:
    """Open a file in the user's $EDITOR."""
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        # Try common editors
        for candidate in ("code", "vim", "nano", "notepad"):
            try:
                subprocess.run([candidate, "--version"], capture_output=True, check=True)
                editor = candidate
                break
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue

    if editor:
        try:
            subprocess.run([editor, str(path)], check=False)
        except FileNotFoundError:
            console.print(f"[yellow]Could not open editor.[/yellow] Edit manually: {path}")
    else:
        console.print(f"[yellow]No editor found.[/yellow] Edit manually: {path}")
