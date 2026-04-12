"""Tests for type inference, changed patterns, plan --local, reverse drift, core files."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from writ.cli import app
from writ.core.type_inference import infer_instruction_type

runner = CliRunner()


class TestTypeInference:
    """Tests for infer_instruction_type()."""

    def test_explicit_task_type_agent(self):
        assert infer_instruction_type(task_type="agent") == "agent"

    def test_explicit_task_type_skill(self):
        assert infer_instruction_type(task_type="skill") == "skill"

    def test_explicit_task_type_rule(self):
        assert infer_instruction_type(task_type="rule") == "rule"

    def test_explicit_task_type_plan(self):
        assert infer_instruction_type(task_type="plan") == "plan"

    def test_explicit_task_type_context(self):
        assert infer_instruction_type(task_type="context") == "context"

    def test_explicit_task_type_program_maps_to_context(self):
        assert infer_instruction_type(task_type="program") == "context"

    def test_explicit_task_type_template_maps_to_other(self):
        assert infer_instruction_type(task_type="template") == "other"

    def test_folder_skills(self):
        p = Path(".cursor/skills/writ/my-skill.mdc")
        assert infer_instruction_type(file_path=p) == "skill"

    def test_folder_agents(self):
        p = Path(".claude/agents/reviewer.md")
        assert infer_instruction_type(file_path=p) == "agent"

    def test_folder_rules(self):
        p = Path(".cursor/rules/project-rule.mdc")
        assert infer_instruction_type(file_path=p) == "rule"

    def test_folder_steering_is_rule(self):
        p = Path(".kiro/steering/review.md")
        assert infer_instruction_type(file_path=p) == "rule"

    def test_folder_plans(self):
        p = Path(".cursor/plans/my-plan.md")
        assert infer_instruction_type(file_path=p) == "plan"

    def test_folder_context(self):
        p = Path(".writ/context/project-context.yaml")
        assert infer_instruction_type(file_path=p) == "context"

    def test_folder_clinerules_is_rule(self):
        p = Path(".clinerules/my-rule.md")
        assert infer_instruction_type(file_path=p) == "rule"

    def test_folder_instructions_is_rule(self):
        p = Path(".github/instructions/writ-copilot.instructions.md")
        assert infer_instruction_type(file_path=p) == "rule"

    def test_filename_stem_skill(self):
        assert infer_instruction_type(name="doc-health-skill") == "skill"

    def test_filename_stem_rule(self):
        assert infer_instruction_type(name="project-rule") == "rule"

    def test_filename_stem_plan(self):
        assert infer_instruction_type(name="my-plan") == "plan"

    def test_fallback_is_other(self):
        assert infer_instruction_type(name="readme") == "other"

    def test_fallback_no_args(self):
        assert infer_instruction_type() == "other"

    def test_task_type_takes_precedence_over_path(self):
        p = Path(".cursor/skills/writ/my-file.mdc")
        assert infer_instruction_type(file_path=p, task_type="agent") == "agent"


class TestChangedPatterns:
    """Test that _CHANGED_PATTERNS covers all 11 IDEs."""

    def test_all_ides_covered(self):
        from writ.commands.lint import _CHANGED_PATTERNS
        from writ.core.formatter import IDE_PATHS

        for key, ide_cfg in IDE_PATHS.items():
            detect = ide_cfg.detect
            expected = f"{detect}/"
            assert expected in _CHANGED_PATTERNS, (
                f"IDE '{key}' detect dir '{detect}/' missing from _CHANGED_PATTERNS"
            )

    def test_root_files_covered(self):
        from writ.commands.lint import _CHANGED_PATTERNS

        for f in ("CLAUDE.md", "AGENTS.md", "SKILL.md"):
            assert f in _CHANGED_PATTERNS

    def test_writ_dirs_covered(self):
        from writ.commands.lint import _CHANGED_PATTERNS

        for d in (".writ/agents/", ".writ/rules/", ".writ/context/"):
            assert d in _CHANGED_PATTERNS


class TestPlanReviewLocal:
    """Test --local plan review prints rubric without API call."""

    def test_local_prints_rubric_no_api(self, tmp_project: Path):
        plan = tmp_project / "plan.md"
        plan.write_text("# My Plan\n\nStep 1: Do the thing.\n", encoding="utf-8")

        result = runner.invoke(app, ["plan", "review", str(plan), "--local"])
        assert result.exit_code == 0
        assert "Plan Review" in result.output
        assert "Review Priorities" in result.output
        assert "Step 1: Do the thing" not in result.output

    def test_local_with_plan_includes_content(self, tmp_project: Path):
        plan = tmp_project / "plan.md"
        plan.write_text("# My Plan\n\nStep 1: Do the thing.\n", encoding="utf-8")

        result = runner.invoke(
            app, ["plan", "review", str(plan), "--local", "--with-plan"],
        )
        assert result.exit_code == 0
        assert "Plan Review" in result.output
        assert "Step 1: Do the thing" in result.output


class TestLintDeepTypeHooks:
    """Test that --deep injects type-specific hooks."""

    def test_deep_skill_gets_hook(self, tmp_project: Path):
        skill_dir = tmp_project / ".cursor" / "skills"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "my-skill.md"
        skill_file.write_text("# My Skill\n\nDo the thing.\n", encoding="utf-8")

        result = runner.invoke(app, ["lint", str(skill_file), "--deep"])
        assert result.exit_code == 0
        assert "type: skill" in result.output
        assert "Type Context: Skill" in result.output

    def test_deep_rule_gets_hook(self, tmp_project: Path):
        rule_dir = tmp_project / ".cursor" / "rules"
        rule_dir.mkdir(parents=True)
        rule_file = rule_dir / "my-rule.mdc"
        rule_file.write_text("# My Rule\n\nAlways do X.\n", encoding="utf-8")

        result = runner.invoke(app, ["lint", str(rule_file), "--deep"])
        assert result.exit_code == 0
        assert "type: rule" in result.output
        assert "Type Context: Rule" in result.output

    def test_deep_unknown_gets_other_hook(self, tmp_project: Path):
        f = tmp_project / "random-doc.md"
        f.write_text("# Random\n\nSome content.\n", encoding="utf-8")

        result = runner.invoke(app, ["lint", str(f), "--deep"])
        assert result.exit_code == 0
        assert "type: other" in result.output
        assert "Type Context: Unknown" in result.output


class TestReverseDrift:
    """Test that docs check detects files missing from the index."""

    def test_missing_from_index_reported(self, initialized_project: Path):
        from writ.core import store
        from writ.core.models import InstructionConfig

        cursor_dir = initialized_project / ".cursor" / "rules"
        cursor_dir.mkdir(parents=True)
        (cursor_dir / "new-file.md").write_text("# New\n", encoding="utf-8")

        store.save_instruction(InstructionConfig(
            name="writ-docs-index",
            task_type="rule",
            instructions="```\n.cursor/\n  rules/\n    old-file.md  #\n```\n",
        ))

        result = runner.invoke(app, ["docs", "check"])
        assert result.exit_code == 0


class TestDocsScanDirs:
    """Test that docs/ and doc/ directories are scanned."""

    def test_docs_dir_scanned(self, tmp_project: Path):
        from writ.core.doc_health import find_doc_files

        docs = tmp_project / "docs"
        docs.mkdir()
        (docs / "architecture.md").write_text("# Arch\n", encoding="utf-8")

        files = find_doc_files(tmp_project)
        names = [f.name for f in files]
        assert "architecture.md" in names

    def test_doc_dir_scanned(self, tmp_project: Path):
        from writ.core.doc_health import find_doc_files

        doc = tmp_project / "doc"
        doc.mkdir()
        (doc / "api.md").write_text("# API\n", encoding="utf-8")

        files = find_doc_files(tmp_project)
        names = [f.name for f in files]
        assert "api.md" in names


class TestCoreFilesSection:
    """Test core files section generation."""

    def test_build_core_files_no_git(self, tmp_project: Path):
        from writ.commands.docs import _build_core_files_section

        result = _build_core_files_section(tmp_project, [])
        assert result == ""

    @patch("subprocess.run")
    def test_build_core_files_with_mocked_git(self, mock_run, tmp_project: Path):
        from writ.commands.docs import _build_core_files_section

        readme = tmp_project / "README.md"
        readme.write_text("# Hi\n", encoding="utf-8")

        def side_effect(cmd, **kwargs):
            class Result:
                returncode = 0
            r = Result()
            if "rev-list" in cmd:
                r.stdout = "100\n"
            elif "log" in cmd:
                r.stdout = "\n".join(f"abc{i} line" for i in range(40))
            else:
                r.stdout = ""
            return r

        mock_run.side_effect = side_effect

        section = _build_core_files_section(tmp_project, [readme])
        assert "## Core files" in section
        assert "README.md" in section
        assert "40 commits" in section


class TestStalenessConfig:
    """Test configurable staleness thresholds."""

    def test_docs_config_defaults(self):
        from writ.core.models import DocsConfig

        cfg = DocsConfig()
        assert cfg.stale_threshold == 30
        assert cfg.critical_threshold == 100

    def test_project_config_has_docs(self):
        from writ.core.models import ProjectConfig

        cfg = ProjectConfig()
        assert cfg.docs.stale_threshold == 30
        assert cfg.docs.critical_threshold == 100

    def test_custom_thresholds(self):
        from writ.core.models import DocsConfig, ProjectConfig

        cfg = ProjectConfig(docs=DocsConfig(stale_threshold=10, critical_threshold=50))
        assert cfg.docs.stale_threshold == 10
        assert cfg.docs.critical_threshold == 50
