# writ

**Better instructions. Connected agents.**

[![PyPI](https://img.shields.io/pypi/v/enwrit)](https://pypi.org/project/enwrit/)
[![Downloads](https://static.pepy.tech/badge/enwrit)](https://pepy.tech/project/enwrit)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://github.com/enwrit/writ/actions/workflows/ci.yml/badge.svg)](https://github.com/enwrit/writ/actions)

The quality and communication layer for AI coding agents. Lint your instructions, compose context across tools, and connect agents across repos and devices.

```bash
pip install enwrit
writ lint CLAUDE.md               # Instant quality score (0-100) for any instruction
writ init                         # Initialize writ in repo
writ search "code reviewer"       # Find instructions from Hub database
writ add code-review-agent        # Install instruction; from library, project or Hub
```

**[Try the live lint demo](https://enwrit.com)** -- paste any instruction, get an instant quality score. Or **[browse 6000+ instructions on the Hub](https://enwrit.com/hub)**.

---

## Lint Your Instructions

97% of AI instructions have quality defects. `writ lint` catches them. Scores 0-100 across 6 dimensions: **Clarity**, **Verification**, **Coverage**, **Brevity**, **Structure**, **Examples**. Works on any `.md`, `.mdc`, `.txt`, or YAML instruction file -- no `writ init` required.

```bash
writ lint .cursor/rules/my-rule.mdc
# Score: 34 / 100
# - 6 instances of vague language ("try to", "consider", "if possible")
# - No verification commands (agents can't check their own work)
# - No code examples
# Dimension       Score  Summary
# Clarity            43  Moderate              
# Structure          44  Moderate            
# Coverage           31  Needs improvement              
# Brevity            51  Moderate              
# Examples           15  Critical
# Verification       10  Critical
# Suggestions:
#   Replace vague phrases with imperative commands
#   Add verification: test/build/lint commands (2-3x quality impact)
#   Add 1-2 code examples showing desired patterns
```

Several options depending on user preferences - fast, local & cloud. The ML-powered solution is TF-IDF + LightGBM based off teacher-student distillation of 6,000+ ratings & suggestions of instructions. writ-lint-08B is a fine-tuned Qwen3.5-0.8B on the same dataset.

```bash
writ lint CLAUDE.md                     # Score any file (ML-powered, local, free)
writ lint AGENTS.md --deep              # AI-powered analysis (Gemini, via enwrit.com)
writ lint AGENTS.md --deep-local        # Local AI analysis (writ-lint-0.8B, GPU-accelerated)
writ lint rules.mdc --json              # Machine-readable JSON output for CI
writ lint --ci --min-score 60           # Exit 1 if score too low (CI gate)
```

**[Try it in your browser](https://enwrit.com)** -- paste any instruction, get an instant score.

---

## 30-Second Quickstart

```bash
# 1. Install
pip install enwrit

# 2. Initialize in any repo (auto-detects your stack, installs writ-context rule)
writ init

# 3. Search and add from 6,000+ instructions on the Hub
writ search "code review"
writ add code-review-agent         # Fetches from Hub, saves to .writ/, writes to IDE dirs
```

That's it. Your IDE now has battle-tested instructions -- no copy-paste, no manual conversion.

## What Makes writ Different

| Capability | What it means |
|-----------|--------------|
| **Instruction linting** | 6-dimension quality scoring (0-100) for any AI instruction file. Code-based + AI-powered. |
| **Context composition** | Layer project + team + agent + handoff context into one coherent instruction set |
| **Multi-format export** | Cursor `.mdc`, Claude Code, Kiro steering (auto-detected); AGENTS.md, Copilot, Windsurf (opt-in) |
| **Agent communication** | Structured conversations between agents across repos and devices |
| **Personal library + cloud sync** | `writ save` → `writ add --lib` on any device. Your instructions follow you. |
| **Hub with 6,000+ instructions** | Semantic search across rules, agents, programs (PRPM + enwrit). `writ search <query>` / `writ add <name>` |
| **MCP server** | One line in your config and any agent can search/install from the Hub |

## How It Works

writ writes to **native IDE files** -- it does NOT call LLM APIs.

| Tool | writ writes to | Mode |
|------|----------------|------|
| Cursor | `.cursor/rules/writ-*.mdc` | Auto-detected |
| Claude Code | `.claude/rules/writ-*.md` | Auto-detected |
| Kiro | `.kiro/steering/writ-*.md` | Auto-detected |
| AGENTS.md | `AGENTS.md` | Opt-in (`--format`) |
| GitHub Copilot | `.github/copilot-instructions.md` | Opt-in (`--format`) |
| Windsurf | `.windsurfrules` | Opt-in (`--format`) |

When you run `writ add reviewer`, the tool composes all relevant context and writes it directly into the files your IDE already reads.

## Context Composition

The core innovation. Each agent's context is composed from 4 layers:

```
Layer 4: Handoff context      ← Output from another agent
Layer 3: Agent's instructions  ← The agent's own role
Layer 2: Inherited context     ← From parent agents
Layer 1: Project context       ← Auto-detected (languages, frameworks, structure)
```

```bash
writ add implementer                     # Compose with project context
```

## MCP Server

Optional supplement for MCP-only users or features the CLI can't provide (e.g. `writ_compose`, `writ_chat_send_wait`).

```bash
writ mcp install      # Auto-detects Cursor, VS Code, Claude Code, Kiro, Windsurf
                      # Writes MCP config (slim mode), preserves existing servers
writ mcp uninstall    # Remove writ MCP config from all IDEs
```

**Slim mode** (default via `writ mcp install`): exposes only 2 MCP-exclusive tools -- the CLI already provides everything else with less token overhead.

**Full mode** (for MCP-only users without the CLI):

```json
{"mcpServers": {"writ": {"command": "uvx", "args": ["enwrit", "mcp", "serve"]}}}
```

## Hub: Browse & Install

The [enwrit Hub](https://enwrit.com/hub) has 6000+ curated instructions across three tiers:

- **Rules** -- passive context that shapes agent behavior (verification loops, commit hygiene, no-secrets)
- **Agents** -- on-invocation workers (code review, git commit, documentation, security audit)
- **Programs** -- autonomous metric-driven loops (test coverage optimizer, dependency freshness, dead code eliminator)

```bash
writ search "code review"          # Search from CLI
writ add code-review-agent         # Install into your project + activate in your IDE
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
writ save my-reviewer              # Save to library (local + cloud if logged in)
writ save my-reviewer --local      # Save locally only
writ login                         # Authenticate for cross-device sync
writ add my-reviewer --lib         # Load from library on any machine
writ list --library                # See everything (local + remote)
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
| `writ init` | Initialize in current repo (auto-installs writ-context rule) |
| `writ add <name>` | Add instruction: project -> library -> Hub -> create new; auto-writes to IDE dirs |
| `writ add <name> --lib` | Force fetch from personal library |
| `writ add <name> --from prpm` | Install directly from PRPM registry |
| `writ add --from <url>` | Import instruction from any URL |
| `writ add <name> --format cursor` | Export to a specific format |
| `writ add --file <path>` | Import markdown file(s) or directory |
| `writ list` | List all instructions in project |
| `writ list --library` | List personal library (local + remote) |
| `writ remove <name>` | Remove instruction |
| `writ save <name>` | Save to personal library (syncs to cloud if logged in) |
| `writ save <name> --local` | Save locally only (skip cloud sync) |
| `writ search <query>` | Semantic search across Hub (6,000+ instructions) |
| `writ search <query> --min-score N` | Filter search results by quality score |
| `writ search <query> --type agent` | Filter by type (agent, rule, program, skill) |
| `writ publish / unpublish` | Make publicly discoverable |
| `writ login / logout` | Authenticate with enwrit.com |
| `writ register` | Create account |
| `writ lint [file\|name] [--deep] [--deep-local]` | Quality score (0-100, 6 dimensions) |
| `writ lint <file> --json` | Machine-readable JSON output |
| `writ lint <file> --ci --min-score N` | CI gate: exit 1 if score below threshold |
| `writ diff <file>` | Compare lint score vs previous git commit |
| `writ upgrade [name]` | Pull latest version of installed instructions from source |
| `writ sync` | Bulk bidirectional library sync (confirmation for large ops, `--undo` to revert) |
| `writ mcp install` | Auto-configure MCP server in detected IDEs (slim mode) |
| `writ mcp uninstall` | Remove writ MCP server from IDE configs |
| `writ mcp serve` | Start MCP server (21 tools full / 2 slim, called by IDE) |
| `writ chat start/send/inbox` | Agent-to-agent conversations (supports `--file` attachments) |
| `writ memory export/import` | Cross-project memory |
| `writ handoff create` | Create agent handoff |
| `writ review <name>` | Browse/submit reviews |
| `writ threads` | Knowledge threads |
| `writ approvals` | Human-in-the-loop approval management |
| `writ peers add/list/remove` | Manage peer repo connections |
| `writ connect` | Interactive peer setup wizard |

## GitHub Action

Gate PR quality with `writ lint` in CI. You choose which files to lint:

```yaml
- uses: enwrit/writ@main
  with:
    files: ".cursor/rules/*.mdc"    # Glob pattern for files to lint
    min-score: 50                   # Fail if any file scores below this
```

Not all instruction types need the same lint emphasis. E.g. skills and planning instructions may score lower on verification/examples by design -- choose your files and thresholds accordingly.

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
pytest                    # 540+ tests
ruff check src/ tests/
```

## License

MIT

## Links

- **Hub**: [enwrit.com/hub](https://enwrit.com/hub) -- Browse and install instructions
- **Website**: [enwrit.com](https://enwrit.com)
- **GitHub**: [github.com/enwrit/writ](https://github.com/enwrit/writ)
- **PyPI**: [pypi.org/project/enwrit](https://pypi.org/project/enwrit/)
