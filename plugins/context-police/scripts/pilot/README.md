# Lesson-retrieval pilot — the harness that proved retrieval CAN'T replace force-load

This is the reproduction harness behind context-police's central, **settled** finding:

> A context-keyed **retrieval hook cannot replace force-loading** episodic trap-lessons. Both a
> keyword (BM25) gate and a semantic (embedding) gate hit the same **base-rate wall** —
> precision-when-firing **< 0.5%** at any usable recall — so a hook can *assist* but never *replace*.
> The real lever is **curation** (`skillOverrides` per-project + `disable-model-invocation` globally),
> plus the agent's own *grep-lessons-on-task-start* discipline.

The scripts here let you **re-run that experiment on your own `~/.claude` corpus** instead of taking
the result on faith. Nothing here changes Claude Code's behavior — the hook ships **SHADOW by
default** (logs what it *would* inject, injects nothing).

## Why the question mattered

Most of a runaway skills catalog is *episodic traps* (single-incident gotchas), and force-loading
them all is the token cost context-police measures. The tempting fix: hide the traps from the
always-on catalog and surface them on demand via a retrieval hook keyed on the prompt + the last
tool action. If that worked, you could hide traps "safely." **It doesn't** — and this harness is how
that was nailed down rather than assumed.

## The result (reproduced on a real ~900-skill catalog)

Replay over real model-initiated trap invocations across all `~/.claude/projects`:

| gate | recall@5 | firing rate | precision-when-firing |
|---|---|---|---|
| keyword BM25, no gate | ~51% (per-trap) | **~99.6% of turns** | ~0.1–0.3% |
| keyword + any specificity gate (5 families tried) | collapses with firing | — | **≤ 0.31%** |
| semantic cosine (static embedder) over prompts | ~23% @ thr 0.30 | ~99% | ~0.2%; best realized **≈0.4%** |

The load-bearing reason is arithmetic, not tuning: genuine-trap moments are only **~0.1% of all
triggers**, so even a *perfect* gate fires ≤0.1% of the time — and every real gate fires far more,
making it ~99.7% noise. Tightening a keyword **or** an embedding threshold collapses recall faster
than it collapses firing. Five keyword gate families (score floor, distinctive-token count, IDF-sum,
score margin, distinctive-coverage) all fail the same way; the embedding probe fails identically.

**Verdict:** never run the hook LIVE, and **never** flip `disable-model-invocation` on the basis that
"the hook makes it safe." Decide the flip on *catalog-cost* grounds alone (it pays regardless), and
re-rate any single-rater trap/procedure labels before a destructive sweep (see "Spot-check" below).

## Pieces

- `retrieve.py` — builds `lesson-index.jsonl` from `~/.claude/skills/*/SKILL.md` (in place, no
  migration) + a dependency-free BM25 retriever. `python3 retrieve.py "<paraphrase>"` to probe;
  `--build` to (re)index.
- `replay_recall.py` — rank-only recall@K over real past trap invocations in `~/.claude/projects`.
- `hook.py` — the two-trigger hook (`UserPromptSubmit` + `PostToolUse`), **SHADOW by default** (logs
  to `~/.claude/lesson-retrieval-shadow.log`, injects nothing; logs `{"warn":"index-missing"}` if the
  index isn't built, so you can tell inert from working).
- `audit_classifier.py` — trap vs procedure split against firing counts.
- `recompute_with_overrides.py` — recall over **genuine traps only** (excludes name-invoked
  procedures). Its `PROCEDURE_OVERRIDES` set is **illustrative — replace it with your own catalog's
  name-invoked procedures**; it also provides the `_text` / `corrected_index` helpers the phase
  scripts import.
- `phase2_floor_sweep.py` — floor-applied recall + the ~99.6% injection rate + relative floor.
- `phase3_diagnose.py` — why genuine traps miss (no-signal vs paraphrase).
- `phase4_subagent_scan.py` — subagent `agent_type` ↔ trap-firing + bundle-coverage (the subagent leg
  is rare, ~0.9%, and concentrates in `general-purpose` → a per-agent_type bundle doesn't pay).
- `phase5_precision_gate.py`, `phase6_mode_decompose.py`, `phase7_margin_coverage.py` — the keyword
  specificity-gate families, each shown to fail the base-rate wall.
- `phase8_embeddings_probe.py` — the semantic cosine gate (static `model2vec` embedder) over the
  `user_prompt` path; the same wall, semantic version.

## Reproduce on your own corpus

1. **Build the index** from your installed skills:
   `python3 retrieve.py --build` → writes `lesson-index.jsonl` (gitignored; not shipped).
2. **Curate intent labels.** The phase scripts read a `intent-labels.json` (`{"labels":[{"id":...,
   "kind":"trap"|"procedure"}]}`) — the trap/procedure split *by description intent*, not name shape.
   Generate it with a fan-out of agents over each `SKILL.md` description (the discriminator: *does the
   agent go LOOKING for it BY NAME → procedure; or does it only help if SURFACED REACTIVELY → trap*).
3. **Measure recall + firing:** `python3 replay_recall.py`, then `python3 phase2_floor_sweep.py`.
4. **Try the gates:** `phase5/6/7` (keyword) and `phase8_embeddings_probe.py` (semantic). Watch
   precision-when-firing stay below ~0.5% at any usable recall — the wall.
5. **(Optional) Shadow-run the hook** for a few days to collect a real firing log:
   build the index, then APPEND these as NEW entries to your existing `~/.claude/settings.json`
   (keep your other hooks):
   ```jsonc
   // hooks.UserPromptSubmit  (additional array element):
   { "hooks": [ { "type": "command", "command": "python3 <path>/hook.py user_prompt" } ] }
   // hooks.PostToolUse  (additional matcher group):
   { "matcher": "Bash|Edit|Write", "hooks": [ { "type": "command", "command": "python3 <path>/hook.py post_tool" } ] }
   ```
   Run it from a **stable path** (a git worktree gets cleaned). Expect it to fire on nearly every turn.

## Spot-check before any destructive sweep

If you do flip traps to `disable-model-invocation` on cost grounds, **re-rate a single-rater
hide-list first**: a blind second rater + a 2-of-3-majority tie-break. The dangerous error direction
is *procedure mislabeled as trap* (hiding a name-invoked playbook = pure recall loss). In the
reference run this rescued **33 of 434** "traps" that were actually procedures. The actionable flip
applier is `../apply_disable_model_invocation.py` (idempotent, `--dry-run`/`--apply`/`--revert`).

## Honest limits (carry these)

- Recall is a **floor**, not a point estimate — ground truth = traps that *did* fire (no
  counterfactual for traps that were silently missed).
- One static embedder was tested in `phase8`; a heavier model is untested, but the wall is a
  base-rate property (to reach ≥2% precision you must reject ~89% of prompts while keeping the right
  trap top-5, and recall collapses long before firing drops that far) — a qualitative change is
  unlikely.
- The harness reads two generated inputs (`lesson-index.jsonl`, `intent-labels.json`) that are
  **specific to your corpus and are not shipped** — regenerate them per steps 1–2 above.
