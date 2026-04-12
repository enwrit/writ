## Type Context: Plan

This file appears to be an **implementation plan** (detected from its folder location).
Plans propose a sequence of changes to achieve a goal.

Adapt your review with these plan-specific priorities:

- **Step ordering**: Are steps sequenced correctly? Flag dependencies that
  would fail if executed in the stated order.
- **Dependency identification**: Does the plan call out what must exist
  before each step begins (files, APIs, permissions, data)?
- **Scope realism**: Is the plan trying to do too much in one pass?
  Plans that touch 10+ files without intermediate checkpoints tend to fail.
- **Risk awareness**: What happens if a step fails? Is there a rollback
  path or at least a "known risk" callout?
- **Measurable completion**: How will someone know the plan succeeded?
  Plans without success criteria lead to scope creep.
- **File/module accuracy**: Do referenced file paths, function names, and
  APIs actually exist? Plans that reference non-existent code waste effort.
