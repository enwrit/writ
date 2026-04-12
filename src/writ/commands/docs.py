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

    return _INDEX_HEADER + "\n".join(lines) + "\n"


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

    check_context = _format_check_results(report)

    prompt = _load_prompt("docs-update-v1.md")

    append_log(root, "docs update -- triggered documentation update pass")

    console.print("[bold cyan]--- Documentation Update Instruction ---[/bold cyan]")
    console.print()
    console.print(prompt)
    console.print(check_context)


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
            "Run [cyan]writ docs update[/cyan] to trigger an AI-powered fix.",
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
