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
    cleanup_legacy_skill_files,
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

# Hand-crafted "When to read" descriptions for built-in skills.
# User-added skills fall back to their stored description field.
_BUILTIN_SKILL_HINTS: dict[str, str] = {
    "writ-commands": (
        "**Start here.** Full command reference for all `writ` features. "
        "Read whenever running, configuring, or troubleshooting any `writ` "
        "command, editing `.writ/` config, or unsure which writ feature "
        "applies to a task"
    ),
    "writ-plan-skill": "Writing implementation plans",
    "writ-doc-health": "Documentation health checks (`writ docs check/update`)",
    "writ-doc-maintenance": "Maintaining project documentation",
    "writ-pre-commit-checks": "Pre-commit verification",
    "writ-code-simplifier": "Simplifying complex code",
    "writ-tech-debt-fixer": "Reducing technical debt",
    "writ-security-scan": "Security review",
    "writ-autoresearch": "Research tasks",
    "writ-verify-skill": "Verifying changes and claims",
    "writ-skill-creator-skill": "Authoring new skills",
    "writ-superpower-skill": "Advanced multi-step agent workflows",
}


def _refresh_writ_context_if_stale() -> bool:
    """Silently overwrite writ-context in IDE dirs if the bundled version changed."""
    context_file = _BUILTIN_ROOT / "writ-context.md"
    if not context_file.exists():
        return False

    template = context_file.read_text(encoding="utf-8").strip()
    bundled = template.replace(
        "{skills_table}", _build_skills_table("skills"),
    )

    existing_cfg = store.load_instruction("writ-context")
    if existing_cfg and existing_cfg.instructions.strip() == bundled:
        return False

    detected_formats = [
        key for key, cfg in IDE_PATHS.items()
        if (Path.cwd() / cfg.detect).exists()
    ]

    _install_writ_context(detected_formats)
    return True


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
        refreshed = _refresh_writ_context_if_stale()
        console.print(
            "[yellow]Already initialized.[/yellow] Use --force to reinitialize."
        )
        if refreshed:
            console.print("[green]Refreshed[/green] writ-context to latest version.")
        raise typer.Exit()

    # 1. Create .writ/ directory structure (clean content dirs on --force)
    writ_dir = store.init_project_store(clean=force)
    console.print(f"[green]Created[/green] {writ_dir.relative_to(Path.cwd())}/")

    # 1b. Migrate legacy flat-file skill outputs to the folder-per-skill layout.
    #     Always safe to run; only removes files writ itself wrote in the
    #     old ``{ide}/skills/writ/`` parent dir.
    removed_legacy = cleanup_legacy_skill_files(Path.cwd())
    if removed_legacy:
        console.print(
            f"[dim]Migrated[/dim] {len(removed_legacy)} legacy skill file(s) "
            "to folder-per-skill layout"
        )

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

    # 5. Install built-in skills to detected IDEs (before writ-context so table is populated)
    skills_installed = _install_builtin_skills(detected_formats)

    # 5b. Install writ-agent to detected IDE agent dirs
    _install_builtin_agents(detected_formats)

    # 6. Install writ-context rule (reads skill list from store for the table)
    _install_writ_context(detected_formats)

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
        "  [cyan]writ docs init[/cyan]         Set up documentation health tracking\n"
        "  [cyan]writ docs check[/cyan]        Documentation health scan\n"
        "  [cyan]writ docs update[/cyan]       Review and fix documentation issues\n"
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


def _build_skills_table(
    skills_dir: str,
    *,
    extra_rows: list[str] | None = None,
) -> str:
    """Build a markdown table of all installed skills for writ-context.

    *extra_rows* are user-added table rows (from manual edits) that are
    preserved across rebuilds.  They are appended after all store-based rows.
    """
    skills = [
        cfg for cfg in store.list_instructions()
        if cfg.task_type == "skill"
    ]

    # Stable ordering: built-in skills first (in map order), then user skills alphabetically
    builtin_order = list(_BUILTIN_SKILL_HINTS.keys())
    builtin_set = set(builtin_order)

    builtin_skills = [s for name in builtin_order for s in skills if s.name == name]
    user_skills = sorted(
        [s for s in skills if s.name not in builtin_set],
        key=lambda s: s.name,
    )

    rows = ["| Skill | When to read |", "|---|---|"]
    generated_paths: set[str] = set()
    for s in builtin_skills + user_skills:
        hint = _BUILTIN_SKILL_HINTS.get(s.name, s.description or s.name)
        folder = s.name if s.name.startswith("writ-") else f"writ-{s.name}"
        path = f"{skills_dir}/{folder}/SKILL.md"
        rows.append(f"| {path} | {hint} |")
        generated_paths.add(path)

    if extra_rows:
        for row in extra_rows:
            # Skip if the row references a path we already generated
            already_covered = any(gp in row for gp in generated_paths)
            if not already_covered:
                rows.append(row)

    return "\n".join(rows)


def _extract_user_rows(file_path: Path, skills_dir: str) -> list[str]:
    """Extract manually-added table rows from an existing writ-context file.

    Returns rows that reference paths outside the ``writ-*/SKILL.md`` pattern
    managed by writ, so they survive rebuilds.
    """
    if not file_path.exists():
        return []
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError:
        return []

    user_rows: list[str] = []
    writ_prefix = f"{skills_dir}/writ-"
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("| Skill") or stripped.startswith("|---"):
            continue
        # Row managed by writ -- skip (will be regenerated)
        if writ_prefix in stripped:
            continue
        user_rows.append(stripped)
    return user_rows


