# Skill Creator

A skill for creating new skills and iteratively improving them.

Originally from Anthropic's Claude Code skill-creator plugin. Generalized for
any AI coding tool.

At a high level, the process of creating a skill goes like this:

- Decide what you want the skill to do and roughly how it should do it
- Write a draft of the skill
- Create a few test prompts and run the agent-with-access-to-the-skill on them
- Help the user evaluate the results both qualitatively and quantitatively
- Rewrite the skill based on feedback
- Repeat until satisfied
- Expand the test set and try again at larger scale

Your job is to figure out where the user is in this process and help them
progress through these stages. Maybe they want to create a skill from scratch,
or maybe they already have a draft and want to improve it. Be flexible -- if
the user says "I don't need evaluations, just vibe with me", do that instead.

## Communicating with the User

Skills are used by people across a wide range of familiarity with coding jargon.
Pay attention to context cues to understand how to phrase your communication.

- "evaluation" and "benchmark" are borderline, but OK for most users
- For "JSON" and "assertion", look for cues that the user knows what those are
  before using them without explaining

It's OK to briefly explain terms if you're in doubt.

---

## Creating a Skill

### Capture Intent

Start by understanding the user's intent. The current conversation might already
contain a workflow the user wants to capture (e.g., they say "turn this into a
skill"). If so, extract answers from the conversation history first -- the tools
used, the sequence of steps, corrections the user made, input/output formats
observed. The user may need to fill gaps, and should confirm before proceeding.

1. What should this skill enable the AI agent to do?
2. When should this skill trigger? (what user phrases/contexts)
3. What's the expected output format?
4. Should we set up test cases to verify the skill works? Skills with objectively
   verifiable outputs (file transforms, data extraction, code generation, fixed
   workflow steps) benefit from test cases. Skills with subjective outputs
   (writing style, art) often don't. Suggest the appropriate default based on
   the skill type, but let the user decide.

### Interview and Research

Proactively ask questions about edge cases, input/output formats, example files,
success criteria, and dependencies. Wait to write test prompts until you've got
this part ironed out.

If the environment offers tools for research (searching docs, finding similar
skills, looking up best practices), use them. Come prepared with context to
reduce burden on the user.

### Write the Skill

Based on the user interview, create the skill file with these components:

- **Name/title**: Skill identifier
- **Description**: When to trigger, what it does. This is the primary triggering
  mechanism -- include both what the skill does AND specific contexts for when to
  use it. AI agents tend to "undertrigger" skills, so make descriptions slightly
  "pushy". Example: instead of "Dashboard builder", write "Build data dashboards
  and visualizations. Use when the user mentions dashboards, data visualization,
  metrics display, or wants to display any kind of structured data visually."
- **The rest of the skill**: Instructions, examples, patterns

### Skill Writing Guide

#### Anatomy of a Skill

```
skill-name/
├── SKILL.md (or skill-name.md)
│   ├── Title + description (what it does, when to use)
│   └── Markdown instructions
└── Bundled Resources (optional)
    ├── scripts/    - Executable code for deterministic/repetitive tasks
    ├── references/ - Docs loaded into context as needed
    └── assets/     - Files used in output (templates, icons, fonts)
```

#### Progressive Disclosure

Skills use a three-level loading system:
1. **Metadata** (name + description) - Always in context (~100 words)
2. **Skill body** - In context whenever skill triggers (<500 lines ideal)
3. **Bundled resources** - Loaded as needed (unlimited size)

Key patterns:
- Keep the main file under 500 lines. If approaching this limit, add a hierarchy
  with clear pointers to reference files.
- Reference files clearly with guidance on when to read them.
- For large reference files (>300 lines), include a table of contents.

**Domain organization**: When a skill supports multiple domains/frameworks,
organize by variant:
```
cloud-deploy/
├── SKILL.md (workflow + selection logic)
└── references/
    ├── aws.md
    ├── gcp.md
    └── azure.md
```
The agent reads only the relevant reference file based on context.

#### Principle of Lack of Surprise

Skills must not contain malware, exploit code, or any content that could
compromise system security. A skill's contents should not surprise the user in
their intent if described. Don't create misleading skills or skills designed to
facilitate unauthorized access or data exfiltration.

#### Writing Patterns

Prefer the imperative form in instructions.

**Defining output formats:**
```markdown
## Report structure
Use this template:
# [Title]
## Executive summary
## Key findings
## Recommendations
```

**Examples pattern:**
```markdown
## Commit message format
**Example 1:**
Input: Added user authentication with JWT tokens
Output: feat(auth): implement JWT-based authentication
```

#### Writing Style

Explain to the agent why things are important instead of heavy-handed MUSTs.
AI agents are smart -- they have good theory of mind and when given a good
harness can go beyond rote instructions. If you find yourself writing ALWAYS
or NEVER in all caps, that's a signal to reframe and explain the reasoning
instead. That's a more powerful and effective approach.

Make the skill general, not super-narrow to specific examples. Start by writing
a draft and then look at it with fresh eyes and improve it.

### Test Cases

After writing the skill draft, come up with 2-3 realistic test prompts -- the
kind of thing a real user would actually say. Share them with the user for
approval, then run them.

Good test prompts are realistic, varied, and edge-case heavy:

Bad: `"Format this data"`, `"Create a chart"`

Good: `"ok so my boss just sent me this xlsx file (in my downloads, called
something like 'Q4 sales final FINAL v2.xlsx') and she wants me to add a
column that shows the profit margin. Revenue is in column C and costs in D"`

Save test prompts in a structured format (e.g., `evals/evals.json`) for
reproducibility across iterations.

---

## Running and Evaluating Test Cases

For each test case, run the skill and save the output. If the environment
supports parallel execution (subagents, multiple sessions), run all test cases
simultaneously for faster iteration. If it supports baseline comparisons, also
run each prompt without the skill to measure the difference.

Organize results by iteration:
```
skill-workspace/
├── iteration-1/
│   ├── eval-descriptive-name/
│   │   ├── with_skill/outputs/
│   │   └── without_skill/outputs/
│   └── ...
├── iteration-2/
└── ...
```

While runs are in progress, draft quantitative assertions for each test case
if the outputs are objectively verifiable. Good assertions are:
- Objectively verifiable (file exists, contains expected content, passes validation)
- Descriptively named (someone should understand what each assertion checks at a glance)

Don't force assertions onto subjective outputs -- use qualitative review instead.

---

## Improving the Skill

This is the heart of the loop. You've run the test cases, the user has reviewed
the results, and now you need to make the skill better based on their feedback.

### How to Think About Improvements

1. **Generalize from the feedback.** You're creating skills that will be used
   across many different prompts, not just these test cases. If the skill works
   only for the test examples, it's useless. Rather than fiddly overfit changes
   or oppressively constrictive rules, try branching out -- use different
   metaphors, recommend different patterns. It's cheap to try and you might land
   on something great.

2. **Keep the prompt lean.** Remove things that aren't pulling their weight.
   Read the transcripts, not just the final outputs -- if the skill is making the
   agent waste time on unproductive steps, remove the instructions causing that.

3. **Explain the why.** Try hard to explain the *why* behind everything you're
   asking the agent to do. Even if the user's feedback is terse or frustrated,
   try to actually understand the task and why they wrote what they wrote, then
   transmit this understanding into the instructions. If you find yourself
   writing ALWAYS or NEVER in all caps, reframe and explain the reasoning. That's
   a more humane, powerful, and effective approach.

4. **Look for repeated work across test cases.** Read the transcripts and notice
   if the agent independently wrote similar helper scripts in every test run. If
   all 3 test cases resulted in a `create_docx.py` or `build_chart.py`, that's
   a strong signal the skill should bundle that script in `scripts/`. Write it
   once and tell the skill to use it.

Take your time and really mull things over. Write a draft revision, then look at
it with fresh eyes and improve it. Get into the head of the user and understand
what they want and need.

### The Iteration Loop

After improving the skill:

1. Apply improvements
2. Rerun all test cases into a new `iteration-<N+1>/` directory
3. Compare with previous iteration's results
4. Present results to the user for review
5. Read feedback, improve again, repeat

Keep going until:
- The user says they're happy
- All feedback is empty (everything looks good)
- You're not making meaningful progress

---

## Improving an Existing Skill

If the user already has a skill and wants to improve it:

1. Read the existing skill carefully
2. Skip straight to testing (come up with realistic test prompts)
3. Evaluate, improve, repeat

When updating, preserve the original name and identity. Don't rename unless
the user asks.

---

## Advanced: Blind Comparison

For more rigorous comparison between two versions of a skill, use blind
evaluation: give two outputs to an independent evaluator (human or agent)
without revealing which version produced which output, and let them judge
quality. This controls for bias toward the newer version.

This is optional and most users won't need it. The human review loop is
usually sufficient.

---

## Description Optimization

After the skill content is finalized, optimize the description for better
triggering accuracy.

### Generate Trigger Eval Queries

Create ~20 eval queries -- a mix of should-trigger and should-not-trigger:

**Should-trigger queries (8-10):** Different phrasings of the same intent --
some formal, some casual. Include cases where the user doesn't explicitly name
the skill but clearly needs it. Include uncommon use cases and cases where this
skill competes with another but should win.

**Should-not-trigger queries (8-10):** The most valuable ones are near-misses --
queries that share keywords with the skill but actually need something different.
Think adjacent domains and ambiguous phrasing where a naive keyword match would
trigger but shouldn't.

Don't make should-not-trigger queries obviously irrelevant. "Write a fibonacci
function" as a negative test for a PDF skill is too easy. The negative cases
should be genuinely tricky.

All queries should be realistic: include file paths, personal context, casual
speech, typos, varying lengths. Focus on edge cases.

### Test and Iterate

Run each query and check whether the skill triggers correctly. Adjust the
description based on what fails. Iterate until the trigger rate is high for
should-trigger queries and low for should-not-trigger queries.

How triggering works: AI agents see the skill's name + description and decide
whether to activate it. Simple, one-step queries may not trigger even with a
matching description because the agent can handle them without specialized help.
Complex, multi-step queries reliably trigger when the description matches. Design
eval queries that are substantive enough to benefit from the skill.

---

## Recap

The core loop, one more time:

1. Figure out what the skill is about
2. Draft or edit the skill
3. Run the agent-with-skill on test prompts
4. Evaluate outputs with the user (qualitative + quantitative)
5. Improve based on feedback
6. Repeat until satisfied
