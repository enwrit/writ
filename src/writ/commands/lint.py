"""writ lint -- Validate instruction quality and compute scores."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from writ.core import linter as lint_engine
from writ.core import store
from writ.core.models import InstructionConfig, LintScore
from writ.utils import console, project_writ_dir


def _maybe_ml_score(
    agent: InstructionConfig,
    results: list,
    force_code: bool = False,
) -> LintScore:
    """Compute lint score, upgrading to Tier 2 ML when models are available.

    Returns Tier 2 (ML) by default, Tier 1 (code) if --code or models missing.
    """
    tier1 = lint_engine.compute_score(agent, results)
    if force_code:
        return tier1
    try:
        from writ.models.tier2 import models_available
        if models_available():
            from writ.core.ml_scorer import compute_score_ml
            return compute_score_ml(tier1, instruction_text=agent.instructions or "")
    except Exception:
        pass
    return tier1

_CHANGED_PATTERNS = (
    ".writ/agents/",
    ".writ/rules/",
    ".writ/context/",
    ".writ/programs/",
    "CLAUDE.md",
    "AGENTS.md",
    "SKILL.md",
    ".windsurfrules",
    ".cursorrules",
    ".github/copilot-instructions.md",
)

LEVEL_STYLES = {
    "error": "[bold red]ERROR[/bold red]",
    "warning": "[yellow]WARN[/yellow]",
    "info": "[dim]INFO[/dim]",
}


def _parse_file_to_config(file_path: Path) -> InstructionConfig:
    """Parse a raw file into InstructionConfig without writ init.

    Supports YAML files, markdown with YAML frontmatter (via
    python-frontmatter), and plain markdown/text as instructions.
    """
    content = file_path.read_text(encoding="utf-8")
    name = file_path.stem

    if file_path.suffix in (".yaml", ".yml"):
        import yaml

        data = yaml.safe_load(content) or {}
        if isinstance(data, dict):
            data.setdefault("name", name)
            return InstructionConfig(**data)

    try:
        import frontmatter

        post = frontmatter.loads(content)
        meta = post.metadata or {}
        meta.setdefault("name", name)
        meta.setdefault("instructions", post.content)
        return InstructionConfig(**meta)
    except ImportError:
        pass
    except Exception:  # noqa: BLE001
        pass

    return InstructionConfig(name=name, instructions=content)


def _score_color(score: int) -> str:
    if score >= 70:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"


def _badge_url(score: int) -> str:
    """Return shields.io badge URL for writ_lint score."""
    color = _score_color(score)
    return f"https://img.shields.io/badge/writ_lint-{score}%2F100-{color}"


def _get_changed_instruction_files() -> list[Path]:
    """Return paths of instruction files modified since last commit."""
    try:
        root_out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        root = Path(root_out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        root = Path.cwd()

    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
            cwd=root,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return []

    result: list[Path] = []
    for line in out.stdout.strip().splitlines():
        if not line.strip():
            continue
        p = (root / line.strip()).resolve()
        if not p.exists():
            continue
        if any(line.startswith(pat) for pat in _CHANGED_PATTERNS):
            result.append(p)
        elif p.suffix == ".mdc":
            result.append(p)
    return result


def _print_score(lint_score: LintScore, quiet: bool = False) -> None:
    """Print the full lint score in rich format.

    When quiet=True, shows headline + dimension table but suppresses
    individual issues and suggestions.
    """
    from rich.table import Table

    color = _score_color(lint_score.score)
    console.print(
        f"\n  Score: [{color}][bold]{lint_score.score}"
        f"[/bold] / 100[/{color}]",
    )

    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("Dimension", style="bold", min_width=14)
    table.add_column("Score", justify="right", min_width=5)
    table.add_column("Summary", style="dim")

    for dim in lint_score.dimensions:
        dc = _score_color(dim.score)
        table.add_row(
            dim.label,
            f"[{dc}]{dim.score}[/{dc}]",
            dim.summary,
        )

    console.print(table)

    if not quiet and lint_score.suggestions:
        console.print("\n  [bold]Suggestions:[/bold]")
        for i, sug in enumerate(lint_score.suggestions, 1):
            console.print(f"    {i}. {sug}")


def _score_to_json(lint_score: LintScore) -> str:
    """Serialize LintScore to JSON for --json output."""
    return lint_score.model_dump_json(indent=2)


_LINT_SCORES_FILE = "lint-scores.json"


def _lint_timestamp() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep="T")


def _path_key_for_scores(path: Path | None) -> str | None:
    if path is None:
        return None
    cwd = Path.cwd().resolve()
    try:
        resolved = path.resolve()
        rel = resolved.relative_to(cwd)
        return rel.as_posix()
    except (ValueError, OSError):
        try:
            return path.resolve().as_posix()
        except OSError:
            return None


def _storage_entry_from_lint_score(lint_score: LintScore) -> dict:
    ts = _lint_timestamp()
    dims = {d.name: d.score for d in lint_score.dimensions}
    return {
        "headline_score": lint_score.score,
        "tier": lint_score.tier,
        "dimensions": dims,
        "issue_count": len(lint_score.issues),
        "suggestion_count": len(lint_score.suggestions),
        "timestamp": ts,
    }


def _dim_name_from_api_row(d: dict) -> str:
    name = d.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip().lower()
    label = d.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip().lower().replace(" ", "_")
    return ""


def _storage_entry_from_deep_dict(data: dict) -> dict:
    ts = _lint_timestamp()
    dims: dict[str, int] = {}
    for row in data.get("dimensions") or []:
        if not isinstance(row, dict):
            continue
        key = _dim_name_from_api_row(row)
        if not key:
            continue
        try:
            dims[key] = int(row.get("score", 0))
        except (TypeError, ValueError):
            dims[key] = 0
    issues = data.get("issues")
    if not isinstance(issues, list):
        issues = []
    suggestions = data.get("suggestions")
    if not isinstance(suggestions, list):
        suggestions = []
    tier = data.get("tier")
    if not isinstance(tier, str) or not tier:
        tier = "ai"
    try:
        headline = int(data.get("score", 0))
    except (TypeError, ValueError):
        headline = 0
    return {
        "headline_score": headline,
        "tier": tier,
        "dimensions": dims,
        "issue_count": len(issues),
        "suggestion_count": len(suggestions),
        "timestamp": ts,
    }


def _merge_write_lint_scores(updates: dict[str, dict]) -> None:
    if not updates or not store.is_initialized():
        return
    root = project_writ_dir()
    if not root.is_dir():
        return
    out_path = root / _LINT_SCORES_FILE
    now_meta = _lint_timestamp()
    try:
        scores: dict[str, dict] = {}
        meta: dict[str, str] = {}
        if out_path.is_file():
            raw = out_path.read_text(encoding="utf-8")
            if raw.strip():
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    existing_scores = loaded.get("scores")
                    if isinstance(existing_scores, dict):
                        scores = {
                            str(k): v
                            for k, v in existing_scores.items()
                            if isinstance(v, dict)
                        }
                    existing_meta = loaded.get("_meta")
                    if isinstance(existing_meta, dict):
                        meta = {
                            str(k): str(v)
                            for k, v in existing_meta.items()
                        }
        scores.update(updates)
        meta["last_updated"] = now_meta
        payload = {"scores": scores, "_meta": meta}
        out_path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        pass


def _persist_lint_scores(
    *,
    lint_score: LintScore | None = None,
    deep_response: dict | None = None,
    file: Path | None = None,
    instruction_name: str | None = None,
) -> None:
    if not store.is_initialized():
        return
    rel_key: str | None = None
    if file is not None:
        rel_key = _path_key_for_scores(file)
    elif instruction_name:
        inst_path = store.find_instruction_path(instruction_name)
        rel_key = _path_key_for_scores(inst_path)
    if not rel_key:
        return
    if lint_score is not None:
        entry = _storage_entry_from_lint_score(lint_score)
    elif deep_response is not None:
        entry = _storage_entry_from_deep_dict(deep_response)
    else:
        return
    _merge_write_lint_scores({rel_key: entry})


def _run_deep_lint(
    name: str | None,
    file: Path | None,
    json_output: bool,
    ci: bool,
    min_score: int,
    score_only: bool = False,
    quiet: bool = False,
) -> None:
    """Run AI-powered lint via the enwrit.com backend."""
    from writ.core import auth

    token = auth.get_token()
    if not token:
        console.print(
            "[red]--deep requires an enwrit account.[/red] "
            "Run [cyan]writ register[/cyan] or [cyan]writ login[/cyan] first.",
        )
        raise typer.Exit(1)

    if file:
        if not file.exists():
            console.print(f"[red]File not found:[/red] {file}")
            raise typer.Exit(1)
        agent = _parse_file_to_config(file)
    elif name:
        if not store.is_initialized():
            console.print(
                "[red]Not initialized.[/red] Run "
                "[cyan]writ init[/cyan] first, or pass a file path.",
            )
            raise typer.Exit(1)
        agent = store.load_instruction(name)
        if not agent:
            console.print(f"[red]Agent '{name}' not found.[/red]")
            raise typer.Exit(1)
    else:
        console.print(
            "[yellow]--deep requires a target.[/yellow] "
            "Specify a file path or agent name.",
        )
        raise typer.Exit(1)

    content = agent.instructions or ""
    if not content.strip():
        console.print("[yellow]Instruction content is empty.[/yellow]")
        raise typer.Exit(1)

    import httpx

    from writ.core.store import load_global_config

    cfg = load_global_config()
    base_url = cfg.registry_url.rstrip("/")

    console.print("[dim]Requesting AI-powered analysis...[/dim]")
    try:
        resp = httpx.post(
            f"{base_url}/lint",
            json={"content": content, "tier": "ai", "source": "cli"},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
    except httpx.RequestError as exc:
        console.print(
            f"[red]Network error:[/red] {exc}. "
            "Falling back to code-based scoring.",
        )
        _fallback_local_lint(agent, file, json_output, ci, min_score)
        return

    if resp.status_code == 429:
        console.print(
            "[yellow]Daily AI limit reached.[/yellow] "
            "Falling back to code-based scoring.",
        )
        _fallback_local_lint(agent, file, json_output, ci, min_score)
        return

    if resp.status_code != 200:
        console.print(
            f"[yellow]AI scoring unavailable (HTTP {resp.status_code}).[/yellow] "
            "Falling back to code-based scoring.",
        )
        _fallback_local_lint(agent, file, json_output, ci, min_score)
        return

    data = resp.json()
    tier = data.get("tier", "code")
    score = data.get("score", 0)

    if json_output:
        sys.stdout.write(json.dumps(data, indent=2) + "\n")
    elif score_only:
        color = _score_color(score)
        console.print(f"[{color}]{score}[/{color}]")
    else:
        color = _score_color(score)
        tier_label = (
            "AI Score" if tier == "ai"
            else "Code-based Score"
        )
        console.print(
            f"\n  {tier_label}: [{color}][bold]{score}"
            f"[/bold] / 100[/{color}]",
        )
        if tier == "ai":
            console.print("  [dim](powered by Gemini)[/dim]")
        elif tier == "code":
            console.print(
                "  [dim](AI scoring unavailable, "
                "showing code-based score)[/dim]",
            )

        dims = data.get("dimensions", [])
        if dims:
            from rich.table import Table

            table = Table(show_header=True, box=None, padding=(0, 1))
            table.add_column("Dimension", style="bold", min_width=14)
            table.add_column("Score", justify="right", min_width=5)
            table.add_column("Summary", style="dim")
            for d in dims:
                dc = _score_color(d.get("score", 0))
                table.add_row(
                    d.get("label", d.get("name", "")),
                    f"[{dc}]{d.get('score', '?')}[/{dc}]",
                    d.get("summary", ""),
                )
            console.print(table)

        if not quiet:
            suggestions = data.get("suggestions", [])
            if suggestions:
                console.print("\n  [bold]Suggestions:[/bold]")
                for i, sug in enumerate(suggestions, 1):
                    console.print(f"    {i}. {sug}")

    _persist_lint_scores(
        deep_response=data,
        file=file,
        instruction_name=name if file is None else None,
    )

    if ci and score < min_score:
        raise typer.Exit(1)


def _run_deep_local_lint(
    name: str | None,
    file: Path | None,
    json_output: bool,
    ci: bool,
    min_score: int,
    score_only: bool = False,
    quiet: bool = False,
) -> None:
    """Run local AI-powered lint via fine-tuned Qwen model."""
    if file:
        if not file.exists():
            console.print(f"[red]File not found:[/red] {file}")
            raise typer.Exit(1)
        agent = _parse_file_to_config(file)
    elif name:
        if not store.is_initialized():
            console.print(
                "[red]Not initialized.[/red] Run "
                "[cyan]writ init[/cyan] first, or pass a file path.",
            )
            raise typer.Exit(1)
        agent = store.load_instruction(name)
        if not agent:
            console.print(f"[red]Agent '{name}' not found.[/red]")
            raise typer.Exit(1)
    else:
        console.print(
            "[yellow]--deep-local requires a target.[/yellow] "
            "Specify a file path or agent name.",
        )
        raise typer.Exit(1)

    content = agent.instructions or ""
    if not content.strip():
        console.print("[yellow]Instruction content is empty.[/yellow]")
        raise typer.Exit(1)

    console.print("[dim]Running local AI analysis...[/dim]")

    try:
        from writ.core.local_llm import compute_score_local

        results = lint_engine.lint(agent, source_path=file)
        tier1 = lint_engine.compute_score(agent, results)
        lint_score = compute_score_local(
            content, tier1_issues=tier1.issues
        )
    except SystemExit:
        raise
    except Exception as exc:
        console.print(
            f"[red]Local AI scoring failed:[/red] {exc}\n"
            "Falling back to ML/code-based scoring.",
        )
        _fallback_local_lint(agent, file, json_output, ci, min_score)
        return

    if json_output:
        sys.stdout.write(_score_to_json(lint_score) + "\n")
    elif score_only:
        color = _score_color(lint_score.score)
        console.print(f"[{color}]{lint_score.score}[/{color}]")
    else:
        if not quiet:
            ai_issues = [i for i in lint_score.issues if i.rule == "local-ai"]
            if ai_issues:
                console.print()
                for item in ai_issues:
                    style = LEVEL_STYLES.get(item.level, item.level)
                    console.print(f"  {style} {item.message}")

        _print_score(lint_score, quiet=quiet)
        console.print("  [dim](writ-lint-0.8B -- fine-tuned on 30k+ expert evaluations)[/dim]")

    _persist_lint_scores(
        lint_score=lint_score,
        file=file,
        instruction_name=name if file is None else None,
    )

    if ci and lint_score.score < min_score:
        raise typer.Exit(1)


def _fallback_local_lint(
    agent: InstructionConfig,
    file: Path | None,
    json_output: bool,
    ci: bool,
    min_score: int,
) -> None:
    """Run local lint as fallback from --deep (uses ML when available)."""
    results = lint_engine.lint(agent, source_path=file)
    lint_score = _maybe_ml_score(agent, results)

    if json_output:
        sys.stdout.write(_score_to_json(lint_score) + "\n")
    else:
        _print_results(results)
        _print_score(lint_score)

    _persist_lint_scores(
        lint_score=lint_score,
        file=file,
        instruction_name=agent.name if file is None else None,
    )

    if ci and lint_score.score < min_score:
        raise typer.Exit(1)


def _looks_like_file(value: str) -> bool:
    """Return True if the argument looks like a file path rather than a store name."""
    p = Path(value)
    if p.exists() and p.is_file():
        return True
    _file_extensions = {
        ".md", ".mdc", ".yaml", ".yml", ".txt",
        ".windsurfrules", ".cursorrules",
    }
    if p.suffix.lower() in _file_extensions:
        return True
    if "/" in value or "\\" in value:
        return True
    return False


def lint_command(
    name: Annotated[
        str | None,
        typer.Argument(
            help="File path or agent name to lint (auto-detected).",
        ),
    ] = None,
    file: Annotated[
        Path | None,
        typer.Option(
            "--file", "-f",
            help="(Deprecated) Lint a raw file. Pass the path as the argument instead.",
            hidden=True,
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output full score as JSON (for CI/tooling).",
        ),
    ] = False,
    ci: Annotated[
        bool,
        typer.Option(
            "--ci",
            help="Exit code 1 if score below threshold.",
        ),
    ] = False,
    min_score: Annotated[
        int,
        typer.Option(
            "--min-score",
            help="Minimum score for --ci (default: 50).",
        ),
    ] = 50,
    score_only: Annotated[
        bool,
        typer.Option(
            "--score",
            help="Show only the headline score.",
        ),
    ] = False,
    badge: Annotated[
        bool,
        typer.Option(
            "--badge",
            help="Print shields.io badge URL for the score.",
        ),
    ] = False,
    changed: Annotated[
        bool,
        typer.Option(
            "--changed",
            help="Only lint files modified since last commit.",
        ),
    ] = False,
    deep: Annotated[
        bool,
        typer.Option(
            "--deep",
            help="AI-powered analysis via enwrit.com (requires login).",
        ),
    ] = False,
    code: Annotated[
        bool,
        typer.Option(
            "--code",
            help="Force code-based Tier 1 scoring (skip ML models).",
        ),
    ] = False,
    deep_local: Annotated[
        bool,
        typer.Option(
            "--deep-local",
            help="Local AI analysis via fine-tuned Qwen model (no API needed).",
        ),
    ] = False,
    stop_server: Annotated[
        bool,
        typer.Option(
            "--stop-server",
            help="Stop the persistent local AI server (frees GPU memory).",
        ),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet", "-q",
            help="Show headline + dimensions only (suppress issues and suggestions).",
        ),
    ] = False,
) -> None:
    """Validate instruction quality and compute scores.

    Checks for: instruction length, weak language, bloat,
    missing verification, contradictions, and more. Produces
    a 0-100 quality score across 6 dimensions.

    By default uses ML-predicted scores (Tier 2) when models
    are available. Use --code for deterministic code-only scoring,
    --deep for AI-powered analysis via enwrit.com, or --deep-local
    for local AI analysis via a fine-tuned Qwen model.

    Example:
        writ lint                         # lint all (ML or code)
        writ lint reviewer                # lint by store name
        writ lint AGENTS.md               # lint a file (auto-detected)
        writ lint CLAUDE.md --deep        # AI analysis (API)
        writ lint rules.mdc --json        # JSON output
        writ lint --code                  # force Tier 1 only
        writ lint --ci --min-score 60     # fail CI if < 60
        writ lint --changed               # only modified files
        writ lint --badge                 # print badge URL
        writ lint CLAUDE.md --deep-local  # AI analysis (local)
        writ lint --stop-server           # free GPU memory
    """
    if stop_server:
        from writ.core.local_llm import stop_server as _stop

        if _stop():
            console.print("[green]Local AI server stopped.[/green]")
        else:
            console.print("[dim]No local AI server running.[/dim]")
        return
    if file is None and name is not None and _looks_like_file(name):
        file = Path(name)
        name = None
    if deep_local:
        _run_deep_local_lint(
            name=name,
            file=file,
            json_output=json_output,
            ci=ci,
            min_score=min_score,
            score_only=score_only,
            quiet=quiet,
        )
        return
    if deep:
        _run_deep_lint(
            name=name,
            file=file,
            json_output=json_output,
            ci=ci,
            min_score=min_score,
            score_only=score_only,
            quiet=quiet,
        )
        return
    if changed:
        changed_files = _get_changed_instruction_files()
        if not changed_files:
            console.print("[yellow]No instruction files changed.[/yellow]")
            return

        all_scores_changed: list[LintScore] = []
        scores_batch: dict[str, dict] = {}
        for fp in changed_files:
            agent = _parse_file_to_config(fp)
            results = lint_engine.lint(agent, source_path=fp)
            lint_score = _maybe_ml_score(agent, results, force_code=code)
            all_scores_changed.append(lint_score)
            if store.is_initialized():
                rel_k = _path_key_for_scores(fp)
                if rel_k:
                    scores_batch[rel_k] = _storage_entry_from_lint_score(lint_score)

            if json_output:
                data = json.loads(lint_score.model_dump_json())
                data["name"] = agent.name
                data["file"] = str(fp)
                sys.stdout.write(json.dumps(data, indent=2) + "\n")
            elif badge:
                pass
            elif score_only:
                color = _score_color(lint_score.score)
                console.print(
                    f"  {fp.name}: [{color}]{lint_score.score}[/{color}]",
                )
            elif quiet:
                console.print(f"\n[bold]{fp.name}[/bold]:")
                _print_score(lint_score, quiet=True)
            else:
                console.print(f"\n[bold]{fp.name}[/bold]:")
                _print_results(results)
                _print_score(lint_score)

        if badge:
            avg = sum(s.score for s in all_scores_changed) // len(all_scores_changed)
            console.print(_badge_url(avg))

        if not json_output and not score_only and not badge and not quiet:
            _print_summary(all_scores_changed)

        _merge_write_lint_scores(scores_batch)

        if ci and all_scores_changed:
            worst = min(s.score for s in all_scores_changed)
            if worst < min_score:
                raise typer.Exit(1)
        return

    if file:
        if not file.exists():
            console.print(f"[red]File not found:[/red] {file}")
            raise typer.Exit(1)

        agent = _parse_file_to_config(file)
        results = lint_engine.lint(agent, source_path=file)
        lint_score = _maybe_ml_score(agent, results, force_code=code)

        if json_output:
            sys.stdout.write(_score_to_json(lint_score) + "\n")
        elif badge:
            console.print(_badge_url(lint_score.score))
        elif score_only:
            color = _score_color(lint_score.score)
            console.print(
                f"[{color}]{lint_score.score}[/{color}]",
            )
        elif quiet:
            console.print(f"\n[bold]{file.name}[/bold]:")
            _print_score(lint_score, quiet=True)
        else:
            console.print(f"\n[bold]{file.name}[/bold]:")
            _print_results(results)
            _print_score(lint_score)

        _persist_lint_scores(lint_score=lint_score, file=file)

        if ci and lint_score.score < min_score:
            raise typer.Exit(1)

        return

    if not store.is_initialized():
        console.print(
            "[red]Not initialized.[/red] Run "
            "[cyan]writ init[/cyan] first, or pass a file path "
            "(e.g. [cyan]writ lint AGENTS.md[/cyan]).",
        )
        raise typer.Exit(1)

    if name:
        agent = store.load_instruction(name)
        if not agent:
            console.print(
                f"[red]Agent '{name}' not found.[/red] "
                "Run [cyan]writ list[/cyan] to see available.",
            )
            raise typer.Exit(1)
        agents = [agent]
    else:
        agents = store.list_instructions()
        if not agents:
            console.print("[yellow]No agents to lint.[/yellow]")
            return

    all_scores: list[LintScore] = []
    scores_batch: dict[str, dict] = {}

    for agent in agents:
        src_path = store.find_instruction_path(agent.name)
        results = lint_engine.lint(agent, source_path=src_path)
        lint_score = _maybe_ml_score(agent, results, force_code=code)
        all_scores.append(lint_score)
        if store.is_initialized():
            rel_k = _path_key_for_scores(src_path)
            if rel_k:
                scores_batch[rel_k] = _storage_entry_from_lint_score(lint_score)

        if json_output:
            data = json.loads(lint_score.model_dump_json())
            data["name"] = agent.name
            sys.stdout.write(
                json.dumps(data, indent=2) + "\n",
            )
        elif badge:
            pass
        elif score_only:
            color = _score_color(lint_score.score)
            console.print(
                f"  {agent.name}: "
                f"[{color}]{lint_score.score}[/{color}]",
            )
        elif quiet:
            console.print(f"\n[bold]{agent.name}[/bold]:")
            _print_score(lint_score, quiet=True)
        else:
            if not results:
                console.print(
                    f"[green]  {agent.name}[/green] -- "
                    "all checks passed "
                    f"(score: {lint_score.score})",
                )
            else:
                console.print(
                    f"\n[bold]{agent.name}[/bold]:",
                )
                _print_results(results)
                _print_score(lint_score)

    if badge and all_scores:
        avg = sum(s.score for s in all_scores) // len(all_scores)
        console.print(_badge_url(avg))
    elif not json_output and not score_only and not badge and not quiet:
        _print_summary(all_scores)

    _merge_write_lint_scores(scores_batch)

    if ci:
        worst = min(
            s.score for s in all_scores
        ) if all_scores else 0
        if worst < min_score:
            raise typer.Exit(1)


def _print_results(results: list) -> None:
    """Print individual lint results."""
    for r in results:
        style = LEVEL_STYLES.get(r.level, r.level)
        rule_str = f" [{r.rule}]" if r.rule else ""
        line_str = f" line {r.line}" if r.line else ""
        console.print(
            f"  {style}{rule_str}{line_str} {r.message}",
        )


def _print_summary(scores: list[LintScore]) -> None:
    """Print overall summary."""
    console.print()
    if not scores:
        return

    total_errors = sum(
        1 for s in scores for i in s.issues
        if i.level == "error"
    )
    total_warnings = sum(
        1 for s in scores for i in s.issues
        if i.level == "warning"
    )
    avg_score = sum(s.score for s in scores) // len(scores)

    color = _score_color(avg_score)
    console.print(
        f"  Average score: [{color}][bold]{avg_score}"
        f"[/bold] / 100[/{color}]",
    )

    if total_errors:
        console.print(
            f"  [bold red]{total_errors} error(s)[/bold red]"
            f", {total_warnings} warning(s)",
        )
    elif total_warnings:
        console.print(
            f"  [yellow]{total_warnings} warning(s)"
            "[/yellow], no errors",
        )
    else:
        console.print("  [green]All checks passed![/green]")
