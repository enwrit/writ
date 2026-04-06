# Pre-Commit Verification

Before committing code, run through a verification checklist. Catching problems
before they enter version control prevents broken builds, failed CI, and wasted
review cycles.

Inspired by obra/superpowers (verification-before-completion, finishing-a-
development-branch) and community pre-commit best practices.

## Before Every Commit

Run these checks in order. Stop at the first failure and fix before continuing.

### 1. Build / Compile

Does the code compile or pass syntax checks?

```bash
# Python
python -m py_compile src/module.py

# TypeScript
npx tsc --noEmit

# Rust
cargo check

# Go
go build ./...
```

If it doesn't compile, nothing else matters. Fix first.

### 2. Tests

Run the test suite for the modules you changed. Full suite if it completes in
under 2 minutes.

```bash
# Python
python -m pytest tests/ -v --tb=short

# JavaScript/TypeScript
npm test

# Rust
cargo test

# Go
go test ./...
```

Read the output. Count failures. Don't trust "it should pass" -- verify.

### 3. Lint

Run the project's linter. Fix all new warnings introduced by your changes.

```bash
# Python
ruff check src/ tests/

# JavaScript/TypeScript
npx eslint src/

# Rust
cargo clippy -- -D warnings

# Go
golangci-lint run
```

Don't commit code with linter errors. If the existing codebase has pre-existing
warnings, at minimum don't add new ones.

### 4. Type Check

If the project uses static type checking, run it.

```bash
# Python
mypy src/ --ignore-missing-imports

# TypeScript
npx tsc --noEmit

# (Rust and Go handle this at compile time)
```

Type errors caught now are bugs prevented later.

### 5. Smoke Test

For the specific feature you changed:
- **UI changes**: Visually verify the change renders correctly
- **CLI changes**: Run the affected command with typical inputs
- **API changes**: Hit the endpoint and verify the response
- **Library changes**: Run a quick integration check

Automated tests don't catch everything. One manual verification is worth it.

## Before Every PR / Merge

In addition to the above:

### 6. Review Your Own Diff

```bash
git diff --staged
```

Read it as if reviewing someone else's code. Common catches:
- Debug prints / console.log statements
- TODO comments that should be resolved
- Unused imports added during development
- Accidentally staged test files or config changes
- Hardcoded values that should be configurable

### 7. Check for Secrets

Scan for hardcoded API keys, passwords, tokens, or credentials.

```bash
# Quick pattern scan
git diff --staged | grep -iE '(api[_-]?key|password|secret|token|credential).*=.*["\x27]'
```

Never commit `.env` files with real values. Check `.gitignore` covers sensitive
files.

### 8. Update Documentation

If your change affects documented behavior:
- Update README if user-facing behavior changed
- Update API docs if endpoints changed
- Update instruction files if CLI commands changed
- Update treeview annotations if files were added/removed/renamed

Do this in the same commit. A separate "update docs" task will be forgotten.

### 9. Verify Commit Message

Write a message that explains **why**, not just **what**:
- Bad: "Update auth.py"
- Good: "Fix session expiry check that allowed stale tokens past 24h"

## Recovery

If you committed something broken:

- **Not pushed**: `git commit --amend` (for small fixes) or `git reset HEAD~1`
  (to redo entirely)
- **Already pushed**: Fix forward with a new commit. Don't force-push shared
  branches unless you know what you're doing.

## Quick Reference

| Check | Command (adapt to your stack) | Must pass? |
|-------|-------------------------------|------------|
| Build | `cargo check` / `tsc --noEmit` / `python -m py_compile` | Yes |
| Tests | `pytest` / `npm test` / `cargo test` | Yes |
| Lint | `ruff check` / `eslint` / `clippy` | Yes |
| Types | `mypy` / `tsc` / (built-in) | Yes |
| Smoke test | Manual verification | Yes |
| Self-review | `git diff --staged` | Before PR |
| Secrets | Pattern grep on staged diff | Before PR |
| Docs | Manual check | Before PR |
