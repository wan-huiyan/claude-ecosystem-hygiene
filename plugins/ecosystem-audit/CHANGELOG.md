# Changelog — ecosystem-audit

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
