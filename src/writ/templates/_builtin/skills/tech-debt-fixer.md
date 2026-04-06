# Tech Debt Fixer

Systematic technical debt detection and remediation. Spawns parallel analysis
tasks to scan for duplicated code, dead imports, complexity hotspots, and
structural issues -- then consolidates findings into a prioritized fix plan.

Inspired by 0xdarkmatter/claude-mods (techdebt), Boris Cherny's deduplication
workflow, and giulio-leone/vscode-agent-skills (tech-debt-reducer).

## When to Use

- End of a coding session (catch debt while context is fresh)
- Before a commit or PR (pre-merge cleanup)
- Starting a refactoring sprint
- When codebase "feels slow" to work in
- When the user asks to clean up, deduplicate, or reduce tech debt

## Step 1: Determine Scope

**Default**: Scan files changed since last commit.

```bash
git diff --name-only HEAD
git diff --name-only --cached
```

**Deep scan**: When explicitly requested, scan the entire codebase or a specific
directory. Use for refactoring sprints or major release prep.

## Step 2: Parallel Analysis

Run these four analysis passes. If the tool supports subagents or parallel tasks,
run them simultaneously. Otherwise, run sequentially.

### Pass 1: Duplication Scanner

Find duplicated or near-duplicate code blocks across the scoped files.

- Look for code blocks with >80% structural similarity
- Minimum threshold: 6+ consecutive lines duplicated in 2+ locations
- Check for copy-pasted functions with minor variable name differences
- Check for repeated patterns that should be extracted into shared utilities

**Severity:**
- P1: 30+ lines duplicated in 3+ locations
- P2: 15+ lines duplicated in 2+ locations
- P3: 6+ lines duplicated in 2 locations

### Pass 2: Dead Code Scanner

Find unused imports, variables, functions, and unreachable code.

- Unused imports (never referenced after import statement)
- Variables written but never read
- Functions/methods never called anywhere in the codebase
- Unreachable code after return/break/continue/raise
- Commented-out code blocks (>5 lines)

**Safety**: Only flag code as dead if no external references exist and it's not
part of a public API. Be conservative -- false positives waste time.

### Pass 3: Complexity Scanner

Identify overly complex functions and deeply nested logic.

- Functions exceeding 50 lines
- Cyclomatic complexity >10 (deeply branching logic)
- Nesting depth >4 levels
- Functions with >5 parameters
- God objects / classes that do too much (>300 lines)

### Pass 4: Structural Issues

Look for architectural smells and maintainability problems.

- Circular imports / dependencies
- Feature envy (function uses another module's data more than its own)
- Outdated dependencies with known issues
- Missing type annotations on public API functions
- Magic numbers / hardcoded values that should be constants

## Step 3: Consolidate Findings

After all passes complete:

1. **Deduplicate** -- Remove findings that overlap across categories
2. **Rank by severity** (P0-P3):
   - **P0 (Critical)**: Security-adjacent issues, blocking problems
   - **P1 (High)**: Major duplication, high complexity functions
   - **P2 (Medium)**: Minor duplication, moderate complexity
   - **P3 (Low)**: Dead code, style issues, small cleanup
3. **Group by file** -- Show all findings per file together
4. **If no issues found, say so and stop. Do not invent problems.**

## Step 4: Report

Present findings in this format:

```markdown
## Tech Debt Report

**Scope:** X files scanned
**Findings:** X total (P0: X, P1: X, P2: X, P3: X)

### P1: High Priority

**`src/utils/helpers.py:45-89`** -- Duplication
45-line block duplicated in `src/api/handlers.py:120-164`.
Fix: Extract to shared function in `src/utils/common.py`.

**`src/core/engine.py:process_data()`** -- Complexity
Cyclomatic complexity 18, 4 levels of nesting.
Fix: Extract inner loops into helper functions.

### P2: Medium Priority
...

### P3: Low Priority
...
```

## Step 5: Refactor

For each fix, follow this workflow:

1. **Ensure tests exist** for the code you're about to change. If not, write
   them first.
2. **Create a checkpoint**: `git commit` current state (or stash).
3. **Apply one refactoring at a time**. Never batch unrelated changes.
4. **Run tests after each change**. If tests fail, fix or revert before continuing.
5. **Commit with a descriptive message** that explains what was cleaned up.

### Deduplication Strategy

When fixing duplicated code:

- **Exact duplicates**: Extract to a shared function, replace all call sites.
- **Near duplicates** (same structure, different values): Extract with parameters
  for the varying parts.
- **Structural duplicates** (same pattern, different types): Consider generics
  or a template function.
- After extraction, verify all original call sites produce identical behavior.

## Step 6: Verify

After all refactoring is complete:

1. Run the full test suite. All tests must pass.
2. Run the project's linter. No new warnings.
3. If the project has a build step, verify it succeeds.
4. Review the git diff to confirm no unintended behavioral changes.

## Safety Rules

- Never refactor without tests covering the affected code
- Never make multiple unrelated changes in one commit
- Never refactor and add features simultaneously
- Never auto-fix security issues without manual review
- Always preserve external behavior (same inputs, same outputs)
- If scope grows beyond the initial estimate, stop and reassess
