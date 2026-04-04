"""Tests for writ handoff create/list CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from writ.cli import app
from writ.core import store
from writ.core.models import InstructionConfig

runner = CliRunner()


@pytest.fixture()
def project_with_agents(initialized_project: Path):
    """Initialized project with two agents for handoff testing."""
    store.save_instruction(InstructionConfig(
        name="architect", description="Architect agent", instructions="Design systems.",
    ))
    store.save_instruction(InstructionConfig(
        name="implementer", description="Implementer agent", instructions="Write code.",
    ))
    return initialized_project


class TestHandoffCreate:

    def test_create_with_summary(self, project_with_agents):
        result = runner.invoke(app, [
            "handoff", "create", "architect", "implementer",
            "--summary", "API design complete. Use REST with JSON.",
        ])
        assert result.exit_code == 0
        assert "Created" in result.output
        assert "writ add implementer" in result.output

    def test_create_with_file(self, project_with_agents):
        notes = project_with_agents / "handoff-notes.md"
        notes.write_text("# Handoff\nDetailed design docs here.", encoding="utf-8")
        result = runner.invoke(app, [
            "handoff", "create", "architect", "implementer",
            "--file", "handoff-notes.md",
        ])
        assert result.exit_code == 0
        assert "Created" in result.output

    def test_create_no_content(self, project_with_agents):
        result = runner.invoke(app, ["handoff", "create", "architect", "implementer"])
        assert result.exit_code == 1
        assert "summary" in result.output.lower() or "file" in result.output.lower()

    def test_create_source_not_found(self, project_with_agents):
        result = runner.invoke(app, [
            "handoff", "create", "nonexistent", "implementer",
            "--summary", "test",
        ])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_create_target_not_found(self, project_with_agents):
        result = runner.invoke(app, [
            "handoff", "create", "architect", "nonexistent",
            "--summary", "test",
        ])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_create_not_initialized(self, tmp_project):
        result = runner.invoke(app, [
            "handoff", "create", "a", "b", "--summary", "test",
        ])
        assert result.exit_code == 1
        assert "init" in result.output.lower()

    def test_create_file_not_found(self, project_with_agents):
        result = runner.invoke(app, [
            "handoff", "create", "architect", "implementer",
            "--file", "missing.md",
        ])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestHandoffList:

    def test_list_empty(self, initialized_project):
        result = runner.invoke(app, ["handoff", "list"])
        assert result.exit_code == 0
        assert "No handoffs" in result.output

    def test_list_after_create(self, project_with_agents):
        runner.invoke(app, [
            "handoff", "create", "architect", "implementer",
            "--summary", "Design done.",
        ])
        result = runner.invoke(app, ["handoff", "list"])
        assert result.exit_code == 0
        assert "architect" in result.output
        assert "implementer" in result.output

    def test_list_not_initialized(self, tmp_project):
        result = runner.invoke(app, ["handoff", "list"])
        assert result.exit_code == 1
        assert "init" in result.output.lower()
