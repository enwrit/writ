"""Tests for the .writ/ store operations."""

from pathlib import Path

from writ.core import store
from writ.core.models import InstructionConfig, ProjectConfig


class TestProjectStore:
    def test_init_creates_directories(self, tmp_project: Path):
        root = store.init_project_store()
        assert root.is_dir()
        assert (root / "agents").is_dir()
        assert (root / "rules").is_dir()
        assert (root / "context").is_dir()
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

    def test_save_and_load_agent(self, initialized_project: Path, sample_agent: InstructionConfig):
        store.save_instruction(sample_agent)
        loaded = store.load_instruction("test-agent")
        assert loaded is not None
        assert loaded.name == "test-agent"
        assert loaded.description == "A test agent"
        assert loaded.instructions == "You are a test agent. Follow best practices."

    def test_load_nonexistent_agent(self, initialized_project: Path):
        assert store.load_instruction("nonexistent") is None

    def test_list_agents(self, initialized_project: Path, sample_agent: InstructionConfig):
        store.save_instruction(sample_agent)
        items = store.list_instructions()
        assert len(items) == 1
        assert items[0].name == "test-agent"

    def test_remove_agent(self, initialized_project: Path, sample_agent: InstructionConfig):
        store.save_instruction(sample_agent)
        assert store.remove_instruction("test-agent") is True
        assert store.load_instruction("test-agent") is None

    def test_remove_nonexistent(self, initialized_project: Path):
        assert store.remove_instruction("nonexistent") is False

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


class TestDirectoryRouting:
    """Verify that task_type routes instructions to the correct subdirectory."""

    def test_agent_routes_to_agents_dir(self, initialized_project: Path):
        cfg = InstructionConfig(name="my-agent", task_type="agent", instructions="Do things.")
        path = store.save_instruction(cfg)
        assert "agents" in path.parts
        assert path.exists()

    def test_rule_routes_to_rules_dir(self, initialized_project: Path):
        cfg = InstructionConfig(name="my-rule", task_type="rule", instructions="Follow this.")
        path = store.save_instruction(cfg)
        assert "rules" in path.parts
        assert path.exists()

    def test_context_routes_to_context_dir(self, initialized_project: Path):
        cfg = InstructionConfig(name="my-ctx", task_type="context", instructions="Context info.")
        path = store.save_instruction(cfg)
        assert "context" in path.parts
        assert path.exists()

    def test_none_task_type_defaults_to_agents(self, initialized_project: Path):
        cfg = InstructionConfig(name="legacy", instructions="No task type set.")
        path = store.save_instruction(cfg)
        assert "agents" in path.parts

    def test_load_finds_rule_by_name(self, initialized_project: Path):
        cfg = InstructionConfig(name="coding-standards", task_type="rule", instructions="Standards.")
        store.save_instruction(cfg)
        loaded = store.load_instruction("coding-standards")
        assert loaded is not None
        assert loaded.task_type == "rule"

    def test_load_finds_context_by_name(self, initialized_project: Path):
        cfg = InstructionConfig(name="api-ctx", task_type="context", instructions="API context.")
        store.save_instruction(cfg)
        loaded = store.load_instruction("api-ctx")
        assert loaded is not None
        assert loaded.task_type == "context"

    def test_list_gathers_from_all_dirs(self, initialized_project: Path):
        store.save_instruction(InstructionConfig(name="a1", task_type="agent", instructions="A"))
        store.save_instruction(InstructionConfig(name="r1", task_type="rule", instructions="R"))
        store.save_instruction(InstructionConfig(name="c1", task_type="context", instructions="C"))
        items = store.list_instructions()
        names = {i.name for i in items}
        assert names == {"a1", "r1", "c1"}

    def test_remove_finds_and_deletes_rule(self, initialized_project: Path):
        cfg = InstructionConfig(name="old-rule", task_type="rule", instructions="Remove me.")
        store.save_instruction(cfg)
        assert store.remove_instruction("old-rule") is True
        assert store.load_instruction("old-rule") is None

    def test_save_moves_stale_copy_from_agents_to_rules(self, initialized_project: Path):
        """Simulates upgrading from old layout where everything lived in agents/."""
        old = InstructionConfig(name="coding-standards", instructions="Old copy.")
        store.save_instruction(old)  # task_type=None -> agents/
        agents_path = store.project_writ_dir() / "agents" / "coding-standards.yaml"
        assert agents_path.exists()

        updated = InstructionConfig(name="coding-standards", task_type="rule", instructions="New.")
        new_path = store.save_instruction(updated)
        assert "rules" in new_path.parts
        assert not agents_path.exists(), "stale copy in agents/ should be removed"

    def test_init_force_clears_content(self, tmp_project: Path):
        root = store.init_project_store()
        store.save_instruction(InstructionConfig(name="a1", instructions="Keep?"))
        assert (root / "agents" / "a1.yaml").exists()
        store.init_project_store(clean=True)
        assert not (root / "agents" / "a1.yaml").exists()
        assert root.is_dir()


class TestGlobalStore:
    def test_init_creates_content_dirs(self, tmp_global_writ: Path):
        root = store.init_global_store()
        assert (root / "agents").is_dir()
        assert (root / "rules").is_dir()
        assert (root / "context").is_dir()

    def test_save_and_load_library(self, tmp_global_writ: Path, sample_agent: InstructionConfig):
        store.init_global_store()
        store.save_to_library(sample_agent)
        loaded = store.load_from_library("test-agent")
        assert loaded is not None
        assert loaded.name == "test-agent"

    def test_save_with_alias(self, tmp_global_writ: Path, sample_agent: InstructionConfig):
        store.init_global_store()
        store.save_to_library(sample_agent, alias="my-agent")
        loaded = store.load_from_library("my-agent")
        assert loaded is not None

    def test_list_library(self, tmp_global_writ: Path, sample_agent: InstructionConfig):
        store.init_global_store()
        store.save_to_library(sample_agent)
        items = store.list_library()
        assert len(items) == 1

    def test_library_routes_rule_to_rules_dir(self, tmp_global_writ: Path):
        store.init_global_store()
        cfg = InstructionConfig(name="lib-rule", task_type="rule", instructions="Library rule.")
        path = store.save_to_library(cfg)
        assert "rules" in path.parts
        loaded = store.load_from_library("lib-rule")
        assert loaded is not None

    def test_library_list_gathers_all_dirs(self, tmp_global_writ: Path):
        store.init_global_store()
        store.save_to_library(InstructionConfig(name="a", task_type="agent", instructions="A"))
        store.save_to_library(InstructionConfig(name="r", task_type="rule", instructions="R"))
        items = store.list_library()
        assert len(items) == 2
