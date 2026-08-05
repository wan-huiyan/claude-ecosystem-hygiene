# Changelog — ecosystem-audit

## v1.2.2 — 2026-08-04

### Fix: description was over the skill-listing cap since v1.0.0 (159 chars invisible)

**Problem.** Claude Code caps each model-invocable skill's listing entry at
`skillListingMaxDescChars` (default 1536, read from the v2.1.221 binary) and truncates by
keeping `full[:1535]` plus an ellipsis — no intelligent summarisation, no warning. This
skill's description has been **1694 chars since the very first commit** (`bd256ab`,
2026-04-17, "feat: initial marketplace release with 3 plugins"), so the last **159 chars were
never once seen by the model**. What was silently dead:

- `…cross-category coverage that neither provides alone.`
- **`Use this proactively whenever the user describes ANY ecosystem-level symptom, even if they
  don't explicitly ask for an "audit".`** — the entire proactive-invocation instruction, which
  is the single sentence most responsible for the skill firing without being named.

> **159, not 158.** The harness keeps `full[:cap-1]`, so the dead tail is
> `len(desc) - (cap - 1)`, not `len(desc) - cap`. The gate under-reported every over-cap
> skill by exactly one character until the off-by-one was fixed in context-police v2.2.0;
> this entry quotes the corrected figure.

**Fix.** Retrimmed to **1495 chars (41 under cap)**. Trigger vocabulary was preserved and
extended; only prose and implementation detail were cut.

- **Kept every quoted trigger phrase, including `"what needs cleanup"`.** An earlier cut of
  this trim dropped that one as "a synonym of `clean up my ecosystem` / `audit my setup`";
  `check_skill_descriptions.py --compare` reported it as `DROPPED`, and since it fits, it is
  back. Deleting a phrase outright is invisible to the gate's `lost_triggers` count, which by
  construction only counts phrases lost to *truncation*.
- Added trigger surface that eval prompts relied on but the description lacked: `lessons`,
  `feedbacks`, `ADRs`, `docs` in the opening scope line, `"give me a cleanup script"`, and
  `"regenerate my stale audit"`.
- Cut prose and implementation detail: `dark-themed`, `6 categories`, `health percentages`,
  `ready-to-run`, `radar chart`, and the per-category list inside the report sentence (every
  category name it held already appears in the opening scope line).
- **Kept the sibling-skill positioning**, compressed: `schliff:doctor (per-skill quality)` and
  `memory-hygiene (knowledge store)` are still named. That sentence is the only text saying
  what this skill is *not*, and it is the disambiguator in an install where those two are also
  present. See the measurement caveat below — the eval cannot price it.
- The proactive-invocation sentence now fits and is live for the first time.

**Measured against `evals/trigger_eval.json`** (10 positive / 10 negative prompts), word-overlap
coverage. Baseline is `old_description[:1535]` — what the model actually read, not the full
source. **Reproduce with the committed harness:**

```
python3 plugins/ecosystem-audit/scripts/score_trigger_coverage.py \
    --old  af97fee:plugins/ecosystem-audit/SKILL.md \
    --new  ebb228a:plugins/ecosystem-audit/SKILL.md \
    --eval plugins/ecosystem-audit/evals/trigger_eval.json
```

> **Refs pinned 2026-08-05.** This block originally read `--old main:… --new <worktree>`,
> which was correct only while the trim was unmerged. Once #14 landed, `main` *became* the
> post-trim state and the same command printed `0.5198 → 0.5198` — every delta zero, the
> table apparently refuted by its own reproduce line. Both sides are now pinned to commits:
> `af97fee` is the pre-trim parent, `ebb228a` the merge. Both tables below still reproduce to
> four decimals, and the harness prints **both** stopword variants in one run.

| metric | before (truncated) | after | Δ |
|---|---|---|---|
| positive mean coverage | 0.4968 | 0.5198 | **+0.0230** |
| negative mean coverage | 0.1917 | 0.2042 | +0.0125 |
| separation (pos − neg) | 0.3051 | 0.3156 | **+0.0105** |

Per-prompt: **4 better / 6 same / 0 worse** on positives.

Word overlap is stopword-list sensitive, so the harness prints an unfiltered run too, and
both are reported here rather than only the flattering one:

| metric (no stopword filter) | before | after | Δ |
|---|---|---|---|
| positive mean coverage | 0.5422 | 0.5650 | **+0.0228** |
| negative mean coverage | 0.2988 | 0.3209 | +0.0221 |
| separation (pos − neg) | 0.2434 | 0.2441 | +0.0007 |

Positives are **4 better / 6 same / 0 worse** under both variants, so the positive-side result
does not depend on the stopword list. Separation is the fragile number: it widens clearly with
the filter and only marginally without it.

> **Retraction.** v1.2.2's first draft quoted `0.4291 → 0.4525`, `0.2104 → 0.1937`,
> `0.2187 → 0.2588` from a scoring script that was never committed. Those figures are
> withdrawn: they are not reproducible from this repo, and a reviewer using a different
> stopword list reproduced the direction but not the values. The numbers above come from
> `scripts/score_trigger_coverage.py`, which is now in the tree.

**What this measurement cannot see.** It scores one description against prompts *in isolation*,
with no competing skill present, so removing a sibling skill's name can only ever register as a
precision win. The negative prompt *"run schliff:doctor on my installed skills…"* moves
0.625 → 0.750 here precisely *because* the `schliff:doctor` name was kept. Read that as the
cost of keeping a real disambiguator, not as a regression — in an install where
`schliff:doctor` exists, that name is what stops this skill from firing on it. Word overlap is
also blind to trigger-condition restructuring; `check_skill_descriptions.py --compare` reports
**0 DROPPED, 0 NARROWED** for this trim.

