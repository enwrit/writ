"""MCP server exposing writ instructions, project context, and resources.

Allows external AI agents (in Cursor, Claude Desktop, etc.) to discover
and read this repo's instructions without the human running CLI commands.

Install: pip install enwrit[mcp]
Run:     writ mcp serve
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from writ.core import scanner, store
from writ.utils import yaml_dumps

mcp = FastMCP("writ")


# ---------------------------------------------------------------------------
# Tools -- actions external agents can invoke
# ---------------------------------------------------------------------------

@mcp.tool()
def writ_list_instructions() -> list[dict[str, str | None]]:
    """List all instructions available in this writ project.

    Returns a list of instruction summaries (name, description, task_type, tags).
    Use this to discover what instructions, rules, and context are available.
    """
    instructions = store.list_instructions()
    return [
        {
            "name": cfg.name,
            "description": cfg.description,
            "task_type": cfg.task_type,
            "tags": ", ".join(cfg.tags) if cfg.tags else None,
        }
        for cfg in instructions
    ]


@mcp.tool()
def writ_get_instruction(name: str) -> str:
    """Get the full content of a writ instruction by name.

    Returns the instruction as YAML (name, description, tags, instructions, composition).
    Use this to read another repo's agent instructions, rules, or context.
    """
    cfg = store.load_instruction(name)
    if cfg is None:
        return (
            f"Error: instruction '{name}' not found. "
            "Use writ_list_instructions to see available instructions."
        )
    return yaml_dumps(cfg.model_dump(mode="json"))


@mcp.tool()
def writ_get_project_context() -> str:
    """Get this project's auto-detected context (languages, frameworks, directory structure).

    Returns the project-context.md that writ generates on init. Use this to
    understand what kind of project you're connecting to.
    """
    context = store.load_project_context()
    if context:
        return context

    if not store.is_initialized():
        return "Error: this project has no .writ/ directory. Run 'writ init' first."

    languages = scanner.detect_languages()
    tree = scanner.get_directory_tree()
    parts = ["# Project Context\n"]
    if languages:
        parts.append("## Languages\n")
        for lang, count in sorted(languages.items(), key=lambda x: -x[1]):
            parts.append(f"- {lang}: {count} files")
    if tree:
        parts.append(f"\n## Directory Structure\n\n```\n{tree}\n```")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Resources -- read-only data external agents can pull into context
# ---------------------------------------------------------------------------

@mcp.resource("writ://instructions/{name}")
def instruction_resource(name: str) -> str:
    """Read a writ instruction by name."""
    cfg = store.load_instruction(name)
    if cfg is None:
        return f"Instruction '{name}' not found."
    return yaml_dumps(cfg.model_dump(mode="json"))


@mcp.resource("writ://project-context")
def project_context_resource() -> str:
    """Read this project's auto-detected context."""
    return store.load_project_context() or "No project context available."


def run_server() -> None:
    """Start the MCP server on stdio transport."""
    mcp.run(transport="stdio")
