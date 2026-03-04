"""Pydantic data models for writ agent configurations and messaging."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class CompositionConfig(BaseModel):
    """Rules for how an agent's context is composed from multiple layers."""

    inherits_from: list[str] = Field(
        default_factory=list,
        description="Agent names whose instructions are prepended to this agent's context.",
    )
    receives_handoff_from: list[str] = Field(
        default_factory=list,
        description="Agent names that can hand off context to this agent.",
    )
    project_context: bool = Field(
        default=True,
        description="Whether to include auto-detected project context.",
    )


class CursorOverrides(BaseModel):
    """Cursor-specific format overrides."""

    description: str | None = None
    always_apply: bool = False
    globs: str | None = None


class FormatOverrides(BaseModel):
    """Per-format configuration overrides (optional)."""

    cursor: CursorOverrides | None = None
    claude: dict | None = None
    codex: dict | None = None
    copilot: dict | None = None
    windsurf: dict | None = None
    kiro: dict | None = None


class InstructionConfig(BaseModel):
    """The canonical instruction configuration model.

    Used for all content types: agents, rules, context, and more.
    Stored as YAML in .writ/{agents,rules,context}/<name>.yaml.
    """

    name: str = Field(description="Unique agent name (slug-safe).")
    description: str = Field(default="", description="Short description of the agent's role.")
    version: str = Field(default="1.0.0", description="Semantic version.")
    author: str | None = Field(default=None, description="Author (set when published).")
    tags: list[str] = Field(default_factory=list, description="Searchable tags.")
    task_type: str | None = Field(
        default=None,
        description="Content category for registry filtering (agent, rule, context, template).",
    )
    created: date = Field(default_factory=date.today)
    updated: date = Field(default_factory=date.today)
    instructions: str = Field(
        default="",
        description="The actual agent instructions (written to IDE files).",
    )
    source: str | None = Field(
        default=None,
        description="Where this instruction was installed from (e.g. enwrit.com/git-commit@1.0.0).",
    )
    includes: list[str] = Field(
        default_factory=list,
        description="For templates: list of instruction names to install together.",
    )
    composition: CompositionConfig = Field(default_factory=CompositionConfig)
    format_overrides: FormatOverrides = Field(default_factory=FormatOverrides)


class ProjectConfig(BaseModel):
    """Project-level writ configuration stored in .writ/config.yaml."""

    formats: list[str] = Field(
        default_factory=lambda: ["agents_md"],
        description="Active output formats (e.g. cursor, claude, agents_md, copilot, windsurf).",
    )
    default_format: str = Field(
        default="agents_md",
        description="The default format used when none is specified.",
    )
    auto_export: bool = Field(
        default=True,
        description="Automatically write to IDE files on 'writ use'.",
    )


class GlobalConfig(BaseModel):
    """Global writ configuration stored in ~/.writ/config.yaml."""

    default_formats: list[str] = Field(
        default_factory=lambda: ["agents_md"],
        description="Default output formats for new projects.",
    )
    registry_url: str = Field(
        default="https://api.enwrit.com",
        description="Registry API base URL.",
    )
    auth_token: str | None = Field(
        default=None,
        description="API key for enwrit.com authentication.",
    )


class LintResult(BaseModel):
    """A single lint finding."""

    level: str = Field(description="Severity: error, warning, info.")
    rule: str = Field(default="", description="Rule identifier.")
    message: str = Field(description="Human-readable description.")


# ---------------------------------------------------------------------------
# Agent-to-agent communication models (V3)
# ---------------------------------------------------------------------------

class ConversationStatus(StrEnum):
    """Conversation lifecycle states, aligned with A2A TaskState."""

    ACTIVE = "active"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class AutoRespondTier(StrEnum):
    """How autonomously a peer's messages are handled.

    off             -- No auto-invocation; user handles manually.
    read_only       -- Agent can read/analyze but not write (--mode ask).
    approval        -- Can use MCP tools; elevated actions require human approval.
    full            -- Agent can read + respond via MCP tools (no shell).
    dangerous_full  -- Unrestricted shell access (--force). Opt-in only.
    """

    OFF = "off"
    READ_ONLY = "read_only"
    APPROVAL = "approval"
    FULL = "full"
    DANGEROUS_FULL = "dangerous_full"


class Participant(BaseModel):
    """A participant in a conversation."""

    agent: str = Field(description="Agent name (e.g. 'coding-agent').")
    repo: str = Field(description="Repository identifier (e.g. 'writ-cli').")
    device: str = Field(default="", description="Device identifier for cross-device.")


class Message(BaseModel):
    """A single message within a conversation."""

    id: str = Field(description="Sequential message ID (e.g. 'msg-001').")
    author_agent: str = Field(description="Name of the sending agent.")
    author_repo: str = Field(description="Repository the agent belongs to.")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content: str = Field(default="", description="Markdown message body.")
    attachments: list[str] = Field(
        default_factory=list,
        description="Embedded file content blocks (already rendered as <attached> tags).",
    )


class Conversation(BaseModel):
    """A two-party conversation between agents in different repos."""

    format_version: int = Field(default=1)
    id: str = Field(description="Unique conversation ID (e.g. 'conv-abc123').")
    participants: list[Participant] = Field(default_factory=list)
    goal: str = Field(default="", description="What this conversation aims to achieve.")
    status: ConversationStatus = Field(default=ConversationStatus.ACTIVE)
    created: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(UTC))
    messages: list[Message] = Field(default_factory=list)
    turn_count: int = Field(default=0, description="Number of messages exchanged.")


class PeerConfig(BaseModel):
    """Configuration for a connected peer repository."""

    name: str = Field(description="Short name for this peer (e.g. 'research-repo').")
    path: str | None = Field(default=None, description="Local filesystem path.")
    remote: str | None = Field(default=None, description="Remote API URL.")
    transport: str = Field(default="local", description="Transport: local or remote.")
    auto_respond: AutoRespondTier = Field(default=AutoRespondTier.OFF)
    max_turns: int = Field(default=10, description="Safety limit per conversation.")
    allowed_context: list[str] = Field(
        default_factory=lambda: ["writ://instructions/*"],
        description="Glob patterns for what context can be shared.",
    )


class PeersManifest(BaseModel):
    """The .writ/peers.yaml file."""

    peers: dict[str, PeerConfig] = Field(default_factory=dict)
