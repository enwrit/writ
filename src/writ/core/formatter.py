"""Export agent instructions to native IDE/CLI formats.

Safe formats (auto-detected, separate writ-owned files):
- cursor: .cursor/rules/ | .cursor/skills/writ/ | .cursor/agents/
- claude_rules: .claude/rules/ | .claude/skills/writ/ | .claude/agents/
- kiro_steering: .kiro/steering/ | .kiro/skills/writ/ | .kiro/agents/
- copilot: .github/instructions/ | .github/skills/writ/ | .github/agents/
- windsurf: .windsurf/rules/ | .windsurf/skills/writ/ | .windsurf/agents/
- cline: .clinerules/ | .cline/skills/writ/ | .cline/agents/
- roo: .roo/rules/ | .roo/skills/writ/ | .roo/agents/
- amazonq: .amazonq/rules/ | .amazonq/agents/
- gemini: .gemini/rules/ | .gemini/skills/writ/ | .gemini/agents/
- codex: .codex/rules/ | .codex/skills/writ/ | .codex/agents/
- opencode: .opencode/rules/ | .opencode/skills/writ/ | .opencode/agents/

Legacy formats (modify user-owned shared files -- explicit opt-in only):
- claude: CLAUDE.md (managed sections)
- agents_md: AGENTS.md (managed sections)
- copilot_legacy: .github/copilot-instructions.md
- windsurf_legacy: .windsurfrules
- codex_legacy: AGENTS.md (alias)
- kiro: AGENTS.md (alias)

Other:
- skill: SKILL.md (Anthropic standard, YAML frontmatter + body)
- agent-card: .well-known/<name>.agent-card.json
- cursor-mcp: .cursor/mcp.json
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from writ.core.models import InstructionConfig
from writ.utils import update_or_create_markdown, yaml_dumps

# ---------------------------------------------------------------------------
# IDE path configuration -- single source of truth for all IDE support
# ---------------------------------------------------------------------------


class IDEPathEntry(NamedTuple):
    """Path config for one content category (rules/skills/agents) in one IDE."""

    directory: str
    extension: str
    frontmatter_fn: Callable[[InstructionConfig], dict | None] | None = None
    namespaced: bool = False


class IDEConfig(NamedTuple):
    """Full path configuration for one IDE/CLI tool."""

    name: str
    detect: str
    rules: IDEPathEntry
    skills: IDEPathEntry
    agents: IDEPathEntry
    mcp: tuple[str, str] | None = None


# -- Frontmatter builders ---------------------------------------------------


def _cursor_rule_frontmatter(agent: InstructionConfig) -> dict | None:
    fm: dict = {
        "description": agent.description or f"Agent: {agent.name}",
        "alwaysApply": False,
    }
    if agent.format_overrides.cursor:
        ov = agent.format_overrides.cursor
        if ov.description:
            fm["description"] = ov.description
        fm["alwaysApply"] = ov.always_apply
        if ov.globs:
            fm["globs"] = ov.globs
    return fm


def _cursor_skill_frontmatter(agent: InstructionConfig) -> dict | None:
    return {
        "description": agent.description or f"Skill: {agent.name}",
        "alwaysApply": True,
    }


def _cursor_agent_frontmatter(agent: InstructionConfig) -> dict | None:
    return {
        "description": agent.description or f"Agent: {agent.name}",
        "alwaysApply": False,
    }


def _kiro_frontmatter(agent: InstructionConfig) -> dict | None:
    return {"inclusion": "always"}


# -- Central config ----------------------------------------------------------

IDE_PATHS: dict[str, IDEConfig] = {
    "cursor": IDEConfig(
        name="Cursor",
        detect=".cursor",
        rules=IDEPathEntry(".cursor/rules", "mdc", _cursor_rule_frontmatter),
        skills=IDEPathEntry(
            ".cursor/skills/writ", "mdc", _cursor_skill_frontmatter, namespaced=True,
        ),
        agents=IDEPathEntry(".cursor/agents", "mdc", _cursor_agent_frontmatter),
        mcp=(".cursor/mcp.json", "mcpServers"),
    ),
    "claude_rules": IDEConfig(
        name="Claude Code",
        detect=".claude",
        rules=IDEPathEntry(".claude/rules", "md"),
        skills=IDEPathEntry(".claude/skills/writ", "md", namespaced=True),
        agents=IDEPathEntry(".claude/agents", "md"),
        mcp=(".mcp.json", "mcpServers"),
    ),
    "kiro_steering": IDEConfig(
        name="Kiro",
        detect=".kiro",
        rules=IDEPathEntry(".kiro/steering", "md", _kiro_frontmatter),
        skills=IDEPathEntry(".kiro/skills/writ", "md", namespaced=True),
        agents=IDEPathEntry(".kiro/agents", "md"),
        mcp=(".kiro/settings/mcp.json", "mcpServers"),
    ),
    "copilot": IDEConfig(
        name="GitHub Copilot",
        detect=".github",
        rules=IDEPathEntry(".github/instructions", "instructions.md"),
        skills=IDEPathEntry(".github/skills/writ", "md", namespaced=True),
        agents=IDEPathEntry(".github/agents", "md"),
    ),
    "windsurf": IDEConfig(
        name="Windsurf",
        detect=".windsurf",
        rules=IDEPathEntry(".windsurf/rules", "md"),
        skills=IDEPathEntry(".windsurf/skills/writ", "md", namespaced=True),
        agents=IDEPathEntry(".windsurf/agents", "md"),
    ),
    "cline": IDEConfig(
        name="Cline",
        detect=".clinerules",
        rules=IDEPathEntry(".clinerules", "md"),
        skills=IDEPathEntry(".cline/skills/writ", "md", namespaced=True),
        agents=IDEPathEntry(".cline/agents", "md"),
    ),
    "roo": IDEConfig(
        name="Roo Code",
        detect=".roo",
        rules=IDEPathEntry(".roo/rules", "md"),
        skills=IDEPathEntry(".roo/skills/writ", "md", namespaced=True),
        agents=IDEPathEntry(".roo/agents", "md"),
    ),
    "amazonq": IDEConfig(
        name="Amazon Q",
        detect=".amazonq",
        rules=IDEPathEntry(".amazonq/rules", "md"),
        skills=IDEPathEntry(".amazonq/rules", "md"),
        agents=IDEPathEntry(".amazonq/agents", "md"),
    ),
    "gemini": IDEConfig(
        name="Gemini CLI",
        detect=".gemini",
        rules=IDEPathEntry(".gemini/rules", "md"),
        skills=IDEPathEntry(".gemini/skills/writ", "md", namespaced=True),
        agents=IDEPathEntry(".gemini/agents", "md"),
    ),
    "codex": IDEConfig(
        name="Codex",
        detect=".codex",
        rules=IDEPathEntry(".codex/rules", "md"),
        skills=IDEPathEntry(".codex/skills/writ", "md", namespaced=True),
        agents=IDEPathEntry(".codex/agents", "md"),
    ),
    "opencode": IDEConfig(
        name="OpenCode",
        detect=".opencode",
        rules=IDEPathEntry(".opencode/rules", "md"),
        skills=IDEPathEntry(".opencode/skills/writ", "md", namespaced=True),
        agents=IDEPathEntry(".opencode/agents", "md"),
    ),
}


# -- Content-category routing ------------------------------------------------

_CATEGORY_MAP: dict[str | None, str] = {
    "agent": "agents",
    "rule": "rules",
    "context": "rules",
    "program": "rules",
    "skill": "skills",
    "template": "rules",
}


def resolve_content_category(task_type: str | None) -> str:
    """Map instruction task_type to IDE content category (rules/skills/agents)."""
    return _CATEGORY_MAP.get(task_type, "rules")


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------


def _writ_filename(name: str, ext: str) -> str:
    """Build ``writ-<name>.<ext>`` avoiding a ``writ-writ-`` double prefix."""
    if name.startswith("writ-"):
        return f"{name}.{ext}"
    return f"writ-{name}.{ext}"


def _plain_filename(name: str, ext: str) -> str:
    """Build ``<name>.<ext>``, stripping ``writ-`` prefix if present."""
    bare = name.removeprefix("writ-")
    return f"{bare}.{ext}"


def _build_filename(entry: IDEPathEntry, name: str) -> str:
    """Build filename: plain name in namespaced dirs, writ- prefix otherwise."""
    if entry.namespaced:
        return _plain_filename(name, entry.extension)
    return _writ_filename(name, entry.extension)


# ---------------------------------------------------------------------------
# Base formatter
# ---------------------------------------------------------------------------


class BaseFormatter:
    """Base class for format writers."""

    format_name: str = ""

    def write(
        self,
        agent: InstructionConfig,
        composed_instructions: str,
        root: Path | None = None,
    ) -> Path:
        """Write composed instructions to the format's native file. Returns the file path."""
        raise NotImplementedError

    def clean(self, agent_name: str, root: Path | None = None) -> bool:
        """Remove this agent's output file/section. Returns True if cleaned."""
        return False


