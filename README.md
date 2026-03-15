# writ

**Your AI instructions are scattered across 8 formats in 5 tools.** writ fixes that.

[![PyPI](https://img.shields.io/pypi/v/enwrit)](https://pypi.org/project/enwrit/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://github.com/enwrit/writ/actions/workflows/ci.yml/badge.svg)](https://github.com/enwrit/writ/actions)

Write agent instructions once. Route them to Cursor, Claude Code, Copilot, Windsurf, Codex, Kiro -- automatically. Save your best agents to the cloud. Reuse them anywhere.

```bash
pip install enwrit
writ init --template fullstack
writ use architect
# Done. Your IDE now has a 4-layer composed instruction set.
```

**[Browse 50+ curated instructions on the Hub](https://enwrit.com/hub)** -- rules, agents, and programs ready to install.

---

## 30-Second Quickstart

```bash
# 1. Install
pip install enwrit

# 2. Initialize in any repo (auto-detects your stack)
writ init

# 3. Install a pre-built instruction from the Hub
writ install verification-loop
writ install code-review-agent

# 4. Activate -- writes to your IDE's native files
writ use verification-loop
writ use code-review-agent
```

That's it. Your IDE now has battle-tested instructions -- no copy-paste, no manual conversion.

## What Makes writ Different

| Capability | What it means |
|-----------|--------------|
| **Context composition** | Layer project + team + agent + handoff context into one coherent instruction set |
| **9 output formats** | Write once, export to Cursor `.mdc`, `CLAUDE.md`, `AGENTS.md`, Copilot, Windsurf, Codex, Kiro, Agent Cards |
| **Personal library + cloud sync** | `writ save` → `writ load` on any device. Your agents follow you. |
| **Cross-project memory** | Export context from Repo A, import into Repo B |
| **Hub with 50+ instructions** | Rules, agents, and autonomous programs. All peer-reviewed. `writ install <name>` |
| **MCP server** | One line in your config and any agent can search/install from the Hub |

## How It Works

writ writes to **native IDE files** -- it does NOT call LLM APIs.

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
Layer 4: Handoff context      ← Output from another agent
Layer 3: Agent's instructions  ← The agent's own role
Layer 2: Inherited context     ← From parent agents
Layer 1: Project context       ← Auto-detected (languages, frameworks, structure)
```

```bash
writ use implementer --with architect    # Compose with architect's context
writ compose reviewer --with architect   # Preview before writing
```

## MCP Server (One-Line Setup)

Give any MCP-compatible agent access to the Hub -- no CLI needed:

```json
{
  "mcpServers": {
    "writ": {
      "command": "uvx",
      "args": ["enwrit", "mcp", "serve"]
    }
  }
}
```

This exposes 22 tools: search the Hub, install instructions, compose context, read files, start agent conversations, and more. Run `writ mcp serve --help` for the full list.

## Hub: Browse & Install

The [enwrit Hub](https://enwrit.com/hub) has 50+ curated instructions across three tiers:

- **Rules** -- passive context that shapes agent behavior (verification loops, commit hygiene, no-secrets)
- **Agents** -- on-invocation workers (code review, git commit, documentation, security audit)
- **Programs** -- autonomous metric-driven loops (test coverage optimizer, dependency freshness, dead code eliminator)

```bash
writ search "code review"          # Search from CLI
writ install code-review-agent     # Install into your project
writ use code-review-agent         # Activate in your IDE
```

## Templates

Bootstrap an agent team in seconds:

```bash
writ init --template fullstack     # Architect + implementer + reviewer + tester
writ init --template python        # Python developer + reviewer
writ init --template typescript    # TypeScript developer + reviewer
writ init --template rules         # Project rule + coding standards
```

## Personal Library & Cloud Sync

```bash
writ save my-reviewer              # Save to library (local + cloud)
writ login                         # Authenticate for cross-device sync
writ load my-reviewer              # Load on any machine
writ library                       # See everything (local + remote)
```

## Cross-Project Memory

```bash
writ memory export research-insights     # Export from current project
writ memory import research-insights     # Import in another project
```

## Agent-to-Agent Communication

Agents can have structured conversations across repos:

```bash
writ peers add partner-repo --path ../partner-repo
writ chat start --with partner-repo --goal "Review API design"
writ chat send <conv-id> "Here's my proposed schema..."
writ inbox                          # Check for responses
```

## All Commands

| Command | Description |
|---------|-------------|
| `writ init` | Initialize in current repo |
| `writ add <name>` | Create instruction (agent, rule, context, program) |
| `writ add --file <path>` | Import markdown file(s) or directory |
| `writ list` | List all instructions |
| `writ use <name>` | Activate (compose + write to IDE files) |
| `writ edit <name>` | Open in $EDITOR |
| `writ remove <name>` | Remove instruction |
| `writ export <name> <format>` | Export to specific format |
| `writ compose <name>` | Preview composed context |
| `writ save / load` | Personal library (local + cloud) |
| `writ library` | List personal library |
| `writ search <query>` | Search Hub |
| `writ install <name>` | Install from Hub |
| `writ publish / unpublish` | Make publicly discoverable |
| `writ login / logout` | Authenticate with enwrit.com |
| `writ register` | Create account |
| `writ lint [name]` | Validate instruction quality |
| `writ sync` | Bulk bidirectional library sync |
| `writ mcp serve` | Start MCP server (22 tools) |
| `writ chat start/send/inbox` | Agent-to-agent conversations |
| `writ memory export/import` | Cross-project memory |
| `writ handoff create` | Create agent handoff |
| `writ review <name>` | Browse/submit reviews |
| `writ threads` | Knowledge threads |

## Instruction Format

Instructions are YAML files in `.writ/`, routed by `task_type`:

```yaml
name: reviewer
description: "Code reviewer for TypeScript"
version: 1.0.0
task_type: agent    # agent | rule | context | program | template
tags: [typescript, review]
instructions: |
  You are a code reviewer specializing in TypeScript.
  Focus on: type safety, component composition, performance.
composition:
  inherits_from: [architect]
  project_context: true
```

Users interact primarily with markdown. Use `writ add --file` to import `.md`, `.mdc`, or `.txt` files directly.

## Development

```bash
git clone https://github.com/enwrit/writ.git
cd writ
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"
pytest                    # 309 tests
ruff check src/ tests/
```

## License

MIT

## Links

- **Hub**: [enwrit.com/hub](https://enwrit.com/hub) -- Browse and install instructions
- **Website**: [enwrit.com](https://enwrit.com)
- **GitHub**: [github.com/enwrit/writ](https://github.com/enwrit/writ)
- **PyPI**: [pypi.org/project/enwrit](https://pypi.org/project/enwrit/)
