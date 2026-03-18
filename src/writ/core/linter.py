"""Validate instruction quality and compute quality scores.

Based on findings from "Evaluating AGENTS.md" (arXiv:2602.11988),
cursor-doctor (50-repo scan, 998 issues), AGENTIF (NeurIPS 2025),
MCP Smells (arXiv:2602.14878), and Boris Cherny's verification research.

Scoring uses 6 user-facing dimensions (Clarity, Structure, Coverage,
Brevity, Examples, Verification) each 0-100, with a weighted headline.
"""

from __future__ import annotations

import re
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


def lint(
    agent: InstructionConfig,
    source_path: Path | None = None,
) -> list[LintResult]:
    """Run all lint checks. Returns list of findings."""
    results: list[LintResult] = []

    results.extend(_check_name(agent))
    results.extend(_check_instructions_length(agent))
    results.extend(_check_description(agent))
    results.extend(_check_tags(agent))
    results.extend(_check_project_context(agent))
    results.extend(_check_composition_references(agent))
    results.extend(_check_contradictions(agent))
    results.extend(_check_weak_language(agent))
    results.extend(_check_expert_preamble(agent))
    results.extend(_check_instruction_bloat(agent))
    results.extend(_check_no_verification(agent))
    results.extend(_check_has_commands(agent))
    results.extend(_check_excessive_examples(agent))
    results.extend(_check_missing_metadata(agent, source_path))
    results.extend(_check_empty_globs(agent))
    results.extend(_check_dead_content(agent))
    results.extend(_check_has_boundaries(agent))
    results.extend(_check_has_examples(agent))
    results.extend(_check_mixed_concerns(agent))

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
) -> list[LintResult]:
    """Check YAML frontmatter in .mdc, task_type/description in YAML configs."""
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
    else:
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
# Scoring engine
# ---------------------------------------------------------------------------

_DECAY = 0.7


def _compute_dimension_score(
    issues: list[LintResult],
    char_count: int,
    base: int = 100,
) -> int:
    """Compute a 0-100 score for one dimension.

    Uses diminishing deductions with length normalization.
    """
    score = float(base)

    sorted_issues = sorted(
        issues, key=lambda x: x.base_penalty, reverse=True,
    )
    for i, issue in enumerate(sorted_issues):
        if issue.base_penalty <= 0:
            continue
        penalty = issue.base_penalty * (_DECAY ** i)
        score -= penalty

    effective_length = max(char_count, 200)
    length_factor = min(1.0, 800 / effective_length)
    total_deduction = base - score
    score = base - (total_deduction * (0.5 + 0.5 * length_factor))

    return max(10, min(100, round(score)))


_IMPERATIVE_RE = re.compile(
    r"(?:^|\n)\s*[-*]?\s*"
    r"(?:Use|Run|Add|Set|Create|Install|Configure|Enable"
    r"|Disable|Check|Test|Build|Write|Read|Delete|Update"
    r"|Ensure|Avoid|Do not|Never|Always)\b",
)


def _collect_raw_signals(
    agent: InstructionConfig,
    results: list[LintResult],
) -> dict:
    """Collect ~30 raw measurements for ML storage."""
    text = agent.instructions or ""
    prose = _prose_text(text)

    weak_count = sum(1 for r in results if r.rule == "weak-language")
    sentences = [s for s in re.split(r"[.!?]+", prose) if s.strip()]
    total_sentences = len(sentences)
    imperative_count = len(_IMPERATIVE_RE.findall(prose))
    imperative_ratio = imperative_count / max(total_sentences, 1)

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
        "imperative_sentence_ratio": round(imperative_ratio, 2),
        "quantitative_threshold_count": len(
            re.findall(r"\b\d+\b", prose),
        ),
        "vague_phrase_count": weak_count,
        "has_frontmatter": text.strip().startswith("---"),
        "heading_count": len(headings),
        "max_nesting_depth": max(
            (len(h) - len(h.lstrip("#")) for h in headings),
            default=0,
        ),
        "section_count": len(headings),
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
        "expert_preamble_present": any(
            r.rule == "expert-preamble" for r in results
        ),
        "dead_content_count": sum(
            1 for r in results if r.rule == "dead-content"
        ),
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


