"""Export agent instructions to native IDE/CLI formats.

Supported formats (safe -- separate writ-owned files):
- cursor: .cursor/rules/writ-<name>.mdc
- claude_rules: .claude/rules/writ-<name>.md (auto-loaded by Claude Code)
- kiro_steering: .kiro/steering/writ-<name>.md (auto-loaded by Kiro)

Legacy formats (modify user-owned shared files -- explicit opt-in only):
- claude: CLAUDE.md (managed sections)
- agents_md: AGENTS.md (managed sections)
- copilot: .github/copilot-instructions.md
- windsurf: .windsurfrules
- codex: AGENTS.md (alias)
- kiro: AGENTS.md (alias, prefer kiro_steering)

Other:
- skill: SKILL.md (Anthropic standard, YAML frontmatter + body)
- agent-card: .well-known/<name>.agent-card.json
- cursor-mcp: .cursor/mcp.json
"""

from __future__ import annotations

import json
from pathlib import Path

from writ.core.models import InstructionConfig
from writ.utils import update_or_create_markdown, yaml_dumps

# ---------------------------------------------------------------------------
# Base formatter
# ---------------------------------------------------------------------------

def _writ_filename(name: str, ext: str) -> str:
    """Build ``writ-<name>.<ext>`` avoiding a ``writ-writ-`` double prefix."""
    if name.startswith("writ-"):
        return f"{name}.{ext}"
    return f"writ-{name}.{ext}"


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
# Cursor: .cursor/rules/writ-<name>.mdc
# ---------------------------------------------------------------------------

class CursorFormatter(BaseFormatter):
    format_name = "cursor"

    def write(
        self,
        agent: InstructionConfig,
        composed_instructions: str,
        root: Path | None = None,
    ) -> Path:
        root = root or Path.cwd()
        path = root / ".cursor" / "rules" / _writ_filename(agent.name, "mdc")
        path.parent.mkdir(parents=True, exist_ok=True)

        # Build frontmatter
        frontmatter: dict = {
            "description": agent.description or f"Agent: {agent.name}",
            "alwaysApply": False,
        }

        # Merge cursor-specific overrides
        if agent.format_overrides.cursor:
            overrides = agent.format_overrides.cursor
            if overrides.description:
                frontmatter["description"] = overrides.description
            frontmatter["alwaysApply"] = overrides.always_apply
            if overrides.globs:
                frontmatter["globs"] = overrides.globs

        fm_str = yaml_dumps(frontmatter).strip()
        content = f"---\n{fm_str}\n---\n\n{composed_instructions}\n"
        path.write_text(content, encoding="utf-8")
        return path

    def clean(self, agent_name: str, root: Path | None = None) -> bool:
        root = root or Path.cwd()
        path = root / ".cursor" / "rules" / _writ_filename(agent_name, "mdc")
        if path.exists():
            path.unlink()
            return True
        return False


# ---------------------------------------------------------------------------
# Claude Code: CLAUDE.md
# ---------------------------------------------------------------------------

class ClaudeFormatter(BaseFormatter):
    format_name = "claude"

    def write(
        self,
        agent: InstructionConfig,
        composed_instructions: str,
        root: Path | None = None,
    ) -> Path:
        root = root or Path.cwd()
        path = root / "CLAUDE.md"
        section = f"## Agent: {agent.name}\n\n{composed_instructions}"
        update_or_create_markdown(path, section, marker_name=f"writ:{agent.name}")
        return path


# ---------------------------------------------------------------------------
# AGENTS.md (universal format -- Codex, Kiro, general)
# ---------------------------------------------------------------------------

class AgentsMdFormatter(BaseFormatter):
    format_name = "agents_md"

    def write(
        self,
        agent: InstructionConfig,
        composed_instructions: str,
        root: Path | None = None,
    ) -> Path:
        root = root or Path.cwd()
        path = root / "AGENTS.md"
        section = f"## {agent.name}\n\n{composed_instructions}"
        update_or_create_markdown(path, section, marker_name=f"writ:{agent.name}")
        return path


# ---------------------------------------------------------------------------
# GitHub Copilot: .github/copilot-instructions.md
# ---------------------------------------------------------------------------

class CopilotFormatter(BaseFormatter):
    format_name = "copilot"

    def write(
        self,
        agent: InstructionConfig,
        composed_instructions: str,
        root: Path | None = None,
    ) -> Path:
        root = root or Path.cwd()
        path = root / ".github" / "copilot-instructions.md"
        section = f"## Agent: {agent.name}\n\n{composed_instructions}"
        update_or_create_markdown(path, section, marker_name=f"writ:{agent.name}")
        return path


# ---------------------------------------------------------------------------
# Windsurf: .windsurfrules
# ---------------------------------------------------------------------------

class WindsurfFormatter(BaseFormatter):
    format_name = "windsurf"

    def write(
        self,
        agent: InstructionConfig,
        composed_instructions: str,
        root: Path | None = None,
    ) -> Path:
        root = root or Path.cwd()
        path = root / ".windsurfrules"
        # Windsurf uses a single file, so we use sections
        section = f"## Agent: {agent.name}\n\n{composed_instructions}"
        update_or_create_markdown(path, section, marker_name=f"writ:{agent.name}")
        return path


# ---------------------------------------------------------------------------
# Codex (alias for AGENTS.md)
# ---------------------------------------------------------------------------

class CodexFormatter(AgentsMdFormatter):
    format_name = "codex"


# ---------------------------------------------------------------------------
# Kiro (alias for AGENTS.md)
# ---------------------------------------------------------------------------

class KiroFormatter(AgentsMdFormatter):
    format_name = "kiro"


