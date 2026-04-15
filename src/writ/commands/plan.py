"""writ plan review -- AI-powered plan review."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Annotated

import typer

from writ.utils import console

plan_app = typer.Typer(
    name="plan",
    help="AI-powered plan review and analysis.",
    no_args_is_help=True,
)


def _load_rubric() -> str:
    """Load the plan review rubric from the bundled .md file."""
    rubric_path = Path(__file__).parent.parent / "core" / "rubrics" / "plan-review-v1.md"
    if not rubric_path.exists():
        console.print("[red]Plan review rubric not found.[/red]")
        raise typer.Exit(1)
    return rubric_path.read_text(encoding="utf-8")


def _build_user_prompt(plan_text: str, project_context: str | None) -> str:
    """Assemble the user prompt from plan text and optional project context."""
    parts: list[str] = []
    if project_context:
        parts.append("## Project Context\n")
        parts.append(project_context)
        parts.append("\n---\n")
    parts.append("## Plan to Review\n")
    parts.append(plan_text)
    return "\n".join(parts)


def _display_streaming(token_gen) -> str:  # type: ignore[type-arg]
    """Stream tokens to terminal, return the full collected text."""
    collected: list[str] = []
    for chunk in token_gen:
        sys.stdout.write(chunk)
        sys.stdout.flush()
        collected.append(chunk)
    sys.stdout.write("\n")
    return "".join(collected)


_BUILTIN_PROMPTS = Path(__file__).resolve().parent.parent / "templates" / "_builtin" / "prompts"


def _run_local_review(plan_path: Path, with_plan: bool) -> None:
    """Print plan review rubric as an injected instruction for the IDE's AI."""
    rubric_path = _BUILTIN_PROMPTS / "plan-review-local-v1.md"
    if not rubric_path.exists():
        console.print("[red]Local review prompt not found.[/red]")
        raise typer.Exit(1)
    rubric = rubric_path.read_text(encoding="utf-8")

    console.print("[bold cyan]--- Plan Review Instruction ---[/bold cyan]")
    console.print()
    console.print(rubric)

    if with_plan:
        plan_text = plan_path.read_text(encoding="utf-8").strip()
        console.print()
        console.print(
            f"[bold cyan]--- Plan to Review: {plan_path} ---[/bold cyan]",
        )
        console.print()
        console.print(plan_text)


def _display_review(review_text: str | list | dict, model_label: str, file_path: str) -> None:
    """Parse and display a plan review with Rich formatting."""
    from rich.panel import Panel

    header = (
        f"[bold]Plan Review:[/bold] {file_path}\n"
        f"[dim]Model: {model_label} | Rubric: plan-review-v1[/dim]"
    )

    try:
        if isinstance(review_text, dict):
            data = review_text
        elif isinstance(review_text, list):
            data = {"feedback": review_text}
        else:
            data = json.loads(review_text)
            if isinstance(data, list):
                data = {"feedback": data}
    except (json.JSONDecodeError, TypeError):
        console.print(Panel(header, border_style="cyan"))
        console.print(str(review_text))
        return

    console.print(Panel(header, border_style="cyan"))

    feedback = data.get("feedback", [])
    if feedback:
        console.print("\n[bold]TECHNICAL CONCERNS:[/bold]")
        for i, item in enumerate(feedback, 1):
            topic = item.get("topic", "")
            detail = item.get("detail", "")
            console.print(f"  [bold]{i}. {topic}[/bold]")
            for line in detail.split("\n"):
                console.print(f"     {line}")
            console.print()

    feasibility = data.get("feasibility_notes", "")
    if feasibility:
        console.print("[bold]FEASIBILITY:[/bold]")
        for line in feasibility.split("\n"):
            console.print(f"  {line}")
        console.print()

    alternatives = data.get("alternatives", [])
    if alternatives:
        console.print("[bold]ALTERNATIVES CONSIDERED:[/bold]")
        for alt in alternatives:
            console.print(f"  - {alt}")
        console.print()

    overall = data.get("overall_assessment", "")
    if overall:
        console.print("[bold]OVERALL:[/bold]")
        for line in overall.split("\n"):
            console.print(f"  {line}")
        console.print()


