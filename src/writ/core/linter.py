"""Validate agent config quality.

Based on findings from "Evaluating AGENTS.md" paper:
- Minimal instructions outperform verbose ones
- Conflicting instructions hurt performance
- Missing essentials (build commands, test commands) cause failures
"""

from __future__ import annotations

import re
from pathlib import Path

from writ.core.models import AgentConfig, LintResult

# ---------------------------------------------------------------------------
# Contradiction patterns (basic heuristic detection)
# ---------------------------------------------------------------------------

CONTRADICTION_PAIRS: list[tuple[str, str]] = [
    (r"\balways\b.*\buse\b.*\b(\w+)\b", r"\bnever\b.*\buse\b.*\b(\w+)\b"),
    (r"\bdo not\b.*\b(\w+)\b", r"\balways\b.*\b(\w+)\b"),
    (r"\bprefer\b.*\b(\w+)\b.*\bover\b.*\b(\w+)\b", r"\bprefer\b.*\b(\w+)\b.*\bover\b.*\b(\w+)\b"),
]


def lint(agent: AgentConfig) -> list[LintResult]:
    """Run all lint checks on an agent config. Returns list of findings."""
    results: list[LintResult] = []

    results.extend(_check_name(agent))
    results.extend(_check_instructions_length(agent))
    results.extend(_check_description(agent))
    results.extend(_check_tags(agent))
    results.extend(_check_project_context(agent))
    results.extend(_check_composition_references(agent))
    results.extend(_check_contradictions(agent))

    return results


def _check_name(agent: AgentConfig) -> list[LintResult]:
    """Validate agent name."""
    results: list[LintResult] = []
    if not agent.name:
        results.append(LintResult(
            level="error", rule="name-required", message="Agent name is required.",
        ))
    elif not re.match(r"^[a-z0-9][a-z0-9-]*$", agent.name):
        results.append(LintResult(
            level="warning",
            rule="name-format",
            message=f"Agent name '{agent.name}' should be lowercase alphanumeric with hyphens.",
        ))
    return results


def _check_instructions_length(agent: AgentConfig) -> list[LintResult]:
    """Check instruction word count (research: shorter is better)."""
    results: list[LintResult] = []
    if not agent.instructions:
        results.append(LintResult(
            level="warning",
            rule="instructions-empty",
            message="Agent has no instructions. Add instructions for it to be useful.",
        ))
        return results

    word_count = len(agent.instructions.split())
    if word_count > 2000:
        results.append(LintResult(
            level="warning",
            rule="instructions-long",
            message=(
                f"Instructions are {word_count} words. Research shows shorter "
                "instructions perform better. Consider trimming to under 2000 words."
            ),
        ))
    elif word_count < 20:
        results.append(LintResult(
            level="info",
            rule="instructions-short",
            message=(
                f"Instructions are only {word_count} words. "
                "Consider adding more context for better results."
            ),
        ))
    return results


def _check_description(agent: AgentConfig) -> list[LintResult]:
    """Check description quality."""
    results: list[LintResult] = []
    if not agent.description:
        results.append(LintResult(
            level="info",
            rule="description-missing",
            message=(
                "No description set. A good description helps "
                "with discovery and team communication."
            ),
        ))
    elif len(agent.description) < 10:
        results.append(LintResult(
            level="info",
            rule="description-short",
            message="Description is very short. Consider being more descriptive.",
        ))
    return results


def _check_tags(agent: AgentConfig) -> list[LintResult]:
    """Check tags."""
    results: list[LintResult] = []
    if not agent.tags:
        results.append(LintResult(
            level="info",
            rule="tags-missing",
            message="No tags set. Tags improve discoverability when published.",
        ))
    return results


def _check_project_context(agent: AgentConfig) -> list[LintResult]:
    """Check if project context exists when composition references it."""
    results: list[LintResult] = []
    if agent.composition.project_context:
        ctx_path = Path.cwd() / ".writ" / "project-context.md"
        if not ctx_path.exists():
            results.append(LintResult(
                level="info",
                rule="project-context-missing",
                message=(
                    "Agent expects project context but .writ/project-context.md "
                    "doesn't exist. Run 'writ init' to generate it."
                ),
            ))
    return results


def _check_composition_references(agent: AgentConfig) -> list[LintResult]:
    """Check that referenced agents exist."""
    results: list[LintResult] = []
    agents_dir = Path.cwd() / ".writ" / "agents"

    for parent_name in agent.composition.inherits_from:
        if not (agents_dir / f"{parent_name}.yaml").exists():
            results.append(LintResult(
                level="warning",
                rule="inherit-missing",
                message=(
                    f"Agent inherits from '{parent_name}' but no agent "
                    "with that name exists in this project."
                ),
            ))

    for source_name in agent.composition.receives_handoff_from:
        if not (agents_dir / f"{source_name}.yaml").exists():
            results.append(LintResult(
                level="warning",
                rule="handoff-source-missing",
                message=(
                    f"Agent receives handoff from '{source_name}' "
                    "but no agent with that name exists."
                ),
            ))

    return results


def _check_contradictions(agent: AgentConfig) -> list[LintResult]:
    """Basic heuristic contradiction detection in instructions."""
    results: list[LintResult] = []
    if not agent.instructions:
        return results

    text = agent.instructions.lower()
    lines = text.split("\n")

    # Check for "always X" + "never X" patterns
    always_patterns: list[str] = []
    never_patterns: list[str] = []
    for line in lines:
        always_match = re.findall(r"\balways\s+(?:use\s+)?(\w+)", line)
        never_match = re.findall(r"\bnever\s+(?:use\s+)?(\w+)", line)
        always_patterns.extend(always_match)
        never_patterns.extend(never_match)

    conflicts = set(always_patterns) & set(never_patterns)
    for word in conflicts:
        results.append(LintResult(
            level="warning",
            rule="contradiction",
            message=f"Possible contradiction: both 'always' and 'never' used with '{word}'.",
        ))

    return results
