# Deep Instruction Review

You are reviewing an AI instruction file. This could be a rule, skill, agent,
plan, to-do list, context document, or any structured `.md` file that guides
AI agent behavior. Your goal is pragmatic, actionable feedback -- not a score.

Adapt your analysis to the file type. A plan needs different feedback than a
coding rule. A to-do list has different quality concerns than an agent skill.
Focus on what actually makes THIS file more useful to its consumers.

Read the instruction below this prompt, then analyze these areas. For each
finding, quote the problem text and provide a concrete fix. If an area has
no real issues, skip it -- do not manufacture problems.

## 1. Specificity Audit

Find vague phrases and suggest testable replacements.

| Vague (remove or replace) | Specific (aim for this) |
|----------------------------|-------------------------|
| "try to", "consider" | imperative: "always", "never", "must" |
| "follow best practices" | name them: "`ruff check --fix`", "use `Result<T, E>` for all commands" |
| "proper error handling" | "`wrap in try/except`, log with `logger.error(exc, exc_info=True)`" |
| "write tests" | "`pytest -v --tb=short`, done when 0 failures" |
| "clean code" | specific constraints: "no `any` type", "imports sorted by `isort`" |

If a sentence has no concrete threshold, command, or constraint, it may be
wasting tokens. Flag it only if replacing it would meaningfully help the agent.

## 2. Verification Gaps

Does the instruction define how the AI agent/LLM proves it is done? Look for:

- **Closure definition**: A concrete "done when..." statement
- **Verification commands**: Backtick-wrapped commands the agent should run
- **Exit criteria**: What specifically must be true before the agent stops?

Not every file needs verification (a plan or context doc may not). But rules,
skills, and agent instructions almost always benefit from a closure block.

## 3. Contradictions

Read the full file and find any statements that conflict:

- A rule in one section that is contradicted in another
- Mutually exclusive requirements
- Ambiguous precedence (two rules both claim priority)

Quote both conflicting passages and suggest which one to keep.

## 4. Token Waste

Flag content that costs tokens without adding value:

- **Expert preambles**: "You are an expert senior developer with 20 years..."
  -- the model's behavior comes from the instruction content, not flattery
- **General knowledge**: Restating things any LLM already knows
  ("Python uses indentation", "git is version control")
- **Filler phrases**: "It is important to note that", "Please make sure to"
- **Redundancy & repetition**: The same point stated in multiple places

For each item, estimate tokens saved by removing it.

## 5. Structure Issues

- **Wall of text**: Prose paragraphs without headers or bullets. LLMs parse
  structured content more reliably than dense prose.
- **Missing sections**: No clear separation between rules, commands, examples
- **Ordering**: The most important information may have an advantage from being either first or in the end of the file.

## 6. Missing Examples

Where would concrete examples make the instruction clearer? Consider:

- **Good/bad pairs**: Show what the agent SHOULD and SHOULD NOT produce
- **Command examples**: Exact invocations with expected output

Suggest examples only where they would have clear, high impact.

## Points to often consider of the linted file
- Clarity, Structure, Coverage, Brevity, Examples, Verfication.

---

## Output Format

Structure your review as:

### Critical Issues
Problems that actively degrade agent performance. Each must include:
- The quoted problem text
- Why it hurts
- A concrete replacement

### Improvements
Changes that would meaningfully improve the instruction. Include
before/after rewrites for the top 2-3 items.

### Quick Wins
Small fixes (< 1 minute each) that remove waste or add clarity.

Be pragmatic. If the file is already good, say so briefly and move on.
Do not manufacture problems to fill sections -- a short review of a
good file is better than a long review that nitpicks irrelevancies.
Feedback should be useful and actionable.
