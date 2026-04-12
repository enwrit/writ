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
        result = mcp_server.writ_list()
        names = {r["name"] for r in result}
        assert "dev" in names
        assert "rule1" in names
        assert any(r["task_type"] == "agent" for r in result)
        assert any(r["task_type"] == "rule" for r in result)

    def test_get_instruction_found(self, initialized_project: Path):
        save_instruction(
            InstructionConfig(name="reviewer", instructions="Review code carefully.")
        )
        result = mcp_server.writ_get("reviewer")
        assert "reviewer" in result
        assert "Review code carefully" in result

    def test_get_instruction_not_found(self, initialized_project: Path):
        result = mcp_server.writ_get("nonexistent")
        assert "not found" in result.lower()


# ---------------------------------------------------------------------------
# V2 Tools
# ---------------------------------------------------------------------------

class TestMcpV2Compose:
    """Test writ_compose tool."""

    def test_compose_returns_instructions(self, initialized_project: Path):
        save_instruction(
            InstructionConfig(name="dev", instructions="You are a Python developer.")
        )
        result = mcp_server.writ_compose("dev")
        assert "Python developer" in result

    def test_compose_includes_project_context(self, initialized_project: Path):
        save_project_context("# My Project\nPython + FastAPI")
        save_instruction(
            InstructionConfig(name="dev", instructions="Build features.")
        )
        result = mcp_server.writ_compose("dev")
        assert "My Project" in result
        assert "Build features" in result

    def test_compose_not_found(self, initialized_project: Path):
        result = mcp_server.writ_compose("ghost")
        assert "not found" in result.lower()


class TestMcpV2Search:
    """Test writ_search tool."""

    def test_search_by_name(self, initialized_project: Path):
        save_instruction(InstructionConfig(name="react-dev", description="React developer"))
        save_instruction(InstructionConfig(name="py-lint", description="Python linter"))
        results = mcp_server.writ_search("react")
        assert len(results) == 1
        assert results[0]["name"] == "react-dev"

    def test_search_by_tag(self, initialized_project: Path):
        save_instruction(InstructionConfig(name="a1", tags=["security", "review"]))
        save_instruction(InstructionConfig(name="a2", tags=["typescript"]))
        results = mcp_server.writ_search("security")
        assert len(results) == 1
        assert results[0]["name"] == "a1"

    def test_search_no_match(self, initialized_project: Path):
        save_instruction(InstructionConfig(name="dev"))
        results = mcp_server.writ_search("zzz_no_match")
        assert len(results) == 0


class TestMcpV2Add:
    """Test writ_add tool."""

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
            result = mcp_server.writ_add("test-rule")
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
            mock_client_fn.return_value.hub_search.return_value = []
            result = mcp_server.writ_add("nonexistent")
        assert "error" in result
        assert "not found" in result["error"]

    def test_install_already_exists(self, initialized_project: Path):
        save_instruction(InstructionConfig(name="existing", instructions="Hi"))
        result = mcp_server.writ_add("existing")
        assert "error" in result
        assert "already exists" in result["error"]


# ---------------------------------------------------------------------------
# Removed tools -- verify they no longer exist
# ---------------------------------------------------------------------------

class TestRemovedTools:
    """Verify that redundant tools were removed from MCP server."""

    def test_no_read_file(self):
        assert not hasattr(mcp_server, "writ_read_file")

    def test_no_list_files(self):
        assert not hasattr(mcp_server, "writ_list_files")

    def test_no_project_context(self):
        assert not hasattr(mcp_server, "writ_project_context")


# ---------------------------------------------------------------------------
# CLI + Formatter
# ---------------------------------------------------------------------------

class TestMcpCommand:
    """Test the writ mcp CLI commands."""

    def test_mcp_help(self):
        result = runner.invoke(app, ["mcp", "--help"])
        assert result.exit_code == 0
        assert "serve" in result.output
        assert "install" in result.output
        assert "uninstall" in result.output

    def test_mcp_serve_help(self):
        result = runner.invoke(app, ["mcp", "serve", "--help"])
        assert result.exit_code == 0
        assert "writ_compose" in result.output
        assert "--slim" in result.output

    def test_mcp_install_help(self):
        result = runner.invoke(app, ["mcp", "install", "--help"])
        assert result.exit_code == 0
        assert "Cursor" in result.output
        assert "Claude" in result.output
        assert "slim" in result.output.lower()


