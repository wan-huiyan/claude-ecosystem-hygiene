# claude-code-ab-harness

A counterfactual A/B + layered-ablation harness for the `~/.claude` setup. Answers
the question **"does my Claude Code setup actually help, or am I just collecting
dormant skills?"** with real numbers — turns, tool calls, cost, pitfall hits —
across matched task pairs.

> **Budget $10+ and 30 min – 3 hrs of wall time. This is a measurement
> experiment, not a lint.**

## When to use

This skill is **heavyweight**. Reach for it only after you've run the cheap
scans first.

| Question | Use this | Not this |
|---|---|---|
| "Which of my skills are actually getting referenced?" | `ecosystem-audit` (minutes, $0) | — |
| "Is my MEMORY.md bloated? Are axioms over Cowan's cap?" | `memory-hygiene` (seconds, $0) | — |
| "**Do the HOT artifacts from the audit translate into better answers?**" | **this plugin** ($10+, 30min–3hrs) | ecosystem-audit alone (reference counts ≠ quality) |
| "Which layer should a colleague copy first?" | this plugin (layered ablation flow) | — |

The reference-count signal from `ecosystem-audit` answers *which artifacts get
touched*. This harness answers *whether touching them actually changes the
output*. Those are different questions.

## Relationship to the other plugins in this marketplace

```
ecosystem-audit          →   claude-code-ab-harness    →   memory-hygiene
"what's HOT vs              "do the HOT artifacts         "prune what the
 DORMANT?"                   improve outcomes?"            harness showed
                                                           adds no value"
   ~minutes, $0                ~30min–3hrs, $10+             ~minutes, $0
```

- **ecosystem-audit** tells you utilization (8.9% of 394 skills invoked last 30
  days, say). That catches DORMANT artifacts. But a HOT artifact might still be
  noise — it gets touched and adds nothing.
- **this harness** runs the same tasks twice (setup-ON vs setup-OFF, or
  layer-by-layer strips) and reports whether the setup actually changes the
  answer. Only the harness can distinguish "HOT and useful" from "HOT and ritual."
- **memory-hygiene** uses the harness's ranked-contribution list to decide what
  to prune. If C8 (ADRs) had zero Δ-pitfall effect across n≥5 tasks, that's a
  concrete signal to consolidate the ADR tree.

## Two flows

### 1. Binary A/B — quickest path, measures global value

Run each task twice, once with full `~/.claude`, once with
`CLAUDE_CONFIG_DIR=/tmp/claude-empty`. Compare turns, tool calls, cost,
pitfall-keyword hits.

- **Cost:** ~$2 for n=3 tasks, ~$10 for n=15.
- **Wall time:** ~30 minutes for n=3.
- **What it tells you:** "On average, does the setup help?"
- **What it hides:** which sub-layer (axioms vs skills vs lessons vs project docs)
  did the work.

See [`examples/binary_ab_example.md`](examples/binary_ab_example.md) for a full
real-run write-up. Headline from that run: **on n=3, setup did NOT save turns
(27 clean vs 30 normal) but prevented 1 of 3 pitfalls (33%). The win is quality
of root-cause depth, not efficiency.**

### 2. Layered ablation — more expensive, ranks individual layers

Strip one layer at a time from a full-setup baseline (C0 = full, C1 = strip
`~/.claude/CLAUDE.md`, C2 = strip axioms, … C11 = strip everything). Rank
layers by (−Δ pitfalls, −Δ turns, Δ cost).

- **Cost:** ~$11 for 12 cells × 3 tasks at n=1 per cell; ~$33 at n=3 per cell;
  ~$80 if you want tight CIs at n≥5.
