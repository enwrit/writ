# writ

Optional CLI extension for AI instructions -- find, install, quality-check, and route
instructions across AI coding tools, projects, and agents.

## Commands

### Setup
- `writ init` -- initialize writ in this repo (creates .writ/, auto-installs writ-context)
- `writ init --template <name>` -- bootstrap from template (fullstack, python, react, typescript, rules, context)

### Find & Add
- `writ search <query>` -- semantic search across 6,000+ instructions ranked by relevance and quality score
- `writ add <name>` -- add instruction: checks project, personal library, then Hub; creates new if not found
- `writ add <name> --lib` -- force fetch from personal library
- `writ add <name> --from prpm` -- install directly from PRPM registry
- `writ add <name> --format cursor` -- write to a specific IDE format
- `writ add --file <path>` -- import from markdown file or directory
- `writ add --template <name>` -- add from built-in template

### Manage
- `writ list` -- show all instructions in this project
- `writ list --library` -- show personal library (local + remote)
- `writ remove <name>` -- remove instruction

### Quality
- `writ lint [file|name]` -- score instruction quality (0-100, ML-powered)
- `writ lint --deep` -- AI-powered deep analysis (requires login)
- `writ lint --code` -- deterministic code-only scoring
- `writ diff <file>` -- compare lint score vs previous git commit
- `writ upgrade [name]` -- check for and apply instruction updates from Hub/PRPM

### Library & Sync
- `writ save <name>` -- save to personal library (~/.writ/); syncs to cloud if logged in
- `writ save <name> --local` -- save locally only (skip cloud sync)
- `writ sync` -- bulk sync library with enwrit.com (confirmation for large operations)
- `writ login` / `writ logout` -- authenticate for cross-device sync
- `writ register` -- create account
- `writ publish <name>` / `writ unpublish <name>` -- public Hub visibility

### Agent Communication
- `writ chat start --with <repo>` -- start conversation with a peer repo's agent
- `writ chat send <id> "msg" --file <path>` -- send message with optional file attachments
- `writ chat list` / `writ chat read` -- manage conversations
- `writ inbox` -- show conversations with unread messages
- `writ peers add|list|remove` -- manage peer repo connections
- `writ connect` -- interactive peer setup wizard
- `writ handoff create <from> <to>` -- context handoff between agents
- `writ memory export|import|list` -- cross-project memory sharing

### Knowledge & Review
- `writ review <name>` -- browse or submit reviews for public instructions
- `writ threads list|start|post|resolve` -- knowledge threads for collaborative discussions
- `writ approvals create` -- request human approval for an agent action
- `writ approvals list|approve|deny` -- human-in-the-loop approval management

### Integration
- `writ mcp install` -- auto-configure MCP server in detected IDEs (slim mode, opt-in)
- `writ mcp uninstall` -- remove writ MCP config from IDEs
- `writ mcp serve` -- expose writ tools via MCP protocol (auto-installs deps)

Docs: https://github.com/enwrit/writ
