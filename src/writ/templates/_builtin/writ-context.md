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
- `writ list` -- show user instructions in this project (built-in hidden by default)
- `writ list --all` -- show all instructions including built-in
- `writ list --user` -- show only user instructions
- `writ list --library` -- show personal library (local + remote)
- `writ remove <name>` -- remove instruction

### Quality
- `writ lint [file|name]` -- score instruction quality (0-100, ML-powered)
- `writ lint --prompt` -- type-aware qualitative review (prints analysis instruction for your IDE's AI)
- `writ lint --prompt --fix` -- review + instruct the AI to apply fixes directly
- `writ lint --prompt --with-file` -- inline file content in the prompt (instead of asking agent to read it)
- `writ lint --prompt --subagent` -- instruct IDE to launch a subagent for the review
- `writ lint --cloud` -- AI scoring via enwrit.com API only (requires login)
- `writ lint --local` -- AI scoring via your configured local model (writ model set local)
- `writ lint --local-model` -- bundled writ-lint-0.8B model (auto-downloaded, no setup needed)
- `writ lint --code` -- deterministic code-only scoring
- `writ plan review <file>` -- plan review via prompt injection (default, no API call)
- `writ plan review <file> --with-plan` -- include plan content inline in the prompt
- `writ plan review <file> --local` -- send to your configured local model (writ model set local)
- `writ plan review <file> --cloud` -- send to enwrit.com API only (requires login)
- `writ plan review <file> --cloud --json` -- structured JSON output for agent consumption
- `writ plan review <file> --subagent` -- launch a subagent for the review
- `writ diff <file>` -- compare lint score vs previous git commit
- `writ upgrade [name]` -- check for and apply instruction updates from Hub/PRPM

### Documentation Health
- `writ docs init` -- create documentation index (writ-docs-index) for knowledge health tracking
- `writ docs check` -- heuristic documentation health scan (dead refs, staleness, contradictions)
- `writ docs check --user` -- show only user documentation files
- `writ docs check --all` -- show all files including static built-in
- `writ docs update` -- documentation update pass (runs check, then instructs your model to fix issues and log summary)
- `writ docs update --user` -- focus on user documentation only
- `writ query` -- show documentation index (helps agents navigate project knowledge)
- `writ query "search term"` -- filter index by keyword and show relevant files
- `writ status` -- recent activity summary + documentation health score

### Library & Sync
- `writ save <name>` -- save to personal library (~/.writ/); syncs to cloud if logged in
- `writ save <name> --local` -- save locally only (skip cloud sync)
- `writ sync` -- bulk sync library with enwrit.com (confirmation for large operations)
- `writ login` / `writ logout` -- authenticate for cross-device sync
- `writ register` -- create account
- `writ publish <name>` / `writ unpublish <name>` -- public Hub visibility

### Agent Communication
- `writ chat start --with <repo> [--goal "purpose"]` -- start conversation with a peer repo's agent
- `writ chat send <id> "msg" --file <path>` -- send message with optional file attachments
- `writ chat list` / `writ chat read` -- manage conversations
- `writ inbox` -- show conversations with unread messages
- `writ peers add|list|remove` -- manage peer repo connections
- `writ connect` -- interactive peer setup wizard
- `writ handoff create <from> <to> --summary "..." | --file <path>` -- context handoff between agents (content required via --summary or --file)
- `writ memory export|import|list` -- cross-project memory sharing

### Knowledge & Review
- `writ review <name>` -- browse or submit reviews for public instructions
- `writ threads list|start|post|resolve` -- knowledge threads for collaborative discussions
- `writ approvals create` -- request human approval for an agent action
- `writ approvals list|approve|deny` -- human-in-the-loop approval management

### Configuration
- `writ model set <provider>` -- configure LLM for plan review (openai, anthropic, gemini, local)
- `writ model set local --url <url>` -- use LM Studio, Ollama, or any OpenAI-compatible server
- `writ model list` -- show current model configuration
- `writ model clear` -- remove model configuration
- `writ hook install` -- git pre-commit hook for instruction quality checks
- `writ hook uninstall` -- remove pre-commit hook

### Integration
- `writ mcp install` -- auto-configure MCP server in detected IDEs (slim mode, opt-in)
- `writ mcp uninstall` -- remove writ MCP config from IDEs
- `writ mcp serve` -- expose writ tools via MCP protocol (24 tools full / 2 slim)

Docs: https://github.com/enwrit/writ
