"""Tests for writ login/logout commands and remote sync paths."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from writ.cli import app
from writ.core import auth, store

runner = CliRunner()


class TestLogin:
    def test_login_saves_token(self, tmp_project: Path, tmp_global_writ: Path) -> None:
        result = runner.invoke(app, ["login", "--token", "sk_test123"])
        assert result.exit_code == 0
        assert "Logged in" in result.output
        assert auth.get_token() == "sk_test123"

    def test_login_interactive_prompt(self, tmp_project: Path, tmp_global_writ: Path) -> None:
        result = runner.invoke(app, ["login"], input="sk_interactive456\n")
        assert result.exit_code == 0
        assert "Logged in" in result.output
        assert auth.get_token() == "sk_interactive456"

    def test_login_empty_key_fails(self, tmp_project: Path, tmp_global_writ: Path) -> None:
        result = runner.invoke(app, ["login", "--token", ""])
        assert result.exit_code == 1
        assert "empty" in result.output.lower()

    def test_login_whitespace_only_fails(self, tmp_project: Path, tmp_global_writ: Path) -> None:
        result = runner.invoke(app, ["login", "--token", "   "])
        assert result.exit_code == 1

    def test_login_strips_whitespace(self, tmp_project: Path, tmp_global_writ: Path) -> None:
        result = runner.invoke(app, ["login", "--token", "  sk_padded789  "])
        assert result.exit_code == 0
        assert auth.get_token() == "sk_padded789"

    def test_login_overwrites_previous_token(
        self, tmp_project: Path, tmp_global_writ: Path,
    ) -> None:
        runner.invoke(app, ["login", "--token", "sk_first"])
        runner.invoke(app, ["login", "--token", "sk_second"])
        assert auth.get_token() == "sk_second"


class TestLogout:
    def test_logout_clears_token(self, tmp_project: Path, tmp_global_writ: Path) -> None:
        runner.invoke(app, ["login", "--token", "sk_tobecleared"])
        assert auth.is_logged_in()

        result = runner.invoke(app, ["logout"])
        assert result.exit_code == 0
        assert "Logged out" in result.output
        assert not auth.is_logged_in()
        assert auth.get_token() is None

    def test_logout_when_not_logged_in(self, tmp_project: Path, tmp_global_writ: Path) -> None:
        store.init_global_store()
        result = runner.invoke(app, ["logout"])
        assert result.exit_code == 0
        assert "Not logged in" in result.output


class TestIsLoggedIn:
    def test_not_logged_in_by_default(self, tmp_project: Path, tmp_global_writ: Path) -> None:
        store.init_global_store()
        assert not auth.is_logged_in()

    def test_logged_in_after_login(self, tmp_project: Path, tmp_global_writ: Path) -> None:
        runner.invoke(app, ["login", "--token", "sk_check"])
        assert auth.is_logged_in()

    def test_not_logged_in_after_logout(self, tmp_project: Path, tmp_global_writ: Path) -> None:
        runner.invoke(app, ["login", "--token", "sk_check"])
        runner.invoke(app, ["logout"])
        assert not auth.is_logged_in()


class TestRemoteSyncPaths:
    """Test that save/load/library work correctly with mocked remote."""

    def test_save_pushes_to_remote_when_logged_in(
        self, initialized_project: Path, tmp_global_writ: Path
    ) -> None:
        runner.invoke(app, ["add", "reviewer", "--instructions", "Review code."])
        runner.invoke(app, ["login", "--token", "sk_test"])

        with patch("writ.commands.library.RegistryClient") as mock_client:
            mock_client.return_value.push_to_library.return_value = True
            result = runner.invoke(app, ["save", "reviewer"])

        assert result.exit_code == 0
        assert "Synced to enwrit.com" in result.output
        mock_client.return_value.push_to_library.assert_called_once()

    def test_save_shows_failure_when_remote_fails(
        self, initialized_project: Path, tmp_global_writ: Path
    ) -> None:
        runner.invoke(app, ["add", "reviewer", "--instructions", "Review code."])
        runner.invoke(app, ["login", "--token", "sk_test"])

        with patch("writ.commands.library.RegistryClient") as mock_client:
            mock_client.return_value.push_to_library.return_value = False
            result = runner.invoke(app, ["save", "reviewer"])

        assert result.exit_code == 0
        assert "Local save only" in result.output

    def test_save_skips_remote_when_logged_out(
        self, initialized_project: Path, tmp_global_writ: Path
    ) -> None:
        runner.invoke(app, ["add", "reviewer", "--instructions", "Review code."])
        store.init_global_store()

        with patch("writ.commands.library.RegistryClient") as mock_client:
            result = runner.invoke(app, ["save", "reviewer"])

        assert result.exit_code == 0
        mock_client.return_value.push_to_library.assert_not_called()

    def test_load_falls_back_to_remote(
        self, initialized_project: Path, tmp_global_writ: Path
    ) -> None:
        runner.invoke(app, ["login", "--token", "sk_test"])

        remote_data = {
            "name": "remote-agent",
            "description": "From the cloud",
            "version": "2.0.0",
            "tags": ["remote"],
            "instructions": "Remote instructions here.",
        }

        with patch("writ.commands.library.RegistryClient") as mock_client:
            mock_client.return_value.pull_from_library.return_value = remote_data
            result = runner.invoke(app, ["load", "remote-agent"])

        assert result.exit_code == 0
        assert "from enwrit.com" in result.output

    def test_library_shows_remote_columns_when_logged_in(
        self, initialized_project: Path, tmp_global_writ: Path
    ) -> None:
        runner.invoke(app, ["add", "local-only", "--instructions", "Local."])
        runner.invoke(app, ["save", "local-only"])
        runner.invoke(app, ["login", "--token", "sk_test"])

        remote_list = [
            {"name": "local-only", "description": "Local.", "version": "1.0.0", "tags": []},
            {"name": "remote-only", "description": "Remote.", "version": "1.0.0", "tags": []},
        ]

        with patch("writ.commands.library.RegistryClient") as mock_client:
            mock_client.return_value.list_library.return_value = remote_list
            result = runner.invoke(app, ["library"])

        assert result.exit_code == 0
        assert "Local" in result.output
        assert "Remote" in result.output

    def test_load_remote_with_malformed_data(
        self, initialized_project: Path, tmp_global_writ: Path
    ) -> None:
        """Backend returns data missing required fields -- should not crash."""
        runner.invoke(app, ["login", "--token", "sk_test"])

        with patch("writ.commands.library.RegistryClient") as mock_client:
            mock_client.return_value.pull_from_library.return_value = {
                "unexpected": "format",
            }
            result = runner.invoke(app, ["load", "bad-agent"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_library_with_malformed_remote_entries(
        self, initialized_project: Path, tmp_global_writ: Path
    ) -> None:
        """Remote returns entries missing 'name' -- should skip gracefully."""
        runner.invoke(app, ["login", "--token", "sk_test"])

        remote_list = [
            {"name": "good-agent", "description": "OK", "version": "1.0.0", "tags": []},
            {"no_name_field": True},
        ]

        with patch("writ.commands.library.RegistryClient") as mock_client:
            mock_client.return_value.list_library.return_value = remote_list
            result = runner.invoke(app, ["library"])

        assert result.exit_code == 0
        assert "good-agent" in result.output
