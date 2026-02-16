"""Shared pytest fixtures for writ tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from writ.core.models import AgentConfig, CompositionConfig


@pytest.fixture()
def tmp_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Create a temporary project directory and change into it."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture()
def initialized_project(tmp_project: Path):
    """Create a temporary project with .writ/ initialized."""
    from writ.core import store
    store.init_project_store()
    store.save_config(store.load_config())
    return tmp_project


@pytest.fixture()
def sample_agent() -> AgentConfig:
    """A sample agent config for testing."""
    return AgentConfig(
        name="test-agent",
        description="A test agent",
        version="1.0.0",
        tags=["test", "sample"],
        instructions="You are a test agent. Follow best practices.",
        composition=CompositionConfig(
            inherits_from=[],
            receives_handoff_from=[],
            project_context=True,
        ),
    )


@pytest.fixture()
def sample_agent_with_parents() -> AgentConfig:
    """A sample agent that inherits from another agent."""
    return AgentConfig(
        name="child-agent",
        description="A child agent that inherits",
        instructions="You are a child agent. Follow parent instructions too.",
        composition=CompositionConfig(
            inherits_from=["parent-agent"],
            project_context=True,
        ),
    )


@pytest.fixture()
def parent_agent() -> AgentConfig:
    """A parent agent for composition testing."""
    return AgentConfig(
        name="parent-agent",
        description="A parent agent",
        instructions="You are the parent agent. Define architecture.",
    )


@pytest.fixture()
def tmp_global_writ(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Override ~/.writ/ to a temp directory."""
    global_dir = tmp_path / "global_writ"
    global_dir.mkdir()
    monkeypatch.setattr("writ.utils.global_writ_dir", lambda: global_dir)
    monkeypatch.setattr("writ.core.store.global_writ_dir", lambda: global_dir)
    return global_dir
