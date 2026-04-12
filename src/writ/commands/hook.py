"""writ hook install/uninstall -- pre-commit quality gate for instruction files."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from writ.utils import console

hook_app = typer.Typer(
    name="hook",
    help="Git pre-commit hook for instruction quality.",
    no_args_is_help=True,
)

_HOOK_MARKER_START = "# --- writ lint hook start ---"
_HOOK_MARKER_END = "# --- writ lint hook end ---"

_INSTRUCTION_GLOBS = (
    ".cursor/rules/*.mdc",
    ".cursor/rules/*.md",
    ".cursor/agents/*.mdc",
    ".cursor/agents/*.md",
    ".cursor/skills/*/*.mdc",
    ".claude/rules/*.md",
    ".claude/agents/*.md",
    ".claude/skills/*/*.md",
    ".kiro/steering/*.md",
    ".writ/agents/*.yaml",
    ".writ/rules/*.yaml",
    ".writ/context/*.yaml",
    ".writ/programs/*.yaml",
    "AGENTS.md",
    "CLAUDE.md",
    ".windsurfrules",
    ".github/copilot-instructions.md",
    ".github/instructions/*.instructions.md",
    ".github/agents/*.md",
    ".github/skills/*/*.md",
)


def _build_hook_script(min_score: int) -> str:
    """Generate the shell script for the pre-commit hook."""
    globs_pattern = "|".join(
        g.replace("*", ".*").replace("/", r"[/\\]")
        for g in _INSTRUCTION_GLOBS
    )
    pattern = globs_pattern
    return (
        f"{_HOOK_MARKER_START}\n"
        f"# Lint changed instruction files before commit\n"
        f"WRIT_PATTERN='{pattern}'\n"
        f"INSTRUCTION_FILES=$(git diff --cached --name-only "
        f"--diff-filter=ACM | grep -E \"$WRIT_PATTERN\" || true)\n"
        f"if [ -n \"$INSTRUCTION_FILES\" ]; then\n"
        f"    echo \"writ: linting changed instruction files...\"\n"
        f"    FAILED=0\n"
        f"    for f in $INSTRUCTION_FILES; do\n"
        f"        if [ -f \"$f\" ]; then\n"
        f"            writ lint \"$f\" --ci --min-score {min_score}"
        f" || FAILED=1\n"
        f"        fi\n"
        f"    done\n"
        f"    if [ $FAILED -ne 0 ]; then\n"
        f"        echo \"\"\n"
        f"        echo \"writ: quality gate failed"
        f" (min score: {min_score})\"\n"
        f"        echo \"Fix issues above, or bypass with:"
        f" git commit --no-verify\"\n"
        f"        exit 1\n"
        f"    fi\n"
        f"fi\n"
        f"{_HOOK_MARKER_END}"
    )


def _find_git_hooks_dir() -> Path | None:
    """Find the .git/hooks directory from the current working directory."""
    cwd = Path.cwd()
    git_dir = cwd / ".git"
    if git_dir.is_dir():
        return git_dir / "hooks"
    for parent in cwd.parents:
        git_dir = parent / ".git"
        if git_dir.is_dir():
            return git_dir / "hooks"
    return None


@hook_app.command(name="install")
def install_hook(
    min_score: Annotated[
        int,
        typer.Option("--min-score", "-s", help="Minimum lint score (0-100). Default: 40."),
    ] = 40,
) -> None:
    """Install a git pre-commit hook that lints changed instruction files.

    Changed instruction files (.mdc, .md rules, AGENTS.md, etc.) are linted
    on each commit. If any file scores below --min-score, the commit is blocked.

    \b
    Examples:
      writ hook install
      writ hook install --min-score 60
    """
    hooks_dir = _find_git_hooks_dir()
    if hooks_dir is None:
        console.print("[red]Not a git repository.[/red] Run this from a git repo.")
        raise typer.Exit(1)

    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "pre-commit"

    hook_script = _build_hook_script(min_score)

    if hook_path.exists():
        existing = hook_path.read_text(encoding="utf-8")
        if _HOOK_MARKER_START in existing:
            import re

            pattern = (
                re.escape(_HOOK_MARKER_START) + r".*?" + re.escape(_HOOK_MARKER_END)
            )
            updated = re.sub(pattern, hook_script, existing, flags=re.DOTALL)
            hook_path.write_text(updated, encoding="utf-8")
            console.print(
                f"[green]Pre-commit hook updated[/green] (min score: {min_score})",
            )
        else:
            hook_path.write_text(
                existing.rstrip() + "\n\n" + hook_script + "\n",
                encoding="utf-8",
            )
            console.print(
                f"[green]Pre-commit hook installed[/green] (min score: {min_score})",
            )
    else:
        hook_path.write_text("#!/bin/sh\n\n" + hook_script + "\n", encoding="utf-8")
        try:
            hook_path.chmod(0o755)
        except OSError:
            pass
        console.print(
            f"[green]Pre-commit hook installed[/green] (min score: {min_score})",
        )

    console.print(f"[dim]Hook: {hook_path}[/dim]")
    console.print("[dim]Bypass with: git commit --no-verify[/dim]")


@hook_app.command(name="uninstall")
def uninstall_hook() -> None:
    """Remove the writ pre-commit hook."""
    hooks_dir = _find_git_hooks_dir()
    if hooks_dir is None:
        console.print("[red]Not a git repository.[/red]")
        raise typer.Exit(1)

    hook_path = hooks_dir / "pre-commit"
    if not hook_path.exists():
        console.print("[dim]No pre-commit hook found.[/dim]")
        return

    existing = hook_path.read_text(encoding="utf-8")
    if _HOOK_MARKER_START not in existing:
        console.print("[dim]No writ hook found in pre-commit.[/dim]")
        return

    import re

    pattern = re.escape(_HOOK_MARKER_START) + r".*?" + re.escape(_HOOK_MARKER_END)
    cleaned = re.sub(pattern, "", existing, flags=re.DOTALL)
    cleaned = cleaned.strip()

    if cleaned and cleaned != "#!/bin/sh":
        hook_path.write_text(cleaned + "\n", encoding="utf-8")
    else:
        hook_path.unlink()

    console.print("[green]Pre-commit hook removed.[/green]")
