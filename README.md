# writ

**The communication layer for AI agents.** Route context between repos, devices, and tools.

[![PyPI](https://img.shields.io/pypi/v/enwrit)](https://pypi.org/project/enwrit/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://github.com/enwrit/writ/actions/workflows/ci.yml/badge.svg)](https://github.com/enwrit/writ/actions)

---

## What is writ?

writ manages AI agent instructions across tools, projects, and devices. Write once, use everywhere -- Cursor, Claude Code, Copilot, Windsurf, Codex, Kiro. No copy-paste, no manual conversion.

```bash
pip install enwrit
writ init --template python
writ use developer
# Done. Your IDE now has the agent instructions.
```

## What Makes It Different

1. **Context composition** -- layer project + team + agent + handoff context into one coherent instruction set
2. **Personal agent library with cloud sync** -- save agents to [enwrit.com](https://enwrit.com), access from any device
3. **Cross-project memory** -- export context from Repo A, import into Repo B

## Quick Start

```bash
# Initialize in your repo (auto-detects languages, frameworks, structure)
writ init

# Create an agent with instructions
writ add reviewer --description "Code reviewer" --tags "review,quality"
writ edit reviewer

# Activate it -- writes to your IDE's native files
writ use reviewer

# Export to a specific format
writ export reviewer cursor
writ export reviewer claude

# Save to your personal library (syncs to enwrit.com if logged in)
writ save reviewer

# Load in another project
writ load reviewer

# Check project status
writ status
```

## How It Works

writ writes to **native IDE/CLI files** -- it does NOT call LLM APIs.

| Tool | writ writes to |
|------|----------------|
| Cursor | `.cursor/rules/writ-*.mdc` |
| Claude Code | `CLAUDE.md` |
| AGENTS.md | `AGENTS.md` |
| GitHub Copilot | `.github/copilot-instructions.md` |
| Windsurf | `.windsurfrules` |
| Codex / Kiro | `AGENTS.md` |

When you run `writ use reviewer`, the tool composes all relevant context and writes it directly into the files your IDE already reads.

## Context Composition

The core innovation. Each agent's context is composed from 4 layers:

```
Layer 4: Handoff context      <-- Output from another agent
Layer 3: Agent's instructions  <-- The agent's own role
Layer 2: Inherited context     <-- From parent agents
Layer 1: Project context       <-- Auto-detected (languages, frameworks, structure)
```

```bash
# Compose with additional context from another agent
writ use implementer --with architect

# Preview what would be written
writ compose reviewer --with architect
```

## Templates

Bootstrap an entire agent team in seconds:

```bash
writ init --template default       # General-purpose assistant
writ init --template fullstack     # Architect + implementer + reviewer + tester
writ init --template python        # Python developer + reviewer
writ init --template typescript    # TypeScript developer + reviewer
```

Or add templates to an existing project:

```bash
writ add --template fullstack
```

## Personal Library & Cloud Sync

Save agents and reuse them across projects and devices:

```bash
# Save to library (local + remote if logged in)
writ save my-reviewer

# Log in for cross-device sync
writ login

# Load in another project (tries local, falls back to remote)
writ load my-reviewer

# See your full library (local + remote status)
writ library
```

## Cross-Project Memory

Share context between repositories:

```bash
# Export from current project
writ memory export research-insights

# Import in another project
writ memory import research-insights

# Create an agent from memory
writ memory import research-insights --as-agent research-context
```

## A2A Agent Card Export

Export agents as [A2A-compatible Agent Cards](https://google.github.io/A2A/) for machine-readable discovery:

```bash
writ export reviewer agent-card
writ export reviewer agent-card --dry-run   # Preview the JSON
```

## .writignore

Control what the scanner picks up. Create a `.writignore` file in your project root with gitignore-style patterns:

```
# Ignore generated files
generated/
*.min.js

# But keep this one
!important-generated.js
```

Built-in defaults already ignore `node_modules/`, `venv/`, `.git/`, `__pycache__/`, `dist/`, `build/`, and more.

## Commands

| Command | Description |
|---------|-------------|
| `writ init` | Initialize writ in current repo |
| `writ add <name>` | Create a new agent |
| `writ list` | List all agents |
| `writ use <name>` | Activate agent (compose + write) |
| `writ edit <name>` | Open in $EDITOR |
| `writ remove <name>` | Remove agent |
| `writ export <name> <format>` | Export to specific format |
| `writ compose <name>` | Preview composed context |
| `writ save <name>` | Save to personal library |
| `writ load <name>` | Load from library |
| `writ library` | List personal library |
| `writ login` / `writ logout` | Authenticate with enwrit.com |
| `writ lint [name]` | Validate quality |
| `writ status` | Show project diagnostics |
| `writ version` | Show version and environment |
| `writ memory export/import` | Cross-project memory |
| `writ handoff create <from> <to>` | Create agent handoff |
| `writ search <query>` | Search registries |
| `writ install <name>` | Install from registry |

## Agent Config Format

Agents are YAML files in `.writ/agents/`:

```yaml
name: reviewer
description: "Code reviewer for TypeScript"
version: 1.0.0
tags: [typescript, review]
instructions: |
  You are a code reviewer specializing in TypeScript.
  Focus on: type safety, component composition, performance.
composition:
  inherits_from: [architect]
  receives_handoff_from: [implementer]
  project_context: true
```

## Development

```bash
git clone https://github.com/enwrit/writ.git
cd writ
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/ tests/
```

## License

MIT

## Links

- **Website**: [enwrit.com](https://enwrit.com)
- **GitHub**: [github.com/enwrit/writ](https://github.com/enwrit/writ)
- **PyPI**: [pypi.org/project/enwrit](https://pypi.org/project/enwrit/)
