"""Tests for core data models."""

from datetime import date

from writ.core.models import (
    InstructionConfig,
    CompositionConfig,
    LintResult,
    ProjectConfig,
)


class TestInstructionConfig:
    def test_default_values(self):
        agent = InstructionConfig(name="test", instructions="Do something")
        assert agent.name == "test"
        assert agent.description == ""
        assert agent.version == "1.0.0"
        assert agent.author is None
        assert agent.tags == []
        assert agent.created == date.today()
        assert agent.composition.project_context is True
        assert agent.composition.inherits_from == []

    def test_full_config(self):
        agent = InstructionConfig(
            name="reviewer",
            description="Code reviewer",
            version="2.0.0",
            author="testuser",
            tags=["review", "typescript"],
            instructions="You are a reviewer.",
            composition=CompositionConfig(
                inherits_from=["architect"],
                receives_handoff_from=["implementer"],
                project_context=True,
            ),
        )
        assert agent.name == "reviewer"
        assert agent.composition.inherits_from == ["architect"]
        assert agent.composition.receives_handoff_from == ["implementer"]

    def test_serialization_roundtrip(self):
        agent = InstructionConfig(name="test", instructions="Hello")
        data = agent.model_dump()
        restored = InstructionConfig(**data)
        assert restored.name == agent.name
        assert restored.instructions == agent.instructions


class TestProjectConfig:
    def test_defaults(self):
        config = ProjectConfig()
        assert config.formats == ["agents_md"]
        assert config.default_format == "agents_md"
        assert config.auto_export is True


class TestLintResult:
    def test_creation(self):
        result = LintResult(level="warning", rule="test-rule", message="Test message")
        assert result.level == "warning"
        assert result.rule == "test-rule"
