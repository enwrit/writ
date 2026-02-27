"""Tests for CLI commands via Typer's testing runner."""

from pathlib import Path

from typer.testing import CliRunner

from writ.cli import app

runner = CliRunner()


class TestVersion:
    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestInit:
    def test_init_creates_writ_dir(self, tmp_project: Path):
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (tmp_project / ".writ").is_dir()
        assert (tmp_project / ".writ" / "agents").is_dir()
        assert (tmp_project / ".writ" / "config.yaml").exists()
        assert (tmp_project / ".writ" / "project-context.md").exists()

    def test_init_twice_warns(self, tmp_project: Path):
        runner.invoke(app, ["init"])
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Already initialized" in result.output

    def test_init_force(self, tmp_project: Path):
        runner.invoke(app, ["init"])
        result = runner.invoke(app, ["init", "--force"])
        assert result.exit_code == 0
        assert "initialized" in result.output.lower()


class TestAdd:
    def test_add_agent(self, initialized_project: Path):
        result = runner.invoke(app, [
            "add", "reviewer",
            "--description", "Code reviewer",
            "--instructions", "You review code.",
            "--tags", "review,quality",
        ])
        assert result.exit_code == 0
        assert "Added" in result.output or "Created" in result.output
        assert (initialized_project / ".writ" / "agents" / "reviewer.yaml").exists()

    def test_add_duplicate(self, initialized_project: Path):
        runner.invoke(app, ["add", "reviewer", "--instructions", "Test"])
        result = runner.invoke(app, ["add", "reviewer", "--instructions", "Test"])
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_add_without_init(self, tmp_project: Path):
        result = runner.invoke(app, ["add", "test", "--instructions", "Test"])
        assert result.exit_code == 1
        assert "Not initialized" in result.output


