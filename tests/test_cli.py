"""Tests for CLI commands via Typer's testing runner."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from writ.cli import app

runner = CliRunner()


class TestVersion:
    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        from writ import __version__
        assert __version__ in result.output


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


class TestAddFromUrl:
    """``writ add --from https://...`` and ``--from url`` with mocked HTTP."""

    def _mock_response(self, text: str, final_url: str) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.text = text
        mock_resp.url = final_url
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_add_from_https_url_name_from_path(self, initialized_project: Path):
        body = "# Remote Guide\n\nDo the thing.\n"
        mock_resp = self._mock_response(
            body, "https://example.com/path/remote-guide.md",
        )
        with patch("writ.integrations.url.httpx.get", return_value=mock_resp):
            result = runner.invoke(
                app,
                ["add", "--from", "https://example.com/path/remote-guide.md"],
            )
        assert result.exit_code == 0
        assert "Added" in result.output
        assert "remote-guide" in result.output
        assert (initialized_project / ".writ" / "agents" / "remote-guide.yaml").exists()

    def test_add_from_https_url_with_name_override(self, initialized_project: Path):
        body = "# Title\n\nBody.\n"
        mock_resp = self._mock_response(body, "https://example.com/x.md")
        with patch("writ.integrations.url.httpx.get", return_value=mock_resp):
            result = runner.invoke(
                app,
                ["add", "custom-name", "--from", "https://example.com/x.md"],
            )
        assert result.exit_code == 0
        assert "custom-name" in result.output
        assert (initialized_project / ".writ" / "agents" / "custom-name.yaml").exists()

    def test_add_from_url_legacy_flag(self, initialized_project: Path):
        body = "# Legacy\n\nOK.\n"
        mock_resp = self._mock_response(body, "https://example.com/legacy.md")
        with patch("writ.integrations.url.httpx.get", return_value=mock_resp):
            result = runner.invoke(
                app,
                ["add", "https://example.com/legacy.md", "--from", "url"],
            )
        assert result.exit_code == 0
        assert "legacy" in result.output

    def test_add_from_https_fetch_fails(self, initialized_project: Path):
        import httpx

        with patch(
            "writ.integrations.url.httpx.get",
            side_effect=httpx.HTTPError("network"),
        ):
            result = runner.invoke(
                app,
                ["add", "--from", "https://example.com/missing.md"],
            )
        assert result.exit_code == 1
        assert "Could not fetch" in result.output


class TestList:
    def test_list_empty(self, initialized_project: Path):
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No instructions found" in result.output

    def test_list_with_instructions(self, initialized_project: Path):
        runner.invoke(app, ["add", "agent-a", "--instructions", "A"])
        runner.invoke(app, ["add", "agent-b", "--instructions", "B"])
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "agent-a" in result.output
        assert "agent-b" in result.output


class TestRemove:
    def test_remove_agent(self, initialized_project: Path):
        runner.invoke(app, ["add", "reviewer", "--instructions", "Test"])
        result = runner.invoke(app, ["remove", "reviewer", "--yes"])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_remove_nonexistent(self, initialized_project: Path):
        result = runner.invoke(app, ["remove", "nonexistent", "--yes"])
        assert result.exit_code == 1


class TestAddTemplate:
    def test_add_template_fullstack(self, initialized_project: Path):
        result = runner.invoke(app, ["add", "--template", "fullstack"])
        assert result.exit_code == 0
        assert "Created" in result.output or "Loaded" in result.output
        # Verify template instructions were created
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
        # Add fullstack template first
        runner.invoke(app, ["add", "--template", "fullstack"])
        # Add again -- should skip
        result = runner.invoke(app, ["add", "--template", "fullstack"])
        assert result.exit_code == 0
        assert (
            "Skipped" in result.output
            or "No new instructions from template" in result.output
        )

    def test_add_no_name_no_template_fails(self, initialized_project: Path):
        result = runner.invoke(app, ["add"])
        assert result.exit_code == 1


class TestInitImport:
    def test_init_imports_agents_md(self, tmp_project: Path):
        (tmp_project / "AGENTS.md").write_text("# Agents\nFollow strict rules.")
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Imported" in result.output
        # Verify the instruction was created
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
    def test_search_no_results(self, tmp_project: Path, monkeypatch):
        """Search when Hub and legacy return empty shows no results gracefully."""
        monkeypatch.setattr(
            "writ.commands.search._search_hub",
            lambda q, **kw: [],
        )
        monkeypatch.setattr(
            "writ.commands.search._search_legacy_all",
            lambda q, lim, **kw: [],
        )
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

    def test_status_shows_instruction_count(self, initialized_project: Path):
        runner.invoke(app, ["add", "agent-a", "--instructions", "A"])
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "1" in result.output


