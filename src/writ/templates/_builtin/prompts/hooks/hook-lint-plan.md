## Type Context: Plan

This file appears to be an **implementation plan** (detected from its folder location). Plans propose a sequence of changes to achieve a goal. A good plan is the difference between a successful multi-file change and a mess of half-finished edits.

Prioritize these plan-specific concerns:

- **Step ordering and dependencies**: Are steps sequenced correctly? If step 3 uses output from step 5, that's a dependency bug. Look for implicit assumptions like "after the module is created" without that creation being an earlier step.
- **File path accuracy**: Do referenced files, functions, and APIs exist? Plans that reference wrong paths waste the implementer's entire first pass. Cross-check any `src/...` or `tests/...` paths mentioned.
- **Success criteria**: How will someone know the plan succeeded? Look for test bullets, acceptance criteria, or measurable checks. A plan without "done when..." is a plan with scope creep.
- **Risk and fallback**: What happens if a step fails? Plans that touch external tools (git, APIs, subprocess) without mentioning error handling or degradation paths are fragile.
- **Scope realism**: Is the plan trying to change 10+ files in one pass without intermediate checkpoints? Large plans without phases or milestones tend to fail. Suggest adding phases into the plan if needed.
- **Traceability**: Do the overview, todo list, and file inventory agree? Deliverables mentioned in the overview but absent from the file list (or vice versa) signal drift. Also, does the plan include a date, and a status (completed/ongoing, etc). This is often good to have for traceability as a project grows over time.
