---
name: claude-code-ab-harness
description: |
  Run a counterfactual A/B harness on Claude Code to measure whether the user's
  ~/.claude setup (memories, lessons, axioms, skills, hooks, plugins) actually helps
  on real tasks vs. a blank-canvas env. Use when: (1) User wants to "prove my setup
  works" or "quantify setup impact" to colleagues; (2) User asks "is my setup actually
  helping" beyond what ecosystem-audit's reference-count scan can show; (3) A
  project has the counterfactual measurement step of an audit → measure → clean
  pipeline queued. Covers the clean-env mechanism (CLAUDE_CONFIG_DIR), what it does
  and doesn't isolate, fair-comparison knobs (model pinning, permission mode, stdin),
  how to mine num_turns/tool_calls/pitfall-hits from the resulting JSONL transcripts,
  and the honest caveats any n=3 harness report must declare.
author: wan-huiyan (Claude-assisted, from 2026-04-21 binary A/B session; layered-ablation extensions 2026-04-23)
version: 1.1.0
date: 2026-04-23
---

# Claude Code A/B Counterfactual Harness

## Problem

The user wants to quantify whether their accumulated `~/.claude/` setup (axioms,
lessons, skills, plugins, hooks, auto-memory) *actually helps* on representative
tasks, not just whether artifacts get referenced (that's `ecosystem-audit`'s job).

Naive attempts fail because:
- The default Claude Code run pulls the full `~/.claude` context — there's no obvious
  switch to "turn the setup off."
- Simply `cd`-ing to a different project doesn't help — global axioms/skills still
  load.
- Even with a clean env, the *project repo's* `docs/runbooks/`, `docs/findings/`,
  and in-repo `MEMORY.md` stay visible — the harness must either accept that
  leakage (measure *marginal* ~/.claude value) or scrub repo files too.

## Context / Trigger Conditions

- User has completed the `ecosystem-audit` scan (utilization %) and wants the
  **counterfactual** number next ("setup saved X turns / prevented Y pitfalls").
- User says "I want to show colleagues my setup works," "quantify the setup,"
  "A/B test my Claude setup," "replay a task without my memory."
- A project plan references a counterfactual harness step — the canonical
  measurement stage after (1) usage audit and (2) before (3) cleanup.
- User asks whether a specific skill / lesson / axiom pulls its weight on real work.

## Solution

### Step 1 — Verify the clean-env mechanism before spending a cent

The knob is `CLAUDE_CONFIG_DIR`. Point it at an empty dir:

```bash
mkdir -p /tmp/claude-empty
CLAUDE_CONFIG_DIR=/tmp/claude-empty claude -p --output-format json \
  "Reply JSON: {has_axioms: <bool>, num_skills_visible: <int>, session_start_hook_fired: <bool>}" \
  < /dev/null
```

Expected diff vs a normal run (same probe, no env var):

| Signal | Normal | Clean (`CLAUDE_CONFIG_DIR=/tmp/claude-empty`) |
|---|---|---|
| skills visible | hundreds | ~10 (defaults only) |
| axioms auto-loaded | true | false |
| SessionStart hook fired | true | false |
| project auto-memory (`~/.claude/projects/*/memory/MEMORY.md`) | injected | empty |

**What it does NOT isolate** (important for caveats):
- Files in the **project repo** — `docs/runbooks/`, `docs/decisions/`, `findings/`,
  in-repo `MEMORY.md`. Claude can still `Read`/`Glob` them. This is usually what
  you want (you're measuring the marginal value of `~/.claude`, not rebuilding the
  project from scratch), but call it out in the report.

### Step 2 — Pick tasks that actually test the setup

Pitfall: picking random tasks dilutes the signal. Pitfall-prevention effects show up
only on tasks where the setup has **documented guidance for a specific trap**. Use
the `ecosystem-audit` output:

1. List HOT artifacts (top 20% by ref count).
2. For each, find the **failure mode** it was written to prevent. Check commit
   messages, associated ADRs, the "Why this exists" section.
