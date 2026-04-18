"""writ status -- project status with knowledge health and recent activity."""

from __future__ import annotations

from pathlib import Path

import typer

from writ.utils import console


def status_command(
    show_all: bool = typer.Option(False, "--all", "-a", help="Show full log history."),
) -> None:
    """Show project status, health score, and recent activity.

    Combines connectivity diagnostics with documentation health score
    and recent entries from the knowledge log.

    \\b
    Examples:
      writ status
      writ status --all
    """
    from rich.panel import Panel
    from rich.table import Table

    from writ.core import auth, store

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value")

    initialized = store.is_initialized()
    if initialized:
        init_val = "[green]yes[/green]"
    else:
        init_val = "[red]no[/red]  (run [cyan]writ init[/cyan])"
    table.add_row("Project initialized", init_val)

    if initialized:
        instructions = store.list_instructions()
        table.add_row("Instructions in project", str(len(instructions)))
        config = store.load_config()
        table.add_row("Active formats", ", ".join(config.formats))

    logged_in = auth.is_logged_in()
    table.add_row("Logged in", "[green]yes[/green]" if logged_in else "[dim]no[/dim]")

    lib_items = store.list_library()
    table.add_row("Library instructions", str(len(lib_items)))

    if initialized:
        health_str = _quick_health()
        table.add_row("Documentation health", health_str)

        lint_str = _lint_summary()
        if lint_str:
            table.add_row("Lint (avg / delta)", lint_str)

        peer_str = _peer_activity_summary()
        if peer_str:
            table.add_row("Peer activity", peer_str)

        inst_change = _last_instruction_change()
        if inst_change:
            table.add_row("Last instruction change", inst_change)

    if logged_in:
        sync_str = _sync_delta_summary()
        if sync_str:
            table.add_row("Sync (local / remote)", sync_str)

    backend_status = _check_backend()
    table.add_row("Backend (api.enwrit.com)", backend_status)

    console.print(Panel(table, title="writ status", border_style="cyan"))

    if initialized:
        _show_recent_log(show_all=show_all)


def _quick_health() -> str:
    """Run a quick health check and return a formatted score string."""
    try:
        from writ.core.doc_health import run_health_check

        report = run_health_check(Path.cwd())
        score = report.health_score
        if score >= 80:
            return f"[green]{score}/100[/green]"
        if score >= 50:
            return f"[yellow]{score}/100[/yellow]"
        return f"[red]{score}/100[/red]"
    except Exception:  # noqa: BLE001
        return "[dim]unavailable[/dim]"


def _show_recent_log(*, show_all: bool = False) -> None:
    """Display recent entries from the writ-log instruction."""
    from writ.core import store

    cfg = store.load_instruction("writ-log")
    if cfg is None or not cfg.instructions:
        return

    text = cfg.instructions

    entries = [line for line in text.splitlines() if line.startswith("- [")]
    if not entries:
        return

    if not show_all:
        entries = entries[-10:]

    console.print()
    console.print("[bold]Recent activity:[/bold]")
    for entry in entries:
        console.print(f"  {entry}")


def _lint_summary() -> str | None:
    """Return formatted 'avg ↑N' string from .writ/lint-scores.json.

    Tracks the previous average in ``_meta.previous_avg`` so successive
    calls show a delta arrow. Returns None when no cache exists yet.
    """
    import json

    try:
        from writ.utils import project_writ_dir
        path = project_writ_dir() / "lint-scores.json"
    except Exception:  # noqa: BLE001
        return None
    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, ValueError):
        return None
    scores = data.get("scores") if isinstance(data, dict) else None
    if not isinstance(scores, dict) or not scores:
        return None

    values: list[int] = []
    for entry in scores.values():
        if not isinstance(entry, dict):
            continue
        val = entry.get("headline_score")
        try:
            if val is not None:
                values.append(int(val))
        except (TypeError, ValueError):
            continue
    if not values:
        return None

    avg = sum(values) / len(values)
    meta = data.get("_meta") if isinstance(data, dict) else {}
    if not isinstance(meta, dict):
        meta = {}
    previous_avg = meta.get("previous_avg")

    delta_suffix = ""
    if isinstance(previous_avg, (int, float)):
        diff = avg - float(previous_avg)
        if abs(diff) >= 0.5:
            arrow = "↑" if diff > 0 else "↓"
            colour = "green" if diff > 0 else "red"
            delta_suffix = f"  [{colour}]{arrow}{abs(diff):.1f}[/{colour}]"
        else:
            delta_suffix = "  [dim]=[/dim]"

    try:
        meta["previous_avg"] = round(avg, 1)
        data["_meta"] = meta
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass

    if avg >= 80:
        colour = "green"
    elif avg >= 50:
        colour = "yellow"
    else:
        colour = "red"
    return f"[{colour}]{avg:.1f}[/{colour}]  ({len(values)} file(s)){delta_suffix}"


