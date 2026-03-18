"""``writ connect`` -- interactive peer setup wizard for real repos.

Guides users through connecting two repositories as peers, enabling
agent-to-agent communication via ``writ chat``.
"""

from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.panel import Panel

from writ.core import peers, store
from writ.core.models import AutoRespondTier
from writ.utils import console, error_console


def _find_sibling_repos() -> list[Path]:
    """Scan parent directory for directories that look like repos."""
    parent = Path.cwd().parent
    candidates: list[Path] = []
    if not parent.is_dir():
        return candidates
    try:
        for child in sorted(parent.iterdir()):
            if child == Path.cwd() or not child.is_dir():
                continue
            if child.name.startswith("."):
                continue
            has_git = (child / ".git").exists()
            has_writ = (child / ".writ").exists()
            has_src = any(
                (child / f).exists()
                for f in ("src", "package.json", "pyproject.toml",
                          "Cargo.toml", "go.mod", "README.md")
            )
            if has_git or has_writ or has_src:
                candidates.append(child)
    except PermissionError:
        pass
    return candidates


def _init_remote_repo(path: Path) -> None:
    """Run writ init in a remote repo by temporarily changing cwd."""
    original = os.getcwd()
    try:
        os.chdir(str(path))
        store.init_project_store(clean=False)
    finally:
        os.chdir(original)


def connect_command(
    peer_path: str = typer.Argument(
        default="",
        help="Path to the peer repo. If empty, shows discovered repos.",
    ),
    name: str = typer.Option(
        "", "--name", "-n",
        help="Short name for the peer (defaults to directory name).",
    ),
    auto_respond: str = typer.Option(
        "off", "--auto-respond",
        help="Auto-respond policy: off, read_only, or full.",
    ),
    bidirectional: bool = typer.Option(
        True, "--bidirectional/--one-way",
        help="Register peer in both repos (default: bidirectional).",
    ),
) -> None:
    """Interactive wizard to connect two repos for agent-to-agent chat.

    Discovers nearby repos, validates both sides, configures peers in
    both directions, and sends a test message.

    Examples:
        writ connect                           # discover + choose
        writ connect ../backend                # direct path
        writ connect ../backend --name api     # custom name
    """
    if not store.is_initialized():
        console.print(
            "[yellow]This repo is not initialized.[/yellow] "
            "Running [cyan]writ init[/cyan] first..."
        )
        store.init_project_store(clean=False)
        console.print("[green]Initialized.[/green]\n")

    try:
        tier = AutoRespondTier(auto_respond)
    except ValueError:
        error_console.print(
            f"[red]Invalid auto-respond: {auto_respond}[/red] "
            "(use off, read_only, or full)"
        )
        raise typer.Exit(1) from None

    resolved: Path | None = None

    if peer_path:
        resolved = Path(peer_path).resolve()
    else:
        siblings = _find_sibling_repos()
        if siblings:
            console.print("[bold]Nearby repositories:[/bold]\n")
            for i, s in enumerate(siblings, 1):
                writ_mark = " [green](writ)[/green]" if (s / ".writ").exists() else ""
                console.print(f"  [cyan]{i}[/cyan]  {s.name}{writ_mark}")
            console.print()
            choice = typer.prompt(
                "Enter number or path", default="1",
            )
            if choice.isdigit() and 1 <= int(choice) <= len(siblings):
                resolved = siblings[int(choice) - 1]
            else:
                resolved = Path(choice).resolve()
        else:
            resolved_str = typer.prompt("Path to peer repository")
            resolved = Path(resolved_str).resolve()

    if resolved is None or not resolved.is_dir():
        error_console.print(
            f"[red]Directory not found:[/red] {resolved}"
        )
        raise typer.Exit(1)

    peer_name = name or resolved.name
    local_name = Path.cwd().name

    if not (resolved / ".writ").exists():
        console.print(
            f"\n[yellow]{peer_name}[/yellow] has no .writ/ directory."
        )
        do_init = typer.confirm(
            f"Initialize writ in {resolved.name}?", default=True,
        )
        if do_init:
            _init_remote_repo(resolved)
            console.print(f"[green]Initialized[/green] {peer_name}")
        else:
            console.print("[dim]Skipping init. Peer may not work until initialized.[/dim]")

    existing = peers.get_peer(peer_name)
    if existing:
        console.print(
            f"\n[yellow]Peer '{peer_name}' already registered.[/yellow] "
            "Updating..."
        )

    peers.add_peer(
        peer_name,
        path=str(resolved),
        auto_respond=tier,
        max_turns=10,
    )
    console.print(
        f"\n[green]Added peer[/green] [cyan]{peer_name}[/cyan] "
        f"-> {resolved}"
    )

    if bidirectional:
        if (resolved / ".writ").is_dir():
            original = os.getcwd()
            try:
                os.chdir(str(resolved))
                peers.add_peer(
                    local_name,
                    path=str(Path(original).resolve()),
                    auto_respond=tier,
                    max_turns=10,
                )
                console.print(
                    f"[green]Added reverse peer[/green] "
                    f"[cyan]{local_name}[/cyan] in {peer_name}"
                )
            finally:
                os.chdir(original)
        else:
            console.print(
                f"[dim]Skipped reverse peer (no .writ/ in {peer_name})[/dim]"
            )

    console.print()
    console.print(Panel.fit(
        f"[bold green]Connected![/bold green]\n\n"
        f"  [cyan]{local_name}[/cyan]  <-->  [cyan]{peer_name}[/cyan]\n\n"
        "Try it:\n"
        f"  [cyan]writ chat start --with {peer_name} "
        f"--goal 'Test' -m 'Hello!'[/cyan]\n"
        f"  [cyan]writ peers list[/cyan]",
        border_style="green",
        title="writ connect",
    ))