3. Construct a task prompt that would *naturally* hit that failure mode. Good
   prompts are plausible, not leading ("Diagnose why X broke" beats "Check the
   feature-mismatch runbook before diagnosing X").

Target n≥5 tasks for a real effect-size estimate. n=3 is a pilot; call it evidence,
not proof.

### Step 3 — Pin the knobs for a fair run

```bash
cd /path/to/your/project_repo

# NORMAL env
claude -p --output-format json \
  --model claude-sonnet-4-6 \
  --permission-mode bypassPermissions \
  --max-turns 40 \
  "<task prompt>" \
  < /dev/null \
  > /tmp/ab-harness/tN_normal.json 2>&1

# CLEAN env — same cwd, same model, same flags
CLAUDE_CONFIG_DIR=/tmp/claude-empty \
  claude -p --output-format json \
  --model claude-sonnet-4-6 \
  --permission-mode bypassPermissions \
  --max-turns 40 \
  "<task prompt>" \
  < /dev/null \
  > /tmp/ab-harness/tN_clean.json 2>&1
```

Critical knobs and **why**:

- `--model claude-sonnet-4-6` (or whichever model, pinned explicitly) — different
  `CLAUDE_CONFIG_DIR` values can default to different models. Unpinned comparison is
  worthless. Use Sonnet for cost, not Opus, unless cost is no constraint.
- `--permission-mode bypassPermissions` — clean env has no preauthorized permissions;
  without this, it will stall on every Bash/Write.
- `< /dev/null` — prevents the "Warning: no stdin data received in 3s" 3-second
  stall that otherwise adds jitter to every run.
- `--max-turns 40` — caps runaways. Default is higher; don't rely on it.
- `--output-format json` — gives `num_turns`, `duration_ms`, `session_id`,
  `total_cost_usd`, `is_error` in one line. Essential for the aggregate table.
- **Run from the project repo cwd**, not `~/` or `/tmp`. The project's auto-memory
  at `~/.claude/projects/<slug>/memory/MEMORY.md` is keyed on cwd.

### Step 4 — Mine the session JSONLs for real metrics

`--output-format json` gives you turn count and cost. For tool-call breakdown and
files-read lists, parse the session JSONL written by Claude Code itself:

```bash
# Normal env JSONLs
~/.claude/projects/<cwd-slug>/<session_id>.jsonl

# Clean env JSONLs (under the alt config dir)
/tmp/claude-empty/projects/<cwd-slug>/<session_id>.jsonl
```

Tool-call histogram:
```bash
jq -r 'select(.message.content != null) | .message.content[]? |
  select(.type=="tool_use") | .name' "$JSONL" | sort | uniq -c | sort -rn
```

Files read:
```bash
jq -r 'select(.message.content != null) | .message.content[]? |
  select(.type=="tool_use" and .name=="Read") | .input.file_path' "$JSONL" | sort -u
```

Skills invoked:
```bash
jq -r 'select(.message.content != null) | .message.content[]? |
  select(.type=="tool_use" and .name=="Skill") | .input.skill' "$JSONL"
```

Pitfall keyword scan in assistant output:
```bash
jq -r 'select(.message.role=="assistant") | .message.content[]? |
  select(.type=="text") | .text' "$JSONL" | grep -iE "<pitfall-phrase>"
```

### Step 5 — Build the comparison table

Per task:

| | Clean | Normal |
|---|---|---|
| Turns | X | Y |
| Tool calls | X | Y |
| Cost | $X | $Y |
| Pitfall avoided? (specific keyword / behavior) | ✅/❌ | ✅/❌ |
| Skills invoked? | list | list |

Aggregate:

| Metric | Σ Clean | Σ Normal | Δ |
|---|---|---|---|
| Turns | ... | ... | ... |
| Tool calls | ... | ... | ... |
| Pitfalls avoided | a/n | b/n | +(b-a) |

### Step 6 — Mandatory caveats for the report

These are not optional. If you publish an A/B harness report without them, you're
misleading colleagues:

1. **n** — state it prominently. n=3 is a pilot, not a measurement.
2. **Task selection not randomized** — you picked tasks that have known pitfalls.
   This upward-biases pitfall-prevention. Honest mitigation: run on 2-3 additional
   "uncovered" tasks to check generalization.
3. **Author's known-answer bias** — you knew the pitfalls when writing prompts.
   Prompt phrasing could cue deeper analysis.
4. **Project-repo files leak into clean env.** `CLAUDE_CONFIG_DIR` isolates 4 of
   the 6 setup layers (global CLAUDE.md imports, global skills, global hooks,
   project auto-memory). It does NOT isolate in-repo `docs/` or in-repo `MEMORY.md`.
   The harness measures the marginal value of the first 4 layers, not the total
   setup. Say so.
5. **Turn count is a weak quality proxy.** A clean env can "finish" fast with a
   partially-wrong answer. Pair turn count with a pitfall-hit or human rubric check.
6. **Model pinning done** (call it out). Note both envs used the same model.
7. **Single shot, no variance estimate.** ±2 turns of jitter per cell is typical.
8. **Normal env cache is warm, clean is cold.** Some normal-env cost advantage per
   turn comes from cache hits on repeat-visited skills, not the model working harder.

## Verification

The harness "worked" if:
- The probe (Step 1) shows a measurable diff in skills/axioms/hook signals between
  envs. If the clean env still reports `has_axioms: true` or ~400 skills, you've
  misconfigured `CLAUDE_CONFIG_DIR` (check the env var actually reached the claude
  subprocess — shell aliases/functions can strip it).
- Every task's JSONL has `num_turns > 0` and `is_error: false`. Errored runs don't
  count.
- The report includes a per-task table, an aggregate table, and the full caveats
  list. Headline numbers without caveats are worse than no report.

## Example (real run, 2026-04-21)

A 3-task binary A/B on a real user's setup produced these numbers
(full sanitized report at [`examples/binary_ab_example.md`](examples/binary_ab_example.md)):

- Setup **did not** save turns (27 clean vs 30 normal) or tool-calls (48 vs 48).
- Setup **prevented 1 of 3 pitfalls** (33%). Specifically on a diagnostic task, only
  the normal env identified both cascading root causes; clean env found only the
  surface bug.
- Normal env cost ~1.4× per task (extra input-token overhead from axioms + skills
  list). On tasks clean can already handle, the setup is pure overhead.

The honest framing to colleagues from that run: *"Setup adds a quality floor on
diagnostic tasks, not speed. Most of the value comes from project-repo discipline
(docs/runbooks/ etc.), not from ~/.claude."*

## Layered ablation (v1.1+)

The binary A/B measures "setup ON vs OFF." That confounds every `~/.claude` + in-repo
layer into one treatment and is uninformative about *which* sub-layer earned its keep.
For the adoption question ("what should I copy first?"), run a **subtractive layered
ablation** — strip one layer at a time from a full-setup baseline.

### Cell design (12 cells per task, n=1 per cell)

| Cell | Strip | Mechanism |
|---|---|---|
| C0 | Nothing (control) | Real env |
| C1 | `~/.claude/CLAUDE.md` | Shadow dir, replace with empty stub |
| C2 | `~/.claude/axioms.md` | Shadow dir, file absent |
| C3 | `~/.claude/lessons.md` | Shadow dir, file absent |
| C4 | `~/.claude/{plugins,skills,marketplaces}` | Shadow dir, dirs absent |
| C5 | `~/.claude/projects/<slug>/memory` | Shadow dir, per-project auto-memory absent |
| C6 | In-repo `MEMORY.md` | Git worktree, repo-root file removed |
| C7 | In-repo `docs/runbooks/` | Worktree without runbooks |
| C8 | In-repo `docs/decisions/` | Worktree without ADRs |
| C9 | In-repo `docs/findings/` | Worktree without findings |
| C10 | In-repo `docs/handoffs/`+`docs/plans/` | Worktree without these dirs |
| C11 | **Everything** (empty CCDIR + stripped worktree) | Truly-clean lower bound |

### Shadow-dir mechanism

Don't `cp -a ~/.claude` — 1GB of session transcripts makes 12 copies wasteful. Instead:
- Symlink every top-level entry in `~/.claude/*` into the shadow dir **except** `projects/`.
- Recreate `projects/` as a real dir; for each project inside, make a real dir and
  symlink *only* the `memory` subdir (so the subprocess's session JSONL writes land
  in the isolated shadow, not the real `~/.claude/projects/`).
- **Copy `~/.claude.json` into the shadow dir** (not symlink) — the CLI mutates this
  file during startup. If missing, CLI errors "Claude configuration file not found at…".
- For C1–C5, run the specific `rm`/stub operation on the target file or dir.

```bash
setup_shadow() {
    local DST="$1"
    rm -rf "$DST"; mkdir -p "$DST"
    for entry in ~/.claude/*; do
        bname=$(basename "$entry")
        [ "$bname" = "projects" ] && continue
        ln -s "$entry" "$DST/$bname"
    done
    mkdir -p "$DST/projects"
    for proj in ~/.claude/projects/*; do
        pname=$(basename "$proj")
        mkdir -p "$DST/projects/$pname"
        [ -d "$proj/memory" ] && ln -s "$proj/memory" "$DST/projects/$pname/memory"
    done
    [ -f ~/.claude.json ] && cp ~/.claude.json "$DST/.claude.json"
}
```

### Worktree mechanism for project-layer strips (C6–C10)

```bash
git -C "$REPO" worktree add -f "$WT_PATH" -b "ablation-c$N" HEAD
rm -rf "$WT_PATH/docs/runbooks"   # or the relevant dir for the cell
# Subprocess runs with cwd=$WT_PATH
```

Note: macOS resolves `/tmp/` → `/private/tmp/`, so the auto-memory slug under
`$CCDIR/projects/` becomes `-private-tmp-ablation-wt-<name>-c$N`, not
`-tmp-ablation-wt-<name>-c$N`. Account for this when parsing JSONLs.

### Marginal contribution = Cn − C0

Negative Δ pitfalls = removing the layer made the answer miss a pitfall.
Negative Δ turns usually means "model finished faster with a shallower answer"
(the pitfall column is the quality check, not turn count).

### Rank layers by (−Δ pitfalls, −Δ turns, Δ cost)

The ranking directly answers "what should I copy first?" On one real setup
(2026-04-23 run), only **skills/plugins (−2/3) and lessons.md (−1/3)** were
strips with measurable pitfall loss at n=1; every other layer was a draw. This
contradicted the binary A/B's qualitative framing ("project repo does most of
the work"). The binary framing was correct for project-repo cost but not for
pitfall-prevention attribution.

Cost: 36 runs × ~$0.30 ≈ $11, ~30 min wall time at batch-size-6 parallelism.
Sanitized artifacts from that run: [`examples/layered_ablation_example.md`](examples/layered_ablation_example.md).

## Orchestration pitfalls (bit the 2026-04-23 run — cost +$5 in re-runs)

### 1. Parse the JSONL, not the CLI output file

`claude -p --output-format json > out.json` opens the output file with **truncate
semantics**. If two subprocesses race on the same output path (e.g., a duplicate
launch from a buggy orchestrator), the later launch zeros the file at open time
even if the first run's content hasn't been written yet. The first run's summary
is lost.

The session JSONL at `$CLAUDE_CONFIG_DIR/projects/<slug>/<session_id>.jsonl` is
per-session, append-only, and survives concurrent launches. For any harness you
might re-run, treat the JSONL as the ground truth and the CLI output as a
convenience summary. Reconstruction from JSONL:

- `turns ≈ tool_call_count + 2` (calibrated within ±1 on a control cell; conversation
  turns = user prompt + tool-use cycles + final answer)
- `cost = input_tok × $3/Mtok + output_tok × $15/Mtok + cache_creation × 1.25 × $3/Mtok
  + cache_read × 0.1 × $3/Mtok` (Sonnet 4.6 pricing; within ~10% of authoritative CLI total)
- Tool calls, skills invoked, pitfall keyword hits: parse directly from JSONL records

### 2. `wait -n` is not portable

On macOS bash 3.2 (and some older Linux bashes), `wait -n` inside a `for` loop returns
*silently when no jobs are currently tracked in the parent's jobs table*. Backgrounded
children can detach from the job table before `wait -n` is called, making the loop
launch everything at once instead of batching.

Use explicit PID tracking or a mature tool:

```bash
# Explicit batch
batch_pids=()
for pair in "${work[@]}"; do
    run_cell "$pair" &
    batch_pids+=($!)
    if [ "${#batch_pids[@]}" -ge "$BATCH" ]; then
        for pid in "${batch_pids[@]}"; do wait "$pid"; done
        batch_pids=()
    fi
done
for pid in "${batch_pids[@]}"; do wait "$pid"; done
```

Or `xargs -P $N` / `parallel -j $N`. Don't rely on `wait -n`.

### 3. Detect rate-limit stubs before trusting re-run outputs

A rate-limit error from the CLI writes this shape to the output file:

```json
{"is_error": true, "num_turns": 1, "total_cost_usd": 0,
 "result": "You've hit your limit · resets HH:MMam/pm (<tz>)",
 "api_error_status": 429, "stop_reason": "stop_sequence", ...}
```

If your orchestrator re-runs cells and gets this, it has **destroyed a prior
good run**. Add a detector:

```bash
is_rate_limit_stub() {
    local f="$1"
    jq -e '.is_error == true and .num_turns <= 1 and .total_cost_usd == 0' "$f" >/dev/null 2>&1
}
```

When detected, recover from the session JSONL (see #1). Do not simply re-run — you'll
hit the same rate limit and make the problem worse.

### 4. Idempotent skip check

Orchestrator skip logic must treat "file exists AND has valid session_id AND is not a
rate-limit stub" as "already done":

```bash
already_done() {
    local f="$1"
    [ -f "$f" ] && jq -e '.session_id' "$f" >/dev/null 2>&1 && ! is_rate_limit_stub "$f"
}
```

## Notes

- **Shell cwd persistence:** the Claude Code `Bash` tool preserves cwd across calls,
  but if you run `Bash` and observe a `Shell cwd was reset to …` message, cwd *was*
  reset. Always chain `cd /path && claude …` in the same Bash call for A/B runs
  where cwd matters. Do not rely on an earlier `cd` sticking.
- **Shell aliases that inject flags:** on some setups, `claude` is a zsh function
  that appends custom flags. To bypass, use `command claude …`. Check `type claude`
  first.
- **Killing orphaned runs:** each Claude subprocess forks child `bash`/`jq`
  processes. `TaskStop` on the outer Bash task is enough; the subprocess tree dies
  with SIGPIPE when stdout closes.
- **Cost budgeting:** per-task Sonnet run is ~$0.15–$0.50 depending on tool calls.
  n=3 × 2 envs ≈ $2. n=15 × 2 envs ≈ $10. The cost is not the bottleneck; task
  selection and caveat rigor are.
- **Project-layer isolation** (advanced): for a truly clean run, `git stash` the
  in-repo `docs/` and `MEMORY.md`, run the clean cell, then `git stash pop`. Only
  do this if the claimed A/B result depends on it — usually not worth the risk.
- **Integrates with `ecosystem-audit`:** that skill tells you *which* artifacts
  are HOT (getting referenced). This harness tells you whether those references
  *translate into better answers*. The two together are the full utility story.

## References

- Claude Code CLI `--output-format json` shape — inspect any `tN_*.json` for keys
- Session JSONL format — `~/.claude/projects/<slug>/<session_id>.jsonl`, one JSON
  object per line, `.message.content[].type` ∈ {`text`, `tool_use`, `tool_result`}
- `ecosystem-audit` skill (sibling plugin in this marketplace) — companion
  utilization-scan skill, sits upstream of this harness in the audit → measure → clean
  pipeline
- Example run artifacts (sanitized): [`examples/binary_ab_example.md`](examples/binary_ab_example.md)
  and [`examples/layered_ablation_example.md`](examples/layered_ablation_example.md)
