"""Tests for agent-to-agent messaging (V3): conversations, peers, attachments."""

from __future__ import annotations

from pathlib import Path

import pytest

from writ.core.models import (
    AutoRespondTier,
    Conversation,
    ConversationStatus,
    PeerConfig,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def initialized_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a minimal .writ/ project in a temp dir."""
    monkeypatch.chdir(tmp_path)
    from writ.core.store import init_project_store

    init_project_store()
    return tmp_path


@pytest.fixture()
def peer_project(tmp_path: Path) -> Path:
    """Create a second temp dir representing a peer repo."""
    peer = tmp_path / "peer-repo"
    peer.mkdir()
    (peer / ".writ").mkdir()
    (peer / ".writ" / "conversations").mkdir(parents=True)
    return peer


# ---------------------------------------------------------------------------
# Conversation lifecycle
# ---------------------------------------------------------------------------

class TestConversationLifecycle:
    """Create, append, read, complete, resume conversations."""

    def test_create_conversation(self, initialized_project: Path):
        from writ.core.messaging import conversations_dir, create_conversation

        conv = create_conversation(
            peer_repo="research-repo",
            goal="Design auth system",
            local_agent="coding-agent",
            local_repo="writ-cli",
        )
        assert conv.id.startswith("conv-")
        assert conv.goal == "Design auth system"
        assert conv.status == ConversationStatus.ACTIVE
        assert len(conv.participants) == 2

        md_files = list(conversations_dir().glob("*.md"))
        assert len(md_files) == 1

    def test_append_and_load(self, initialized_project: Path):
        from writ.core.messaging import (
            append_message,
            conversations_dir,
            create_conversation,
            load_conversation,
        )

        create_conversation(
            peer_repo="research",
            goal="test append",
            local_agent="agent-a",
            local_repo="repo-a",
        )
        conv_path = list(conversations_dir().glob("*.md"))[0]

        msg = append_message(
            conv_path,
            agent="agent-a",
            repo="repo-a",
            content="Hello from repo A!",
        )
        assert msg.id == "msg-001"
        assert msg.content == "Hello from repo A!"

        loaded = load_conversation(conv_path)
        assert loaded is not None
        assert len(loaded.messages) == 1
        assert loaded.messages[0].content == "Hello from repo A!"
        assert loaded.messages[0].author_agent == "agent-a"

    def test_multi_turn_conversation(self, initialized_project: Path):
        from writ.core.messaging import (
            append_message,
            conversations_dir,
            create_conversation,
            load_conversation,
        )

        create_conversation(
            peer_repo="peer",
            goal="multi-turn",
            local_agent="a",
            local_repo="repo-a",
        )
        path = list(conversations_dir().glob("*.md"))[0]

        append_message(path, agent="a", repo="repo-a", content="Turn 1")
        append_message(path, agent="b", repo="repo-b", content="Turn 2")
        append_message(path, agent="a", repo="repo-a", content="Turn 3")

        conv = load_conversation(path)
        assert conv is not None
        assert len(conv.messages) == 3
        assert conv.messages[0].id == "msg-001"
        assert conv.messages[1].id == "msg-002"
        assert conv.messages[2].id == "msg-003"
        assert conv.messages[1].author_repo == "repo-b"

    def test_complete_conversation(self, initialized_project: Path):
        from writ.core.messaging import (
            complete_conversation,
            conversations_dir,
            create_conversation,
            load_conversation,
        )

        create_conversation(
            peer_repo="peer", goal="complete-test",
            local_agent="a", local_repo="repo",
        )
        path = list(conversations_dir().glob("*.md"))[0]

        complete_conversation(path, "We agreed on the design.")

        conv = load_conversation(path)
        assert conv is not None
        assert conv.status == ConversationStatus.COMPLETED

    def test_update_status_resume(self, initialized_project: Path):
        from writ.core.messaging import (
            conversations_dir,
            create_conversation,
            load_conversation,
            update_status,
        )

        create_conversation(
            peer_repo="peer", goal="status-test",
            local_agent="a", local_repo="repo",
        )
        path = list(conversations_dir().glob("*.md"))[0]

        update_status(path, ConversationStatus.PAUSED)
        conv = load_conversation(path)
        assert conv is not None
        assert conv.status == ConversationStatus.PAUSED

        update_status(path, ConversationStatus.ACTIVE)
        conv = load_conversation(path)
        assert conv is not None
        assert conv.status == ConversationStatus.ACTIVE

    def test_list_and_find_conversations(self, initialized_project: Path):
        from writ.core.messaging import (
            create_conversation,
            find_conversation,
            list_conversations,
        )

        c1 = create_conversation(
            peer_repo="peer-a", goal="goal-a",
            local_agent="a", local_repo="r",
        )
        c2 = create_conversation(
            peer_repo="peer-b", goal="goal-b",
            local_agent="a", local_repo="r",
        )

        convs = list_conversations()
        assert len(convs) == 2

        found = find_conversation(c1.id)
        assert found is not None
        assert found[1].goal == "goal-a"

        found2 = find_conversation(c2.id)
        assert found2 is not None
        assert found2[1].goal == "goal-b"

        assert find_conversation("conv-nonexistent") is None


# ---------------------------------------------------------------------------
# File attachments
# ---------------------------------------------------------------------------

class TestAttachments:
    """File embedding and blocklist enforcement."""

    def test_embed_text_file(self, initialized_project: Path):
        from writ.core.messaging import embed_files

        (initialized_project / "hello.py").write_text("print('hi')", encoding="utf-8")
        blocks = embed_files(["hello.py"], repo_root=initialized_project)
        assert len(blocks) == 1
        assert '<attached file="hello.py">' in blocks[0]
        assert "print('hi')" in blocks[0]

    def test_blocklist_env_file(self, initialized_project: Path):
        from writ.core.messaging import embed_files

        (initialized_project / ".env").write_text("SECRET=123", encoding="utf-8")
        blocks = embed_files([".env"], repo_root=initialized_project)
        assert len(blocks) == 1
        assert 'blocked="true"' in blocks[0]

    def test_blocklist_key_file(self, initialized_project: Path):
        from writ.core.messaging import embed_files

        (initialized_project / "server.key").write_text("PRIVATE KEY", encoding="utf-8")
        blocks = embed_files(["server.key"], repo_root=initialized_project)
        assert 'blocked="true"' in blocks[0]

    def test_nonexistent_file(self, initialized_project: Path):
        from writ.core.messaging import embed_files

        blocks = embed_files(["does-not-exist.txt"], repo_root=initialized_project)
        assert 'error="file not found"' in blocks[0]

    def test_message_with_attachments(self, initialized_project: Path):
        from writ.core.messaging import (
            append_message,
            conversations_dir,
            create_conversation,
            load_conversation,
        )

        (initialized_project / "plan.md").write_text("# Plan\nDo the thing.", encoding="utf-8")
        create_conversation(
            peer_repo="peer", goal="attach-test",
            local_agent="a", local_repo="r",
        )
        path = list(conversations_dir().glob("*.md"))[0]

        msg = append_message(
            path, agent="a", repo="r", content="See the plan.",
            attach_files=["plan.md"], repo_root=initialized_project,
        )
        assert len(msg.attachments) == 1
        assert "# Plan" in msg.attachments[0]

        conv = load_conversation(path)
        assert conv is not None
        assert len(conv.messages) == 1
        assert len(conv.messages[0].attachments) == 1


# ---------------------------------------------------------------------------
# Peers config
# ---------------------------------------------------------------------------

class TestPeers:
    """Peer management: add, list, remove, config parsing."""

    def test_add_and_load_peer(self, initialized_project: Path):
        from writ.core.peers import add_peer, load_peers

        add_peer("research", path="C:/projects/research")
        manifest = load_peers()
        assert "research" in manifest.peers
        peer = manifest.peers["research"]
        assert peer.path == "C:/projects/research"
        assert peer.transport == "local"
        assert peer.auto_respond == AutoRespondTier.OFF

    def test_add_remote_peer(self, initialized_project: Path):
        from writ.core.peers import add_peer, load_peers

        add_peer("cloud", remote="https://api.enwrit.com")
        manifest = load_peers()
        assert manifest.peers["cloud"].transport == "remote"
        assert manifest.peers["cloud"].remote == "https://api.enwrit.com"

    def test_remove_peer(self, initialized_project: Path):
        from writ.core.peers import add_peer, load_peers, remove_peer

        add_peer("temp", path="/tmp/repo")
        assert remove_peer("temp") is True
        assert "temp" not in load_peers().peers
        assert remove_peer("nonexistent") is False

    def test_auto_respond_tiers(self, initialized_project: Path):
        from writ.core.peers import add_peer, load_peers

        add_peer("full", path="/a", auto_respond=AutoRespondTier.FULL)
        add_peer("ro", path="/b", auto_respond=AutoRespondTier.READ_ONLY)
        manifest = load_peers()
        assert manifest.peers["full"].auto_respond == AutoRespondTier.FULL
        assert manifest.peers["ro"].auto_respond == AutoRespondTier.READ_ONLY

    def test_max_turns_config(self, initialized_project: Path):
        from writ.core.peers import add_peer, load_peers

        add_peer("limited", path="/c", max_turns=5)
        assert load_peers().peers["limited"].max_turns == 5

    def test_resolve_peer_conversations_dir(
        self, initialized_project: Path, peer_project: Path,
    ):
        from writ.core.peers import resolve_peer_conversations_dir

        peer = PeerConfig(
            name="test-peer",
            path=str(peer_project),
            transport="local",
        )
        result = resolve_peer_conversations_dir(peer)
        assert result is not None
        assert result == peer_project / ".writ" / "conversations"


# ---------------------------------------------------------------------------
# File locking
# ---------------------------------------------------------------------------

class TestFileLocking:
    """Cross-platform file locking basics."""

    def test_atomic_append(self, tmp_path: Path):
        from writ.core.file_io import atomic_append

        f = tmp_path / "test.md"
        f.write_text("initial\n", encoding="utf-8")
        atomic_append(f, "appended\n")
        content = f.read_text(encoding="utf-8")
        assert "initial\n" in content
        assert "appended\n" in content

    def test_file_lock_creates_lock_file(self, tmp_path: Path):
        from writ.core.file_io import file_lock

        f = tmp_path / "data.md"
        f.write_text("", encoding="utf-8")
        with file_lock(f):
            lock = f.with_suffix(".md.lock")
            assert lock.exists()


# ---------------------------------------------------------------------------
# Store update (conversations/ directory)
# ---------------------------------------------------------------------------

class TestStoreConversationsDir:
    """Verify init_project_store creates conversations/ directory."""

    def test_init_creates_conversations_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        from writ.core.store import init_project_store

        root = init_project_store()
        assert (root / "conversations").is_dir()


# ---------------------------------------------------------------------------
# CLI commands (smoke tests)
# ---------------------------------------------------------------------------

class TestChatCLI:
    """Smoke tests for writ chat commands via typer runner."""

    def test_chat_list_empty(self, initialized_project: Path):
        from typer.testing import CliRunner

        from writ.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["chat", "list"])
        assert result.exit_code == 0
        assert "No conversations" in result.output

    def test_peers_list_empty(self, initialized_project: Path):
        from typer.testing import CliRunner

        from writ.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["peers", "list"])
        assert result.exit_code == 0
        assert "No peers" in result.output

    def test_peers_add_and_list(self, initialized_project: Path, peer_project: Path):
        from typer.testing import CliRunner

        from writ.cli import app

        runner = CliRunner()
        result = runner.invoke(app, [
            "peers", "add", "test-peer", "--path", str(peer_project),
        ])
        assert result.exit_code == 0
        assert "Added peer" in result.output

        result = runner.invoke(app, ["peers", "list"])
        assert result.exit_code == 0
        assert "test-peer" in result.output

    def test_inbox_empty(self, initialized_project: Path):
        from typer.testing import CliRunner

        from writ.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["inbox"])
        assert result.exit_code == 0
        assert "No unread" in result.output

    def test_chat_start_requires_peer(self, initialized_project: Path):
        from typer.testing import CliRunner

        from writ.cli import app

        runner = CliRunner()
        result = runner.invoke(app, [
            "chat", "start", "--with", "nonexistent", "--goal", "test",
        ])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_full_chat_workflow(self, initialized_project: Path, peer_project: Path):
        from typer.testing import CliRunner

        from writ.cli import app
        from writ.core.peers import add_peer

        add_peer("peer", path=str(peer_project))

        runner = CliRunner()

        result = runner.invoke(app, [
            "chat", "start",
            "--with", "peer",
            "--goal", "Test conversation",
            "--message", "Hello peer!",
        ])
        assert result.exit_code == 0
        assert "Conversation started" in result.output

        result = runner.invoke(app, ["chat", "list"])
        assert result.exit_code == 0
        assert "Test conversation" in result.output

    def test_chat_send_with_diff(self, initialized_project: Path, peer_project: Path):
        from typer.testing import CliRunner

        from writ.cli import app
        from writ.core.peers import add_peer

        add_peer("peer", path=str(peer_project))

        runner = CliRunner()

        result = runner.invoke(app, [
            "chat", "start",
            "--with", "peer",
            "--goal", "Diff test",
            "--message", "Initial",
            "--no-invoke",
        ])
        assert result.exit_code == 0

        from writ.core.messaging import list_conversations
        convs = list_conversations()
        assert convs
        _, conv = convs[0]

        result = runner.invoke(app, [
            "chat", "send", conv.id, "Here are my changes",
            "--with-diff", "--no-invoke",
        ])
        assert result.exit_code == 0
        assert "Sent" in result.output


# ---------------------------------------------------------------------------
# writ connect (interactive peer setup wizard)
# ---------------------------------------------------------------------------

class TestConnect:
    """Tests for the writ connect command."""

    def test_connect_with_path(
        self, initialized_project: Path, peer_project: Path,
    ):
        from typer.testing import CliRunner

        from writ.cli import app

        runner = CliRunner()
        result = runner.invoke(app, [
            "connect", str(peer_project), "--one-way",
        ])
        assert result.exit_code == 0
        assert "Connected" in result.output
        assert "peer-repo" in result.output

        from writ.core.peers import get_peer
        peer = get_peer("peer-repo")
        assert peer is not None
        assert peer.path == str(peer_project)

    def test_connect_bidirectional(
        self, initialized_project: Path, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        peer = tmp_path / "other-repo"
        peer.mkdir()
        (peer / ".writ").mkdir()
        (peer / ".writ" / "conversations").mkdir(parents=True)

        from typer.testing import CliRunner

        from writ.cli import app

        runner = CliRunner()
        result = runner.invoke(app, [
            "connect", str(peer), "--bidirectional",
        ])
        assert result.exit_code == 0
        assert "Connected" in result.output
        assert "reverse peer" in result.output

    def test_connect_custom_name(
        self, initialized_project: Path, peer_project: Path,
    ):
        from typer.testing import CliRunner

        from writ.cli import app

        runner = CliRunner()
        result = runner.invoke(app, [
            "connect", str(peer_project),
            "--name", "my-api",
            "--one-way",
        ])
        assert result.exit_code == 0
        assert "my-api" in result.output

        from writ.core.peers import get_peer
        assert get_peer("my-api") is not None

    def test_connect_nonexistent_path(self, initialized_project: Path):
        from typer.testing import CliRunner

        from writ.cli import app

        runner = CliRunner()
        result = runner.invoke(app, [
            "connect", "/nonexistent/path/does/not/exist",
        ])
        assert result.exit_code == 1
        assert "not found" in result.output


# ---------------------------------------------------------------------------
# Remote conversation pull (backend relay inbound sync)
# ---------------------------------------------------------------------------

class TestRemotePull:
    """Verify _pull_remote_messages appends new messages from the relay."""

    def _setup_remote_conv(self, repo_root: Path) -> tuple[Path, PeerConfig, Conversation]:
        """Register a remote peer and seed a conversation file."""
        from writ.core import messaging
        from writ.core.peers import add_peer

        peer = add_peer("remote-peer", remote="peeruser")
        conv = messaging.create_conversation(
            peer_repo="remote-peer",
            goal="Remote sync test",
            local_agent="me",
            local_repo=repo_root.name,
        )
        path = messaging.conversations_dir() / messaging._conv_filename(
            "remote-peer", "Remote sync test",
        )
        return path, peer, conv

    def test_pull_appends_new_messages(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        from writ.commands.chat import _pull_remote_messages
        from writ.core import auth

        path, peer, conv = self._setup_remote_conv(initialized_project)

        monkeypatch.setattr(auth, "is_logged_in", lambda: True)

        class _FakeClient:
            def pull_conversation(self, conv_id, *, after_message=0):
                return {
                    "messages": [
                        {
                            "id": "msg-r1",
                            "agent_name": "peer-agent",
                            "repo_name": "remote-peer",
                            "content": "Hello from the relay",
                            "attachments": [],
                        }
                    ]
                }

        import writ.integrations.registry as reg_mod
        monkeypatch.setattr(reg_mod, "RegistryClient", lambda: _FakeClient())

        appended = _pull_remote_messages(peer, path, conv)
        assert appended == 1

        from writ.core.messaging import load_conversation
        refreshed = load_conversation(path)
        assert refreshed is not None
        assert len(refreshed.messages) == 1
        assert refreshed.messages[0].content == "Hello from the relay"

    def test_pull_idempotent_on_re_pull(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        from writ.commands.chat import _pull_remote_messages
        from writ.core import auth, messaging

        path, peer, conv = self._setup_remote_conv(initialized_project)
        monkeypatch.setattr(auth, "is_logged_in", lambda: True)

        all_remote = [
            {
                "id": "msg-r1",
                "agent_name": "peer-agent",
                "repo_name": "remote-peer",
                "content": "Only-once message",
                "attachments": [],
            }
        ]

        class _FakeClient:
            def pull_conversation(self, conv_id, *, after_message=0):
                return {"messages": all_remote[after_message:]}

        import writ.integrations.registry as reg_mod
        monkeypatch.setattr(reg_mod, "RegistryClient", lambda: _FakeClient())

        first = _pull_remote_messages(peer, path, conv)
        assert first == 1

        refreshed = messaging.load_conversation(path)
        assert refreshed is not None
        second = _pull_remote_messages(peer, path, refreshed)
        assert second == 0

        refreshed2 = messaging.load_conversation(path)
        assert refreshed2 is not None
        assert len(refreshed2.messages) == 1

    def test_pull_graceful_on_network_error(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        from writ.commands.chat import _pull_remote_messages
        from writ.core import auth

        path, peer, conv = self._setup_remote_conv(initialized_project)
        monkeypatch.setattr(auth, "is_logged_in", lambda: True)

        class _FakeClient:
            def pull_conversation(self, conv_id, *, after_message=0):
                raise RuntimeError("boom")

        import writ.integrations.registry as reg_mod
        monkeypatch.setattr(reg_mod, "RegistryClient", lambda: _FakeClient())

        assert _pull_remote_messages(peer, path, conv) == 0

    def test_pull_skipped_for_local_peer(
        self, initialized_project: Path,
    ):
        from writ.commands.chat import _pull_remote_messages
        from writ.core import messaging
        from writ.core.peers import add_peer

        local_peer_root = initialized_project.parent / "local-peer"
        local_peer_root.mkdir()
        (local_peer_root / ".writ").mkdir()
        peer = add_peer("local-peer", path=str(local_peer_root))

        conv = messaging.create_conversation(
            peer_repo="local-peer",
            goal="Local",
            local_agent="me",
            local_repo=initialized_project.name,
        )
        path = messaging.conversations_dir() / messaging._conv_filename(
            "local-peer", "Local",
        )
        assert _pull_remote_messages(peer, path, conv) == 0

    def test_pull_skipped_when_not_logged_in(
        self, initialized_project: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        from writ.commands.chat import _pull_remote_messages
        from writ.core import auth

        path, peer, conv = self._setup_remote_conv(initialized_project)
        monkeypatch.setattr(auth, "is_logged_in", lambda: False)

        assert _pull_remote_messages(peer, path, conv) == 0


# ---------------------------------------------------------------------------
# PeerConfig context-bloat limits (item 7)
# ---------------------------------------------------------------------------

class TestPeerConfigLimits:
    """Enforce max_turns + max_context_tokens in chat_send."""

    def _start_conversation(
        self, initialized_project: Path, peer_name: str = "peer",
        *, max_turns: int | None = None, max_context_tokens: int | None = None,
    ):
        from writ.core import messaging
        from writ.core.peers import add_peer

        peer_root = initialized_project.parent / "peer-project"
        peer_root.mkdir(parents=True, exist_ok=True)
        (peer_root / ".writ").mkdir(exist_ok=True)

        kwargs: dict = {"path": str(peer_root)}
        if max_turns is not None:
            kwargs["max_turns"] = max_turns
        add_peer(peer_name, **kwargs)

        if max_context_tokens is not None:
            from writ.core.peers import load_peers, save_peers
            manifest = load_peers()
            manifest.peers[peer_name].max_context_tokens = max_context_tokens
            save_peers(manifest)

        conv = messaging.create_conversation(
            peer_repo=peer_name,
            goal="Limits test",
            local_agent="me",
            local_repo=initialized_project.name,
        )
        return conv

    def test_send_blocked_when_message_exceeds_token_cap(
        self, initialized_project: Path,
    ):
        from typer.testing import CliRunner

        from writ.cli import app

        conv = self._start_conversation(
            initialized_project, max_context_tokens=100,
        )
        runner = CliRunner()
        huge = "x " * 1000
        result = runner.invoke(
            app, ["chat", "send", conv.id, huge, "--no-invoke"],
        )
        assert result.exit_code == 1
        assert "--truncate" in result.output or "--force" in result.output

    def test_truncate_flag_lets_message_through(
        self, initialized_project: Path,
    ):
        from typer.testing import CliRunner

        from writ.cli import app

        conv = self._start_conversation(
            initialized_project, max_context_tokens=100,
        )
        runner = CliRunner()
        huge = "x " * 1000
        result = runner.invoke(
            app, ["chat", "send", conv.id, huge, "--truncate", "--no-invoke"],
        )
        assert result.exit_code == 0
        assert "Truncated" in result.output or "Sent" in result.output

    def test_force_flag_bypasses_token_cap(
        self, initialized_project: Path,
    ):
        from typer.testing import CliRunner

        from writ.cli import app

        conv = self._start_conversation(
            initialized_project, max_context_tokens=100,
        )
        runner = CliRunner()
        huge = "x " * 1000
        result = runner.invoke(
            app, ["chat", "send", conv.id, huge, "--force", "--no-invoke"],
        )
        assert result.exit_code == 0

    def test_turn_cap_blocks_further_sends(
        self, initialized_project: Path,
    ):
        from typer.testing import CliRunner

        from writ.cli import app
        from writ.core import messaging

        conv = self._start_conversation(
            initialized_project, max_turns=1,
        )
        path_pair = messaging.find_conversation(conv.id)
        assert path_pair is not None
        path, _ = path_pair
        messaging.append_message(
            path, agent="me", repo=initialized_project.name,
            content="first message to hit the cap",
        )

        runner = CliRunner()
        result = runner.invoke(
            app, ["chat", "send", conv.id, "second", "--no-invoke"],
        )
        assert result.exit_code == 1
        assert (
            "capacity reached" in result.output.lower()
            or "max_turns" in result.output.lower()
        )