- **Wall time:** ~30 min with batch-6 parallelism; longer if you hit rate limits.
- **What it tells you:** "Which layer do I copy first?"
- **What it hides:** layer interactions (n=1 can't separate "axioms alone
  vs axioms + lessons").

See [`examples/layered_ablation_example.md`](examples/layered_ablation_example.md)
for a full real-run write-up. Headline: **on that setup, only skills+plugins
(−2/3 pitfalls) and lessons.md (−1/3) were measurable pitfall-loss strips; all
other layers (CLAUDE.md, axioms, auto-memory, runbooks, decisions, findings,
handoffs, plans) were zero-delta at n=1.** This contradicted the usual "copy my
CLAUDE.md first" framing.

## What to do with the results

Feed them back into `memory-hygiene`. If the ablation showed 8 of 10 layers had
zero measurable impact at n=1, those are concrete pruning candidates — not
because they're unused (they were referenced), but because the harness couldn't
detect an outcome change when they were removed. That's exactly the signal
`memory-hygiene` should consume when deciding what to consolidate or delete.

Bear in mind the limitations, especially at n=1: rank ties within noise, and
the task set upward-biases pitfall-prevention. See the "Limitations" section in
each example file.

## Installation

```bash
# Install the whole marketplace
claude plugin marketplace add wan-huiyan/claude-ecosystem-hygiene
claude plugin install claude-code-ab-harness@wan-huiyan-ecosystem-hygiene
```

Or copy directly:

```bash
git clone https://github.com/wan-huiyan/claude-ecosystem-hygiene.git /tmp/ceh
cp -r /tmp/ceh/plugins/claude-code-ab-harness ~/.claude/skills/
```

## Source of truth

**This directory in the marketplace is canonical for this plugin.** Unlike
`memory-hygiene` (which auto-syncs from its own upstream repo), the A/B harness
has no separate upstream — edit here and push here. No cross-repo sync job is
needed.

## Quickstart

**Step 1 — verify the clean-env mechanism before spending a cent:**

```bash
mkdir -p /tmp/claude-empty
CLAUDE_CONFIG_DIR=/tmp/claude-empty claude -p --output-format json \
  "Reply JSON: {has_axioms: <bool>, num_skills_visible: <int>, session_start_hook_fired: <bool>}" \
  < /dev/null
```

You should see ~10 skills visible, `has_axioms: false`, `session_start_hook_fired: false`. If not, your shell alias or function is swallowing the env var — read the skill's "Notes" section.

**Step 2 — pick tasks with known pitfalls** (the `ecosystem-audit` HOT list is where to start).

**Step 3 — run each task on both envs with model pinned, `< /dev/null`, `--permission-mode bypassPermissions`, `--max-turns 40`.**

**Step 4 — mine the session JSONLs** at `$CCDIR/projects/<slug>/<session_id>.jsonl` for tool-call histograms, files-read lists, pitfall keyword hits.

**Step 5 — build the comparison table, always with caveats attached.**

Full details, orchestration pitfalls (JSONL truncate races, `wait -n`
portability, rate-limit stub detection, idempotent skip checks), and the
layered-ablation shadow-dir mechanism are in [`SKILL.md`](SKILL.md).

## Quality checklist

- [x] **No client data.** Examples use generic `project-A` / `project-B` placeholders. All personal paths (`/Users/...`, `~/Documents/<real-project>`) removed.
- [x] **Numbers preserved.** The 2026-04-21 binary A/B (27/30 turns, 1/3 pitfall) and 2026-04-23 layered ablation (C4 −2/3, C3 −1/3) are quoted as-is.
- [x] **Heavyweight expectation bolded** at the top of the README.
- [x] **Relationship to sibling plugins** explicit (audit → measure → clean).
- [x] **Example outputs linked**, not just referenced.
- [x] **Canonical plugin layout.** `plugin.json` in `.claude-plugin/`, `SKILL.md` at root, `examples/` alongside.
- [x] **MIT licensed.** Free to fork, modify, redistribute.

## Limitations

- **Heavyweight.** Not for quick checks. Budget accordingly.
- **n=3 is a pilot.** Don't cite results from small-n runs as proof.
- **Pitfall grading is keyword-match by default.** A human rubric would be stricter; swap in one if stakes are high.
- **Project-repo files leak into the "clean" env.** `CLAUDE_CONFIG_DIR` isolates 4 of 6 setup layers. The harness measures the *marginal* value of the first 4, not the total setup.
- **Task selection bias.** If you pick tasks with known pitfalls (you'll want to — it's the only way to get signal), that upward-biases the pitfall-prevention number. Randomize or run an uncovered control set to check generalization.
- **Layered ablation at n=1** ranks tightly only at the top; layers 3+ are within noise.

## License

MIT. See the repo root [LICENSE](../../LICENSE).
