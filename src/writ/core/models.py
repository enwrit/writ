"""Pydantic data models for writ agent configurations."""

from __future__ import annotations

from datetime import date

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