# ---------------------------------------------------------------------------
# IDEFormatter -- config-driven formatter for all safe formats
# ---------------------------------------------------------------------------


class IDEFormatter(BaseFormatter):
    """Config-driven formatter that routes to the correct IDE subdirectory
    based on the instruction's task_type and the IDE_PATHS config."""

    def __init__(self, format_key: str):
        self._key = format_key
        self.format_name = format_key

    def _get_path_entry(self, agent: InstructionConfig) -> IDEPathEntry:
        config = IDE_PATHS[self._key]
        category = resolve_content_category(agent.task_type)
        return getattr(config, category)

    def write(
        self,
        agent: InstructionConfig,
        composed_instructions: str,
        root: Path | None = None,
    ) -> Path:
        root = root or Path.cwd()
        entry = self._get_path_entry(agent)
        filename = _build_filename(entry, agent.name)
        path = root / entry.directory / filename
        path.parent.mkdir(parents=True, exist_ok=True)

        if entry.frontmatter_fn:
            fm_dict = entry.frontmatter_fn(agent)
            if fm_dict:
                fm_str = yaml_dumps(fm_dict).strip()
                content = f"---\n{fm_str}\n---\n\n{composed_instructions}\n"
            else:
                content = composed_instructions + "\n"
        else:
            content = composed_instructions + "\n"

        path.write_text(content, encoding="utf-8")
        return path

    def clean(self, agent_name: str, root: Path | None = None) -> bool:
        root = root or Path.cwd()
        config = IDE_PATHS[self._key]
        cleaned = False
        for category in ("rules", "skills", "agents"):
            entry: IDEPathEntry = getattr(config, category)
            filename = _build_filename(entry, agent_name)
            path = root / entry.directory / filename
            if path.exists():
                path.unlink()
                cleaned = True
        return cleaned


