"""Tests for writ upgrade command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from writ.cli import app
from writ.core import store
from writ.core.models import InstructionConfig

runner = CliRunner()

_REGISTRY_PATCH = "writ.integrations.registry.RegistryClient"


def _save_sourced_agent(name: str, version: str = "1.0.0", source: str = "enwrit/test"):
    cfg = InstructionConfig(
        name=name, description=f"Test {name}", version=version,
        instructions="Original instructions.", source=source,
    )
    store.save_instruction(cfg)
    return cfg


class TestUpgradeCommand:

    def test_not_initialized(self, tmp_project):
        result = runner.invoke(app, ["upgrade"])
        assert result.exit_code == 1
        assert "init" in result.output.lower()

    def test_no_instructions(self, initialized_project):
        result = runner.invoke(app, ["upgrade"])
        assert result.exit_code == 0
        assert "No instructions" in result.output

    def test_no_upgradeable(self, initialized_project):
        store.save_instruction(InstructionConfig(
            name="local-only", instructions="No source set.",
        ))
        result = runner.invoke(app, ["upgrade"])
        assert result.exit_code == 0
        assert "No upgradeable" in result.output

    def test_up_to_date(self, initialized_project):
        _save_sourced_agent("my-agent", "1.0.0")
        mock_client = MagicMock()
        mock_client.hub_download.return_value = {
            "name": "my-agent", "version": "1.0.0",
            "instructions": "Original instructions.",
        }
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["upgrade"])
        assert result.exit_code == 0
        assert "up to date" in result.output

    def test_upgrade_available_dry_run(self, initialized_project):
        _save_sourced_agent("my-agent", "1.0.0")
        mock_client = MagicMock()
        mock_client.hub_download.return_value = {
            "name": "my-agent", "version": "2.0.0",
            "instructions": "Updated instructions.",
        }
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["upgrade", "--dry-run"])
        assert result.exit_code == 0
        assert "update available" in result.output
        assert "Dry run" in result.output
        reloaded = store.load_instruction("my-agent")
        assert reloaded.version == "1.0.0"

    def test_upgrade_applies(self, initialized_project):
        _save_sourced_agent("my-agent", "1.0.0")
        mock_client = MagicMock()
        mock_client.hub_download.return_value = {
            "name": "my-agent", "version": "2.0.0",
            "instructions": "Brand new instructions.",
        }
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["upgrade"])
        assert result.exit_code == 0
        assert "upgraded" in result.output
        reloaded = store.load_instruction("my-agent")
        assert "Brand new" in reloaded.instructions

    def test_upgrade_specific_name(self, initialized_project):
        _save_sourced_agent("agent-a", "1.0.0")
        _save_sourced_agent("agent-b", "1.0.0")
        mock_client = MagicMock()
        mock_client.hub_download.return_value = {
            "name": "agent-a", "version": "2.0.0",
            "instructions": "Updated A.",
        }
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["upgrade", "agent-a"])
        assert result.exit_code == 0
        assert "agent-a" in result.output

    def test_upgrade_name_not_found(self, initialized_project):
        result = runner.invoke(app, ["upgrade", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_source_unavailable(self, initialized_project):
        _save_sourced_agent("my-agent", "1.0.0")
        mock_client = MagicMock()
        mock_client.hub_download.return_value = None
        mock_client.pull_public_agent.return_value = None
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["upgrade"])
        assert result.exit_code == 0
        assert "source unavailable" in result.output

    def test_prpm_source(self, initialized_project):
        _save_sourced_agent("prpm-pkg", "1.0.0", source="prpm/my-prpm-pkg")
        mock_client = MagicMock()
        mock_client.hub_download.return_value = {
            "name": "my-prpm-pkg", "version": "1.1.0",
            "instructions": "PRPM updated.",
        }
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["upgrade", "prpm-pkg"])
        assert result.exit_code == 0
        mock_client.hub_download.assert_called_with("prpm", "my-prpm-pkg")
