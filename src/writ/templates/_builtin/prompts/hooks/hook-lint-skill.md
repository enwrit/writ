## Type Context: Skill

This file appears to be a **skill** (detected from its folder location). Skills are reusable procedures invoked on-demand. Vercel's research shows skills without clear instructions perform at 53% -- same as having no docs at all. Skills WITH explicit instructions reach 79%. Quality here matters enormously.

Prioritize these skill-specific concerns:

- **Trigger clarity**: When should this skill activate? Vague triggers like "when appropriate" mean the agent never invokes it (Vercel: 56% of evals, the agent never even called the skill). Explicit: "Run when user asks to review code" or "Activate on `writ lint --deep`".
- **Step completeness**: Can the agent follow every step without guessing? Each step should be a concrete action, not a description of intent. Missing intermediate steps are the #1 skill failure mode.
- **Self-containment**: Does the skill reference tools, files, or state it doesn't explain? Every dependency must be stated or have a prerequisite check ("If X does not exist, run Y first").
- **Closure**: How does the agent know the skill is done? Skills without a "finished when..." block either loop forever or stop too early.
