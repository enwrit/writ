## Type Context: Rule

This file appears to be a **rule** (detected from its folder location). Rules constrain AI LLM behavior and are typically always-on. cursor-doctor found 75% of popular community rules mix multiple concerns in one file, and 60% of projects scored C or lower on rule quality.

Prioritize these rule-specific concerns:

- **Verifiability**: Can the rule's objective be checked with a command or observable condition? "Write clean code" is unverifiable. "Run `ruff check` with zero errors before committing" is. Rules without verification produce no observable change in agent behavior (Blake Crosley).
- **Single concern**: Does this rule try to cover too many topics? Rules mixing coding style, git workflow, and testing in one file are harder for agents to follow. If there are 3+ unrelated sections, suggest splitting for modularity.
- **Constraint count**: AGENTIF data shows compliance drops sharply past ~20 constraints. If this rule has many directives, flag the risk and suggest prioritizing the critical ones.
- **Exception handling**: Rules that say "always" or "never" without exceptions break in legitimate edge cases. Check for rigid absolutes that need escape hatches.
