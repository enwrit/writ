"""Tests for the .writ/ store operations."""

from pathlib import Path

from writ.core import store
from writ.core.models import AgentConfig, ProjectConfig


class TestProjectStore:
    def test_init_creates_directories(self, tmp_project: Path):
        root = store.init_project_store()
        assert root.is_dir()
        assert (root / "agents").is_dir()
        assert (root / "handoffs").is_dir()
        assert (root / "memory").is_dir()

    def test_is_initialized(self, tmp_project: Path):
        assert not store.is_initialized()
        store.init_project_store()
        assert store.is_initialized()

    def test_save_and_load_config(self, initialized_project: Path):
        config = ProjectConfig(formats=["cursor", "claude"], default_format="cursor")
        store.save_config(config)
        loaded = store.load_config()
        assert loaded.formats == ["cursor", "claude"]
        assert loaded.default_format == "cursor"

    def test_save_and_load_agent(self, initialized_project: Path, sample_agent: AgentConfig):
        store.save_agent(sample_agent)
        loaded = store.load_agent("test-agent")
        assert loaded is not None
        assert loaded.name == "test-agent"
        assert loaded.description == "A test agent"
        assert loaded.instructions == "You are a test agent. Follow best practices."

    def test_load_nonexistent_agent(self, initialized_project: Path):
        assert store.load_agent("nonexistent") is None

    def test_list_agents(self, initialized_project: Path, sample_agent: AgentConfig):
        store.save_agent(sample_agent)
        agents = store.list_agents()
        assert len(agents) == 1
        assert agents[0].name == "test-agent"

    def test_remove_agent(self, initialized_project: Path, sample_agent: AgentConfig):
        store.save_agent(sample_agent)
        assert store.remove_agent("test-agent") is True
        assert store.load_agent("test-agent") is None

    def test_remove_nonexistent(self, initialized_project: Path):
        assert store.remove_agent("nonexistent") is False

    def test_project_context(self, initialized_project: Path):
        store.save_project_context("# Test Project\n\nSome context.")
        content = store.load_project_context()
        assert content is not None
        assert "Test Project" in content

    def test_handoff(self, initialized_project: Path):
        store.save_handoff("agent-a", "agent-b", "Handoff content here.")
        content = store.load_handoff("agent-a", "agent-b")
        assert content is not None
        assert "Handoff content" in content

    def test_handoff_nonexistent(self, initialized_project: Path):
        assert store.load_handoff("x", "y") is None


class TestGlobalStore:
    def test_save_and_load_library(self, tmp_global_writ: Path, sample_agent: AgentConfig):
        store.init_global_store()
        store.save_to_library(sample_agent)
        loaded = store.load_from_library("test-agent")
        assert loaded is not None
        assert loaded.name == "test-agent"

    def test_save_with_alias(self, tmp_global_writ: Path, sample_agent: AgentConfig):
        store.init_global_store()
        store.save_to_library(sample_agent, alias="my-agent")
        loaded = store.load_from_library("my-agent")
        assert loaded is not None

    def test_list_library(self, tmp_global_writ: Path, sample_agent: AgentConfig):
        store.init_global_store()
        store.save_to_library(sample_agent)
        agents = store.list_library()
        assert len(agents) == 1
