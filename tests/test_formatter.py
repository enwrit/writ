"""Tests for the multi-format formatter."""

from pathlib import Path

from writ.core.formatter import (
    ALL_FORMAT_NAMES,
    IDE_PATHS,
    LEGACY_FORMAT_NAMES,
    SAFE_FORMAT_NAMES,
    AgentsMdFormatter,
    ClaudeFormatter,
    ClaudeRulesFormatter,
    CopilotLegacyFormatter,
    CursorFormatter,
    IDEFormatter,
    KiroSteeringFormatter,
    SkillFormatter,
    WindsurfLegacyFormatter,
    get_formatter,
    resolve_content_category,
    write_agent,
)
from writ.core.models import CursorOverrides, FormatOverrides, InstructionConfig

# ---------------------------------------------------------------------------
# IDE_PATHS config + content-category routing
# ---------------------------------------------------------------------------


class TestIDEPaths:
    def test_all_safe_formats_in_ide_paths(self):
        for fmt in SAFE_FORMAT_NAMES:
            assert fmt in IDE_PATHS, f"{fmt} missing from IDE_PATHS"

    def test_cursor_config(self):
        c = IDE_PATHS["cursor"]
        assert c.name == "Cursor"
        assert c.detect == ".cursor"
        assert c.rules.directory == ".cursor/rules"
        assert c.rules.extension == "mdc"
        assert c.skills.directory == ".cursor/skills/writ"
        assert c.skills.namespaced is True
        assert c.agents.directory == ".cursor/agents"
        assert c.mcp == (".cursor/mcp.json", "mcpServers")

    def test_claude_config(self):
        c = IDE_PATHS["claude_rules"]
        assert c.detect == ".claude"
        assert c.rules.directory == ".claude/rules"
        assert c.agents.directory == ".claude/agents"

    def test_copilot_config(self):
        c = IDE_PATHS["copilot"]
        assert c.detect == ".github"
        assert c.rules.extension == "instructions.md"
        assert c.skills.extension == "md"
        assert c.agents.directory == ".github/agents"

    def test_windsurf_config(self):
        c = IDE_PATHS["windsurf"]
        assert c.detect == ".windsurf"
        assert c.rules.directory == ".windsurf/rules"
        assert c.agents.directory == ".windsurf/agents"

    def test_cline_config(self):
        c = IDE_PATHS["cline"]
        assert c.detect == ".clinerules"
        assert c.rules.directory == ".clinerules"
        assert c.agents.directory == ".cline/agents"

    def test_roo_config(self):
        c = IDE_PATHS["roo"]
        assert c.detect == ".roo"
        assert c.rules.directory == ".roo/rules"
        assert c.agents.directory == ".roo/agents"

    def test_amazonq_config(self):
        c = IDE_PATHS["amazonq"]
        assert c.detect == ".amazonq"
        assert c.rules.directory == ".amazonq/rules"
        assert c.agents.directory == ".amazonq/agents"

    def test_gemini_config(self):
        c = IDE_PATHS["gemini"]
        assert c.name == "Gemini CLI"
        assert c.detect == ".gemini"
        assert c.rules.directory == ".gemini/rules"
        assert c.skills.directory == ".gemini/skills/writ"
        assert c.skills.namespaced is True
        assert c.agents.directory == ".gemini/agents"

    def test_codex_config(self):
        c = IDE_PATHS["codex"]
        assert c.name == "Codex"
        assert c.detect == ".codex"
        assert c.rules.directory == ".codex/rules"
        assert c.agents.directory == ".codex/agents"

    def test_opencode_config(self):
        c = IDE_PATHS["opencode"]
        assert c.name == "OpenCode"
        assert c.detect == ".opencode"
        assert c.rules.directory == ".opencode/rules"
        assert c.agents.directory == ".opencode/agents"


class TestContentCategoryRouting:
    def test_agent_routes_to_agents(self):
        assert resolve_content_category("agent") == "agents"

    def test_rule_routes_to_rules(self):
        assert resolve_content_category("rule") == "rules"

    def test_context_routes_to_rules(self):
        assert resolve_content_category("context") == "rules"

    def test_skill_routes_to_skills(self):
        assert resolve_content_category("skill") == "skills"

    def test_program_routes_to_rules(self):
        assert resolve_content_category("program") == "rules"

    def test_none_defaults_to_rules(self):
        assert resolve_content_category(None) == "rules"

    def test_unknown_defaults_to_rules(self):
        assert resolve_content_category("mystery") == "rules"


