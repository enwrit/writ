"""Tests for core/invoker.py -- CLI agent detection, invocation, and API fallback."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from writ.core.invoker import (
    CLIAgent,
    detect_cli_agents,
    invoke_api,
    invoke_cli_agent,
    invoke_peer,
    preferred_cli_agent,
)
from writ.core.models import PeerConfig

# ---------------------------------------------------------------------------
# CLI agent detection
# ---------------------------------------------------------------------------

class TestCLIAgentDetection:
    def test_detect_no_agents(self):
        with patch("shutil.which", return_value=None):
            agents = detect_cli_agents()
            assert agents == []

    def test_detect_claude(self):
        def fake_which(name: str):
            return "/usr/bin/claude" if name == "claude" else None

        with patch("shutil.which", side_effect=fake_which):
            agents = detect_cli_agents()
            assert len(agents) == 1
            assert agents[0].name == "claude"

    def test_detect_multiple_agents(self):
        def fake_which(name: str):
            if name in ("claude", "gemini"):
                return f"/usr/bin/{name}"
            return None

        with patch("shutil.which", side_effect=fake_which):
            agents = detect_cli_agents()
            assert len(agents) == 2
            names = [a.name for a in agents]
            assert "claude" in names
            assert "gemini" in names

    def test_preferred_returns_first(self):
        def fake_which(name: str):
            return f"/usr/bin/{name}" if name == "claude" else None

        with patch("shutil.which", side_effect=fake_which):
            agent = preferred_cli_agent()
            assert agent is not None
            assert agent.name == "claude"

    def test_preferred_returns_none_when_empty(self):
        with patch("shutil.which", return_value=None):
            agent = preferred_cli_agent()
            assert agent is None


# ---------------------------------------------------------------------------
# CLI agent command building
# ---------------------------------------------------------------------------

class TestCLIAgentCommand:
    def test_claude_command(self):
        agent = CLIAgent(name="claude", binary="claude")
        cmd = agent.build_command("hello", "/repo")
        assert cmd == ["claude", "--print", "--message", "hello", "--cwd", "/repo"]

    def test_gemini_command(self):
        agent = CLIAgent(name="gemini", binary="gemini")
        cmd = agent.build_command("hello", "/repo")
        assert cmd == ["gemini", "--message", "hello", "--cwd", "/repo"]

    def test_generic_command(self):
        agent = CLIAgent(name="codex", binary="codex")
        cmd = agent.build_command("hello", "/repo")
        assert cmd == ["codex", "--message", "hello", "--cwd", "/repo"]


# ---------------------------------------------------------------------------
# CLI agent invocation
# ---------------------------------------------------------------------------

class TestCLIInvocation:
    def test_no_cli_agent_available(self):
        peer = PeerConfig(name="test", path="/tmp/repo")
        with patch("writ.core.invoker.preferred_cli_agent", return_value=None):
            result = invoke_cli_agent(peer, "hello")
            assert not result.success
            assert "No CLI agent" in result.error

    def test_peer_has_no_path(self):
        peer = PeerConfig(name="test", path=None)
        agent = CLIAgent(name="claude", binary="claude")
        result = invoke_cli_agent(peer, "hello", agent=agent)
        assert not result.success
        assert "no local path" in result.error

    def test_peer_directory_missing(self, tmp_path: Path):
        peer = PeerConfig(name="test", path=str(tmp_path / "nonexistent"))
        agent = CLIAgent(name="claude", binary="claude")
        result = invoke_cli_agent(peer, "hello", agent=agent)
        assert not result.success
        assert "does not exist" in result.error

    def test_successful_invocation(self, tmp_path: Path):
        peer = PeerConfig(name="test", path=str(tmp_path))
        agent = CLIAgent(name="claude", binary="claude")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "This is the response"

        with patch("subprocess.run", return_value=mock_result):
            result = invoke_cli_agent(peer, "hello", agent=agent)
            assert result.success
            assert result.response == "This is the response"
            assert result.method == "cli"
            assert result.agent_name == "claude"

    def test_failed_invocation(self, tmp_path: Path):
        peer = PeerConfig(name="test", path=str(tmp_path))
        agent = CLIAgent(name="claude", binary="claude")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error occurred"

        with patch("subprocess.run", return_value=mock_result):
            result = invoke_cli_agent(peer, "hello", agent=agent)
            assert not result.success
            assert "error occurred" in result.error

    def test_timeout_handling(self, tmp_path: Path):
        import subprocess

        peer = PeerConfig(name="test", path=str(tmp_path))
        agent = CLIAgent(name="claude", binary="claude")

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 5)):
            result = invoke_cli_agent(peer, "hello", agent=agent, timeout=5)
            assert not result.success
            assert "timed out" in result.error


# ---------------------------------------------------------------------------
# API invocation
# ---------------------------------------------------------------------------

class TestAPIInvocation:
    def test_no_api_key(self):
        peer = PeerConfig(name="test")
        result = invoke_api(peer, "hello")
        assert not result.success
        assert "No API key" in result.error

    def test_unsupported_provider(self):
        peer = PeerConfig(name="test")
        result = invoke_api(peer, "hello", provider="unknown", api_key="sk-test")
        assert not result.success
        assert "Unsupported" in result.error

    def test_anthropic_success(self):
        peer = PeerConfig(name="test")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "Hello back!"}],
        }

        with patch("httpx.post", return_value=mock_resp):
            result = invoke_api(
                peer, "hello",
                provider="anthropic",
                api_key="sk-test",
            )
            assert result.success
            assert result.response == "Hello back!"
            assert result.method == "api"

    def test_anthropic_error(self):
        peer = PeerConfig(name="test")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with patch("httpx.post", return_value=mock_resp):
            result = invoke_api(
                peer, "hello",
                provider="anthropic",
                api_key="sk-test",
            )
            assert not result.success
            assert "500" in result.error

    def test_openai_success(self):
        peer = PeerConfig(name="test")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "OpenAI response"}}],
        }

        with patch("httpx.post", return_value=mock_resp):
            result = invoke_api(
                peer, "hello",
                provider="openai",
                api_key="sk-test",
            )
            assert result.success
            assert result.response == "OpenAI response"


# ---------------------------------------------------------------------------
# Smart invocation (invoke_peer)
# ---------------------------------------------------------------------------

class TestInvokePeer:
    def test_local_peer_prefers_cli(self, tmp_path: Path):
        peer = PeerConfig(name="test", path=str(tmp_path), transport="local")
        agent = CLIAgent(name="claude", binary="claude")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "cli response"

        with (
            patch("writ.core.invoker.preferred_cli_agent", return_value=agent),
            patch("subprocess.run", return_value=mock_result),
        ):
            result = invoke_peer(peer, "hello")
            assert result.success
            assert result.method == "cli"

    def test_falls_back_to_api(self):
        peer = PeerConfig(name="test", transport="remote")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "api response"}],
        }

        with patch("httpx.post", return_value=mock_resp):
            result = invoke_peer(
                peer, "hello",
                llm_config={"api_key": "sk-test", "provider": "anthropic"},
            )
            assert result.success
            assert result.method == "api"

    def test_no_method_available(self):
        peer = PeerConfig(name="test", transport="remote")
        with patch("writ.core.invoker.preferred_cli_agent", return_value=None):
            result = invoke_peer(peer, "hello")
            assert not result.success
            assert "Cannot reach peer" in result.error
