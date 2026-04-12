# writ

**Better instructions. Connected agents.**

[![PyPI](https://img.shields.io/pypi/v/enwrit)](https://pypi.org/project/enwrit/)
[![Downloads](https://static.pepy.tech/badge/enwrit)](https://pepy.tech/project/enwrit)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://github.com/enwrit/writ/actions/workflows/ci.yml/badge.svg)](https://github.com/enwrit/writ/actions)

The quality and communication layer for AI coding agents. Lint instructions, review plans, check documentation health, and connect agents across repos, devices, and tools.

> **Requires Python 3.11+.** On macOS, `brew install python@3.12` or use [pyenv](https://github.com/pyenv/pyenv). The default macOS Python (3.9) will show "no matching distribution" on install.

```bash
pip install enwrit
writ lint CLAUDE.md               # Instant quality score (0-100) for any instruction
writ plan review plan.md          # AI-powered plan review before implementation
writ init                         # Initialize + install 11 built-in skills
writ search "code reviewer"       # Find from 6,000+ instructions on the Hub
writ add code-review-agent        # Add to project + activate in your IDE
```

**[Try the live lint demo](https://enwrit.com)** -- paste any instruction, get an instant quality score. Or **[browse the Hub](https://enwrit.com/hub)**.

---

## Lint Your Instructions

`writ lint` scores any instruction 0-100 across 6 dimensions: **Clarity**, **Verification**, **Coverage**, **Brevity**, **Structure**, **Examples**. Works on any `.md`, `.mdc`, `.txt`, or YAML file -- no `writ init` required.

```bash
writ lint .cursor/rules/my-rule.mdc
# Score: 34 / 100
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

Three tiers depending on your needs:

```bash
writ lint CLAUDE.md                     # Default: ML-powered, local, free (TF-IDF + LightGBM)
writ lint AGENTS.md --deep              # Deep qualitative review (your IDE's AI)
writ lint AGENTS.md --deep --fix        # Review + auto-fix
writ lint AGENTS.md --deep-api          # AI scoring via enwrit.com (Gemini)
writ lint AGENTS.md --deep-local        # Fully local AI (writ-lint-0.8B, GPU-accelerated)
writ lint rules.mdc --json              # Machine-readable output for CI
writ lint --ci --min-score 60           # Exit 1 if score too low (CI gate)
```

---

## Review Plans Before You Code

`writ plan review` analyzes implementation plans with AI -- catching technical issues, questioning assumptions, and suggesting alternatives before implementation. Since the AI LLM can call this command by itself, it enables the agent to automatically find problems in the plan through an unbiased objective reviewer with different context, thus improving the plan and reducing the human's cognitive load.

```bash
writ plan review plan.md                # Review with your configured model
writ plan review plan.md --json         # Structured JSON for agent consumption
writ plan review plan.md --no-context   # Skip project context injection
```

**Free tier**: `writ login` gives you 5 daily reviews via Gemini -- zero config needed.

---

## Bring Your Own Model

Configure any LLM provider for plan review and AI-powered features. Full privacy -- local models never send data to enwrit.com.

```bash
writ model set openai --api-key sk-...
writ model set anthropic --api-key sk-ant-...
writ model set gemini --api-key AIza...
writ model set local --url http://localhost:1234/v1    # LM Studio, Ollama, etc.
writ model list                                        # Show current config
```

Works with **LM Studio**, **Ollama**, **vLLM**, or any OpenAI-compatible local server.

---

## Documentation Health

Keep your agent's knowledge base accurate. `writ docs` provides schema-driven health-checking -- a documentation index tracks what exists, and heuristic scans detect when reality drifts.

```bash
writ docs init                     # Create documentation index (agents populate it)
writ docs check                    # Heuristic scan: dead refs, treeview drift, staleness
writ docs update                   # AI-powered fix pass (runs check + instructs your model)
writ query                         # Show the docs index (agents use this to navigate)
writ status                        # Activity log + health score at a glance
```

```bash
writ docs check
# Documentation Health: 72/100
# - 3 dead file references in AGENTS.md
# - 2 treeview entries for files that no longer exist
# - 1 stale instruction (last modified 90+ days ago)
```

The documentation index (`writ-docs-index`) acts as a schema for your project's knowledge -- agents read it to know what documentation exists and where. `writ docs update` feeds the health check findings to your IDE's model with a comprehensive instruction to fix issues, update the index, and log a summary of decisions to the `writ-log` instruction.

---

## 11 Built-in Skills

`writ init` auto-installs 11 battle-tested skills into your IDE's skill directory (`.cursor/skills/writ/`, `.claude/skills/writ/`, etc.). Each is generalized from popular open-source repos:

| Skill | What it does | Inspired by |
|-------|-------------|-------------|
| autoresearch | Autonomous research loop | [Karpathy auto-research](https://github.com/karpathy) |
| plan-skill | Structured planning methodology | [obra/superpowers](https://github.com/obra/superpowers) (134k stars) |
| verify-skill | Post-implementation verification | [obra/superpowers](https://github.com/obra/superpowers) (134k stars) |
| superpower-skill | Brainstorming + systematic debugging | [obra/superpowers](https://github.com/obra/superpowers) (134k stars) |
| code-simplifier | Code cleanup patterns | [Anthropic Claude Code plugins](https://github.com/anthropics/claude-code) |
| skill-creator-skill | Meta-skill for creating new skills | [Anthropic Claude Code plugins](https://github.com/anthropics/claude-code) |
| security-scan | Lightweight security audit | [Anthropic security review](https://github.com/anthropics/claude-code) |
| tech-debt-fixer | Technical debt detection | [0xdarkmatter/claude-mods](https://github.com/0xdarkmatter/claude-mods) |
| pre-commit-checks | Pre-commit verification | obra + community patterns |
| doc-maintenance | Documentation health | Community patterns |
| doc-health | Schema-driven doc maintenance | [Karpathy LLM Wiki](https://github.com/karpathy) |

---

## Works With Your Tools

writ writes to **native IDE files** -- your editor picks them up automatically. Instructions are routed to `rules/`, `skills/`, or `agents/` subdirectories based on type.

| Tool | Auto-detected | Rules | Skills | Agents |
|------|:---:|-------|--------|--------|
| Cursor | Yes | `.cursor/rules/` | `.cursor/skills/writ/` | `.cursor/agents/` |
| Claude Code | Yes | `.claude/rules/` | `.claude/skills/writ/` | `.claude/agents/` |
| GitHub Copilot | Yes | `.github/instructions/` | `.github/skills/writ/` | `.github/agents/` |
| Kiro | Yes | `.kiro/steering/` | `.kiro/skills/writ/` | `.kiro/agents/` |
| Windsurf | Yes | `.windsurf/rules/` | `.windsurf/skills/writ/` | `.windsurf/agents/` |
| Codex | Yes | `.codex/rules/` | `.codex/skills/writ/` | `.codex/agents/` |
| Gemini CLI | Yes | `.gemini/rules/` | `.gemini/skills/writ/` | `.gemini/agents/` |
| OpenCode | Yes | `.opencode/rules/` | `.opencode/skills/writ/` | `.opencode/agents/` |
| Cline | Yes | `.clinerules/` | `.cline/skills/writ/` | `.cline/agents/` |
| Roo Code | Yes | `.roo/rules/` | `.roo/skills/writ/` | `.roo/agents/` |
| Amazon Q | Yes | `.amazonq/rules/` | `.amazonq/rules/` | `.amazonq/agents/` |

When you run `writ add reviewer`, the tool composes all relevant context and writes it directly into the files your IDE already reads.

## What Makes writ Different

| Capability | What it means |
|-----------|--------------|
| **Instruction linting** | 6-dimension quality scoring (0-100). Code-based, ML-powered, or AI-powered. |
| **Plan review** | AI analyzes your implementation plans before coding. Local or cloud models. |
| **Docs health** | Schema-driven knowledge health: docs index, heuristic scan, AI-powered update pass, knowledge log. |
| **Multi-format export** | One instruction, 11 auto-detected IDE formats + legacy opt-in formats. |
| **Personal library + cloud sync** | `writ save` → `writ add --lib` on any device. Your instructions follow you. |
| **Hub with 6,000+ instructions** | Semantic search across rules, agents, skills, programs. `writ search` / `writ add`. |
| **Built-in skills** | 11 community-tested skills auto-installed on `writ init`. |
| **Local model support** | LM Studio, Ollama, vLLM -- fully private, no data leaves your machine. |
| **Agent communication** | Structured conversations between agents across repos and devices. |
| **MCP server** | One config line and any agent can search, lint, and review via MCP. |

## Hub: Browse & Install

The [enwrit Hub](https://enwrit.com/hub) aggregates instructions from multiple sources:

- **Rules** -- passive context that shapes agent behavior
- **Agents** -- on-invocation workers (code review, security audit, etc.)
- **Programs** -- autonomous metric-driven loops
- **Skills** -- curated skills from popular GitHub repos

```bash
writ search "code review"          # Semantic search from CLI
writ add code-review-agent         # Add to project + activate in your IDE
```

## Context Composition

Each agent's context is composed from 4 layers:

```
Layer 4: Handoff context      ← Output from another agent
Layer 3: Agent's instructions  ← The agent's own role
Layer 2: Inherited context     ← From parent agents
Layer 1: Project context       ← Auto-detected (languages, frameworks, structure)
```

## Personal Library & Cloud Sync

```bash
writ save my-reviewer              # Save to library (local + cloud if logged in)
writ login                         # Authenticate for cross-device sync
writ add my-reviewer --lib         # Load from library on any machine
writ sync                          # Bulk bidirectional sync
```

## MCP Server

```bash
writ mcp install      # Auto-detects Cursor, VS Code, Claude Code, Kiro, Windsurf
```

**Slim mode** (default): 2 MCP-exclusive tools. **Full mode**: 24 tools including `writ_lint_instruction`, `writ_plan_review`, `writ_docs_check`, and `writ_docs_update`.

```json
{"mcpServers": {"writ": {"command": "uvx", "args": ["enwrit", "mcp", "serve"]}}}
```

## Git Pre-Commit Hook

```bash
writ hook install     # Quality gate: lint instructions on every commit
writ hook uninstall   # Remove cleanly
```

## Agent-to-Agent Communication

```bash
writ peers add partner-repo --path ../partner-repo
writ chat start --with partner-repo --goal "Review API design"
writ chat send <conv-id> "Here's my proposed schema..."
writ inbox                          # Check for responses
```

## All Commands

| Command | Description |
|---------|-------------|
| `writ init` | Initialize in repo, auto-install 11 built-in skills to IDE dirs |
| `writ add <name>` | Add instruction: project -> library -> Hub -> create new |
| `writ add <name> --lib` | Force fetch from personal library |
| `writ add <name> --from prpm` | Install from PRPM registry |
| `writ add --file <path>` | Import markdown file(s) or directory |
| `writ add <name> --format cursor` | Export to a specific format |
| `writ list` | List all instructions in project |
| `writ remove <name>` | Remove instruction |
| `writ save <name>` | Save to personal library (syncs to cloud if logged in) |
| `writ search <query>` | Semantic search across Hub |
| `writ lint [file] [--deep] [--deep --fix] [--deep-api]` | Quality score, qualitative review, or auto-fix |
| `writ lint --ci --min-score N` | CI gate: exit 1 if score below threshold |
| `writ plan review <file>` | AI-powered plan review (configured model or free Gemini) |
| `writ plan review <file> --json` | Structured JSON output for agents |
| `writ docs init / check / update` | Documentation health (index, scan, AI-powered fix pass) |
| `writ query` | Show documentation index (agent navigation) |
| `writ status` | Activity log + health score summary |
| `writ model set / list / clear` | Configure LLM (openai, anthropic, gemini, local) |
| `writ hook install / uninstall` | Git pre-commit hook for quality checks |
| `writ diff <file>` | Compare lint score vs previous git commit |
| `writ upgrade [name]` | Pull latest version from source |
| `writ sync` | Bulk bidirectional library sync |
| `writ mcp install / uninstall / serve` | MCP server (auto-detect IDE, 24 tools full / 2 slim) |
| `writ publish / unpublish` | Make publicly discoverable on enwrit.com |
| `writ login / logout / register` | Authentication for cloud sync |
| `writ chat start / send / inbox` | Agent-to-agent conversations |
| `writ peers add / list / remove` | Manage peer repo connections |
| `writ review <name>` | Browse/submit reviews |
| `writ threads list / start / post` | Knowledge threads |
| `writ approvals create / approve / deny` | Human-in-the-loop approvals |

## GitHub Action

```yaml
- uses: enwrit/writ@main
  with:
    files: ".cursor/rules/*.mdc"
    min-score: 50
```

## Development

```bash
git clone https://github.com/enwrit/writ.git
cd writ
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"
pytest                    # 610+ tests
ruff check src/ tests/
```

## License

MIT

## Links

- **Hub**: [enwrit.com/hub](https://enwrit.com/hub) -- Browse and install instructions
- **Website**: [enwrit.com](https://enwrit.com)
- **GitHub**: [github.com/enwrit/writ](https://github.com/enwrit/writ)
- **PyPI**: [pypi.org/project/enwrit](https://pypi.org/project/enwrit/)
