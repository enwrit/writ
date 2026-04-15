"""Utility helpers for writ CLI."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

console = Console()
error_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# YAML I/O
# ---------------------------------------------------------------------------

class _LiteralBlockDumper(yaml.SafeDumper):
    """SafeDumper that writes multi-line strings as literal blocks (|)
    and short lists of scalars as flow sequences [a, b, c]."""


def _literal_str_representer(dumper: yaml.Dumper, data: str) -> yaml.ScalarNode:
    if "\n" in data:
        lines = data.split("\n")
        clean = "\n".join(line.rstrip() for line in lines)
        clean = clean.replace("\t", "    ")
        return dumper.represent_scalar("tag:yaml.org,2002:str", clean, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


def _compact_list_representer(
    dumper: yaml.Dumper, data: list,  # type: ignore[type-arg]
) -> yaml.SequenceNode:
    """Use flow style [a, b, c] for flat lists of scalars (e.g. tags)."""
    if data and all(isinstance(item, (str, int, float, bool)) for item in data):
        return dumper.represent_sequence(
            "tag:yaml.org,2002:seq", data, flow_style=True,
        )
    return dumper.represent_sequence(
        "tag:yaml.org,2002:seq", data, flow_style=False,
    )


_LiteralBlockDumper.add_representer(str, _literal_str_representer)
_LiteralBlockDumper.add_representer(list, _compact_list_representer)


def yaml_load(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dict."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def yaml_dump(path: Path, data: dict[str, Any]) -> None:
    """Write a dict to a YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            data, f,
            Dumper=_LiteralBlockDumper,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


def yaml_dumps(data: dict[str, Any]) -> str:
    """Serialize a dict to a YAML string."""
    return yaml.dump(
        data,
        Dumper=_LiteralBlockDumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )


def yaml_loads_safe(text: str) -> dict[str, Any]:
    """Parse a YAML string, returning an empty dict on failure."""
    try:
        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        return {}


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def project_writ_dir() -> Path:
    """Return the .writ/ directory for the current project (cwd)."""
    return Path.cwd() / ".writ"


def global_writ_dir() -> Path:
    """Return the ~/.writ/ directory (global/personal store)."""
    return Path.home() / ".writ"


def ensure_dir(path: Path) -> Path:
    """Create a directory (and parents) if it doesn't exist, return the path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# String helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Convert a string to a URL/filename-safe slug.

    Example: "My Cool Agent!" -> "my-cool-agent"
    Example: "@sanjeed5/go"   -> "sanjeed5-go"
    """
    text = text.lower().strip()
    text = re.sub(r"[@/\\]", "-", text)
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


# ---------------------------------------------------------------------------
# Instruction classification helpers
# ---------------------------------------------------------------------------

_WRIT_DYNAMIC_NAMES = {"writ-docs-index", "writ-log"}


def is_builtin_instruction(tags: list[str] | None) -> bool:
    """True if instruction was installed by writ (built-in skills, context, etc.)."""
    if not tags:
        return False
    return "builtin" in tags or ("writ" in tags and "skill" in tags)


def is_writ_managed(name: str, tags: list[str] | None) -> bool:
    """True if instruction is any writ-managed file (builtin OR writ-context/docs/log)."""
    if is_builtin_instruction(tags):
        return True
    return name.startswith("writ-") and bool(tags) and "writ" in tags


def is_writ_dynamic(name: str) -> bool:
    """True for writ-managed files that agents update (docs-index, log)."""
    return name in _WRIT_DYNAMIC_NAMES


def is_writ_static(name: str, tags: list[str] | None) -> bool:
    """True for writ-managed files that are NOT updated by agents."""
    return is_writ_managed(name, tags) and not is_writ_dynamic(name)


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------

WRIT_SECTION_START = "<!-- writ:{name}:start -->"
WRIT_SECTION_END = "<!-- writ:{name}:end -->"


def update_or_create_markdown(
    path: Path,
    section_content: str,
    marker_name: str,
) -> None:
    """Update a named section in a markdown file, or create the file.

    Uses HTML comment markers to identify sections managed by writ.
    Preserves all content outside the markers.
    """
    start_marker = WRIT_SECTION_START.format(name=marker_name)
    end_marker = WRIT_SECTION_END.format(name=marker_name)
    wrapped = f"{start_marker}\n{section_content}\n{end_marker}"

    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if start_marker in existing and end_marker in existing:
            # Replace existing section
            pattern = re.escape(start_marker) + r".*?" + re.escape(end_marker)
            updated = re.sub(pattern, wrapped, existing, flags=re.DOTALL)
            path.write_text(updated, encoding="utf-8")
        else:
            # Append new section
            path.write_text(existing.rstrip() + "\n\n" + wrapped + "\n", encoding="utf-8")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(wrapped + "\n", encoding="utf-8")


def read_text_safe(path: Path) -> str | None:
    """Read a text file, returning None if it doesn't exist."""
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def append_log(root: Path, entry: str) -> None:
    """Append a timestamped entry to the writ-log instruction.

    The log is stored as a writ instruction (writ-log) and written to IDE
    dirs so agents and humans can access it directly.  On first call it
    creates the instruction; subsequent calls append to the YAML and
    re-write the IDE files.
    """
    from datetime import UTC, datetime

    from writ.core import store
    from writ.core.models import (
        CompositionConfig,
        CursorOverrides,
        FormatOverrides,
        InstructionConfig,
    )

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    line = f"- [{timestamp}] {entry}"
    header = (
        "# writ log\n\n"
        "Persistent knowledge log. Agents append findings, decisions,\n"
        "and summaries here so ephemeral context survives across sessions.\n\n"
    )

    existing = store.load_instruction("writ-log")
    if existing and existing.instructions:
        new_instructions = existing.instructions.rstrip("\n") + "\n" + line + "\n"
    else:
        new_instructions = header + line + "\n"

    cfg = InstructionConfig(
        name="writ-log",
        description="Knowledge persistence log -- decisions, findings, summaries across sessions",
        task_type="context",
        instructions=new_instructions,
        tags=["writ", "log"],
        composition=CompositionConfig(project_context=False),
        format_overrides=FormatOverrides(
            cursor=CursorOverrides(
                description="Knowledge persistence log (writ)",
                always_apply=False,
            ),
        ),
    )
    store.save_instruction(cfg)

    _write_log_to_ides(cfg, new_instructions, root)


def _write_log_to_ides(cfg, content: str, root: Path) -> None:  # type: ignore[type-arg]
    """Write the log instruction to all detected IDE directories."""
    from writ.core.formatter import IDE_PATHS, IDEFormatter

    for key, ide_cfg in IDE_PATHS.items():
        if (root / ide_cfg.detect).is_dir():
            formatter = IDEFormatter(key)
            formatter.write(cfg, content, root=root)