class TestLint:
    def test_lint_instruction(self, initialized_project: Path):
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

    def test_publish_instruction_not_found(
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
        assert "Browse" in result.output
        assert "writ add reviewer" in result.output

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
        result = runner.invoke(app, ["unpublish", "reviewer", "--yes"])
        assert result.exit_code == 0
        assert "private" in result.output


class TestSearchRegistry:
    def test_search_includes_enwrit_source(
        self, tmp_project: Path, monkeypatch,
    ):
        """Search reports enwrit as a source when Hub returns enwrit items."""
        monkeypatch.setattr(
            "writ.commands.search._search_hub",
            lambda q, **kw: [
                {"name": "my-agent", "source": "enwrit", "description": "Test", "writ_score": 70},
            ],
        )
        result = runner.invoke(app, ["search", "python"])
        assert result.exit_code == 0
        assert "enwrit" in result.output

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


class TestInitWritContext:
    """Tests for the writ-context auto-install on writ init."""

    def test_init_creates_writ_context_in_cursor(self, tmp_project: Path):
        (tmp_project / ".cursor").mkdir()
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        ctx_path = tmp_project / ".cursor" / "rules" / "writ-context.mdc"
        assert ctx_path.exists()
        content = ctx_path.read_text()
        assert "alwaysApply: true" in content
        assert "writ init" in content
        assert "writ search" in content

    def test_init_creates_writ_context_in_claude_rules(self, tmp_project: Path):
        (tmp_project / ".claude").mkdir()
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        ctx_path = tmp_project / ".claude" / "rules" / "writ-context.md"
        assert ctx_path.exists()
        content = ctx_path.read_text()
        assert "writ init" in content

    def test_init_creates_writ_context_in_kiro(self, tmp_project: Path):
        (tmp_project / ".kiro").mkdir()
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        ctx_path = tmp_project / ".kiro" / "steering" / "writ-context.md"
        assert ctx_path.exists()
        content = ctx_path.read_text()
        assert "inclusion: always" in content
        assert "writ init" in content

    def test_init_no_ide_saves_to_writ_only(self, tmp_project: Path):
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        yaml_path = tmp_project / ".writ" / "rules" / "writ-context.yaml"
        assert yaml_path.exists()
        assert not (tmp_project / ".cursor").exists()
        assert not (tmp_project / ".claude").exists()
        assert not (tmp_project / ".kiro").exists()

    def test_init_does_not_inject_agents_md(self, tmp_project: Path):
        (tmp_project / "AGENTS.md").write_text("# My Agent\n\nMy rules.\n")
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        agents_md = (tmp_project / "AGENTS.md").read_text()
        assert "writ" not in agents_md.lower() or "My Agent" in agents_md

    def test_init_multi_ide(self, tmp_project: Path):
        (tmp_project / ".cursor").mkdir()
        (tmp_project / ".claude").mkdir()
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (tmp_project / ".cursor" / "rules" / "writ-context.mdc").exists()
        assert (tmp_project / ".claude" / "rules" / "writ-context.md").exists()


class TestDetectActiveTools:
    def test_detects_cursor_only(self, tmp_project: Path):
        (tmp_project / ".cursor").mkdir()
        from writ.commands.init import _detect_active_tools
        formats = _detect_active_tools()
        assert formats == ["cursor"]

    def test_detects_claude_rules(self, tmp_project: Path):
        (tmp_project / ".claude").mkdir()
        from writ.commands.init import _detect_active_tools
        formats = _detect_active_tools()
        assert formats == ["claude_rules"]

    def test_detects_kiro_steering(self, tmp_project: Path):
        (tmp_project / ".kiro").mkdir()
        from writ.commands.init import _detect_active_tools
        formats = _detect_active_tools()
        assert formats == ["kiro_steering"]

    def test_ignores_shared_files(self, tmp_project: Path):
        (tmp_project / "AGENTS.md").write_text("# Agents\n")
        (tmp_project / "CLAUDE.md").write_text("# Claude\n")
        (tmp_project / ".windsurfrules").write_text("rules\n")
        from writ.commands.init import _detect_active_tools
        formats = _detect_active_tools()
        assert "agents_md" not in formats
        assert "claude" not in formats
        assert "windsurf" not in formats

    def test_empty_when_no_ide(self, tmp_project: Path):
        from writ.commands.init import _detect_active_tools
        formats = _detect_active_tools()
        assert formats == []


class TestSearchRewrite:
    def test_search_uses_hub_fallback(self, tmp_project: Path, monkeypatch):
        monkeypatch.setattr(
            "writ.commands.search._search_hub",
            lambda q, **kw: [],
        )
        monkeypatch.setattr(
            "writ.commands.search._search_legacy_all",
            lambda q, lim, **kw: [
                {"name": "test-agent", "source": "enwrit", "description": "Test", "writ_score": 80},
            ],
        )
        result = runner.invoke(app, ["search", "test"])
        assert result.exit_code == 0
        assert "test-agent" in result.output

    def test_search_default_limit_5(self, tmp_project: Path, monkeypatch):
        items = [
            {"name": f"agent-{i}", "source": "prpm", "description": f"Agent {i}", "writ_score": 50}
            for i in range(10)
        ]
        monkeypatch.setattr(
            "writ.commands.search._search_hub",
            lambda q, **kw: items,
        )
        result = runner.invoke(app, ["search", "test"])
        assert result.exit_code == 0
        assert "agent-0" in result.output
        assert "agent-4" in result.output
        assert "agent-5" not in result.output

    def test_search_prpm_direct(self, tmp_project: Path, monkeypatch):
        monkeypatch.setattr(
            "writ.commands.search._search_prpm",
            lambda q, lim: [{"name": "prpm-pkg", "source": "prpm", "description": "From PRPM"}],
        )
        result = runner.invoke(app, ["search", "test", "--from", "prpm"])
        assert result.exit_code == 0
        assert "prpm-pkg" in result.output


class _MockRegistryClient:
    """Mock RegistryClient for publish tests."""

    def __init__(self, *args, **kwargs):
        pass

    def push_to_library(self, name, agent, *, is_public=False):
        return True
