"""Infer the instruction type from file path, name, or store metadata.

Used by ``writ lint --deep`` to select type-specific review hooks and by
scoring logic to weight dimensions appropriately.

Inference priority (first match wins):
    1. Explicit ``task_type`` from store metadata (if valid)
    2. Folder name patterns derived from ``IDE_PATHS``
    3. Filename stem heuristics
    4. Fallback: ``"other"``
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Known types returned by infer_instruction_type()
# ---------------------------------------------------------------------------

KNOWN_TYPES: frozenset[str] = frozenset({
    "agent", "skill", "rule", "plan", "context", "other",
})

# ---------------------------------------------------------------------------
# Folder-segment -> type mapping
#
# Built from IDE_PATHS conventions across all 11 supported IDEs.
# e.g. .cursor/skills/  -> skill
#      .claude/rules/   -> rule
#      .kiro/steering/  -> rule
#      .cursor/agents/  -> agent
#      .cursor/plans/   -> plan   (common user convention)
# ---------------------------------------------------------------------------

_FOLDER_TO_TYPE: dict[str, str] = {
    "skills": "skill",
    "agents": "agent",
    "rules": "rule",
    "steering": "rule",       # Kiro uses steering/ for rules
    "instructions": "rule",   # Copilot .github/instructions/
    "plans": "plan",
    "to-do": "plan",
    "context": "context",
    "programs": "context",    # programs are close to context
}

# Also match full IDE detect-dir roots that act as rule dirs themselves.
# e.g. .clinerules/ is itself the rules dir (no subdirectory).
_ROOT_RULE_DIRS: frozenset[str] = frozenset({
    ".clinerules",
    ".cursorrules",
    ".windsurfrules",
})

# ---------------------------------------------------------------------------
# Filename stem heuristics (checked after folder patterns)
# ---------------------------------------------------------------------------

_STEM_KEYWORDS: list[tuple[str, str]] = [
    ("skill", "skill"),
    ("rule", "rule"),
    ("plan", "plan"),
    ("context", "context"),
    ("agent", "agent"),
]


def infer_instruction_type(
    file_path: Path | None = None,
    name: str | None = None,
    task_type: str | None = None,
) -> str:
    """Return the inferred instruction type.

    Parameters
    ----------
    file_path:
        Filesystem path to the instruction file (absolute or relative).
    name:
        Instruction name (from store or CLI argument).
    task_type:
        Explicit ``task_type`` from store metadata (InstructionConfig).

    Returns
    -------
    str
        One of ``KNOWN_TYPES``: agent, skill, rule, plan, context, other.
    """
    # 1. Explicit metadata
    if task_type:
        normalized = task_type.lower().strip()
        if normalized in KNOWN_TYPES:
            return normalized
        if normalized == "program":
            return "context"
        if normalized == "template":
            return "other"

    # 2. Folder name patterns
    if file_path is not None:
        folder_type = _type_from_path(file_path)
        if folder_type:
            return folder_type

    # 3. Filename stem heuristics
    stem = ""
    if file_path is not None:
        stem = file_path.stem.lower()
    elif name:
        stem = name.lower()

    if stem:
        for keyword, itype in _STEM_KEYWORDS:
            if keyword in stem:
                return itype

    return "other"


def _type_from_path(file_path: Path) -> str | None:
    """Check folder segments and root-dir conventions."""
    parts = PurePosixPath(file_path.as_posix()).parts

    for part in parts:
        if part in _ROOT_RULE_DIRS:
            return "rule"

    for part in parts:
        result = _FOLDER_TO_TYPE.get(part)
        if result:
            return result

    return None
