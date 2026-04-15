"""writ docs -- project documentation health diagnostics and maintenance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from writ.utils import console

docs_app = typer.Typer(
    name="docs",
    help="Documentation health diagnostics and knowledge maintenance.",
    no_args_is_help=True,
)

_BUILTIN_PROMPTS = Path(__file__).resolve().parent.parent / "templates" / "_builtin" / "prompts"

_INDEX_HEADER = """\
# Documentation Index

This file maps the project's documentation and instruction files.
AI agents use it to navigate, and writ uses it for health-checking.
Update annotations when files are added, removed, or their purpose changes.

"""


def _build_index_treeview(root: Path) -> str:
    """Build an annotated treeview from documentation files found on disk."""
    from writ.core.doc_health import find_doc_files

    doc_files = find_doc_files(root)
    if not doc_files:
        return _INDEX_HEADER + "No documentation files found.\n"

    tree: dict[str, list[str] | dict] = {}
    for fp in doc_files:
        rel = fp.relative_to(root)
        parts = list(rel.parts)
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})  # type: ignore[arg-type,assignment]
        files_list = node.setdefault("__files__", [])  # type: ignore[assignment]
        files_list.append(parts[-1])  # type: ignore[union-attr]

    lines: list[str] = ["```"]
    _render_tree(tree, lines, indent=0)
    lines.append("```")

    core_section = _build_core_files_section(root, doc_files)
    body = "\n".join(lines) + "\n"
    if core_section:
        body += "\n" + core_section

    body += _writ_managed_section()

    return _INDEX_HEADER + body


def _writ_managed_section() -> str:
    """Append a section listing writ-managed files that always exist."""
    return (
        "\n## Writ-managed files\n\n"
        "These files are created and maintained by writ. "
        "They may be updated by AI agents (docs update) or by writ itself.\n\n"
        "- `writ-docs-index` -- this index file (documentation treeview)\n"
        "- `writ-log` -- append-only activity log for writ operations\n"
        "- `writ-context` -- CLI command reference (updated on writ init)\n"
    )


def _build_core_files_section(root: Path, doc_files: list[Path]) -> str:
    """Generate a '## Core files' section from relative git commit frequency.

    Files whose commit count exceeds 30 % of total repo commits are
    considered "core".  If fewer than 2 qualify, the top-3 by ratio are
    shown instead.  Returns empty string if git is unavailable.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            capture_output=True, text=True, check=True, timeout=10, cwd=root,
        )
        total_commits = int(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, OSError, ValueError):
        return ""

    if total_commits < 1:
        return ""

    ratios: list[tuple[str, int, float]] = []
    for fp in doc_files:
        try:
            out = subprocess.run(
                ["git", "log", "--oneline", "--follow", "--", str(fp)],
                capture_output=True, text=True, check=True,
                timeout=10, cwd=root,
            )
            file_commits = len(out.stdout.strip().splitlines())
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            continue
        if file_commits < 1:
            continue
        try:
            rel = fp.relative_to(root).as_posix()
        except ValueError:
            rel = str(fp)
        ratio = file_commits / total_commits
        ratios.append((rel, file_commits, ratio))

    if not ratios:
        return ""

    ratios.sort(key=lambda r: r[2], reverse=True)

    core = [r for r in ratios if r[2] >= 0.30]
    if len(core) < 2:
        core = ratios[:3]

    lines = [
        "## Core files",
        "",
        "Files frequently updated alongside code changes (by git commit frequency):",
    ]
    for rel_path, commits, ratio in core:
        pct = round(ratio * 100)
        lines.append(f"- {rel_path}  [{commits} commits, {pct}%]")

    return "\n".join(lines) + "\n"


def _render_tree(node: dict, lines: list[str], indent: int) -> None:
    """Recursively render a directory tree into indented lines."""
    prefix = "  " * indent
    dirs = sorted(k for k in node if k != "__files__")
    files = sorted(node.get("__files__", []))  # type: ignore[arg-type]

    for d in dirs:
        lines.append(f"{prefix}{d}/")
        _render_tree(node[d], lines, indent + 1)  # type: ignore[arg-type]

    for f in files:
        lines.append(f"{prefix}{f}  #")


def _load_prompt(name: str) -> str:
    """Load an injected instruction from the bundled prompts/ directory."""
    path = _BUILTIN_PROMPTS / name
    if not path.exists():
        console.print(f"[red]Prompt file not found:[/red] {name}")
        raise typer.Exit(1)
    return path.read_text(encoding="utf-8")


def _require_init() -> Path:
    """Ensure .writ/ exists, return project root."""
    from writ.core import store

    if not store.is_initialized():
        console.print(
            "[red]Not initialized.[/red] Run [cyan]writ init[/cyan] first."
        )
        raise typer.Exit(1)
    return Path.cwd()