**The cap is necessary, not sufficient.** Being under `skillListingMaxDescChars` means this
description is *no longer truncated*. It does not mean it is visible:
`skillListingBudgetFraction` (1% of the context window) is a budget shared across *every*
installed skill, and when the listing exceeds it the harness collapses descriptions to bare
names by usage rank, not by length.

No behavioural change to the audit itself; body and report template are untouched. New
`scripts/score_trigger_coverage.py` (measurement only — the gate is
`.github/scripts/check_skill_descriptions.py`).

## v1.2.1 — 2026-06-01

*Backfilled 2026-08-05: this release shipped in `d556709` and was never given a CHANGELOG
entry, leaving a gap between v1.2.0 and v1.2.2.*

Recalibrate the `memory-hygiene` version pin from v3.0 to v3.3. The pin's baseline
parenthetical still named v3.0. Verified the delegated interface (Phase 1 Discover +
Phase 1h ADRs / MADR 4.0) is intact in v3.3, so the major-version pin still passes; this
updates the stale calibration baseline to the verified-compatible current version. No
behavioural change.

## v1.2.0 — 2026-04-25

### Change A: A/B-evidence-backed T1 promotion

**Motivation:** The v3 layered ablation (240 cells, n=15) found that high reference count
alone does not predict A/B contribution. `lessons.md` was the highest-ref layer in the study
but its Δ vs the no-op control cell (C6) was within noise. `skills+plugins` (cell C4), with
lower ref count, cleanly separated from the noise floor: pitfall-avoided rate dropped from
80% to 43% when stripped. Reference count is a starting point, not a verdict.

**New behavior:**
- T1 now means "evidence-backed load-bearing," not "frequently referenced."
- T1 layers must supply one of:
  - `ab_evidence.delta_vs_noop_se >= 1.0` — A/B-harness result above the noise floor
  - `evidence: "reference-count-only"` — explicit disclaimer that surfaces in the report
- `score_health.py` emits a `t1_warnings` list for layers missing both.
- The audit report must display warnings — a silently-promoted T1 erodes tier trust.
- Backward compatible: layers without either field generate a warning but do not fail scoring.

**Cross-reference:** ab-harness v1.2.0 §"Noise floor: design a no-op cell" and
§"C11 saturation: everything-stripped ties the no-op control."

### Change B: Correctness-vs-latency annotation per skill layer

**Motivation:** v3 ablation cell C4 (`skills+plugins`) was simultaneously the most impactful
layer on pitfall-prone tasks AND the fastest cell on generic tasks (7.2 turns / $0.30 vs
baseline C0's 18.8 turns / $0.57). This means skills add overhead on routine work — a
blanket "install more skills" recommendation is harmful for users whose task mix is primarily
generic.

**New behavior:**
- Each skill-type layer in the audit now carries:
  - `latency_cost`: `unmeasured` | `low` (<1 turn) | `medium` (1–3 turns) | `high` (>3 turns)
  - `trigger_surface_match`: `matched` | `mismatched` | `unmeasured`
- Mismatch definition: `ref_count > 10` AND `delta_vs_noop_se < 1.0 SE`. The skill appears
  frequently in session logs but does not measurably reduce pitfalls on the measured workload.
- New report section: **"Skills with mismatched trigger surface"** — lists each mismatched
  skill with ref_count, A/B signal, latency cost, and remediation options.
- Recommendation engine updated: mines session prompts for dominant task-type patterns before
  recommending skills; flags high-ref / low-signal skills as "noise."

**Note on regex-OR grading:** v3 also found that regex-OR keyword grading over-calls hits
~3× (50% agreement with LLM rubric on n=16 sample). True absolute pitfall rates are roughly
half the headline; rankings hold but are noisy. `unmeasured` is an honest annotation when
no LLM-rubric A/B data is available.

---

## v1.1.0 — 2026-04-17

Memory subagent now delegates to memory-hygiene Phase 1 (single source of truth; prevents
drift). T1.5 tier coverage added (`~/.claude/templates/phase_*.md` + `.claude/rules/phase-*.md`
with `paths:` glob validity). Axiom health checks classification (Universal/Role/Phase), not
just count vs Cowan cap. Staleness expanded from 2 to 4 signals + agency-aware detection via
`user_role.md`. Radar chart renders `N/A` with hatched pattern when sub-checks can't compute
(no fabricated scores). Memory weighting rebalanced to 6 inputs (25/15/15/10/20/15).

## v1.0.0 — 2026-04-16

Initial release. Full-coverage audit across 9 artifact categories (skills, memory, handoffs,
ADRs, plans, reviews, worktrees, automation, provenance). Parses JSONL session logs for real
skill invocation data. Produces interactive HTML report with radar chart and prioritized
P0/P1/P2 cleanup actions.

> **Correction (2026-08-05).** That category list was wrong on the day it was written and
> was copied into both READMEs. `provenance` appears **zero** times in `SKILL.md`, and
> `automation` only in an unrelated P0 example; neither has ever been a scanned category.
> The nine are **skills, memory, handoffs, ADRs, plans, reviews, findings, tasks,
> worktrees** — see `SKILL.md`'s scoring section, where `Docs` is defined as
> `plans + reviews + findings + tasks`. They score on **6** radar axes because those four
> roll up into one `Docs` axis, which is why "9 categories" and "6 axes" were both correct
> and looked contradictory.
