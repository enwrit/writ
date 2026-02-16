"""writ init -- Initialize writ in the current repository."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel

from writ.core import scanner, store
from writ.core.models import ProjectConfig
from writ.utils import console

# Resolve template root once, relative to package source
_TEMPLATE_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "templates"


def init_command(
    template: Annotated[
        str | None,
        typer.Option(
            "--template", "-t",
            help="Bootstrap from a built-in template (e.g. default, fullstack).",
        ),
    ] = None,
    import_existing: Annotated[
        bool,
        typer.Option(
            "--import-existing/--no-import-existing",
            help="Import detected agent files into .writ/agents/.",
        ),
    ] = True,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Reinitialize even if .writ/ already exists."),
    ] = False,
) -> None:
    """Initialize writ in the current repository.

    Scans the repo for existing agent files, detects project context,
    and creates the .writ/ directory structure.
    """
    if store.is_initialized() and not force:
        console.print(
            "[yellow]Already initialized.[/yellow] Use --force to reinitialize."
        )
        raise typer.Exit()

    # 1. Create .writ/ directory structure
    writ_dir = store.init_project_store()
    console.print(f"[green]Created[/green] {writ_dir.relative_to(Path.cwd())}/")

    # 2. Detect active IDE tools for format config
    detected_formats = _detect_active_tools()
    config = ProjectConfig(formats=detected_formats or ["agents_md"])
    store.save_config(config)

    # 3. Scan for existing agent files and optionally import
    existing = scanner.detect_existing_files()
    imported_count = 0
    if existing:
        console.print(f"\n[cyan]Found {len(existing)} existing agent file(s):[/cyan]")
        for item in existing:
            console.print(f"  {item['format']:12s} {item['path']}")

        if import_existing:
            imported_count = _import_existing_files(existing)

    # 4. Generate project context
    project_ctx = scanner.analyze_project()
    store.save_project_context(project_ctx)
    console.print("[green]Generated[/green] project context (.writ/project-context.md)")

    # 5. Load template if specified
    if template:
        load_template(template)

    # 6. Summary
    agent_count = len(store.list_agents())
    console.print()
    console.print(Panel.fit(
        "[bold green]writ initialized![/bold green]\n\n"
        + (f"Agents: {agent_count} "
           f"({imported_count} imported)\n" if agent_count else "")
        + "Next steps:\n"
        "  [cyan]writ add <name>[/cyan]       Create a new agent\n"
        "  [cyan]writ add --template[/cyan]   Add agents from a template\n"
        "  [cyan]writ list[/cyan]             List agents in this project\n"
        "  [cyan]writ use <name>[/cyan]       Activate an agent",
        title="writ",
        border_style="green",
    ))


def _detect_active_tools() -> list[str]:
    """Detect which IDE/CLI tools are active in this repo."""
    root = Path.cwd()
    formats: list[str] = []

    if (root / ".cursor").is_dir():
        formats.append("cursor")
    if (root / "CLAUDE.md").exists():
        formats.append("claude")
    if (root / "AGENTS.md").exists():
        formats.append("agents_md")
    if (root / ".github" / "copilot-instructions.md").exists():
        formats.append("copilot")
    if (root / ".windsurfrules").exists():
        formats.append("windsurf")

    # Default to agents_md if nothing detected
    if not formats:
        formats.append("agents_md")

    return formats


def _import_existing_files(existing: list[dict[str, str]]) -> int:
    """Parse and import detected existing agent files. Returns count imported."""
    count = 0
    for item in existing:
        agent = scanner.parse_existing_file(item)
        if agent:
            # Avoid overwriting if agent with same name already exists
            if store.load_agent(agent.name):
                console.print(
                    f"  [dim]Skipped[/dim] '{agent.name}' (already exists)"
                )
                continue
            store.save_agent(agent)
            console.print(f"  [green]Imported[/green] '{agent.name}' from {item['format']}")
            count += 1
    if count:
        console.print(f"[green]Imported {count} agent(s)[/green] from existing files")
    return count


def load_template(template_name: str) -> int:
    """Load agents from a built-in template. Returns count loaded.

    Shared by both `writ init --template` and `writ add --template`.
    """
    template_dir = _TEMPLATE_ROOT / template_name

    if not template_dir.is_dir():
        console.print(f"[red]Template '{template_name}' not found.[/red]")
        available = list_available_templates()
        if available:
            console.print(f"Available templates: {', '.join(available)}")
        raise typer.Exit(1)

    from writ.core.models import AgentConfig
    from writ.utils import yaml_load

    count = 0
    for yaml_file in sorted(template_dir.glob("*.yaml")):
        try:
            data = yaml_load(yaml_file)
            agent = AgentConfig(**data)
            if store.load_agent(agent.name):
                console.print(f"  [dim]Skipped[/dim] '{agent.name}' (already exists)")
                continue
            store.save_agent(agent)
            console.print(f"  [green]Created[/green] agent: {agent.name}")
            count += 1
        except Exception as e:  # noqa: BLE001
            console.print(f"  [red]Failed[/red] to load {yaml_file.name}: {e}")

    if count:
        console.print(
            f"[green]Loaded {count} agent(s)[/green] from '{template_name}' template"
        )
    else:
        console.print(f"[yellow]No new agents from template '{template_name}'[/yellow]")

    return count


def list_available_templates() -> list[str]:
    """List available built-in templates."""
    if not _TEMPLATE_ROOT.is_dir():
        return []
    return [d.name for d in sorted(_TEMPLATE_ROOT.iterdir()) if d.is_dir()]
