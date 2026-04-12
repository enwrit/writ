## Type Context: Rule

This file appears to be a **rule** (detected from its folder location).
Rules constrain agent behavior -- they define what agents must or must not do.

Adapt your review with these rule-specific priorities:

- **Testability**: Can each rule be mechanically verified? "Write clean code"
  is untestable. "Run `ruff check` with zero errors" is testable.
- **Contradiction check**: Do any rules conflict with each other? Look for
  pairs where following one rule forces violating another.
- **Exception handling**: Are edge cases addressed? Rules that say "always"
  or "never" without exceptions will break in legitimate scenarios.
- **Priority/precedence**: If rules conflict, which wins? Without explicit
  ordering, agents make arbitrary choices.
- **Scope clarity**: Does each rule state when it applies? A rule that
  applies to "all files" when it should only apply to tests wastes tokens
  and causes false constraints.
