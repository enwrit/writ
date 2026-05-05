## Type Context: Skill

This file appears to be a **skill** (detected from its folder location). Skills are reusable procedures invoked on-demand. Vercel's research shows skills without clear instructions perform at 53% -- same as having no docs at all. Skills WITH explicit instructions reach 79%. Quality here matters enormously.

Prioritize these skill-specific concerns:

- **Trigger clarity**: When should this skill activate? Vague triggers like "when appropriate" mean the agent never invokes it (Vercel: 56% of evals, the agent never even called the skill). Explicit: "Run when user asks to review code" or "Activate on `writ lint --deep`".
- **Step completeness**: Can the agent follow every step without guessing? Each step should be a concrete action, not a description of intent. Missing intermediate steps are the #1 skill failure mode.
- **Self-containment**: Does the skill reference tools, files, or state it doesn't explain? Every dependency must be stated or have a prerequisite check ("If X does not exist, run Y first").
- **Closure**: How does the agent know the skill is done? Skills without a "finished when..." block either loop forever or stop too early.

### SKILL.md Spec Compliance Checks (AAIF / Linux Foundation Agent Skills)

Apply these in addition to the general checks. Surface each as its own
finding so the user can fix them individually.

1. **Frontmatter validity**
   - `name`: required, non-empty, <= 64 chars, lowercase-kebab (`[a-z0-9][a-z0-9-]*`).
     If the file lives in `skills/<folder>/SKILL.md`, the frontmatter `name` should match `<folder>`.
   - `description`: required, non-empty, <= 1024 chars, no `<` or `>` characters
     (description is injected verbatim into model prompts -- angle brackets risk prompt injection).

2. **Trigger phrase present**
   The `description` should contain an explicit trigger such as
   "use when", "when the user asks", "triggers when", "activate on", or
   "run when". Without one, the agent never invokes the skill.

3. **Body size budget** (token budget for progressive disclosure)
   - Soft warn at >5,000 tokens (~20,000 chars): consider splitting.
   - Strict warn at >10,000 tokens (~40,000 chars): suggest moving
     long examples or context into sibling `references/` files and
     citing them from the body. **Do not fail** -- some legitimate
     skills (e.g. comprehensive playbooks) are large by design and we
     cannot judge that for the user.

4. **Self-containment**
   - Flag a co-located `README.md` next to `SKILL.md`: agents read
     `SKILL.md`; a parallel README causes drift.
   - Flag deep relative reference paths (`../../`) -- skills should
     reference siblings (`references/foo.md`, `scripts/run.sh`),
     not files outside the skill folder.

5. **Cross-folder duplication**
   If the same skill name exists in multiple IDE skill directories
   (e.g. `.cursor/skills/<x>/SKILL.md` and `.claude/skills/<x>/SKILL.md`)
   with diverging content, warn -- this is a sync drift smell.
   Recommend keeping one canonical copy and using `writ add` to
   route it to all detected IDEs.

6. **Over/under-triggering**
   - If `description` is < 30 chars, it's probably under-triggering
     (model has too little signal to know when to invoke the skill).
   - If `description` reads like a generic intro ("This skill helps
     with X"), suggest a trigger-style rewrite ("Use when the user
     asks to X" / "Triggers when ...").
