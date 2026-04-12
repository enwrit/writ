"""writ diff -- Track instruction quality changes via git."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from writ.commands.lint import _maybe_ml_score, _parse_file_to_config
from writ.core import linter as lint_engine
from writ.core.models import LintScore
from writ.utils import console

# Match common UX ordering (headline table in docs / user spec)
_DISPLAY_DIM_ORDER: tuple[str, ...] = (
    "clarity",
    "verification",
    "coverage",
    "brevity",
    "structure",
    "examples",
)


def _normalize_text(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def _run_git(
    args: list[str],
    *,
    cwd: Path,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=cwd,
            check=check,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        console.print("[red]git not found[/red]")
        raise typer.Exit(1) from None


def _git_repo_root(cwd: Path) -> Path:
    proc = _run_git(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cwd,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        if "not a git repository" in err.lower():
            console.print("[red]Not a git repository.[/red]")
        else:
            console.print(
                f"[red]Git error:[/red] {err or 'could not resolve repository root'}",
            )
        raise typer.Exit(1)
    return Path(proc.stdout.strip()).resolve()


def _git_path_relative(file_resolved: Path, repo_root: Path) -> str:
    try:
        rel = file_resolved.resolve().relative_to(repo_root)
    except ValueError:
        console.print(
            "[red]File is outside the git repository root.[/red]",
        )
        raise typer.Exit(1) from None
    return rel.as_posix()


def _assert_tracked(git_path: str, repo_root: Path) -> None:
    proc = _run_git(
        ["git", "ls-files", "--error-unmatch", "--", git_path],
        cwd=repo_root,
    )
    if proc.returncode != 0:
        console.print("[red]File not tracked by git[/red]")
        raise typer.Exit(1)


def _git_show_blob(repo_root: Path, ref: str, git_path: str) -> str:
    spec = f"{ref}:{git_path}"
    proc = _run_git(
        ["git", "show", spec],
        cwd=repo_root,
    )
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        if "does not exist" in err or "bad revision" in err.lower():
            console.print(
                f"[yellow]No previous version to compare.[/yellow] "
                f"The file may only exist in the current commit.\n"
                f"  Try: [cyan]writ diff {git_path} --ref HEAD~2[/cyan] "
                f"or a specific commit hash.",
            )
        else:
            console.print(
                f"[red]Could not read file at ref[/red] ({spec}).\n"
                f"{err}",
            )
        raise typer.Exit(1)
    return proc.stdout


def _score_file(path: Path, *, force_code: bool) -> LintScore:
    agent = _parse_file_to_config(path)
    results = lint_engine.lint(agent, source_path=path)
    return _maybe_ml_score(agent, results, force_code=force_code)


def _dim_map(score: LintScore) -> dict[str, tuple[str, int]]:
    return {d.name: (d.label, d.score) for d in score.dimensions}


def _fmt_delta(delta: int) -> str:
    if delta > 0:
        return f"[green]+{delta}[/green]"
    if delta < 0:
        return f"[red]{delta}[/red]"
    return "[dim]0[/dim]"


def _fmt_headline_delta(delta: int) -> str:
    if delta > 0:
        return f"[green](+{delta})[/green]"
    if delta < 0:
        return f"[red]({delta})[/red]"
    return "[dim](0)[/dim]"


def diff_command(
    file_path: Annotated[
        Path,
        typer.Argument(
            ...,
            help="Path to an instruction file (tracked by git).",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    ref: str = typer.Option(
        "HEAD~1",
        "--ref",
        help="Git revision to compare the working tree against.",
    ),
    code: bool = typer.Option(
        False,
        "--code",
        help="Force Tier 1 code-only scoring (same as writ lint --code).",
    ),
) -> None:
    """Compare writ lint scores for a file versus a previous git revision.

    Example:
        writ diff AGENTS.md
        writ diff AGENTS.md --ref HEAD~3
    """
    resolved = file_path.resolve()
    cwd = Path.cwd()
    repo_root = _git_repo_root(cwd)
    git_path = _git_path_relative(resolved, repo_root)
    _assert_tracked(git_path, repo_root)

    new_text = resolved.read_text(encoding="utf-8")
    old_text = _git_show_blob(repo_root, ref, git_path)

    if _normalize_text(new_text) == _normalize_text(old_text):
        console.print(f"[dim]No changes from {ref}[/dim]")
        return

    suffix = resolved.suffix or ".md"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=suffix,
        delete=False,
    ) as tmp:
        tmp.write(old_text)
        tmp_path = Path(tmp.name)

    try:
        before = _score_file(tmp_path, force_code=code)
        after = _score_file(resolved, force_code=code)
    finally:
        tmp_path.unlink(missing_ok=True)

    console.print(f"\n  [bold]writ diff:[/bold] {git_path}\n")

    d_score = after.score - before.score
    console.print(
        f"  Score:  {before.score} -> {after.score}  {_fmt_headline_delta(d_score)}",
    )

    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("Dimension", style="bold", min_width=14)
    table.add_column("Before", justify="right", min_width=6)
    table.add_column("After", justify="right", min_width=6)
    table.add_column("Change", justify="right", min_width=8)

    before_dims = _dim_map(before)
    after_dims = _dim_map(after)
    dim_names = [n for n in _DISPLAY_DIM_ORDER if n in after_dims]
    for n in after_dims:
        if n not in dim_names:
            dim_names.append(n)

    for name in dim_names:
        label, after_val = after_dims[name]
        before_val = before_dims[name][1] if name in before_dims else 0
        delta = after_val - before_val
        table.add_row(
            label,
            str(before_val),
            str(after_val),
            _fmt_delta(delta),
        )

    console.print()
    console.print(table)
    console.print()
