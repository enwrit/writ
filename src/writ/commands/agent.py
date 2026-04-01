"""writ add/list/remove -- Instruction management."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from writ.core import store
from writ.core.formatter import get_formatter
from writ.core.models import CompositionConfig, InstructionConfig
from writ.utils import console, slugify


def _require_init() -> None:
    """Ensure .writ/ is initialized."""
    if not store.is_initialized():
        console.print("[red]Not initialized.[/red] Run [cyan]writ init[/cyan] first.")
        raise typer.Exit(1)


def _detect_ide_formats() -> list[str]:
    """Detect which IDE rule directories exist (safe, non-intrusive formats)."""
    root = Path.cwd()
    formats: list[str] = []
    if (root / ".cursor").is_dir():
        formats.append("cursor")
    if (root / ".claude").is_dir():
        formats.append("claude_rules")
    if (root / ".kiro").is_dir():
        formats.append("kiro_steering")
    return formats


def _write_to_ide(
    cfg: InstructionConfig, content: str, *, formats: list[str] | None = None,
) -> list[str]:
    """Write instruction to detected IDE rule directories. Returns written paths."""
    target_formats = formats or _detect_ide_formats()
    if not target_formats:
        return []
    root = Path.cwd()
    written: list[str] = []
    for fmt in target_formats:
        try:
            formatter = get_formatter(fmt)
            path = formatter.write(cfg, content, root=root)
            written.append(str(path))
            console.print(f"  [green]Wrote[/green] {fmt} -> {path}")
        except (KeyError, Exception):  # noqa: BLE001
            pass
    return written


# ---------------------------------------------------------------------------
# writ add  (unified: create / library / Hub / --from prpm / --file / --template)
# ---------------------------------------------------------------------------

def add(
    name: Annotated[
        str | None, typer.Argument(help="Instruction name to add or fetch.")
    ] = None,
    description: Annotated[
        str, typer.Option("--description", "-d", help="Short description.")
    ] = "",
    instructions: Annotated[
        str | None,
        typer.Option("--instructions", "-i", help="Instruction content text."),
    ] = None,
    tags: Annotated[
        str | None, typer.Option("--tags", help="Comma-separated tags.")
    ] = None,
    inherits_from: Annotated[
        str | None,
        typer.Option("--inherits-from", help="Comma-separated parent instruction names."),
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
        typer.Option("--file", help="Import from a markdown file (or directory of files)."),
    ] = None,
    task_type: Annotated[
        str | None,
        typer.Option("--task-type", help="Content category (agent, rule, context, program)."),
    ] = None,
    from_source: Annotated[
        str | None,
        typer.Option("--from", help="Source registry: prpm, skills, url."),
    ] = None,
    format_flag: Annotated[
        str | None,
        typer.Option("--format", "-f", help="Write to specific format (cursor, claude-rules)."),
    ] = None,
    lib: Annotated[
        bool, typer.Option("--lib", help="Force fetch from personal library."),
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite if instruction already exists."),
    ] = False,
) -> None:
    """Add an instruction to this project.

    Searches your personal library and the Hub (6,000+ instructions) automatically.
    Creates a new blank instruction if nothing is found.

    \b
    Examples:
      writ add reviewer                         # fetch from library/Hub or create new
      writ add reviewer --lib                    # force fetch from personal library
      writ add @bfollington/terma-godot          # fetch from Hub (PRPM, enwrit, etc.)
      writ add my-rules --from prpm              # fetch latest directly from PRPM
      writ add --template fullstack              # load a team of instructions
      writ add --template list                   # show available templates
      writ add --file my-rules.md                # import a markdown file
      writ add --file .cursor/rules/             # import all files in a directory
      writ add reviewer --format claude-rules    # write to a specific format only
    """
    if template == "list":
        _show_available_templates()
        return

    _require_init()

    if template:
        from writ.commands.init import load_template
        load_template(template)
        return

    if file:
        _import_from_file(
            file,
            name_override=name,
            description_override=description or None,
            tags_override=tags,
            task_type_override=task_type,
        )
        return

    if not name:
        console.print("[red]Provide a name, --file, or --template.[/red]")
        console.print()
        console.print("Examples:")
        console.print('  [cyan]writ add reviewer -d "Code reviewer"[/cyan]')
        console.print("  [cyan]writ add --file my-rules.md[/cyan]")
        console.print("  [cyan]writ add --template fullstack[/cyan]")
        console.print("  [cyan]writ add --template list[/cyan]  (see all templates)")
        raise typer.Exit(1)

    if from_source:
        _add_from_source(name, from_source, format_flag=format_flag)
        return

    # --lib: skip project check, go straight to personal library
    if lib:
        cfg = _try_library(name)
        if cfg:
            store.save_instruction(cfg)
            _print_added(cfg, source="library")
            _write_to_ide(cfg, cfg.instructions, formats=_resolve_formats(format_flag))
            return
        console.print(f"[red]'{name}' not found in personal library.[/red]")
        console.print("Save with: [cyan]writ save <name>[/cyan]")
        raise typer.Exit(1)

    existing = store.load_instruction(name)
    if existing and not force:
        console.print(f"[yellow]'{name}' already exists.[/yellow] Use --force to overwrite.")
        raise typer.Exit(1)

    # If user provided --instructions, they want to create -- skip library/Hub
    if instructions is None:
        # 1. Check personal library
        cfg = _try_library(name)
        if cfg:
            store.save_instruction(cfg)
            _print_added(cfg, source="library")
            _write_to_ide(cfg, cfg.instructions, formats=_resolve_formats(format_flag))
            return

        # 2. Search Hub
        cfg = _try_hub(name)
        if cfg:
            store.save_instruction(cfg)
            _print_added(cfg, source="Hub")
            _write_to_ide(cfg, cfg.instructions, formats=_resolve_formats(format_flag))
            return

    # 3. Create new instruction
    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    inherit_list = (
        [i.strip() for i in inherits_from.split(",")]
        if inherits_from
        else []
    )

    cfg = InstructionConfig(
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
    store.save_instruction(cfg)
    _print_added(cfg)
    _write_to_ide(cfg, cfg.instructions, formats=_resolve_formats(format_flag))


def _resolve_formats(format_flag: str | None) -> list[str] | None:
    """Convert --format flag to a format list, or None for auto-detect."""
    if not format_flag:
        return None
    fmt = format_flag.replace("-", "_")
    return [fmt]


def _try_library(name: str) -> InstructionConfig | None:
    """Check personal library (local + remote) for an instruction."""
    from writ.core import auth

    cfg = store.load_from_library(name)
    if cfg:
        return cfg

    if auth.is_logged_in():
        try:
            from writ.integrations.registry import RegistryClient
            client = RegistryClient()
            data = client.pull_from_library(name)
            if data:
                return _cfg_from_dict(data)
        except Exception:  # noqa: BLE001
            pass
    return None


def _try_hub(name: str) -> InstructionConfig | None:
    """Search Hub for an instruction and download it."""
    try:
        from writ.integrations.registry import RegistryClient
        client = RegistryClient()

        results = client.hub_search(name, limit=1, semantic=True)
        if not results:
            return None

        best = results[0]
        best_name = best.get("name", "")
        source = best.get("source", "enwrit")

        if best_name.lower() != name.lower():
            console.print(
                f"  [dim]Hub match:[/dim] [cyan]{best_name}[/cyan] "
                f"(Score: {best.get('writ_score', '--')})"
            )

        data = client.hub_download(source, best_name)
        if data:
            return _cfg_from_hub(data, source=source)
    except Exception:  # noqa: BLE001
        pass
    return None


def _cfg_from_dict(data: dict) -> InstructionConfig | None:
    """Build InstructionConfig from a library/registry API response."""
    nm = data.get("name")
    if not nm:
        return None
    try:
        return InstructionConfig(
            name=nm,
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            tags=data.get("tags", []),
            instructions=data.get("instructions", ""),
            task_type=data.get("task_type"),
        )
    except Exception:  # noqa: BLE001
        return None


def _cfg_from_hub(data: dict, *, source: str = "") -> InstructionConfig | None:
    """Build InstructionConfig from a Hub download response."""
    nm = data.get("name") or data.get("display_name")
    if not nm:
        return None
    instr = data.get("instructions") or data.get("content") or ""
    try:
        cfg = InstructionConfig(
            name=slugify(nm),
            description=data.get("description", ""),
            instructions=instr,
            tags=data.get("tags", []),
            version=data.get("version", "1.0.0"),
            task_type=data.get("task_type"),
            author=data.get("author", source or "hub"),
        )
        if source:
            cfg.source = f"{source}/{nm}"
        return cfg
    except Exception:  # noqa: BLE001
        return None


def _add_from_source(name: str, source: str, *, format_flag: str | None = None) -> None:
    """Fetch from a specific source (prpm, skills, url) and save."""
    if source == "prpm":
        from writ.integrations.prpm import PRPMIntegration
        prpm = PRPMIntegration()
        cfg = prpm.install(name)
        if not cfg:
            console.print(f"[red]Package '{name}' not found on PRPM.[/red]")
            raise typer.Exit(1)
    elif source == "skills":
        from writ.integrations.skills import SkillsIntegration
        skills = SkillsIntegration()
        cfg = skills.install(name)
        if not cfg:
            console.print(f"[red]Skill '{name}' not found.[/red]")
            raise typer.Exit(1)
    elif source == "url":
        from writ.integrations.url import URLIntegration
        url_int = URLIntegration()
        cfg = url_int.install(name)
        if not cfg:
            console.print(f"[red]Could not install from URL:[/red] {name}")
            raise typer.Exit(1)
    else:
        console.print(f"[red]Unknown source '{source}'.[/red] Use: prpm, skills, url.")
        raise typer.Exit(1)

    store.save_instruction(cfg)
    _print_added(cfg, source=source)
    _write_to_ide(cfg, cfg.instructions, formats=_resolve_formats(format_flag))


# ---------------------------------------------------------------------------
# writ list
# ---------------------------------------------------------------------------

def list_agents(
    library: Annotated[
        bool, typer.Option("--library", "-L", help="List personal library instead of project.")
    ] = False,
) -> None:
    """List instructions in this project (or personal library with --library)."""
    if library:
        _list_library()
        return

    _require_init()

    agents = store.list_instructions()
    if not agents:
        console.print(
            "[yellow]No instructions found.[/yellow] "
            "Run [cyan]writ add <name>[/cyan] to add one."
        )
        return

    table = Table(title="Project Instructions", show_lines=False)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Type", style="dim", justify="center")
    table.add_column("Description", max_width=50)
    table.add_column("Tags", style="dim")
    table.add_column("Version", justify="center")

    for inst in agents:
        desc = _safe_text(inst.description, max_len=80) if inst.description else "-"
        table.add_row(
            inst.name,
            inst.task_type or "agent",
            desc,
            ", ".join(inst.tags) if inst.tags else "-",
            inst.version,
        )

    console.print(table)
    console.print(f"\n[dim]{len(agents)} instruction(s) total[/dim]")


def _list_library() -> None:
    """List personal library contents (local + remote)."""
    from writ.core import auth
    from writ.integrations.registry import RegistryClient

    local_items = store.list_library()
    local_names = {a.name for a in local_items}

    remote_list: list[dict] = []
    remote_names: set[str] = set()
    if auth.is_logged_in():
        client = RegistryClient()
        remote_list = [a for a in client.list_library() if "name" in a]
        remote_names = {a["name"] for a in remote_list}

    all_names = sorted(local_names | remote_names)

    if not all_names:
        console.print("[yellow]Your personal library is empty.[/yellow]")
        console.print("Save instructions with: [cyan]writ save <name>[/cyan]")
        return

    local_map = {a.name: a for a in local_items}
    remote_map = {a["name"]: a for a in remote_list}

    table = Table(title="Personal Library", show_lines=False)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Description", max_width=50)
    table.add_column("Version", justify="center")
    if auth.is_logged_in():
        table.add_column("Local", justify="center")
        table.add_column("Remote", justify="center")

    for nm in all_names:
        local_inst = local_map.get(nm)
        is_local = nm in local_names
        is_remote = nm in remote_names
        remote_info = remote_map.get(nm, {})
        desc = (local_inst.description if local_inst else remote_info.get("description")) or "-"
        desc = _safe_text(desc, max_len=80)
        ver = (local_inst.version if local_inst else remote_info.get("version")) or "-"

        if auth.is_logged_in():
            table.add_row(
                nm, desc, ver,
                "[green]yes[/green]" if is_local else "[dim]no[/dim]",
                "[green]yes[/green]" if is_remote else "[dim]no[/dim]",
            )
        else:
            table.add_row(nm, desc, ver)

    console.print(table)
    console.print(f"\n[dim]{len(all_names)} instruction(s) in library[/dim]")
    console.print("Add to project: [cyan]writ add <name>[/cyan]")


# ---------------------------------------------------------------------------
# writ remove
# ---------------------------------------------------------------------------

def remove(
    name: Annotated[str, typer.Argument(help="Instruction name to remove.")],
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip confirmation.")
    ] = False,
) -> None:
    """Remove an instruction from this project."""
    _require_init()

    inst = store.load_instruction(name)
    if not inst:
        console.print(
            f"[red]'{name}' not found.[/red] "
            "Run [cyan]writ list[/cyan] to see available instructions."
        )
        raise typer.Exit(1)

    if not yes:
        confirm = typer.confirm(f"Remove '{name}'?")
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit()

    store.remove_instruction(name)
    console.print(f"[green]Removed[/green] {name}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_text(text: str, *, max_len: int = 80) -> str:
    """Truncate and make text safe for Windows cp1252 console output."""
    text = text.replace("\n", " ").strip()
    if len(text) > max_len:
        text = text[:max_len - 3] + "..."
    try:
        text.encode("cp1252")
    except (UnicodeEncodeError, LookupError):
        text = text.encode("ascii", errors="replace").decode("ascii")
    return text


def _print_added(cfg: InstructionConfig, source: str = "") -> None:
    """Content-focused output after adding an instruction."""
    tokens = len(cfg.instructions.split()) if cfg.instructions else 0
    if tokens >= 1000:
        token_str = f"{tokens / 1000:.1f}k tokens"
    else:
        token_str = f"{tokens} tokens"
    type_label = cfg.task_type or "agent"
    src = f" from {source}" if source else ""
    console.print(f"[green]Added[/green] '{cfg.name}' ({type_label}, {token_str}){src}")


def _import_from_file(
    file_path: str,
    *,
    name_override: str | None = None,
    description_override: str | None = None,
    tags_override: str | None = None,
    task_type_override: str | None = None,
) -> None:
    """Import one file or all supported files in a directory."""
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
        console.print(f"[yellow]'{cfg.name}' already exists.[/yellow] Use --force to overwrite.")
        raise typer.Exit(1)

    store.save_instruction(cfg)
    _print_added(cfg)


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