class TestAddFile:
    def test_add_file_md(self, initialized_project: Path):
        md = initialized_project / "my-rules.md"
        md.write_text("# Coding Rules\n\nWrite clean code.\n", encoding="utf-8")
        result = runner.invoke(app, ["add", "--file", str(md)])
        assert result.exit_code == 0
        assert "Added" in result.output
        assert "my-rules" in result.output

    def test_add_file_with_name_override(self, initialized_project: Path):
        md = initialized_project / "random-file.md"
        md.write_text("Some instructions.\n", encoding="utf-8")
        result = runner.invoke(app, ["add", "custom-name", "--file", str(md)])
        assert result.exit_code == 0
        assert "custom-name" in result.output

    def test_add_file_mdc(self, initialized_project: Path):
        mdc = initialized_project / "project.mdc"
        mdc.write_text(
            "---\ndescription: Project rule\nalwaysApply: true\n---\n\n# Rule\n\nBe good.\n",
            encoding="utf-8",
        )
        result = runner.invoke(app, ["add", "--file", str(mdc)])
        assert result.exit_code == 0
        assert "Added" in result.output
        assert "rule" in result.output

    def test_add_file_directory(self, initialized_project: Path):
        rules_dir = initialized_project / "my-rules"
        rules_dir.mkdir()
        (rules_dir / "rule-a.md").write_text("# Rule A\n\nDo A.\n", encoding="utf-8")
        (rules_dir / "rule-b.md").write_text("# Rule B\n\nDo B.\n", encoding="utf-8")
        (rules_dir / "ignore.json").write_text("{}", encoding="utf-8")
        result = runner.invoke(app, ["add", "--file", str(rules_dir)])
        assert result.exit_code == 0
        assert "rule-a" in result.output
        assert "rule-b" in result.output
        assert "Imported 2" in result.output

    def test_add_file_not_found(self, initialized_project: Path):
        result = runner.invoke(app, ["add", "--file", "nonexistent.md"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_add_file_duplicate(self, initialized_project: Path):
        md = initialized_project / "my-agent.md"
        md.write_text("Instructions.\n", encoding="utf-8")
        runner.invoke(app, ["add", "--file", str(md)])
        result = runner.invoke(app, ["add", "--file", str(md)])
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_add_file_with_task_type_override(self, initialized_project: Path):
        md = initialized_project / "api-context.md"
        md.write_text("# API Context\n\nAPI info.\n", encoding="utf-8")
        result = runner.invoke(app, ["add", "--file", str(md), "--task-type", "context"])
        assert result.exit_code == 0
        assert "context" in result.output


class TestList:
    def test_list_empty(self, initialized_project: Path):
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No agents found" in result.output

    def test_list_with_agents(self, initialized_project: Path):
        runner.invoke(app, ["add", "agent-a", "--instructions", "A"])
        runner.invoke(app, ["add", "agent-b", "--instructions", "B"])
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "agent-a" in result.output
        assert "agent-b" in result.output


class TestUse:
    def test_use_agent(self, initialized_project: Path):
        runner.invoke(app, ["add", "reviewer", "--instructions", "You review code."])
        result = runner.invoke(app, ["use", "reviewer"])
        assert result.exit_code == 0
        assert "Activated" in result.output

    def test_use_nonexistent(self, initialized_project: Path):
        result = runner.invoke(app, ["use", "nonexistent"])
        assert result.exit_code == 1

    def test_use_with_format(self, initialized_project: Path):
        runner.invoke(app, ["add", "reviewer", "--instructions", "You review code."])
        result = runner.invoke(app, ["use", "reviewer", "--format", "cursor"])
        assert result.exit_code == 0
        assert (initialized_project / ".cursor" / "rules" / "writ-reviewer.mdc").exists()


class TestRemove:
    def test_remove_agent(self, initialized_project: Path):
        runner.invoke(app, ["add", "reviewer", "--instructions", "Test"])
        result = runner.invoke(app, ["remove", "reviewer", "--yes"])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_remove_nonexistent(self, initialized_project: Path):
        result = runner.invoke(app, ["remove", "nonexistent", "--yes"])
        assert result.exit_code == 1


class TestExport:
    def test_export_to_cursor(self, initialized_project: Path):
        runner.invoke(app, ["add", "reviewer", "--instructions", "Review code."])
        result = runner.invoke(app, ["export", "reviewer", "cursor"])
        assert result.exit_code == 0
        assert "Exported" in result.output

    def test_export_dry_run(self, initialized_project: Path):
        runner.invoke(app, ["add", "reviewer", "--instructions", "Review code."])
        result = runner.invoke(app, ["export", "reviewer", "cursor", "--dry-run"])
        assert result.exit_code == 0
        assert "Review code" in result.output

    def test_export_invalid_format(self, initialized_project: Path):
        runner.invoke(app, ["add", "reviewer", "--instructions", "Test"])
        result = runner.invoke(app, ["export", "reviewer", "invalid"])
        assert result.exit_code == 1


class TestCompose:
    def test_compose_preview(self, initialized_project: Path):
        runner.invoke(app, ["add", "reviewer", "--instructions", "Review carefully."])
        result = runner.invoke(app, ["compose", "reviewer"])
        assert result.exit_code == 0
        assert "Review carefully" in result.output


class TestAddTemplate:
    def test_add_template_fullstack(self, initialized_project: Path):
        result = runner.invoke(app, ["add", "--template", "fullstack"])
        assert result.exit_code == 0
        assert "Created" in result.output or "Loaded" in result.output
        # Verify agents were created
        agents_dir = initialized_project / ".writ" / "agents"
        agent_files = list(agents_dir.glob("*.yaml"))
        assert len(agent_files) >= 3  # architect, implementer, reviewer, tester

    def test_add_template_default(self, initialized_project: Path):
        result = runner.invoke(app, ["add", "--template", "default"])
        assert result.exit_code == 0

    def test_add_template_python(self, initialized_project: Path):
        result = runner.invoke(app, ["add", "--template", "python"])
        assert result.exit_code == 0
        list_result = runner.invoke(app, ["list"])
        assert "python-developer" in list_result.output

    def test_add_template_typescript(self, initialized_project: Path):
        result = runner.invoke(app, ["add", "--template", "typescript"])
        assert result.exit_code == 0
        list_result = runner.invoke(app, ["list"])
        assert "ts-developer" in list_result.output

    def test_add_template_invalid(self, initialized_project: Path):
        result = runner.invoke(app, ["add", "--template", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_add_template_skips_existing(self, initialized_project: Path):
        # Add fullstack agents first
        runner.invoke(app, ["add", "--template", "fullstack"])
        # Add again -- should skip
        result = runner.invoke(app, ["add", "--template", "fullstack"])
        assert result.exit_code == 0
        assert "Skipped" in result.output or "No new agents" in result.output

    def test_add_no_name_no_template_fails(self, initialized_project: Path):
        result = runner.invoke(app, ["add"])
        assert result.exit_code == 1


class TestInitImport:
    def test_init_imports_agents_md(self, tmp_project: Path):
        (tmp_project / "AGENTS.md").write_text("# Agents\nFollow strict rules.")
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Imported" in result.output
        # Verify the agent was created
        assert (tmp_project / ".writ" / "agents" / "agents-md.yaml").exists()

    def test_init_imports_cursor_rule(self, tmp_project: Path):
        rules_dir = tmp_project / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "my-rule.mdc").write_text(
            "---\ndescription: Test rule\n---\n\nFollow this rule."
        )
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Imported" in result.output

    def test_init_no_import_flag(self, tmp_project: Path):
        (tmp_project / "AGENTS.md").write_text("# Agents\nFollow rules.")
        result = runner.invoke(app, ["init", "--no-import-existing"])
        assert result.exit_code == 0
        # Should detect but not import
        assert "Found" in result.output
        assert not (tmp_project / ".writ" / "agents" / "agents-md.yaml").exists()


class TestSearch:
    def test_search_no_results(self, tmp_project: Path):
        """Search when no registries are available returns no results gracefully."""
        result = runner.invoke(app, ["search", "react typescript"])
        assert result.exit_code == 0
        assert "No results" in result.output

    def test_search_with_source_flag(self, tmp_project: Path):
        result = runner.invoke(app, ["search", "python", "--from", "prpm"])
        assert result.exit_code == 0


class TestVersionCommand:
    def test_version_command(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "writ" in result.output
        assert "Python" in result.output


class TestStatus:
    def test_status_not_initialized(self, tmp_project: Path):
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "no" in result.output

    def test_status_initialized(self, initialized_project: Path):
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "yes" in result.output

    def test_status_shows_agent_count(self, initialized_project: Path):
        runner.invoke(app, ["add", "agent-a", "--instructions", "A"])
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "1" in result.output


class TestLint:
    def test_lint_agent(self, initialized_project: Path):
        runner.invoke(app, [
            "add", "reviewer", "--description", "A reviewer",
            "--instructions", "Review code.", "--tags", "review",
        ])
        result = runner.invoke(app, ["lint", "reviewer"])
        assert result.exit_code == 0


class TestPublish:
    def test_publish_requires_init(self, tmp_project: Path):
        result = runner.invoke(app, ["publish", "reviewer", "--yes"])
        assert result.exit_code == 1
        assert "Not initialized" in result.output

    def test_publish_requires_login(
        self, initialized_project: Path, monkeypatch,
    ):
        runner.invoke(app, [
            "add", "reviewer", "--instructions", "Review code.",
        ])
        monkeypatch.setattr("writ.core.auth.is_logged_in", lambda: False)
        result = runner.invoke(app, ["publish", "reviewer", "--yes"])
        assert result.exit_code == 1
        assert "Not logged in" in result.output

    def test_publish_agent_not_found(
        self, initialized_project: Path, monkeypatch,
    ):
        monkeypatch.setattr("writ.core.auth.is_logged_in", lambda: True)
        result = runner.invoke(app, ["publish", "nonexistent", "--yes"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_publish_success(
        self, initialized_project: Path, monkeypatch,
    ):
        runner.invoke(app, [
            "add", "reviewer", "--instructions", "Review code.",
        ])
        monkeypatch.setattr("writ.core.auth.is_logged_in", lambda: True)
        monkeypatch.setattr(
            "writ.integrations.registry.RegistryClient",
            _MockRegistryClient,
        )
        result = runner.invoke(app, ["publish", "reviewer", "--yes"])
        assert result.exit_code == 0
        assert "Published" in result.output
        assert "Agent Card" in result.output
        assert "Browse" in result.output
        assert "Install" in result.output

    def test_publish_confirmation_cancelled(
        self, initialized_project: Path, monkeypatch,
    ):
        runner.invoke(app, [
            "add", "reviewer", "--instructions", "Review code.",
        ])
        monkeypatch.setattr("writ.core.auth.is_logged_in", lambda: True)
        result = runner.invoke(app, ["publish", "reviewer"], input="n\n")
        assert result.exit_code == 0
        assert "Cancelled" in result.output


class TestUnpublish:
    def test_unpublish_success(
        self, initialized_project: Path, monkeypatch,
    ):
        runner.invoke(app, [
            "add", "reviewer", "--instructions", "Review code.",
        ])
        monkeypatch.setattr("writ.core.auth.is_logged_in", lambda: True)
        monkeypatch.setattr(
            "writ.integrations.registry.RegistryClient",
            _MockRegistryClient,
        )
        result = runner.invoke(app, ["unpublish", "reviewer"])
        assert result.exit_code == 0
        assert "private" in result.output


class TestSearchRegistry:
    def test_search_includes_enwrit_source(
        self, tmp_project: Path, monkeypatch,
    ):
        """Search reports enwrit as a searched source."""
        result = runner.invoke(app, ["search", "python"])
        assert result.exit_code == 0
        assert "enwrit" in result.output or "No results" in result.output

    def test_search_from_enwrit(self, tmp_project: Path):
        result = runner.invoke(app, [
            "search", "python", "--from", "enwrit",
        ])
        assert result.exit_code == 0

    def test_search_limit_flag(self, tmp_project: Path):
        result = runner.invoke(app, [
            "search", "python", "--limit", "5",
        ])
        assert result.exit_code == 0


class _MockRegistryClient:
    """Mock RegistryClient for publish tests."""

    def __init__(self, *args, **kwargs):
        pass

    def push_to_library(self, name, agent, *, is_public=False):
        return True
