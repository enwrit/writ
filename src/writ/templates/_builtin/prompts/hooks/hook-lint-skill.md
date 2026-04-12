## Type Context: Skill

This file appears to be a **skill** (detected from its folder location).
Skills are reusable procedures that agents invoke to accomplish specific tasks.

Adapt your review with these skill-specific priorities:

- **Procedure completeness**: Does the skill define every step from trigger to
  completion? Can an agent follow it without guessing intermediate steps?
- **Trigger conditions**: When should this skill be invoked? Are the activation
  criteria explicit, or would an agent guess wrong about when to use it?
- **Self-containment**: Does the skill assume external state, context, or tools
  that aren't mentioned? Every dependency should be stated.
- **Reusability**: Could a different agent in a different project follow this
  skill? Flag assumptions tied to a specific codebase unless intentional.
- **Exit criteria**: How does the agent know the skill is done? A skill without
  a clear "finished when..." block will run indefinitely or stop too early.
