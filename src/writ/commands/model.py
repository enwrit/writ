"""writ model set/list/clear -- configure AI model for plan review."""

from __future__ import annotations

from typing import Annotated

import typer

from writ.core import store
from writ.core.models import ModelConfig
from writ.utils import console

_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-20250514",
    "gemini": "gemini-2.5-flash",
    "local": "default",
}

_DEFAULT_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com",
}

model_app = typer.Typer(
    name="model",
    help="Configure AI model for plan review and other AI features.",
    no_args_is_help=True,
)


@model_app.command(name="set")
def model_set(
    provider: Annotated[
        str,
        typer.Argument(
            help="Provider: openai, anthropic, gemini, or local.",
        ),
    ],
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", "-k", help="API key for cloud providers."),
    ] = None,
    model_name: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Specific model name (e.g. gpt-4o)."),
    ] = None,
    url: Annotated[
        str | None,
        typer.Option("--url", "-u", help="Custom endpoint URL (required for local)."),
    ] = None,
) -> None:
    """Set the AI model for plan review.

    \b
    Examples:
      writ model set openai --api-key sk-...
      writ model set anthropic --api-key sk-ant-... --model claude-sonnet-4-20250514
      writ model set gemini --api-key AIza...
      writ model set local --url http://localhost:1234/v1
    """
    provider = provider.lower().strip()
    valid_providers = ("openai", "anthropic", "gemini", "local")
    if provider not in valid_providers:
        console.print(
            f"[red]Unknown provider:[/red] {provider}\n"
            f"Valid providers: {', '.join(valid_providers)}",
        )
        raise typer.Exit(1)

    if provider == "local" and not url:
        console.print(
            "[red]Local provider requires --url[/red] "
            "(e.g. --url http://localhost:1234/v1)",
        )
        raise typer.Exit(1)

    if provider != "local" and not api_key:
        console.print(f"[red]Provider '{provider}' requires --api-key[/red]")
        raise typer.Exit(1)

    model_cfg = ModelConfig(
        provider=provider,
        api_key=api_key,
        model_name=model_name or _DEFAULT_MODELS.get(provider),
        base_url=url or _DEFAULT_URLS.get(provider),
    )

    store.init_global_store()
    config = store.load_global_config()
    config.model = model_cfg
    store.save_global_config(config)

    display_model = model_cfg.model_name or _DEFAULT_MODELS.get(provider, "default")
    console.print(f"[green]Model configured:[/green] {provider} ({display_model})")
    if provider == "local":
        console.print(f"[dim]Endpoint: {url}[/dim]")
    console.print("[dim]Run [cyan]writ plan review <file>[/cyan] to use it.[/dim]")


@model_app.command(name="list")
def model_list() -> None:
    """Show current AI model configuration."""
    from rich.panel import Panel

    config = store.load_global_config()
    if config.model is None:
        console.print(
            "[dim]No model configured.[/dim]\n"
            "Set one with [cyan]writ model set <provider> --api-key <key>[/cyan]\n"
            "Or run [cyan]writ login[/cyan] for 5 free daily plan reviews via Gemini.",
        )
        return

    m = config.model
    key_display = f"{m.api_key[:8]}..." if m.api_key and len(m.api_key) > 8 else "(none)"
    lines = [
        f"[bold]Provider:[/bold]  {m.provider}",
        f"[bold]Model:[/bold]     {m.model_name or '(default)'}",
        f"[bold]API Key:[/bold]   {key_display}",
    ]
    if m.base_url:
        lines.append(f"[bold]Endpoint:[/bold]  {m.base_url}")
    console.print(Panel("\n".join(lines), title="writ model", border_style="cyan"))


@model_app.command(name="clear")
def model_clear() -> None:
    """Remove model configuration. Falls back to enwrit.com backend."""
    config = store.load_global_config()
    if config.model is None:
        console.print("[dim]No model configured.[/dim]")
        return
    config.model = None
    store.save_global_config(config)
    console.print(
        "[green]Model configuration removed.[/green]\n"
        "[dim]Plan review will use enwrit.com backend (requires [cyan]writ login[/cyan]).[/dim]",
    )
