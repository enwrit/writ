"""Tests for the personal library (save, list --library)."""

from pathlib import Path

from typer.testing import CliRunner

from writ.cli import app

runner = CliRunner()

# Must not collide with Hub semantic matches (empty library -> add would fetch Hub otherwise).
_LIB_NAME = "writ_test_library_unique_z9"


class TestSave:
    def test_save_to_library(self, initialized_project: Path, tmp_global_writ: Path):
        runner.invoke(app, ["add", _LIB_NAME, "--instructions", "Review code."])
        result = runner.invoke(app, ["save", _LIB_NAME])
        assert result.exit_code == 0
        assert "Saved" in result.output
        assert (tmp_global_writ / "agents" / f"{_LIB_NAME}.yaml").exists()

    def test_save_with_alias(self, initialized_project: Path, tmp_global_writ: Path):
        runner.invoke(app, ["add", _LIB_NAME, "--instructions", "Review code."])
        result = runner.invoke(app, ["save", _LIB_NAME, "--as", "my-reviewer"])
        assert result.exit_code == 0
        assert (tmp_global_writ / "agents" / "my-reviewer.yaml").exists()

    def test_save_nonexistent(self, initialized_project: Path, tmp_global_writ: Path):
        result = runner.invoke(app, ["save", "nonexistent"])
        assert result.exit_code == 1
        assert "not found in this project" in result.output


class TestLibraryList:
    def test_empty_library(self, initialized_project: Path, tmp_global_writ: Path):
        result = runner.invoke(app, ["list", "--library"])
        assert result.exit_code == 0
        assert "empty" in result.output.lower()

    def test_library_with_agents(self, initialized_project: Path, tmp_global_writ: Path):
        runner.invoke(app, ["add", _LIB_NAME, "--instructions", "Review code."])
        runner.invoke(app, ["save", _LIB_NAME])
        result = runner.invoke(app, ["list", "--library"])
        assert result.exit_code == 0
        assert _LIB_NAME in result.output
