"""Tests for the multi-format formatter."""

from pathlib import Path

from writ.core.formatter import (
    AgentsMdFormatter,
    ClaudeFormatter,
    CopilotFormatter,
    CursorFormatter,
    WindsurfFormatter,
    get_formatter,
    write_agent,
)
from writ.core.models import CursorOverrides, FormatOverrides, InstructionConfig


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


class TestCopilotFormatter:
    def test_writes_copilot_file(self, tmp_project: Path, sample_agent: InstructionConfig):
        fmt = CopilotFormatter()
        path = fmt.write(sample_agent, "Copilot instructions", root=tmp_project)
        assert path.name == "copilot-instructions.md"
        assert ".github" in str(path)


class TestWindsurfFormatter:
    def test_writes_windsurfrules(self, tmp_project: Path, sample_agent: InstructionConfig):
        fmt = WindsurfFormatter()
        path = fmt.write(sample_agent, "Windsurf instructions", root=tmp_project)
        assert path.name == ".windsurfrules"


class TestFormatterRegistry:
    def test_get_known_formatter(self):
        fmt = get_formatter("cursor")
        assert isinstance(fmt, CursorFormatter)

    def test_get_unknown_raises(self):
        import pytest
        with pytest.raises(KeyError, match="Unknown format"):
            get_formatter("nonexistent")

    def test_write_agent_multiple_formats(self, tmp_project: Path, sample_agent: InstructionConfig):
        paths = write_agent(sample_agent, "Instructions", ["cursor", "agents_md"], root=tmp_project)
        assert len(paths) == 2


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
