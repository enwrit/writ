"""Tests for writ memory export/import/list CLI commands."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from writ.cli import app

runner = CliRunner()


class TestMemoryExport:

    def test_export_with_content(self, tmp_project: Path, tmp_global_writ: Path, monkeypatch):
        monkeypatch.setattr("writ.commands.memory.GLOBAL_MEMORY", tmp_global_writ / "memory")
        result = runner.invoke(
            app, ["memory", "export", "my-notes", "--content", "Key decision: use Rust"],
        )
        assert result.exit_code == 0
        assert "Exported" in result.output
        mem_file = tmp_global_writ / "memory" / "my-notes.md"
        assert mem_file.exists()
        text = mem_file.read_text(encoding="utf-8")
        assert "Key decision: use Rust" in text
        assert "project:" in text

    def test_export_from_file(self, tmp_project: Path, tmp_global_writ: Path, monkeypatch):
        monkeypatch.setattr("writ.commands.memory.GLOBAL_MEMORY", tmp_global_writ / "memory")
        src = tmp_project / "notes.md"
        src.write_text("# My Research\nFindings here.", encoding="utf-8")
        result = runner.invoke(app, ["memory", "export", "research", "--from", "notes.md"])
        assert result.exit_code == 0
        assert "Exported" in result.output
        mem_file = tmp_global_writ / "memory" / "research.md"
        assert "My Research" in mem_file.read_text(encoding="utf-8")

    def test_export_from_missing_file(self, tmp_project: Path, tmp_global_writ: Path, monkeypatch):
        monkeypatch.setattr("writ.commands.memory.GLOBAL_MEMORY", tmp_global_writ / "memory")
        result = runner.invoke(app, ["memory", "export", "x", "--from", "nope.md"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_export_bundles_project_context(
        self, initialized_project: Path, tmp_global_writ: Path, monkeypatch,
    ):
        monkeypatch.setattr("writ.commands.memory.GLOBAL_MEMORY", tmp_global_writ / "memory")
        from writ.core import store
        store.save_project_context("# My Project\nPython backend.")
        result = runner.invoke(app, ["memory", "export", "ctx"])
        assert result.exit_code == 0
        mem_file = tmp_global_writ / "memory" / "ctx.md"
        assert "My Project" in mem_file.read_text(encoding="utf-8")


class TestMemoryImport:

    def test_import_into_project(
        self, initialized_project: Path, tmp_global_writ: Path, monkeypatch,
    ):
        monkeypatch.setattr("writ.commands.memory.GLOBAL_MEMORY", tmp_global_writ / "memory")
        mem_dir = tmp_global_writ / "memory"
        mem_dir.mkdir(parents=True, exist_ok=True)
        content = "---\nproject: other\n---\n\nSome insights."
        (mem_dir / "insights.md").write_text(content, encoding="utf-8")

        result = runner.invoke(app, ["memory", "import", "insights"])
        assert result.exit_code == 0
        assert "Imported" in result.output
        local_mem = initialized_project / ".writ" / "memory" / "insights.md"
        assert local_mem.exists()

    def test_import_as_agent(self, initialized_project: Path, tmp_global_writ: Path, monkeypatch):
        monkeypatch.setattr("writ.commands.memory.GLOBAL_MEMORY", tmp_global_writ / "memory")
        mem_dir = tmp_global_writ / "memory"
        mem_dir.mkdir(parents=True, exist_ok=True)
        content = "---\nproject: other\n---\n\nArchitecture notes."
        (mem_dir / "arch.md").write_text(content, encoding="utf-8")

        result = runner.invoke(app, ["memory", "import", "arch", "--as-agent", "arch-ctx"])
        assert result.exit_code == 0
        assert "Created" in result.output
        from writ.core import store
        inst = store.load_instruction("arch-ctx")
        assert inst is not None
        assert "Architecture notes" in inst.instructions

    def test_import_not_found(self, initialized_project: Path, tmp_global_writ: Path, monkeypatch):
        monkeypatch.setattr("writ.commands.memory.GLOBAL_MEMORY", tmp_global_writ / "memory")
        result = runner.invoke(app, ["memory", "import", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestMemoryList:

    def test_list_empty(self, tmp_project: Path, tmp_global_writ: Path, monkeypatch):
        monkeypatch.setattr("writ.commands.memory.GLOBAL_MEMORY", tmp_global_writ / "memory")
        result = runner.invoke(app, ["memory", "list"])
        assert result.exit_code == 0
        assert "No memories" in result.output

    def test_list_shows_memories(
        self, initialized_project: Path, tmp_global_writ: Path, monkeypatch,
    ):
        monkeypatch.setattr("writ.commands.memory.GLOBAL_MEMORY", tmp_global_writ / "memory")
        mem_dir = tmp_global_writ / "memory"
        mem_dir.mkdir(parents=True, exist_ok=True)
        content = "---\nproject: demo\n---\n\nSome notes."
        (mem_dir / "notes.md").write_text(content, encoding="utf-8")

        result = runner.invoke(app, ["memory", "list"])
        assert result.exit_code == 0
        assert "notes" in result.output
