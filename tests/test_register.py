"""Tests for writ register -- account creation and auto-login."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
from typer.testing import CliRunner

from writ.cli import app
from writ.core import auth

runner = CliRunner()


class TestAlreadyLoggedIn:
    def test_already_logged_in(self, tmp_project: Path, tmp_global_writ: Path) -> None:
        runner.invoke(app, ["login", "--token", "sk_existing"])
        result = runner.invoke(app, ["register", "--username", "someone"])
        assert result.exit_code == 0
        assert "Already logged in" in result.output


class TestInputValidation:
    def test_empty_username(self, tmp_project: Path, tmp_global_writ: Path) -> None:
        result = runner.invoke(app, ["register", "--username", "  ", "--email", "a@b.com"])
        assert result.exit_code == 1
        assert "empty" in result.output.lower()


class TestSuccessfulRegistration:
    def test_successful_registration(self, tmp_project: Path, tmp_global_writ: Path) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"api_key": "sk_test123abc"}

        with patch("httpx.post", return_value=mock_resp):
            result = runner.invoke(
                app, ["register", "--username", "testuser", "--email", "test@example.com"],
            )

        assert result.exit_code == 0
        assert "Account created and logged in" in result.output
        assert "testuser" in result.output
        assert auth.is_logged_in()
        assert auth.get_token() == "sk_test123abc"


class TestRegistrationErrors:
    def test_duplicate_account_409(self, tmp_project: Path, tmp_global_writ: Path) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 409

        with patch("httpx.post", return_value=mock_resp):
            result = runner.invoke(
                app, ["register", "--username", "taken", "--email", "t@b.com"],
            )

        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_validation_error_422(self, tmp_project: Path, tmp_global_writ: Path) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.json.return_value = {"detail": "Invalid email"}

        with patch("httpx.post", return_value=mock_resp):
            result = runner.invoke(
                app, ["register", "--username", "user", "--email", "bad"],
            )

        assert result.exit_code == 1
        assert "Invalid email" in result.output

    def test_network_error_connect(self, tmp_project: Path, tmp_global_writ: Path) -> None:
        with patch("httpx.post", side_effect=httpx.ConnectError("Connection refused")):
            result = runner.invoke(
                app, ["register", "--username", "user", "--email", "a@b.com"],
            )

        assert result.exit_code == 1
        assert "Could not reach" in result.output

    def test_generic_network_error(self, tmp_project: Path, tmp_global_writ: Path) -> None:
        with patch("httpx.post", side_effect=RuntimeError("something broke")):
            result = runner.invoke(
                app, ["register", "--username", "user", "--email", "a@b.com"],
            )

        assert result.exit_code == 1
        assert "Network error" in result.output
