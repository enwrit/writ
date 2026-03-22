"""Validate instruction quality and compute quality scores.

Based on findings from "Evaluating AGENTS.md" (arXiv:2602.11988),
cursor-doctor (50-repo scan, 998 issues), AGENTIF (NeurIPS 2025),
MCP Smells (arXiv:2602.14878), and Boris Cherny's verification research.

Scoring uses 6 user-facing dimensions (Clarity, Structure, Coverage,
Brevity, Examples, Verification) each 0-100, with a weighted headline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from markdown_it import MarkdownIt

from writ.core.models import (
    DimensionScore,
    InstructionConfig,
    LintResult,
    LintScore,
)

# ---------------------------------------------------------------------------
# Dimension weights (configurable -- ML can learn true weights later)
# ---------------------------------------------------------------------------

DIMENSION_WEIGHTS: dict[str, float] = {
    "clarity": 0.25,
    "verification": 0.25,
    "coverage": 0.20,
    "brevity": 0.15,
    "structure": 0.10,
    "examples": 0.05,
}

# ---------------------------------------------------------------------------
# Weak-language patterns (from cursor-doctor + AGENTIF research)
# ---------------------------------------------------------------------------

WEAK_LANGUAGE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\btry to\b", re.I), "try to"),
    (re.compile(r"\bconsider\b", re.I), "consider"),
    (re.compile(r"\byou might\b", re.I), "you might"),
    (re.compile(r"\byou might want to\b", re.I), "you might want to"),
    (re.compile(r"\bmaybe\b", re.I), "maybe"),
    (re.compile(r"\bit.?s recommended\b", re.I), "it's recommended"),
    (re.compile(r"\bfollow best practices\b", re.I), "follow best practices"),
    (re.compile(r"\bwrite clean code\b", re.I), "write clean code"),
    (re.compile(r"\bbe helpful\b", re.I), "be helpful"),
    (re.compile(r"\bif possible\b", re.I), "if possible"),
    (re.compile(r"\bwhen appropriate\b", re.I), "when appropriate"),
    (re.compile(r"\byou should\b", re.I), "you should"),
    (re.compile(r"\byou could\b", re.I), "you could"),
    (re.compile(r"\bideally\b", re.I), "ideally"),
    (re.compile(r"\bperhaps\b", re.I), "perhaps"),
    (re.compile(r"\bit would be nice\b", re.I), "it would be nice"),
    (re.compile(r"\btry and\b", re.I), "try and"),
    (re.compile(r"\bas needed\b", re.I), "as needed"),
    (re.compile(r"\bwhere possible\b", re.I), "where possible"),
    (re.compile(r"\bif you can\b", re.I), "if you can"),
]

EXPERT_PREAMBLE_PATTERN = re.compile(
    r"^you are (?:an? )?"
    r"(?:expert|senior|experienced|skilled|world-class)",
    re.I,
)

VERIFICATION_KEYWORDS = re.compile(
    r"\b(?:test|check|verify|lint|build|run|execute"
    r"|pytest|npm test|ruff|eslint|mypy|cargo test)\b",
    re.I,
)

COMMAND_PATTERN = re.compile(r"`[^`]+`")

# ---------------------------------------------------------------------------
# Prose extraction (skip code fences to avoid false positives)
# ---------------------------------------------------------------------------


def extract_prose_sections(text: str) -> list[str]:
    """Return text lines NOT inside triple-backtick code fences."""
    lines = text.split("\n")
    prose_lines: list[str] = []
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            prose_lines.append(line)
    return prose_lines


def _prose_text(instructions: str) -> str:
    """Join prose sections into a single string for analysis."""
    return "\n".join(extract_prose_sections(instructions))


# ---------------------------------------------------------------------------
# Lint rules
# ---------------------------------------------------------------------------


def _is_writ_managed(
    agent: InstructionConfig,
    source_path: Path | None,
) -> bool:
    """True when the instruction comes from a writ project (.writ/ YAML)."""
    if agent.task_type and str(agent.task_type).strip():
        return True
    if source_path and ".writ" in source_path.parts:
        return True
    return False


def lint(
    agent: InstructionConfig,
    source_path: Path | None = None,
) -> list[LintResult]:
    """Run all lint checks. Returns list of findings."""
    results: list[LintResult] = []
    writ_managed = _is_writ_managed(agent, source_path)

    results.extend(_check_name(agent))
    results.extend(_check_instructions_length(agent))
    results.extend(_check_contradictions(agent))
    results.extend(_check_weak_language(agent))
    results.extend(_check_expert_preamble(agent))
    results.extend(_check_instruction_bloat(agent))
    results.extend(_check_no_verification(agent))
    results.extend(_check_has_commands(agent))
    results.extend(_check_excessive_examples(agent))
    results.extend(_check_dead_content(agent))
    results.extend(_check_has_boundaries(agent))
    results.extend(_check_has_examples(agent))
    results.extend(_check_mixed_concerns(agent))

    results.extend(_check_missing_metadata(agent, source_path, writ_managed))
    results.extend(_check_empty_globs(agent))

    if writ_managed:
        results.extend(_check_description(agent))
        results.extend(_check_tags(agent))
        results.extend(_check_project_context(agent))
        results.extend(_check_composition_references(agent))

    return results


def _check_name(agent: InstructionConfig) -> list[LintResult]:
    results: list[LintResult] = []
    if not agent.name:
        results.append(LintResult(
            level="error",
            rule="name-required",
            message="Agent name is required.",
            base_penalty=10,
        ))
    elif not re.match(r"^[a-z0-9][a-z0-9-]*$", agent.name):
        results.append(LintResult(
            level="warning",
            rule="name-format",
            message=(
                f"Agent name '{agent.name}' should be "
                "lowercase alphanumeric with hyphens."
            ),
            base_penalty=5,
        ))
    return results


def _check_instructions_length(
    agent: InstructionConfig,
) -> list[LintResult]:
    results: list[LintResult] = []
    if not agent.instructions:
        results.append(LintResult(
            level="warning",
            rule="instructions-empty",
            message=(
                "Agent has no instructions. "
                "Add instructions for it to be useful."
            ),
            base_penalty=25,
        ))
        return results

    word_count = len(agent.instructions.split())
    if word_count > 2000:
        results.append(LintResult(
            level="warning",
            rule="instructions-long",
            message=(
                f"Instructions are {word_count} words. Research "
                "shows shorter instructions perform better. "
                "Consider trimming to under 2000 words."
            ),
            base_penalty=10,
        ))
    elif word_count < 20:
        results.append(LintResult(
            level="info",
            rule="instructions-short",
            message=(
                f"Instructions are only {word_count} words. "
                "Consider adding more context for better results."
            ),
            base_penalty=5,
        ))
    return results


def _check_description(agent: InstructionConfig) -> list[LintResult]:
    results: list[LintResult] = []
    if not agent.description:
        results.append(LintResult(
            level="info",
            rule="description-missing",
            message=(
                "No description set. A good description "
                "helps with discovery and team communication."
            ),
            base_penalty=3,
        ))
    elif len(agent.description) < 10:
        results.append(LintResult(
            level="info",
            rule="description-short",
            message="Description is very short. Consider being more descriptive.",
            base_penalty=2,
        ))
    return results


def _check_tags(agent: InstructionConfig) -> list[LintResult]:
    results: list[LintResult] = []
    if not agent.tags:
        results.append(LintResult(
            level="info",
            rule="tags-missing",
            message=(
                "No tags set. Tags improve discoverability "
                "when published."
            ),
            base_penalty=0,
        ))
    return results


def _check_project_context(
    agent: InstructionConfig,
) -> list[LintResult]:
    results: list[LintResult] = []
    if agent.composition.project_context:
        ctx_path = Path.cwd() / ".writ" / "project-context.md"
        if not ctx_path.exists():
            results.append(LintResult(
                level="info",
                rule="project-context-missing",
                message=(
                    "Agent expects project context but "
                    ".writ/project-context.md doesn't exist. "
                    "Run 'writ init' to generate it."
                ),
            ))
    return results


def _check_composition_references(
    agent: InstructionConfig,
) -> list[LintResult]:
    results: list[LintResult] = []
    agents_dir = Path.cwd() / ".writ" / "agents"

    for parent_name in agent.composition.inherits_from:
        if not (agents_dir / f"{parent_name}.yaml").exists():
            results.append(LintResult(
                level="warning",
                rule="inherit-missing",
                message=(
                    f"Agent inherits from '{parent_name}' but "
                    "no agent with that name exists."
                ),
                base_penalty=5,
            ))

    for source_name in agent.composition.receives_handoff_from:
        if not (agents_dir / f"{source_name}.yaml").exists():
            results.append(LintResult(
                level="warning",
                rule="handoff-source-missing",
                message=(
                    f"Agent receives handoff from "
                    f"'{source_name}' but no agent with that "
                    "name exists."
                ),
                base_penalty=5,
            ))

    return results


def _check_contradictions(
    agent: InstructionConfig,
) -> list[LintResult]:
    results: list[LintResult] = []
    if not agent.instructions:
        return results

    text = agent.instructions.lower()
    lines = text.split("\n")

    always_patterns: list[str] = []
    never_patterns: list[str] = []
    for line in lines:
        always_patterns.extend(
            re.findall(r"\balways\s+(?:use\s+)?(\w+)", line),
        )
        never_patterns.extend(
            re.findall(r"\bnever\s+(?:use\s+)?(\w+)", line),
        )

    for word in set(always_patterns) & set(never_patterns):
        results.append(LintResult(
            level="warning",
            rule="contradiction",
            message=(
                "Possible contradiction: both 'always' and "
                f"'never' used with '{word}'."
            ),
            base_penalty=15,
        ))

    return results


# ---------------------------------------------------------------------------
# New v0.2.0 rules
# ---------------------------------------------------------------------------


def _check_weak_language(
    agent: InstructionConfig,
) -> list[LintResult]:
    """Flag vague/suggestion language that models treat as optional."""
    if not agent.instructions:
        return []

    prose = _prose_text(agent.instructions)
    prose_lines = prose.split("\n")
    results: list[LintResult] = []

    for line_idx, line in enumerate(prose_lines, start=1):
        for pattern, phrase in WEAK_LANGUAGE_PATTERNS:
            if pattern.search(line):
                results.append(LintResult(
                    level="warning",
                    rule="weak-language",
                    message=(
                        f"Vague language '{phrase}' -- models "
                        "treat suggestions as optional. "
                        "Use imperative commands instead."
                    ),
                    line=line_idx,
                    base_penalty=15,
                ))
                break  # one match per line

    return results


def _check_expert_preamble(
    agent: InstructionConfig,
) -> list[LintResult]:
    """Flag 'You are an expert...' openings that waste tokens."""
    if not agent.instructions:
        return []

    first_line = agent.instructions.strip().split("\n")[0].strip()
    if EXPERT_PREAMBLE_PATTERN.match(first_line):
        return [LintResult(
            level="info",
            rule="expert-preamble",
            message=(
                "'You are an expert...' preamble wastes "
                "10-15 tokens with no measurable impact. "
                "Consider removing."
            ),
            line=1,
            base_penalty=5,
        )]
    return []


def _check_instruction_bloat(
    agent: InstructionConfig,
) -> list[LintResult]:
    """Flag instructions exceeding token budget thresholds."""
    if not agent.instructions:
        return []

    char_count = len(agent.instructions)
    results: list[LintResult] = []

    if char_count > 5000:
        pct = char_count * 100 // 5000 - 100
        results.append(LintResult(
            level="error",
            rule="instruction-bloat",
            message=(
                f"Instructions are {char_count:,} chars "
                f"({pct}% over 5000 limit). "
                "Over-specification reduces agent success "
                "rates by 20%+."
            ),
            base_penalty=25,
        ))
    elif char_count > 2000:
        results.append(LintResult(
            level="warning",
            rule="instruction-bloat",
            message=(
                f"Instructions are {char_count:,} chars "
                "(threshold: 2000). Consider trimming -- "
                "shorter instructions perform better."
            ),
            base_penalty=15,
        ))

    return results


def _check_no_verification(
    agent: InstructionConfig,
) -> list[LintResult]:
    """Flag when no verification commands are present."""
    if not agent.instructions:
        return []

    prose = _prose_text(agent.instructions)
    full_text = agent.instructions

    has_keyword = bool(VERIFICATION_KEYWORDS.search(prose))
    has_backtick = bool(COMMAND_PATTERN.search(full_text))

    if not has_keyword and not has_backtick:
        return [LintResult(
            level="warning",
            rule="no-verification",
            message=(
                "No verification commands found. Agents "
                "can't check their own work without "
                "test/build/lint commands (2-3x quality "
                "impact)."
            ),
            base_penalty=15,
        )]
    return []


def _check_has_commands(
    agent: InstructionConfig,
) -> list[LintResult]:
    """Positive check: flag when no executable commands present."""
    if not agent.instructions:
        return []

    if not COMMAND_PATTERN.search(agent.instructions):
        return [LintResult(
            level="info",
            rule="has-commands",
            message=(
                "No executable commands found "
                "(backtick-wrapped). Add build/test/lint "
                "commands so the agent can verify its work."
            ),
            base_penalty=12,
        )]
    return []


# ---------------------------------------------------------------------------
# v0.2.1 rules
# ---------------------------------------------------------------------------

DEAD_CONTENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"<!--[^>]*-->", re.I), "HTML comment"),
    (re.compile(r"#\s*TODO\b", re.I), "# TODO"),
    (re.compile(r"//\s*FIXME\b", re.I), "// FIXME"),
    (re.compile(r"//\s*PLACEHOLDER\b", re.I), "// PLACEHOLDER"),
]

BOUNDARY_PATTERN = re.compile(
    r"\b(?:always|never|do not|must not|ask first)\b",
    re.I,
)


def _check_excessive_examples(
    agent: InstructionConfig,
) -> list[LintResult]:
    """Count code blocks in instructions, flag if >5."""
    if not agent.instructions:
        return []

    code_blocks = re.findall(r"```[\s\S]*?```", agent.instructions)
    if len(code_blocks) > 5:
        return [LintResult(
            level="warning",
            rule="excessive-examples",
            message=(
                f"Found {len(code_blocks)} code blocks in prose. "
                "More than 5 examples can dilute focus. "
                "Consider trimming to 3-5 key examples."
            ),
            base_penalty=10,
        )]
    return []


def _check_missing_metadata(
    agent: InstructionConfig,
    source_path: Path | None,
    writ_managed: bool = False,
) -> list[LintResult]:
    """Check YAML frontmatter in .mdc, task_type/description in writ YAML."""
    results: list[LintResult] = []

    if source_path and source_path.suffix == ".mdc":
        try:
            raw = source_path.read_text(encoding="utf-8")
            if not raw.strip().startswith("---"):
                results.append(LintResult(
                    level="info",
                    rule="missing-metadata",
                    message=(
                        ".mdc file should have YAML frontmatter "
                        "starting with '---'."
                    ),
                    base_penalty=5,
                ))
        except OSError:
            pass
    elif writ_managed:
        if not agent.task_type or not str(agent.task_type).strip():
            results.append(LintResult(
                level="info",
                rule="missing-metadata",
                message=(
                    "YAML config should have task_type "
                    "(agent, rule, context, program)."
                ),
                base_penalty=5,
            ))
        if not agent.description or len(agent.description.strip()) < 10:
            results.append(LintResult(
                level="info",
                rule="missing-metadata",
                message=(
                    "YAML config should have a meaningful "
                    "description (10+ chars)."
                ),
                base_penalty=5,
            ))

    return results


def _check_empty_globs(agent: InstructionConfig) -> list[LintResult]:
    """Check format_overrides.cursor.globs for empty string."""
    cursor = agent.format_overrides and agent.format_overrides.cursor
    if cursor and cursor.globs == "":
        return [LintResult(
            level="info",
            rule="empty-globs",
            message=(
                "format_overrides.cursor.globs is empty string. "
                "Use a valid glob or omit."
            ),
            base_penalty=5,
        )]
    return []


def _check_dead_content(agent: InstructionConfig) -> list[LintResult]:
    """Detect TODO, FIXME, PLACEHOLDER, HTML comments in prose."""
    if not agent.instructions:
        return []

    prose = _prose_text(agent.instructions)
    prose_lines = prose.split("\n")
    results: list[LintResult] = []

    for line_idx, line in enumerate(prose_lines, start=1):
        for pattern, label in DEAD_CONTENT_PATTERNS:
            if pattern.search(line):
                results.append(LintResult(
                    level="warning",
                    rule="dead-content",
                    message=(
                        f"Found '{label}' in prose. "
                        "Remove placeholders before publishing."
                    ),
                    line=line_idx,
                    base_penalty=10,
                ))
                break

    return results


def _check_has_boundaries(agent: InstructionConfig) -> list[LintResult]:
    """Positive check: flag info when no boundary language in prose."""
    if not agent.instructions:
        return []

    prose = _prose_text(agent.instructions)
    if len(prose.strip()) < 20:
        return []

    if not BOUNDARY_PATTERN.search(prose):
        return [LintResult(
            level="info",
            rule="has-boundaries",
            message=(
                "No boundary language found (always/never/do not/"
                "must not/ask first). Add clear constraints."
            ),
            base_penalty=12,
        )]
    return []


def _check_has_examples(agent: InstructionConfig) -> list[LintResult]:
    """Positive check: flag info when no code blocks present."""
    if not agent.instructions:
        return []

    if "```" not in agent.instructions:
        return [LintResult(
            level="info",
            rule="has-examples",
            message=(
                "No code blocks found. Examples improve "
                "agent performance significantly."
            ),
            base_penalty=8,
        )]
    return []


def _extract_heading_texts(text: str) -> list[str]:
    """Extract heading text from markdown, excluding code fences."""
    prose = _prose_text(text)
    if not prose.strip():
        return []

    md = MarkdownIt()
    tokens = md.parse(prose)
    headings: list[str] = []
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open" and i + 1 < len(tokens):
            next_tok = tokens[i + 1]
            if next_tok.type == "inline" and next_tok.content:
                headings.append(next_tok.content.strip())
    return headings


def _topic_clusters(headings: list[str]) -> int:
    """Group headings by keyword overlap, return cluster count."""
    if len(headings) <= 2:
        return len(headings)

    stop = {"the", "a", "an", "and", "or", "for", "of", "in", "on", "to"}
    clusters: list[set[str]] = []

    for h in headings:
        words = {
            w.lower() for w in re.findall(r"\b\w+\b", h)
            if w.lower() not in stop and len(w) > 1
        }
        if not words:
            continue

        merged = False
        for c in clusters:
            if words & c:
                c.update(words)
                merged = True
                break
        if not merged:
            clusters.append(words)

    for i in range(len(clusters) - 1, -1, -1):
        for j in range(i):
            if clusters[j] & clusters[i]:
                clusters[j].update(clusters[i])
                clusters.pop(i)
                break

    return len(clusters)


def _check_mixed_concerns(agent: InstructionConfig) -> list[LintResult]:
    """Detect >2 topic clusters via heading keyword analysis."""
    if not agent.instructions:
        return []

    headings = _extract_heading_texts(agent.instructions)
    if len(headings) < 3:
        return []

    n = _topic_clusters(headings)
    if n > 2:
        return [LintResult(
            level="warning",
            rule="mixed-concerns",
            message=(
                f"Detected {n} distinct topic clusters in headings. "
                "Consider splitting into focused instructions."
            ),
            base_penalty=10,
        )]
    return []


# ---------------------------------------------------------------------------
# v2 scoring engine
# ---------------------------------------------------------------------------

# -- Section dataclass for parsed markdown structure -------------------------

@dataclass
class Section:
    """A markdown section: heading text, content, nesting level, line."""

    heading: str
    content: str
    level: int
    line_number: int


# -- Specific-token patterns for specificity density ------------------------

SPECIFIC_TOKEN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"`[^`]+`"),
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:lines?|chars?|tokens?"
               r"|%|ms|sec|seconds?|KB|MB|GB)\b"),
    re.compile(r"(?:[a-zA-Z_][\w]*\.)+[a-zA-Z_][\w]*"),
    re.compile(r"[/\\][\w./-]+\.\w+"),
    re.compile(r"\bv?\d+\.\d+(?:\.\d+)?\b"),
]

# -- Verification level definitions (checked top-down, highest first) --------

_VER_CLOSURE = re.compile(
    r"\b(?:definition of done|done when|complete when"
    r"|task is complete|verify by)\b", re.I,
)
_VER_CMD_CRITERIA = re.compile(
    r"`[^`]*(?:test|lint|check|build|verify)[^`]*`"
    r".*\b(?:must|should|expect|assert|pass|fail|exit)\b", re.I,
)
_VER_BACKTICK_CMD = re.compile(
    r"`[^`]*(?:test|lint|check|build|verify|run)[^`]*`", re.I,
)
_VER_NAMED_TOOL = re.compile(
    r"\b(?:pytest|jest|mocha|vitest|eslint|ruff|mypy"
    r"|cargo\s+test|npm\s+test|go\s+test|tsc)\b", re.I,
)
_VER_VAGUE = re.compile(
    r"\b(?:test|verify|check|validate|ensure)\b", re.I,
)

VERIFICATION_LEVELS: list[tuple[int, re.Pattern[str]]] = [
    (5, _VER_CLOSURE),
    (4, _VER_CMD_CRITERIA),
    (3, _VER_BACKTICK_CMD),
    (2, _VER_NAMED_TOOL),
    (1, _VER_VAGUE),
]

# -- Coverage topics: heading pattern + content validation -------------------

COVERAGE_TOPICS: dict[str, re.Pattern[str]] = {
    "commands": re.compile(
        r"\b(?:command|script|run|setup|usage|install"
        r"|deploy|build|getting.started)", re.I,
    ),
    "testing": re.compile(
        r"\b(?:test|spec|coverage|quality|qa"
        r"|jest|pytest|vitest|verify)", re.I,
    ),
    "boundaries": re.compile(
        r"\b(?:don.?t|never|always|rule|constraint"
        r"|boundar|limit|prohibit|require|must)", re.I,
    ),
    "errors": re.compile(
        r"\b(?:error|exception|fail|debug"
        r"|troubleshoot|issue|handle)", re.I,
    ),
    "style": re.compile(
        r"\b(?:style|format|naming|convention|pattern"
        r"|standard|guideline|lint)", re.I,
    ),
}

# -- Critical caps (SonarQube pattern) --------------------------------------

CRITICAL_CAPS: dict[str, int] = {
    "contradiction": 25,
    "instruction-bloat-5k": 40,
}

# -- Imperative verb starters -----------------------------------------------

_IMPERATIVE_STARTERS = re.compile(
    r"^\s*[-*]?\s*(?:Use|Run|Add|Set|Create|Install|Configure"
    r"|Enable|Disable|Check|Test|Build|Write|Read|Delete|Update"
    r"|Ensure|Avoid|Do not|Never|Always|Include|Exclude|Keep"
    r"|Remove|Define|Specify|Implement|Return|Throw|Call|Apply"
    r"|Follow|Prefer|Require|Maintain|Validate|Format)\b",
    re.I,
)


# -- Phase 1: Measurement functions -----------------------------------------

def parse_markdown_sections(content: str) -> list[Section]:
    """Split markdown content by headings into Section objects.

    Skips lines inside fenced code blocks (``` ... ```) so that
    shell comments like ``# comment`` aren't mistaken for headings.
    """
    lines = content.split("\n")
    sections: list[Section] = []
    current_heading = ""
    current_level = 0
    current_line = 1
    buf: list[str] = []
    in_fence = False

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            buf.append(line)
            continue

        if in_fence:
            buf.append(line)
            continue

        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            if current_heading or buf:
                sections.append(Section(
                    heading=current_heading,
                    content="\n".join(buf),
                    level=current_level,
                    line_number=current_line,
                ))
            current_heading = m.group(2).strip()
            current_level = len(m.group(1))
            current_line = i
            buf = []
        else:
            buf.append(line)

    if current_heading or buf:
        sections.append(Section(
            heading=current_heading,
            content="\n".join(buf),
            level=current_level,
            line_number=current_line,
        ))
    return sections


def measure_specificity_density(content: str) -> float:
    """Ratio of specific tokens to total word-level tokens."""
    words = content.split()
    if not words:
        return 0.0
    specific = 0
    for pat in SPECIFIC_TOKEN_PATTERNS:
        specific += len(pat.findall(content))
    return min(1.0, specific / len(words))


def measure_verification_level(content: str) -> int:
    """0-5 gradient for verification quality."""
    for level, pattern in VERIFICATION_LEVELS:
        if pattern.search(content):
            return level
    return 0


def measure_information_density(content: str) -> float:
    """Ratio of actionable lines to total non-empty prose lines."""
    lines = [
        ln for ln in content.split("\n")
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if not lines:
        return 0.0
    actionable_pat = re.compile(
        r"`[^`]+`|\b\d+(?:\.\d+)?(?:\s*(?:lines?|chars?|%|ms|sec))"
        r"|\b(?:always|never|must|do not|don.?t)\b"
        r"|[/\\][\w./-]+\.\w+",
        re.I,
    )
    actionable = sum(1 for ln in lines if actionable_pat.search(ln))
    return actionable / len(lines)


def count_imperative(lines: list[str]) -> int:
    """Count lines starting with imperative verbs."""
    return sum(1 for ln in lines if _IMPERATIVE_STARTERS.match(ln))


def has_substantive_section(
    sections: list[Section],
    topic_pattern: re.Pattern[str],
) -> bool:
    """True if any section heading matches topic AND has 2+ content lines."""
    for sec in sections:
        if topic_pattern.search(sec.heading):
            real_lines = [
                ln for ln in sec.content.split("\n") if ln.strip()
            ]
            if len(real_lines) >= 2:
                return True
    return False


def length_factor(chars: int) -> float:
    """Coverage expectation multiplier based on instruction length."""
    if chars < 100:
        return 0.2
    if chars < 300:
        return 0.5
    if chars < 800:
        return 0.8
    if chars < 2000:
        return 1.0
    if chars < 5000:
        return 0.9
    return 0.7


# -- Phase 2: v2 dimension scorers ------------------------------------------

def _v2_score_clarity(signals: dict) -> int:
    """Positive+negative scorer for clarity (was specificity)."""
    score = 30.0
    score += min(25.0, signals["specificity_density"] * 80)
    score += min(15.0, signals["imperative_ratio"] * 20)
    score += min(15.0, signals["quantitative_count"] * 5)
    score += min(15.0, signals["backtick_command_count"] * 5)
    score -= min(30.0, signals["vague_ratio"] * 40)
    if signals["expert_preamble_present"]:
        score -= 10
    return max(10, min(100, round(score)))


def _v2_score_verification(content: str) -> int:
    """Direct mapping from verification level to score."""
    level = measure_verification_level(content)
    mapping = {0: 10, 1: 20, 2: 45, 3: 70, 4: 85, 5: 95}
    return mapping.get(level, 10)


def _v2_score_coverage(
    sections: list[Section],
    chars: int,
) -> int:
    """Substance-aware coverage scoring."""
    score = 20.0
    for _topic, pattern in COVERAGE_TOPICS.items():
        if has_substantive_section(sections, pattern):
            score += 16
    return max(10, min(100, round(score * length_factor(chars))))


def _v2_score_brevity(chars: int, signals: dict) -> int:
    """Length-curve scoring penalizing short+empty and bloat."""
    density = signals["information_density"]
    if chars < 200 and density < 0.1:
        score = 30.0
    elif chars < 500:
        score = 85.0
    elif chars < 1000:
        score = 90.0
    elif chars < 2000:
        score = 80.0
    elif chars < 5000:
        score = 50.0
    else:
        score = 25.0
    score -= signals["dead_content_count"] * 8
    if signals["expert_preamble_present"]:
        score -= 10
    return max(10, min(100, round(score)))


def _v2_score_structure(
    content: str,
    sections: list[Section],
    has_frontmatter: bool,
) -> int:
    """Positive signal accumulation for structure."""
    score = 20.0
    if has_frontmatter:
        score += 20
    heading_count = sum(1 for s in sections if s.heading)
    score += min(20.0, heading_count * 5)
    bullet_count = len(re.findall(r"^\s*[-*+]\s", content, re.M))
    score += min(15.0, bullet_count * 3)
    levels_used = {s.level for s in sections if s.heading}
    if len(levels_used) >= 2:
        score += 10
    sections_with_code = sum(
        1 for s in sections
        if "```" in s.content or "`" in s.content
    )
    if sections_with_code:
        score += 5
    return max(10, min(100, round(score)))


def _v2_score_examples(content: str) -> int:
    """Score based on code block count with diminishing returns."""
    blocks = len(re.findall(r"```[\s\S]*?```", content))
    if blocks == 0:
        return 10
    if blocks <= 2:
        return 50
    if blocks <= 5:
        return 80
    if blocks <= 8:
        return 70
    return 50


# -- Phase 5: Conditional section checks ------------------------------------

def _check_conditional_sections(
    sections: list[Section],
    chars: int,
) -> list[LintResult]:
    """Validate that sections have substance matching their heading."""
    results: list[LintResult] = []

    for sec in sections:
        heading_lower = sec.heading.lower()
        real_lines = [
            ln for ln in sec.content.split("\n") if ln.strip()
        ]

        if re.search(r"\bcommand", heading_lower):
            has_inline = bool(re.search(r"`[^`]+`", sec.content))
            has_fenced = bool(re.search(
                r"```[^\n]*\n.+?```", sec.content, re.DOTALL,
            ))
            if not has_inline and not has_fenced:
                results.append(LintResult(
                    level="warning",
                    rule="empty-command-section",
                    message=(
                        f"Section '{sec.heading}' has no "
                        "backtick-wrapped commands"
                    ),
                    line=sec.line_number,
                    base_penalty=8,
                ))

        if re.search(r"\btest", heading_lower):
            has_tool = bool(re.search(
                r"`[^`]+`|\b(?:pytest|jest|vitest|mocha"
                r"|cargo\s+test|npm\s+test)\b",
                sec.content, re.I,
            ))
            if not has_tool:
                results.append(LintResult(
                    level="warning",
                    rule="empty-testing-section",
                    message=(
                        f"Section '{sec.heading}' has no "
                        "test commands or tool names"
                    ),
                    line=sec.line_number,
                    base_penalty=8,
                ))

        if re.search(r"\bdon.?t|\bboundar|\bnever\b", heading_lower):
            list_items = [
                ln for ln in real_lines
                if re.match(r"\s*[-*+]\s", ln)
            ]
            if not list_items:
                results.append(LintResult(
                    level="info",
                    rule="empty-boundary-section",
                    message=(
                        f"Section '{sec.heading}' should "
                        "contain a list of boundary rules"
                    ),
                    line=sec.line_number,
                    base_penalty=5,
                ))

    heading_count = sum(1 for s in sections if s.heading)
    if chars > 1000 and heading_count < 2:
        results.append(LintResult(
            level="info",
            rule="long-without-structure",
            message=(
                "Instructions exceed 1000 chars but have "
                "fewer than 2 headings -- consider adding "
                "section structure"
            ),
            base_penalty=5,
        ))

    return results


# -- Grade computation (derived, never stored) -------------------------------

def _compute_grade(score: int) -> str:
    """Map 0-100 score to letter grade."""
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    if score >= 20:
        return "D"
    return "F"


# -- Raw signals collection (v2: includes new measurements) -----------------

def _collect_raw_signals(
    agent: InstructionConfig,
    results: list[LintResult],
    v2_signals: dict,
    sections: list[Section],
) -> dict:
    """Collect raw measurements for ML storage."""
    text = agent.instructions or ""
    prose = _prose_text(text)

    weak_count = sum(1 for r in results if r.rule == "weak-language")
    sentences = [s for s in re.split(r"[.!?]+", prose) if s.strip()]
    total_sentences = len(sentences)

    code_blocks = re.findall(r"```[\s\S]*?```", text)
    inline_commands = COMMAND_PATTERN.findall(text)
    headings = [
        ln for ln in text.split("\n") if ln.strip().startswith("#")
    ]

    has_boundaries = bool(re.search(
        r"\b(?:always|never|ask first|do not|must not)\b",
        prose, re.I,
    ))
    has_testing = bool(re.search(
        r"\b(?:test|pytest|jest|mocha|vitest|cargo test"
        r"|npm test)\b",
        prose, re.I,
    ))
    has_error = bool(re.search(
        r"\b(?:error|exception|catch|handle|fail|fallback)\b",
        prose, re.I,
    ))
    has_edge = bool(re.search(
        r"\b(?:edge case|corner case|special case"
        r"|when .* fails|if .* missing)\b",
        prose, re.I,
    ))
    has_closure = bool(re.search(
        r"\b(?:definition of done|done when"
        r"|complete when|task is complete)\b",
        prose, re.I,
    ))
    ver_cmds = len(re.findall(
        r"`[^`]*(?:test|lint|check|build|verify)[^`]*`",
        text, re.I,
    ))

    core_areas = sum([
        bool(inline_commands), has_testing,
        bool(headings), has_boundaries,
        has_error, has_edge,
    ])

    return {
        "weak_language_count": weak_count,
        "imperative_sentence_ratio": round(
            v2_signals["imperative_ratio"], 2,
        ),
        "imperative_ratio": round(
            v2_signals["imperative_ratio"], 2,
        ),
        "quantitative_threshold_count": v2_signals[
            "quantitative_count"
        ],
        "vague_phrase_count": weak_count,
        "vague_ratio": round(v2_signals["vague_ratio"], 3),
        "specificity_density": round(
            v2_signals["specificity_density"], 3,
        ),
        "information_density": round(
            v2_signals["information_density"], 3,
        ),
        "verification_level": v2_signals["verification_level"],
        "has_frontmatter": text.strip().startswith("---"),
        "heading_count": len(headings),
        "max_nesting_depth": max(
            (len(h) - len(h.lstrip("#")) for h in headings),
            default=0,
        ),
        "section_count": len(sections),
        "topic_count": _topic_clusters(
            _extract_heading_texts(text),
        ) if headings else 0,
        "has_commands": bool(inline_commands),
        "has_testing": has_testing,
        "has_boundaries": has_boundaries,
        "core_areas_covered": core_areas,
        "has_error_handling": has_error,
        "has_edge_cases": has_edge,
        "char_count": len(text),
        "token_count": len(text) // 4,
        "expert_preamble_present": v2_signals[
            "expert_preamble_present"
        ],
        "dead_content_count": v2_signals["dead_content_count"],
        "signal_to_noise_ratio": round(
            1.0 - (weak_count / max(total_sentences, 1)), 2,
        ),
        "code_block_count": len(code_blocks),
        "good_bad_pair_count": min(
            len(re.findall(
                r"<good[_-]example>|<bad[_-]example>|"
                r"(?:good|bad|correct|incorrect)\s+example",
                text, re.I,
            )) // 2,
            5,
        ),
        "example_diversity": min(len(code_blocks), 5),
        "executable_command_count": len(inline_commands),
        "backtick_command_count": v2_signals[
            "backtick_command_count"
        ],
        "has_closure_definition": has_closure,
        "verification_method_count": ver_cmds,
        "patterns_present": [],
        "pattern_count": 0,
        "anti_patterns_present": [
            r.rule for r in results
            if r.level in ("error", "warning")
        ],
        "anti_pattern_count": sum(
            1 for r in results
            if r.level in ("error", "warning")
        ),
    }


# -- Main scoring function (v2) ---------------------------------------------

def compute_score(
    agent: InstructionConfig,
    results: list[LintResult],
) -> LintScore:
    """v2 scoring: earn-up model with positive signals and critical caps."""
    text = agent.instructions or ""
    chars = len(text)
    prose = _prose_text(text)

    sections = parse_markdown_sections(text)
    has_fm = bool(re.match(r"^---\s*\n", text))

    results = list(results)
    results.extend(_check_conditional_sections(sections, chars))

    prose_lines = [ln for ln in prose.split("\n") if ln.strip()]
    weak_count = sum(1 for r in results if r.rule == "weak-language")
    sentences = [s for s in re.split(r"[.!?]+", prose) if s.strip()]
    total_sentences = max(len(sentences), 1)

    v2_signals = {
        "specificity_density": measure_specificity_density(text),
        "information_density": measure_information_density(text),
        "verification_level": measure_verification_level(text),
        "vague_ratio": weak_count / total_sentences,
        "imperative_ratio": (
            count_imperative(prose_lines)
            / max(len(prose_lines), 1)
        ),
        "quantitative_count": len(re.findall(
            r"\b\d+(?:\.\d+)?\s*"
            r"(?:lines?|chars?|tokens?|%|ms|sec|seconds?"
            r"|KB|MB|GB)\b",
            text,
        )),
        "backtick_command_count": len(re.findall(r"`[^`]+`", text)),
        "expert_preamble_present": any(
            r.rule == "expert-preamble" for r in results
        ),
        "dead_content_count": sum(
            1 for r in results if r.rule == "dead-content"
        ),
    }

    clarity = _v2_score_clarity(v2_signals)
    verification = _v2_score_verification(text)
    coverage = _v2_score_coverage(sections, chars)
    brevity = _v2_score_brevity(chars, v2_signals)
    structure = _v2_score_structure(text, sections, has_fm)
    examples = _v2_score_examples(text)

    headline = round(
        clarity * DIMENSION_WEIGHTS["clarity"]
        + verification * DIMENSION_WEIGHTS["verification"]
        + coverage * DIMENSION_WEIGHTS["coverage"]
        + brevity * DIMENSION_WEIGHTS["brevity"]
        + structure * DIMENSION_WEIGHTS["structure"]
        + examples * DIMENSION_WEIGHTS["examples"]
    )

    for r in results:
        if r.rule == "contradiction":
            headline = min(headline, CRITICAL_CAPS["contradiction"])
    if chars > 5000:
        has_bloat = any(
            r.rule == "instruction-bloat" for r in results
        )
        if has_bloat:
            headline = min(
                headline,
                CRITICAL_CAPS["instruction-bloat-5k"],
            )

    headline = max(10, min(100, headline))
    grade = _compute_grade(headline)

    dims = [
        DimensionScore(
            name="clarity", label="Clarity",
            score=clarity,
            summary=_dim_summary(
                "clarity", clarity, v2_signals,
            ),
        ),
        DimensionScore(
            name="structure", label="Structure",
            score=structure,
            summary=_dim_summary(
                "structure", structure, v2_signals,
            ),
        ),
        DimensionScore(
            name="coverage", label="Coverage",
            score=coverage,
            summary=_dim_summary(
                "coverage", coverage, v2_signals,
            ),
        ),
        DimensionScore(
            name="brevity", label="Brevity",
            score=brevity,
            summary=_dim_summary(
                "brevity", brevity, v2_signals,
            ),
        ),
        DimensionScore(
            name="examples", label="Examples",
            score=examples,
            summary=_dim_summary(
                "examples", examples, v2_signals,
            ),
        ),
        DimensionScore(
            name="verification", label="Verification",
            score=verification,
            summary=_dim_summary(
                "verification", verification, v2_signals,
            ),
        ),
    ]

    suggestions = _generate_suggestions(dims, results)
    raw_signals = _collect_raw_signals(
        agent, results, v2_signals, sections,
    )
    raw_signals["grade"] = grade

    scored_results = sorted(
        [r for r in results if not r.rule.startswith("_")],
        key=lambda r: r.base_penalty,
        reverse=True,
    )

    return LintScore(
        score=headline,
        dimensions=dims,
        issues=scored_results,
        suggestions=suggestions,
        raw_signals=raw_signals,
        tier="code",
    )


# -- Dimension summaries (v2) -----------------------------------------------

def _dim_summary(
    dim: str,
    score: int,
    signals: dict,
) -> str:
    """Generate a one-line summary for a dimension score."""
    if score >= 90:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        if dim == "clarity":
            return "Moderate -- some specific signals present"
        if dim == "verification":
            return "Basic verification present"
        return "Adequate"

    if dim == "clarity":
        vr = signals.get("vague_ratio", 0)
        if vr > 0.3:
            return "High ratio of vague language"
        sd = signals.get("specificity_density", 0)
        if sd < 0.05:
            return "Very few specific tokens (paths, numbers, commands)"
        return "Could be more specific"

    if dim == "coverage":
        return "Key topics missing or lack substance"

    if dim == "brevity":
        if signals.get("information_density", 1) < 0.1:
            return "Short but lacks actionable content"
        return "Could be more concise"

    if dim == "verification":
        vl = signals.get("verification_level", 0)
        if vl == 0:
            return "No verification commands found"
        return "Vague verification only (no concrete commands)"

    if dim == "examples":
        return "No code examples found"

    if dim == "structure":
        return "Needs headings and organized sections"

    return "Room for improvement"


# -- Suggestion generation (v2) ---------------------------------------------

def _generate_suggestions(
    dimensions: list[DimensionScore],
    results: list[LintResult],
) -> list[str]:
    """Top 3 improvements targeting lowest-scoring dimensions."""
    suggestions: list[str] = []
    sorted_dims = sorted(dimensions, key=lambda d: d.score)

    for dim in sorted_dims:
        if len(suggestions) >= 3:
            break

        if dim.name == "clarity" and dim.score < 70:
            weak = sum(
                1 for r in results if r.rule == "weak-language"
            )
            if weak:
                suggestions.append(
                    f"Replace {weak} vague phrase"
                    f"{'s' if weak > 1 else ''} with "
                    "imperative commands (e.g., 'Use X' "
                    "instead of 'Try to use X')"
                )
            else:
                suggestions.append(
                    "Add specific file paths, tool names, "
                    "and numeric thresholds to increase "
                    "clarity"
                )

        elif dim.name == "verification" and dim.score < 70:
            suggestions.append(
                "Add backtick-wrapped test/build/lint "
                "commands so the agent can verify its own "
                "work (2-3x quality impact)"
            )

        elif dim.name == "coverage" and dim.score < 70:
            suggestions.append(
                "Add dedicated sections (## Testing, "
                "## Boundaries) with 2+ lines of specific "
                "guidance each"
            )

        elif dim.name == "brevity" and dim.score < 70:
            suggestions.append(
                "Trim instruction length -- "
                "over-specification reduces agent "
                "success rates by 20%+"
            )

        elif dim.name == "examples" and dim.score < 70:
            suggestions.append(
                "Add 1-3 code examples showing "
                "desired input/output patterns"
            )

        elif dim.name == "structure" and dim.score < 70:
            suggestions.append(
                "Add section headings (##) and bullet "
                "lists to improve scannability"
            )

    return suggestions
