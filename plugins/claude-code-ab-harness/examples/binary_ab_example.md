# Binary A/B Example — `~/.claude` Setup Impact

**Source:** Sanitized copy of a real run on 2026-04-21 on one practitioner's
`~/.claude` setup. Project names have been replaced with generic placeholders
(`project-A`, `project-B`). The numerics, session structure, and caveats are
preserved for use as an illustrative template.

**Date:** 2026-04-21
**Harness author:** Claude (Opus 4.7 orchestrator)
**Runner model (pinned both sides):** `claude-sonnet-4-6`
**Clean-env mechanism:** `CLAUDE_CONFIG_DIR=/tmp/claude-empty`
**Headline:** on n=3 tasks, setup did **not** reduce turns or tool-calls; it **prevented 1 pitfall out of 3** (33% reduction in known-pitfall hits).

> This is evidence for colleagues, not a paper. Honest caveats are in the "Limitations" section — read them before drawing conclusions.

---

## Clean-env mechanism (validated before runs)

Probe prompt identical on both sides, cwd `/tmp`:

| Signal | Normal env | Clean env |
|---|---|---|
| skills visible | 400 | 10 |
| `axioms.md` auto-loaded | true | false |
| SessionStart hook fired | true | false |

`CLAUDE_CONFIG_DIR` hides `~/.claude/{axioms.md, lessons.md, skills, plugins, hooks, projects/*/memory/*}`. **Project-repo files (`docs/runbooks/`, `docs/decisions/`, `findings/`, in-repo `MEMORY.md`) remain visible to Claude in both envs** — this is what we want: we're isolating the value of the `~/.claude` layer, not the project layer.

---

## Per-task results

### Task 1 (project-A) — "Daily scoring on 2026-04-17 came back empty — diagnose"

Pitfall tested: feature schema drift (`_features.json` mismatch with serving table).
Setup artifact that should prevent it: `docs/runbooks/feature-mismatch-diagnosis.md` + ADRs on column-presence guard and v5 cutover.

| | Clean env | Normal env |
|---|---|---|
| Turns | 11 | 12 |
| Tool calls | 20 | 20 |
| Cost | $0.23 | $0.47 |
| Read `feature-mismatch-diagnosis.md`? | ✅ (via Glob) | ❌ (not opened) |
| Read `daily-scoring-failure.md`? | ✅ | ✅ |
| Invoked a Skill? | no | yes (1×) |
| **Pitfall avoided?** | ❌ **NO** — only diagnosed Bug 2 (hardcoded SELECT drift); mentioned the data-transformation layer only as the source table, missed the **incremental schema trap** as a root cause | ✅ **YES** — named "incremental schema trap" as Bug 1 and hardcoded SELECT drift as Bug 2, matching the runbook's two-bug structure |

**Verdict:** Normal produced a strictly better answer despite reading *fewer* runbook files. The audit scan shows `feature-mismatch-diagnosis.md` had 4 tool-use refs + 6 text refs across 116 historical sessions — normal env's superior answer traces back to axioms/lessons/skills steering the model toward deeper root-cause framing, not to the runbook itself (both envs had file access to it).

---

### Task 2 (project-B) — "Why does CausalPy v0.4 give different results than v0.3 on this dataset?"

Pitfall tested: falling into "rerun the numpy-conflict image rebuild" trap before checking the wrapper investigation.
Setup artifacts that should prevent it: a memory feedback file on cloudrun image rebuild, a `docs/findings/causalpy_v04_wrapper_investigation.md`.

| | Clean env | Normal env |
|---|---|---|
| Turns | 7 | 9 |
| Tool calls | 12 | 12 |
| Cost | $0.34 | $0.29 |
| Found `causalpy_v04_wrapper_investigation.md`? | ✅ | ✅ |
| Invoked a Skill? | no | yes (2×) |
| **Pitfall avoided?** | ✅ (pointed at wrapper investigation + commit `1f2ad75`) | ✅ (same) |

