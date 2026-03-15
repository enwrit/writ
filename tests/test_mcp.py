"""Tests for the writ MCP server tools and the cursor-mcp formatter."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from writ.cli import app
from writ.core.models import InstructionConfig, PeerConfig, PeersManifest
from writ.core.store import save_instruction, save_project_context

runner = CliRunner()

mcp_server = pytest.importorskip(
    "writ.integrations.mcp_server", reason="mcp extra not installed"
)


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


class TestMcpV2InstallInstruction:
    """Test writ_install_instruction tool."""

    def test_install_from_hub(self, initialized_project: Path):
        mock_data = {
            "name": "test-rule",
            "description": "A test rule",
            "instructions": "Do the thing.",
            "tags": ["test"],
            "version": "1.0.0",
            "task_type": "rule",
        }
        with patch.object(
            mcp_server, "_registry_client"
        ) as mock_client_fn:
            mock_client_fn.return_value.pull_public_agent.return_value = mock_data
            result = mcp_server.writ_install_instruction("test-rule")
        assert result["status"] == "installed"
        assert result["name"] == "test-rule"
        assert result["task_type"] == "rule"
        from writ.core.store import load_instruction
        cfg = load_instruction("test-rule")
        assert cfg is not None
        assert cfg.instructions == "Do the thing."
        assert cfg.source == "enwrit.com/test-rule@1.0.0"

    def test_install_not_found(self, initialized_project: Path):
        with patch.object(
            mcp_server, "_registry_client"
        ) as mock_client_fn:
            mock_client_fn.return_value.pull_public_agent.return_value = None
            result = mcp_server.writ_install_instruction("nonexistent")
        assert "error" in result
        assert "not found" in result["error"]

    def test_install_already_exists(self, initialized_project: Path):
        save_instruction(InstructionConfig(name="existing", instructions="Hi"))
        result = mcp_server.writ_install_instruction("existing")
        assert "error" in result
        assert "already exists" in result["error"]


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


# ---------------------------------------------------------------------------
# V3 Tools -- agent-to-agent conversations
# ---------------------------------------------------------------------------

@pytest.fixture()
def two_peers(initialized_project: Path, tmp_path: Path):
    """Set up two local repos that are peers of each other."""
    from writ.core import peers as peers_mod

    save_instruction(
        InstructionConfig(name="dev", instructions="Developer agent.")
    )

    peer_dir = tmp_path / "peer-repo"
    peer_dir.mkdir()
    peer_writ = peer_dir / ".writ"
    peer_writ.mkdir()
    (peer_writ / "conversations").mkdir()

    manifest = PeersManifest(peers={
        "peer-repo": PeerConfig(
            name="peer-repo",
            path=str(peer_dir),
            transport="local",
        ),
    })
    peers_mod.save_peers(manifest)

    return initialized_project, peer_dir


class TestMcpV3StartConversation:

    def test_creates_conversation(self, two_peers):
        repo_dir, peer_dir = two_peers
        result = mcp_server.writ_start_conversation(
            to_repo="peer-repo",
            goal="test goal",
            message="Hello peer!",
        )
        assert "conv_id" in result
        assert result["status"] == "started"
        assert result["file"].endswith(".md")

    def test_syncs_to_local_peer(self, two_peers):
        repo_dir, peer_dir = two_peers
        mcp_server.writ_start_conversation(
            to_repo="peer-repo",
            goal="sync test",
            message="Should appear in peer",
        )
        peer_convs = list((peer_dir / ".writ" / "conversations").iterdir())
        assert len(peer_convs) == 1
        content = peer_convs[0].read_text(encoding="utf-8")
        assert "Should appear in peer" in content

    def test_unknown_peer_returns_error(self, initialized_project: Path):
        result = mcp_server.writ_start_conversation(
            to_repo="nonexistent",
            goal="nope",
            message="hi",
        )
        assert "error" in result

    def test_returns_conv_id_format(self, two_peers):
        _, _ = two_peers
        result = mcp_server.writ_start_conversation(
            to_repo="peer-repo",
            goal="id test",
            message="check id",
        )
        assert result["conv_id"].startswith("conv-")


class TestMcpV3SendMessage:

    def test_appends_message(self, two_peers):
        _, _ = two_peers
        start = mcp_server.writ_start_conversation(
            to_repo="peer-repo", goal="chat", message="first",
        )
        result = mcp_server.writ_send_message(
            conv_id=start["conv_id"], message="second message",
        )
        assert result["status"] == "sent"
        assert result["message_count"] >= 2

    def test_not_found(self, initialized_project: Path):
        result = mcp_server.writ_send_message(
            conv_id="conv-nonexistent", message="hi",
        )
        assert "error" in result

    def test_rejects_completed_conversation(self, two_peers):
        _, _ = two_peers
        start = mcp_server.writ_start_conversation(
            to_repo="peer-repo", goal="done", message="first",
        )
        mcp_server.writ_complete_conversation(
            conv_id=start["conv_id"], summary="all done",
        )
        result = mcp_server.writ_send_message(
            conv_id=start["conv_id"], message="too late",
        )
        assert "error" in result


class TestMcpV3SendAndWait:

    def test_timeout_returns_timeout_flag(self, two_peers):
        _, _ = two_peers
        start = mcp_server.writ_start_conversation(
            to_repo="peer-repo", goal="wait test", message="hello",
        )

        with patch("asyncio.sleep", return_value=None):
            result = asyncio.run(mcp_server.writ_send_and_wait(
                conv_id=start["conv_id"],
                message="waiting...",
                poll_interval=1,
                timeout=2,
            ))
        assert result.get("timeout") is True

    def test_detects_peer_response(self, two_peers):
        repo_dir, _ = two_peers
        from writ.core import messaging

        start = mcp_server.writ_start_conversation(
            to_repo="peer-repo", goal="respond test",
            message="question",
        )
        conv_id = start["conv_id"]

        call_count = 0

        async def mock_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                found = messaging.find_conversation(conv_id)
                if found:
                    path, _ = found
                    messaging.append_message(
                        path,
                        agent="peer-agent",
                        repo="peer-repo",
                        content="Here is my response",
                    )

        with patch("asyncio.sleep", side_effect=mock_sleep):
            result = asyncio.run(mcp_server.writ_send_and_wait(
                conv_id=conv_id,
                message="please respond",
                poll_interval=1,
                timeout=30,
            ))
        assert "response" in result
        assert "Here is my response" in result["response"]
        assert result["from_repo"] == "peer-repo"


class TestMcpV3CheckInbox:

    def test_empty_inbox(self, initialized_project: Path):
        save_instruction(
            InstructionConfig(name="dev", instructions="Dev.")
        )
        result = mcp_server.writ_check_inbox()
        assert result == []

    def test_detects_unread_message(self, two_peers):
        repo_dir, _ = two_peers
        from writ.core import messaging

        start = mcp_server.writ_start_conversation(
            to_repo="peer-repo", goal="inbox test",
            message="outgoing",
        )
        found = messaging.find_conversation(start["conv_id"])
        assert found is not None
        path, _ = found
        messaging.append_message(
            path, agent="peer-agent", repo="peer-repo",
            content="incoming reply",
        )

        inbox = mcp_server.writ_check_inbox()
        assert len(inbox) >= 1
        item = next(
            i for i in inbox if i["conv_id"] == start["conv_id"]
        )
        assert "incoming reply" in item["last_message_preview"]
        assert item["peer"] == "peer-repo"

    def test_no_unread_when_last_is_self(self, two_peers):
        _, _ = two_peers
        mcp_server.writ_start_conversation(
            to_repo="peer-repo", goal="self test",
            message="I sent this",
        )
        inbox = mcp_server.writ_check_inbox()
        matching = [
            i for i in inbox if i["goal"] == "self test"
        ]
        assert len(matching) == 0


class TestMcpV3ReadConversation:

    def test_reads_full_history(self, two_peers):
        _, _ = two_peers
        start = mcp_server.writ_start_conversation(
            to_repo="peer-repo", goal="read test",
            message="msg one",
        )
        mcp_server.writ_send_message(
            conv_id=start["conv_id"], message="msg two",
        )
        result = mcp_server.writ_read_conversation(
            conv_id=start["conv_id"],
        )
        assert result["goal"] == "read test"
        assert len(result["messages"]) >= 2
        contents = [m["content"] for m in result["messages"]]
        assert "msg one" in contents
        assert "msg two" in contents

    def test_last_n_limits_messages(self, two_peers):
        _, _ = two_peers
        start = mcp_server.writ_start_conversation(
            to_repo="peer-repo", goal="limit test",
            message="first",
        )
        mcp_server.writ_send_message(
            conv_id=start["conv_id"], message="second",
        )
        mcp_server.writ_send_message(
            conv_id=start["conv_id"], message="third",
        )
        result = mcp_server.writ_read_conversation(
            conv_id=start["conv_id"], last_n=1,
        )
        assert len(result["messages"]) == 1
        assert result["messages"][0]["content"] == "third"

    def test_not_found(self, initialized_project: Path):
        result = mcp_server.writ_read_conversation(
            conv_id="conv-ghost",
        )
        assert "error" in result


class TestMcpV3CompleteConversation:

    def test_marks_completed(self, two_peers):
        _, _ = two_peers
        start = mcp_server.writ_start_conversation(
            to_repo="peer-repo", goal="complete test",
            message="let us finish",
        )
        result = mcp_server.writ_complete_conversation(
            conv_id=start["conv_id"],
            summary="We agreed on the design.",
        )
        assert result["status"] == "completed"
        assert "agreed" in result["summary"]

        read = mcp_server.writ_read_conversation(
            conv_id=start["conv_id"],
        )
        assert read["status"] == "completed"

    def test_not_found(self, initialized_project: Path):
        result = mcp_server.writ_complete_conversation(
            conv_id="conv-nope", summary="n/a",
        )
        assert "error" in result
