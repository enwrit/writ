"""Read/write operations for .writ/ (project) and ~/.writ/ (global) stores."""

from __future__ import annotations

from pathlib import Path

from writ.core.models import AgentConfig, GlobalConfig, ProjectConfig
from writ.utils import (
    ensure_dir,
    global_writ_dir,
    project_writ_dir,
    read_text_safe,
    yaml_dump,
    yaml_load,
)

# ---------------------------------------------------------------------------
# Project store (.writ/)
# ---------------------------------------------------------------------------

def is_initialized() -> bool:
    """Check if the current directory has a .writ/ store."""
    return project_writ_dir().is_dir()


def init_project_store() -> Path:
    """Create the .writ/ directory structure. Returns the .writ/ path."""
    root = project_writ_dir()
    ensure_dir(root / "agents")
    ensure_dir(root / "handoffs")
    ensure_dir(root / "memory")
    return root


def save_config(config: ProjectConfig) -> None:
    """Write .writ/config.yaml."""
    yaml_dump(project_writ_dir() / "config.yaml", config.model_dump())


def load_config() -> ProjectConfig:
    """Load .writ/config.yaml, returning defaults if it doesn't exist."""
    path = project_writ_dir() / "config.yaml"
    if path.exists():
        return ProjectConfig(**yaml_load(path))
    return ProjectConfig()


def save_agent(agent: AgentConfig) -> Path:
    """Save an agent config to .writ/agents/<name>.yaml. Returns the file path."""
    path = project_writ_dir() / "agents" / f"{agent.name}.yaml"
    data = agent.model_dump(mode="json")
    # Convert date objects to ISO strings for YAML
    for key in ("created", "updated"):
        if key in data and data[key] is not None:
            data[key] = str(data[key])
    yaml_dump(path, data)
    return path


def load_agent(name: str) -> AgentConfig | None:
    """Load an agent from .writ/agents/<name>.yaml. Returns None if not found."""
    path = project_writ_dir() / "agents" / f"{name}.yaml"
    if not path.exists():
        return None
    return AgentConfig(**yaml_load(path))


def list_agents() -> list[AgentConfig]:
    """List all agents in the project store."""
    agents_dir = project_writ_dir() / "agents"
    if not agents_dir.exists():
        return []

    agents = []
    for path in sorted(agents_dir.glob("*.yaml")):
        try:
            agents.append(AgentConfig(**yaml_load(path)))
        except Exception:  # noqa: BLE001
            pass  # Skip malformed files
    return agents


def remove_agent(name: str) -> bool:
    """Remove an agent from the project store. Returns True if removed."""
    path = project_writ_dir() / "agents" / f"{name}.yaml"
    if path.exists():
        path.unlink()
        return True
    return False


def save_project_context(content: str) -> None:
    """Write .writ/project-context.md."""
    path = project_writ_dir() / "project-context.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_project_context() -> str | None:
    """Load .writ/project-context.md, returns None if not found."""
    return read_text_safe(project_writ_dir() / "project-context.md")


def save_handoff(from_agent: str, to_agent: str, content: str) -> None:
    """Save a handoff document to .writ/handoffs/."""
    path = project_writ_dir() / "handoffs" / f"{from_agent}-to-{to_agent}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_handoff(from_agent: str, to_agent: str) -> str | None:
    """Load a handoff document. Returns None if not found."""
    return read_text_safe(
        project_writ_dir() / "handoffs" / f"{from_agent}-to-{to_agent}.md"
    )


# ---------------------------------------------------------------------------
# Global store (~/.writ/)
# ---------------------------------------------------------------------------

def init_global_store() -> Path:
    """Create ~/.writ/ directory structure. Returns the path."""
    root = global_writ_dir()
    ensure_dir(root / "agents")
    ensure_dir(root / "memory")
    ensure_dir(root / "templates")
    ensure_dir(root / "cache")
    return root


def save_global_config(config: GlobalConfig) -> None:
    """Write ~/.writ/config.yaml."""
    yaml_dump(global_writ_dir() / "config.yaml", config.model_dump())


def load_global_config() -> GlobalConfig:
    """Load ~/.writ/config.yaml, returning defaults if it doesn't exist."""
    path = global_writ_dir() / "config.yaml"
    if path.exists():
        return GlobalConfig(**yaml_load(path))
    return GlobalConfig()


def save_to_library(agent: AgentConfig, alias: str | None = None) -> Path:
    """Save an agent to the personal library (~/.writ/agents/)."""
    name = alias or agent.name
    path = global_writ_dir() / "agents" / f"{name}.yaml"
    data = agent.model_dump(mode="json")
    for key in ("created", "updated"):
        if key in data and data[key] is not None:
            data[key] = str(data[key])
    yaml_dump(path, data)
    return path


def load_from_library(name: str) -> AgentConfig | None:
    """Load an agent from the personal library."""
    path = global_writ_dir() / "agents" / f"{name}.yaml"
    if not path.exists():
        return None
    return AgentConfig(**yaml_load(path))


def list_library() -> list[AgentConfig]:
    """List all agents in the personal library."""
    agents_dir = global_writ_dir() / "agents"
    if not agents_dir.exists():
        return []

    agents = []
    for path in sorted(agents_dir.glob("*.yaml")):
        try:
            agents.append(AgentConfig(**yaml_load(path)))
        except Exception:  # noqa: BLE001
            pass
    return agents
