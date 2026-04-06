# Code Simplifier

Simplify and refine code for clarity, consistency, and maintainability while
preserving all functionality. Focus on recently modified code unless instructed
to review a broader scope.

Inspired by Claude Code's code-simplifier plugin. Generalized for any language
and any AI coding tool.

## What This Skill Does

Analyze recently modified code and apply refinements that:

1. **Preserve functionality**: Never change what the code does -- only how it
   does it. All original features, outputs, and behaviors must remain intact.

2. **Enhance clarity**: Simplify code structure by:
   - Reducing unnecessary complexity and nesting
   - Eliminating redundant code and abstractions
   - Improving readability through clear variable and function names
   - Consolidating related logic
   - Removing comments that describe obvious code
   - Replacing nested ternary operators with switch/if-else chains
   - Choosing clarity over brevity -- explicit code beats clever one-liners

3. **Follow project standards**: Read the project's existing conventions
   (style guides, linter config, existing patterns) and match them. Don't
   impose external standards -- adopt what's already established.

4. **Maintain balance**: Avoid over-simplification that could:
   - Reduce clarity or maintainability
   - Create overly clever solutions that are hard to understand
   - Combine too many concerns into single functions
   - Remove helpful abstractions that improve organization
   - Prioritize "fewer lines" over readability
   - Make the code harder to debug or extend

## Process

1. **Identify scope**: Find recently modified code sections (check `git diff`
   or the current session's changes).
2. **Analyze for opportunities**: Look for complexity, redundancy, inconsistency,
   unclear naming, over-engineering.
3. **Apply project conventions**: Match the codebase's established patterns for
   imports, naming, error handling, typing, and structure.
4. **Verify functionality is unchanged**: If tests exist, run them! If not,
   reason carefully about behavioral preservation.
5. **Document only significant changes**: Don't add comments explaining what
   you simplified -- the cleaner code speaks for itself.

## What to Simplify

| Pattern | Before | After |
|---------|--------|-------|
| Deep nesting | 4+ levels of if/else/try | Early returns, guard clauses |
| Redundant variables | `x = get(); return x` | `return get()` |
| Dead branches | `if DEBUG: ...` (never true) | Remove |
| Over-abstraction | Single-use wrapper function | Inline the logic |
| Magic values | `if status == 3:` | `if status == STATUS_COMPLETE:` |
| Verbose conditionals | `if x == True:` | `if x:` |
| Unused imports | `import os` (never used) | Remove |

## What NOT to Simplify

- **Public API signatures**: Changing function signatures breaks callers.
- **Intentional verbosity**: Sometimes explicit code is clearer than compact code,
  especially for complex business logic.
- **Performance-critical code**: Readability refactors that change algorithmic
  behavior (e.g., converting a loop to a different data structure).
- **Code outside your scope**: Don't go on a refactoring adventure. Stick to
  recently modified files unless explicitly asked otherwise.

## Operating Mode

This skill operates proactively. After code is written or modified, apply
refinements without requiring an explicit request. The goal is to ensure all
code meets high standards of clarity and maintainability while preserving
complete functionality.
