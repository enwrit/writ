# Deep Work

Explore before implementing. Think before coding. Design before building.

This skill enforces a disciplined workflow: understand the problem fully, explore
alternatives, get agreement, then implement. It prevents the most common failure
mode in AI-assisted development -- jumping to code before understanding
requirements.

Inspired by obra/superpowers (brainstorming + systematic-debugging). Generalized
for any AI coding tool and any stack.

## When to Use

- Building new features or components
- Modifying behavior in non-trivial ways
- When requirements are ambiguous or underspecified
- When there are multiple valid approaches with real trade-offs
- When you're about to write code and realize you're not sure what "done" looks like

## Phase 1: Understand

Before writing any code, understand the context.

1. **Explore the project**: Read relevant files, recent commits, existing patterns.
   Don't assume -- read.
2. **Clarify the goal**: Can you state in one sentence what success looks like?
   If not, ask.
3. **Ask questions one at a time**: Don't overwhelm with a list. Ask the most
   important question, get the answer, then ask the next. Prefer multiple-choice
   questions when possible.
4. **Identify constraints**: What can't change? What's the performance budget?
   What existing patterns must be followed? What are the dependencies?

## Phase 2: Design

Once you understand what you're building:

1. **Propose 2-3 approaches** with trade-offs. Lead with your recommendation
   and explain why.
2. **Present the design** in sections scaled to complexity: a few sentences for
   straightforward parts, more detail for nuanced areas.
3. **Get agreement** before proceeding. Ask after each section whether it looks
   right so far.

Design principles:
- Break the system into units with one clear purpose each
- For each unit, answer: what does it do, how do you use it, what does it depend on?
- Can someone understand a unit without reading its internals? Can you change
  internals without breaking consumers? If not, the boundaries need work.
- Prefer smaller, focused files -- you reason better about code you can hold in
  context at once.

### In Existing Codebases

- Explore the current structure before proposing changes. Follow established patterns.
- Where existing code has problems that affect the work, include targeted
  improvements as part of the design -- the way a good developer improves code
  they're working in.
- Don't propose unrelated refactoring. Stay focused on what serves the current goal.

## Phase 3: Plan

After design approval, create a concrete implementation plan (see the
plan-skill for the full planning methodology):

- Map out files to create/modify
- Break into bite-sized tasks (2-5 minutes each)
- Include exact file paths, code, test commands
- No placeholders, no vague instructions

## Phase 4: Implement

Execute the plan task by task:

- Follow steps exactly as written
- Run verifications as specified
- Stop on blockers -- don't guess
- Commit after each logical unit of work

## Phase 5: Verify

Before claiming completion (see the verify-skill for the full methodology):

- Run the test suite
- Run the linter
- Run the build
- Review your own diff
- Check requirements against the original spec, line by line

## When You're Stuck

If implementation hits a wall, switch to systematic debugging:

1. **Don't guess**. Random fixes waste time and create new bugs.
2. **Read error messages carefully**. They often contain the solution.
3. **Reproduce the issue consistently** before attempting any fix.
4. **Check what changed**: `git diff`, recent commits, new dependencies.
5. **Form a single hypothesis**: "I think X is the root cause because Y."
6. **Test minimally**: Make the smallest possible change to test the hypothesis.
   One variable at a time.
7. **If 3+ fixes fail**: Stop fixing. Question the architecture. The problem may
   be structural, not a bug.

## Anti-Patterns

These are failure modes. If you catch yourself doing any of these, stop and
return to the appropriate phase:

- **Jumping to code**: Writing implementation before understanding requirements.
  Return to Phase 1.
- **Gold-plating**: Adding features the spec doesn't require. YAGNI.
- **Scope creep**: "While I'm here, let me also..." -- stick to the plan.
- **Guessing through blockers**: If you don't understand something, ask. Don't
  generate speculative code.
- **Skipping verification**: "Should work" is not evidence. Run the command.
- **Analysis paralysis**: If you've been designing for 30+ minutes without
  code, the scope is too big. Break it down.

## Key Principles

- **One question at a time** -- Don't overwhelm with multiple questions
- **Explore alternatives** -- Always propose 2-3 approaches before settling
- **Evidence before claims** -- Run verification commands before claiming success
- **YAGNI** -- Remove unnecessary features ruthlessly
- **Small steps** -- Break everything into bite-sized, verifiable chunks
- **Stop when blocked** -- Ask for help rather than guessing