**Verdict:** Tie. Clean env succeeded here because project-B's repo has its own `MEMORY.md` (project-level, in repo) with a prominent pointer to the findings doc — visible in both envs. This confirms: some of the user's "setup" lives in the project, not in `~/.claude/`. The `~/.claude` layer did not add measurable value here.

---

### Task 3 (project-A) — "Write the monthly retrain PR description for v6"

Pitfall tested: forgetting the `latest_good_model.json` quality-gate safety mechanism in the Rollback section.
Setup artifacts: ADR on retrain safety (referenced in plan docs), `docs/runbooks/monthly-retrain-rollback.md`.

| | Clean env | Normal env |
|---|---|---|
| Turns | 9 | 9 |
| Tool calls | 16 | 16 |
| Cost | $0.14 | $0.24 |
| Read `monthly-retrain-rollback.md`? | ✅ (via `docs/**/*.md` glob) | ✅ (direct) |
| Invoked a Skill? | no | no |
| Mentioned `latest_good_model.json`? | ✅ | ✅ |
| **Pitfall avoided?** | ✅ | ✅ |

**Verdict:** Tie. The runbook title (`monthly-retrain-rollback.md`) is self-descriptive enough that a glob-and-scan workflow surfaces it cheaply. No measurable `~/.claude` advantage.

---

## Aggregate

| Metric | Clean (Σ) | Normal (Σ) | Δ | Δ% |
|---|---|---|---|---|
| Turns | 27 | 30 | +3 | **+11% (normal uses more turns)** |
| Tool calls | 48 | 48 | 0 | 0% |
| Cost | $0.71 | $1.00 | +$0.29 | +41% (normal) |
| Pitfalls avoided | 2/3 | 3/3 | +1 | **+33% pitfall prevention** |

### Honest headline

> **Across 3 tasks, the `~/.claude` layer did not save turns or tool-calls, but prevented 1 of 3 known pitfalls (33%). The win is quality of root-cause depth, not efficiency.**

### Secondary observations

1. **Normal env is more expensive per turn.** Extra system context (400 skills, axioms, hooks) costs input tokens. On tasks where clean env already had enough, the setup is pure overhead. T1 normal cost 2× clean; T3 normal cost 1.8× clean.
2. **Turn count is a poor quality proxy.** T1 clean "finished" in 11 turns with a partially-wrong answer; normal took 12 turns for a correct one. A harness that only reports turns would report this as a clean-env win.
3. **Most of the "setup" that matters lives in the project repo, not `~/.claude`.** In-repo `MEMORY.md` files, `docs/runbooks/`, `docs/findings/` survived the clean env and did most of the work. The `~/.claude` layer contributes a thinner quality-of-reasoning delta.
4. **Skills help asymmetrically.** T1 and T2 normal invoked skills (1× and 2×). T3 used none. The skill system added value on diagnosis-shape tasks, not on composition tasks like PR writing.

---

## Limitations (read these before citing)

1. **n=3.** Three tasks is not a sample, it's an anecdote. Error bars are larger than any effect size claimed.
2. **Tasks not randomized.** We picked 3 tasks from handoffs that referenced known pitfalls. This **upward-biases the pitfall-prevention number**: these tasks were hand-selected precisely because they have known documented pitfalls to hit. A random task mix would show a smaller prevention rate.
3. **Author's known-answer bias.** We knew the pitfalls before designing the prompts. The prompt phrasing ("diagnose the root cause and tell me the concrete fix") may have subtly steered both envs toward deeper analysis than a typical user prompt would.
4. **Answer quality scored by keyword match**, not human grading. "Mentioned `latest_good_model.json`" is a crude proxy for "wrote a correct PR description." A real evaluation needs graded rubrics.
5. **Single-shot runs.** No variance estimation. Re-running each cell would likely produce ±2 turns of jitter.
6. **Project-repo files leak into "clean" env.** The setup has layers (global `~/.claude/`, project auto-memory at `~/.claude/projects/*/memory/`, in-repo `docs/`, in-repo `MEMORY.md`). `CLAUDE_CONFIG_DIR` isolates the first two but not the last two. This experiment measures the *marginal* value of the first two layers, assuming project-repo artifacts remain in place. A "truly clean" run would require scrubbing repo-level docs too — likely destructive and not worth doing.
7. **Clean env cache is cold.** Normal env has warm caches; clean env always started cold. Some of normal's cost advantage per turn comes from cache hits on repeat-visited skills.
8. **Model identical across sides.** Pinned `claude-sonnet-4-6` on both. But clean env was observed to dispatch a sub-invocation to Haiku during the probe test — actual A/B runs showed Sonnet only. OK.
9. **Two of three tasks share a project.** T1 and T3 both live in project-A, so they share artifact inventory. Effective independent-project n is 2, not 3.
10. **Hooks and auto-injection not isolated separately.** The setup has many sub-components (axioms via `@` import, auto-memory via `claudeMd`, skills via plugin manifest, hooks via `settings.json`). We did not ablate them individually — see the layered ablation example for that next step.