class TestMcpInstall:
    """Test writ mcp install -- auto-configures MCP in detected IDEs."""

    def test_install_creates_cursor_config(self, initialized_project: Path):
        (initialized_project / ".cursor").mkdir(exist_ok=True)
        result = runner.invoke(app, ["mcp", "install"])
        assert result.exit_code == 0
        assert "Cursor" in result.output
        assert "slim mode" in result.output.lower()
        config = json.loads(
            (initialized_project / ".cursor" / "mcp.json").read_text(encoding="utf-8")
        )
        assert "writ" in config["mcpServers"]
        assert "--slim" in config["mcpServers"]["writ"]["args"]

    def test_install_creates_vscode_config(self, initialized_project: Path):
        (initialized_project / ".vscode").mkdir(exist_ok=True)
        result = runner.invoke(app, ["mcp", "install"])
        assert result.exit_code == 0
        assert "VS Code" in result.output
        config = json.loads(
            (initialized_project / ".vscode" / "mcp.json").read_text(encoding="utf-8")
        )
        assert "writ" in config["servers"]
        assert config["servers"]["writ"]["type"] == "stdio"
        assert "--slim" in config["servers"]["writ"]["args"]

    def test_install_creates_claude_code_config(self, initialized_project: Path):
        (initialized_project / ".claude").mkdir(exist_ok=True)
        result = runner.invoke(app, ["mcp", "install"])
        assert result.exit_code == 0
        assert "Claude Code" in result.output
        config = json.loads(
            (initialized_project / ".mcp.json").read_text(encoding="utf-8")
        )
        assert "writ" in config["mcpServers"]

    def test_install_creates_kiro_config(self, initialized_project: Path):
        (initialized_project / ".kiro").mkdir(exist_ok=True)
        result = runner.invoke(app, ["mcp", "install"])
        assert result.exit_code == 0
        assert "Kiro" in result.output
        config = json.loads(
            (initialized_project / ".kiro" / "settings" / "mcp.json").read_text(
                encoding="utf-8"
            )
        )
        assert "writ" in config["mcpServers"]

    def test_install_preserves_existing_servers(self, initialized_project: Path):
        cursor_dir = initialized_project / ".cursor"
        cursor_dir.mkdir(exist_ok=True)
        mcp_json = cursor_dir / "mcp.json"
        mcp_json.write_text(
            json.dumps({"mcpServers": {"github": {
                "command": "npx", "args": ["-y", "server-github"],
            }}}),
            encoding="utf-8",
        )
        result = runner.invoke(app, ["mcp", "install"])
        assert result.exit_code == 0
        config = json.loads(mcp_json.read_text(encoding="utf-8"))
        assert "github" in config["mcpServers"]
        assert "writ" in config["mcpServers"]

    def test_install_detects_multiple_ides(self, initialized_project: Path):
        (initialized_project / ".cursor").mkdir(exist_ok=True)
        (initialized_project / ".claude").mkdir(exist_ok=True)
        (initialized_project / ".kiro").mkdir(exist_ok=True)
        result = runner.invoke(app, ["mcp", "install"])
        assert result.exit_code == 0
        assert "Cursor" in result.output
        assert "Claude Code" in result.output
        assert "Kiro" in result.output

    def test_install_no_ide_detected(self, initialized_project: Path):
        result = runner.invoke(app, ["mcp", "install"])
        assert result.exit_code == 0
        assert "No IDE directories detected" in result.output

    def test_install_idempotent(self, initialized_project: Path):
        (initialized_project / ".cursor").mkdir(exist_ok=True)
        runner.invoke(app, ["mcp", "install"])
        runner.invoke(app, ["mcp", "install"])
        config = json.loads(
            (initialized_project / ".cursor" / "mcp.json").read_text(encoding="utf-8")
        )
        assert len(config["mcpServers"]) == 1
        assert "writ" in config["mcpServers"]


