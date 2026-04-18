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
# Lint-score integration in docs health
# ---------------------------------------------------------------------------


def test_doc_health_populates_lint_score_on_first_check(
    initialized_project: Path, monkeypatch,
) -> None:
    (initialized_project / "README.md").write_text(
        "# Guide\n\nRun `writ init` before anything else.\n",
        encoding="utf-8",
    )
    from writ.core import doc_health

    monkeypatch.setattr(doc_health, "_score_file_tier2", lambda p: 73)

    report = doc_health.run_health_check(initialized_project)
    readme = next((f for f in report.files if f.path == "README.md"), None)
    assert readme is not None
    assert readme.lint_score == 73


def test_doc_health_attaches_lint_score_for_nested_files_windows_paths(
    initialized_project: Path, monkeypatch,
) -> None:
    """Regression: on Windows, file_reports use native `\\` paths while the
    lint-scores map uses posix keys. Scores must still be attached to nested
    files regardless of separator style.
    """
    rules = initialized_project / ".cursor" / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    target = rules / "example-rule.mdc"
    target.write_text("# Example rule\n\nDo the thing.\n", encoding="utf-8")

    from writ.core import doc_health

    monkeypatch.setattr(doc_health, "_score_file_tier2", lambda p: 41)

    report = doc_health.run_health_check(initialized_project)
    nested = next(
        (f for f in report.files if f.path.endswith("example-rule.mdc")), None,
    )
    assert nested is not None
    assert nested.lint_score == 41


def test_doc_health_uses_cache_when_mtime_unchanged(
    initialized_project: Path, monkeypatch,
) -> None:
    (initialized_project / "README.md").write_text("# Guide", encoding="utf-8")
    from writ.core import doc_health

    calls = {"count": 0}

    def _score(_path):
        calls["count"] += 1
        return 60

    monkeypatch.setattr(doc_health, "_score_file_tier2", _score)

    doc_health.run_health_check(initialized_project)
    first_calls = calls["count"]
    assert first_calls == 1

    doc_health.run_health_check(initialized_project)
    assert calls["count"] == first_calls, "should hit cache, not rescore"


def test_doc_health_rescore_when_mtime_newer_than_cache(
    initialized_project: Path, monkeypatch,
) -> None:
    readme = initialized_project / "README.md"
    readme.write_text("# Guide", encoding="utf-8")
    from writ.core import doc_health

    scores = [55, 80]

    def _score(_path):
        return scores.pop(0) if scores else 0

    monkeypatch.setattr(doc_health, "_score_file_tier2", _score)

    first = doc_health.run_health_check(initialized_project)
    first_readme = next(f for f in first.files if f.path == "README.md")
    assert first_readme.lint_score == 55

    import os
    import time
    future = time.time() + 120
    os.utime(readme, (future, future))

    second = doc_health.run_health_check(initialized_project)
    second_readme = next(f for f in second.files if f.path == "README.md")
    assert second_readme.lint_score == 80


def test_orphan_page_flagged_when_no_inbound_refs(
    initialized_project: Path,
) -> None:
    rules = initialized_project / ".cursor" / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "lonely-rule.mdc").write_text("# Lonely rule", encoding="utf-8")
    (rules / "hub-rule.mdc").write_text(
        "# Hub rule\nDoes not mention the orphan.\n", encoding="utf-8",
    )

    from writ.core import doc_health

    report = doc_health.run_health_check(initialized_project)
    lonely = next(
        (f for f in report.files if f.path.endswith("lonely-rule.mdc")), None,
    )
    assert lonely is not None
    assert any(i.kind == "orphan" for i in lonely.issues)


def test_orphan_cleared_when_another_file_references_it(
    initialized_project: Path,
) -> None:
    rules = initialized_project / ".cursor" / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "target-rule.mdc").write_text("# Target", encoding="utf-8")
    (rules / "linker-rule.mdc").write_text(
        "See `target-rule.mdc` for details.\n", encoding="utf-8",
    )

    from writ.core import doc_health

    report = doc_health.run_health_check(initialized_project)
    target = next(
        (f for f in report.files if f.path.endswith("target-rule.mdc")), None,
    )
    assert target is not None
    assert not any(i.kind == "orphan" for i in target.issues)


def test_orphan_exempt_entry_points_never_flagged(
    initialized_project: Path,
) -> None:
    (initialized_project / "README.md").write_text(
        "# Top-level readme\n", encoding="utf-8",
    )
    (initialized_project / "AGENTS.md").write_text(
        "# Agents\n", encoding="utf-8",
    )

    from writ.core import doc_health

    report = doc_health.run_health_check(initialized_project)
    for fname in ("README.md", "AGENTS.md"):
        fr = next((f for f in report.files if f.path == fname), None)
        if fr is None:
            continue
        assert not any(i.kind == "orphan" for i in fr.issues)