@docs_app.command(name="init")
def init_command(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite existing docs index."),
    ] = False,
) -> None:
    """Create a documentation index for knowledge health tracking.

    Creates a writ-docs-index file and prints an instruction for your
    AI agent to populate it by scanning the repository.

    \\b
    Examples:
      writ docs init
      writ docs init --force
    """
    from writ.core import store
    from writ.core.formatter import IDE_PATHS, IDEFormatter
    from writ.core.models import (
        CompositionConfig,
        CursorOverrides,
        FormatOverrides,
        InstructionConfig,
    )
    from writ.utils import append_log

    root = _require_init()

    existing = store.load_instruction("writ-docs-index")
    if existing and not force:
        console.print(
            "[yellow]Documentation index already exists.[/yellow] "
            "Use --force to recreate."
        )
        raise typer.Exit()

    index_content = _build_index_treeview(root)

    cfg = InstructionConfig(
        name="writ-docs-index",
        description="Documentation index -- annotated treeview of project knowledge files",
        task_type="rule",
        instructions=index_content,
        tags=["writ", "docs", "index"],
        composition=CompositionConfig(project_context=False),
        format_overrides=FormatOverrides(
            cursor=CursorOverrides(
                description="Documentation index for knowledge health tracking",
                always_apply=True,
            ),
        ),
    )
    store.save_instruction(cfg)

    detected_formats = [
        key for key, ide_cfg in IDE_PATHS.items()
        if (root / ide_cfg.detect).exists()
    ]
    for fmt in detected_formats:
        if fmt not in IDE_PATHS:
            continue
        formatter = IDEFormatter(fmt)
        path = formatter.write(cfg, index_content, root=root)
        console.print(f"[green]Wrote[/green] writ-docs-index -> {path}")

    if not detected_formats:
        console.print(
            "[green]Saved[/green] writ-docs-index to .writ/rules/writ-docs-index.yaml"
        )

    from writ.core.doc_health import find_doc_files

    n_files = len(find_doc_files(root))
    append_log(root, f"docs init -- created writ-docs-index with {n_files} files")

    prompt = _load_prompt("docs-init-v1.md")
    console.print()
    console.print("[bold cyan]--- Instruction for your AI agent ---[/bold cyan]")
    console.print()
    console.print(prompt)


@docs_app.command(name="check")
def check_command(
    path: Annotated[
        str | None,
        typer.Argument(help="Project root path (defaults to current directory)."),
    ] = None,
    output_json: Annotated[
        bool,
        typer.Option("--json", help="Output raw JSON (for agents/scripts)."),
    ] = False,
    user_only: Annotated[
        bool,
        typer.Option("--user", help="Show only user documentation files."),
    ] = False,
    show_all: Annotated[
        bool,
        typer.Option("--all", "-A", help="Show all files including static built-in."),
    ] = False,
) -> None:
    """Check documentation health across the project.

    Scans instruction files, rules, README, AGENTS.md, and other documentation
    that affects AI agent behavior. Detects dead file references, treeview
    drift, stale instructions, and contradictions.

    \\b
    Examples:
      writ docs check
      writ docs check --json
      writ docs check /path/to/repo
    """
    from writ.core.doc_health import run_health_check

    root = Path(path) if path else Path.cwd()
    if not root.is_dir():
        console.print(f"[red]Not a directory:[/red] {root}")
        raise typer.Exit(1)

    report = run_health_check(root)
    report = _filter_report_files(report, user_only=user_only, show_all=show_all)

    if output_json:
        data = {
            "health_score": report.health_score,
            "total_issues": report.total_issues,
            "files": [
                {
                    "path": f.path,
                    "freshness": f.freshness,
                    "lint_score": f.lint_score,
                    "issues": [
                        {"kind": i.kind, "message": i.message, "severity": i.severity}
                        for i in f.issues
                    ],
                }
                for f in report.files
            ],
        }
        console.print_json(json.dumps(data))
        return

    _display_report(report)


@docs_app.command(name="update")
def update_command(
    path: Annotated[
        str | None,
        typer.Argument(help="Project root path (defaults to current directory)."),
    ] = None,
    user_only: Annotated[
        bool,
        typer.Option("--user", help="Show only user documentation files."),
    ] = False,
    show_all: Annotated[
        bool,
        typer.Option("--all", "-A", help="Show all files including static built-in."),
    ] = False,
) -> None:
    """Run an AI-powered documentation update pass.

    Runs the heuristic health check first, then prints an instruction for
    your AI agent to act on the findings: fix stale docs, update the index,
    and log a summary of decisions.

    \\b
    Examples:
      writ docs update
      writ docs update /path/to/repo
    """
    from writ.core import store
    from writ.core.doc_health import run_health_check
    from writ.utils import append_log

    root = Path(path) if path else Path.cwd()
    if not root.is_dir():
        console.print(f"[red]Not a directory:[/red] {root}")
        raise typer.Exit(1)

    if not store.load_instruction("writ-docs-index"):
        console.print(
            "[yellow]No documentation index found.[/yellow] "
            "Run [cyan]writ docs init[/cyan] first to create one."
        )
        raise typer.Exit(1)

    report = run_health_check(root)
    report = _filter_report_files(report, user_only=user_only, show_all=show_all)

    check_context = _format_check_results(report)

    prompt = _load_prompt("docs-update-v1.md")

    append_log(root, "docs update -- triggered documentation update pass")

    console.print("[bold cyan]--- Documentation Update Instruction ---[/bold cyan]")
    console.print()
    console.print(prompt)
    console.print(check_context)


