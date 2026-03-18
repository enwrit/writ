"""Tests for the agent linter and scoring system."""

from __future__ import annotations

import json

from writ.core import linter
from writ.core.models import (
    CompositionConfig,
    CursorOverrides,
    FormatOverrides,
    InstructionConfig,
    LintResult,
)

# ===================================================================
# Existing rule tests
# ===================================================================


class TestLinter:
    def test_good_agent_passes(self, initialized_project, sample_agent):
        results = linter.lint(sample_agent)
        errors = [r for r in results if r.level == "error"]
        assert len(errors) == 0

    def test_empty_instructions_warning(self, initialized_project):
        agent = InstructionConfig(name="empty", instructions="")
        results = linter.lint(agent)
        assert any(r.rule == "instructions-empty" for r in results)

    def test_very_long_instructions(self, initialized_project):
        agent = InstructionConfig(
            name="verbose",
            instructions=" ".join(["word"] * 2500),
        )
        results = linter.lint(agent)
        assert any(r.rule == "instructions-long" for r in results)

    def test_very_short_instructions(self, initialized_project):
        agent = InstructionConfig(
            name="short", instructions="Be helpful.",
        )
        results = linter.lint(agent)
        assert any(r.rule == "instructions-short" for r in results)

    def test_missing_description(self, initialized_project):
        agent = InstructionConfig(
            name="nodesc", instructions="Do something useful.",
        )
        results = linter.lint(agent)
        assert any(r.rule == "description-missing" for r in results)

    def test_missing_tags(self, initialized_project):
        agent = InstructionConfig(
            name="notags", instructions="Instructions here.",
        )
        results = linter.lint(agent)
        assert any(r.rule == "tags-missing" for r in results)

    def test_bad_name_format(self, initialized_project):
        agent = InstructionConfig(
            name="My Agent!", instructions="Test",
        )
        results = linter.lint(agent)
        assert any(r.rule == "name-format" for r in results)

    def test_contradiction_detection(self, initialized_project):
        agent = InstructionConfig(
            name="contradicted",
            description="Test",
            tags=["test"],
            instructions=(
                "Always use TypeScript.\n"
                "Never use TypeScript."
            ),
        )
        results = linter.lint(agent)
        assert any(r.rule == "contradiction" for r in results)

    def test_missing_parent_warning(self, initialized_project):
        agent = InstructionConfig(
            name="orphan",
            instructions="Test",
            composition=CompositionConfig(
                inherits_from=["nonexistent"],
            ),
        )
        results = linter.lint(agent)
        assert any(r.rule == "inherit-missing" for r in results)


# ===================================================================
# v0.2.0: New rule tests
# ===================================================================


class TestWeakLanguage:
    def test_detects_try_to(self):
        agent = InstructionConfig(
            name="test",
            instructions="Try to keep functions short.",
        )
        results = linter.lint(agent)
        weak = [r for r in results if r.rule == "weak-language"]
        assert len(weak) >= 1
        assert weak[0].line is not None

    def test_detects_consider(self):
        agent = InstructionConfig(
            name="test",
            instructions="Consider using TypeScript.",
        )
        results = linter.lint(agent)
        assert any(r.rule == "weak-language" for r in results)

    def test_detects_you_should(self):
        agent = InstructionConfig(
            name="test",
            instructions="You should always write tests.",
        )
        results = linter.lint(agent)
        assert any(r.rule == "weak-language" for r in results)

    def test_no_trigger_on_imperative(self):
        agent = InstructionConfig(
            name="test",
            instructions="Use TypeScript. Write tests for all functions.",
        )
        results = linter.lint(agent)
        weak = [r for r in results if r.rule == "weak-language"]
        assert len(weak) == 0

    def test_skips_code_fences(self):
        agent = InstructionConfig(
            name="test",
            instructions=(
                "Use proper tools.\n"
                "```bash\n"
                "# try to install this\n"
                "npm install\n"
                "```\n"
                "Run `npm test` after changes."
            ),
        )
        results = linter.lint(agent)
        weak = [r for r in results if r.rule == "weak-language"]
        assert len(weak) == 0

    def test_multiple_matches_one_per_line(self):
        agent = InstructionConfig(
            name="test",
            instructions=(
                "Try to keep code clean.\n"
                "Consider using linting tools.\n"
                "Maybe add some tests."
            ),
        )
        results = linter.lint(agent)
        weak = [r for r in results if r.rule == "weak-language"]
        assert len(weak) == 3


