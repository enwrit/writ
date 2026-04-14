"""writ upgrade -- Update installed instructions to their latest versions."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from writ.core import store
from writ.core.models import InstructionConfig
from writ.utils import console


def upgrade_command(
    name: Annotated[
        str | None,
        typer.Argument(help="Instruction name to upgrade (omit for all)."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be upgraded without applying."),
    ] = False,
) -> None:
    """Upgrade installed instructions to latest versions from their source.

    Without a name, checks all instructions that have a known source
    (installed from Hub, PRPM, library, or URL). Instructions created
    locally (no source) are skipped.

    Examples:
        writ upgrade                  # check all for updates
        writ upgrade my-agent         # upgrade specific instruction
        writ upgrade --dry-run        # preview without applying
    """
    if not store.is_initialized():
        console.print("[red]Not initialized.[/red] Run [cyan]writ init[/cyan] first.")
        raise typer.Exit(1)

    instructions = store.list_instructions()

    if name:
        targets = [i for i in instructions if i.name == name]
        if not targets:
            console.print(f"[red]Instruction '{name}' not found.[/red]")
            raise typer.Exit(1)
    else:
        if not instructions:
            console.print("[yellow]No instructions in this project.[/yellow]")
            return
        targets = [i for i in instructions if i.source]

    if not targets:
        console.print("[dim]No upgradeable instructions found (none have a source).[/dim]")
        return

    from writ.integrations.registry import RegistryClient

    client = RegistryClient()
    upgraded = 0
    skipped = 0

    table = Table(title="Upgrade Check", show_edge=False)
    table.add_column("Name", style="cyan")
    table.add_column("Source", style="dim")
    table.add_column("Local Ver")
    table.add_column("Remote Ver")
    table.add_column("Status")

    for inst in targets:
        source = inst.source or ""
        remote_cfg = _fetch_latest(client, inst)

        if remote_cfg is None:
            table.add_row(inst.name, source, inst.version, "?", "[dim]source unavailable[/dim]")
            skipped += 1
            continue

        if remote_cfg.version == inst.version:
            table.add_row(
                inst.name, source, inst.version, remote_cfg.version, "[green]up to date[/green]",
            )
            skipped += 1
            continue

        if dry_run:
            table.add_row(
                inst.name, source, inst.version, remote_cfg.version,
                "[yellow]update available[/yellow]",
            )
        else:
            remote_cfg.source = inst.source
            store.save_instruction(remote_cfg)
            from writ.commands.agent import _write_to_ide
            _write_to_ide(remote_cfg, remote_cfg.instructions)
            table.add_row(
                inst.name, source, inst.version, remote_cfg.version,
                "[green]upgraded[/green]",
            )
            upgraded += 1

    console.print(table)

    if dry_run:
        console.print("\n[dim]Dry run complete. Run without --dry-run to apply.[/dim]")
    elif upgraded:
        console.print(f"\n[green]{upgraded} instruction(s) upgraded.[/green]")
    else:
        console.print("\n[dim]Everything is up to date.[/dim]")


def _fetch_latest(
    client: object, inst: InstructionConfig,
) -> InstructionConfig | None:
    """Try to fetch the latest version of an instruction from its source."""
    source = inst.source or ""

    if source.startswith("prpm/"):
        return _fetch_from_hub(client, "prpm", source.split("/", 1)[1])
    if source.startswith("enwrit/") or "/" in source:
        parts = source.split("/", 1)
        return _fetch_from_hub(client, parts[0], parts[1])

    return _fetch_from_hub(client, "enwrit", inst.name)


def _fetch_from_hub(client: object, hub_source: str, name: str):
    """Download from Hub and convert to InstructionConfig."""
    from writ.commands.agent import _cfg_from_hub
    try:
        data = client.hub_download(hub_source, name)  # type: ignore[attr-defined]
        if data:
            return _cfg_from_hub(data, source=hub_source)
    except Exception:  # noqa: BLE001
        pass

    try:
        data = client.pull_public_agent(name)  # type: ignore[attr-defined]
        if data:
            from writ.commands.agent import _cfg_from_dict
            return _cfg_from_dict(data)
    except Exception:  # noqa: BLE001
        pass

    return None