class TestMcpUninstall:
    """Test writ mcp uninstall -- removes writ MCP config from IDEs."""

    def test_uninstall_removes_cursor_config(self, initialized_project: Path):
        (initialized_project / ".cursor").mkdir(exist_ok=True)
        runner.invoke(app, ["mcp", "install"])
        config_path = initialized_project / ".cursor" / "mcp.json"
        assert "writ" in json.loads(config_path.read_text(encoding="utf-8"))["mcpServers"]

        result = runner.invoke(app, ["mcp", "uninstall"])
        assert result.exit_code == 0
        assert "Cursor" in result.output

        config = json.loads(config_path.read_text(encoding="utf-8"))
        assert "writ" not in config["mcpServers"]

    def test_uninstall_preserves_other_servers(self, initialized_project: Path):
        cursor_dir = initialized_project / ".cursor"
        cursor_dir.mkdir(exist_ok=True)
        mcp_json = cursor_dir / "mcp.json"
        mcp_json.write_text(
            json.dumps({"mcpServers": {
                "github": {"command": "npx", "args": ["-y", "server-github"]},
                "writ": {"command": "writ", "args": ["mcp", "serve", "--slim"]},
            }}),
            encoding="utf-8",
        )
        result = runner.invoke(app, ["mcp", "uninstall"])
        assert result.exit_code == 0
        config = json.loads(mcp_json.read_text(encoding="utf-8"))
        assert "github" in config["mcpServers"]
        assert "writ" not in config["mcpServers"]

    def test_uninstall_no_configs_found(self, initialized_project: Path):
        result = runner.invoke(app, ["mcp", "uninstall"])
        assert result.exit_code == 0
        assert "No writ MCP configs found" in result.output

    def test_uninstall_multiple_ides(self, initialized_project: Path):
        (initialized_project / ".cursor").mkdir(exist_ok=True)
        (initialized_project / ".claude").mkdir(exist_ok=True)
        runner.invoke(app, ["mcp", "install"])

        result = runner.invoke(app, ["mcp", "uninstall"])
        assert result.exit_code == 0
        assert "Cursor" in result.output
        assert "Claude Code" in result.output


class TestMcpCommandResolution:
    """Test _resolve_writ_command path resolution logic."""

    def test_prefers_uvx(self, monkeypatch):
        import sys

        from writ.commands import mcp as mcp_cmd
        monkeypatch.setattr("shutil.which", lambda cmd: f"/usr/bin/{cmd}" if cmd == "uvx" else None)
        monkeypatch.setattr(sys, "prefix", "/usr")
        monkeypatch.setattr(sys, "base_prefix", "/usr")
        entry = mcp_cmd._resolve_writ_command(slim=True)
        assert entry["command"] == "uvx"
        assert "enwrit" in entry["args"]
        assert "--slim" in entry["args"]

    def test_uses_writ_when_not_in_venv(self, monkeypatch):
        import sys

        from writ.commands import mcp as mcp_cmd
        monkeypatch.setattr("shutil.which", lambda cmd: None if cmd == "uvx" else f"/usr/bin/{cmd}")
        monkeypatch.setattr(sys, "prefix", "/usr")
        monkeypatch.setattr(sys, "base_prefix", "/usr")
        entry = mcp_cmd._resolve_writ_command(slim=False)
        assert entry["command"] == "writ"
        assert "--slim" not in entry["args"]

    def test_uses_python_path_in_venv(self, monkeypatch):
        import sys

        from writ.commands import mcp as mcp_cmd
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        monkeypatch.setattr(sys, "prefix", "/home/user/myenv")
        monkeypatch.setattr(sys, "base_prefix", "/usr")
        entry = mcp_cmd._resolve_writ_command(slim=True)
        assert entry["args"][0] == "-m"
        assert "writ" in entry["args"]
        assert "--slim" in entry["args"]


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
        result = mcp_server.writ_chat_start(
            to_repo="peer-repo",
            goal="test goal",
            message="Hello peer!",
        )
        assert "conv_id" in result
        assert result["status"] == "started"
        assert result["file"].endswith(".md")

    def test_syncs_to_local_peer(self, two_peers):
        repo_dir, peer_dir = two_peers
        mcp_server.writ_chat_start(
            to_repo="peer-repo",
            goal="sync test",
            message="Should appear in peer",
        )
        peer_convs = list((peer_dir / ".writ" / "conversations").iterdir())
        assert len(peer_convs) == 1
        content = peer_convs[0].read_text(encoding="utf-8")
        assert "Should appear in peer" in content

    def test_unknown_peer_returns_error(self, initialized_project: Path):
        result = mcp_server.writ_chat_start(
            to_repo="nonexistent",
            goal="nope",
            message="hi",
        )
        assert "error" in result

    def test_returns_conv_id_format(self, two_peers):
        _, _ = two_peers
        result = mcp_server.writ_chat_start(
            to_repo="peer-repo",
            goal="id test",
            message="check id",
        )
        assert result["conv_id"].startswith("conv-")


