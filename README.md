# writ

**Agent instruction management CLI** -- compose, port, and score AI agent configs across tools, projects, and devices.

[![PyPI](https://img.shields.io/pypi/v/enwrit)](https://pypi.org/project/enwrit/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

---

## The Problem

You have AI agent instructions scattered across projects. You can't move them between projects. You can't combine configs from different sources. And when you switch between Cursor, Claude Code, Copilot, or Codex -- you rewrite everything from scratch.

**writ** fixes this.

## Three Things No Other Tool Does

1. **Context composition** -- layer project + team + agent + handoff context into one coherent instruction set
2. **Personal agent library** -- save agents locally, reuse across any project on any device
3. **Cross-project memory** -- export context from Repo A, import into Repo B

## Install

```bash
pip install enwrit
```

## Quick Start

```bash
# Initialize in your repo
writ init

# Create an agent
writ add reviewer --description "Code reviewer" --tags "review,quality"

# Edit the instructions
writ edit reviewer

# Activate it (writes to your IDE's native files)
writ use reviewer

# Export to a specific format
writ export reviewer cursor
writ export reviewer claude

# Save to your personal library
writ save reviewer

# Load in another project
writ load reviewer

# Preview the composed context
writ compose reviewer

# Lint for quality
writ lint reviewer
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

When you run `writ use architect`, the tool composes all relevant context and writes it directly into the files your IDE already reads. No copy-paste, no API integration.

## Context Composition

The core innovation. Each agent's context is composed from 4 layers:

```
Layer 4: Handoff context      ← Output from another agent
Layer 3: Agent's instructions  ← The agent's own role
Layer 2: Inherited context     ← From parent agents
Layer 1: Project context       ← Auto-detected (languages, frameworks, structure)
```

```bash
# Compose with additional context
writ use implementer --with architect

# Preview what would be written
writ compose reviewer --with architect
```

## Templates

Bootstrap an entire agent team in seconds:

```bash
# General-purpose assistant
writ init --template default

# Full team: architect + implementer + reviewer + tester
writ init --template fullstack
```

## Personal Library

Save agents and reuse them across projects:

```bash
# In Project A
writ save my-reviewer

# In Project B
writ load my-reviewer

# See your full library
writ library
```

## Cross-Project Memory

Share context between projects:

```bash
# Export from current project
writ memory export research-insights

# Import in another project
writ memory import research-insights

# Create an agent from memory
writ memory import research-insights --as-agent research-context
```

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
| `writ lint [name]` | Validate quality |
| `writ memory export <name>` | Export cross-project memory |
| `writ memory import <name>` | Import cross-project memory |
| `writ handoff create <from> <to>` | Create agent handoff |
| `writ install <name> --from <source>` | Install from registry |

## Agent Config Format

Agents are simple YAML files in `.writ/agents/`:

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
# Clone and install
git clone https://github.com/enwrit/writ.git
cd writ
python -m venv venv
venv\Scripts\activate  # or source venv/bin/activate
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