# -- Backward-compatible aliases for the original three safe formatters ------


class CursorFormatter(IDEFormatter):
    def __init__(self) -> None:
        super().__init__("cursor")


class ClaudeRulesFormatter(IDEFormatter):
    def __init__(self) -> None:
        super().__init__("claude_rules")


class KiroSteeringFormatter(IDEFormatter):
    def __init__(self) -> None:
        super().__init__("kiro_steering")


# ---------------------------------------------------------------------------
# Legacy formatters (shared-file, opt-in only via --format)
# ---------------------------------------------------------------------------


class ClaudeFormatter(BaseFormatter):
    format_name = "claude"

    def write(
        self, agent: InstructionConfig, composed_instructions: str,
        root: Path | None = None,
    ) -> Path:
        root = root or Path.cwd()
        path = root / "CLAUDE.md"
        section = f"## Agent: {agent.name}\n\n{composed_instructions}"
        update_or_create_markdown(path, section, marker_name=f"writ:{agent.name}")
        return path


class AgentsMdFormatter(BaseFormatter):
    format_name = "agents_md"

    def write(
        self, agent: InstructionConfig, composed_instructions: str,
        root: Path | None = None,
    ) -> Path:
        root = root or Path.cwd()
        path = root / "AGENTS.md"
        section = f"## {agent.name}\n\n{composed_instructions}"
        update_or_create_markdown(path, section, marker_name=f"writ:{agent.name}")
        return path


class CopilotLegacyFormatter(BaseFormatter):
    """Legacy: injects managed sections into .github/copilot-instructions.md."""

    format_name = "copilot_legacy"

    def write(
        self, agent: InstructionConfig, composed_instructions: str,
        root: Path | None = None,
    ) -> Path:
        root = root or Path.cwd()
        path = root / ".github" / "copilot-instructions.md"
        section = f"## Agent: {agent.name}\n\n{composed_instructions}"
        update_or_create_markdown(path, section, marker_name=f"writ:{agent.name}")
        return path


class WindsurfLegacyFormatter(BaseFormatter):
    """Legacy: injects managed sections into .windsurfrules."""

    format_name = "windsurf_legacy"

    def write(
        self, agent: InstructionConfig, composed_instructions: str,
        root: Path | None = None,
    ) -> Path:
        root = root or Path.cwd()
        path = root / ".windsurfrules"
        section = f"## Agent: {agent.name}\n\n{composed_instructions}"
        update_or_create_markdown(path, section, marker_name=f"writ:{agent.name}")
        return path


class CodexLegacyFormatter(AgentsMdFormatter):
    """Legacy: writes to AGENTS.md. Prefer safe ``codex`` format."""

    format_name = "codex_legacy"


class KiroFormatter(AgentsMdFormatter):
    format_name = "kiro"


# ---------------------------------------------------------------------------
# Special-purpose formatters (unchanged)
# ---------------------------------------------------------------------------


class AgentCardFormatter(BaseFormatter):
    """A2A Agent Card JSON -- machine-readable capability metadata."""

    format_name = "agent-card"

    def format_agent_card(self, agent: InstructionConfig) -> dict:
        capabilities = []
        for tag in agent.tags:
            capabilities.append({
                "type": tag,
                "description": f"{tag.replace('-', ' ').replace('_', ' ').title()} development",
            })
        return {
            "name": agent.name,
            "description": agent.description or f"Agent: {agent.name}",
            "version": agent.version,
            "url": f"https://enwrit.com/agents/{agent.name}",
            "api": {"type": "a2a", "url": f"https://api.enwrit.com/agents/{agent.name}"},
            "capabilities": capabilities,
            "provider": {"organization": "enwrit", "url": "https://enwrit.com"},
        }

    def write(
        self, agent: InstructionConfig, composed_instructions: str,
        root: Path | None = None,
    ) -> Path:
        root = root or Path.cwd()
        path = root / ".well-known" / f"{agent.name}.agent-card.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        card = self.format_agent_card(agent)
        path.write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
        return path


class SkillFormatter(BaseFormatter):
    """Anthropic SKILL.md format -- YAML frontmatter + markdown body."""

    format_name = "skill"

    def write(
        self, agent: InstructionConfig, composed_instructions: str,
        root: Path | None = None,
    ) -> Path:
        root = root or Path.cwd()
        path = root / "SKILL.md"
        frontmatter: dict = {
            "name": agent.name,
            "description": agent.description or f"Agent: {agent.name}",
            "version": agent.version,
            "tags": agent.tags,
        }
        fm_str = yaml_dumps(frontmatter).strip()
        body = f"# {agent.name}\n\n{composed_instructions}"
        content = f"---\n{fm_str}\n---\n\n{body}\n"
        path.write_text(content, encoding="utf-8")
        return path

    def clean(self, agent_name: str, root: Path | None = None) -> bool:
        root = root or Path.cwd()
        path = root / "SKILL.md"
        if path.exists():
            path.unlink()
            return True
        return False


class CursorMcpFormatter(BaseFormatter):
    """Generate Cursor MCP config JSON for connecting to writ MCP server."""

    format_name = "cursor-mcp"

    def write(
        self, agent: InstructionConfig, composed_instructions: str,
        root: Path | None = None,
    ) -> Path:
        root = root or Path.cwd()
        path = root / ".cursor" / "mcp.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        servers = existing.get("mcpServers", {})
        servers["writ"] = {"command": "writ", "args": ["mcp", "serve"]}
        existing["mcpServers"] = servers
        path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        return path


# ---------------------------------------------------------------------------
# Formatter registry
# ---------------------------------------------------------------------------

_LEGACY_FORMATTERS: dict[str, type[BaseFormatter]] = {
    "claude": ClaudeFormatter,
    "agents_md": AgentsMdFormatter,
    "copilot_legacy": CopilotLegacyFormatter,
    "windsurf_legacy": WindsurfLegacyFormatter,
    "codex_legacy": CodexLegacyFormatter,
    "kiro": KiroFormatter,
    "skill": SkillFormatter,
    "agent-card": AgentCardFormatter,
    "cursor-mcp": CursorMcpFormatter,
}

SAFE_FORMAT_NAMES: list[str] = list(IDE_PATHS.keys())

LEGACY_FORMAT_NAMES: list[str] = list(_LEGACY_FORMATTERS.keys())

ALL_FORMAT_NAMES: list[str] = SAFE_FORMAT_NAMES + LEGACY_FORMAT_NAMES


def get_formatter(format_name: str) -> BaseFormatter:
    """Get a formatter instance by name. Raises KeyError if unknown."""
    if format_name in IDE_PATHS:
        return IDEFormatter(format_name)
    cls = _LEGACY_FORMATTERS.get(format_name)
    if cls is None:
        valid = ", ".join(ALL_FORMAT_NAMES)
        raise KeyError(f"Unknown format '{format_name}'. Valid formats: {valid}")
    return cls()


def write_agent(
    agent: InstructionConfig,
    composed_instructions: str,
    formats: list[str],
    root: Path | None = None,
) -> list[Path]:
    """Write an agent to multiple formats. Returns list of written paths."""
    paths: list[Path] = []
    for fmt in formats:
        formatter = get_formatter(fmt)
        path = formatter.write(agent, composed_instructions, root=root)
        paths.append(path)
    return paths