def compute_score(
    agent: InstructionConfig,
    results: list[LintResult],
) -> LintScore:
    """Compute quality score from lint results.

    Returns LintScore with 6 dimension scores (0-100 each),
    a weighted headline, raw signals, and suggestions.
    """
    text = agent.instructions or ""
    char_count = len(text)

    # Empty or near-empty instructions: content-dependent
    # dimensions should score very low since there's nothing
    # to evaluate for quality.
    _empty = not text or char_count < 20

    clarity_issues = [
        r for r in results
        if r.rule in ("weak-language", "expert-preamble")
    ]
    structure_issues = [
        r for r in results
        if r.rule in (
            "name-format", "name-required",
            "description-missing", "description-short",
            "missing-metadata", "empty-globs", "mixed-concerns",
        )
    ]
    coverage_issues = [
        r for r in results
        if r.rule in (
            "no-verification", "has-commands",
            "instructions-empty", "has-boundaries",
        )
    ]
    brevity_issues = [
        r for r in results
        if r.rule in (
            "instruction-bloat", "instructions-long", "dead-content",
        )
    ]
    examples_issues: list[LintResult] = [
        r for r in results
        if r.rule in ("excessive-examples", "has-examples")
    ]
    verification_issues = [
        r for r in results
        if r.rule in ("no-verification", "has-commands")
    ]

    if _empty:
        _no_content = LintResult(
            level="error",
            rule="_empty-content",
            message="No meaningful content",
            base_penalty=40,
        )
        clarity_issues.append(_no_content)
        coverage_issues.append(_no_content)
        verification_issues.append(_no_content)
        examples_issues.append(_no_content)

    clarity = _compute_dimension_score(clarity_issues, char_count)
    structure = _compute_dimension_score(
        structure_issues, char_count,
    )
    coverage = _compute_dimension_score(
        coverage_issues, char_count,
    )
    brevity = _compute_dimension_score(brevity_issues, char_count)
    examples = _compute_dimension_score(
        examples_issues, char_count,
    )
    verification = _compute_dimension_score(
        verification_issues, char_count,
    )

    headline = round(
        clarity * DIMENSION_WEIGHTS["clarity"]
        + structure * DIMENSION_WEIGHTS["structure"]
        + coverage * DIMENSION_WEIGHTS["coverage"]
        + brevity * DIMENSION_WEIGHTS["brevity"]
        + examples * DIMENSION_WEIGHTS["examples"]
        + verification * DIMENSION_WEIGHTS["verification"]
    )
    headline = max(10, min(100, headline))

    dims = [
        DimensionScore(
            name="clarity", label="Clarity",
            score=clarity,
            summary=_dim_summary("clarity", clarity, results),
        ),
        DimensionScore(
            name="structure", label="Structure",
            score=structure,
            summary=_dim_summary("structure", structure, results),
        ),
        DimensionScore(
            name="coverage", label="Coverage",
            score=coverage,
            summary=_dim_summary("coverage", coverage, results),
        ),
        DimensionScore(
            name="brevity", label="Brevity",
            score=brevity,
            summary=_dim_summary("brevity", brevity, results),
        ),
        DimensionScore(
            name="examples", label="Examples",
            score=examples,
            summary=_dim_summary("examples", examples, results),
        ),
        DimensionScore(
            name="verification", label="Verification",
            score=verification,
            summary=_dim_summary(
                "verification", verification, results,
            ),
        ),
    ]

    suggestions = _generate_suggestions(dims, results)
    raw_signals = _collect_raw_signals(agent, results)

    scored_results = sorted(
        [r for r in results if r.rule != "_no-code-blocks"],
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


def _dim_summary(
    dim: str,
    score: int,
    results: list[LintResult],
) -> str:
    """Generate a one-line summary for a dimension score."""
    if score >= 90:
        return "Excellent"
    if score >= 70:
        return "Good"

    if dim == "clarity":
        weak = sum(1 for r in results if r.rule == "weak-language")
        if weak:
            return (
                f"{weak} instance{'s' if weak > 1 else ''} "
                "of vague language"
            )
        return "Could be more specific"

    if dim == "coverage":
        missing = [
            r for r in results
            if r.rule in ("no-verification", "has-commands")
        ]
        if missing:
            return "Missing verification or commands"
        return "Incomplete coverage of core areas"

    if dim == "brevity":
        if any(r.rule == "instruction-bloat" for r in results):
            return "Exceeds recommended length"
        return "Could be more concise"

    if dim == "verification":
        if any(r.rule == "no-verification" for r in results):
            return "No verification commands found"
        return "Limited verification mechanisms"

    if dim == "examples":
        return "No code examples found"

    if dim == "structure":
        return "Structural improvements possible"

    return "Room for improvement"


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

        if dim.name == "clarity" and dim.score < 80:
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

        elif dim.name == "verification" and dim.score < 80:
            suggestions.append(
                "Add test/build/lint commands so the agent "
                "can verify its own work (2-3x quality impact)"
            )

        elif dim.name == "coverage" and dim.score < 80:
            suggestions.append(
                "Add boundary definitions "
                "(always/never/ask-first) and "
                "error handling guidance"
            )

        elif dim.name == "brevity" and dim.score < 80:
            suggestions.append(
                "Trim instruction length -- "
                "over-specification reduces agent "
                "success rates by 20%+"
            )

        elif dim.name == "examples" and dim.score < 80:
            suggestions.append(
                "Add 1-3 code examples showing "
                "desired input/output patterns"
            )

        elif dim.name == "structure" and dim.score < 80:
            suggestions.append(
                "Improve structure: add clear section "
                "headers and a description"
            )

    return suggestions