class TestExpertPreamble:
    def test_detects_expert_preamble(self):
        agent = InstructionConfig(
            name="test",
            instructions=(
                "You are an expert Python developer.\n"
                "Use type hints everywhere."
            ),
        )
        results = linter.lint(agent)
        assert any(r.rule == "expert-preamble" for r in results)

    def test_detects_senior_variant(self):
        agent = InstructionConfig(
            name="test",
            instructions="You are a senior engineer. Write clean code.",
        )
        results = linter.lint(agent)
        assert any(r.rule == "expert-preamble" for r in results)

    def test_no_trigger_normal_start(self):
        agent = InstructionConfig(
            name="test",
            instructions="Use TypeScript for all code.",
        )
        results = linter.lint(agent)
        assert not any(
            r.rule == "expert-preamble" for r in results
        )


class TestInstructionBloat:
    def test_warns_over_2000_chars(self):
        agent = InstructionConfig(
            name="test",
            instructions="x " * 1100,  # ~2200 chars
        )
        results = linter.lint(agent)
        bloat = [r for r in results if r.rule == "instruction-bloat"]
        assert len(bloat) == 1
        assert bloat[0].level == "warning"

    def test_errors_over_5000_chars(self):
        agent = InstructionConfig(
            name="test",
            instructions="x " * 2600,  # ~5200 chars
        )
        results = linter.lint(agent)
        bloat = [r for r in results if r.rule == "instruction-bloat"]
        assert len(bloat) == 1
        assert bloat[0].level == "error"

    def test_no_trigger_short(self):
        agent = InstructionConfig(
            name="test",
            instructions="Use Python 3.11+. Run `pytest`.",
        )
        results = linter.lint(agent)
        assert not any(
            r.rule == "instruction-bloat" for r in results
        )


class TestNoVerification:
    def test_detects_no_verification(self):
        agent = InstructionConfig(
            name="test",
            instructions="Use TypeScript. Keep functions short.",
        )
        results = linter.lint(agent)
        assert any(r.rule == "no-verification" for r in results)

    def test_no_trigger_with_backtick_command(self):
        agent = InstructionConfig(
            name="test",
            instructions="Run `pytest` after changes.",
        )
        results = linter.lint(agent)
        assert not any(
            r.rule == "no-verification" for r in results
        )

    def test_no_trigger_with_test_keyword(self):
        agent = InstructionConfig(
            name="test",
            instructions="Always run tests before committing.",
        )
        results = linter.lint(agent)
        assert not any(
            r.rule == "no-verification" for r in results
        )


class TestHasCommands:
    def test_detects_no_commands(self):
        agent = InstructionConfig(
            name="test",
            instructions="Write clean code. Follow patterns.",
        )
        results = linter.lint(agent)
        assert any(r.rule == "has-commands" for r in results)

    def test_no_trigger_with_commands(self):
        agent = InstructionConfig(
            name="test",
            instructions="Run `npm install` and then `npm test`.",
        )
        results = linter.lint(agent)
        assert not any(
            r.rule == "has-commands" for r in results
        )


# ===================================================================
# Code fence awareness
# ===================================================================


class TestCodeFenceAwareness:
    def test_prose_extraction_strips_fences(self):
        text = (
            "Line 1\n"
            "```python\n"
            "x = try to do something\n"
            "```\n"
            "Line 2"
        )
        prose = linter.extract_prose_sections(text)
        full = "\n".join(prose)
        assert "try to do something" not in full
        assert "Line 1" in full
        assert "Line 2" in full

    def test_weak_language_inside_fence_ignored(self):
        agent = InstructionConfig(
            name="test",
            instructions=(
                "Use the API.\n"
                "```\n"
                "maybe try to consider if possible\n"
                "```\n"
                "Run `pytest`."
            ),
        )
        results = linter.lint(agent)
        assert not any(
            r.rule == "weak-language" for r in results
        )


