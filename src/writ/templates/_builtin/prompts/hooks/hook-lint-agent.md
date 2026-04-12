## Type Context: Agent

This file appears to be an **agent instruction** (detected from its folder location). Agent instructions define persistent behavior loaded into context for e.g. subagents. Research shows over-specification reduces success and increases cost 20%+ (AGENTS.md study). The sweet spot is concise, clear and precise.

Prioritize these agent-specific concerns:

- **Boundaries**: Does the instruction define Always / Ask-first / Never tiers? Without explicit boundaries, agents default to "increasingly creative workarounds -- deleting lock files, bypassing checks, silently ignoring failures" (Blake Crosley). Check for a clear scope section.
- **Escalation rules**: What should the agent do when stuck? "Stop after 3 failed attempts and report" is better than silence. Without escalation, agents resolve ambiguity by guessing (42% resolve-rate drop per AMBIG-SWE).
- **Priority hierarchy**: When constraints conflict, which wins? Safety > correctness > conventions > efficiency is a common ordering. Without it, the agent makes arbitrary choices on every conflict.
- **Over-specification risk**: Does this file try to cover everything? AGENTIF data: compliance drops from 78% to 33% as constraint count increases. IF the agent instruction is > 150 lines, flag bloated sections that could be split into separate rules or skills.
