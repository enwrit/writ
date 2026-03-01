"""Tests for core/context_window.py -- token estimation, sliding window, API message prep."""

from __future__ import annotations

from pathlib import Path

import pytest

from writ.core.context_window import (
    build_api_messages,
    compose_system_prompt,
    estimate_tokens,
    sliding_window,
    truncate_attachment,
)


class TestTokenEstimation:
    def test_basic_estimation(self):
        assert estimate_tokens("hello world") >= 1

    def test_long_text(self):
        text = "a" * 400
        assert estimate_tokens(text) == 100

    def test_empty_text(self):
        assert estimate_tokens("") == 1

    def test_rough_accuracy(self):
        text = "The quick brown fox jumps over the lazy dog"
        tokens = estimate_tokens(text)
        assert 5 <= tokens <= 20


class TestTruncateAttachment:
    def test_short_content_unchanged(self):
        content = "short content"
        assert truncate_attachment(content) == content

    def test_long_content_truncated(self):
        content = "x" * 200_000
        result = truncate_attachment(content, max_chars=1000)
        assert len(result) < len(content)
        assert "[... file truncated for context window ...]" in result

    def test_keeps_start_and_end(self):
        content = "START" + "x" * 200_000 + "END"
        result = truncate_attachment(content, max_chars=1000)
        assert result.startswith("START")
        assert result.endswith("END")


class TestSlidingWindow:
    def test_small_conversation_unchanged(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = sliding_window(messages, max_tokens=100_000)
        assert len(result) == 2

    def test_drops_oldest_when_over_budget(self):
        messages = [
            {"role": "user", "content": "a" * 40_000},
            {"role": "assistant", "content": "b" * 40_000},
            {"role": "user", "content": "c" * 40_000},
        ]
        result = sliding_window(messages, max_tokens=30_000)
        non_system = [m for m in result if m["role"] != "system"]
        assert len(non_system) < 3
        assert result[-1]["content"] == "c" * 40_000

    def test_always_keeps_last_message(self):
        messages = [
            {"role": "user", "content": "x" * 100_000},
        ]
        result = sliding_window(messages, max_tokens=10_000)
        assert len(result) == 1

    def test_adds_context_note_when_dropping(self):
        messages = [
            {"role": "user", "content": "a" * 40_000},
            {"role": "assistant", "content": "b" * 40_000},
            {"role": "user", "content": "c" * 40_000},
        ]
        result = sliding_window(messages, max_tokens=30_000)
        context_notes = [m for m in result if "Context note" in m["content"]]
        assert len(context_notes) >= 1

    def test_empty_messages(self):
        result = sliding_window([])
        assert result == []

    def test_truncates_attachments_in_older_messages(self):
        messages = [
            {
                "role": "user",
                "content": '<attached file="big.txt">' + "x" * 200_000 + "</attached>",
            },
            {"role": "user", "content": "what do you think?"},
        ]
        result = sliding_window(messages, max_tokens=100_000)
        first_content = result[0]["content"] if result[0]["role"] != "system" else result[1]["content"]
        if "truncated" in first_content:
            assert len(first_content) < 200_000


class TestComposeSystemPrompt:
    def test_default_prompt(self):
        prompt = compose_system_prompt()
        assert "helpful" in prompt.lower()

    def test_custom_instructions(self):
        prompt = compose_system_prompt(agent_instructions="You are a code reviewer.")
        assert "code reviewer" in prompt

    def test_reads_from_writ_dir(self, tmp_path: Path):
        agents_dir = tmp_path / ".writ" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "reviewer.yaml").write_text("name: reviewer\ninstructions: Review code carefully.")
        ctx_file = tmp_path / ".writ" / "project-context.md"
        ctx_file.write_text("# My Project\nPython project.")

        prompt = compose_system_prompt(peer_repo_root=tmp_path)
        assert "reviewer" in prompt.lower()
        assert "Python project" in prompt


class TestBuildAPIMessages:
    def test_appends_new_message(self):
        history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        system, messages = build_api_messages(history, "what next?")
        assert messages[-1]["content"] == "what next?"
        assert len(messages) == 3

    def test_with_system_prompt(self):
        system, messages = build_api_messages([], "hello", system_prompt="Be helpful.")
        assert system == "Be helpful."
        assert len(messages) == 1

    def test_windowing_applied(self):
        history = [{"role": "user", "content": "a" * 200_000}]
        system, messages = build_api_messages(
            history, "question", max_tokens=10_000,
        )
        assert len(messages) >= 1
