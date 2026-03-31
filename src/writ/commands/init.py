"""writ init -- Initialize writ in the current repository."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel

from writ.core import scanner, store
from writ.core.formatter import (
    ClaudeRulesFormatter,
    CursorFormatter,
    KiroSteeringFormatter,
)
from writ.core.models import (
    CompositionConfig,
    CursorOverrides,
    FormatOverrides,
    InstructionConfig,
    ProjectConfig,
)
from writ.utils import console

# Resolve template root once, relative to the writ package (src/writ/templates/)
_TEMPLATE_ROOT = Path(__file__).resolve().parent.parent / "templates"
_BUILTIN_ROOT = _TEMPLATE_ROOT / "_builtin"


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

    # 1. Create .writ/ directory structure (clean content dirs on --force)
    writ_dir = store.init_project_store(clean=force)
    console.print(f"[green]Created[/green] {writ_dir.relative_to(Path.cwd())}/")

    # 2. Detect active IDE tools for format config (directory-based only)
    detected_formats = _detect_active_tools()
    config = ProjectConfig(formats=detected_formats or ["cursor"])
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

    # 5. Install writ-context rule to detected IDEs
    _install_writ_context(detected_formats)

    # 6. Load template if specified
    if template:
        load_template(template)

    # 7. Summary
    agent_count = len(store.list_instructions())
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
    """Detect which IDE/CLI tools are active in this repo.

    Only auto-detects directory-based formats where writ writes its own
    separate files (safe, non-intrusive).  Shared-file formats (AGENTS.md,
    CLAUDE.md, .windsurfrules, copilot-instructions.md) are available but
    only activated when the user explicitly passes ``--format <name>``.
    """
    root = Path.cwd()
    formats: list[str] = []

    if (root / ".cursor").is_dir():
        formats.append("cursor")
    if (root / ".claude").is_dir():
        formats.append("claude_rules")
    if (root / ".kiro").is_dir():
        formats.append("kiro_steering")

    return formats


def _import_existing_files(existing: list[dict[str, str]]) -> int:
    """Parse and import detected existing agent files. Returns count imported."""
    count = 0
    for item in existing:
        agent = scanner.parse_existing_file(item)
        if agent:
            # Avoid overwriting if agent with same name already exists
            if store.load_instruction(agent.name):
                console.print(
                    f"  [dim]Skipped[/dim] '{agent.name}' (already exists)"
                )
                continue
            store.save_instruction(agent)
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

    from writ.core.models import InstructionConfig
    from writ.utils import yaml_load

    count = 0
    for yaml_file in sorted(template_dir.glob("*.yaml")):
        try:
            data = yaml_load(yaml_file)
            agent = InstructionConfig(**data)
            if store.load_instruction(agent.name):
                console.print(f"  [dim]Skipped[/dim] '{agent.name}' (already exists)")
                continue
            store.save_instruction(agent)
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


def _install_writ_context(detected_formats: list[str]) -> None:
    """Write writ-context rule to detected IDE directories.

    Falls back to ``.writ/rules/writ-context.md`` when no IDE directory
    is detected -- never creates IDE directories that don't already exist.
    """
    context_file = _BUILTIN_ROOT / "writ-context.md"
    if not context_file.exists():
        return

    content = context_file.read_text(encoding="utf-8").strip()

    cfg = InstructionConfig(
        name="writ-context",
        description="writ CLI command reference (auto-generated)",
        task_type="rule",
        instructions=content,
        tags=["writ", "meta"],
        composition=CompositionConfig(project_context=False),
        format_overrides=FormatOverrides(
            cursor=CursorOverrides(
                description="writ CLI command reference",
                always_apply=True,
            ),
        ),
    )
    store.save_instruction(cfg)

    if not detected_formats:
        console.print(
            "[green]Saved[/green] writ-context to .writ/rules/writ-context.yaml"
        )
        return

    root = Path.cwd()
    for fmt in detected_formats:
        if fmt == "cursor":
            path = CursorFormatter().write(cfg, content, root=root)
        elif fmt == "claude_rules":
            path = ClaudeRulesFormatter().write(cfg, content, root=root)
        elif fmt == "kiro_steering":
            path = KiroSteeringFormatter().write(cfg, content, root=root)
        else:
            continue
        console.print(f"[green]Wrote[/green] writ-context -> {path}")


def list_available_templates() -> list[str]:
    """List available built-in templates."""
    if not _TEMPLATE_ROOT.is_dir():
        return []
    return [
        d.name
        for d in sorted(_TEMPLATE_ROOT.iterdir())
        if d.is_dir() and not d.name.startswith("_")
    ]
