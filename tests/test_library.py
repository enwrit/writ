"""Tests for the personal library (save/load/library)."""

from pathlib import Path

from typer.testing import CliRunner

from writ.cli import app

runner = CliRunner()


class TestSave:
    def test_save_to_library(self, initialized_project: Path, tmp_global_writ: Path):
        runner.invoke(app, ["add", "reviewer", "--instructions", "Review code."])
        result = runner.invoke(app, ["save", "reviewer"])
        assert result.exit_code == 0
        assert "Saved" in result.output
        assert (tmp_global_writ / "agents" / "reviewer.yaml").exists()

    def test_save_with_alias(self, initialized_project: Path, tmp_global_writ: Path):
        runner.invoke(app, ["add", "reviewer", "--instructions", "Review code."])
        result = runner.invoke(app, ["save", "reviewer", "--as", "my-reviewer"])
        assert result.exit_code == 0
        assert (tmp_global_writ / "agents" / "my-reviewer.yaml").exists()

    def test_save_nonexistent(self, initialized_project: Path, tmp_global_writ: Path):
        result = runner.invoke(app, ["save", "nonexistent"])
        assert result.exit_code == 1


class TestLoad:
    def test_load_from_library(self, initialized_project: Path, tmp_global_writ: Path):
        # First save
        runner.invoke(app, ["add", "reviewer", "--instructions", "Review code."])
        runner.invoke(app, ["save", "reviewer"])
        # Remove from project
        runner.invoke(app, ["remove", "reviewer", "--yes"])
        # Load from library
        result = runner.invoke(app, ["load", "reviewer"])
        assert result.exit_code == 0
        assert "Loaded" in result.output

    def test_load_nonexistent(self, initialized_project: Path, tmp_global_writ: Path):
        result = runner.invoke(app, ["load", "nonexistent"])
        assert result.exit_code == 1


class TestLibraryList:
    def test_empty_library(self, initialized_project: Path, tmp_global_writ: Path):
        result = runner.invoke(app, ["library"])
        assert result.exit_code == 0
        assert "empty" in result.output.lower()

    def test_library_with_agents(self, initialized_project: Path, tmp_global_writ: Path):
        runner.invoke(app, ["add", "reviewer", "--instructions", "Review code."])
        runner.invoke(app, ["save", "reviewer"])
        result = runner.invoke(app, ["library"])
        assert result.exit_code == 0
        assert "reviewer" in result.output