# ===================================================================
# Scoring system tests
# ===================================================================


class TestScoring:
    def test_perfect_instruction_high_score(self):
        agent = InstructionConfig(
            name="good-agent",
            description="TypeScript code reviewer",
            tags=["typescript", "review"],
            instructions=(
                "# Code Review\n\n"
                "## Commands\n"
                "Run `npm test` before committing.\n"
                "Run `eslint .` to check style.\n\n"
                "## Rules\n"
                "- Always use TypeScript strict mode\n"
                "- Never commit without tests\n"
                "- Keep functions under 30 lines\n\n"
                "## Example\n"
                "```typescript\n"
                "function greet(name: string): string {\n"
                '  return `Hello, ${name}`;\n'
                "}\n"
                "```\n"
            ),
        )
        results = linter.lint(agent)
        score = linter.compute_score(agent, results)
        assert score.score >= 70
        assert len(score.dimensions) == 6
        assert all(d.score >= 10 for d in score.dimensions)
        assert all(d.score <= 100 for d in score.dimensions)

    def test_terrible_instruction_low_score(self):
        agent = InstructionConfig(
            name="bad",
            instructions=(
                "You are an expert programmer.\n"
                "Try to write clean code.\n"
                "Consider following best practices.\n"
                "Maybe you should be helpful.\n"
                "If possible, write tests.\n"
                "You could perhaps use linting."
            ),
        )
        results = linter.lint(agent)
        score = linter.compute_score(agent, results)
        assert score.score < 80
        assert len(score.suggestions) > 0

    def test_empty_instruction_minimum_score(self):
        agent = InstructionConfig(name="empty", instructions="")
        results = linter.lint(agent)
        score = linter.compute_score(agent, results)
        assert score.score >= 10
        assert score.score <= 70  # not "good"

    def test_headline_is_weighted_average(self):
        agent = InstructionConfig(
            name="test",
            description="A test agent",
            tags=["test"],
            instructions="Run `pytest` to verify. Always test.",
        )
        results = linter.lint(agent)
        score = linter.compute_score(agent, results)
        dims = {d.name: d.score for d in score.dimensions}

        expected = round(
            dims["clarity"] * 0.25
            + dims["verification"] * 0.25
            + dims["coverage"] * 0.20
            + dims["brevity"] * 0.15
            + dims["structure"] * 0.10
            + dims["examples"] * 0.05
        )
        expected = max(10, min(100, expected))
        assert abs(score.score - expected) <= 1

    def test_raw_signals_present(self):
        agent = InstructionConfig(
            name="test",
            instructions="Run `pytest`. Use TypeScript.",
        )
        results = linter.lint(agent)
        score = linter.compute_score(agent, results)
        assert score.raw_signals is not None
        assert "weak_language_count" in score.raw_signals
        assert "char_count" in score.raw_signals
        assert "has_commands" in score.raw_signals

    def test_suggestions_target_lowest_dims(self):
        agent = InstructionConfig(
            name="test",
            instructions="Try to be helpful. Maybe write code.",
        )
        results = linter.lint(agent)
        score = linter.compute_score(agent, results)
        assert len(score.suggestions) > 0
        assert len(score.suggestions) <= 3

    def test_dimension_score_bounds(self):
        from writ.core.linter import _compute_dimension_score

        issues = [
            LintResult(
                level="error", message="bad",
                base_penalty=25,
            ),
            LintResult(
                level="error", message="bad2",
                base_penalty=25,
            ),
            LintResult(
                level="error", message="bad3",
                base_penalty=25,
            ),
        ]
        score = _compute_dimension_score(issues, 500)
        assert 10 <= score <= 100

    def test_dimension_score_no_issues_is_100(self):
        from writ.core.linter import _compute_dimension_score

        score = _compute_dimension_score([], 500)
        assert score == 100

    def test_length_normalization(self):
        from writ.core.linter import _compute_dimension_score

        issue = [LintResult(
            level="warning", message="bad", base_penalty=15,
        )]
        short_score = _compute_dimension_score(issue, 200)
        long_score = _compute_dimension_score(issue, 4000)
        assert long_score >= short_score


