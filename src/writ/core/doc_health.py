"""Project documentation health diagnostics.

Detects dead file references, treeview drift, stale instructions,
contradictions, and computes an aggregate health score.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DocIssue:
    """A single documentation health issue."""

    kind: str  # dead_ref, treeview_drift, stale, contradiction
    message: str
    severity: str = "warning"  # warning, error, info


@dataclass
class DocFileReport:
    """Health report for a single documentation file."""

    path: str
    lint_score: int | None = None
    freshness: str = "unknown"  # fresh, stale, STALE
    issues: list[DocIssue] = field(default_factory=list)
    last_commit_ago: int | None = None


@dataclass
class DocHealthReport:
    """Project-wide documentation health report."""

    health_score: int = 100
    files: list[DocFileReport] = field(default_factory=list)
    total_issues: int = 0


_FILE_PATH_RE = re.compile(
    r'(?:`([^`\n]+\.[a-zA-Z0-9]{1,10})`'  # backtick-fenced paths with extension
    r'|(?:^|\s)((?:\.?[\w./-]+/)+[\w.-]+\.[a-zA-Z0-9]{1,10}))',  # bare paths
    re.MULTILINE,
)

_TREEVIEW_ENTRY_RE = re.compile(
    r'[|+\-`\\/ ]*(?:├──|└──|│   |    |\|--)'
    r'\s*(.+)',
)

_TREEVIEW_SIMPLE_RE = re.compile(
    r'^[\s│├└─┐┘┌┬┤┼\|\-\+\\/ ]*(\S+\.[\w]{1,10})\s*(?:#.*)?$',
    re.MULTILINE,
)

_DIRECTIVE_RE = re.compile(
    r'\b(always|never|must|do not|don\'t|required|forbidden|prohibited)\b'
    r'\s+(?:use|do|run|include|import|call|write|create|add)?\s*'
    r'["\']?(\w[\w\s\-.]*\w)["\']?',
    re.IGNORECASE,
)


_IDE_DETECT_DIRS = [
    ".cursor", ".claude", ".kiro", ".github", ".windsurf",
    ".clinerules", ".roo", ".amazonq", ".gemini", ".codex", ".opencode",
]

_DOC_EXTENSIONS = {".md", ".mdc", ".yaml", ".yml", ".txt"}

_SKIP_DIRS = {"node_modules", "venv", ".venv", ".git", "__pycache__", ".writ"}

_ROOT_FILES = [
    "AGENTS.md", "CLAUDE.md", "SKILL.md", "README.md",
    "CONTRIBUTING.md", "CHANGELOG.md", "ARCHITECTURE.md",
    ".cursorrules", ".windsurfrules",
]


def find_doc_files(root: Path | None = None) -> list[Path]:
    """Find documentation files in IDE folders and well-known root files.

    Scans all detected IDE configuration directories (.cursor/, .claude/,
    .kiro/, etc.) recursively for documentation files.  Also picks up
    well-known root files (README.md, AGENTS.md, etc.).  Excludes .writ/
    internals which are static YAML managed by writ itself.
    """
    root = root or Path.cwd()
    files: list[Path] = []

    for name in _ROOT_FILES:
        p = root / name
        if p.exists():
            files.append(p)

    for ide_dir in _IDE_DETECT_DIRS:
        d = root / ide_dir
        if not d.is_dir():
            continue
        for child in sorted(d.rglob("*")):
            if not child.is_file():
                continue
            if any(skip in child.parts for skip in _SKIP_DIRS):
                continue
            if child.suffix.lower() in _DOC_EXTENSIONS:
                files.append(child)

    return files


_FENCED_CODE_BLOCK_RE = re.compile(
    r'^[ \t]*(`{3,}|~{3,}).*?\n.*?^[ \t]*\1[ \t]*$',
    re.MULTILINE | re.DOTALL,
)

_INLINE_CODE_RE = re.compile(r'`[^`\n]+`')


def _strip_code_blocks(text: str) -> str:
    """Remove fenced code blocks and inline code spans."""
    text = _FENCED_CODE_BLOCK_RE.sub('', text)
    return _INLINE_CODE_RE.sub('', text)


def extract_file_references(text: str) -> list[str]:
    """Extract file path references from instruction text."""
    cleaned = _strip_code_blocks(text)
    refs: list[str] = []
    for match in _FILE_PATH_RE.finditer(cleaned):
        backtick_content = match.group(1)
        path = backtick_content or match.group(2)
        if not path or _is_noise_path(path):
            continue
        if backtick_content and _SHELL_CMD_RE.search(backtick_content):
            continue
        refs.append(path)
    return list(dict.fromkeys(refs))


_SHELL_CMD_RE = re.compile(
    r'(grep|sed|awk|find|cat|echo|curl|wget|rm|cp|mv|mkdir|chmod|'
    r'git|pip|npm|docker|tar|ssh|scp|writ)\s',
    re.IGNORECASE,
)


_PLACEHOLDER_PATTERNS = re.compile(
    r'(?:src/foo|src/bar|foo/bar|path/to/|my[_-]|your[_-]|example[_-]|sample[_-])'
    r'|(?:YY-MM-DD|YYYY-MM|MM-DD)'
    r'|(?:<[^>]+>)'
    r'|(?:\.\.\./)',
    re.IGNORECASE,
)


def _is_noise_path(path: str) -> bool:
    """Filter out common false positives (URLs, versions, dates, placeholders)."""
    if path.startswith(("http://", "https://", "ftp://", "mailto:")):
        return True
    if re.match(r'^\d+[\.\-]\d+[\.\-]\d+', path):
        return True
    if re.match(r'^\d{4}-\d{2}-\d{2}', path):
        return True
    noise_extensions = {
        ".com", ".org", ".net", ".io", ".dev", ".app", ".ai",
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    }
    ext = Path(path).suffix.lower()
    if ext in noise_extensions:
        return True
    if path.startswith("writ-") and ext in {".mdc", ".md"}:
        return True
    if path.startswith(("--", "e.g.", "i.e.")):
        return True
    if "*" in path or "?" in path:
        return True
    if _PLACEHOLDER_PATTERNS.search(path):
        return True
    return False


def check_dead_references(
    text: str,
    root: Path,
    file_path: Path,
) -> list[DocIssue]:
    """Find file references in text that don't exist on disk."""
    issues: list[DocIssue] = []
    refs = extract_file_references(text)

    for ref in refs:
        candidates = [
            root / ref,
            file_path.parent / ref,
        ]
        parent_only = Path(ref).parent
        if parent_only != Path(".") and (root / parent_only).is_dir():
            continue
        if any(c.exists() or c.parent.is_dir() for c in candidates):
            continue
        issues.append(DocIssue(
            kind="dead_ref",
            message=f"References `{ref}` -- file not found",
            severity="warning",
        ))
    return issues


