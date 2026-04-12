"""writ sync -- Bulk bidirectional sync between local library and enwrit.com.

Unlike ``writ save`` (single instruction), ``writ sync`` synchronizes your
entire personal library in one operation.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from writ.core import auth, store
from writ.core.models import InstructionConfig
from writ.integrations.registry import RegistryClient
from writ.utils import console, global_writ_dir


def sync_command(
    push_only: Annotated[
        bool, typer.Option("--push", help="Push local to remote only.")
    ] = False,
    pull_only: Annotated[
        bool, typer.Option("--pull", help="Pull remote to local only.")
    ] = False,
    prefer_local: Annotated[
        bool,
        typer.Option(
            "--prefer-local",
            help="On conflicts keep local version (default: prefer remote).",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would sync without changing anything."),
    ] = False,
    undo: Annotated[
        bool,
        typer.Option("--undo", help="Revert the last sync (restore from backup)."),
    ] = False,
) -> None:
    """Sync your entire personal library with enwrit.com.

    By default performs a bidirectional sync: pushes local-only
    instructions to the remote, and pulls remote-only instructions
    to local. Instructions that exist in both places are updated
    to the remote version (use --prefer-local to reverse).

    A backup is created before each sync. Use --undo to revert.

    \b
    Examples:
      writ sync               # full bidirectional sync
      writ sync --push        # push local -> remote only
      writ sync --pull        # pull remote -> local only
      writ sync --dry-run     # preview what would change
      writ sync --undo        # revert the last sync
    """
    if undo:
        undo_sync()
        return
    if push_only and pull_only:
        console.print("[red]Cannot use --push and --pull together.[/red]")
        raise typer.Exit(1)

    if not auth.is_logged_in():
        console.print(
            "[red]Not logged in.[/red] "
            "Run [cyan]writ login[/cyan] or [cyan]writ register[/cyan] first."
        )
        raise typer.Exit(1)

    store.init_global_store()
    client = RegistryClient()

    local_instructions = store.list_library()
    local_map = {cfg.name: cfg for cfg in local_instructions}

    remote_list = client.list_library()
    remote_names = {item["name"] for item in remote_list if "name" in item}

    local_only = set(local_map.keys()) - remote_names
    remote_only = remote_names - set(local_map.keys())
    shared = set(local_map.keys()) & remote_names

    # Preview what will happen and confirm if the operation is large
    total_ops = 0
    if not pull_only:
        total_ops += len(local_only)
    if not push_only:
        total_ops += len(remote_only)
    if not push_only and not pull_only:
        total_ops += len(shared)

    if total_ops == 0:
        console.print("\n[green]Already in sync.[/green] Nothing to do.")
        return

    if not dry_run and total_ops > 5:
        preview_parts = []
        if not pull_only and local_only:
            preview_parts.append(f"push {len(local_only)} to remote")
        if not push_only and remote_only:
            preview_parts.append(f"pull {len(remote_only)} to local")
        if not push_only and not pull_only and shared:
            direction = "push (local wins)" if prefer_local else "pull (remote wins)"
            preview_parts.append(f"update {len(shared)} ({direction})")

        console.print(f"\n[bold]Sync preview:[/bold] {', '.join(preview_parts)}")
        console.print(f"  Total: {total_ops} operations")
        console.print(
            "[dim]  Use --dry-run to see exactly which instructions are affected.[/dim]"
        )
        confirm = typer.confirm("\nProceed with sync?")
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)

    if not dry_run:
        _backup_library()

    pushed = 0
    pulled = 0
    updated = 0
    skipped = 0
    errors = 0

    if not pull_only:
        for name in sorted(local_only):
            cfg = local_map[name]
            if dry_run:
                console.print(f"  [cyan]push[/cyan]  {name}")
                pushed += 1
                continue
            if client.push_to_library(name, cfg):
                console.print(f"  [green]pushed[/green]  {name}")
                pushed += 1
            else:
                console.print(f"  [red]failed[/red]  {name}")
                errors += 1

    if not push_only:
        for name in sorted(remote_only):
            if dry_run:
                console.print(f"  [cyan]pull[/cyan]  {name}")
                pulled += 1
                continue
            remote_data = client.pull_from_library(name)
            if remote_data:
                cfg = _cfg_from_remote(remote_data)
                if cfg:
                    store.save_to_library(cfg)
                    console.print(f"  [green]pulled[/green]  {name}")
                    pulled += 1
                else:
                    console.print(f"  [red]failed[/red]  {name} (bad data)")
                    errors += 1
            else:
                console.print(f"  [red]failed[/red]  {name}")
                errors += 1

    if not push_only and not pull_only:
        for name in sorted(shared):
            if prefer_local:
                cfg = local_map[name]
                if dry_run:
                    console.print(f"  [cyan]push[/cyan]  {name} (prefer-local)")
                    updated += 1
                    continue
                if client.push_to_library(name, cfg):
                    console.print(f"  [green]pushed[/green]  {name} (local wins)")
                    updated += 1
                else:
                    console.print(f"  [red]failed[/red]  {name}")
                    errors += 1
            else:
                if dry_run:
                    console.print(f"  [cyan]pull[/cyan]  {name} (prefer-remote)")
                    updated += 1
                    continue
                remote_data = client.pull_from_library(name)
                if remote_data:
                    cfg = _cfg_from_remote(remote_data)
                    if cfg:
                        store.save_to_library(cfg)
                        console.print(
                            f"  [green]pulled[/green]  {name} (remote wins)"
                        )
                        updated += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1

    _print_summary(pushed, pulled, updated, skipped, errors, dry_run)

    if errors and not dry_run:
        raise typer.Exit(1)


def _cfg_from_remote(data: dict) -> InstructionConfig | None:
    """Build an InstructionConfig from remote API response."""
    name = data.get("name")
    if not name:
        return None
    try:
        return InstructionConfig(
            name=name,
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            tags=data.get("tags", []),
            task_type=data.get("task_type", "agent"),
            instructions=data.get("instructions", ""),
        )
    except Exception:  # noqa: BLE001
        return None


def _print_summary(
    pushed: int,
    pulled: int,
    updated: int,
    skipped: int,
    errors: int,
    dry_run: bool,
) -> None:
    """Print a sync summary table."""
    prefix = "[dim](dry run)[/dim] " if dry_run else ""

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")

    total = pushed + pulled + updated
    if total == 0 and errors == 0:
        console.print(f"\n{prefix}[green]Already in sync.[/green] Nothing to do.")
        return

    if pushed:
        table.add_row("Pushed (local -> remote)", str(pushed))
    if pulled:
        table.add_row("Pulled (remote -> local)", str(pulled))
    if updated:
        table.add_row("Updated (conflict resolved)", str(updated))
    if skipped:
        table.add_row("Skipped", str(skipped))
    if errors:
        table.add_row("[red]Errors[/red]", str(errors))

    console.print(f"\n{prefix}Sync complete:")
    console.print(table)

    if not dry_run and (pulled or updated):
        console.print(
            "\n[dim]  A backup was saved before sync. "
            "Run [cyan]writ sync --undo[/cyan] to revert.[/dim]"
        )


# ---------------------------------------------------------------------------
# Backup / undo
# ---------------------------------------------------------------------------

_CONTENT_DIRS = ("agents", "rules", "context", "programs")


def _backup_dir() -> Path:
    return global_writ_dir() / ".sync-backup"


def _backup_library() -> None:
    """Snapshot the current library content dirs into ~/.writ/.sync-backup/."""
    backup = _backup_dir()
    if backup.exists():
        shutil.rmtree(backup)
    backup.mkdir(parents=True, exist_ok=True)

    root = global_writ_dir()
    for subdir in _CONTENT_DIRS:
        src = root / subdir
        if src.exists():
            shutil.copytree(src, backup / subdir)

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    (backup / ".timestamp").write_text(ts, encoding="utf-8")


def undo_sync() -> None:
    """Restore library from the last sync backup."""
    backup = _backup_dir()
    if not backup.exists():
        console.print("[red]No sync backup found.[/red] Nothing to undo.")
        raise typer.Exit(1)

    ts_file = backup / ".timestamp"
    ts = ts_file.read_text(encoding="utf-8").strip() if ts_file.exists() else "unknown"

    console.print(f"[bold]Restoring library from backup ({ts})[/bold]")

    confirm = typer.confirm("This will overwrite your current local library. Continue?")
    if not confirm:
        console.print("[dim]Cancelled.[/dim]")
        raise typer.Exit(0)

    root = global_writ_dir()
    for subdir in _CONTENT_DIRS:
        target = root / subdir
        backup_src = backup / subdir
        if target.exists():
            shutil.rmtree(target)
        if backup_src.exists():
            shutil.copytree(backup_src, target)

    console.print("[green]Library restored.[/green]")
    shutil.rmtree(backup)
