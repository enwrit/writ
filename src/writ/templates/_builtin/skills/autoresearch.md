# Autonomous Research

Autonomous iterative research loop. Given a question or optimization target,
you independently explore, experiment, measure, and refine -- indefinitely --
until stopped by the user.

Inspired by A. Karpathy's auto-research pattern. Generalized for any domain:
code optimization, API evaluation, library comparison, architecture exploration,
performance tuning, prompt engineering, configuration search, etc.

## Setup

Before starting the research loop, work with the user to:

1. **Define the objective**: What are you optimizing or investigating? This must be a measurable outcome (e.g., latency in ms, accuracy percentage, binary pass/fail, score, file size, error count) or a concrete question with a clear "done" criteria.
2. **Agree on a run tag**: Propose a tag based on today's date (e.g. `apr6`). Create a branch: `git checkout -b research/<tag>`.
3. **Identify the scope**: Which files can you modify? Which are read-only? What tools/commands are available? What constraints exist (time budget per experiment, resource limits, no new dependencies)?
4. **Establish the baseline**: Run the current state to get baseline measurements. Record them.
5. **Initialize the results log**: Create `results.tsv` (tab-separated) with columns appropriate to the objective. Always include: `commit`, `metric`, `status`, `description`. Add domain-specific columns as needed.
6. **Confirm and go**: Confirm setup with the user, then begin.

## Experimentation

**What you CAN do:**
- Modify files within the agreed scope
- Try any approach: architectural changes, parameter tuning, algorithm swaps, configuration changes, library substitutions
- Combine ideas from previous experiments
- Read documentation, source code, or referenced materials for new angles

**What you CANNOT do:**
- Modify files outside the agreed scope
- Install new dependencies unless explicitly permitted
- Change the evaluation method or success criteria
- Skip measurement -- every experiment must produce a number

**Simplicity criterion**: All else being equal, simpler is better. A small improvement that adds ugly complexity is not worth it. Removing something and getting equal or better results is a great outcome. When evaluating whether to keep a change, weigh the complexity cost against the improvement magnitude.

## The Experiment Loop

LOOP FOREVER:

1. **Plan**: Decide what to try next. Base your hypothesis on results so far.
2. **Implement**: Make the change. Keep diffs small and focused -- one idea per experiment.
3. **Commit**: `git commit` the change with a descriptive message.
4. **Run**: Execute the experiment. Redirect output to a log file to avoid flooding context: `command > run.log 2>&1`
5. **Measure**: Extract the key metric from the log. If the run failed, read the tail of the log for the error.
6. **Record**: Append results to `results.tsv`. Do NOT commit this file (keep it untracked).
7. **Decide**:
   - If the metric improved: keep the commit, advance the branch.
   - If the metric is equal or worse: `git reset` back to the previous best.
   - If it crashed: attempt a quick fix (typo, import error). If fundamentally broken, discard and move on.

**Timeout**: If a single experiment exceeds 2x the expected duration, kill it and treat it as a failure.

**Crashes**: Use judgment. Easy fixes (typos, missing imports) deserve a retry. Fundamentally broken ideas should be logged as "crash" and skipped.

**NEVER STOP**: Once the loop begins, do NOT pause to ask the human if you should continue. Do NOT ask "should I keep going?" or "is this a good stopping point?". The user expects you to continue working autonomously until manually interrupted. If you run out of ideas, think harder: re-read source code, look for patterns in your results log, try combining previous near-misses, try more radical approaches. The loop runs until the user stops you.

## Results Format

Tab-separated (`results.tsv`), never comma-separated:

```
commit	metric	status	description
a1b2c3d	baseline_value	keep	baseline measurement
b2c3d4e	improved_value	keep	brief description of what changed
c3d4e5f	worse_value	discard	brief description of what changed
d4e5f6g	0	crash	brief description of what failed
```

Add domain-specific columns as needed (e.g., `memory_gb`, `latency_ms`, `accuracy`).

## Tips

- Start with the lowest-hanging fruit. Baseline understanding first, exotic ideas later.
- If three experiments in a row fail to improve, step back and reconsider your approach entirely.
- Track which ideas you've already tried to avoid repeating them.
- When comparing alternatives (libraries, algorithms), test them in isolation before combining.
