# Layered Ablation Example — `~/.claude` + project-repo setup

**Source:** Sanitized copy of a real run on 2026-04-23 on one practitioner's
setup. Project names have been replaced with generic placeholders
(`project-A`, `project-B`). The numerics, cell deltas, and limitations are
preserved for use as an illustrative template.

**Date:** 2026-04-23
**Harness author:** Claude (Opus 4.7 orchestrator, Sonnet 4.6 runners)
**Design:** 12 cells × 3 tasks = 36 runs, n=1 per cell (ranked-list experiment, not a statistical test).
**Reference task set:** same 3 tasks as the binary A/B (`binary_ab_example.md`) for comparability.
**Headline:** Only two strips caused measurable pitfall-prevention loss — **C4 (skills + plugins, −2/3 pitfalls)** and **C3 (lessons.md, −1/3)**. Every other layer (CLAUDE.md, axioms, auto-memory, runbooks, decisions, findings, handoffs, plans) was a zero-delta strip at n=1 against this task set. This contradicts the usual "copy my CLAUDE.md first" framing.

> See the "Limitations" section for honest caveats. n=1 per cell is *evidence*, not proof — the ranking of layers 3+ is within noise.

---

## Cells (what each strip removes)

| # | Cell | Strip target |
|---|---|---|
| C0 | **Full setup (control)** | Nothing — full user environment |
| C1 | Strip `~/.claude/CLAUDE.md` | Shadow dir, CLAUDE.md → empty stub |
| C2 | Strip `~/.claude/axioms.md` | Shadow dir, axioms.md absent |
| C3 | Strip `~/.claude/lessons.md` | Shadow dir, lessons.md absent |
| C4 | Strip `~/.claude/{plugins,skills}` | Shadow dir, plugin + skill dirs absent (no `marketplaces/` in this user's env) |
| C5 | Strip `~/.claude/projects/<slug>/memory` | Shadow dir, per-project auto-memory absent |
| C6 | Strip in-repo `MEMORY.md` | Worktree, repo-root `MEMORY.md` removed (neither project has this file → effective no-op for this user) |
| C7 | Strip in-repo `docs/runbooks/` | Worktree without runbooks (project-A only — project-B has none) |
| C8 | Strip in-repo `docs/decisions/` | Worktree without ADRs |
| C9 | Strip in-repo `docs/findings/` | Worktree without findings (project-B only — project-A has none) |
| C10 | Strip in-repo `docs/handoffs/` + `docs/plans/` | Worktree without handoffs+plans |
| C11 | **Strip everything (truly-clean)** | Empty `CLAUDE_CONFIG_DIR` + worktree with all of C6–C10 removed |

Shadow-dir mechanism uses symlinks to `~/.claude/*` with the target file/dir removed; session JSONLs write into an isolated `projects/` subtree so real logs aren't polluted. Worktrees are disposable branches; strips are applied per-branch.

---

## Per-cell × per-task results

| Cell | T1 turns | T1 tools | T1 cost | T1 pitfall | T2 turns | T2 tools | T2 cost | T2 pitfall | T3 turns | T3 tools | T3 cost | T3 pitfall | Σ turns | Σ tools | Σ cost | Pitfalls hit |
|---|---:|---:|---:|---|---:|---:|---:|---|---:|---:|---:|---|---:|---:|---:|---:|
| **C0  Full setup** | 14 | 12 | $0.42 | ✅ | 12 | 9 | $0.32 | ✅ | 14 | 13 | $0.30 | ✅ | **40** | **34** | **$1.04** | **3/3** |
| **C1  −CLAUDE.md** | 14 | 12 | $0.27 | ✅ | 5 | 3 | $0.11 | ✅ | 10 | 9 | $0.24 | ✅ | **29** | **24** | **$0.62** | **3/3** |
| **C2  −axioms** | 4 | 2 | $0.79 | ✅ | 9 | 7 | $0.18 | ✅ | 11 | 10 | $0.25 | ✅ | **24** | **19** | **$1.23** | **3/3** |
| **C3  −lessons** | 7 | 6 | $0.36 | ✅ | 10 | 7 | $0.29 | ✅ | 4 | 3 | $0.26 | ❌ | **21** | **16** | **$0.91** | **2/3** |
| **C4  −skills/plugins** | 7 | 6 | $0.34 | ✅ | 4 | 3 | $0.22 | ❌ | 5 | 4 | $0.08 | ❌ | **16** | **13** | **$0.63** | **1/3** |
| **C5  −project auto-mem** | 9 | 8 | $0.34 | ✅ | 21 | 18 | $0.44 | ✅ | 9 | 8 | $0.31 | ✅ | **39** | **34** | **$1.09** | **3/3** |
| **C6  −in-repo MEMORY.md** † | 18 | 16 | $0.64 | ✅ | 3 | 1 | $0.26 | ✅ | 11 | 10 | $0.26 | ✅ | **32** | **27** | **$1.15** | **3/3** |
| **C7  −docs/runbooks** | 8 | 6 | $1.09 | ✅ | 5 | 2 | $0.19 | ✅ | 7 | 6 | $0.20 | ✅ | **20** | **14** | **$1.48** | **3/3** |
| **C8  −docs/decisions** | 12 | 11 | $0.44 | ✅ | 6 | 3 | $0.22 | ✅ | 11 | 10 | $0.27 | ✅ | **29** | **24** | **$0.93** | **3/3** |
| **C9  −docs/findings** ‡ | 4 | 2 | $0.42 | ✅ | 6 | 4 | $0.41 | ✅ | 11 | 9 | $0.60 | ✅ | **21** | **15** | **$1.43** | **3/3** |
| **C10 −docs/handoffs+plans** ‡ | 15 | 13 | $1.26 | ✅ | 5 | 3 | $0.35 | ✅ | 16 | 14 | $0.79 | ✅ | **36** | **30** | **$2.41** | **3/3** |
| **C11 −everything** ‡ | 20 | 18 | $1.80 | ✅ | 5 | 3 | $0.20 | ✅ | 17 | 15 | $0.47 | ✅ | **42** | **36** | **$2.47** | **3/3** |

† = C6 is an effective no-op: neither project has a repo-root `MEMORY.md`, so the worktree strip removed nothing. Included for completeness.
‡ = C9 ablation only affects project-B (T2); C10 affects both projects. C10–C11 rows partially reconstructed from session JSONL + token-cost estimate after a rate-limit hit during parallel re-runs overwrote the CLI JSON outputs for 7 cells (see limitations).

**Pitfall keywords** (regex-AND, case-insensitive):
- T1 = (`hardcoded SELECT` | `SELECT *` | `feature mismatch` | `column presence` | `_features.json`) AND (`dataform` | `incremental` | `drift` | `column` | `feature`)
- T2 = (`wrapper` | `causalpy_v04_wrapper` | `1f2ad75`) AND (`v0.4` | `v04` | `api` | `breaking`)
- T3 = `latest_good_model` AND (`rollback` | `safety` | `gate` | `pointer`)

---

## Marginal contribution per ablated layer

Δ = Cn − C0. Positive turn/tool/cost Δ = removing the layer made the run worse (more turns/cost). Negative pitfall Δ = removing the layer caused a pitfall miss.

| Cell | Δ turns | Δ tools | Δ cost | Δ pitfalls |
|---|---:|---:|---:|---:|
| C1  −CLAUDE.md | −11 | −10 | −$0.41 | ±0 |
| C2  −axioms | −16 | −15 | +$0.20 | ±0 |
| **C3  −lessons** | **−19** | **−18** | **−$0.13** | **−1** |
| **C4  −skills/plugins** | **−24** | **−21** | **−$0.41** | **−2** |
| C5  −project auto-mem | −1 | ±0 | +$0.05 | ±0 |
| C6  −in-repo MEMORY.md † | −8 | −7 | +$0.12 | ±0 |
| C7  −docs/runbooks | −20 | −20 | +$0.44 | ±0 |
| C8  −docs/decisions | −11 | −10 | −$0.10 | ±0 |
| C9  −docs/findings | −19 | −19 | +$0.39 | ±0 |
| C10 −docs/handoffs+plans | −4 | −4 | +$1.37 | ±0 |
| C11 −everything | +2 | +2 | +$1.43 | ±0 |

**Why most Δ turns are negative.** Stripping a context layer often makes the model *finish faster with a shallower answer*. Turn count alone would lie. The pitfall column is the quality check: only C3 and C4 lost pitfall prevention. Rows with sharply negative Δ turns but Δ pitfalls = 0 (e.g., C2, C7, C9) mean "the model answered in fewer steps but still hit the pitfall keywords" — the regex grading counts that as a pass. Human grading would likely be stricter.

**Why C11 has a positive Δ turn/cost.** With *everything* stripped, the model has to discover repo structure from scratch via `Glob`/`Grep`/`ls`, which drives up both turn count and input-token cost. It still finds the answers because each repo contains enough code-level signal for keyword hit on the grading criteria. This is the 3/3 pitfall rate at C11 — see the pitfall-robustness discussion in limitations.

---

## Ranked layer-contribution list (the colleague-facing headline)

Ranking by (most negative Δ pitfalls) → (most negative Δ turns) → (Δ cost). Strips 1–5 are `~/.claude` global layers; 6–10 are in-repo project layers.

| Rank | Layer | Δ pitfalls | Δ turns | Δ cost | Colleague-adoption recommendation |
|---|---|---:|---:|---:|---|
| 1 | **C4 strip skills + plugins** | **−2** | −24 | −$0.41 | **Copy skills + plugins first.** The marketplace-installed skills (especially diagnostic / debugging skills invoked on T1 and T2) are the single biggest source of pitfall prevention here. Half the tasks missed their pitfall without them. |
| 2 | **C3 strip lessons.md** | **−1** | −19 | −$0.13 | **Copy lessons.md second.** T3 missed the rollback safety pattern without it. The lessons file is where past-fix recipes live. |
| 3 | C7 strip docs/runbooks | ±0 | −20 | +$0.44 | Nice-to-have. Answers still hit keywords but cost went UP without runbooks (more groping). |
| 4 | C9 strip docs/findings | ±0 | −19 | +$0.39 | Similar: helpful but keyword-indistinguishable at n=1. |
| 5 | C2 strip axioms | ±0 | −16 | +$0.20 | Answers got shorter without axioms but still hit pitfall keywords. |
| 6 | C1 strip CLAUDE.md | ±0 | −11 | −$0.41 | CLAUDE.md's behavioral nudges didn't show up in this task set. Cheaper without it. |
| 7 | C8 strip docs/decisions | ±0 | −11 | −$0.10 | ADRs not load-bearing at n=1. |
| 8 | C6 strip in-repo MEMORY.md † | ±0 | −8 | +$0.12 | No-op for this user (no root MEMORY.md exists). |
| 9 | C10 strip handoffs+plans | ±0 | −4 | +$1.37 | Big cost hit (more searching) but pitfall still hit. |
| 10 | C5 strip project auto-mem | ±0 | −1 | +$0.05 | Effectively null at n=1 for these tasks. |

**Interpretation.** Only 2 of 10 layers produced measurable pitfall-prevention loss at n=1. If a colleague asks "what do I copy first?", the ranked answer is:

1. Skills + plugins (**largest effect**)
2. `lessons.md`
3. Everything else is a draw on this task set and would need a larger n to separate.

This differs from the binary A/B's qualitative framing ("most of the value lives in the project repo"). Under subtractive ablation, **`~/.claude/skills` and `~/.claude/lessons.md` dominate** — not the project repo, and not CLAUDE.md.

---

## C11 vs binary-A/B clean-cell comparison (continuity check)

Binary A/B used `CLAUDE_CONFIG_DIR=/tmp/claude-empty` on the real project repo (global layer stripped; project layer intact). C11 strips BOTH global AND project layers — the truly-clean lower bound this study introduces.

| Metric | Binary A/B `clean` | C11 (this study) | Δ |
|---|---:|---:|---:|
| Σ turns | 27 | 42 | **+15** |
| Σ tool calls | 48 | 36 | −12 |
| Σ cost | $0.71 | $2.47 | **+$1.76** |
| Pitfalls avoided (loose keyword grade) | 2/3 | 3/3 | +1 |

**What this says:** removing the project-layer artifacts in addition to `~/.claude` added **+15 turns and +$1.76** — the model had to reconstruct context from code alone. The pitfall rate *went up* (2 → 3) which is surprising. Two explanations: (a) this study uses a slightly looser pitfall keyword pattern than the binary A/B's human-adjacent grading, so C11's 3/3 may be inflated; (b) the extra turns spent exploring code let the model surface the keywords organically even without the runbook/findings files. The 3/3 at C11 is a hint that **these pitfalls are discoverable from code alone given enough turns** — the setup's value is compression (same answer in fewer turns and less token spend), not unreachable insights.

---

## Surprises

1. **Project-repo layers (C6–C10) barely moved pitfall rates at n=1.** The binary A/B concluded "most of the setup value lives in the project repo." The ablation doesn't support that at this grade. Project docs kept cost down but didn't gate pitfall prevention. What keeps pitfall prevention up is global skills + lessons.
2. **Stripping CLAUDE.md and axioms didn't degrade quality.** Many users assume CLAUDE.md is load-bearing. At n=1 on these tasks it wasn't.
3. **C4 (skills/plugins) is the only −2 strip.** Skills did real work — the diagnostic and debugging skill invocations on T1 and T2 explain the drop.
4. **C5 (project auto-memory) was nearly null.** Despite being the most-read artifact category in the usage audit (MEMORY.md = 87 refs, lessons.md = 80), stripping it at n=1 didn't move anything. Possible reason: the *contents* of auto-memory mostly duplicate what's already in the repo or in lessons.md; the marginal information is thin.

---

## Honest limitations (read before citing)

1. **n = 1 per cell.** 12 cells × 3 tasks × 1 run each. Error bars are larger than most effect sizes reported. The ranking of layers 3+ (where Δ pitfalls = 0 for all) is within noise; only the top two ranks (C4 skills/plugins, C3 lessons) survive as plausibly real effects. Would need ≥3 runs per cell to produce confidence intervals.
2. **Task set reused from binary A/B.** Three tasks (T1 project-A daily-scoring diagnosis, T2 project-B CausalPy version-diff, T3 project-A monthly-retrain PR). All three were **hand-selected** precisely because they hit documented pitfalls. This upward-biases the pitfall-prevention metric at C0 and therefore biases Δ pitfalls at stripped cells — strip-induced losses show up more cleanly than they would on a random task mix. The "global skills dominate" finding is specifically about pitfall-labeled tasks; uncovered tasks may rank layers differently.
3. **Two projects.** T1 and T3 both live in project-A, so 2/3 tasks share an artifact inventory. Effective independent-project n = 2.
4. **Forward ablation NOT measured.** This is subtractive (start from full, strip one layer). A constructive ablation ("start from nothing, add one layer") would measure different things because of layer interactions. We picked subtractive because it maps better to the "what do I lose if I skip this?" adoption question.
5. **Layer interactions unmeasured.** With n=1, we can't distinguish "axioms helps" from "axioms helps *when paired with* lessons." A 2^10 factorial (1024 cells) is out of scope.
6. **Pitfall grading is loose regex-AND, not human rubric.** Catches both thoughtful mentions and shallow keyword-drops equally. A human rubric (1–5 on root-cause depth, fix specificity, pitfall acknowledgement) would likely lower several cells from ✅ to partial-credit.
7. **C9, C10, C11 rows (7 of 9 sub-cells) were reconstructed from session JSONL + token-based cost estimate** after a rate-limit hit during parallel re-runs overwrote their CLI JSON outputs. Estimates within ~10% for cost and ±1–2 for turns based on calibration. Flagged with ‡ in the results table.
8. **Orchestrator race condition.** First-version orchestrator used `wait -n` which produced a race when shells detached backgrounded jobs; recovery orchestrator launched 6 duplicate cells before first-run JSONs were fully written. All cells were eventually recovered either from a valid second run (17 cells) or JSONL reconstruction (7 cells). The result table is valid but don't trust any single cell to 1-turn resolution.
9. **Shadow dir is not a fresh install.** C1–C5 use a symlink tree rooted at `~/.claude` with the target file/dir omitted. Preserves hooks, `settings.json`, `commands/`, backup state, and cache shapes that a fresh-install user wouldn't have.
10. **Cache state is not equalized across cells.** Normal env has a warm cache; shadow cells start cold.

---

## Reproducibility (sanitized)

- Per-cell outputs: `/tmp/ablation/c{0..11}_t{1..3}.json`
- Session transcripts: `/tmp/ablation/shadow-c{0..11}/projects/<slug>/<session_id>.jsonl`
- Shadow-dir builder: `/tmp/ablation/setup_shadow.sh`
- Cell builder: `/tmp/ablation/build_cells.sh`
- Single-cell runner: `/tmp/ablation/run_cell.sh`
- Orchestrator: `/tmp/ablation/run_all_v2.sh`

To rerun a single cell:

```bash
bash /tmp/ablation/run_cell.sh <cell_id 0..11> <task_id 1..3>
```

---

## Cost summary

- 36 runs + 2 manual recovery runs + probes ≈ **~$16** ($0.44 avg per run, slightly above the binary A/B's $0.30 avg due to higher turn counts in recovered cells and some expensive runs like C7-T1 at $1.09 and C11-T1 at $1.80).
- Wall time: ~28 minutes end-to-end with batch size 6 (first orchestrator ran sequentially-blocked due to `wait -n` race, re-runs introduced a rate-limit hit on the final 7 cells; see limitations).
