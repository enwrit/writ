"""writ install -- Install agents from external registries."""

from __future__ import annotations

from typing import Annotated

import typer

from writ.core import store
from writ.utils import console


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
        # Default: try our own registry (Phase 3)
        console.print(
            "[yellow]Registry not available yet.[/yellow] Use --from prpm, skills, or url."
        )
        console.print("\nExamples:")
        console.print("  [cyan]writ install react-reviewer --from prpm[/cyan]")
        console.print("  [cyan]writ install --from url https://example.com/agent.yaml[/cyan]")
        raise typer.Exit(1)
    else:
        console.print(f"[red]Unknown source '{from_source}'.[/red] Use: prpm, skills, url.")
        raise typer.Exit(1)


def _install_from_prpm(name: str) -> None:
    """Install from PRPM registry."""
    try:
        from writ.integrations.prpm import PRPMIntegration
        prpm = PRPMIntegration()
        agent = prpm.install(name)
        if agent:
            store.save_agent(agent)
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
            store.save_agent(agent)
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
            store.save_agent(agent)
            console.print(f"[green]Installed[/green] '{agent.name}' from URL")
        else:
            console.print(f"[red]Could not install from URL:[/red] {url}")
            raise typer.Exit(1)
    except ImportError:
        console.print("[red]URL integration not available.[/red]")
        raise typer.Exit(1) from None
