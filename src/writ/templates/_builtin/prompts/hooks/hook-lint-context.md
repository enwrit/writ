## Type Context: Context Document

This file appears to be a **context document** (detected from its folder location). Context documents describe project structure, conventions, or domain knowledge. Research warns that generic context *reduces* agent success rates and
increases cost 20%+ (AGENTS.md study). Context must earn its tokens.

Prioritize these context-specific concerns:

- **Structural accuracy**: If the document contains a treeview, file listing, or architecture diagram, does it match actual code? Stale treeviews are the most common context rot -- files renamed, moved, or deleted but the treeview still references the old paths.
- **No general knowledge**: Does the document explain things any LLM already knows? "Python uses indentation for blocks" or "React is a UI framework" wastes tokens. Context should contain project-specific facts only.
- **Currency of references**: Are version numbers, dependency names, command examples, and file paths still correct? Context docs rot fast when code changes -- flag anything that looks like it could be outdated.
- **Minimality**: Does the document repeat information available in code comments, README, or other always-on rules? Duplicated context means double the maintenance and double the tokens for no gain.
- **Token budget awareness**: This file is likely loaded into every prompt. Is its size justified? Per-file threshold: >5,000-7,000 chars can give a slight warning.
