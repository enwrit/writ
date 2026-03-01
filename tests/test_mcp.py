"""Tests for the writ MCP server tools and the cursor-mcp formatter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from writ.cli import app
from writ.core.models import InstructionConfig
from writ.core.store import save_instruction, save_project_context

runner = CliRunner()

mcp_server = pytest.importorskip("writ.integrations.mcp_server", reason="mcp extra not installed")


# ---------------------------------------------------------------------------
# V1 Tools
# ---------------------------------------------------------------------------

class TestMcpTools:
    """Test MCP tool functions directly (no MCP transport needed)."""

    def test_list_instructions_returns_summaries(self, initialized_project: Path):
        save_instruction(
            InstructionConfig(name="dev", description="Developer", task_type="agent", tags=["py"])
        )
        save_instruction(
            InstructionConfig(name="rule1", task_type="rule", instructions="Standards.")
        )
        result = mcp_server.writ_list_instructions()
        names = {r["name"] for r in result}
        assert "dev" in names
        assert "rule1" in names
        assert any(r["task_type"] == "agent" for r in result)
        assert any(r["task_type"] == "rule" for r in result)

    def test_get_instruction_found(self, initialized_project: Path):
        save_instruction(
            InstructionConfig(name="reviewer", instructions="Review code carefully.")
        )
        result = mcp_server.writ_get_instruction("reviewer")
        assert "reviewer" in result
        assert "Review code carefully" in result

    def test_get_instruction_not_found(self, initialized_project: Path):
        result = mcp_server.writ_get_instruction("nonexistent")
        assert "not found" in result.lower()

    def test_get_project_context_from_stored(self, initialized_project: Path):
        save_project_context("# My Project\n\nPython + React")
        result = mcp_server.writ_get_project_context()
        assert "My Project" in result
        assert "Python + React" in result

    def test_get_project_context_generates_if_missing(self, initialized_project: Path):
        result = mcp_server.writ_get_project_context()
        assert "Project Context" in result or "Directory Structure" in result


# ---------------------------------------------------------------------------
# V2 Tools
# ---------------------------------------------------------------------------

class TestMcpV2ComposeContext:
    """Test writ_compose_context tool."""

    def test_compose_returns_instructions(self, initialized_project: Path):
        save_instruction(
            InstructionConfig(name="dev", instructions="You are a Python developer.")
        )
        result = mcp_server.writ_compose_context("dev")
        assert "Python developer" in result

    def test_compose_includes_project_context(self, initialized_project: Path):
        save_project_context("# My Project\nPython + FastAPI")
        save_instruction(
            InstructionConfig(name="dev", instructions="Build features.")
        )
        result = mcp_server.writ_compose_context("dev")
        assert "My Project" in result
        assert "Build features" in result

    def test_compose_not_found(self, initialized_project: Path):
        result = mcp_server.writ_compose_context("ghost")
        assert "not found" in result.lower()


class TestMcpV2SearchInstructions:
    """Test writ_search_instructions tool."""

    def test_search_by_name(self, initialized_project: Path):
        save_instruction(InstructionConfig(name="react-dev", description="React developer"))
        save_instruction(InstructionConfig(name="py-lint", description="Python linter"))
        results = mcp_server.writ_search_instructions("react")
        assert len(results) == 1
        assert results[0]["name"] == "react-dev"

    def test_search_by_tag(self, initialized_project: Path):
        save_instruction(InstructionConfig(name="a1", tags=["security", "review"]))
        save_instruction(InstructionConfig(name="a2", tags=["typescript"]))
        results = mcp_server.writ_search_instructions("security")
        assert len(results) == 1
        assert results[0]["name"] == "a1"

    def test_search_no_match(self, initialized_project: Path):
        save_instruction(InstructionConfig(name="dev"))
        results = mcp_server.writ_search_instructions("zzz_no_match")
        assert len(results) == 0


class TestMcpV2ReadFile:
    """Test writ_read_file tool."""

    def test_read_existing_file(self, initialized_project: Path):
        test_file = initialized_project / "hello.txt"
        test_file.write_text("Hello world!", encoding="utf-8")
        result = mcp_server.writ_read_file("hello.txt")
        assert result == "Hello world!"

    def test_read_nested_file(self, initialized_project: Path):
        nested = initialized_project / "src" / "app.py"
        nested.parent.mkdir(parents=True, exist_ok=True)
        nested.write_text("print('hi')", encoding="utf-8")
        result = mcp_server.writ_read_file("src/app.py")
        assert "print('hi')" in result

    def test_reject_path_traversal(self, initialized_project: Path):
        result = mcp_server.writ_read_file("../../etc/passwd")
        assert "error" in result.lower()

    def test_reject_nonexistent(self, initialized_project: Path):
        result = mcp_server.writ_read_file("no_such_file.txt")
        assert "error" in result.lower()

    def test_reject_empty_path(self, initialized_project: Path):
        result = mcp_server.writ_read_file("")
        assert "error" in result.lower()

    def test_reject_ignored_file(self, initialized_project: Path):
        node_mod = initialized_project / "node_modules" / "pkg" / "index.js"
        node_mod.parent.mkdir(parents=True, exist_ok=True)
        node_mod.write_text("module.exports = {}", encoding="utf-8")
        result = mcp_server.writ_read_file("node_modules/pkg/index.js")
        assert "error" in result.lower()


class TestMcpV2ListFiles:
    """Test writ_list_files tool."""

    def test_list_root(self, initialized_project: Path):
        (initialized_project / "README.md").write_text("# Hi", encoding="utf-8")
        (initialized_project / "main.py").write_text("pass", encoding="utf-8")
        result = mcp_server.writ_list_files(".")
        filenames = [Path(p).name for p in result]
        assert "README.md" in filenames
        assert "main.py" in filenames

    def test_list_with_pattern(self, initialized_project: Path):
        (initialized_project / "app.py").write_text("pass", encoding="utf-8")
        (initialized_project / "app.js").write_text("//", encoding="utf-8")
        result = mcp_server.writ_list_files(".", pattern=".py")
        assert any(p.endswith(".py") for p in result)
        assert not any(p.endswith(".js") for p in result)

    def test_list_ignores_node_modules(self, initialized_project: Path):
        nm = initialized_project / "node_modules" / "pkg" / "index.js"
        nm.parent.mkdir(parents=True, exist_ok=True)
        nm.write_text("//", encoding="utf-8")
        result = mcp_server.writ_list_files(".")
        assert not any("node_modules" in p for p in result)

    def test_list_invalid_directory(self, initialized_project: Path):
        result = mcp_server.writ_list_files("no_such_dir")
        assert any("error" in str(r).lower() for r in result)


# ---------------------------------------------------------------------------
# CLI + Formatter
# ---------------------------------------------------------------------------

class TestMcpCommand:
    """Test the writ mcp serve CLI command."""

    def test_mcp_help(self):
        result = runner.invoke(app, ["mcp", "--help"])
        assert result.exit_code == 0
        assert "serve" in result.output

    def test_mcp_serve_help(self):
        result = runner.invoke(app, ["mcp", "serve", "--help"])
        assert result.exit_code == 0
        assert "writ_list_instructions" in result.output
        assert "writ_compose_context" in result.output
        assert "writ_read_file" in result.output


class TestCursorMcpFormatter:
    """Test the cursor-mcp formatter."""

    def test_generates_mcp_json(self, initialized_project: Path):
        from writ.core.formatter import get_formatter

        fmt = get_formatter("cursor-mcp")
        cfg = InstructionConfig(name="dev", instructions="Dev agent.")
        path = fmt.write(cfg, "Dev agent.", root=initialized_project)

        assert path.name == "mcp.json"
        assert path.parent.name == ".cursor"

        data = json.loads(path.read_text(encoding="utf-8"))
        assert "mcpServers" in data
        assert "writ" in data["mcpServers"]
        assert data["mcpServers"]["writ"]["command"] == "writ"
        assert data["mcpServers"]["writ"]["args"] == ["mcp", "serve"]

    def test_preserves_existing_mcp_json(self, initialized_project: Path):
        cursor_dir = initialized_project / ".cursor"
        cursor_dir.mkdir(exist_ok=True)
        mcp_json = cursor_dir / "mcp.json"
        mcp_json.write_text(
            json.dumps({"mcpServers": {"other": {"command": "other-tool"}}}),
            encoding="utf-8",
        )

        from writ.core.formatter import get_formatter

        fmt = get_formatter("cursor-mcp")
        cfg = InstructionConfig(name="dev", instructions="Dev agent.")
        fmt.write(cfg, "Dev agent.", root=initialized_project)

        data = json.loads(mcp_json.read_text(encoding="utf-8"))
        assert "other" in data["mcpServers"]
        assert "writ" in data["mcpServers"]
