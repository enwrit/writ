"""Read/write operations for .writ/ (project) and ~/.writ/ (global) stores."""

from __future__ import annotations

from pathlib import Path

from writ.core.models import GlobalConfig, InstructionConfig, ProjectConfig
from writ.utils import (
    ensure_dir,
    global_writ_dir,
    project_writ_dir,
    read_text_safe,
    yaml_dump,
    yaml_load,
)

_CONTENT_DIRS = ("agents", "rules", "context")

_EXCLUDE_IF_DEFAULT = {
    "author": None,
    "source": None,
    "includes": [],
    "format_overrides": {
        "cursor": None, "claude": None, "codex": None,
        "copilot": None, "windsurf": None, "kiro": None,
    },
}


def _clean_dump(cfg: InstructionConfig) -> dict:
    """Serialize InstructionConfig to a dict, omitting null/default-only fields."""
    data = cfg.model_dump(mode="json")
    for key in ("created", "updated"):
        if key in data and data[key] is not None:
            data[key] = str(data[key])
    for key, default_val in _EXCLUDE_IF_DEFAULT.items():
        if data.get(key) == default_val:
            data.pop(key, None)
    return data

_TASK_TYPE_TO_DIR: dict[str | None, str] = {
    "agent": "agents",
    "rule": "rules",
    "context": "context",
}


def _subdir_for(cfg: InstructionConfig) -> str:
    """Return the content subdirectory name based on task_type."""
    return _TASK_TYPE_TO_DIR.get(cfg.task_type, "agents")


def _find_in_content_dirs(root: Path, name: str) -> Path | None:
    """Search all content directories for <name>.yaml, return first match."""
    for subdir in _CONTENT_DIRS:
        path = root / subdir / f"{name}.yaml"
        if path.exists():
            return path
    return None


def _remove_stale_copies(root: Path, name: str, target_subdir: str) -> None:
    """Remove <name>.yaml from any content directory that isn't *target_subdir*."""
    for subdir in _CONTENT_DIRS:
        if subdir == target_subdir:
            continue
        stale = root / subdir / f"{name}.yaml"
        if stale.exists():
            stale.unlink()


def _collect_from_content_dirs(root: Path) -> list[InstructionConfig]:
    """Gather all InstructionConfig entries from every content directory."""
    results: list[InstructionConfig] = []
    for subdir in _CONTENT_DIRS:
        content_dir = root / subdir
        if not content_dir.exists():
            continue
        for path in sorted(content_dir.glob("*.yaml")):
            try:
                results.append(InstructionConfig(**yaml_load(path)))
            except Exception:  # noqa: BLE001
                pass
    return results


# ---------------------------------------------------------------------------
# Project store (.writ/)
# ---------------------------------------------------------------------------

def is_initialized() -> bool:
    """Check if the current directory has a .writ/ store."""
    return project_writ_dir().is_dir()


def init_project_store(*, clean: bool = False) -> Path:
    """Create the .writ/ directory structure. Returns the .writ/ path.

    If *clean* is True, remove all YAML files from content directories first
    (used by ``writ init --force`` for a fresh start).
    """
    root = project_writ_dir()
    if clean:
        for subdir in _CONTENT_DIRS:
            content_dir = root / subdir
            if content_dir.exists():
                for f in content_dir.glob("*.yaml"):
                    f.unlink()
    for subdir in _CONTENT_DIRS:
        ensure_dir(root / subdir)
    ensure_dir(root / "handoffs")
    ensure_dir(root / "memory")
    return root


def find_instruction_path(name: str) -> Path | None:
    """Return the file path for an instruction, searching all content directories."""
    return _find_in_content_dirs(project_writ_dir(), name)


def save_config(config: ProjectConfig) -> None:
    """Write .writ/config.yaml."""
    yaml_dump(project_writ_dir() / "config.yaml", config.model_dump())


def load_config() -> ProjectConfig:
    """Load .writ/config.yaml, returning defaults if it doesn't exist."""
    path = project_writ_dir() / "config.yaml"
    if path.exists():
        return ProjectConfig(**yaml_load(path))
    return ProjectConfig()


def save_instruction(cfg: InstructionConfig) -> Path:
    """Save an instruction to .writ/{agents,rules,context}/<name>.yaml.

    Routes to the correct subdirectory based on task_type.
    Removes stale copies from other directories to prevent duplicates.
    """
    root = project_writ_dir()
    subdir = _subdir_for(cfg)
    _remove_stale_copies(root, cfg.name, subdir)
    dest = root / subdir / f"{cfg.name}.yaml"
    ensure_dir(dest.parent)
    yaml_dump(dest, _clean_dump(cfg))
    return dest


def load_instruction(name: str) -> InstructionConfig | None:
    """Load an instruction by name, searching all content directories."""
    path = _find_in_content_dirs(project_writ_dir(), name)
    if path is None:
        return None
    return InstructionConfig(**yaml_load(path))


def list_instructions() -> list[InstructionConfig]:
    """List all instructions across all content directories in the project store."""
    return _collect_from_content_dirs(project_writ_dir())


def remove_instruction(name: str) -> bool:
    """Remove an instruction by name, searching all content directories."""
    path = _find_in_content_dirs(project_writ_dir(), name)
    if path is not None:
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
    for subdir in _CONTENT_DIRS:
        ensure_dir(root / subdir)
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


def save_to_library(cfg: InstructionConfig, alias: str | None = None) -> Path:
    """Save an instruction to the personal library (~/.writ/).

    Routes to the correct subdirectory based on task_type.
    Removes stale copies from other directories to prevent duplicates.
    """
    root = global_writ_dir()
    name = alias or cfg.name
    subdir = _subdir_for(cfg)
    _remove_stale_copies(root, name, subdir)
    dest = root / subdir / f"{name}.yaml"
    ensure_dir(dest.parent)
    yaml_dump(dest, _clean_dump(cfg))
    return dest


def load_from_library(name: str) -> InstructionConfig | None:
    """Load an instruction from the personal library, searching all content dirs."""
    path = _find_in_content_dirs(global_writ_dir(), name)
    if path is None:
        return None
    return InstructionConfig(**yaml_load(path))


def list_library() -> list[InstructionConfig]:
    """List all instructions in the personal library."""
    return _collect_from_content_dirs(global_writ_dir())
