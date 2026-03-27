"""Tests for the agent linter and scoring system."""

from __future__ import annotations

import json

from writ.core import linter
from writ.core.models import (
    CompositionConfig,
    CursorOverrides,
    FormatOverrides,
    InstructionConfig,
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
            instructions=" ".join(["word"] * 5500),
        )
        results = linter.lint(agent)
        assert any(r.rule == "instructions-long" for r in results)

    def test_moderate_length_no_warning(self, initialized_project):
        agent = InstructionConfig(
            name="moderate",
            instructions=" ".join(["word"] * 2500),
        )
        results = linter.lint(agent)
        assert not any(r.rule == "instructions-long" for r in results)

    def test_very_short_instructions(self, initialized_project):
        agent = InstructionConfig(
            name="short", instructions="Be helpful.",
        )
        results = linter.lint(agent)
        assert any(r.rule == "instructions-short" for r in results)

    def test_missing_description(self, initialized_project):
        agent = InstructionConfig(
            name="nodesc", task_type="agent",
            instructions="Do something useful.",
        )
        results = linter.lint(agent)
        assert any(r.rule == "description-missing" for r in results)

    def test_missing_tags(self, initialized_project):
        agent = InstructionConfig(
            name="notags", task_type="agent",
            instructions="Instructions here.",
        )
        results = linter.lint(agent)
        assert any(r.rule == "tags-missing" for r in results)

    def test_no_writ_rules_for_generic_instructions(self):
        """Writ-specific rules should NOT fire for generic instructions."""
        agent = InstructionConfig(
            name="generic", instructions="Be helpful.",
        )
        results = linter.lint(agent)
        writ_rules = {
            "description-missing", "tags-missing",
            "project-context-missing", "inherit-missing",
        }
        for r in results:
            assert r.rule not in writ_rules, (
                f"Writ-specific rule '{r.rule}' should not fire "
                "for generic (non-writ) instructions"
            )

    def test_bad_name_format(self, initialized_project):
        """name-format only fires for writ-managed instructions."""
        agent = InstructionConfig(
            name="My Agent!", instructions="Test",
            task_type="agent",
        )
        results = linter.lint(agent)
        assert any(r.rule == "name-format" for r in results)

    def test_bad_name_format_skipped_for_files(self):
        """name-format does NOT fire for file-based linting (non writ-managed)."""
        agent = InstructionConfig(
            name="AGENTS", instructions="Test instructions here.",
        )
        results = linter.lint(agent)
        assert not any(r.rule == "name-format" for r in results)

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
            task_type="agent",
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
        assert len(weak) == 1
        assert "try to" in weak[0].message.lower()

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

    def test_multiple_matches_consolidated(self):
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
        assert len(weak) == 1
        assert "try to" in weak[0].message.lower()
        assert "consider" in weak[0].message.lower()
        assert "maybe" in weak[0].message.lower()


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
    def test_no_trigger_2200_chars(self):
        agent = InstructionConfig(
            name="test",
            instructions="x " * 1100,  # ~2200 chars
        )
        results = linter.lint(agent)
        bloat = [r for r in results if r.rule == "instruction-bloat"]
        assert len(bloat) == 0

    def test_no_trigger_5200_chars(self):
        agent = InstructionConfig(
            name="test",
            instructions="x " * 2600,  # ~5200 chars
        )
        results = linter.lint(agent)
        bloat = [r for r in results if r.rule == "instruction-bloat"]
        assert len(bloat) == 0

    def test_info_over_7500_chars(self):
        agent = InstructionConfig(
            name="test",
            instructions="x " * 4000,  # ~8000 chars
        )
        results = linter.lint(agent)
        bloat = [r for r in results if r.rule == "instruction-bloat"]
        assert len(bloat) == 1
        assert bloat[0].level == "info"

    def test_info_over_20000_chars(self):
        agent = InstructionConfig(
            name="test",
            instructions="x " * 11000,  # ~22000 chars
        )
        results = linter.lint(agent)
        bloat = [r for r in results if r.rule == "instruction-bloat"]
        assert len(bloat) == 1
        assert bloat[0].level == "info"
        msg = bloat[0].message.lower()
        assert "over-specification" in msg or "redundant" in msg

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
    def test_detects_no_commands_with_verification(self):
        """has-commands fires when no backtick commands AND no-verification didn't fire."""
        agent = InstructionConfig(
            name="test",
            instructions="Run tests often. Verify your work.",
        )
        results = linter.lint(agent)
        assert any(r.rule == "has-commands" for r in results)

    def test_suppressed_when_no_verification_fires(self):
        """has-commands is suppressed when no-verification already covers it."""
        agent = InstructionConfig(
            name="test",
            instructions="Write clean code. Follow patterns.",
        )
        results = linter.lint(agent)
        assert any(r.rule == "no-verification" for r in results)
        assert not any(r.rule == "has-commands" for r in results)

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
    def test_good_instruction_decent_score(self):
        agent = InstructionConfig(
            name="good-agent",
            description="TypeScript code reviewer",
            tags=["typescript", "review"],
            task_type="agent",
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
        assert score.score >= 30
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
            task_type="agent",
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

    def test_v2_scorer_bounds(self):
        from writ.core.linter import _v2_score_clarity

        low = _v2_score_clarity({
            "specificity_density": 0.0,
            "imperative_ratio": 0.0,
            "quantitative_count": 0,
            "backtick_command_count": 0,
            "vague_ratio": 1.0,
            "expert_preamble_present": True,
        })
        assert 10 <= low <= 30

        high = _v2_score_clarity({
            "specificity_density": 0.5,
            "imperative_ratio": 1.0,
            "quantitative_count": 5,
            "backtick_command_count": 5,
            "vague_ratio": 0.0,
            "expert_preamble_present": False,
        })
        assert 80 <= high <= 100

    def test_v2_verification_level_mapping(self):
        from writ.core.linter import _v2_score_verification

        assert _v2_score_verification("") == 10
        assert _v2_score_verification("test it") == 20
        assert _v2_score_verification("Run `pytest`") >= 70
        assert _v2_score_verification(
            "Done when `pytest` passes with 0 failures"
        ) >= 85

    def test_v2_length_factor(self):
        from writ.core.linter import length_factor

        assert length_factor(50) < length_factor(500)
        assert length_factor(1000) < length_factor(3500)
        assert length_factor(3500) == 1.0
        assert length_factor(8000) <= 1.0
        assert length_factor(30000) < length_factor(8000)


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

    def test_yaml_missing_task_type(self, tmp_path):
        writ_dir = tmp_path / ".writ" / "agents"
        writ_dir.mkdir(parents=True)
        src = writ_dir / "test.yaml"
        src.write_text("name: test\n", encoding="utf-8")
        agent = InstructionConfig(
            name="test",
            description="A good description here",
            instructions="Use Python.",
        )
        results = linter.lint(agent, source_path=src)
        assert any(r.rule == "missing-metadata" for r in results)

    def test_no_metadata_warning_for_generic_files(self):
        """Non-writ instructions should NOT get task_type/description warnings."""
        agent = InstructionConfig(
            name="test",
            instructions="Use Python.",
        )
        results = linter.lint(agent, source_path=None)
        metadata_msgs = [
            r for r in results
            if r.rule == "missing-metadata"
            and "task_type" in r.message
        ]
        assert not metadata_msgs


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


class TestGeneralKnowledge:
    def test_flags_restated_knowledge(self):
        """3+ general knowledge rules should trigger."""
        agent = InstructionConfig(
            name="test",
            instructions=(
                "- Use meaningful variable names\n"
                "- Avoid magic numbers\n"
                "- Keep functions small and focused\n"
                "- Use proper error handling"
            ),
        )
        results = linter.lint(agent)
        assert any(r.rule == "general-knowledge" for r in results)

    def test_no_trigger_few_matches(self):
        """1-2 matches should not trigger."""
        agent = InstructionConfig(
            name="test",
            instructions=(
                "- Use meaningful variable names\n"
                "- Run `pytest -v` before committing\n"
                "- All endpoints must return JSON"
            ),
        )
        results = linter.lint(agent)
        assert not any(r.rule == "general-knowledge" for r in results)


class TestWallOfText:
    def test_flags_long_prose_block(self):
        """6+ consecutive prose lines should trigger."""
        agent = InstructionConfig(
            name="test",
            instructions=(
                "This is a long paragraph about coding.\n"
                "It goes on and on without any structure.\n"
                "There are no bullet points here at all.\n"
                "Nor are there any code examples to speak of.\n"
                "The agent will likely skip this entire block.\n"
                "Because it has no actionable content whatsoever."
            ),
        )
        results = linter.lint(agent)
        assert any(r.rule == "wall-of-text" for r in results)

    def test_no_trigger_with_structure(self):
        """Prose interspersed with structural elements should not trigger."""
        agent = InstructionConfig(
            name="test",
            instructions=(
                "This project uses FastAPI.\n"
                "- Always use async endpoints\n"
                "- Run `pytest` before committing\n"
                "We follow strict typing.\n"
                "- Use `mypy --strict` for type checking\n"
                "- All functions need return types"
            ),
        )
        results = linter.lint(agent)
        assert not any(r.rule == "wall-of-text" for r in results)


# ===================================================================
# v2 anchor calibration tests
# ===================================================================


class TestV2Anchors:
    """Anchor instructions with expected score ranges.

    Any scoring change that breaks these is a regression.
    """

    def test_anchor_terrible(self):
        agent = InstructionConfig(
            name="terrible",
            task_type="agent",
            instructions="You are an expert. Write clean code.",
        )
        results = linter.lint(agent)
        score = linter.compute_score(agent, results)
        assert score.score <= 25, (
            f"Terrible instruction scored {score.score}, expected <= 25"
        )
        assert score.grade == "F" or score.grade == "D"

    def test_anchor_mediocre(self):
        agent = InstructionConfig(
            name="mediocre",
            description="Generic coding helper",
            task_type="agent",
            instructions=(
                "You are a helpful coding assistant.\n"
                "Try to write good code.\n"
                "Consider testing your changes.\n"
                "Handle errors properly.\n"
                "If possible, follow best practices.\n"
                "Maybe add some documentation."
            ),
        )
        results = linter.lint(agent)
        score = linter.compute_score(agent, results)
        assert 14 <= score.score <= 30, (
            f"Mediocre scored {score.score}, expected 14-30"
        )

    def test_anchor_good(self):
        agent = InstructionConfig(
            name="good-agent",
            description="Python code reviewer",
            task_type="agent",
            tags=["python", "review"],
            instructions=(
                "# Python Code Review\n\n"
                "## Commands\n"
                "Run `pytest -v` before approving.\n"
                "Run `ruff check src/` for linting.\n\n"
                "## Rules\n"
                "- Always use type hints on function signatures\n"
                "- Never use `print()` for logging; "
                "use the `logging` module\n"
                "- Keep functions under 40 lines\n"
                "- Require docstrings on all public functions\n\n"
                "## Don't\n"
                "- Do not approve PRs without passing tests\n"
                "- Never merge directly to main\n\n"
                "## Style\n"
                "- Follow PEP 8 naming conventions\n"
                "- Use `pathlib.Path` instead of `os.path`\n\n"
                "## Example\n"
                "```python\n"
                "def calculate_total("
                "items: list[float]) -> float:\n"
                '    """Sum all item prices."""\n'
                "    return sum(items)\n"
                "```\n"
            ),
        )
        results = linter.lint(agent)
        score = linter.compute_score(agent, results)
        assert 55 <= score.score <= 80, (
            f"Good instruction scored {score.score}, "
            f"expected 55-80"
        )

    def test_anchor_excellent(self):
        agent = InstructionConfig(
            name="excellent-agent",
            description="Production deployment reviewer",
            task_type="agent",
            tags=["devops", "review", "production"],
            instructions=(
                "---\n"
                "description: Production deployment reviewer\n"
                "---\n\n"
                "# Production Deployment Review\n\n"
                "## Commands\n"
                "Run `pytest --cov=src/ --cov-fail-under=80` "
                "to verify test coverage.\n"
                "Run `docker build -t app:test .` to verify "
                "the build succeeds.\n"
                "Run `trivy image app:test` for security "
                "scanning.\n\n"
                "## Testing\n"
                "- All tests must pass with 0 failures\n"
                "- Coverage must exceed 80%\n"
                "- Integration tests must include database "
                "migrations\n\n"
                "## Boundaries\n"
                "- Never deploy on Fridays after 3pm\n"
                "- Always require 2 approvals for production\n"
                "- Do not bypass CI checks\n"
                "- Must not expose internal APIs publicly\n\n"
                "## Error Handling\n"
                "- All API endpoints must return structured "
                "error responses\n"
                "- Use circuit breakers for external service "
                "calls\n"
                "- Log all errors with correlation IDs\n\n"
                "## Style\n"
                "- Follow the ADR template for architecture "
                "decisions\n"
                "- Use conventional commits format\n"
                "- Document all environment variables in "
                "`.env.example`\n\n"
                "## Example\n"
                "```yaml\n"
                "# Good: structured error response\n"
                "status: 422\n"
                "body:\n"
                '  error: "validation_failed"\n'
                '  message: "Email format invalid"\n'
                "  field: email\n"
                "```\n\n"
                "```yaml\n"
                "# Bad: unstructured error\n"
                "status: 500\n"
                'body: "Something went wrong"\n'
                "```\n\n"
                "## Definition of Done\n"
                "Task is complete when `pytest` passes with "
                "80%+ coverage, `docker build` succeeds, "
                "and `trivy` reports no critical "
                "vulnerabilities.\n"
            ),
        )
        results = linter.lint(agent)
        score = linter.compute_score(agent, results)
        assert 70 <= score.score <= 100, (
            f"Excellent instruction scored {score.score}, "
            f"expected 70-100"
        )

    # -- Edge cases --

    def test_edge_empty_string(self):
        agent = InstructionConfig(
            name="empty", task_type="agent",
            instructions="",
        )
        results = linter.lint(agent)
        score = linter.compute_score(agent, results)
        assert score.grade == "F"

    def test_edge_tech_list_only(self):
        agent = InstructionConfig(
            name="tech-list", task_type="agent",
            instructions="Python, TypeScript, React, Docker.",
        )
        results = linter.lint(agent)
        score = linter.compute_score(agent, results)
        assert score.grade in ("D", "F")

    def test_edge_expert_preamble_bloat(self):
        agent = InstructionConfig(
            name="bloat", task_type="agent",
            instructions=(
                "You are a world-class senior principal "
                "staff engineer with 20 years of experience "
                "in distributed systems, machine learning, "
                "and cloud architecture.\n"
                "Try to write clean code.\n"
                "Consider best practices.\n"
                "Maybe add tests if possible.\n"
                "You should perhaps use linting.\n"
                "If you can, handle errors."
            ),
        )
        results = linter.lint(agent)
        score = linter.compute_score(agent, results)
        assert score.grade in ("F", "D")

    def test_edge_single_command(self):
        agent = InstructionConfig(
            name="cmd", task_type="agent",
            instructions="Run `pytest`.",
        )
        results = linter.lint(agent)
        score = linter.compute_score(agent, results)
        assert score.grade in ("C", "D", "F")

    def test_edge_concise_3_commands(self):
        agent = InstructionConfig(
            name="concise", task_type="agent",
            description="Build verifier",
            instructions=(
                "Run `pytest -v` to verify tests.\n"
                "Run `ruff check src/` for linting.\n"
                "Run `mypy src/` for type checking.\n"
                "Never commit with failing tests.\n"
                "Always use type hints."
            ),
        )
        results = linter.lint(agent)
        score = linter.compute_score(agent, results)
        assert score.grade in ("B", "C")


# ===================================================================
# New: ML issue gating tests
# ===================================================================


class TestMLIssueGating:
    """Verify Tier 1 issues are gated by ML dimension scores."""

    def test_no_verification_suppressed_when_ml_high(self):
        from writ.core.ml_scorer import _gate_tier1_issues
        from writ.core.models import LintResult

        issues = [
            LintResult(
                level="info", rule="no-verification",
                message="No verification steps found.",
            ),
        ]
        predicted = {"verification": 70, "examples": 40}
        filtered = _gate_tier1_issues(issues, predicted)
        assert len(filtered) == 0

    def test_no_verification_kept_when_ml_low(self):
        from writ.core.ml_scorer import _gate_tier1_issues
        from writ.core.models import LintResult

        issues = [
            LintResult(
                level="info", rule="no-verification",
                message="No verification steps found.",
            ),
        ]
        predicted = {"verification": 40, "examples": 40}
        filtered = _gate_tier1_issues(issues, predicted)
        assert len(filtered) == 1

    def test_always_keep_rules_not_gated(self):
        from writ.core.ml_scorer import _gate_tier1_issues
        from writ.core.models import LintResult

        issues = [
            LintResult(level="warning", rule="weak-language",
                       message="Vague language."),
            LintResult(level="error", rule="contradiction",
                       message="Contradiction found."),
            LintResult(level="info", rule="no-verification",
                       message="No verification."),
        ]
        predicted = {"verification": 80, "examples": 80}
        filtered = _gate_tier1_issues(issues, predicted)
        rules = [i.rule for i in filtered]
        assert "weak-language" in rules
        assert "contradiction" in rules
        assert "no-verification" not in rules

    def test_instruction_bloat_gated_by_brevity(self):
        from writ.core.ml_scorer import _gate_tier1_issues
        from writ.core.models import LintResult

        issues = [
            LintResult(level="info", rule="instruction-bloat",
                       message="Instructions are 8,000 chars."),
        ]
        predicted = {"brevity": 75}
        filtered = _gate_tier1_issues(issues, predicted)
        assert len(filtered) == 0


# ===================================================================
# New: Text quality signal tests
# ===================================================================


class TestTextQualitySignals:
    """Test the four new text quality signals."""

    def test_contextual_redundancy_low_for_unique_sections(self):
        text = (
            "# Setup\nInstall Python 3.11 and configure virtualenv.\n\n"
            "# Testing\nRun pytest with coverage to verify all endpoints.\n\n"
            "# Deployment\nUse Docker containers on Kubernetes cluster.\n"
        )
        r = linter._compute_contextual_redundancy(text)
        assert 0.0 <= r <= 0.4

    def test_contextual_redundancy_high_for_repeated_content(self):
        text = (
            "# Section A\n"
            "Use Python for development and ensure that all code is "
            "properly tested with comprehensive unit tests and integration tests.\n\n"
            "# Section B\n"
            "Use Python for development and ensure that all code is "
            "properly tested with comprehensive unit tests and integration tests.\n\n"
            "# Section C\n"
            "Use Python for development and ensure that all code is "
            "properly tested with comprehensive unit tests and integration tests.\n"
        )
        r = linter._compute_contextual_redundancy(text)
        assert r > 0.3

    def test_information_density_v2_range(self):
        text = "Use strict TypeScript. Run `pytest -v`. Never use `any`."
        d = linter._compute_information_density_v2(text)
        assert 0.0 <= d <= 1.0

    def test_information_density_v2_verbose_lower(self):
        verbose = (
            "In order to ensure that the code is of high quality, "
            "it is recommended that you should take into consideration "
            "the fact that testing is important. It should be noted that "
            "as a general rule, it is worth noting that code quality matters. "
            "It is important to remember that in the context of development, "
            "with regard to best practices, for the purpose of maintaining "
            "code quality, you should consider writing tests."
        )
        concise = (
            "Write tests for all public functions. "
            "Maintain 80% code coverage. "
            "Run `pytest -v` before committing."
        )
        d_verbose = linter._compute_information_density_v2(verbose)
        d_concise = linter._compute_information_density_v2(concise)
        assert d_verbose < d_concise

    def test_duplicate_ratio_zero_for_unique(self):
        text = " ".join(f"word{i}" for i in range(100))
        r = linter._compute_duplicate_ratio(text)
        assert r < 0.1

    def test_duplicate_ratio_high_for_repeated(self):
        block = "Always use type hints. Never use any type. Run pytest first. "
        text = (block * 10).strip()
        r = linter._compute_duplicate_ratio(text)
        assert r > 0.2

    def test_prose_ratio_low_for_structured(self):
        text = (
            "# Rules\n"
            "- Use TypeScript\n"
            "- Run `pytest`\n"
            "- Never skip tests\n"
            "```bash\npytest -v\n```\n"
            "| Tool | Command |\n"
            "| --- | --- |\n"
            "| Lint | `ruff check` |\n"
        )
        r = linter._compute_prose_ratio(text)
        assert r < 0.3

    def test_prose_ratio_high_for_prose(self):
        text = (
            "This is a long paragraph about code quality and how to "
            "properly structure your applications. You should always "
            "think about the architecture before writing code.\n\n"
            "Another paragraph about testing strategies and deployment "
            "pipelines that goes on for quite a while with many words."
        )
        r = linter._compute_prose_ratio(text)
        assert r > 0.5

    def test_signals_in_raw_signals(self):
        agent = InstructionConfig(
            name="test", task_type="agent",
            description="Test agent",
            instructions=(
                "# Rules\n"
                "Use Python 3.11+.\n"
                "Run `pytest -v` for testing.\n"
                "Never use `print()` for logging.\n"
            ),
        )
        results = linter.lint(agent)
        score = linter.compute_score(agent, results)
        raw = score.raw_signals
        assert "contextual_redundancy" in raw
        assert "information_density_v2" in raw
        assert "duplicate_ratio" in raw
        assert "prose_ratio" in raw


# ===================================================================
# New: Length factor tests
# ===================================================================


class TestLengthFactor:
    """Test the updated length_factor curve."""

    def test_very_short(self):
        assert linter.length_factor(50) == 0.3

    def test_short(self):
        assert linter.length_factor(300) == 0.6

    def test_medium(self):
        assert linter.length_factor(1000) == 0.9

    def test_neutral_zone(self):
        assert linter.length_factor(3500) == 1.0
        assert linter.length_factor(5000) == 1.0

    def test_long(self):
        assert linter.length_factor(10000) == 0.95

    def test_very_long(self):
        assert linter.length_factor(20000) == 0.85

    def test_extreme(self):
        assert linter.length_factor(30000) == 0.75


# ===================================================================
# New: Critical caps tests
# ===================================================================


class TestCriticalCaps:
    """Verify instruction-bloat-5k cap was removed."""

    def test_no_bloat_5k_cap(self):
        assert "instruction-bloat-5k" not in linter.CRITICAL_CAPS

    def test_contradiction_cap_still_present(self):
        assert "contradiction" in linter.CRITICAL_CAPS
        assert linter.CRITICAL_CAPS["contradiction"] == 25