# ---------------------------------------------------------------------------
# IDEFormatter -- config-driven (routes by task_type)
# ---------------------------------------------------------------------------


class TestIDEFormatterRouting:
    """Test that IDEFormatter routes instructions to the correct directory."""

    def test_rule_goes_to_rules_dir(self, tmp_project: Path):
        agent = InstructionConfig(name="my-rule", task_type="rule", instructions="x")
        fmt = IDEFormatter("cursor")
        path = fmt.write(agent, "Test", root=tmp_project)
        assert ".cursor/rules" in str(path).replace("\\", "/")
        assert path.name == "writ-my-rule.mdc"

    def test_agent_goes_to_agents_dir(self, tmp_project: Path):
        agent = InstructionConfig(name="my-agent", task_type="agent", instructions="x")
        fmt = IDEFormatter("cursor")
        path = fmt.write(agent, "Test", root=tmp_project)
        assert ".cursor/agents" in str(path).replace("\\", "/")
        assert path.name == "writ-my-agent.mdc"

    def test_skill_goes_to_skills_dir(self, tmp_project: Path):
        agent = InstructionConfig(name="my-skill", task_type="skill", instructions="x")
        fmt = IDEFormatter("cursor")
        path = fmt.write(agent, "Test", root=tmp_project)
        assert ".cursor/skills/writ" in str(path).replace("\\", "/")
        assert path.name == "my-skill.mdc"  # namespaced: no writ- prefix

    def test_none_task_type_goes_to_rules(self, tmp_project: Path):
        agent = InstructionConfig(name="default", instructions="x")
        fmt = IDEFormatter("cursor")
        path = fmt.write(agent, "Test", root=tmp_project)
        assert ".cursor/rules" in str(path).replace("\\", "/")

    def test_copilot_rule_uses_instructions_md_ext(self, tmp_project: Path):
        agent = InstructionConfig(name="my-rule", task_type="rule", instructions="x")
        fmt = IDEFormatter("copilot")
        path = fmt.write(agent, "Test", root=tmp_project)
        assert path.name == "writ-my-rule.instructions.md"
        assert ".github/instructions" in str(path).replace("\\", "/")

    def test_copilot_agent_goes_to_agents(self, tmp_project: Path):
        agent = InstructionConfig(name="reviewer", task_type="agent", instructions="x")
        fmt = IDEFormatter("copilot")
        path = fmt.write(agent, "Test", root=tmp_project)
        assert ".github/agents" in str(path).replace("\\", "/")
        assert path.name == "writ-reviewer.md"

    def test_windsurf_rule_safe_path(self, tmp_project: Path):
        agent = InstructionConfig(name="my-rule", task_type="rule", instructions="x")
        fmt = IDEFormatter("windsurf")
        path = fmt.write(agent, "Test", root=tmp_project)
        assert ".windsurf/rules" in str(path).replace("\\", "/")
        assert path.name == "writ-my-rule.md"

    def test_cline_rule_to_clinerules(self, tmp_project: Path):
        agent = InstructionConfig(name="my-rule", task_type="rule", instructions="x")
        fmt = IDEFormatter("cline")
        path = fmt.write(agent, "Test", root=tmp_project)
        assert ".clinerules" in str(path).replace("\\", "/")

    def test_cline_agent_to_agents(self, tmp_project: Path):
        agent = InstructionConfig(name="my-agent", task_type="agent", instructions="x")
        fmt = IDEFormatter("cline")
        path = fmt.write(agent, "Test", root=tmp_project)
        assert ".cline/agents" in str(path).replace("\\", "/")

    def test_roo_agent_to_agents(self, tmp_project: Path):
        agent = InstructionConfig(name="reviewer", task_type="agent", instructions="x")
        fmt = IDEFormatter("roo")
        path = fmt.write(agent, "Test", root=tmp_project)
        assert ".roo/agents" in str(path).replace("\\", "/")

    def test_amazonq_agent_to_agents(self, tmp_project: Path):
        agent = InstructionConfig(name="reviewer", task_type="agent", instructions="x")
        fmt = IDEFormatter("amazonq")
        path = fmt.write(agent, "Test", root=tmp_project)
        assert ".amazonq/agents" in str(path).replace("\\", "/")

    def test_gemini_agent_to_agents(self, tmp_project: Path):
        agent = InstructionConfig(name="reviewer", task_type="agent", instructions="x")
        fmt = IDEFormatter("gemini")
        path = fmt.write(agent, "Test", root=tmp_project)
        assert ".gemini/agents" in str(path).replace("\\", "/")
        assert path.name == "writ-reviewer.md"

    def test_codex_safe_agent_to_agents(self, tmp_project: Path):
        agent = InstructionConfig(name="reviewer", task_type="agent", instructions="x")
        fmt = IDEFormatter("codex")
        path = fmt.write(agent, "Test", root=tmp_project)
        assert ".codex/agents" in str(path).replace("\\", "/")
        assert path.name == "writ-reviewer.md"

    def test_opencode_agent_to_agents(self, tmp_project: Path):
        agent = InstructionConfig(name="reviewer", task_type="agent", instructions="x")
        fmt = IDEFormatter("opencode")
        path = fmt.write(agent, "Test", root=tmp_project)
        assert ".opencode/agents" in str(path).replace("\\", "/")
        assert path.name == "writ-reviewer.md"


