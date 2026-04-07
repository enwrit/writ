"""writ init -- Initialize writ in the current repository.

Scans the repo, creates .writ/, detects IDEs, and installs writ-context.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel

from writ.core import scanner, store
from writ.core.formatter import (
    IDE_PATHS,
    IDEFormatter,
    _build_filename,
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
            help="Import detected instruction files into .writ/.",
        ),
    ] = True,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Reinitialize even if .writ/ already exists."),
    ] = False,
) -> None:
    """Initialize writ in the current repository.

    Scans the repo for existing instruction files, detects project context,
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

    # 3. Scan for existing instruction files and optionally import
    existing = scanner.detect_existing_files()
    imported_count = 0
    if existing:
        console.print(f"\n[cyan]Found {len(existing)} existing instruction file(s):[/cyan]")
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

    # 6. Install built-in skills to detected IDEs
    skills_installed = _install_builtin_skills(detected_formats)

    # 7. Load template if specified
    if template:
        load_template(template)

    # 8. Summary
    instr_count = len(store.list_instructions())
    console.print()
    summary = "[bold green]writ initialized![/bold green]\n\n"
    if instr_count:
        summary += (
            f"Instructions: {instr_count} "
            f"({imported_count} imported)\n"
        )
    if skills_installed:
        summary += f"Built-in skills: {skills_installed} installed\n"
    summary += (
        "\n"
        "Next steps:\n"
        "  [cyan]writ search <query>[/cyan]    Find instructions (6,000+ in Hub)\n"
        "  [cyan]writ add <name>[/cyan]        Add from Hub, library, or create new\n"
        "  [cyan]writ lint <file>[/cyan]       Score instruction quality\n"
        "  [cyan]writ list[/cyan]              List instructions in this project\n"
        "  [cyan]writ plan review <file>[/cyan] AI-powered plan review\n"
        "  [cyan]writ docs check[/cyan]        Documentation health scan\n"
        "\n"
        "  [dim]writ save <name>[/dim]       [dim]Save to personal library (cross-device)[/dim]\n"
        "  [dim]writ connect / chat[/dim]    [dim]Agent-to-agent communication[/dim]\n"
        "  [dim]writ review / threads[/dim]  [dim]Knowledge sharing[/dim]\n"
        "  [dim]writ mcp install[/dim]      [dim]Connect via MCP protocol (opt-in)[/dim]\n"
        "\n"
        "[dim]Star us on GitHub: https://github.com/enwrit/writ[/dim]"
    )
    console.print(Panel.fit(summary, title="writ", border_style="green"))


def _detect_active_tools() -> list[str]:
    """Detect which IDE/CLI tools are active in this repo.

    Only auto-detects directory-based formats where writ writes its own
    separate files (safe, non-intrusive).  Shared-file formats (AGENTS.md,
    CLAUDE.md, .windsurfrules, copilot-instructions.md) are available but
    only activated when the user explicitly passes ``--format <name>``.
    """
    root = Path.cwd()
    return [
        key for key, cfg in IDE_PATHS.items()
        if (root / cfg.detect).exists()
    ]


def _import_existing_files(existing: list[dict[str, str]]) -> int:
    """Parse and import detected existing instruction files. Returns count imported."""
    count = 0
    for item in existing:
        inst = scanner.parse_existing_file(item)
        if inst:
            if store.load_instruction(inst.name):
                console.print(
                    f"  [dim]Skipped[/dim] '{inst.name}' (already exists)"
                )
                continue
            store.save_instruction(inst)
            console.print(f"  [green]Imported[/green] '{inst.name}' from {item['format']}")
            count += 1
    if count:
        console.print(f"[green]Imported {count} instruction(s)[/green] from existing files")
    return count


def load_template(template_name: str) -> int:
    """Load instructions from a built-in template. Returns count loaded.

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
            console.print(f"  [green]Created[/green] {agent.name}")
            count += 1
        except Exception as e:  # noqa: BLE001
            console.print(f"  [red]Failed[/red] to load {yaml_file.name}: {e}")

    if count:
        console.print(
            f"[green]Loaded {count} instruction(s)[/green] from '{template_name}' template"
        )
    else:
        console.print(f"[yellow]No new instructions from template '{template_name}'[/yellow]")

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
        if fmt not in IDE_PATHS:
            continue
        formatter = IDEFormatter(fmt)
        path = formatter.write(cfg, content, root=root)
        console.print(f"[green]Wrote[/green] writ-context -> {path}")


def _install_builtin_skills(detected_formats: list[str]) -> int:
    """Install built-in skills from _builtin/skills/ to IDE skill directories.

    Skills go to dedicated skill dirs (e.g. .cursor/skills/writ/) NOT to
    rules dirs. This keeps skills separate from project-specific rules.
    Returns the number of skills installed.
    """
    skills_dir = _BUILTIN_ROOT / "skills"
    if not skills_dir.is_dir():
        return 0

    skill_files = sorted(skills_dir.glob("*.md"))
    if not skill_files:
        return 0

    root = Path.cwd()
    count = 0

    from writ.utils import yaml_dumps

    for skill_file in skill_files:
        skill_name = skill_file.stem
        content = skill_file.read_text(encoding="utf-8").strip()
        writ_name = f"writ-{skill_name}"

        cfg = InstructionConfig(
            name=writ_name,
            description=f"Built-in skill: {skill_name.replace('-', ' ')}",
            task_type="rule",
            instructions=content,
            tags=["writ", "skill", "builtin"],
            composition=CompositionConfig(project_context=False),
            format_overrides=FormatOverrides(
                cursor=CursorOverrides(
                    description=f"Built-in skill: {skill_name.replace('-', ' ')}",
                    always_apply=True,
                ),
            ),
        )
        store.save_instruction(cfg)

        wrote_to_ide = False
        for fmt in detected_formats:
            if fmt not in IDE_PATHS:
                continue
            ide_config = IDE_PATHS[fmt]
            skills_entry = ide_config.skills
            skill_dir = root / skills_entry.directory
            skill_dir.mkdir(parents=True, exist_ok=True)
            filename = _build_filename(skills_entry, skill_name)
            path = skill_dir / filename

            if skills_entry.frontmatter_fn:
                fm_dict = skills_entry.frontmatter_fn(cfg)
                if fm_dict:
                    fm_str = yaml_dumps(fm_dict).strip()
                    path.write_text(
                        f"---\n{fm_str}\n---\n\n{content}\n",
                        encoding="utf-8",
                    )
                else:
                    path.write_text(content + "\n", encoding="utf-8")
            else:
                path.write_text(content + "\n", encoding="utf-8")
            wrote_to_ide = True

        if wrote_to_ide:
            count += 1

    if count:
        skill_names = ", ".join(f.stem for f in skill_files)
        console.print(
            f"[green]Installed {count} built-in skill(s):[/green] {skill_names}",
        )

    return count


def list_available_templates() -> list[str]:
    """List available built-in templates."""
    if not _TEMPLATE_ROOT.is_dir():
        return []
    return [
        d.name
        for d in sorted(_TEMPLATE_ROOT.iterdir())
        if d.is_dir() and not d.name.startswith("_")
    ]
