# Enrich the Documentation Index

A `writ-docs-index` file was just created for this project. It contains an
auto-generated treeview of documentation files found in IDE configuration
folders and well-known root files. **This treeview is rough** -- it was built
programmatically and may need considerable updates from you:

- Annotations (`#` descriptions) are empty and need to be filled in
- Files in unusual locations (e.g. `docs/`, custom directories) may be missing
- The treeview may include files that aren't meaningful documentation

Your task is to **enrich and correct** the index.

## Step 1: Fill in Annotations

Open the `writ-docs-index` file. Each file entry has an empty `#` placeholder.
For each entry:

1. **Read the file** (or at least its first ~20 lines) to understand its purpose
2. **Write a 5-10 word annotation** after the `#` describing what the file is

Example -- before:

```
.cursor/
  rules/
    project-rule.mdc  #
    project-treeview.mdc  #
README.md  #
```

After:

```
.cursor/
  rules/
    project-rule.mdc          # Project identity, conventions, architecture
    project-treeview.mdc       # Annotated repository structure
README.md                      # Project overview, install, quickstart
```

## Step 2: Add Missing Files, Remove Irrelevant Ones

The auto-scan covers IDE configuration folders (`.cursor/`, `.claude/`, `.kiro/`,
etc.) and root files (`README.md`, `AGENTS.md`). It may miss:

- Documentation directories: `docs/`, `doc/`, `documentation/`
- Plans, to-do lists, research notes, architecture decision records
- Any `.md` or `.mdc` file outside IDE folders whose purpose is documentation

Add missing files in their correct hierarchical position with an annotation.
Remove any entries that aren't meaningful documentation (e.g. auto-generated
stubs with no real content).

## Step 3: Add Core Files Section

After the treeview code block, add a `## Core files` section listing the most
frequently committed documentation files. Compute from git history:

```bash
git log --oneline -- <file> | wc -l
```

Run this for each file in the index. List the top 5-10 files sorted by commit
count:

```
## Core files

Files most frequently updated (by git commit count). Prioritize these during
documentation passes.

- `path/to/file.md` (N commits)
- `another/file.mdc` (M commits)
```

This gives future agents a persistent signal about which files are actively
maintained ("hot") versus archived or rarely updated ("cold").

## Step 4: Log

Append a brief entry to the `writ-log` file (visible in your IDE's
rules/context directory):

```
- [YYYY-MM-DD HH:MM UTC] docs init -- Enriched documentation index: N files
  annotated. Core files: [top 3].
```