class TestIDEFormatterClean:
    def test_clean_from_rules(self, tmp_project: Path):
        agent = InstructionConfig(name="test-agent", task_type="rule", instructions="x")
        fmt = IDEFormatter("cursor")
        fmt.write(agent, "Test", root=tmp_project)
        assert fmt.clean("test-agent", root=tmp_project) is True
        assert not (tmp_project / ".cursor" / "rules" / "writ-test-agent.mdc").exists()

    def test_clean_from_agents(self, tmp_project: Path):
        agent = InstructionConfig(name="test-agent", task_type="agent", instructions="x")
        fmt = IDEFormatter("cursor")
        fmt.write(agent, "Test", root=tmp_project)
        assert fmt.clean("test-agent", root=tmp_project) is True
        assert not (tmp_project / ".cursor" / "agents" / "writ-test-agent.mdc").exists()

    def test_clean_nonexistent(self, tmp_project: Path):
        fmt = IDEFormatter("cursor")
        assert fmt.clean("nonexistent", root=tmp_project) is False


# ---------------------------------------------------------------------------
# Backward-compatible named formatters
# ---------------------------------------------------------------------------


class TestCursorFormatter:
    def test_writes_mdc_file(self, tmp_project: Path, sample_agent: InstructionConfig):
        fmt = CursorFormatter()
        path = fmt.write(sample_agent, "Test instructions", root=tmp_project)
        assert path.exists()
        assert path.name == "writ-test-agent.mdc"
        content = path.read_text()
        assert "---" in content
        assert "Test instructions" in content

    def test_includes_frontmatter(self, tmp_project: Path, sample_agent: InstructionConfig):
        fmt = CursorFormatter()
        path = fmt.write(sample_agent, "Instructions", root=tmp_project)
        content = path.read_text()
        assert "description:" in content
        assert "alwaysApply:" in content

    def test_cursor_overrides(self, tmp_project: Path):
        agent = InstructionConfig(
            name="custom",
            instructions="Custom",
            format_overrides=FormatOverrides(
                cursor=CursorOverrides(description="Custom desc", always_apply=True),
            ),
        )
        fmt = CursorFormatter()
        path = fmt.write(agent, "Instructions", root=tmp_project)
        content = path.read_text()
        assert "Custom desc" in content
        assert "alwaysApply: true" in content

    def test_clean(self, tmp_project: Path, sample_agent: InstructionConfig):
        fmt = CursorFormatter()
        fmt.write(sample_agent, "Test", root=tmp_project)
        assert fmt.clean("test-agent", root=tmp_project) is True
        assert not (tmp_project / ".cursor" / "rules" / "writ-test-agent.mdc").exists()

    def test_is_ide_formatter(self):
        fmt = CursorFormatter()
        assert isinstance(fmt, IDEFormatter)


class TestClaudeFormatter:
    def test_writes_claude_md(self, tmp_project: Path, sample_agent: InstructionConfig):
        fmt = ClaudeFormatter()
        path = fmt.write(sample_agent, "Claude instructions", root=tmp_project)
        assert path.name == "CLAUDE.md"
        content = path.read_text()
        assert "Agent: test-agent" in content
        assert "Claude instructions" in content

    def test_updates_existing(self, tmp_project: Path, sample_agent: InstructionConfig):
        (tmp_project / "CLAUDE.md").write_text("# Existing content\n\nSome rules.")
        fmt = ClaudeFormatter()
        fmt.write(sample_agent, "New instructions", root=tmp_project)
        content = (tmp_project / "CLAUDE.md").read_text()
        assert "Existing content" in content
        assert "New instructions" in content


class TestAgentsMdFormatter:
    def test_writes_agents_md(self, tmp_project: Path, sample_agent: InstructionConfig):
        fmt = AgentsMdFormatter()
        path = fmt.write(sample_agent, "Agent instructions", root=tmp_project)
        assert path.name == "AGENTS.md"
        content = path.read_text()
        assert "test-agent" in content


