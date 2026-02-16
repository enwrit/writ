"""writ memory -- Cross-project memory sharing."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from writ.core import store
from writ.core.models import AgentConfig
from writ.utils import console, ensure_dir, global_writ_dir, project_writ_dir

GLOBAL_MEMORY = global_writ_dir() / "memory"


# ---------------------------------------------------------------------------
# writ memory export
# ---------------------------------------------------------------------------

def export_memory(
    name: Annotated[str, typer.Argument(help="Name for this memory export.")],
    source: Annotated[
        str | None, typer.Option("--from", help="File path to export as memory.")
    ] = None,
    content: Annotated[
        str | None, typer.Option("--content", help="Direct content to save as memory.")
    ] = None,
) -> None:
    """Export context from this project for use in other projects.

    Examples:
        writ memory export research-insights --from notes.md
        writ memory export decisions --content "We chose Rust for performance..."
    """
    ensure_dir(GLOBAL_MEMORY)
    dest = GLOBAL_MEMORY / f"{name}.md"

    if source:
        source_path = Path(source)
        if not source_path.exists():
            console.print(f"[red]File not found:[/red] {source}")
            raise typer.Exit(1)
        data = source_path.read_text(encoding="utf-8")
    elif content:
        data = content
    else:
        # Export project context + any handoffs as a bundle
        data = _bundle_project_memory()

    # Add metadata header
    metadata = f"---\nproject: {Path.cwd().name}\ndate: {date.today()}\n---\n\n"
    dest.write_text(metadata + data, encoding="utf-8")

    console.print(f"[green]Exported[/green] memory '{name}' to {dest}")
    console.print(f"\n  Import in another project: [cyan]writ memory import {name}[/cyan]")


# ---------------------------------------------------------------------------
# writ memory import
# ---------------------------------------------------------------------------

def import_memory(
    name: Annotated[str, typer.Argument(help="Memory name to import.")],
    as_agent: Annotated[
        str | None, typer.Option("--as-agent", help="Create an agent from this memory.")
    ] = None,
) -> None:
    """Import cross-project memory into this project.

    The memory becomes available as a composition layer for agents.

    Examples:
        writ memory import research-insights
        writ memory import research-insights --as-agent research-context
    """
    source = GLOBAL_MEMORY / f"{name}.md"
    if not source.exists():
        console.print(f"[red]Memory '{name}' not found.[/red]")
        console.print("Run [cyan]writ memory list[/cyan] to see available memories.")
        raise typer.Exit(1)

    # Copy to project's memory directory
    dest = project_writ_dir() / "memory" / f"{name}.md"
    ensure_dir(dest.parent)
    shutil.copy(source, dest)

    if as_agent:
        # Create an agent wrapping this memory
        memory_content = source.read_text(encoding="utf-8")
        agent = AgentConfig(
            name=as_agent,
            description=f"Context imported from memory '{name}'",
            instructions=memory_content,
            tags=["imported", "memory", name],
        )
        store.save_agent(agent)
        console.print(f"[green]Created[/green] agent '{as_agent}' from memory '{name}'")
    else:
        console.print(f"[green]Imported[/green] memory '{name}' to {dest}")


# ---------------------------------------------------------------------------
# writ memory list
# ---------------------------------------------------------------------------

def list_memory() -> None:
    """List all available cross-project memories."""
    global_mems = sorted(GLOBAL_MEMORY.glob("*.md")) if GLOBAL_MEMORY.exists() else []
    local_dir = project_writ_dir() / "memory"
    local_mems = sorted(local_dir.glob("*.md")) if local_dir.exists() else []

    if not global_mems and not local_mems:
        console.print("[yellow]No memories found.[/yellow]")
        console.print("Export with: [cyan]writ memory export <name>[/cyan]")
        return

    table = Table(title="Cross-Project Memories", show_lines=False)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Source", style="dim")
    table.add_column("Location")

    seen: set[str] = set()

    for path in local_mems:
        name = path.stem
        seen.add(name)
        location = "project + global" if (GLOBAL_MEMORY / path.name).exists() else "project"
        table.add_row(name, _extract_project(path), location)

    for path in global_mems:
        name = path.stem
        if name not in seen:
            table.add_row(name, _extract_project(path), "global")

    console.print(table)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bundle_project_memory() -> str:
    """Bundle project context and handoffs into a memory export."""
    parts: list[str] = []

    project_ctx = store.load_project_context()
    if project_ctx:
        parts.append("# Project Context\n\n" + project_ctx)

    # Include all handoffs
    handoffs_dir = project_writ_dir() / "handoffs"
    if handoffs_dir.exists():
        for hf in sorted(handoffs_dir.glob("*.md")):
            parts.append(f"# Handoff: {hf.stem}\n\n" + hf.read_text(encoding="utf-8"))

    return "\n\n---\n\n".join(parts) if parts else "No project context available."


def _extract_project(path: Path) -> str:
    """Extract the 'project' field from memory file's YAML frontmatter."""
    try:
        content = path.read_text(encoding="utf-8")
        if content.startswith("---"):
            end = content.index("---", 3)
            fm = content[3:end].strip()
            for line in fm.split("\n"):
                if line.startswith("project:"):
                    return line.split(":", 1)[1].strip()
    except (ValueError, OSError):
        pass
    return "-"
