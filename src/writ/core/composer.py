"""4-layer context composition engine -- the core innovation of writ.

Academic basis:
- Agent Context Protocols (arXiv 2505.14569): DAG-based execution blueprints
- Context Folding (arXiv 2510.24699): Branch & return for 10x context reduction

Layers (composed in order):
1. Project context -- auto-detected from repo (languages, frameworks, structure)
2. Inherited context -- from parent agents via inherits_from
3. Agent's own instructions -- the instructions field
4. Handoff context -- summaries from previous agent work
"""

from __future__ import annotations

from writ.core import store
from writ.core.models import AgentConfig


def compose(
    agent: AgentConfig,
    additional: list[str] | None = None,
    include_project: bool = True,
    include_handoffs: bool = True,
) -> str:
    """Compose full context for an agent from all 4 layers.

    Args:
        agent: The primary agent to compose for.
        additional: Extra agent names to include (--with flag).
        include_project: Include auto-detected project context (Layer 1).
        include_handoffs: Include handoff context (Layer 4).

    Returns:
        A single markdown document with all layers merged.
    """
    additional = additional or []
    layers: list[tuple[str, str]] = []

    # Layer 1: Project context (auto-detected)
    if include_project and agent.composition.project_context:
        project_ctx = store.load_project_context()
        if project_ctx:
            layers.append(("Project Context", project_ctx))

    # Layer 2: Inherited context (from other agents)
    for parent_name in agent.composition.inherits_from:
        parent = store.load_agent(parent_name)
        if parent and parent.instructions:
            layers.append((f"Inherited from {parent_name}", parent.instructions))

    # Layer 2b: Additional agents composed in (--with flag)
    for extra_name in additional:
        if extra_name == agent.name:
            continue  # Skip self
        extra = store.load_agent(extra_name)
        if extra and extra.instructions:
            layers.append((f"Context from {extra_name}", extra.instructions))

    # Layer 3: Agent's own instructions
    if agent.instructions:
        layers.append((f"Your Role: {agent.name}", agent.instructions))

    # Layer 4: Handoff context
    if include_handoffs:
        for source_name in agent.composition.receives_handoff_from:
            handoff = store.load_handoff(source_name, agent.name)
            if handoff:
                layers.append((f"Handoff from {source_name}", handoff))

    return _merge_layers(layers)


def _merge_layers(layers: list[tuple[str, str]]) -> str:
    """Merge context layers into a single markdown document.

    Uses clear section headers so the LLM understands the structure.
    Each layer is clearly delineated with separators.
    """
    if not layers:
        return ""

    parts: list[str] = []
    for title, content in layers:
        parts.append(f"## {title}\n\n{content.strip()}")

    return "\n\n---\n\n".join(parts)
