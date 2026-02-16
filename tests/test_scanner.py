"""Tests for the project scanner."""

from pathlib import Path

from writ.core import scanner


class TestLanguageDetection:
    def test_detect_python(self, tmp_project: Path):
        (tmp_project / "app.py").write_text("print('hello')")
        (tmp_project / "utils.py").write_text("def helper(): pass")
        langs = scanner.detect_languages(tmp_project)
        assert "Python" in langs
        assert langs["Python"] == 2

    def test_detect_typescript(self, tmp_project: Path):
        (tmp_project / "app.ts").write_text("const x: number = 1;")
        langs = scanner.detect_languages(tmp_project)
        assert "TypeScript" in langs

    def test_skip_dirs(self, tmp_project: Path):
        node_modules = tmp_project / "node_modules" / "pkg"
        node_modules.mkdir(parents=True)
        (node_modules / "index.js").write_text("module.exports = {};")
        (tmp_project / "app.js").write_text("console.log('hi');")
        langs = scanner.detect_languages(tmp_project)
        assert langs.get("JavaScript", 0) == 1  # Only app.js, not node_modules


class TestFrameworkDetection:
    def test_detect_react(self, tmp_project: Path):
        (tmp_project / "package.json").write_text('{"dependencies": {"react": "^19.0.0"}}')
        frameworks = scanner.detect_frameworks(tmp_project)
        assert "React" in frameworks

    def test_detect_pytest(self, tmp_project: Path):
        (tmp_project / "pyproject.toml").write_text('[tool.pytest]\ntestpaths = ["tests"]')
        frameworks = scanner.detect_frameworks(tmp_project)
        assert "Pytest" in frameworks

    def test_no_frameworks(self, tmp_project: Path):
        frameworks = scanner.detect_frameworks(tmp_project)
        assert frameworks == []


class TestExistingFileDetection:
    def test_detect_agents_md(self, tmp_project: Path):
        (tmp_project / "AGENTS.md").write_text("# Agents")
        found = scanner.detect_existing_files(tmp_project)
        assert len(found) == 1
        assert found[0]["format"] == "agents_md"

    def test_detect_cursor_rules(self, tmp_project: Path):
        rules_dir = tmp_project / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "my-rule.mdc").write_text("---\ndescription: test\n---\nRule content")
        found = scanner.detect_existing_files(tmp_project)
        assert any(f["format"] == "cursor" for f in found)

    def test_skip_writ_managed_cursor_rules(self, tmp_project: Path):
        rules_dir = tmp_project / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "writ-test.mdc").write_text("managed by writ")
        found = scanner.detect_existing_files(tmp_project)
        assert not any(f["format"] == "cursor" for f in found)

    def test_detect_claude_md(self, tmp_project: Path):
        (tmp_project / "CLAUDE.md").write_text("# Claude")
        found = scanner.detect_existing_files(tmp_project)
        assert any(f["format"] == "claude" for f in found)


class TestParseExistingFile:
    def test_parse_cursor_mdc_with_frontmatter(self, tmp_project: Path):
        mdc_path = tmp_project / "test.mdc"
        mdc_path.write_text(
            "---\ndescription: My rule\nalwaysApply: true\n---\n\n"
            "# Rule\nYou must write tests for all code."
        )
        result = scanner.parse_existing_file({
            "path": str(mdc_path), "format": "cursor", "name": "test",
        })
        assert result is not None
        assert result.name == "test"
        assert result.description == "My rule"
        assert "write tests" in result.instructions
        assert "imported" in result.tags
        assert "cursor" in result.tags

    def test_parse_cursor_mdc_no_frontmatter(self, tmp_project: Path):
        mdc_path = tmp_project / "plain.mdc"
        mdc_path.write_text("Just plain instructions here.")
        result = scanner.parse_existing_file({
            "path": str(mdc_path), "format": "cursor", "name": "plain",
        })
        assert result is not None
        assert result.name == "plain"
        assert "plain instructions" in result.instructions

    def test_parse_agents_md(self, tmp_project: Path):
        md_path = tmp_project / "AGENTS.md"
        md_path.write_text("# Agents\n\nFollow strict coding standards.")
        result = scanner.parse_existing_file({
            "path": str(md_path), "format": "agents_md", "name": "agents-md",
        })
        assert result is not None
        assert result.name == "agents-md"
        assert "strict coding standards" in result.instructions
        assert "agents-md" in result.tags

    def test_parse_claude_md(self, tmp_project: Path):
        md_path = tmp_project / "CLAUDE.md"
        md_path.write_text("# Claude Instructions\n\nBe helpful.")
        result = scanner.parse_existing_file({
            "path": str(md_path), "format": "claude", "name": "claude",
        })
        assert result is not None
        assert result.name == "claude"
        assert "Be helpful" in result.instructions

    def test_parse_windsurfrules(self, tmp_project: Path):
        ws_path = tmp_project / ".windsurfrules"
        ws_path.write_text("Always use TypeScript strict mode.")
        result = scanner.parse_existing_file({
            "path": str(ws_path), "format": "windsurf", "name": "windsurfrules",
        })
        assert result is not None
        assert "TypeScript strict" in result.instructions

    def test_parse_copilot(self, tmp_project: Path):
        cp_path = tmp_project / "copilot-instructions.md"
        cp_path.write_text("Write clean code.")
        result = scanner.parse_existing_file({
            "path": str(cp_path),
            "format": "copilot",
            "name": "copilot-instructions",
        })
        assert result is not None
        assert "clean code" in result.instructions

    def test_parse_empty_file_returns_none(self, tmp_project: Path):
        empty = tmp_project / "empty.md"
        empty.write_text("")
        result = scanner.parse_existing_file({
            "path": str(empty), "format": "claude", "name": "empty",
        })
        assert result is None

    def test_parse_nonexistent_returns_none(self):
        result = scanner.parse_existing_file({
            "path": "/nonexistent/file.md", "format": "claude", "name": "x",
        })
        assert result is None


class TestProjectAnalysis:
    def test_analyze_generates_markdown(self, tmp_project: Path):
        (tmp_project / "app.py").write_text("print('hello')")
        result = scanner.analyze_project(tmp_project)
        assert "# Project Context" in result
        assert "Python" in result

    def test_directory_tree(self, tmp_project: Path):
        (tmp_project / "src").mkdir()
        (tmp_project / "src" / "main.py").write_text("")
        tree = scanner.get_directory_tree(tmp_project, max_depth=2)
        assert "src/" in tree
