# AGENTS.md

> Managed by [writ](https://github.com/enwrit/writ) -- dogfooding our own tool.

## Project Overview

**enwrit** (`writ`) is the communication layer for AI agents. It routes context between repos, devices, and tools -- composing, syncing, and exporting agent instructions everywhere.

## Development Conventions

- **Language**: Python 3.11+, type hints everywhere
- **CLI**: Typer + Rich for beautiful terminal output
- **Data**: Pydantic models, YAML config files
- **Testing**: pytest with comprehensive test coverage
- **Linting**: ruff for code quality
- **Architecture**: Commands are thin wrappers; core/ does the heavy lifting

## Key Commands

```bash
writ init                    # Initialize in repo
writ add <name>              # Create agent
writ use <name>              # Activate agent (writes to IDE files)
writ compose <name>          # Preview composed context
writ export <name> <format>  # Export to specific format
writ save <name>             # Save to personal library
writ load <name>             # Load from personal library
writ publish <name>          # Make agent publicly discoverable on enwrit.com
writ unpublish <name>        # Remove agent from public registry
writ login / logout          # Authenticate with enwrit.com for cross-device sync
writ lint [name]             # Validate quality
```

## File Structure

- `src/writ/` -- Python package
- `src/writ/commands/` -- One file per command group
- `src/writ/core/` -- Business logic (models, store, composer, formatter, etc.)
- `src/writ/integrations/` -- External registry adapters (enwrit API, PRPM, Agent Skills, URL)
- `src/writ/templates/` -- Built-in agent team templates (bundled in package)
- `tests/` -- pytest test suite
