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


class TestWritignore:
    def test_default_ignores_node_modules(self, tmp_project: Path):
        """Default patterns ignore node_modules without a .writignore file."""
        (tmp_project / "app.py").write_text("print('hello')")
        nm = tmp_project / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {}")

        from writ.core.scanner import detect_languages
        langs = detect_languages(tmp_project)
        assert "Python" in langs
        assert "JavaScript" not in langs

    def test_writignore_excludes_custom_dir(self, tmp_project: Path):
        """A .writignore file excludes custom directories."""
        (tmp_project / ".writignore").write_text("generated/\n")
        src = tmp_project / "src"
        src.mkdir(exist_ok=True)
        (src / "app.py").write_text("print('hello')")
        gen = tmp_project / "generated"
        gen.mkdir()
        (gen / "output.py").write_text("# auto-generated")

        from writ.core.scanner import detect_languages
        langs = detect_languages(tmp_project)
        assert langs.get("Python", 0) == 1

    def test_writignore_supports_negation(self, tmp_project: Path):
        """Negation patterns with ! re-include previously excluded files."""
        (tmp_project / ".writignore").write_text("*.log\n!important.log\n")
        (tmp_project / "debug.log").write_text("debug")
        (tmp_project / "important.log").write_text("important")
        (tmp_project / "app.py").write_text("print('hello')")

        from writ.core.scanner import load_ignore_spec
        spec = load_ignore_spec(tmp_project)
        assert spec.match_file("debug.log")
        assert not spec.match_file("important.log")

    def test_writignore_comments_ignored(self, tmp_project: Path):
        """Lines starting with # are comments."""
        (tmp_project / ".writignore").write_text("# This is a comment\n*.tmp\n")
        from writ.core.scanner import load_ignore_spec
        spec = load_ignore_spec(tmp_project)
        assert spec.match_file("test.tmp")
        assert not spec.match_file("test.py")

    def test_directory_tree_respects_writignore(self, tmp_project: Path):
        """get_directory_tree should exclude .writignore patterns."""
        (tmp_project / ".writignore").write_text("secret/\n")
        (tmp_project / "src").mkdir()
        (tmp_project / "src" / "app.py").write_text("x")
        (tmp_project / "secret").mkdir()
        (tmp_project / "secret" / "keys.txt").write_text("x")

        from writ.core.scanner import get_directory_tree
        tree = get_directory_tree(tmp_project)
        assert "src" in tree
        assert "secret" not in tree


class TestParseMarkdownFile:
    """Tests for the public parse_markdown_file / parse_markdown_content API."""

    def test_parse_md_file(self, tmp_project: Path):
        md = tmp_project / "my-rules.md"
        md.write_text("# Project Rules\n\nAlways write tests.\n", encoding="utf-8")
        from writ.core.scanner import parse_markdown_file
        cfg = parse_markdown_file(md)
        assert cfg is not None
        assert cfg.name == "my-rules"
        assert cfg.description == "Project Rules"
        assert "Always write tests" in cfg.instructions

    def test_parse_md_name_override(self, tmp_project: Path):
        md = tmp_project / "messy-Name.md"
        md.write_text("Some instructions\n", encoding="utf-8")
        from writ.core.scanner import parse_markdown_file
        cfg = parse_markdown_file(md, name_override="clean-name")
        assert cfg is not None
        assert cfg.name == "clean-name"

    def test_parse_mdc_preserves_frontmatter(self, tmp_project: Path):
        mdc = tmp_project / "project-rule.mdc"
        mdc.write_text(
            "---\ndescription: My project rule\nalwaysApply: true\nglobs: \"**/*.py\"\n---\n\n"
            "# Rule\n\nDo the thing.\n",
            encoding="utf-8",
        )
        from writ.core.scanner import parse_markdown_file
        cfg = parse_markdown_file(mdc)
        assert cfg is not None
        assert cfg.name == "project-rule"
        assert cfg.task_type == "rule"
        assert cfg.format_overrides.cursor is not None
        assert cfg.format_overrides.cursor.always_apply is True
        assert cfg.format_overrides.cursor.globs == "**/*.py"
        assert cfg.format_overrides.cursor.description == "My project rule"

    def test_mdc_roundtrip_fidelity(self, tmp_project: Path):
        """Import .mdc then export as cursor -- frontmatter should be preserved."""
        original = (
            "---\ndescription: Code standards\nalwaysApply: true\nglobs: \"src/**\"\n---\n\n"
            "Write clean code.\n"
        )
        mdc = tmp_project / "standards.mdc"
        mdc.write_text(original, encoding="utf-8")

        from writ.core.scanner import parse_markdown_file
        from writ.core.formatter import CursorFormatter

        cfg = parse_markdown_file(mdc)
        assert cfg is not None

        fmt = CursorFormatter()
        out_path = fmt.write(cfg, cfg.instructions, root=tmp_project)
        exported = out_path.read_text(encoding="utf-8")

        assert "alwaysApply: true" in exported
        assert "src/**" in exported
        assert "Code standards" in exported
        assert "Write clean code." in exported

    def test_parse_plain_txt(self, tmp_project: Path):
        txt = tmp_project / "notes.txt"
        txt.write_text("Just plain text instructions.\n", encoding="utf-8")
        from writ.core.scanner import parse_markdown_file
        cfg = parse_markdown_file(txt)
        assert cfg is not None
        assert cfg.name == "notes"
        assert "plain text" in cfg.instructions

    def test_parse_empty_file_returns_none(self, tmp_project: Path):
        md = tmp_project / "empty.md"
        md.write_text("", encoding="utf-8")
        from writ.core.scanner import parse_markdown_file
        assert parse_markdown_file(md) is None

    def test_parse_content_directly(self):
        from writ.core.scanner import parse_markdown_content
        cfg = parse_markdown_content("# My Rule\n\nDo stuff.\n", "test-rule", ".md")
        assert cfg is not None
        assert cfg.name == "test-rule"
        assert cfg.description == "My Rule"


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