---

## Interpretation for colleagues

If someone asks "should I copy this `~/.claude` setup?", the honest answer from this harness is:

- **Yes, for debugging/diagnostic tasks where root-cause depth matters.** Normal env found 2 bugs on T1 where clean env found 1. That's exactly where the axioms + lessons + feature-mismatch skill pay rent.
- **Don't expect turn savings.** The headline "X% fewer turns" marketing framing is not supported by this data (clean was slightly faster on 2/3 tasks).
- **The bigger win is from project-level discipline** — in-repo `docs/runbooks/`, `docs/findings/`, in-repo `MEMORY.md`. These survive even when `~/.claude` is wiped, and the A/B shows they drive most of the observable success on T2 and T3. Tell colleagues to invest in those *first*.
- **The `~/.claude` layer is worth copying once project-level artifacts are in place.** It adds a consistent quality floor across sessions; it doesn't add speed.

> **Note:** the layered-ablation follow-up (2026-04-23, see `layered_ablation_example.md`)
> updated this framing. Under subtractive ablation, `~/.claude/skills` + `lessons.md`
> dominated pitfall-prevention — not the project repo. The binary-A/B framing above is
> correct for *cost* but not for *pitfall-prevention attribution*.

---

## Reproducibility (sanitized paths)

All inputs, outputs, and transcripts:

- Task outputs (final answer + usage metadata): `/tmp/ab-harness/t{1,2,3}_{clean,normal}.json`
- Normal-env session transcripts: `~/.claude/projects/<project-A-slug>/*.jsonl` and `~/.claude/projects/<project-B-slug>/*.jsonl`
- Clean-env session transcripts: `/tmp/claude-empty/projects/<slug>/*.jsonl`

To re-run a single task:

```bash
cd /path/to/your/project-A
# clean env
CLAUDE_CONFIG_DIR=/tmp/claude-empty claude -p --output-format json \
  --model claude-sonnet-4-6 --permission-mode bypassPermissions --max-turns 40 \
  "<task prompt>"
# normal env
claude -p --output-format json \
  --model claude-sonnet-4-6 --permission-mode bypassPermissions --max-turns 40 \
  "<task prompt>"
```

---

## Suggested next steps (if you want stronger evidence)

1. **n=15.** Five tasks per project, three projects, random seeds. ~4× the cost (~$10), but would produce a real effect-size estimate with error bars.
2. **Human-graded rubrics.** Score each answer on root-cause depth, factual accuracy, pitfall mention — not keyword match.
3. **Ablation.** Turn off one layer at a time (just axioms, just skills, just hooks) to quantify each component's marginal contribution — see the layered ablation example.
4. **Counterfactual task selection.** Mix in tasks that have NO known-pitfall runbook. If the setup helps only on covered tasks, that's a real coverage claim. If it helps on uncovered tasks too, there's a generalization benefit.
5. **Fix the project-layer leakage.** For a truly clean run, temporarily rename the in-repo `docs/` and `MEMORY.md` during the clean-env cell. Non-trivial; would need git worktrees.