def test_doc_health_respects_rescore_cap(
    initialized_project: Path, monkeypatch,
) -> None:
    rules = initialized_project / ".cursor" / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    for i in range(55):
        (rules / f"rule-{i:02d}.mdc").write_text(
            f"# rule {i}", encoding="utf-8",
        )

    from writ.core import doc_health

    monkeypatch.setattr(doc_health, "_score_file_tier2", lambda p: 70)

    report = doc_health.run_health_check(initialized_project)
    assert report.lint_cap_exceeded is True


# ---------------------------------------------------------------------------
# writ docs update
# ---------------------------------------------------------------------------


def test_docs_update_requires_index(initialized_project: Path) -> None:
    result = runner.invoke(app, ["docs", "update"])
    assert result.exit_code == 1
    assert "No documentation index found" in result.output


def test_docs_update_prompt_includes_concept_gap_pass() -> None:
    from writ.commands.docs import _BUILTIN_PROMPTS

    text = (_BUILTIN_PROMPTS / "docs-update-v1.md").read_text(encoding="utf-8")
    assert "Step 2b: Concept-gap pass" in text
    assert "A single clarifying sentence" in text
    assert "A short bullet added to an existing list" in text
    assert "A new subsection in an existing file" in text
    assert "A new dedicated page" in text
    assert "Prefer silence over padding" in text


def test_docs_update_prints_instruction(initialized_project: Path) -> None:
    runner.invoke(app, ["docs", "init"])
    result = runner.invoke(app, ["docs", "update"])
    assert result.exit_code == 0
    assert "Documentation Update Instruction" in result.output
    assert "Health score" in result.output


def test_docs_update_subagent_emits_wrapper_prompt(
    initialized_project: Path,
) -> None:
    runner.invoke(app, ["docs", "init"])
    result = runner.invoke(app, ["docs", "update", "--subagent"])
    assert result.exit_code == 0
    assert "subagent" in result.output.lower()
    assert "handover" in result.output.lower()
    assert "git status" in result.output, (
        "subagent prompt should instruct the subagent to run git status itself"
    )


def test_docs_update_subagent_does_not_run_health_check_inline(
    initialized_project: Path,
) -> None:
    """Regression: the subagent runs `writ docs check` itself.

    The parent emits only the delegation prompt; it must not include the
    health check output, otherwise the parent has already paid the token
    cost the delegation was supposed to avoid.
    """
    runner.invoke(app, ["docs", "init"])
    result = runner.invoke(app, ["docs", "update", "--subagent"])
    assert result.exit_code == 0
    assert "Health score" not in result.output
    assert "Project Documentation Health" not in result.output


def test_docs_update_subagent_logs_delegation(
    initialized_project: Path,
) -> None:
    runner.invoke(app, ["docs", "init"])
    runner.invoke(app, ["docs", "update", "--subagent"])

    from writ.core import store

    cfg = store.load_instruction("writ-log")
    assert cfg is not None
    assert "subagent" in cfg.instructions.lower()


def test_docs_update_default_does_not_emit_subagent_prompt(
    initialized_project: Path,
) -> None:
    runner.invoke(app, ["docs", "init"])
    result = runner.invoke(app, ["docs", "update"])
    assert result.exit_code == 0
    assert "Subagent Delegation" not in result.output


def test_docs_update_subagent_prompt_includes_concept_gap() -> None:
    from writ.commands.docs import _BUILTIN_PROMPTS

    path = _BUILTIN_PROMPTS / "docs-update-subagent-v1.md"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "concept-gap" in text.lower() or "Step 2b" in text


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
    assert "No matches" in result.output or "Matches for" in result.output
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


def test_status_shows_lint_average_when_cache_present(
    initialized_project: Path,
) -> None:
    import json

    cache = initialized_project / ".writ" / "lint-scores.json"
    cache.write_text(
        json.dumps({
            "scores": {
                "README.md": {"headline_score": 72, "timestamp": "2026-04-18T00:00:00"},
                "AGENTS.md": {"headline_score": 88, "timestamp": "2026-04-18T00:00:00"},
            },
        }),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Lint" in result.output


def test_status_shows_last_instruction_change(
    initialized_project: Path, monkeypatch,
) -> None:
    from writ.commands import status as status_mod

    monkeypatch.setattr(status_mod, "_last_instruction_change", lambda: "abc1234 fix docs")
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "abc1234" in result.output


def test_status_hides_sync_row_when_logged_out(
    initialized_project: Path,
) -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Sync" not in result.output or "out of sync" not in result.output


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
