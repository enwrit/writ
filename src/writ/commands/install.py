"""writ install -- Install agents from external registries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import typer

from writ.core import store
from writ.utils import console

if TYPE_CHECKING:
    from writ.core.models import InstructionConfig


def install_command(
    name: Annotated[str, typer.Argument(help="Agent/package name to install.")],
    from_source: Annotated[
        str | None,
        typer.Option("--from", help="Source registry: prpm, skills, url."),
    ] = None,
) -> None:
    """Install an agent from a registry or URL.

    Examples:
        writ install react-reviewer --from prpm
        writ install typescript-tools --from skills
        writ install --from url https://github.com/user/agents/blob/main/reviewer.yaml
    """
    if not store.is_initialized():
        console.print("[red]Not initialized.[/red] Run [cyan]writ init[/cyan] first.")
        raise typer.Exit(1)

    if from_source == "prpm":
        _install_from_prpm(name)
    elif from_source == "skills":
        _install_from_skills(name)
    elif from_source == "url":
        _install_from_url(name)
    elif from_source is None:
        _install_from_registry(name)
    else:
        console.print(f"[red]Unknown source '{from_source}'.[/red] Use: prpm, skills, url.")
        raise typer.Exit(1)


def _install_from_registry(name: str) -> None:
    """Install from the enwrit public registry.

    Handles both regular instructions and templates. Templates have an
    ``includes`` list which is resolved by pulling each referenced
    instruction from the registry.
    """
    try:
        from writ.integrations.registry import RegistryClient

        client = RegistryClient()
        data = client.pull_public_agent(name)
        if not data:
            _not_found(name)
            return

        cfg = _cfg_from_registry(data)
        if cfg is None:
            _not_found(name)
            return

        if cfg.task_type == "template" and cfg.includes:
            _install_template(cfg, client)
        else:
            _save_with_source(cfg)
            console.print(
                f"[green]Installed[/green] '{cfg.name}' "
                "from enwrit registry"
            )
        return
    except typer.Exit:
        raise
    except Exception:  # noqa: BLE001
        pass

    _not_found(name)


def _cfg_from_registry(data: dict) -> InstructionConfig | None:
    """Build an InstructionConfig from a registry API response.

    Checks multiple locations for the ``includes`` field:
    1. Top-level ``includes`` key (future API extension)
    2. ``metadata.includes`` (JSONB metadata)
    3. ``config_yaml`` (full YAML stored on push, always has it)
    """
    from writ.core.models import InstructionConfig
    from writ.utils import yaml_loads_safe

    name = data.get("name")
    if not name:
        return None
    try:
        includes: list[str] = data.get("includes") or []

        if not includes:
            meta = data.get("metadata") or {}
            if isinstance(meta, dict):
                includes = meta.get("includes", [])

        if not includes:
            config_yaml = data.get("config_yaml", "")
            if config_yaml:
                parsed = yaml_loads_safe(config_yaml)
                includes = parsed.get("includes", [])

        return InstructionConfig(
            name=name,
            description=data.get("description", ""),
            instructions=data.get("instructions", ""),
            tags=data.get("tags", []),
            version=data.get("version", "1.0.0"),
            task_type=data.get("task_type"),
            includes=includes if isinstance(includes, list) else [],
        )
    except Exception:  # noqa: BLE001
        return None


def _save_with_source(cfg: InstructionConfig) -> None:
    """Save an instruction with source tracking."""
    cfg.source = f"enwrit.com/{cfg.name}@{cfg.version}"
    store.save_instruction(cfg)


def _install_template(
    template: InstructionConfig,
    client: object,
) -> None:
    """Resolve and install all instructions referenced by a template."""
    console.print(
        f"[bold]Installing template '{template.name}'[/bold] "
        f"({len(template.includes)} instructions)\n"
    )
    installed = 0
    for ref_name in template.includes:
        existing = store.load_instruction(ref_name)
        if existing:
            console.print(
                f"  [dim]skip[/dim]  {ref_name} (already exists)"
            )
            continue

        data = client.pull_public_agent(ref_name)  # type: ignore[attr-defined]
        if not data:
            console.print(f"  [red]fail[/red]  {ref_name} (not found)")
            continue

        cfg = _cfg_from_registry(data)
        if cfg is None:
            console.print(f"  [red]fail[/red]  {ref_name} (bad data)")
            continue

        _save_with_source(cfg)
        console.print(f"  [green]installed[/green]  {cfg.name}")
        installed += 1

    console.print(
        f"\n[bold]{installed}[/bold] instruction(s) installed "
        f"from template '{template.name}'."
    )
    if template.instructions:
        console.print(f"\n[dim]{template.description}[/dim]")


def _not_found(name: str) -> None:
    """Print not-found message and exit."""
    console.print(
        f"[yellow]'{name}' not found on enwrit registry.[/yellow]"
    )
    console.print(
        "\nTry specifying a source:\n"
        "  [cyan]writ install <name> --from prpm[/cyan]\n"
        "  [cyan]writ install <name> --from skills[/cyan]\n"
        "  [cyan]writ install --from url <url>[/cyan]"
    )
    raise typer.Exit(1)


def _install_from_prpm(name: str) -> None:
    """Install from PRPM registry."""
    try:
        from writ.integrations.prpm import PRPMIntegration
        prpm = PRPMIntegration()
        agent = prpm.install(name)
        if agent:
            store.save_instruction(agent)
            console.print(f"[green]Installed[/green] '{agent.name}' from PRPM")
        else:
            console.print(f"[red]Package '{name}' not found on PRPM.[/red]")
            raise typer.Exit(1)
    except ImportError:
        console.print("[red]PRPM integration not available.[/red]")
        raise typer.Exit(1) from None


def _install_from_skills(name: str) -> None:
    """Install from Agent Skills CLI."""
    try:
        from writ.integrations.skills import SkillsIntegration
        skills = SkillsIntegration()
        agent = skills.install(name)
        if agent:
            store.save_instruction(agent)
            console.print(f"[green]Installed[/green] '{agent.name}' from Agent Skills CLI")
        else:
            console.print(f"[red]Skill '{name}' not found.[/red]")
            raise typer.Exit(1)
    except ImportError:
        console.print("[red]Skills integration not available.[/red]")
        raise typer.Exit(1) from None


def _install_from_url(url: str) -> None:
    """Install from a URL (YAML file or git repo)."""
    try:
        from writ.integrations.url import URLIntegration
        url_int = URLIntegration()
        agent = url_int.install(url)
        if agent:
            store.save_instruction(agent)
            console.print(f"[green]Installed[/green] '{agent.name}' from URL")
        else:
            console.print(f"[red]Could not install from URL:[/red] {url}")
            raise typer.Exit(1)
    except ImportError:
        console.print("[red]URL integration not available.[/red]")
        raise typer.Exit(1) from None
