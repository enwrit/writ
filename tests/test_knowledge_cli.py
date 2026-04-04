"""Tests for writ review and writ threads CLI commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from writ.cli import app

runner = CliRunner()

_REGISTRY_PATCH = "writ.integrations.registry.RegistryClient"


def _mock_logged_in(monkeypatch):
    monkeypatch.setattr("writ.commands.knowledge.auth.is_logged_in", lambda: True)


def _mock_logged_out(monkeypatch):
    monkeypatch.setattr("writ.commands.knowledge.auth.is_logged_in", lambda: False)


class TestReviewCommand:

    def test_list_reviews_empty(self, monkeypatch):
        mock_client = MagicMock()
        mock_client.list_reviews.return_value = []
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["review", "some-agent"])
        assert result.exit_code == 0
        assert "No reviews" in result.output

    def test_list_reviews_with_data(self, monkeypatch):
        mock_client = MagicMock()
        mock_client.list_reviews.return_value = [
            {"rating": 4.5, "summary": "Great agent", "author_agent": "reviewer-bot"},
            {"rating": 3.0, "summary": "Decent", "author_agent": "user1"},
        ]
        mock_client.review_summary.return_value = {
            "avg_rating": 3.75, "review_count": 2,
        }
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["review", "some-agent"])
        assert result.exit_code == 0
        assert "3.8" in result.output or "3.75" in result.output
        assert "Great agent" in result.output

    def test_submit_review_requires_login(self, monkeypatch):
        _mock_logged_out(monkeypatch)
        result = runner.invoke(
            app, ["review", "some-agent", "--rating", "4.0", "--summary", "Good"],
        )
        assert result.exit_code == 1
        assert "login" in result.output.lower()

    def test_submit_review_success(self, monkeypatch):
        _mock_logged_in(monkeypatch)
        mock_client = MagicMock()
        mock_client.submit_review.return_value = {"id": "abc"}
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(
                app, ["review", "some-agent", "--rating", "4.5", "--summary", "Excellent"],
            )
        assert result.exit_code == 0
        assert "submitted" in result.output.lower()
        mock_client.submit_review.assert_called_once()

    def test_submit_review_failure(self, monkeypatch):
        _mock_logged_in(monkeypatch)
        mock_client = MagicMock()
        mock_client.submit_review.return_value = None
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(
                app, ["review", "some-agent", "--rating", "3.0", "--summary", "OK"],
            )
        assert result.exit_code == 1
        assert "failed" in result.output.lower()


class TestThreadsList:

    def test_list_empty(self):
        mock_client = MagicMock()
        mock_client.search_threads.return_value = []
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["threads", "list"])
        assert result.exit_code == 0
        assert "No threads" in result.output

    def test_list_with_results(self):
        mock_client = MagicMock()
        mock_client.search_threads.return_value = [
            {"title": "Best patterns", "type": "research", "status": "open",
             "message_count": 5, "id": "abc12345-1234-1234-1234-123456789012"},
        ]
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["threads", "list"])
        assert result.exit_code == 0
        assert "Best patterns" in result.output

    def test_list_with_filters(self):
        mock_client = MagicMock()
        mock_client.search_threads.return_value = []
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(
                app, ["threads", "list", "--type", "research", "--status", "open"],
            )
        assert result.exit_code == 0
        mock_client.search_threads.assert_called_once_with(
            q=None, thread_type="research", category=None, status="open", limit=20,
        )


class TestThreadsStart:

    def test_start_requires_login(self, monkeypatch):
        _mock_logged_out(monkeypatch)
        result = runner.invoke(app, [
            "threads", "start", "My Thread", "--goal", "Test",
            "--message", "Opening msg",
        ])
        assert result.exit_code == 1
        assert "login" in result.output.lower()

    def test_start_success(self, monkeypatch):
        _mock_logged_in(monkeypatch)
        mock_client = MagicMock()
        mock_client.start_thread.return_value = {"id": "tid-123", "title": "My Thread"}
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, [
                "threads", "start", "My Thread", "--goal", "Compare approaches",
                "--message", "Let's discuss",
            ])
        assert result.exit_code == 0
        assert "created" in result.output.lower()
        assert "tid-123" in result.output

    def test_start_failure(self, monkeypatch):
        _mock_logged_in(monkeypatch)
        mock_client = MagicMock()
        mock_client.start_thread.return_value = None
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, [
                "threads", "start", "Fail", "--goal", "Test",
                "--message", "msg",
            ])
        assert result.exit_code == 1


class TestThreadsPost:

    def test_post_requires_login(self, monkeypatch):
        _mock_logged_out(monkeypatch)
        result = runner.invoke(app, ["threads", "post", "tid-123", "--message", "Hello"])
        assert result.exit_code == 1

    def test_post_success(self, monkeypatch):
        _mock_logged_in(monkeypatch)
        mock_client = MagicMock()
        mock_client.post_to_thread.return_value = {"id": "msg-1"}
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["threads", "post", "tid-123", "--message", "Finding X"])
        assert result.exit_code == 0
        assert "Posted" in result.output


class TestThreadsResolve:

    def test_resolve_requires_login(self, monkeypatch):
        _mock_logged_out(monkeypatch)
        result = runner.invoke(app, ["threads", "resolve", "tid-123", "--conclusion", "Done"])
        assert result.exit_code == 1

    def test_resolve_success(self, monkeypatch):
        _mock_logged_in(monkeypatch)
        mock_client = MagicMock()
        mock_client.resolve_thread.return_value = {"status": "resolved"}
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(
                app, ["threads", "resolve", "tid-123", "--conclusion", "Pattern X wins"],
            )
        assert result.exit_code == 0
        assert "resolved" in result.output.lower()


class TestThreadsRead:

    def test_read_not_found(self):
        mock_client = MagicMock()
        mock_client.get_thread.return_value = None
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["threads", "read", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_read_success(self):
        mock_client = MagicMock()
        mock_client.get_thread.return_value = {
            "title": "Test Thread", "goal": "Testing",
            "type": "research", "status": "open",
            "conclusion": None,
            "messages": [
                {"message_type": "comment", "author_agent": "bot", "content": "Hello"},
                {"message_type": "finding", "author_agent": "bot", "content": "Found X"},
            ],
        }
        with patch(_REGISTRY_PATCH, return_value=mock_client):
            result = runner.invoke(app, ["threads", "read", "tid-123"])
        assert result.exit_code == 0
        assert "Test Thread" in result.output
        assert "Found X" in result.output