def _writ_context_cfg(content: str) -> InstructionConfig:
    """Build the InstructionConfig for writ-context."""
    return InstructionConfig(
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


def _install_writ_context(detected_formats: list[str]) -> None:
    """Write writ-context rule to detected IDE directories.

    Falls back to ``.writ/rules/writ-context.md`` when no IDE directory
    is detected -- never creates IDE directories that don't already exist.
    """
    context_file = _BUILTIN_ROOT / "writ-context.md"
    if not context_file.exists():
        return

    template = context_file.read_text(encoding="utf-8").strip()

    generic = template.replace(
        "{skills_table}", _build_skills_table("skills"),
    )
    cfg = _writ_context_cfg(generic)
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
        ide_cfg = IDE_PATHS[fmt]
        content = template.replace(
            "{skills_table}", _build_skills_table(ide_cfg.skills.directory),
        )
        formatter = IDEFormatter(fmt)
        path = formatter.write(cfg, content, root=root)
        console.print(f"[green]Wrote[/green] writ-context -> {path}")


def _writ_context_path(ide_cfg: "IDEConfig", root: Path) -> Path:
    """Resolve the file path where writ-context lives for a given IDE."""
    rules = ide_cfg.rules
    return root / rules.directory / f"writ-context.{rules.extension}"


def rebuild_writ_context() -> None:
    """Rebuild writ-context in all detected IDE dirs from current store state.

    Called after add/remove of skills so the table stays in sync.
    Preserves any manually-added table rows the user inserted.
    """
    if not store.is_initialized():
        return

    context_file = _BUILTIN_ROOT / "writ-context.md"
    if not context_file.exists():
        return

    template = context_file.read_text(encoding="utf-8").strip()
    root = Path.cwd()

    generic = template.replace(
        "{skills_table}", _build_skills_table("skills"),
    )
    cfg = _writ_context_cfg(generic)
    store.save_instruction(cfg)

    for fmt, ide_cfg in IDE_PATHS.items():
        if not (root / ide_cfg.detect).exists():
            continue
        skills_dir = ide_cfg.skills.directory
        existing_path = _writ_context_path(ide_cfg, root)
        user_rows = _extract_user_rows(existing_path, skills_dir)
        content = template.replace(
            "{skills_table}",
            _build_skills_table(skills_dir, extra_rows=user_rows),
        )
        try:
            IDEFormatter(fmt).write(cfg, content, root=root)
        except Exception:  # noqa: BLE001
            pass


def _install_builtin_skills(detected_formats: list[str]) -> int:
    """Install built-in skills from _builtin/skills/ to IDE skill directories.

    Each skill is written as ``{ide}/skills/writ-<name>/SKILL.md`` per the
    AAIF Agent Skills folder convention.  Returns the number of skills
    installed.
    """
    skills_dir = _BUILTIN_ROOT / "skills"
    if not skills_dir.is_dir():
        return 0

    skill_files = sorted(skills_dir.glob("*.md"))
    if not skill_files:
        return 0

    root = Path.cwd()
    count = 0

    for skill_file in skill_files:
        skill_name = skill_file.stem
        content = skill_file.read_text(encoding="utf-8").strip()
        writ_name = f"writ-{skill_name}"

        cfg = InstructionConfig(
            name=writ_name,
            description=f"Built-in skill: {skill_name.replace('-', ' ')}",
            task_type="skill",
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
            try:
                IDEFormatter(fmt).write(cfg, content, root=root)
                wrote_to_ide = True
            except OSError:
                continue

        if wrote_to_ide:
            count += 1

    if count:
        skill_names = ", ".join(f.stem for f in skill_files)
        console.print(
            f"[green]Installed {count} built-in skill(s):[/green] {skill_names}",
        )

    return count


def _install_builtin_agents(detected_formats: list[str]) -> int:
    """Install built-in agent templates to IDE agent directories.

    Agents go to {IDE}/agents/ (e.g. .cursor/agents/writ-agent.mdc).
    Returns the number of agents installed.
    """
    agents_dir = _BUILTIN_ROOT / "agents"
    if not agents_dir.is_dir():
        return 0

    agent_files = sorted(agents_dir.glob("*.md"))
    if not agent_files:
        return 0

    root = Path.cwd()
    count = 0

    for agent_file in agent_files:
        agent_name = agent_file.stem
        content = agent_file.read_text(encoding="utf-8").strip()

        cfg = InstructionConfig(
            name=agent_name,
            description=f"Built-in agent: {agent_name.replace('-', ' ')}",
            task_type="agent",
            instructions=content,
            tags=["writ", "agent", "builtin"],
            composition=CompositionConfig(project_context=False),
        )
        store.save_instruction(cfg)

        wrote_to_ide = False
        for fmt in detected_formats:
            if fmt not in IDE_PATHS:
                continue
            try:
                IDEFormatter(fmt).write(cfg, content, root=root)
                wrote_to_ide = True
            except OSError:
                continue

        if wrote_to_ide:
            count += 1

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