@plan_app.command(name="review")
def review_command(
    file: Annotated[
        str,
        typer.Argument(help="Path to the plan file (.md, .mdc, .txt)."),
    ],
    local: Annotated[
        bool,
        typer.Option(
            "--local",
            help="Review via your configured local model (writ model set local).",
        ),
    ] = False,
    cloud: Annotated[
        bool,
        typer.Option(
            "--cloud",
            help="Review via enwrit.com API only (requires login).",
        ),
    ] = False,
    with_plan: Annotated[
        bool,
        typer.Option(
            "--with-plan",
            help="Include plan content inline in the prompt output.",
        ),
    ] = False,
    no_context: Annotated[
        bool,
        typer.Option("--no-context", help="Skip project context (faster)."),
    ] = False,
    output_json: Annotated[
        bool,
        typer.Option("--json", help="Output raw JSON (for agents/scripts)."),
    ] = False,
    subagent: Annotated[
        bool,
        typer.Option(
            "--subagent",
            help="Instruct the IDE to launch a subagent for the review.",
        ),
    ] = False,
    # LEGACY aliases (hidden) -------------------------------------------------
    prompt: Annotated[
        bool,
        typer.Option(
            "--prompt", hidden=True,
            help="LEGACY: prompt is now the default.",
        ),
    ] = False,
) -> None:
    """Review an implementation plan with AI.

    By default, prints the review rubric for your IDE's AI agent to
    analyze the plan (prompt injection). Use --local to send to your
    configured local model (e.g. LM Studio), or --cloud for the
    enwrit.com API.

    \\b
    Examples:
      writ plan review plan.md                 # prompt for IDE agent (default)
      writ plan review plan.md --with-plan     # prompt + inline plan content
      writ plan review plan.md --local         # your local model
      writ plan review plan.md --cloud         # enwrit.com API
      writ plan review plan.md --cloud --json  # API with JSON output
      writ plan review plan.md --no-context    # skip project context
    """
    plan_path = Path(file)
    if not plan_path.exists():
        console.print(f"[red]File not found:[/red] {file}")
        raise typer.Exit(1)

    if local:
        _run_model_review(plan_path, no_context, output_json)
        return

    if cloud:
        _run_cloud_review(plan_path, no_context, output_json, file)
        return

    # Default: prompt injection for IDE agent
    if subagent:
        console.print("[bold cyan]--- Subagent Task ---[/bold cyan]")
        console.print()
        console.print(
            f"Launch a subagent and have it run:\n\n"
            f"  writ plan review {file}\n\n"
            f"The subagent will receive the review rubric and analyze "
            f"the plan. It should follow the rubric and report its "
            f"findings back to you."
        )
        return
    _run_local_review(plan_path, with_plan=with_plan)


def _run_model_review(
    plan_path: Path,
    no_context: bool,
    output_json: bool,
) -> None:
    """Review plan via the user's configured model (writ model set)."""
    from writ.core import llm_client

    model_cfg = llm_client.get_model_config()
    if model_cfg is None:
        console.print(
            "[red]No model configured.[/red]\n\n"
            "Set up a local model first:\n"
            "  [cyan]writ model set local "
            "--url http://127.0.0.1:1234/v1[/cyan]",
        )
        raise typer.Exit(1)

    plan_text = plan_path.read_text(encoding="utf-8").strip()
    if not plan_text:
        console.print("[red]Plan file is empty.[/red]")
        raise typer.Exit(1)

    project_context: str | None = None
    if not no_context:
        from writ.core import store
        project_context = store.load_project_context()

    rubric = _load_rubric()
    user_prompt = _build_user_prompt(plan_text, project_context)

    model_label = (
        f"{model_cfg.provider} "
        f"({llm_client._resolve_model(model_cfg)})"
    )
    interactive = llm_client.is_interactive() and not output_json

    if interactive:
        console.print(
            f"[dim]Reviewing plan with {model_label}...[/dim]",
        )
    try:
        if interactive:
            token_gen = llm_client.call_llm(
                rubric, user_prompt, stream=True, json_mode=True,
            )
            review_text = _display_streaming(token_gen)
        else:
            result = llm_client.call_llm(
                rubric, user_prompt, stream=False, json_mode=True,
            )
            if not isinstance(result, str):
                result = "".join(result)
            review_text = result
    except llm_client.LLMError as exc:
        console.print(f"[red]Model error:[/red] {exc}")
        raise typer.Exit(1) from None

    if output_json:
        try:
            if isinstance(review_text, (dict, list)):
                parsed = review_text
            else:
                parsed = json.loads(review_text)
            console.print_json(json.dumps(parsed))
        except (json.JSONDecodeError, TypeError):
            console.print(str(review_text))
    else:
        _display_review(review_text, model_label, str(plan_path))


def _run_cloud_review(
    plan_path: Path,
    no_context: bool,
    output_json: bool,
    file_label: str,
) -> None:
    """Review plan via enwrit.com API only (never uses configured model)."""
    from writ.core import auth as auth_mod
    from writ.core import llm_client

    if not auth_mod.is_logged_in():
        console.print(
            "[red]--cloud requires an enwrit account.[/red]\n"
            "Run [cyan]writ register[/cyan] or "
            "[cyan]writ login[/cyan] first.",
        )
        raise typer.Exit(1)

    plan_text = plan_path.read_text(encoding="utf-8").strip()
    if not plan_text:
        console.print("[red]Plan file is empty.[/red]")
        raise typer.Exit(1)

    project_context: str | None = None
    if not no_context:
        from writ.core import store
        project_context = store.load_project_context()

    model_label = "enwrit.com (Gemini)"
    interactive = llm_client.is_interactive() and not output_json

    if interactive:
        from rich.status import Status

        with Status(
            "[dim]Reviewing plan via enwrit.com...[/dim]",
            console=console,
        ):
            t0 = time.monotonic()
            try:
                review_text = llm_client.call_backend_plan_review(
                    plan_text, project_context,
                )
            except llm_client.LLMError as exc:
                console.print(f"[red]Error:[/red] {exc}")
                raise typer.Exit(1) from None
            elapsed = time.monotonic() - t0
        console.print(f"[dim]Completed in {elapsed:.1f}s[/dim]")
    else:
        try:
            review_text = llm_client.call_backend_plan_review(
                plan_text, project_context,
            )
        except llm_client.LLMError as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(1) from None

    if output_json:
        try:
            if isinstance(review_text, (dict, list)):
                parsed = review_text
            else:
                parsed = json.loads(review_text)
            console.print_json(json.dumps(parsed))
        except (json.JSONDecodeError, TypeError):
            console.print(str(review_text))
    else:
        _display_review(review_text, model_label, file_label)
