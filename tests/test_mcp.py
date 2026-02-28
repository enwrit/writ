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
