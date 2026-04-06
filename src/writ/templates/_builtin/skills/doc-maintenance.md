# Documentation Maintenance

After structural changes to a codebase, check whether documentation still
reflects reality. Stale documentation actively misleads AI agents and teammates.
This skill provides a systematic, git-aware approach to finding and fixing drift.

## When to Run

After any change that:
- Adds, removes, or renames files or directories
- Changes public APIs, CLI commands, or configuration formats
- Modifies architecture (new modules, changed data flow)
- Updates dependencies in a way that affects usage

Also run periodically (weekly or per-sprint) as a health check.

## Step 1: Identify What Changed

Start from version control. These commands reveal what documentation might be stale.

```bash
# Files changed since last release/tag
git diff --name-only <last-tag>..HEAD

# Files changed in the last N commits
git log --oneline -20 --name-only

# Recently deleted files (docs may still reference them)
git log --diff-filter=D --name-only --since="2 weeks ago"

# Recently renamed files
git log --diff-filter=R --name-only --since="2 weeks ago"

# Current untracked or modified files
git status --short
```

Build a list of changed, deleted, and renamed paths. These are your search targets.

## Step 2: Identify Documentation Files

Scan the repository for all documentation that might reference code paths:

- **Instruction files**: `.cursor/rules/*.mdc`, `.claude/rules/*.md`,
  `.kiro/steering/*.md`
- **Project rules**: `AGENTS.md`, `CLAUDE.md`, `.windsurfrules`, `.cursorrules`
- **READMEs**: `README.md`, any `*/README.md`
- **Treeview files**: Annotated directory structures (often in rules or docs)
- **Architecture docs**: `docs/`, ADRs, design documents
- **Config references**: Comments in `pyproject.toml`, `package.json`, etc. that
  describe structure

## Step 3: Check for Staleness

For each documentation file, check these categories:

### File References

Search for backtick-fenced paths (`` `src/foo/bar.py` ``) and verify they match
the current file tree. Cross-reference against the deleted/renamed files from
Step 1.

```bash
# Find all backtick-quoted paths in a doc file and check if they exist
# (conceptual -- adapt to your tooling)
grep -oP '`[^`]*\.(py|ts|js|rs|go|yaml|toml|json|md)`' AGENTS.md
```

### Treeview Accuracy

If the project has annotated directory trees, compare them against the actual
structure:

```bash
# List actual directory structure
find src/ -type f | sort

# Compare against what the treeview claims exists
```

Common drift: new files missing from the tree, deleted files still listed,
renamed files showing the old name.

### Command Accuracy

If docs reference CLI commands, flags, or examples:
- Do the documented commands still work?
- Have flags been renamed or removed?
- Have default values changed?

### Terminology Consistency

If a concept was renamed (e.g., "agent" to "instruction", "use" to "add"),
search all docs for the old term and update.

### Contradictions

If two docs give conflicting guidance, resolve the conflict. Don't leave it for
the next reader.

## Step 4: Fix

Make **surgical, minimal edits**. The goal is accuracy, not rewriting.

- Update file paths to match current structure
- Add new files to treeviews, remove deleted ones
- Fix renamed commands, flags, or concepts
- Resolve contradictions by keeping the more recent/correct version
- Remove references to deleted functionality

### Rules for Fixes

- Update docs in the same commit as the code change when possible
- If fixing stale docs unrelated to the current change: fix if quick (<5 min),
  otherwise note for a separate cleanup
- Don't restructure or rewrite docs unless explicitly asked -- just fix
  inaccuracies
- Preserve the original author's style and structure
- When adding new entries to a treeview, match the existing annotation style

## Step 5: Verify

After making fixes:

```bash
# Confirm no broken references remain
# Search for paths that don't exist on disk
grep -rn '`[^`]*\.(py|ts|js|rs|go)`' .cursor/rules/ AGENTS.md README.md | \
  while read line; do
    path=$(echo "$line" | grep -oP '`\K[^`]+')
    [ ! -e "$path" ] && echo "STALE: $line"
  done
```

Review the diff before committing. Documentation fixes should be obviously
correct.

## Automation

If the project uses writ, run `writ docs check` to detect stale references and
treeview drift automatically. This covers Steps 1-3 and surfaces findings for
manual review.
