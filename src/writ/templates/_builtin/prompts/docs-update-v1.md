# Documentation Update Pass

You are performing a documentation health update for this project. Below this
instruction you will find the results of a heuristic health check -- concrete
findings about dead references, treeview drift, staleness, and contradictions.
Your job is to act on those findings and update the documentation.

## Scope: What to Focus On

Do NOT blindly read every file in the documentation index. Prioritize:

1. **Recently changed files** -- run `git status --short` and
   `git log --oneline -15 --name-only` to see what changed. Documentation
   describing changed code is most likely to be stale.
2. **Core files from the index** -- the `## Core files` section in the docs
   index lists frequently maintained files. These are high-priority.
3. **Files flagged by the health check** -- the heuristic findings below
   identify specific issues. Address those directly.
4. **Cold files** -- only touch archived or rarely-updated files if the health
   check specifically flags them (e.g., a dead reference pointing to a cold
   file).

## Step 1: Review Health Check Findings

Read through the health check results provided below this instruction. For each
issue:

- **Dead references**: Verify the reference is truly dead (not a false
  positive), then update or remove it.
- **Treeview drift**: Compare the documented treeview against the actual file
  tree. Add missing files, remove deleted ones, fix renamed entries.
- **Staleness**: Read the stale file and the code it describes. Update any
  claims that no longer hold (counts, paths, descriptions, examples).
- **Contradictions**: Read both conflicting files. Determine which is correct
  (usually the more recently updated one). Fix the incorrect file.

## Step 2: Cross-Reference with Recent Changes

After addressing the flagged issues, check whether recent code changes
(from `git log`) introduced new files, commands, or patterns that should be
documented but aren't yet covered. Look for:

- New source files with no corresponding documentation entry
- Changed CLI commands, flags, or configuration formats
- Renamed or reorganized modules
- New architectural patterns or conventions

## Step 3: Surgical Updates

Fix documentation with minimal edits:

- Update file paths to match current structure
- Add new entries to treeviews, remove deleted ones
- Fix renamed commands, flags, or concepts
- Resolve contradictions
- Update stale counts, versions, or statistics
- Preserve the original author's style and structure
- Match annotation conventions used in treeviews and the docs index

Do NOT rewrite files. Do NOT restructure documentation. Fix what is wrong and
move on.

## Step 4: Update the Documentation Index

After fixing documentation files, update the `writ-docs-index`:

- **Add** newly discovered documentation files with appropriate annotations
- **Remove** entries for deleted files
- **Update annotations** for files whose purpose or scope changed
- **Update Core files** if commit frequencies shifted significantly

The index must stay in sync with reality.

## Step 5: Log the Summary

As the final step, append a compact entry to the `writ-log` file (visible in
your IDE's rules/context directory). This is critical -- it turns your ephemeral
session context into persistent project knowledge.

Format:

```
- [YYYY-MM-DD HH:MM UTC] docs update -- [what was done]. [key decisions].
  [important findings]. [anything deferred].
```

Example:

```
- [2026-04-11 14:30 UTC] docs update -- Fixed 3 dead refs in project-treeview,
  added query.py and status.py entries. Resolved contradiction between README
  and AGENTS.md on command count (kept README, updated AGENTS). Deferred:
  architecture.md needs full rewrite after v2 migration (flagged for human).
```

Keep it to 3-5 lines. Include what changed, why key decisions were made, and
anything you chose to defer rather than fix now.

---

## Health Check Results

The following findings were produced by `writ docs check` (heuristic analysis).
Use them as your starting point:

