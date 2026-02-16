# Example Project

This is a sample project used for testing and demonstrating `writ` workflows.

It simulates a real repo with:
- A Python + TypeScript stack
- Pre-existing agent files (AGENTS.md, .cursor/rules/)
- A `.writ/` directory with configured agents

## Testing Workflows

```bash
# From the example_project/ directory:

# 1. Initialize writ (imports existing agent files)
writ init

# 2. List imported + created agents
writ list

# 3. Add agents from a template
writ add --template fullstack

# 4. Preview composed context
writ compose reviewer

# 5. Activate an agent (writes to IDE files)
writ use reviewer --format cursor --format agents_md

# 6. Export to a specific format
writ export architect claude

# 7. Save to personal library and load elsewhere
writ save reviewer
# (In another project:)
# writ load reviewer

# 8. Lint agents for quality
writ lint

# 9. Create a handoff
writ handoff create architect implementer --summary "Architecture done. Use REST API."

# 10. Compose with handoff + additional agents
writ compose implementer --with architect
```
