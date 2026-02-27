"""Tests for the agent linter."""

from writ.core import linter
from writ.core.models import CompositionConfig, InstructionConfig


class TestLinter:
    def test_good_agent_passes(self, initialized_project, sample_agent):
        results = linter.lint(sample_agent)
        # Should have no errors (may have info-level findings)
        errors = [r for r in results if r.level == "error"]
        assert len(errors) == 0

    def test_empty_instructions_warning(self, initialized_project):
        agent = InstructionConfig(name="empty", instructions="")
        results = linter.lint(agent)
        assert any(r.rule == "instructions-empty" for r in results)

    def test_very_long_instructions(self, initialized_project):
        agent = InstructionConfig(
            name="verbose",
            instructions=" ".join(["word"] * 2500),
        )
        results = linter.lint(agent)
        assert any(r.rule == "instructions-long" for r in results)

    def test_very_short_instructions(self, initialized_project):
        agent = InstructionConfig(name="short", instructions="Be helpful.")
        results = linter.lint(agent)
        assert any(r.rule == "instructions-short" for r in results)

    def test_missing_description(self, initialized_project):
        agent = InstructionConfig(name="nodesc", instructions="Do something useful.")
        results = linter.lint(agent)
        assert any(r.rule == "description-missing" for r in results)

    def test_missing_tags(self, initialized_project):
        agent = InstructionConfig(name="notags", instructions="Instructions here.")
        results = linter.lint(agent)
        assert any(r.rule == "tags-missing" for r in results)

    def test_bad_name_format(self, initialized_project):
        agent = InstructionConfig(name="My Agent!", instructions="Test")
        results = linter.lint(agent)
        assert any(r.rule == "name-format" for r in results)

    def test_contradiction_detection(self, initialized_project):
        agent = InstructionConfig(
            name="contradicted",
            description="Test",
            tags=["test"],
            instructions="Always use TypeScript.\nNever use TypeScript.",
        )
        results = linter.lint(agent)
        assert any(r.rule == "contradiction" for r in results)

    def test_missing_parent_warning(self, initialized_project):
        agent = InstructionConfig(
            name="orphan",
            instructions="Test",
            composition=CompositionConfig(inherits_from=["nonexistent"]),
        )
        results = linter.lint(agent)
        assert any(r.rule == "inherit-missing" for r in results)
