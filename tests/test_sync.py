"""Tests for writ sync -- bulk bidirectional library sync."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from writ.cli import app
from writ.core.models import InstructionConfig

runner = CliRunner()


class TestSyncCommand:
    """Test the writ sync CLI command."""

    def test_not_logged_in(self):
        with patch("writ.commands.sync.auth") as mock_auth:
            mock_auth.is_logged_in.return_value = False
            result = runner.invoke(app, ["sync"])
        assert result.exit_code == 1
        assert "not logged in" in result.output.lower()

    def test_push_and_pull_together_fails(self):
        result = runner.invoke(app, ["sync", "--push", "--pull"])
        assert result.exit_code == 1
        assert "cannot" in result.output.lower()

    def test_already_in_sync(self, monkeypatch: object, tmp_path: Path):
        """When local and remote are empty, reports already in sync."""
        monkeypatch.setattr("writ.commands.sync.auth.is_logged_in", lambda: True)
        monkeypatch.setattr("writ.commands.sync.store.init_global_store", lambda: tmp_path)
        monkeypatch.setattr("writ.commands.sync.store.list_library", lambda: [])

        mock_client = MagicMock()
        mock_client.list_library.return_value = []
        monkeypatch.setattr(
            "writ.commands.sync.RegistryClient", lambda: mock_client
        )

        result = runner.invoke(app, ["sync"])
        assert result.exit_code == 0
        assert "in sync" in result.output.lower()

    def test_push_only(self, monkeypatch: object, tmp_path: Path):
        """Push-only pushes local instructions to remote."""
        monkeypatch.setattr("writ.commands.sync.auth.is_logged_in", lambda: True)
        monkeypatch.setattr("writ.commands.sync.store.init_global_store", lambda: tmp_path)

        local = [InstructionConfig(name="dev", instructions="Dev agent.")]
        monkeypatch.setattr("writ.commands.sync.store.list_library", lambda: local)

        mock_client = MagicMock()
        mock_client.list_library.return_value = []
        mock_client.push_to_library.return_value = True
        monkeypatch.setattr(
            "writ.commands.sync.RegistryClient", lambda: mock_client
        )

        result = runner.invoke(app, ["sync", "--push"])
        assert result.exit_code == 0
        assert "pushed" in result.output.lower()
        mock_client.push_to_library.assert_called_once()

    def test_pull_only(self, monkeypatch: object, tmp_path: Path):
        """Pull-only pulls remote instructions to local."""
        monkeypatch.setattr("writ.commands.sync.auth.is_logged_in", lambda: True)
        monkeypatch.setattr("writ.commands.sync.store.init_global_store", lambda: tmp_path)
        monkeypatch.setattr("writ.commands.sync.store.list_library", lambda: [])

        mock_client = MagicMock()
        mock_client.list_library.return_value = [{"name": "remote-dev"}]
        mock_client.pull_from_library.return_value = {
            "name": "remote-dev",
            "instructions": "Remote dev.",
        }
        monkeypatch.setattr(
            "writ.commands.sync.RegistryClient", lambda: mock_client
        )
        saved: list = []
        monkeypatch.setattr(
            "writ.commands.sync.store.save_to_library",
            lambda cfg, **kw: saved.append(cfg.name),
        )

        result = runner.invoke(app, ["sync", "--pull"])
        assert result.exit_code == 0
        assert "pulled" in result.output.lower()
        assert "remote-dev" in saved

    def test_dry_run_no_changes(self, monkeypatch: object, tmp_path: Path):
        """Dry run shows what would sync without making changes."""
        monkeypatch.setattr("writ.commands.sync.auth.is_logged_in", lambda: True)
        monkeypatch.setattr("writ.commands.sync.store.init_global_store", lambda: tmp_path)

        local = [InstructionConfig(name="local-only", instructions="Local.")]
        monkeypatch.setattr("writ.commands.sync.store.list_library", lambda: local)

        mock_client = MagicMock()
        mock_client.list_library.return_value = [{"name": "remote-only"}]
        monkeypatch.setattr(
            "writ.commands.sync.RegistryClient", lambda: mock_client
        )

        result = runner.invoke(app, ["sync", "--dry-run"])
        assert result.exit_code == 0
        assert "dry run" in result.output.lower()
        mock_client.push_to_library.assert_not_called()
        mock_client.pull_from_library.assert_not_called()

    def test_conflict_prefer_remote_default(
        self, monkeypatch: object, tmp_path: Path,
    ):
        """By default, shared instructions pull from remote."""
        monkeypatch.setattr("writ.commands.sync.auth.is_logged_in", lambda: True)
        monkeypatch.setattr("writ.commands.sync.store.init_global_store", lambda: tmp_path)

        local = [InstructionConfig(name="shared", instructions="Local ver.")]
        monkeypatch.setattr("writ.commands.sync.store.list_library", lambda: local)

        mock_client = MagicMock()
        mock_client.list_library.return_value = [{"name": "shared"}]
        mock_client.pull_from_library.return_value = {
            "name": "shared",
            "instructions": "Remote ver.",
        }
        monkeypatch.setattr(
            "writ.commands.sync.RegistryClient", lambda: mock_client
        )
        saved: list = []
        monkeypatch.setattr(
            "writ.commands.sync.store.save_to_library",
            lambda cfg, **kw: saved.append(cfg.instructions),
        )

        result = runner.invoke(app, ["sync"])
        assert result.exit_code == 0
        assert "remote wins" in result.output.lower()
        assert "Remote ver." in saved

    def test_conflict_prefer_local(self, monkeypatch: object, tmp_path: Path):
        """With --prefer-local, shared instructions push to remote."""
        monkeypatch.setattr("writ.commands.sync.auth.is_logged_in", lambda: True)
        monkeypatch.setattr("writ.commands.sync.store.init_global_store", lambda: tmp_path)

        local = [InstructionConfig(name="shared", instructions="Local ver.")]
        monkeypatch.setattr("writ.commands.sync.store.list_library", lambda: local)

        mock_client = MagicMock()
        mock_client.list_library.return_value = [{"name": "shared"}]
        mock_client.push_to_library.return_value = True
        monkeypatch.setattr(
            "writ.commands.sync.RegistryClient", lambda: mock_client
        )

        result = runner.invoke(app, ["sync", "--prefer-local"])
        assert result.exit_code == 0
        assert "local wins" in result.output.lower()
        mock_client.push_to_library.assert_called_once()

    def test_push_failure_reports_error(
        self, monkeypatch: object, tmp_path: Path,
    ):
        """When push fails, errors are counted and reported."""
        monkeypatch.setattr("writ.commands.sync.auth.is_logged_in", lambda: True)
        monkeypatch.setattr("writ.commands.sync.store.init_global_store", lambda: tmp_path)

        local = [InstructionConfig(name="dev", instructions="Dev.")]
        monkeypatch.setattr("writ.commands.sync.store.list_library", lambda: local)

        mock_client = MagicMock()
        mock_client.list_library.return_value = []
        mock_client.push_to_library.return_value = False
        monkeypatch.setattr(
            "writ.commands.sync.RegistryClient", lambda: mock_client
        )

        result = runner.invoke(app, ["sync", "--push"])
        assert result.exit_code == 0
        assert "failed" in result.output.lower()
        assert "error" in result.output.lower()
