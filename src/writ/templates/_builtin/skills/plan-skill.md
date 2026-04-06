# Writing Implementation Plans

Write comprehensive implementation plans before touching code. The plan assumes
the implementer has zero context for the codebase and limited domain knowledge.
Document everything they need: which files to touch, exact code, how to test,
how to verify. Give the whole plan as bite-sized tasks.

Inspired by obra/superpowers (writing-plans). Generalized for any stack.

## When to Plan

- Multi-file changes (3+ files affected)
- New features or significant refactors
- Anything estimated at >30 minutes of work
- When requirements are ambiguous or have trade-offs

Skip planning for: single-file bug fixes, typo corrections, dependency bumps, or
changes where the implementation path is obvious.

## Before Writing the Plan

1. **Understand the goal**: One sentence -- what does success look like?
2. **Explore the codebase**: Read relevant files, recent commits, existing patterns.
3. **Propose 2-3 approaches** with trade-offs and your recommendation. Lead with the
   recommended option. Get agreement before writing the plan.

## Scope Check

If the task covers multiple independent subsystems, break it into separate plans.
Each plan should produce working, testable software on its own.

## File Structure

Before defining tasks, map out which files will be created or modified and what
each one is responsible for.

- Design units with clear boundaries and well-defined interfaces. Each file should
  have one clear responsibility.
- Prefer smaller, focused files over large ones that do too much.
- Files that change together should live together. Split by responsibility, not
  by technical layer.
- In existing codebases, follow established patterns. Don't unilaterally
  restructure -- but if a file has grown unwieldy, a split in the plan is fine.

## Task Granularity

Each step is one action (2-5 minutes):

- "Write the failing test" -- step
- "Run it to make sure it fails" -- step
- "Implement the minimal code to make the test pass" -- step
- "Run the tests and make sure they pass" -- step
- "Commit" -- step

## Where to Store Plans

Save plans to the project's planning directory. Use today's date and a short
feature name:

```
plans/YY-MM-DD_feature-name.md
```

The `plans/` directory lives wherever the project keeps agent/tool configuration:

| Tool | Location |
|------|----------|
| Cursor | `.cursor/plans/` |
| Claude Code | `.claude/plans/` or `docs/plans/` |
| Kiro | `.kiro/plans/` |
| Generic | `docs/plans/` or `plans/` at repo root |

If the project already has a plans directory, use it. If not, create one in the
most appropriate location. The plan file should be committed to version control
so the implementer (human or agent) can reference it.

## Plan Document Format

Every plan starts with:

```markdown
# [Feature Name] Implementation Plan

**Goal:** [One sentence]
**Approach:** [2-3 sentences about architecture]
**Tech stack:** [Key technologies/libraries]
**Date:** [YYYY-MM-DD]
**Status:** not started | in progress | completed

---
```

## Task Structure

````markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.ext`
- Modify: `exact/path/to/existing.ext`
- Test: `tests/exact/path/to/test_file.ext`

- [ ] **Step 1: Write the failing test**

```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/path/test_file.py::test_name -v`
Expected: FAIL with "function not defined"

- [ ] **Step 3: Write minimal implementation**

```python
def function(input):
    return expected
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/path/test_file.py::test_name -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/path/test_file.py src/path/file.py
git commit -m "feat: add specific feature"
```
````

## No Placeholders

Every step must contain the actual content an engineer needs. These are plan
failures -- never write them:

- "TBD", "TODO", "implement later", "fill in details"
- "Add appropriate error handling" (show the actual error handling)
- "Write tests for the above" (without actual test code)
- "Similar to Task N" (repeat the code -- the implementer may read tasks out of order)
- Steps that describe what to do without showing how
- References to types, functions, or methods not defined in any task

## Risks and Rollback

After the tasks, include:

- **Risks**: What could go wrong? Migration issues, backward compatibility,
  performance, security. For each risk, note your mitigation.
- **Rollback**: If this goes wrong in production, how do you undo it?

## Self-Review

After writing the complete plan, review it with fresh eyes:

1. **Spec coverage**: Skim each requirement. Can you point to a task that
   implements it? List any gaps.
2. **Placeholder scan**: Search for "TBD", "TODO", vague instructions. Fix them.
3. **Consistency**: Do types, method signatures, and property names match across
   tasks? A function called `clear_layers()` in Task 3 but `clear_all_layers()`
   in Task 7 is a bug.
4. **Testability**: Does every behavioral change have a corresponding test?

If you find issues, fix them inline. If you find a requirement with no task, add
the task.

## Key Principles

- **DRY** -- Don't repeat yourself across the codebase
- **YAGNI** -- Don't add features the spec doesn't require
- **TDD** -- Write tests before implementation when possible
- **Frequent commits** -- One commit per logical unit of work
- **Exact file paths** -- Always specify the full path
- **Complete code** -- If a step changes code, show the code
- **Exact commands** -- Show the command to run with expected output