_WRIT_STATIC_PATTERNS = ("skills/writ/", "skills\\writ\\", "writ-context")
_WRIT_DYNAMIC_NAMES = ("writ-docs-index", "writ-log")


def _is_writ_static_doc(file_path: str) -> bool:
    """True for writ-managed files agents don't update (skills, writ-context)."""
    for pat in _WRIT_STATIC_PATTERNS:
        if pat in file_path:
            return True
    return False


def _is_writ_dynamic_doc(file_path: str) -> bool:
    """True for writ-managed files that agents DO update (docs-index, log)."""
    for name in _WRIT_DYNAMIC_NAMES:
        if name in file_path:
            return True
    return False


def _filter_report_files(report, *, user_only: bool, show_all: bool):  # type: ignore[type-arg]
    """Filter report files based on visibility flags.

    Default: user files + writ dynamic files. Static built-in hidden.
    --user: user files only.
    --all: everything.
    """
    if show_all:
        return report

    filtered = []
    for f in report.files:
        if _is_writ_static_doc(f.path):
            continue
        if user_only and _is_writ_dynamic_doc(f.path):
            continue
        filtered.append(f)

    report.files = filtered
    report.total_issues = sum(len(f.issues) for f in filtered)
    return report


def _format_check_results(report) -> str:  # type: ignore[type-arg]
    """Format health check results as plain text for LLM consumption."""
    lines: list[str] = []
    lines.append(f"Health score: {report.health_score}/100")
    lines.append(f"Total issues: {report.total_issues}")
    lines.append(f"Files scanned: {len(report.files)}")
    lines.append("")

    for f in report.files:
        status_parts: list[str] = []
        if f.freshness != "unknown":
            suffix = f" ({f.last_commit_ago} commits ago)" if f.last_commit_ago else ""
            status_parts.append(f"freshness={f.freshness}{suffix}")
        if f.issues:
            status_parts.append(f"{len(f.issues)} issue(s)")
        status = ", ".join(status_parts) if status_parts else "ok"
        lines.append(f"- {f.path}: {status}")

        for issue in f.issues:
            lines.append(f"    [{issue.severity}] {issue.kind}: {issue.message}")

    if not report.files:
        lines.append("No documentation files found.")

    return "\n".join(lines)


def _display_report(report) -> None:  # type: ignore[type-arg]
    """Display the health report with Rich formatting."""
    from rich.panel import Panel
    from rich.table import Table

    if not report.files:
        console.print(
            "[dim]No documentation files found.[/dim]\n"
            "Run [cyan]writ init[/cyan] to set up your project.",
        )
        return

    score = report.health_score
    if score >= 80:
        score_style = "green"
    elif score >= 50:
        score_style = "yellow"
    else:
        score_style = "red"

    console.print(Panel(
        f"[{score_style} bold]Project Documentation Health: {score}/100[/{score_style} bold]",
        border_style=score_style,
    ))

    table = Table(show_header=True, header_style="bold")
    table.add_column("File", min_width=35)
    table.add_column("Freshness", justify="center", min_width=10)
    table.add_column("Issues", min_width=40)

    for f in report.files:
        freshness_display = _freshness_label(f.freshness, f.last_commit_ago)

        if f.issues:
            issue_lines = []
            for issue in f.issues[:3]:
                issue_lines.append(issue.message)
            if len(f.issues) > 3:
                issue_lines.append(f"... +{len(f.issues) - 3} more")
            issues_text = "\n".join(issue_lines)
        else:
            issues_text = "[dim]-[/dim]"

        table.add_row(f.path, freshness_display, issues_text)

    console.print(table)

    files_needing_attention = sum(
        1 for f in report.files
        if f.issues or f.freshness in ("stale", "STALE")
    )
    if files_needing_attention > 0:
        console.print(
            f"\n[bold]{files_needing_attention} file(s) need attention.[/bold] "
            "Run [cyan]writ docs update[/cyan] to review and fix these issues.",
        )
    else:
        console.print("\n[green]All documentation files look healthy.[/green]")


def _freshness_label(freshness: str, commits_ago: int | None) -> str:
    """Format freshness label with color."""
    if freshness == "STALE":
        suffix = f" ({commits_ago} commits ago)" if commits_ago else ""
        return f"[red bold]STALE[/red bold]{suffix}"
    if freshness == "stale":
        suffix = f" ({commits_ago} commits ago)" if commits_ago else ""
        return f"[yellow]stale[/yellow]{suffix}"
    if freshness == "fresh":
        return "[green]fresh[/green]"
    return "[dim]unknown[/dim]"
