"""writ add/list/use/edit/remove -- Local agent management."""

from __future__ import annotations

import os
import subprocess
from typing import Annotated

import typer
from rich.table import Table

from writ.core import composer, store
from writ.core.formatter import get_formatter
from writ.core.models import CompositionConfig, InstructionConfig
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
            help="Load from a built-in template. Use --template list to see options.",
        ),
    ] = None,
    file: Annotated[
        str | None,
        typer.Option(
            "--file",
            help="Import from a markdown file (or directory of files).",
        ),
    ] = None,
    task_type: Annotated[
        str | None,
        typer.Option("--task-type", help="Content category (agent, rule, context, program)."),
    ] = None,
    edit_flag: Annotated[
        bool, typer.Option("--edit", "-e", help="Open in $EDITOR after creating.")
    ] = False,
) -> None:
    """Create a new agent in this project.

    \b
    Examples:
      writ add reviewer -d "Code reviewer"    # create a single agent
      writ add --template fullstack            # load a team of agents
      writ add --template list                 # show available templates
      writ add --file my-rules.md              # import a markdown file
      writ add --file .cursor/rules/           # import all files in a directory
    """
    # Show template list without requiring init
    if template == "list":
        _show_available_templates()
        return

    _require_init()

    # Template mode: load agents from built-in template
    if template:
        from writ.commands.init import load_template
        load_template(template)
        return

    # File import mode
    if file:
        _import_from_file(
            file,
            name_override=name,
            description_override=description or None,
            tags_override=tags,
            task_type_override=task_type,
        )
        return

    # Normal mode: create single agent
    if not name:
        console.print("[red]Provide an agent name, --file, or --template.[/red]")
        console.print()
        console.print("Examples:")
        console.print("  [cyan]writ add reviewer -d \"Code reviewer\"[/cyan]")
        console.print("  [cyan]writ add --file my-rules.md[/cyan]")
        console.print("  [cyan]writ add --template fullstack[/cyan]")
        console.print("  [cyan]writ add --template list[/cyan]  (see all templates)")
        raise typer.Exit(1)

    # Check if agent already exists
    if store.load_instruction(name):
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

    agent = InstructionConfig(
        name=name,
        description=description,
        instructions=instructions or "",
        tags=tag_list,
        task_type=task_type,
        composition=CompositionConfig(
            inherits_from=inherit_list,
            project_context=True,
        ),
    )

    store.save_instruction(agent)
    _print_added(agent)

    if edit_flag or not instructions:
        path = store.find_instruction_path(name)
        if path:
            _open_in_editor(path)

    console.print(f"\nNext: [cyan]writ use {name}[/cyan] to activate this agent.")


# ---------------------------------------------------------------------------
# writ list
# ---------------------------------------------------------------------------

def list_agents() -> None:
    """List all agents in this project."""
    _require_init()

    agents = store.list_instructions()
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

    agent = store.load_instruction(name)
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

    path = store.find_instruction_path(name)
    if not path:
        console.print(
            f"[red]Agent '{name}' not found.[/red] "
            "Run [cyan]writ list[/cyan] to see available agents."
        )
        raise typer.Exit(1)

    _open_in_editor(path)

    # Reload and validate
    try:
        data = yaml_load(path)
        InstructionConfig(**data)
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

    agent = store.load_instruction(name)
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

    store.remove_instruction(name)
    console.print(f"[green]Removed[/green] agent: {name}")


# ---------------------------------------------------------------------------
# File import helpers
# ---------------------------------------------------------------------------

def _print_added(cfg: InstructionConfig) -> None:
    """Content-focused output after adding an instruction."""
    tokens = len(cfg.instructions.split())
    if tokens >= 1000:
        token_str = f"{tokens / 1000:.1f}k tokens"
    else:
        token_str = f"{tokens} tokens"
    type_label = cfg.task_type or "agent"
    console.print(f"[green]Added[/green] '{cfg.name}' ({type_label}, {token_str})")


