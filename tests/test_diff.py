"""Tests for writ diff (git-linked lint comparison)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from writ.cli import app

runner = CliRunner()

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git executable not found",
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_diff_not_git_repo(tmp_project: Path) -> None:
    f = tmp_project / "AGENTS.md"
    f.write_text("# Hi\n", encoding="utf-8")
    result = runner.invoke(app, ["diff", str(f), "--code"])
    assert result.exit_code == 1
    assert "git" in result.output.lower()


def test_diff_untracked(tmp_project: Path) -> None:
    _git(tmp_project, "init")
    _git(tmp_project, "config", "user.email", "t@t.t")
    _git(tmp_project, "config", "user.name", "t")
    f = tmp_project / "AGENTS.md"
    f.write_text("x", encoding="utf-8")
    result = runner.invoke(app, ["diff", str(f), "--code"])
    assert result.exit_code == 1
    assert "not tracked" in result.output.lower()


def test_diff_no_changes_from_ref(tmp_project: Path) -> None:
    _git(tmp_project, "init")
    _git(tmp_project, "config", "user.email", "t@t.t")
    _git(tmp_project, "config", "user.name", "t")
    agents = tmp_project / "AGENTS.md"
    agents.write_text("# A\n\nBe brief.\n", encoding="utf-8")
    _git(tmp_project, "add", "AGENTS.md")
    _git(tmp_project, "commit", "-m", "c1")
    other = tmp_project / "README.md"
    other.write_text("readme", encoding="utf-8")
    _git(tmp_project, "add", "README.md")
    _git(tmp_project, "commit", "-m", "c2")
    result = runner.invoke(
        app,
        ["diff", str(agents), "--ref", "HEAD~1", "--code"],
    )
    assert result.exit_code == 0
    assert "No changes" in result.output


def test_diff_shows_score_table(tmp_project: Path) -> None:
    _git(tmp_project, "init")
    _git(tmp_project, "config", "user.email", "t@t.t")
    _git(tmp_project, "config", "user.name", "t")
    agents = tmp_project / "AGENTS.md"
    agents.write_text("x", encoding="utf-8")
    _git(tmp_project, "add", "AGENTS.md")
    _git(tmp_project, "commit", "-m", "c1")
    agents.write_text(
        "## Title\n\nWhen editing code, run `pytest` and `ruff`.\n"
        "Verify with tests before merge.\n\n"
        "```python\ndef f():\n    pass\n```\n",
        encoding="utf-8",
    )
    _git(tmp_project, "add", "AGENTS.md")
    _git(tmp_project, "commit", "-m", "c2")
    result = runner.invoke(app, ["diff", str(agents), "--code"])
    assert result.exit_code == 0
    assert "writ diff:" in result.output
    assert "Score:" in result.output
    assert "->" in result.output
    assert "Clarity" in result.output