def extract_treeview_entries(text: str) -> list[str]:
    """Extract file/folder names from treeview-formatted code blocks."""
    entries: list[str] = []
    in_code_block = False
    is_treeview = False

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code_block:
                in_code_block = False
                is_treeview = False
            else:
                in_code_block = True
                is_treeview = False
            continue

        if in_code_block:
            if _TREEVIEW_ENTRY_RE.match(line) or "├" in line or "└" in line:
                is_treeview = True

            if is_treeview:
                for m in _TREEVIEW_SIMPLE_RE.finditer(line):
                    entry = m.group(1).strip()
                    if entry and not entry.startswith("#"):
                        entries.append(entry)

    return list(dict.fromkeys(entries))


def check_treeview_drift(
    text: str,
    root: Path,
) -> list[DocIssue]:
    """Check if treeview entries match the actual file tree."""
    issues: list[DocIssue] = []
    entries = extract_treeview_entries(text)

    for entry in entries:
        if entry.endswith("/"):
            entry = entry.rstrip("/")
        p = root / entry
        if not p.exists():
            issues.append(DocIssue(
                kind="treeview_drift",
                message=f"Treeview lists `{entry}` -- not found on disk",
                severity="warning",
            ))
    return issues


def _git_commits_since(file_path: Path, root: Path) -> int | None:
    """Count how many commits have happened since file was last modified."""
    try:
        rel = file_path.relative_to(root)
        last_mod = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", str(rel)],
            capture_output=True, text=True, cwd=root, timeout=10,
        )
        if last_mod.returncode != 0 or not last_mod.stdout.strip():
            return None

        total = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            capture_output=True, text=True, cwd=root, timeout=10,
        )
        file_rev = subprocess.run(
            ["git", "rev-list", "--count", last_mod.stdout.strip() + "..HEAD"],
            capture_output=True, text=True, cwd=root, timeout=10,
        )
        if total.returncode == 0 and file_rev.returncode == 0:
            return int(file_rev.stdout.strip())
    except Exception:  # noqa: BLE001
        pass
    return None


