"""Tests for the context composition engine."""

from writ.core import composer, store
from writ.core.models import CompositionConfig, InstructionConfig


class TestComposer:
    def test_basic_compose(self, initialized_project, sample_agent):
        store.save_instruction(sample_agent)
        result = composer.compose(sample_agent)
        assert "test-agent" in result
        assert "You are a test agent" in result

    def test_compose_with_project_context(self, initialized_project, sample_agent):
        store.save_project_context("# My Project\n\nUses Python and React.")
        store.save_instruction(sample_agent)
        result = composer.compose(sample_agent)
        assert "Project Context" in result
        assert "My Project" in result
        assert "test-agent" in result

    def test_compose_without_project_context(self, initialized_project, sample_agent):
        store.save_project_context("# Context")
        store.save_instruction(sample_agent)
        result = composer.compose(sample_agent, include_project=False)
        assert "Project Context" not in result

    def test_compose_with_inheritance(
        self, initialized_project, parent_agent, sample_agent_with_parents,
    ):
        store.save_instruction(parent_agent)
        store.save_instruction(sample_agent_with_parents)
        result = composer.compose(sample_agent_with_parents)
        assert "Inherited from parent-agent" in result
        assert "parent agent" in result
        assert "child agent" in result

    def test_compose_with_additional(self, initialized_project, sample_agent, parent_agent):
        store.save_instruction(sample_agent)
        store.save_instruction(parent_agent)
        result = composer.compose(sample_agent, additional=["parent-agent"])
        assert "Context from parent-agent" in result

    def test_compose_with_handoff(self, initialized_project, sample_agent):
        sample_agent.composition.receives_handoff_from = ["source-agent"]
        store.save_instruction(sample_agent)

        # Create a source agent and handoff
        source = InstructionConfig(name="source-agent", instructions="Source instructions")
        store.save_instruction(source)
        store.save_handoff("source-agent", "test-agent", "Handoff data here.")

        result = composer.compose(sample_agent)
        assert "Handoff from source-agent" in result
        assert "Handoff data here" in result

    def test_compose_empty_agent(self, initialized_project):
        agent = InstructionConfig(
            name="empty",
            instructions="",
            composition=CompositionConfig(project_context=False),
        )
        store.save_instruction(agent)
        result = composer.compose(agent)
        assert result == ""

    def test_layers_separated(self, initialized_project, sample_agent, parent_agent):
        store.save_project_context("# Project")
        store.save_instruction(parent_agent)
        sample_agent.composition.inherits_from = ["parent-agent"]
        store.save_instruction(sample_agent)
        result = composer.compose(sample_agent)
        assert "---" in result  # Layers separated by ---