def _import_from_file(
    file_path: str,
    *,
    name_override: str | None = None,
    description_override: str | None = None,
    tags_override: str | None = None,
    task_type_override: str | None = None,
) -> None:
    """Import one file or all supported files in a directory."""
    from pathlib import Path

    from writ.core.scanner import _IMPORTABLE_EXTENSIONS, parse_markdown_file

    path = Path(file_path)

    if not path.exists():
        console.print(f"[red]File not found:[/red] {file_path}")
        raise typer.Exit(1)

    if path.is_dir():
        files = sorted(
            f for f in path.iterdir()
            if f.is_file() and f.suffix.lower() in _IMPORTABLE_EXTENSIONS
        )
        if not files:
            console.print(f"[yellow]No importable files found in {file_path}[/yellow]")
            console.print("[dim]Supported extensions: .md, .mdc, .txt[/dim]")
            raise typer.Exit(1)

        count = 0
        for f in files:
            cfg = parse_markdown_file(f)
            if cfg is None:
                console.print(f"  [dim]Skipped[/dim] {f.name} (empty or unparseable)")
                continue
            if task_type_override:
                cfg.task_type = task_type_override
            if tags_override:
                cfg.tags = [t.strip() for t in tags_override.split(",")]
            if store.load_instruction(cfg.name):
                console.print(f"  [dim]Skipped[/dim] '{cfg.name}' (already exists)")
                continue
            store.save_instruction(cfg)
            _print_added(cfg)
            count += 1
        if count:
            console.print(f"\n[green]Imported {count} file(s)[/green] from {file_path}")
        else:
            console.print("[yellow]No new instructions imported.[/yellow]")
        return

    if path.suffix.lower() not in _IMPORTABLE_EXTENSIONS:
        console.print(
            f"[red]Unsupported file type:[/red] {path.suffix}\n"
            "[dim]Supported: .md, .mdc, .txt, .windsurfrules, .cursorrules[/dim]"
        )
        raise typer.Exit(1)

    cfg = parse_markdown_file(path, name_override=name_override)
    if cfg is None:
        console.print(f"[red]Could not parse[/red] {file_path} (empty or invalid)")
        raise typer.Exit(1)

    if description_override:
        cfg.description = description_override
    if tags_override:
        cfg.tags = [t.strip() for t in tags_override.split(",")]
    if task_type_override:
        cfg.task_type = task_type_override

    if store.load_instruction(cfg.name):
        console.print(
            f"[red]'{cfg.name}' already exists.[/red] "
            f"Use [cyan]writ edit {cfg.name}[/cyan] to modify."
        )
        raise typer.Exit(1)

    store.save_instruction(cfg)
    _print_added(cfg)
    console.print(f"\nNext: [cyan]writ use {cfg.name}[/cyan] to activate.")


# ---------------------------------------------------------------------------
# Template / editor helpers
# ---------------------------------------------------------------------------

def _show_available_templates() -> None:
    """List available templates with descriptions."""
    from writ.commands.init import list_available_templates

    templates = list_available_templates()
    if not templates:
        console.print("[yellow]No templates found.[/yellow]")
        return

    descriptions: dict[str, str] = {
        "default": "General-purpose coding assistant",
        "fullstack": "Architect + implementer + reviewer + tester",
        "python": "Python developer + reviewer",
        "react": "React + TypeScript developer + reviewer",
        "typescript": "TypeScript developer + reviewer",
        "rules": "Project rule template + coding standards",
        "context": "Project context + API context",
    }

    console.print("[bold]Available templates:[/bold]")
    console.print()
    for name in templates:
        desc = descriptions.get(name, "")
        console.print(f"  [cyan]{name:<14}[/cyan] {desc}")

    console.print()
    console.print("Usage: [cyan]writ add --template <name>[/cyan]")


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