class TestMcpV3SendMessage:

    def test_appends_message(self, two_peers):
        _, _ = two_peers
        start = mcp_server.writ_chat_start(
            to_repo="peer-repo", goal="chat", message="first",
        )
        result = mcp_server.writ_chat_send(
            conv_id=start["conv_id"], message="second message",
        )
        assert result["status"] == "sent"
        assert result["message_count"] >= 2

    def test_not_found(self, initialized_project: Path):
        result = mcp_server.writ_chat_send(
            conv_id="conv-nonexistent", message="hi",
        )
        assert "error" in result

    def test_rejects_completed_conversation(self, two_peers):
        _, _ = two_peers
        start = mcp_server.writ_chat_start(
            to_repo="peer-repo", goal="done", message="first",
        )
        mcp_server.writ_chat_end(
            conv_id=start["conv_id"], summary="all done",
        )
        result = mcp_server.writ_chat_send(
            conv_id=start["conv_id"], message="too late",
        )
        assert "error" in result


class TestMcpV3SendAndWait:

    def test_timeout_returns_timeout_flag(self, two_peers):
        _, _ = two_peers
        start = mcp_server.writ_chat_start(
            to_repo="peer-repo", goal="wait test", message="hello",
        )

        with patch("asyncio.sleep", return_value=None):
            result = asyncio.run(mcp_server.writ_chat_send_wait(
                conv_id=start["conv_id"],
                message="waiting...",
                poll_interval=1,
                timeout=2,
            ))
        assert result.get("timeout") is True

    def test_detects_peer_response(self, two_peers):
        repo_dir, _ = two_peers
        from writ.core import messaging

        start = mcp_server.writ_chat_start(
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
            result = asyncio.run(mcp_server.writ_chat_send_wait(
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
        result = mcp_server.writ_inbox()
        assert result == []

    def test_detects_unread_message(self, two_peers):
        repo_dir, _ = two_peers
        from writ.core import messaging

        start = mcp_server.writ_chat_start(
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

        inbox = mcp_server.writ_inbox()
        assert len(inbox) >= 1
        item = next(
            i for i in inbox if i["conv_id"] == start["conv_id"]
        )
        assert "incoming reply" in item["last_message_preview"]
        assert item["peer"] == "peer-repo"

    def test_no_unread_when_last_is_self(self, two_peers):
        _, _ = two_peers
        mcp_server.writ_chat_start(
            to_repo="peer-repo", goal="self test",
            message="I sent this",
        )
        inbox = mcp_server.writ_inbox()
        matching = [
            i for i in inbox if i["goal"] == "self test"
        ]
        assert len(matching) == 0


class TestMcpV3ReadConversation:

    def test_reads_full_history(self, two_peers):
        _, _ = two_peers
        start = mcp_server.writ_chat_start(
            to_repo="peer-repo", goal="read test",
            message="msg one",
        )
        mcp_server.writ_chat_send(
            conv_id=start["conv_id"], message="msg two",
        )
        result = mcp_server.writ_chat_read(
            conv_id=start["conv_id"],
        )
        assert result["goal"] == "read test"
        assert len(result["messages"]) >= 2
        contents = [m["content"] for m in result["messages"]]
        assert "msg one" in contents
        assert "msg two" in contents

    def test_last_n_limits_messages(self, two_peers):
        _, _ = two_peers
        start = mcp_server.writ_chat_start(
            to_repo="peer-repo", goal="limit test",
            message="first",
        )
        mcp_server.writ_chat_send(
            conv_id=start["conv_id"], message="second",
        )
        mcp_server.writ_chat_send(
            conv_id=start["conv_id"], message="third",
        )
        result = mcp_server.writ_chat_read(
            conv_id=start["conv_id"], last_n=1,
        )
        assert len(result["messages"]) == 1
        assert result["messages"][0]["content"] == "third"

    def test_not_found(self, initialized_project: Path):
        result = mcp_server.writ_chat_read(
            conv_id="conv-ghost",
        )
        assert "error" in result


class TestMcpV3CompleteConversation:

    def test_marks_completed(self, two_peers):
        _, _ = two_peers
        start = mcp_server.writ_chat_start(
            to_repo="peer-repo", goal="complete test",
            message="let us finish",
        )
        result = mcp_server.writ_chat_end(
            conv_id=start["conv_id"],
            summary="We agreed on the design.",
        )
        assert result["status"] == "completed"
        assert "agreed" in result["summary"]

        read = mcp_server.writ_chat_read(
            conv_id=start["conv_id"],
        )
        assert read["status"] == "completed"

    def test_not_found(self, initialized_project: Path):
        result = mcp_server.writ_chat_end(
            conv_id="conv-nope", summary="n/a",
        )
        assert "error" in result

    def test_default_summary(self, two_peers):
        _, _ = two_peers
        start = mcp_server.writ_chat_start(
            to_repo="peer-repo", goal="default summary test",
            message="quick test",
        )
        result = mcp_server.writ_chat_end(conv_id=start["conv_id"])
        assert result["status"] == "completed"
        assert result["summary"] == "Conversation ended"


# ---------------------------------------------------------------------------
# V3 Peer management
# ---------------------------------------------------------------------------


class TestMcpPeerTools:

    def test_add_local_peer(self, initialized_project: Path):
        result = mcp_server.writ_peers_add(
            name="test-peer", path=str(initialized_project),
        )
        assert result["status"] == "added"
        assert result["transport"] == "local"
        assert result["name"] == "test-peer"

    def test_add_remote_peer(self, initialized_project: Path):
        result = mcp_server.writ_peers_add(
            name="remote-peer", remote="some-user",
        )
        assert result["status"] == "added"
        assert result["transport"] == "remote"

    def test_add_peer_no_path_or_remote(self, initialized_project: Path):
        result = mcp_server.writ_peers_add(name="bad-peer")
        assert "error" in result

    def test_add_duplicate_peer(self, initialized_project: Path):
        mcp_server.writ_peers_add(name="dup-peer", path="/tmp/fake")
        result = mcp_server.writ_peers_add(name="dup-peer", path="/tmp/other")
        assert "error" in result
        assert "already" in result["error"].lower()

    def test_list_peers(self, initialized_project: Path):
        mcp_server.writ_peers_add(name="p1", path="/tmp/a")
        mcp_server.writ_peers_add(name="p2", remote="user2")
        result = mcp_server.writ_peers_list()
        names = {p["name"] for p in result}
        assert "p1" in names
        assert "p2" in names

    def test_remove_peer(self, initialized_project: Path):
        mcp_server.writ_peers_add(name="to-remove", path="/tmp/x")
        result = mcp_server.writ_peers_remove("to-remove")
        assert result["status"] == "removed"
        listing = mcp_server.writ_peers_list()
        assert not any(p["name"] == "to-remove" for p in listing)

    def test_remove_nonexistent(self, initialized_project: Path):
        result = mcp_server.writ_peers_remove("nope")
        assert "error" in result


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


class TestIdentity:

    def test_get_identity_generates_and_persists(self, tmp_global_writ, monkeypatch):
        monkeypatch.setattr("writ.core.auth._fetch_remote_identity", lambda _: None)
        from writ.core.auth import get_identity
        identity = get_identity()
        assert identity
        assert "-" in identity
        identity2 = get_identity()
        assert identity == identity2

    def test_get_identity_uses_stored(self, tmp_global_writ):
        from writ.core import store
        from writ.core.auth import get_identity
        config = store.load_global_config()
        config.identity = "axel-custom"
        store.save_global_config(config)
        assert get_identity() == "axel-custom"


# ---------------------------------------------------------------------------
# V4 Tools -- Knowledge (reviews + threads)
# ---------------------------------------------------------------------------


class TestMcpV4ReviewInstruction:

    def test_requires_login(self, initialized_project, monkeypatch):
        monkeypatch.setattr("writ.integrations.mcp_server.auth.is_logged_in", lambda: False)
        result = mcp_server.writ_review(
            instruction_name="test-agent", rating=4.0, summary="Good",
        )
        assert "error" in result
        assert "login" in result["error"].lower()

    def test_submit_success(self, initialized_project, monkeypatch):
        monkeypatch.setattr("writ.integrations.mcp_server.auth.is_logged_in", lambda: True)
        save_instruction(InstructionConfig(name="dev", instructions="Dev agent."))
        mock_client = type("MockClient", (), {
            "submit_review": lambda self, *a, **kw: {"id": "rev-1", "rating": 4.0},
        })()
        monkeypatch.setattr(mcp_server, "_registry_client", lambda: mock_client)
        result = mcp_server.writ_review(
            instruction_name="dev", rating=4.0, summary="Great",
        )
        assert "id" in result

    def test_submit_failure(self, initialized_project, monkeypatch):
        monkeypatch.setattr("writ.integrations.mcp_server.auth.is_logged_in", lambda: True)
        save_instruction(InstructionConfig(name="dev", instructions="Dev agent."))
        mock_client = type("MockClient", (), {
            "submit_review": lambda self, *a, **kw: None,
        })()
        monkeypatch.setattr(mcp_server, "_registry_client", lambda: mock_client)
        result = mcp_server.writ_review(
            instruction_name="dev", rating=3.0, summary="OK",
        )
        assert "error" in result


class TestMcpV4SearchThreads:

    def test_search_empty(self, initialized_project, monkeypatch):
        mock_client = type("MockClient", (), {
            "search_threads": lambda self, **kw: [],
        })()
        monkeypatch.setattr(mcp_server, "_registry_client", lambda: mock_client)
        result = mcp_server.writ_threads_list()
        assert result == []

    def test_search_with_results(self, initialized_project, monkeypatch):
        mock_client = type("MockClient", (), {
            "search_threads": lambda self, **kw: [
                {"id": "t1", "title": "Best patterns", "status": "open"},
            ],
        })()
        monkeypatch.setattr(mcp_server, "_registry_client", lambda: mock_client)
        result = mcp_server.writ_threads_list(query="patterns")
        assert len(result) == 1
        assert result[0]["title"] == "Best patterns"

    def test_search_with_filters(self, initialized_project, monkeypatch):
        calls = []
        mock_client = type("MockClient", (), {
            "search_threads": lambda self, **kw: (calls.append(kw), [])[1],
        })()
        monkeypatch.setattr(mcp_server, "_registry_client", lambda: mock_client)
        mcp_server.writ_threads_list(thread_type="research", status="open", limit=5)
        assert calls[0]["thread_type"] == "research"
        assert calls[0]["status"] == "open"
        assert calls[0]["limit"] == 5


class TestMcpV4StartThread:

    def test_requires_login(self, initialized_project, monkeypatch):
        monkeypatch.setattr("writ.integrations.mcp_server.auth.is_logged_in", lambda: False)
        result = mcp_server.writ_threads_start(
            title="Test", goal="Test", thread_type="research", first_message="Hello",
        )
        assert "error" in result
        assert "login" in result["error"].lower()

    def test_start_success(self, initialized_project, monkeypatch):
        monkeypatch.setattr("writ.integrations.mcp_server.auth.is_logged_in", lambda: True)
        save_instruction(InstructionConfig(name="dev", instructions="Agent."))
        mock_client = type("MockClient", (), {
            "start_thread": lambda self, **kw: {"id": "t-new", "title": kw["title"]},
        })()
        monkeypatch.setattr(mcp_server, "_registry_client", lambda: mock_client)
        result = mcp_server.writ_threads_start(
            title="New Thread", goal="Discuss X",
            thread_type="research", first_message="Let's go",
        )
        assert result["id"] == "t-new"

    def test_start_failure(self, initialized_project, monkeypatch):
        monkeypatch.setattr("writ.integrations.mcp_server.auth.is_logged_in", lambda: True)
        save_instruction(InstructionConfig(name="dev", instructions="Agent."))
        mock_client = type("MockClient", (), {
            "start_thread": lambda self, **kw: None,
        })()
        monkeypatch.setattr(mcp_server, "_registry_client", lambda: mock_client)
        result = mcp_server.writ_threads_start(
            title="Fail", goal="Fail", thread_type="research", first_message="msg",
        )
        assert "error" in result


class TestMcpV4PostToThread:

    def test_requires_login(self, initialized_project, monkeypatch):
        monkeypatch.setattr("writ.integrations.mcp_server.auth.is_logged_in", lambda: False)
        result = mcp_server.writ_threads_post(thread_id="t-1", content="Hello")
        assert "error" in result

    def test_post_success(self, initialized_project, monkeypatch):
        monkeypatch.setattr("writ.integrations.mcp_server.auth.is_logged_in", lambda: True)
        save_instruction(InstructionConfig(name="dev", instructions="Agent."))
        mock_client = type("MockClient", (), {
            "post_to_thread": lambda self, *a, **kw: {"id": "msg-1"},
        })()
        monkeypatch.setattr(mcp_server, "_registry_client", lambda: mock_client)
        result = mcp_server.writ_threads_post(
            thread_id="t-1", content="Found something",
            message_type="finding",
        )
        assert "id" in result


class TestMcpV4ResolveThread:

    def test_requires_login(self, initialized_project, monkeypatch):
        monkeypatch.setattr("writ.integrations.mcp_server.auth.is_logged_in", lambda: False)
        result = mcp_server.writ_threads_resolve(
            thread_id="t-1", conclusion="Done",
        )
        assert "error" in result

    def test_resolve_success(self, initialized_project, monkeypatch):
        monkeypatch.setattr("writ.integrations.mcp_server.auth.is_logged_in", lambda: True)
        mock_client = type("MockClient", (), {
            "resolve_thread": lambda self, *a, **kw: {"status": "resolved"},
        })()
        monkeypatch.setattr(mcp_server, "_registry_client", lambda: mock_client)
        result = mcp_server.writ_threads_resolve(
            thread_id="t-1", conclusion="Pattern X is best",
        )
        assert result["status"] == "resolved"


# ---------------------------------------------------------------------------
# V5 Tools -- Approvals (human-in-the-loop)
# ---------------------------------------------------------------------------


class TestMcpV5RequestApproval:

    def test_requires_login(self, initialized_project, monkeypatch):
        monkeypatch.setattr("writ.integrations.mcp_server.auth.is_logged_in", lambda: False)
        monkeypatch.setattr("writ.core.auth.is_logged_in", lambda: False)
        result = mcp_server.writ_approvals_create(
            action_type="deploy", description="Deploy v2",
        )
        assert "error" in result
        assert "login" in result["error"].lower()

    def test_create_success(self, initialized_project, monkeypatch):
        monkeypatch.setattr("writ.core.auth.is_logged_in", lambda: True)
        save_instruction(InstructionConfig(name="deployer", instructions="Deploys."))
        mock_client = type("MockClient", (), {
            "create_approval": lambda self, **kw: {
                "id": "apr-1", "status": "pending",
                "expires_at": "2026-04-04T00:00:00Z",
            },
        })()
        monkeypatch.setattr(mcp_server, "_registry_client", lambda: mock_client)
        result = mcp_server.writ_approvals_create(
            action_type="deploy",
            description="Deploy to production",
            reasoning="All tests pass",
            urgency="high",
        )
        assert result["id"] == "apr-1"
        assert result["console_url"] == "https://enwrit.com/console?approval=apr-1"

    def test_create_with_context_json(self, initialized_project, monkeypatch):
        monkeypatch.setattr("writ.core.auth.is_logged_in", lambda: True)
        save_instruction(InstructionConfig(name="dev", instructions="Agent."))
        calls = []
        mock_client = type("MockClient", (), {
            "create_approval": lambda self, **kw: (calls.append(kw), {"id": "apr-2"})[1],
        })()
        monkeypatch.setattr(mcp_server, "_registry_client", lambda: mock_client)
        mcp_server.writ_approvals_create(
            action_type="shell_command",
            description="Run npm install",
            context='{"command": "npm install express"}',
        )
        assert calls[0]["context"] == {"command": "npm install express"}

    def test_invalid_context_json(self, initialized_project, monkeypatch):
        monkeypatch.setattr("writ.core.auth.is_logged_in", lambda: True)
        save_instruction(InstructionConfig(name="dev", instructions="Agent."))
        calls = []
        mock_client = type("MockClient", (), {
            "create_approval": lambda self, **kw: (calls.append(kw), {"id": "apr-3"})[1],
        })()
        monkeypatch.setattr(mcp_server, "_registry_client", lambda: mock_client)
        mcp_server.writ_approvals_create(
            action_type="deploy", description="test",
            context="not-json",
        )
        assert calls[0]["context"] == {"raw": "not-json"}


class TestMcpV5CheckApproval:

    def test_requires_login(self, initialized_project, monkeypatch):
        monkeypatch.setattr("writ.core.auth.is_logged_in", lambda: False)
        result = mcp_server.writ_approvals_check(approval_id="apr-1")
        assert "error" in result

    def test_check_pending(self, initialized_project, monkeypatch):
        monkeypatch.setattr("writ.core.auth.is_logged_in", lambda: True)
        mock_client = type("MockClient", (), {
            "get_approval": lambda self, aid: {"id": aid, "status": "pending"},
        })()
        monkeypatch.setattr(mcp_server, "_registry_client", lambda: mock_client)
        result = mcp_server.writ_approvals_check(approval_id="apr-1")
        assert result["status"] == "pending"

    def test_check_approved(self, initialized_project, monkeypatch):
        monkeypatch.setattr("writ.core.auth.is_logged_in", lambda: True)
        mock_client = type("MockClient", (), {
            "get_approval": lambda self, aid: {
                "id": aid, "status": "approved", "resolved_at": "2026-04-03T12:00:00Z",
            },
        })()
        monkeypatch.setattr(mcp_server, "_registry_client", lambda: mock_client)
        result = mcp_server.writ_approvals_check(approval_id="apr-1")
        assert result["status"] == "approved"


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------


class TestMcpResources:

    def test_instruction_resource_found(self, initialized_project):
        save_instruction(InstructionConfig(name="my-agent", instructions="My instructions."))
        result = mcp_server.instruction_resource("my-agent")
        assert "my-agent" in result
        assert "My instructions" in result

    def test_instruction_resource_not_found(self, initialized_project):
        result = mcp_server.instruction_resource("nonexistent")
        assert "not found" in result.lower()

    def test_project_context_resource(self, initialized_project):
        save_project_context("# My Project\nPython + React")
        result = mcp_server.project_context_resource()
        assert "My Project" in result

    def test_project_context_resource_empty(self, initialized_project):
        result = mcp_server.project_context_resource()
        assert "no project context" in result.lower()