def check_staleness(
    file_path: Path,
    root: Path,
    stale_threshold: int = 30,
    critical_threshold: int = 100,
) -> tuple[str, int | None]:
    """Check if a doc file is stale based on git history.

    Returns (freshness_label, commits_behind).
    """
    commits = _git_commits_since(file_path, root)
    if commits is None:
        return "unknown", None
    if commits >= critical_threshold:
        return "STALE", commits
    if commits >= stale_threshold:
        return "stale", commits
    return "fresh", commits


def check_contradictions(
    files: list[tuple[Path, str]],
) -> list[tuple[str, str, DocIssue]]:
    """Find basic contradictions between doc files.

    Returns list of (file1, file2, issue) tuples.
    """
    issues: list[tuple[str, str, DocIssue]] = []
    directives: dict[str, list[tuple[str, str, str]]] = {}

    for file_path, text in files:
        for match in _DIRECTIVE_RE.finditer(text):
            verb = match.group(1).lower()
            topic = match.group(2).lower().strip()
            if len(topic) < 3:
                continue
            key = topic
            polarity = "negative" if verb in (
                "never", "do not", "don't", "forbidden", "prohibited",
            ) else "positive"
            directives.setdefault(key, []).append(
                (str(file_path.name), polarity, match.group(0).strip()),
            )

    for topic, entries in directives.items():
        polarities = {e[1] for e in entries}
        if len(polarities) > 1:
            pos_files = [e for e in entries if e[1] == "positive"]
            neg_files = [e for e in entries if e[1] == "negative"]
            if pos_files and neg_files:
                f1 = pos_files[0][0]
                f2 = neg_files[0][0]
                issues.append((f1, f2, DocIssue(
                    kind="contradiction",
                    message=(
                        f"Contradiction about '{topic}': "
                        f"{f1} says \"{pos_files[0][2]}\" "
                        f"but {f2} says \"{neg_files[0][2]}\""
                    ),
                    severity="warning",
                )))

    return issues


def run_health_check(root: Path | None = None) -> DocHealthReport:
    """Run a full documentation health check.

    Returns a DocHealthReport with per-file reports and aggregate score.
    """
    root = root or Path.cwd()
    doc_files = find_doc_files(root)
    report = DocHealthReport()

    files_with_text: list[tuple[Path, str]] = []
    for fp in doc_files:
        try:
            text = fp.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        files_with_text.append((fp, text))

    file_reports: dict[str, DocFileReport] = {}
    for fp, text in files_with_text:
        rel = str(fp.relative_to(root))
        fr = DocFileReport(path=rel)

        dead_refs = check_dead_references(text, root, fp)
        fr.issues.extend(dead_refs)

        if "├" in text or "└" in text or "│" in text:
            drift = check_treeview_drift(text, root)
            fr.issues.extend(drift)

        freshness, commits = check_staleness(fp, root)
        fr.freshness = freshness
        fr.last_commit_ago = commits

        file_reports[rel] = fr

    contradiction_results = check_contradictions(files_with_text)
    for f1, f2, issue in contradiction_results:
        for rel, fr in file_reports.items():
            if rel.endswith(f1) or rel.endswith(f2):
                if not any(i.message == issue.message for i in fr.issues):
                    fr.issues.append(issue)
                break

    total_issues = 0
    penalty = 0
    for fr in file_reports.values():
        total_issues += len(fr.issues)
        file_penalty = 0
        for issue in fr.issues:
            if issue.severity == "error":
                file_penalty += 10
            else:
                file_penalty += 3
        file_penalty = min(file_penalty, 30)
        if fr.freshness == "STALE":
            file_penalty += 10
        elif fr.freshness == "stale":
            file_penalty += 5
        penalty += file_penalty

    n_files = max(len(file_reports), 1)
    health = max(0, 100 - int(penalty * 100 / (n_files * 30)))

    report.health_score = health
    report.files = list(file_reports.values())
    report.total_issues = total_issues
    return report
