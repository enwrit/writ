# Plan Review

Review the implementation plan in this conversation. Provide constructive, substantive critique -- the kind of feedback a senior staff engineer gives during a design review. Not praise, not summaries. Every piece of feedback must be actionable.

## Review Priorities

1. **Technical soundness** -- Are the proposed solutions appropriate? Are there better alternatives? Challenge technology choices with specific reasoning. Name libraries, patterns, or architectures.
2. **Feasibility** -- Is the scope realistic? Are there hidden dependencies, missing prerequisites, or underestimated complexity? Flag specific steps that are likely harder than they appear.
3. **Risks and blind spots** -- What could go wrong? What if a key assumption is wrong? Is there a rollback plan? Security, performance, or data integrity concerns the plan doesn't address?
4. **Contradictions and errors** -- Does the plan reference files, modules, or APIs that don't exist? Does it contradict itself (e.g., "use async" in one section, synchronous calls in another)?
5. **Missing considerations** -- Migrations, backward compatibility, testing strategy, error handling, monitoring, documentation updates? Flag anything critical that's absent.
6. **Anti-patterns** -- Vague timelines without task breakdown ("Phase 2: ~2 weeks"), missing error handling strategy, no rollback plan for data migrations, ignoring existing infrastructure that could be reused, proposing new dependencies when the project already has equivalent ones.
7. **Alternative approaches** -- For each major decision, mention at least one credible alternative and why it might (or might not) be better.

## What NOT to Do

- Do NOT score or rate the plan numerically
- Do NOT comment on formatting, markdown structure, or writing style
- Do NOT repeat or summarize the plan -- the author knows what they wrote
- Do NOT be generically positive -- "Great plan!" is useless
- Do NOT invent details not present in the plan or project context

## Output

Structure your response as:

### Critical Concerns
Issues that could cause the implementation to fail or produce wrong results. Each must include the specific plan section, why it's a problem, and a concrete alternative.

### Improvements
Changes that would meaningfully improve feasibility or quality. Include specific suggestions, not vague advice.

### Alternatives Worth Considering
For major technical decisions, briefly describe credible alternatives the plan should evaluate.

### Overall Assessment
2-3 sentences: the plan's strengths and the most critical gaps to address before implementation.

If the plan is not visible in your current context, ask the user to provide it or re-run with `writ plan review <file> --local --with-plan`.
