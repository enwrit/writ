# Documentation Health (Schema-Driven)

Maintain project documentation using the documentation index (`writ-docs-index`)
as the source of truth for what exists and where it lives. This skill differs
from general documentation maintenance: it reads the index first, so it knows
exactly which files to check rather than scanning ad-hoc.

## When to Run

- Before committing after structural changes (new files, renames, deletions)
- After adding or removing instructions via `writ add` / `writ remove`
- Periodically as a health pass (weekly or per-sprint)
- When `writ docs check` reports issues

## Prerequisites

The project must have a `writ-docs-index` file. If it does not exist, run
`writ docs init` to create one, then return here.

## Step 1: Read the Index

Read the `writ-docs-index` file. This is your map -- it lists every
documentation file in the project with an annotation describing its purpose.
Parse the treeview to build the list of files you need to check.

If the index is available in your IDE rules (it should be -- it is installed
with `alwaysApply`), you may already have it in context.

## Step 2: Identify What Changed

Run git commands to see what changed since the last documentation pass:

```bash
git status --short
git log --oneline -15 --name-only
git log --diff-filter=D --name-only --since="2 weeks ago"
```

Build a list of changed, added, deleted, and renamed paths. Cross-reference
this list against the index -- which indexed files were touched? Which
non-indexed files were added that might need indexing?

## Step 3: Check Indexed Files

For each file in the index that was touched (or references something that was
touched):

1. **Verify it exists** -- if deleted, remove it from the index
2. **Check accuracy** -- do file references, command examples, and architecture
   descriptions still match reality?
3. **Check cross-references** -- does this file reference other indexed files
   that have changed? Follow the chain.
4. **Check freshness** -- if the file describes code that changed significantly,
   the documentation is likely stale even if the file itself wasn't modified

## Step 4: Deep Checks

Look for problems that span multiple files:

- **Contradictions**: Two files giving conflicting guidance on the same topic
- **Orphan references**: Files referencing paths or concepts that no longer exist
- **Missing concepts**: New modules, commands, or patterns that exist in code
  but have no documentation entry in the index
- **Stale claims**: Version numbers, counts ("541+ tests"), or statistics that
  may have drifted

## Step 5: Surgical Updates

Fix what you find. Rules:

- Make **minimal edits** -- fix inaccuracies, don't rewrite
- Preserve the original author's style and structure
- Match the annotation style used in the index and treeviews
- Update file paths to match current structure
- Add new entries, remove deleted ones
- Resolve contradictions by keeping the more recent/correct version
- If a fix requires more than 5 minutes of work and is unrelated to the current
  task, note it for later rather than doing it now

## Step 6: Update the Index

After fixing documentation files, update the `writ-docs-index` itself:

- **Add** new documentation files discovered in Step 2
- **Remove** entries for deleted files
- **Update annotations** for files whose purpose or scope changed
- **Update the Core files section** if commit frequency has shifted
  significantly (run `git log --format=%H -- <file> | wc -l` for doc files
  if unsure)

The index must stay in sync with reality -- it is the schema that other tools
and agents rely on.

## Step 7: Log the Summary

As the final step, append a compact entry to the `writ-log` file (visible in
your IDE's rules/context directory):

```
- [YYYY-MM-DD HH:MM UTC] docs health pass -- Updated X, Y, Z. Found
  contradiction between A and B (resolved: kept A). Added new-file.md to index.
  Deferred: stale architecture claims in docs/design.md (needs human review).
```

Keep it concise (3-5 lines). Include: what was updated, key decisions made,
important findings, anything deferred. This log turns your session's ephemeral
context into persistent project knowledge that future agents can read.

## Fallback

If `writ docs check` is available, run it first to get a heuristic report of
issues (dead references, treeview drift, staleness scores). Use those findings
as your starting point rather than scanning from scratch.

If no `writ-docs-index` exists, suggest running `writ docs init` to create one.
You can still do ad-hoc documentation maintenance, but the schema-driven
approach is more thorough and reproducible.