# ---------------------------------------------------------------------------
# Claude Code rules: .claude/rules/writ-<name>.md (separate file, safe)
# ---------------------------------------------------------------------------

class ClaudeRulesFormatter(BaseFormatter):
    """Write to .claude/rules/writ-<name>.md -- auto-loaded by Claude Code.

    Files in .claude/rules/ without a ``paths:`` frontmatter are loaded at
    launch with the same priority as .claude/CLAUDE.md (always-on).
    """

    format_name = "claude_rules"

    def write(
        self,
        agent: InstructionConfig,
        composed_instructions: str,
        root: Path | None = None,
    ) -> Path:
        root = root or Path.cwd()
        path = root / ".claude" / "rules" / _writ_filename(agent.name, "md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(composed_instructions + "\n", encoding="utf-8")
        return path

    def clean(self, agent_name: str, root: Path | None = None) -> bool:
        root = root or Path.cwd()
        path = root / ".claude" / "rules" / _writ_filename(agent_name, "md")
        if path.exists():
            path.unlink()
            return True
        return False


# ---------------------------------------------------------------------------
# Kiro steering: .kiro/steering/writ-<name>.md (separate file, safe)
# ---------------------------------------------------------------------------

class KiroSteeringFormatter(BaseFormatter):
    """Write to .kiro/steering/writ-<name>.md -- auto-loaded by Kiro.

    Files with ``inclusion: always`` frontmatter are loaded into every
    Kiro interaction automatically.
    """

    format_name = "kiro_steering"

    def write(
        self,
        agent: InstructionConfig,
        composed_instructions: str,
        root: Path | None = None,
    ) -> Path:
        root = root or Path.cwd()
        path = root / ".kiro" / "steering" / _writ_filename(agent.name, "md")
        path.parent.mkdir(parents=True, exist_ok=True)

        fm_str = yaml_dumps({"inclusion": "always"}).strip()
        content = f"---\n{fm_str}\n---\n\n{composed_instructions}\n"
        path.write_text(content, encoding="utf-8")
        return path

    def clean(self, agent_name: str, root: Path | None = None) -> bool:
        root = root or Path.cwd()
        path = root / ".kiro" / "steering" / _writ_filename(agent_name, "md")
        if path.exists():
            path.unlink()
            return True
        return False


# ---------------------------------------------------------------------------
# A2A Agent Card JSON
# ---------------------------------------------------------------------------

class AgentCardFormatter(BaseFormatter):
    """A2A Agent Card JSON -- machine-readable capability metadata.

    Produces a valid A2A Agent Card JSON document from a writ agent config.
    Used for agent discovery by A2A-compatible systems.
    """

    format_name = "agent-card"

    def format_agent_card(self, agent: InstructionConfig) -> dict:
        """Build the A2A Agent Card dict from an InstructionConfig."""
        capabilities = []
        for tag in agent.tags:
            capabilities.append({
                "type": tag,
                "description": f"{tag.replace('-', ' ').replace('_', ' ').title()} development",
            })

        card: dict = {
            "name": agent.name,
            "description": agent.description or f"Agent: {agent.name}",
            "version": agent.version,
            "url": f"https://enwrit.com/agents/{agent.name}",
            "api": {
                "type": "a2a",
                "url": f"https://api.enwrit.com/agents/{agent.name}",
            },
            "capabilities": capabilities,
            "provider": {
                "organization": "enwrit",
                "url": "https://enwrit.com",
            },
        }
        return card

    def write(
        self,
        agent: InstructionConfig,
        composed_instructions: str,
        root: Path | None = None,
    ) -> Path:
        root = root or Path.cwd()
        path = root / ".well-known" / f"{agent.name}.agent-card.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        card = self.format_agent_card(agent)
        path.write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
        return path


# ---------------------------------------------------------------------------
# SKILL.md (Anthropic standard instruction format)
# ---------------------------------------------------------------------------

class SkillFormatter(BaseFormatter):
    """Anthropic SKILL.md format -- YAML frontmatter + markdown body."""

    format_name = "skill"

    def write(
        self,
        agent: InstructionConfig,
        composed_instructions: str,
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


# ---------------------------------------------------------------------------
# Cursor MCP config: .cursor/mcp.json
# ---------------------------------------------------------------------------

class CursorMcpFormatter(BaseFormatter):
    """Generate Cursor MCP config JSON for connecting to writ MCP server."""

    format_name = "cursor-mcp"

    def write(
        self,
        agent: InstructionConfig,
        composed_instructions: str,
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
        servers["writ"] = {
            "command": "writ",
            "args": ["mcp", "serve"],
        }
        existing["mcpServers"] = servers
        path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        return path


# ---------------------------------------------------------------------------
# Formatter registry
# ---------------------------------------------------------------------------

FORMATTERS: dict[str, type[BaseFormatter]] = {
    "cursor": CursorFormatter,
    "claude_rules": ClaudeRulesFormatter,
    "kiro_steering": KiroSteeringFormatter,
    "claude": ClaudeFormatter,
    "agents_md": AgentsMdFormatter,
    "copilot": CopilotFormatter,
    "windsurf": WindsurfFormatter,
    "codex": CodexFormatter,
    "kiro": KiroFormatter,
    "skill": SkillFormatter,
    "agent-card": AgentCardFormatter,
    "cursor-mcp": CursorMcpFormatter,
}

SAFE_FORMAT_NAMES: list[str] = ["cursor", "claude_rules", "kiro_steering"]

ALL_FORMAT_NAMES: list[str] = list(FORMATTERS.keys())


def get_formatter(format_name: str) -> BaseFormatter:
    """Get a formatter instance by name. Raises KeyError if unknown."""
    cls = FORMATTERS.get(format_name)
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
