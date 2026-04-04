"""Tests for writ approvals CLI commands (create, list, approve, deny)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from writ.cli import app

runner = CliRunner()

_REGISTRY_PATCH = "writ.integrations.registry.RegistryClient"


def _mock_logged_in(monkeypatch):
    monkeypatch.setattr("writ.commands.approvals.auth.is_logged_in", lambda: True)


def _mock_logged_out(monkeypatch):
    monkeypatch.setattr("writ.commands.approvals.auth.is_logged_in", lambda: False)


class TestApprovalsCreate:

    def test_create_requires_login(self, monkeypatch):
        _mock_logged_out(monkeypatch)
        result = runner.invoke(app, ["approvals", "create", "deploy", "Deploy v2"])
        assert result.exit_code == 1
        assert "login" in result.output.lower()

    def test_create_success(self, monkeypatch, tmp_project):
        _mock_logged_in(monkeypatch)
        mock_client = MagicMock()
        mock_client.create_approval.return_value = {
            "id": "apr-123", "status": "pending",
        }
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["approvals", "create", "deploy", "Deploy v2.0"])
        assert result.exit_code == 0
        assert "apr-123" in result.output
        assert "pending" in result.output.lower()
        mock_client.create_approval.assert_called_once()

    def test_create_with_urgency(self, monkeypatch, tmp_project):
        _mock_logged_in(monkeypatch)
        mock_client = MagicMock()
        mock_client.create_approval.return_value = {"id": "apr-456"}
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, [
                "approvals", "create", "delete", "Remove legacy module",
                "--urgency", "high", "--reasoning", "No longer needed",
            ])
        assert result.exit_code == 0
        call_kwargs = mock_client.create_approval.call_args
        assert call_kwargs[1]["urgency"] == "high" or call_kwargs.kwargs.get("urgency") == "high"

    def test_create_error(self, monkeypatch, tmp_project):
        _mock_logged_in(monkeypatch)
        mock_client = MagicMock()
        mock_client.create_approval.return_value = {"error": "Network error"}
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["approvals", "create", "deploy", "Deploy"])
        assert result.exit_code == 1
        assert "error" in result.output.lower()


class TestApprovalsList:

    def test_list_requires_login(self, monkeypatch):
        _mock_logged_out(monkeypatch)
        result = runner.invoke(app, ["approvals", "list"])
        assert result.exit_code == 1
        assert "login" in result.output.lower()

    def test_list_empty(self, monkeypatch):
        _mock_logged_in(monkeypatch)
        mock_client = MagicMock()
        mock_client.list_approvals.return_value = {"approvals": []}
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["approvals", "list"])
        assert result.exit_code == 0
        assert "No approval" in result.output

    def test_list_with_data(self, monkeypatch):
        _mock_logged_in(monkeypatch)
        mock_client = MagicMock()
        mock_client.list_approvals.return_value = {"approvals": [
            {
                "id": "apr-100", "action_type": "deploy",
                "description": "Deploy v2.0 to production",
                "urgency": "high", "status": "pending",
                "agent_name": "deployer",
            },
        ]}
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["approvals", "list"])
        assert result.exit_code == 0
        assert "deploy" in result.output.lower()

    def test_list_with_status_filter(self, monkeypatch):
        _mock_logged_in(monkeypatch)
        mock_client = MagicMock()
        mock_client.list_approvals.return_value = {"approvals": []}
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["approvals", "list", "--status", "pending"])
        assert result.exit_code == 0
        mock_client.list_approvals.assert_called_once_with(status="pending")

    def test_list_error(self, monkeypatch):
        _mock_logged_in(monkeypatch)
        mock_client = MagicMock()
        mock_client.list_approvals.return_value = {"error": "Server error"}
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["approvals", "list"])
        assert result.exit_code == 1
        assert "error" in result.output.lower()


class TestApprovalsApprove:

    def test_approve_requires_login(self, monkeypatch):
        _mock_logged_out(monkeypatch)
        result = runner.invoke(app, ["approvals", "approve", "apr-100"])
        assert result.exit_code == 1

    def test_approve_success(self, monkeypatch):
        _mock_logged_in(monkeypatch)
        mock_client = MagicMock()
        mock_client.resolve_approval.return_value = {
            "description": "Deploy v2.0", "status": "approved",
        }
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["approvals", "approve", "apr-100"])
        assert result.exit_code == 0
        assert "Approved" in result.output
        mock_client.resolve_approval.assert_called_once_with("apr-100", decision="approved")

    def test_approve_error(self, monkeypatch):
        _mock_logged_in(monkeypatch)
        mock_client = MagicMock()
        mock_client.resolve_approval.return_value = {"error": "Not found"}
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["approvals", "approve", "nope"])
        assert result.exit_code == 1


class TestApprovalsDeny:

    def test_deny_requires_login(self, monkeypatch):
        _mock_logged_out(monkeypatch)
        result = runner.invoke(app, ["approvals", "deny", "apr-100"])
        assert result.exit_code == 1

    def test_deny_success(self, monkeypatch):
        _mock_logged_in(monkeypatch)
        mock_client = MagicMock()
        mock_client.resolve_approval.return_value = {
            "description": "Deploy v2.0", "status": "denied",
        }
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["approvals", "deny", "apr-100", "--reason", "Not ready"])
        assert result.exit_code == 0
        assert "Denied" in result.output
        mock_client.resolve_approval.assert_called_once_with(
            "apr-100", decision="denied", reason="Not ready",
        )