# ===================================================================
# CLI flags tests
# ===================================================================


class TestCLIFlags:
    def test_file_flag_md(self, tmp_path):
        md_file = tmp_path / "test-rule.md"
        md_file.write_text(
            "# My Rule\n\n"
            "Use Python 3.11+. Run `pytest`.\n",
            encoding="utf-8",
        )
        from writ.commands.lint import _parse_file_to_config

        config = _parse_file_to_config(md_file)
        assert config.name == "test-rule"
        assert "pytest" in config.instructions

    def test_file_flag_yaml(self, tmp_path):
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text(
            "name: my-agent\n"
            "description: Test agent\n"
            "instructions: |\n"
            "  Use Python. Run `pytest`.\n",
            encoding="utf-8",
        )
        from writ.commands.lint import _parse_file_to_config

        config = _parse_file_to_config(yaml_file)
        assert config.name == "my-agent"
        assert config.description == "Test agent"

    def test_file_flag_mdc_with_frontmatter(self, tmp_path):
        mdc_file = tmp_path / "rule.mdc"
        mdc_file.write_text(
            "---\n"
            "description: A cursor rule\n"
            "globs: '*.py'\n"
            "---\n"
            "Use type hints. Run `mypy .` to check.\n",
            encoding="utf-8",
        )
        from writ.commands.lint import _parse_file_to_config

        config = _parse_file_to_config(mdc_file)
        assert config.name == "rule"
        assert "type hints" in config.instructions

    def test_json_output_valid(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "Use Python. Run `pytest`.\n",
            encoding="utf-8",
        )
        from writ.commands.lint import _parse_file_to_config

        config = _parse_file_to_config(md_file)
        results = linter.lint(config)
        score = linter.compute_score(config, results)
        json_str = score.model_dump_json()
        data = json.loads(json_str)
        assert "score" in data
        assert "dimensions" in data
        assert len(data["dimensions"]) == 6

    def test_ci_threshold(self, tmp_path, initialized_project):
        from typer.testing import CliRunner

        from writ.cli import app

        md_file = tmp_path / "bad.md"
        md_file.write_text(
            "Be helpful. Try to write clean code.",
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["lint", "--file", str(md_file), "--ci", "--min-score", "95"],
        )
        assert result.exit_code == 1

    def test_score_only_flag(self, tmp_path):
        from typer.testing import CliRunner

        from writ.cli import app

        md_file = tmp_path / "ok.md"
        md_file.write_text(
            "# Rules\nUse Python. Run `pytest`.\n",
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["lint", "--file", str(md_file), "--score"],
        )
        assert result.exit_code == 0
        output = result.output.strip()
        assert any(c.isdigit() for c in output)

    def test_file_flag_no_init_required(self, tmp_path, monkeypatch):
        """--file works in a bare directory (no .writ/)."""
        monkeypatch.chdir(tmp_path)
        md_file = tmp_path / "standalone.md"
        md_file.write_text(
            "Use Go. Run `go test ./...`.\n",
            encoding="utf-8",
        )

        from typer.testing import CliRunner

        from writ.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["lint", "--file", str(md_file)],
        )
        assert result.exit_code == 0
        assert "Score" in result.output

    def test_badge_flag(self, tmp_path):
        from typer.testing import CliRunner

        from writ.cli import app

        md_file = tmp_path / "ok.md"
        md_file.write_text(
            "# Rules\nUse Python. Run `pytest`. Always test.\n",
            encoding="utf-8",
        )
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["lint", "--file", str(md_file), "--badge"],
        )
        assert result.exit_code == 0
        assert "shields.io" in result.output
        assert "writ_lint" in result.output


# ===================================================================
# v0.2.1 rule tests
# ===================================================================


