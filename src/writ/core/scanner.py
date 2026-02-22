"""Detect languages, frameworks, existing agent files, and project structure."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pathspec

if TYPE_CHECKING:
    from writ.core.models import AgentConfig

# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

LANGUAGE_MAP: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (React)",
    ".jsx": "JavaScript (React)",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".swift": "Swift",
    ".dart": "Dart",
    ".lua": "Lua",
    ".zig": "Zig",
    ".sh": "Shell",
    ".sql": "SQL",
    ".md": "Markdown",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".svelte": "Svelte",
    ".vue": "Vue",
}

# Directories to always skip when scanning
SKIP_DIRS: set[str] = {
    ".git", ".writ", "node_modules", "venv", ".venv", "env",
    "__pycache__", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".next", ".nuxt", "target", ".cargo", "vendor", ".mypy_cache",
    "htmlcov", ".tox", ".eggs", "*.egg-info",
}

DEFAULT_IGNORE_PATTERNS: list[str] = [
    "node_modules/",
    "venv/",
    ".venv/",
    ".git/",
    "__pycache__/",
    "dist/",
    "build/",
    ".next/",
    ".nuxt/",
    "target/",
    ".cargo/",
    "vendor/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    "htmlcov/",
    ".tox/",
    ".eggs/",
    "*.egg-info/",
    ".writ/",
]


def load_ignore_spec(root: Path | None = None) -> pathspec.PathSpec:
    """Load .writignore patterns, combined with built-in defaults.

    Uses gitignore-style matching via the pathspec library.
    """
    patterns = list(DEFAULT_IGNORE_PATTERNS)

    root = root or Path.cwd()
    writignore = root / ".writignore"
    if writignore.exists():
        try:
            content = writignore.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
        except (OSError, UnicodeDecodeError):
            pass

    return pathspec.PathSpec.from_lines("gitignore", patterns)


def detect_languages(root: Path | None = None, max_files: int = 5000) -> dict[str, int]:
    """Count files by language. Returns {language_name: count}."""
    root = root or Path.cwd()
    spec = load_ignore_spec(root)
    counts: dict[str, int] = {}
    scanned = 0

    for dirpath_str, dirnames, filenames in os.walk(root):
        dirpath = Path(dirpath_str)
        rel_dir = dirpath.relative_to(root)

        # Prune ignored directories
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not spec.match_file(str(rel_dir / d) + "/")
        ]

        for fname in filenames:
            if scanned >= max_files:
                return counts
            rel_path = str(rel_dir / fname)
            if spec.match_file(rel_path):
                continue
            ext = Path(fname).suffix.lower()
            if ext in LANGUAGE_MAP:
                lang = LANGUAGE_MAP[ext]
                counts[lang] = counts.get(lang, 0) + 1
                scanned += 1

    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))


# ---------------------------------------------------------------------------
# Framework detection
# ---------------------------------------------------------------------------

FRAMEWORK_INDICATORS: dict[str, list[tuple[str, str]]] = {
    # (file_to_check, substring_in_file) -> framework_name
    "React": [("package.json", '"react"')],
    "Next.js": [("package.json", '"next"')],
    "Vue": [("package.json", '"vue"')],
    "Svelte": [("package.json", '"svelte"')],
    "Angular": [("package.json", '"@angular/core"')],
    "Express": [("package.json", '"express"')],
    "FastAPI": [("requirements.txt", "fastapi"), ("pyproject.toml", "fastapi")],
    "Django": [("requirements.txt", "django"), ("pyproject.toml", "django")],
    "Flask": [("requirements.txt", "flask"), ("pyproject.toml", "flask")],
    "Tauri": [("Cargo.toml", "tauri"), ("package.json", '"@tauri-apps"')],
    "Vite": [("package.json", '"vite"')],
    "TypeScript": [("tsconfig.json", "")],
    "Tailwind CSS": [("package.json", '"tailwindcss"'), ("tailwind.config.js", "")],
    "Pytest": [("pyproject.toml", "pytest"), ("requirements.txt", "pytest")],
    "Jest": [("package.json", '"jest"')],
}


def detect_frameworks(root: Path | None = None) -> list[str]:
    """Detect frameworks based on config/dependency files."""
    root = root or Path.cwd()
    frameworks: list[str] = []

    for framework, indicators in FRAMEWORK_INDICATORS.items():
        for filename, substring in indicators:
            filepath = root / filename
            if filepath.exists():
                if not substring:
                    # Just check file existence
                    frameworks.append(framework)
                    break
                try:
                    content = filepath.read_text(encoding="utf-8")
                    if substring in content:
                        frameworks.append(framework)
                        break
                except (OSError, UnicodeDecodeError):
                    continue

    return sorted(set(frameworks))


# ---------------------------------------------------------------------------
# Build/test command detection
# ---------------------------------------------------------------------------

def detect_commands(root: Path | None = None) -> dict[str, str]:
    """Detect build/test/dev commands from project files."""
    root = root or Path.cwd()
    commands: dict[str, str] = {}

    # package.json scripts
    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            import json

            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            scripts = data.get("scripts", {})
            if "dev" in scripts:
                commands["dev"] = "npm run dev"
            if "build" in scripts:
                commands["build"] = "npm run build"
            if "test" in scripts:
                commands["test"] = "npm run test"
            if "lint" in scripts:
                commands["lint"] = "npm run lint"
        except (json.JSONDecodeError, OSError):
            pass

    # Python project
    if (root / "pyproject.toml").exists():
        commands.setdefault("test", "pytest")
        commands.setdefault("lint", "ruff check .")

    # Makefile
    if (root / "Makefile").exists():
        commands.setdefault("build", "make")

    # Cargo
    if (root / "Cargo.toml").exists():
        commands.setdefault("build", "cargo build")
        commands.setdefault("test", "cargo test")

    return commands


# ---------------------------------------------------------------------------
# Directory tree
# ---------------------------------------------------------------------------

def get_directory_tree(root: Path | None = None, max_depth: int = 2) -> str:
    """Get a simplified directory tree (top N levels)."""
    root = root or Path.cwd()
    spec = load_ignore_spec(root)
    lines: list[str] = [f"{root.name}/"]

    def _walk(directory: Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return
        entries = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        entries = [
            e for e in entries
            if e.name not in SKIP_DIRS
            and not (e.name.startswith(".") and e.name not in (".github", ".cursor"))
            and not spec.match_file(
                str(e.relative_to(root)) + ("/" if e.is_dir() else "")
            )
        ]
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "+-- " if is_last else "|-- "
            if entry.is_dir():
                lines.append(f"{prefix}{connector}{entry.name}/")
                extension = "    " if is_last else "|   "
                _walk(entry, prefix + extension, depth + 1)
            else:
                lines.append(f"{prefix}{connector}{entry.name}")

    _walk(root, "", 1)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Detect existing agent files
# ---------------------------------------------------------------------------

EXISTING_AGENT_PATTERNS: dict[str, str] = {
    "AGENTS.md": "agents_md",
    "CLAUDE.md": "claude",
    ".cursorrules": "cursorrules",
    ".windsurfrules": "windsurf",
}

EXISTING_AGENT_DIRS: dict[str, str] = {
    ".cursor/rules": "cursor",
    ".github": "copilot",
}


def detect_existing_files(root: Path | None = None) -> list[dict[str, str]]:
    """Find existing agent config files in the repo."""
    root = root or Path.cwd()
    found: list[dict[str, str]] = []

    # Check single files
    for filename, format_type in EXISTING_AGENT_PATTERNS.items():
        path = root / filename
        if path.exists():
            found.append({
                "path": str(path),
                "format": format_type,
                "name": path.stem.lower(),
            })

    # Check .cursor/rules/*.mdc
    cursor_rules = root / ".cursor" / "rules"
    if cursor_rules.is_dir():
        for mdc in cursor_rules.glob("*.mdc"):
            # Skip writ-managed files
            if mdc.name.startswith("writ-"):
                continue
            found.append({
                "path": str(mdc),
                "format": "cursor",
                "name": mdc.stem.lower(),
            })

    # Check copilot instructions
    copilot_path = root / ".github" / "copilot-instructions.md"
    if copilot_path.exists():
        found.append({
            "path": str(copilot_path),
            "format": "copilot",
            "name": "copilot-instructions",
        })

    return found


# ---------------------------------------------------------------------------
# Parse existing agent files into AgentConfig
# ---------------------------------------------------------------------------

def parse_existing_file(file_info: dict[str, str]) -> AgentConfig | None:
    """Parse a detected existing agent file into an AgentConfig.

    Supports: Cursor .mdc, CLAUDE.md, AGENTS.md, .windsurfrules,
    .cursorrules, copilot-instructions.md.
    """
    path = Path(file_info["path"])
    fmt = file_info["format"]
    name = file_info["name"]

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    if not content.strip():
        return None

    if fmt == "cursor":
        return _parse_cursor_mdc(content, name)
    elif fmt == "cursorrules":
        return _parse_plain_instructions(content, "cursorrules", ["cursor"])
    elif fmt == "claude":
        return _parse_markdown_sections(content, "claude", ["claude"])
    elif fmt == "agents_md":
        return _parse_markdown_sections(content, "agents-md", ["agents-md"])
    elif fmt == "copilot":
        return _parse_plain_instructions(
            content, "copilot-instructions", ["copilot"],
        )
    elif fmt == "windsurf":
        return _parse_plain_instructions(content, "windsurfrules", ["windsurf"])

    return None


def _parse_cursor_mdc(content: str, name: str) -> AgentConfig | None:
    """Parse a .cursor/rules/*.mdc file (YAML frontmatter + markdown body)."""
    import re

    import yaml

    from writ.core.models import AgentConfig  # runtime import

    description = ""
    instructions = content

    # Extract YAML frontmatter
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if fm_match:
        try:
            fm = yaml.safe_load(fm_match.group(1))
            if isinstance(fm, dict):
                description = fm.get("description", "")
        except yaml.YAMLError:
            pass
        instructions = fm_match.group(2).strip()

    if not instructions:
        return None

    return AgentConfig(
        name=name,
        description=str(description) if description else f"Imported from .cursor/rules/{name}.mdc",
        instructions=instructions,
        tags=["imported", "cursor"],
    )


def _parse_markdown_sections(
    content: str, name: str, tags: list[str],
) -> AgentConfig | None:
    """Parse a markdown file (CLAUDE.md, AGENTS.md) as a single agent."""
    import re

    from writ.core.models import AgentConfig  # runtime import

    cleaned = re.sub(r"<!-- writ:.*?-->", "", content).strip()
    if not cleaned:
        return None

    return AgentConfig(
        name=name,
        description=f"Imported from {name}",
        instructions=cleaned,
        tags=["imported", *tags],
    )


def _parse_plain_instructions(
    content: str, name: str, tags: list[str],
) -> AgentConfig | None:
    """Parse a plain text/markdown file as instructions."""
    from writ.core.models import AgentConfig  # runtime import

    content = content.strip()
    if not content:
        return None

    return AgentConfig(
        name=name,
        description=f"Imported from {name}",
        instructions=content,
        tags=["imported", *tags],
    )


# ---------------------------------------------------------------------------
# Full project analysis
# ---------------------------------------------------------------------------

def analyze_project(root: Path | None = None) -> str:
    """Generate a markdown summary of the project for context composition.

    This becomes .writ/project-context.md -- Layer 1 of composition.
    """
    root = root or Path.cwd()
    sections: list[str] = []

    sections.append(f"# Project Context: {root.name}\n")
    sections.append("*Auto-generated by writ. Updated on each `writ init`.*\n")

    # Languages
    languages = detect_languages(root)
    if languages:
        sections.append("## Languages\n")
        for lang, count in list(languages.items())[:10]:
            sections.append(f"- {lang}: {count} files")
        sections.append("")

    # Frameworks
    frameworks = detect_frameworks(root)
    if frameworks:
        sections.append("## Frameworks & Tools\n")
        for fw in frameworks:
            sections.append(f"- {fw}")
        sections.append("")

    # Commands
    commands = detect_commands(root)
    if commands:
        sections.append("## Commands\n")
        for cmd_name, cmd_value in commands.items():
            sections.append(f"- **{cmd_name}**: `{cmd_value}`")
        sections.append("")

    # Directory structure
    tree = get_directory_tree(root, max_depth=2)
    sections.append("## Directory Structure\n")
    sections.append(f"```\n{tree}\n```\n")

    return "\n".join(sections)