class TestCopilotLegacyFormatter:
    def test_writes_copilot_file(self, tmp_project: Path, sample_agent: InstructionConfig):
        fmt = CopilotLegacyFormatter()
        path = fmt.write(sample_agent, "Copilot instructions", root=tmp_project)
        assert path.name == "copilot-instructions.md"
        assert ".github" in str(path)


class TestWindsurfLegacyFormatter:
    def test_writes_windsurfrules(self, tmp_project: Path, sample_agent: InstructionConfig):
        fmt = WindsurfLegacyFormatter()
        path = fmt.write(sample_agent, "Windsurf instructions", root=tmp_project)
        assert path.name == ".windsurfrules"


class TestSkillFormatter:
    def test_writes_skill_md(self, tmp_project: Path, sample_agent: InstructionConfig):
        fmt = SkillFormatter()
        path = fmt.write(sample_agent, "You are a code reviewer...", root=tmp_project)
        assert path.name == "SKILL.md"
        assert path.parent == tmp_project
        content = path.read_text()
        assert "---" in content
        assert "name: test-agent" in content
        assert "description:" in content
        assert "version: 1.0.0" in content
        assert "tags:" in content
        assert "# test-agent" in content
        assert "You are a code reviewer..." in content

    def test_skill_clean(self, tmp_project: Path, sample_agent: InstructionConfig):
        fmt = SkillFormatter()
        fmt.write(sample_agent, "Instructions", root=tmp_project)
        assert (tmp_project / "SKILL.md").exists()
        assert fmt.clean("test-agent", root=tmp_project) is True
        assert not (tmp_project / "SKILL.md").exists()

    def test_in_formatter_registry(self):
        fmt = get_formatter("skill")
        assert isinstance(fmt, SkillFormatter)


class TestFormatterRegistry:
    def test_get_cursor_returns_ide_formatter(self):
        fmt = get_formatter("cursor")
        assert isinstance(fmt, IDEFormatter)

    def test_get_unknown_raises(self):
        import pytest
        with pytest.raises(KeyError, match="Unknown format"):
            get_formatter("nonexistent")

    def test_write_agent_multiple_formats(self, tmp_project: Path, sample_agent: InstructionConfig):
        paths = write_agent(sample_agent, "Instructions", ["cursor", "agents_md"], root=tmp_project)
        assert len(paths) == 2

    def test_all_safe_formats_are_gettable(self):
        for fmt in SAFE_FORMAT_NAMES:
            f = get_formatter(fmt)
            assert isinstance(f, IDEFormatter)

    def test_legacy_formats_are_gettable(self):
        for fmt in LEGACY_FORMAT_NAMES:
            f = get_formatter(fmt)
            assert f is not None

    def test_copilot_safe_format(self):
        fmt = get_formatter("copilot")
        assert isinstance(fmt, IDEFormatter)

    def test_copilot_legacy_format(self):
        fmt = get_formatter("copilot_legacy")
        assert isinstance(fmt, CopilotLegacyFormatter)

    def test_windsurf_safe_format(self):
        fmt = get_formatter("windsurf")
        assert isinstance(fmt, IDEFormatter)

    def test_windsurf_legacy_format(self):
        fmt = get_formatter("windsurf_legacy")
        assert isinstance(fmt, WindsurfLegacyFormatter)

    def test_new_formats_in_registry(self):
        for fmt in ("cline", "roo", "amazonq"):
            f = get_formatter(fmt)
            assert isinstance(f, IDEFormatter)


class TestAgentCardFormatter:
    def test_produces_valid_json(self, tmp_project: Path, sample_agent: InstructionConfig):
        import json

        from writ.core.formatter import AgentCardFormatter

        fmt = AgentCardFormatter()
        path = fmt.write(sample_agent, "Instructions", root=tmp_project)
        assert path.exists()
        card = json.loads(path.read_text())
        assert card["name"] == "test-agent"
        assert card["version"] == "1.0.0"

    def test_maps_tags_to_capabilities(self):
        from writ.core.formatter import AgentCardFormatter

        agent = InstructionConfig(
            name="reviewer",
            description="Code reviewer",
            tags=["python", "code-review"],
        )
        fmt = AgentCardFormatter()
        card = fmt.format_agent_card(agent)
        assert len(card["capabilities"]) == 2
        assert card["capabilities"][0]["type"] == "python"
        assert "description" in card["capabilities"][0]

    def test_includes_api_url(self):
        from writ.core.formatter import AgentCardFormatter

        agent = InstructionConfig(name="test", description="Test")
        fmt = AgentCardFormatter()
        card = fmt.format_agent_card(agent)
        assert card["api"]["url"] == "https://api.enwrit.com/agents/test"
        assert card["api"]["type"] == "a2a"

    def test_in_formatter_registry(self):
        from writ.core.formatter import AgentCardFormatter

        fmt = get_formatter("agent-card")
        assert isinstance(fmt, AgentCardFormatter)


class TestClaudeRulesFormatter:
    def test_writes_separate_file(self, tmp_project: Path, sample_agent: InstructionConfig):
        (tmp_project / ".claude" / "rules").mkdir(parents=True)
        fmt = ClaudeRulesFormatter()
        path = fmt.write(sample_agent, "Claude rules content", root=tmp_project)
        assert path.exists()
        assert path.name == "writ-test-agent.md"
        assert ".claude" in str(path)
        assert "rules" in str(path)
        content = path.read_text()
        assert "Claude rules content" in content

    def test_no_frontmatter(self, tmp_project: Path, sample_agent: InstructionConfig):
        fmt = ClaudeRulesFormatter()
        path = fmt.write(sample_agent, "Instructions", root=tmp_project)
        content = path.read_text()
        assert "---" not in content

    def test_clean(self, tmp_project: Path, sample_agent: InstructionConfig):
        fmt = ClaudeRulesFormatter()
        fmt.write(sample_agent, "Test", root=tmp_project)
        assert fmt.clean("test-agent", root=tmp_project) is True
        assert not (tmp_project / ".claude" / "rules" / "writ-test-agent.md").exists()

    def test_clean_nonexistent(self, tmp_project: Path):
        fmt = ClaudeRulesFormatter()
        assert fmt.clean("nonexistent", root=tmp_project) is False

    def test_in_registry(self):
        fmt = get_formatter("claude_rules")
        assert isinstance(fmt, IDEFormatter)


class TestKiroSteeringFormatter:
    def test_writes_separate_file(self, tmp_project: Path, sample_agent: InstructionConfig):
        (tmp_project / ".kiro" / "steering").mkdir(parents=True)
        fmt = KiroSteeringFormatter()
        path = fmt.write(sample_agent, "Kiro steering content", root=tmp_project)
        assert path.exists()
        assert path.name == "writ-test-agent.md"
        assert ".kiro" in str(path)
        assert "steering" in str(path)
        content = path.read_text()
        assert "Kiro steering content" in content

    def test_includes_inclusion_frontmatter(
        self, tmp_project: Path, sample_agent: InstructionConfig,
    ):
        fmt = KiroSteeringFormatter()
        path = fmt.write(sample_agent, "Instructions", root=tmp_project)
        content = path.read_text()
        assert "---" in content
        assert "inclusion: always" in content

    def test_clean(self, tmp_project: Path, sample_agent: InstructionConfig):
        fmt = KiroSteeringFormatter()
        fmt.write(sample_agent, "Test", root=tmp_project)
        assert fmt.clean("test-agent", root=tmp_project) is True
        assert not (tmp_project / ".kiro" / "steering" / "writ-test-agent.md").exists()

    def test_clean_nonexistent(self, tmp_project: Path):
        fmt = KiroSteeringFormatter()
        assert fmt.clean("nonexistent", root=tmp_project) is False

    def test_in_registry(self):
        fmt = get_formatter("kiro_steering")
        assert isinstance(fmt, IDEFormatter)


class TestSafeFormatNames:
    def test_includes_all_ide_paths(self):
        for key in IDE_PATHS:
            assert key in SAFE_FORMAT_NAMES

    def test_includes_new_formats(self):
        assert "copilot" in SAFE_FORMAT_NAMES
        assert "windsurf" in SAFE_FORMAT_NAMES
        assert "cline" in SAFE_FORMAT_NAMES
        assert "roo" in SAFE_FORMAT_NAMES
        assert "amazonq" in SAFE_FORMAT_NAMES

    def test_excludes_legacy(self):
        assert "claude" not in SAFE_FORMAT_NAMES
        assert "agents_md" not in SAFE_FORMAT_NAMES
        assert "copilot_legacy" not in SAFE_FORMAT_NAMES
        assert "windsurf_legacy" not in SAFE_FORMAT_NAMES

    def test_all_format_names_complete(self):
        combined = set(SAFE_FORMAT_NAMES) | set(LEGACY_FORMAT_NAMES)
        assert combined == set(ALL_FORMAT_NAMES)