class TestExcessiveExamples:
    def test_flags_more_than_five_blocks(self):
        blocks = "\n\n".join([f"```\ncode{i}\n```" for i in range(6)])
        agent = InstructionConfig(
            name="test",
            instructions=f"Use Python.\n\n{blocks}",
        )
        results = linter.lint(agent)
        assert any(r.rule == "excessive-examples" for r in results)

    def test_no_trigger_few_blocks(self):
        agent = InstructionConfig(
            name="test",
            instructions="Use Python.\n\n```\ncode\n```",
        )
        results = linter.lint(agent)
        assert not any(r.rule == "excessive-examples" for r in results)


class TestMissingMetadata:
    def test_mdc_without_frontmatter(self, tmp_path):
        mdc = tmp_path / "rule.mdc"
        mdc.write_text("No frontmatter here.\n", encoding="utf-8")
        agent = InstructionConfig(
            name="rule",
            instructions="No frontmatter here.",
        )
        results = linter.lint(agent, source_path=mdc)
        assert any(r.rule == "missing-metadata" for r in results)

    def test_yaml_missing_task_type(self):
        agent = InstructionConfig(
            name="test",
            description="A good description here",
            instructions="Use Python.",
        )
        results = linter.lint(agent, source_path=None)
        assert any(r.rule == "missing-metadata" for r in results)


class TestEmptyGlobs:
    def test_flags_empty_globs(self):
        agent = InstructionConfig(
            name="test",
            instructions="Use Python.",
            format_overrides=FormatOverrides(
                cursor=CursorOverrides(globs=""),
            ),
        )
        results = linter.lint(agent)
        assert any(r.rule == "empty-globs" for r in results)

    def test_no_trigger_valid_globs(self):
        agent = InstructionConfig(
            name="test",
            instructions="Use Python.",
            format_overrides=FormatOverrides(
                cursor=CursorOverrides(globs="*.py"),
            ),
        )
        results = linter.lint(agent)
        assert not any(r.rule == "empty-globs" for r in results)


class TestDeadContent:
    def test_detects_todo(self):
        agent = InstructionConfig(
            name="test",
            instructions="Use Python.\n\n# TODO: add more",
        )
        results = linter.lint(agent)
        assert any(r.rule == "dead-content" for r in results)

    def test_detects_fixme(self):
        agent = InstructionConfig(
            name="test",
            instructions="Use Python.\n\n// FIXME: fix this",
        )
        results = linter.lint(agent)
        assert any(r.rule == "dead-content" for r in results)

    def test_skips_code_fences(self):
        agent = InstructionConfig(
            name="test",
            instructions=(
                "Use Python.\n"
                "```\n# TODO in code - ok\n```\n"
                "Run `pytest`."
            ),
        )
        results = linter.lint(agent)
        assert not any(r.rule == "dead-content" for r in results)


class TestHasBoundaries:
    def test_flags_no_boundaries(self):
        agent = InstructionConfig(
            name="test",
            instructions="Use Python. Write clean code. Be helpful.",
        )
        results = linter.lint(agent)
        assert any(r.rule == "has-boundaries" for r in results)

    def test_no_trigger_with_always(self):
        agent = InstructionConfig(
            name="test",
            instructions="Always use TypeScript. Never use any.",
        )
        results = linter.lint(agent)
        assert not any(r.rule == "has-boundaries" for r in results)


class TestHasExamples:
    def test_flags_no_code_blocks(self):
        agent = InstructionConfig(
            name="test",
            instructions="Use Python. Write tests.",
        )
        results = linter.lint(agent)
        assert any(r.rule == "has-examples" for r in results)

    def test_no_trigger_with_blocks(self):
        agent = InstructionConfig(
            name="test",
            instructions="Use Python.\n\n```\nprint(1)\n```",
        )
        results = linter.lint(agent)
        assert not any(r.rule == "has-examples" for r in results)


class TestMixedConcerns:
    def test_flags_many_topic_clusters(self):
        agent = InstructionConfig(
            name="test",
            instructions=(
                "# Testing\nUse pytest.\n\n"
                "# Security\nUse HTTPS.\n\n"
                "# Performance\nUse caching.\n\n"
                "# Architecture\nUse layers."
            ),
        )
        results = linter.lint(agent)
        assert any(r.rule == "mixed-concerns" for r in results)
