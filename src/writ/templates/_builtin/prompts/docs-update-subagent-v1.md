# Documentation Update Pass (Subagent Delegation)

You (the parent agent) are delegating a documentation update pass to a subagent. The point of delegation is to keep your context lean: the subagent will do the heavy reading and tool-running, not you.

Your only job is a **semantic handover** -- a short block of context only you can provide, since the subagent does not inherit your conversation history. Everything else (git inspection, health check, applying changes, writing the log entry) is the subagent's responsibility.

## Step 1: Write the semantic handover

This is the one thing the subagent cannot recover on its own. Produce a compact block with the following sections. Keep each section tight -- this is handover, not an essay.

```
# Session handover for docs update

## What I worked on this session
- <2-6 bullets: features / fixes / refactors touched, in plain language>

## Files / areas likely affected
- <bullets: paths or areas the subagent should look at first, e.g. `src/writ/commands/chat.py`, `.cursor/rules/project-rule.mdc`>

## Intent and reasoning
- <1-4 bullets: why these changes were made, what they enable, what pattern they follow>
- <constraints you kept in mind, invariants you preserved>

## Things the subagent should NOT touch
- <bullets: areas out of scope, e.g. "do not rewrite AGENTS.md, it was intentionally kept terse">
- <any open questions you want the subagent to flag rather than resolve>

## Known deferrals
- <bullets: things I chose not to document yet, and why>
```

Keep the whole block under ~60 lines. Do not paste code diffs here -- the subagent will pull those itself. This is about *intent*, not *content*.

## Step 2: Launch the subagent

Launch the subagent with the task description below. Paste your semantic handover block inline. Do not run `git status`, `git diff`, or `writ docs check` yourself -- the subagent will.

> **Task: Documentation update pass**
>
> You have no prior context on this repo's current state. Treat the *Session handover* block below as the authoritative summary of what just happened.
>
> Execute the following steps in order:
>
> 1. Run `git status --short` and `git diff --stat HEAD` to see uncommitted changes. Run `git log --oneline -10` for recent committed context. Cross-reference with the handover.
> 2. Run `writ docs check` and capture the full output (it contains dead refs, treeview drift, staleness, contradictions, orphan pages, and lint scores).
> 3. Run `writ docs update` to fetch the full rubric (the standard `docs-update-v1.md` instruction). Follow it step by step.
> 4. Apply **Step 2b: Concept-gap pass** from the rubric. Zoom out on the documentation as a whole and fill genuinely missing concepts. Prefer the cheapest fix: a single clarifying sentence in an existing rule > a short bullet in an existing list > a new subsection > a new dedicated page (last resort). Acronyms expand on first use. Prefer silence over padding.
> 5. For every change, respect the handover's "should NOT touch" list and "deferrals" list. If you find something that arguably needs a change but falls in those lists, note it in your final summary instead of editing.
> 6. After applying all edits, re-run `writ docs check` and confirm issues are resolved (or explicitly left open).
> 7. Append a compact entry to `writ-log` (the writ knowledge log rule). Format:
>    ```
>    - [YYYY-MM-DD HH:MM UTC] docs update (subagent) -- <2-line summary of what changed and why>
>    ```
>
> Return a short final summary to the parent containing: (a) files changed, (b) concept-gap additions (if any), (c) anything you deferred or flagged.
>
> --- Session handover ---
>
> <PASTE YOUR STEP 1 BLOCK HERE>
>
> --- End handover ---

## Step 3: After the subagent finishes

You will receive a short summary back. Do **not** re-verify by re-reading the whole repo -- that would defeat the delegation. Only act if the summary flagged something you specifically need to resolve (e.g. a deferral you want handled now, or a conflict with intent).

If everything looks clean, the update is done. The subagent has already written the `writ-log` entry.
