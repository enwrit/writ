"""Tests for writ docs (init/check/update), writ query, writ status, log, and soft nudge."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from writ.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# writ docs init
# ---------------------------------------------------------------------------


def test_docs_init_creates_index(initialized_project: Path) -> None:
    result = runner.invoke(app, ["docs", "init"])
    assert result.exit_code == 0
    assert "writ-docs-index" in result.output
    assert "Instruction for your AI agent" in result.output

    from writ.core import store

    cfg = store.load_instruction("writ-docs-index")
    assert cfg is not None
    assert cfg.task_type == "rule"
    assert "Documentation Index" in cfg.instructions


def test_docs_init_creates_log(initialized_project: Path) -> None:
    runner.invoke(app, ["docs", "init"])

    from writ.core import store

    cfg = store.load_instruction("writ-log")
    assert cfg is not None
    assert "docs init" in cfg.instructions
    assert "writ-docs-index" in cfg.instructions


def test_docs_init_refuses_duplicate(initialized_project: Path) -> None:
    runner.invoke(app, ["docs", "init"])
    result = runner.invoke(app, ["docs", "init"])
    assert result.exit_code == 0
    assert "already exists" in result.output


def test_docs_init_force_overwrites(initialized_project: Path) -> None:
    runner.invoke(app, ["docs", "init"])
    result = runner.invoke(app, ["docs", "init", "--force"])
    assert result.exit_code == 0
    assert "writ-docs-index" in result.output


def test_docs_init_requires_writ_dir(tmp_project: Path) -> None:
    result = runner.invoke(app, ["docs", "init"])
    assert result.exit_code == 1
    assert "init" in result.output.lower()


def test_docs_init_finds_ide_files(initialized_project: Path) -> None:
    """Index should include files from IDE folders, not .writ/ internals."""
    rules_dir = initialized_project / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "my-rule.mdc").write_text("# rule", encoding="utf-8")
    (initialized_project / "README.md").write_text("# Hi", encoding="utf-8")

    runner.invoke(app, ["docs", "init"])

    from writ.core import store

    cfg = store.load_instruction("writ-docs-index")
    assert cfg is not None
    assert "my-rule.mdc" in cfg.instructions
    assert "README.md" in cfg.instructions


def test_docs_init_excludes_writ_dir(initialized_project: Path) -> None:
    """Index should NOT include .writ/ internal YAML files."""
    runner.invoke(app, ["docs", "init"])

    from writ.core import store

    cfg = store.load_instruction("writ-docs-index")
    assert cfg is not None
    assert ".writ/" not in cfg.instructions


# ---------------------------------------------------------------------------
# writ docs check
# ---------------------------------------------------------------------------


def test_docs_check_empty_project(initialized_project: Path) -> None:
    result = runner.invoke(app, ["docs", "check"])
    assert result.exit_code == 0
    assert "No documentation files found" in result.output


def test_docs_check_with_files(initialized_project: Path) -> None:
    readme = initialized_project / "README.md"
    readme.write_text("# Test\n\nSome content.\n", encoding="utf-8")
    result = runner.invoke(app, ["docs", "check"])
    assert result.exit_code == 0
    assert "Documentation Health" in result.output


def test_docs_check_json_output(initialized_project: Path) -> None:
    readme = initialized_project / "README.md"
    readme.write_text("# Test\n\nSome content.\n", encoding="utf-8")
    result = runner.invoke(app, ["docs", "check", "--json"])
    assert result.exit_code == 0
    assert "health_score" in result.output


def test_docs_check_invalid_path() -> None:
    result = runner.invoke(app, ["docs", "check", "/nonexistent/path/xyz"])
    assert result.exit_code == 1
    assert "Not a directory" in result.output


# ---------------------------------------------------------------------------
# writ docs update
# ---------------------------------------------------------------------------


def test_docs_update_requires_index(initialized_project: Path) -> None:
    result = runner.invoke(app, ["docs", "update"])
    assert result.exit_code == 1
    assert "No documentation index found" in result.output


def test_docs_update_prints_instruction(initialized_project: Path) -> None:
    runner.invoke(app, ["docs", "init"])
    result = runner.invoke(app, ["docs", "update"])
    assert result.exit_code == 0
    assert "Documentation Update Instruction" in result.output
    assert "Health score" in result.output


def test_docs_update_creates_log_entry(initialized_project: Path) -> None:
    runner.invoke(app, ["docs", "init"])
    runner.invoke(app, ["docs", "update"])

    from writ.core import store

    cfg = store.load_instruction("writ-log")
    assert cfg is not None
    assert "docs update" in cfg.instructions


# ---------------------------------------------------------------------------
# writ query
# ---------------------------------------------------------------------------


def test_query_no_index(initialized_project: Path) -> None:
    result = runner.invoke(app, ["query"])
    assert result.exit_code == 1
    assert "No documentation index found" in result.output


def test_query_shows_index(initialized_project: Path) -> None:
    runner.invoke(app, ["docs", "init"])
    result = runner.invoke(app, ["query"])
    assert result.exit_code == 0
    assert "Documentation Index" in result.output


def test_query_with_search_arg(initialized_project: Path) -> None:
    runner.invoke(app, ["docs", "init"])
    result = runner.invoke(app, ["query", "architecture"])
    assert result.exit_code == 0
    assert "coming soon" in result.output
    assert "Documentation Index" in result.output


# ---------------------------------------------------------------------------
# writ status (enhanced with health + log)
# ---------------------------------------------------------------------------


def test_status_basic(initialized_project: Path) -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "writ status" in result.output
    assert "Project initialized" in result.output


def test_status_shows_health_score(initialized_project: Path) -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Documentation health" in result.output


def test_status_shows_log_entries(initialized_project: Path) -> None:
    runner.invoke(app, ["docs", "init"])
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Recent activity" in result.output
    assert "docs init" in result.output


def test_status_not_initialized(tmp_project: Path) -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "no" in result.output.lower()


# ---------------------------------------------------------------------------
# append_log utility
# ---------------------------------------------------------------------------


def test_append_log_creates_instruction(initialized_project: Path) -> None:
    from writ.utils import append_log

    append_log(initialized_project, "test entry one")

    from writ.core import store

    cfg = store.load_instruction("writ-log")
    assert cfg is not None
    assert "writ log" in cfg.instructions
    assert "test entry one" in cfg.instructions


def test_append_log_appends(initialized_project: Path) -> None:
    from writ.utils import append_log

    append_log(initialized_project, "first")
    append_log(initialized_project, "second")

    from writ.core import store

    cfg = store.load_instruction("writ-log")
    assert cfg is not None
    assert "first" in cfg.instructions
    assert "second" in cfg.instructions
    assert cfg.instructions.count("# writ log") == 1


def test_append_log_has_timestamp(initialized_project: Path) -> None:
    from writ.utils import append_log

    append_log(initialized_project, "timestamped")

    from writ.core import store

    cfg = store.load_instruction("writ-log")
    assert cfg is not None
    assert "UTC]" in cfg.instructions


def test_append_log_always_apply_off(initialized_project: Path) -> None:
    from writ.utils import append_log

    append_log(initialized_project, "test")

    from writ.core import store

    cfg = store.load_instruction("writ-log")
    assert cfg is not None
    assert cfg.format_overrides is not None
    assert cfg.format_overrides.cursor is not None
    assert cfg.format_overrides.cursor.always_apply is False


# ---------------------------------------------------------------------------
# Soft nudge after writ add
# ---------------------------------------------------------------------------


def test_add_no_nudge_without_index(initialized_project: Path) -> None:
    result = runner.invoke(app, ["add", "test-temp", "--yes"])
    assert "docs index" not in result.output.lower() or result.exit_code != 0


def test_add_nudge_with_index(initialized_project: Path) -> None:
    runner.invoke(app, ["docs", "init"])

    from writ.core import store
    from writ.core.models import InstructionConfig

    cfg = InstructionConfig(
        name="my-test-rule",
        description="test",
        instructions="test content",
        task_type="rule",
    )
    store.save_instruction(cfg)

    from io import StringIO

    from rich.console import Console

    from writ.commands.agent import _print_added

    console_capture = Console(file=StringIO())
    import writ.commands.agent as agent_mod
    original_console = agent_mod.console
    agent_mod.console = console_capture

    try:
        _print_added(cfg, "test")
        output = console_capture.file.getvalue()
        assert "docs index" in output.lower() or "writ docs update" in output.lower()
    finally:
        agent_mod.console = original_console


def test_add_no_nudge_for_index_itself(initialized_project: Path) -> None:
    runner.invoke(app, ["docs", "init"])

    from writ.core import store

    cfg = store.load_instruction("writ-docs-index")
    assert cfg is not None

    from io import StringIO

    from rich.console import Console

    from writ.commands.agent import _print_added

    console_capture = Console(file=StringIO())
    import writ.commands.agent as agent_mod
    original_console = agent_mod.console
    agent_mod.console = console_capture

    try:
        _print_added(cfg, "test")
        output = console_capture.file.getvalue()
        assert "docs index" not in output.lower() or "writ docs update" not in output.lower()
    finally:
        agent_mod.console = original_console
