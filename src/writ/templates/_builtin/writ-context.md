# writ

Optional CLI extension for AI agent instructions -- find, install, quality-check, and route
instructions across AI coding tools, projects, and agents.

## Commands

### Setup
- `writ init` -- initialize writ in this repo (creates .writ/)
- `writ init --template <name>` -- bootstrap from template (fullstack, python, react, typescript, rules, context)

### Find & Install
- `writ search <query>` -- semantic search across 6,000+ instructions ranked by relevance and quality score
- `writ install <name>` -- install an instruction into this project
- `writ install <name> --from prpm` -- install from a specific source

### Create & Manage
- `writ add <name>` -- create a new instruction
- `writ add --file <path>` -- import from markdown file or directory
- `writ add --template <name>` -- add from built-in template
- `writ list` -- show all instructions in this project
- `writ edit <name>` -- open instruction in editor
- `writ remove <name>` -- remove instruction
- `writ use <name>` -- activate (compose context and write to IDE files)
- `writ compose <name>` -- preview composed context (dry run)
- `writ export <name> <format>` -- export to specific format

### Quality
- `writ lint [file|name]` -- score instruction quality (0-100, ML-powered)
- `writ lint --deep` -- AI-powered deep analysis (requires login)
- `writ lint --code` -- deterministic code-only scoring

### Library & Sync
- `writ save <name>` -- save to personal library (~/.writ/)
- `writ load <name>` -- load from personal library
- `writ sync` -- bulk sync library with enwrit.com
- `writ login` / `writ logout` -- authenticate for cross-device sync
- `writ register` -- create account
- `writ publish <name>` / `writ unpublish <name>` -- public Hub visibility

### Agent Communication
- `writ chat start --with <repo>` -- start conversation with a peer repo's agent
- `writ chat send` / `writ chat list` / `writ chat read` -- manage conversations
- `writ inbox` -- show conversations with unread messages
- `writ peers add|list|remove` -- manage peer repo connections
- `writ connect` -- interactive peer setup wizard
- `writ handoff create <from> <to>` -- context handoff between agents
- `writ memory export|import|list` -- cross-project memory sharing

### Knowledge & Review
- `writ review <name>` -- browse or submit reviews for public instructions
- `writ threads list|start|post|resolve` -- knowledge threads for collaborative discussions
- `writ approvals list|approve|deny` -- human-in-the-loop approval management

### Integration
- `writ mcp serve` -- expose writ tools via MCP protocol (22 tools)

Docs: https://github.com/enwrit/writ