def _peer_activity_summary() -> str | None:
    """Return 'N conversations, M unread' (pulls remote first, silently)."""
    try:
        from writ.commands.chat import _pull_all_remote
        from writ.core import messaging
    except Exception:  # noqa: BLE001
        return None

    try:
        _pull_all_remote(silent=True)
    except Exception:  # noqa: BLE001
        pass

    try:
        pairs = messaging.list_conversations()
    except Exception:  # noqa: BLE001
        return None
    if not pairs:
        return None

    repo_name = Path.cwd().name
    unread = 0
    for _, conv in pairs:
        try:
            msgs = getattr(conv, "messages", []) or []
            if not msgs:
                continue
            last = msgs[-1]
            if getattr(last, "author_repo", None) != repo_name:
                unread += 1
        except Exception:  # noqa: BLE001
            continue

    if unread:
        return f"{len(pairs)} conversation(s), [yellow]{unread} unread[/yellow]"
    return f"{len(pairs)} conversation(s), [dim]0 unread[/dim]"


def _last_instruction_change() -> str | None:
    """Return 'abcd123 <subject>' for the last commit touching instruction dirs."""
    import subprocess

    targets = [".writ", ".cursor/rules", "AGENTS.md", "CLAUDE.md"]
    existing = [t for t in targets if Path(t).exists()]
    if not existing:
        return None
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%h %s", "--", *existing],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, FileNotFoundError):
        return None
    if out.returncode != 0:
        return None
    line = out.stdout.strip()
    if not line:
        return None
    if len(line) > 72:
        line = line[:69] + "..."
    return f"[dim]{line}[/dim]"


def _sync_delta_summary() -> str | None:
    """Return 'N local / M remote / K out of sync' when logged in."""
    try:
        from writ.core import store
        from writ.integrations.registry import RegistryClient
    except Exception:  # noqa: BLE001
        return None

    try:
        local_instructions = store.list_library()
    except Exception:  # noqa: BLE001
        return None
    local_names = {cfg.name for cfg in local_instructions}

    try:
        remote_list = RegistryClient().list_library()
    except Exception:  # noqa: BLE001
        return f"{len(local_names)} local / [dim]remote unavailable[/dim]"
    if remote_list is None:
        return f"{len(local_names)} local / [dim]remote unavailable[/dim]"

    remote_names = {item["name"] for item in remote_list if "name" in item}
    diff = (local_names ^ remote_names)
    if diff:
        return (
            f"{len(local_names)} local / {len(remote_names)} remote "
            f"/ [yellow]{len(diff)} out of sync[/yellow]"
        )
    return (
        f"{len(local_names)} local / {len(remote_names)} remote "
        f"/ [green]in sync[/green]"
    )


def _check_backend() -> str:
    """Quick health check against the backend."""
    try:
        import httpx

        resp = httpx.get("https://api.enwrit.com/health", timeout=5.0)
        if resp.status_code == 200:
            return "[green]reachable[/green]"
        return f"[yellow]HTTP {resp.status_code}[/yellow]"
    except Exception:  # noqa: BLE001
        return "[red]unreachable[/red]"
