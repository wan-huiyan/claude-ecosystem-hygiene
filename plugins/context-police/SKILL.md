---
name: context-police
description: |
  Use when the installed skills/agents catalog has grown large (hundreds+ standalone ~/.claude/skills/,
  e.g. from a claudeception/auto-skill-minting loop) and is driving token cost or breaking subagents.
  Symptoms: (1) the available-skills list is huge and re-appears in context every turn and inside every
  subagent; (2) a subagent dispatch fails with "Prompt is too long" at 0 tokens; (3) you want to cut the
  per-turn/per-subagent overhead WITHOUT deleting skills, ideally scoped to one project. Covers the verified
  fix (`skillOverrides`), the settings-precedence gotcha (project OVERRIDES user, so `enabledPlugins`
  per-project is the wrong tool), the VERIFIED global lever (`disable-model-invocation: true` drops a skill's
  NAME from the catalog while keeping it /name-invocable + rg-reachable), how to build a wide per-project
  denylist SAFELY (anchored startswith not substring; PROTECT allowlist; review-panel because allow-by-default
  makes false-hides the only harm), how to measure the overhead, how to verify Claude Code mechanics when
  the `claude-code-guide` agent itself overflows, how to emit an INTERACTIVE HTML recap of the treatment
  (`scripts/render_treatment_report.py` — a clickable, searchable drill-down of every skill by decision), and
  the DURABLE root-cause analysis when most of the catalog is claudeception lesson/traps: the per-project
  `skillOverrides` + global `disable-model-invocation` CURATION is the real, measured bloat win; the
  "route traps to a two-trigger retrieval hook instead of force-loading" idea was tested to ground and KILLED
  — keyword AND embedding retrievers both hit the same base-rate wall (precision-when-firing <0.3%; proven, not a
  tuning gap); the shadow hook is removed. The curation flip WAS executed (S13): 404 traps `disable-model-invocation`d
  after a 3-rater spot-check rescued 33 mislabeled procedures from a single-rater hide-list.
author: Claude Code
version: 1.8.0
date: 2026-06-05
---

# context-police — Skills-Catalog Context Cost + the skillOverrides Fix

*(formerly `skills-catalog-context-cost-skilloverrides-scoping`; renamed S10 2026-06-04. It polices the
context budget: measure the catalog cost, trim it per-project, and report it.)*

## Problem
Claude Code injects the catalog of available skills/agents into context **every turn and into every
subagent's base context**. A claudeception-style loop that mints a new skill most sessions grows
`~/.claude/skills/` unboundedly (800+), and every one is force-loaded forever. Two real effects: (a) large
per-turn and per-subagent token cost (a trivial `general-purpose` subagent was observed carrying ~30k tokens
of base context for a one-word reply — paid N× across a fan-out run); (b) small-context agent types can
overflow on launch.

## Context / Trigger Conditions
- `~/.claude/skills/` has hundreds of standalone skills; the injected list is huge.
- A subagent fails immediately with **"Prompt is too long" (0 tokens, 0 tool_uses)** — especially a
  small-context agent type like `claude-code-guide`.
- You want to reduce overhead for a focused project but keep all skills installed (and keep heavily-used
  plugins like a voltagent/agent-review-panel set fully enabled elsewhere).

## Solution (verified against code.claude.com/docs/en/settings, 2026-06-03)
1. **Diagnose precisely — don't overstate.** Catalog injection is a real *cost* that multiplies per subagent,
   but it does NOT universally break launches. Probe empirically: dispatch a one-word-prompt `general-purpose`
   subagent (works → general subagents have room) vs the failing agent type. If only one type overflows, the
   cause is **that agent type's smaller context window**, not a universal catalog overflow. State it that way.
2. **The lever for standalone skills is `skillOverrides`** (NOT `enabledPlugins` — that only governs plugins).
   `skillOverrides` is a settings.json map keyed by skill name; value `"on" | "name-only" |
   "user-invocable-only" | "off"`. `"off"` removes the skill from the model-invocable catalog (drops its
   context cost) without editing/deleting its SKILL.md; `"name-only"` keeps it discoverable but drops the
   description. Example: `{"alphafold-database":"off","scanpy":"off"}`.
3. **Scope it per-project — and mind the precedence.** Settings precedence is Managed > CLI > Local >
   **Project > User**, and same-key project settings **OVERRIDE (replace)** user settings (only *permissions*
   merge). So:
   - **`skillOverrides` in the project's `.claude/settings.json` is the right tool** — scope the noise cut to
     this project; other projects keep their full catalog. Set domain-irrelevant skills to `"off"` (e.g. for a
     static-SPA project, turn off bio/science DBs + cloud-infra one-offs that can never match the work — zero
     discoverability loss).
   - **`enabledPlugins` per-project is the WRONG tool** — replace-semantics means a project-local value
     disables every plugin you didn't re-list. Keep plugin enable/disable global.
4. **`enabledPlugins` (global) is still the lever for plugin-provided agents/skills** if you genuinely don't
   use a plugin anywhere (`{"plugin@marketplace": false}`). Don't disable plugins you actually use elsewhere.
5. **The VERIFIED global lever is `disable-model-invocation: true`** (SKILL.md frontmatter), NOT `"name-only"`.
   Empirically (2026-06-04): every skill carrying the flag is ABSENT from the injected catalog (verified 16
   flagged → all gone; a normal loaded skill lacks it), while the skill stays on disk → still `/name`-invocable
   and `rg`-reachable (so claudeception's mint-time dedup still finds it). It **drops the name** (reclaims the
   full per-skill cost) and **strictly dominates physical archive** (global, no per-project replication, no path
   juggling). Use it to bound the catalog at the source (mint new niche lesson/traps WITH the flag) + a one-time
   sweep of the existing backlog.
6. **Two CORRECTIONS to the naive durable plan:**
   - **`"name-only"` is a NO-OP for standalone skills** — they already inject as bare names (no description in
     the catalog). Only `"off"` (or `disable-model-invocation`/archive) reclaims their tokens.
   - **`find-skills`/`search-skill` search EXTERNAL marketplaces only** (`npx skills` / `site:`-scoped web
     search) — NEITHER reads `~/.claude/skills/` on disk. So they are NOT a local re-discovery path for hidden
     skills. Local re-surfacing is via claudeception's mint-time `rg` (dedup) + manual `/name` only. Don't sell
     "archive + find-skills will resurface it" — it won't.
   - Caveat: the policy of hiding all lesson/trap skills rests on the (docs-derived, **unmeasured**) premise that
     bare-name auto-recall is already marginal at scale — present it to the user as a tradeoff, not a slam dunk.

## Building a WIDE per-project denylist safely (when 211-conservative isn't enough)
Going past the obvious bio/infra one-offs into the claudeception lesson/trap bulk needs care. It is
**allow-by-default**, so the ONLY harm is hiding a skill that's actually relevant to *this* project; a missed
cut is just unrealized savings. Method that worked (211 → ~48% cut):
1. **Match ANCHORED (`name.startswith(prefix)`), NEVER substring (`prefix in name`).** Substring re-introduces
   classic traps: `"ml-"` matches `html-...`, `"react"` matches `reactome-database`, `"sql"` matches a relevant
   skill, etc. (The original conservative generator used `p in n` and got away with it only because its prefixes
   were long/unique.)
2. **Add an explicit PROTECT allowlist** (also anchored) for THIS project's real stack — it overrides the
   denylist. Err toward over-protecting.
3. **Vet the candidate ADD set with a review panel** (3 diverse-lens reviewers — e.g. app-stack / workflow / a
   skeptic doing false-positive-confirm + false-negative-scan). Take the **conservative UNION of their PULLs**
   (keep ON anything ANY reviewer flags). Because false-hide is the only harm, union-not-intersection is correct.
4. **Final guard:** scan the resulting OFF-set for protect-marker substrings and eyeball the hits (they'll be
   mostly false substring matches like `gcloud-WORKFLOWs` ≠ CC workflow, `in-memory` matched "memory") — but
   catch the real one (e.g. `dashboard-redesign-gated-…` named our pending redesign → pull it).
   Keep `gen_*` + the review JSON + a decision record for provenance and easy revert.

## Optional: emit an interactive recap report (`scripts/render_treatment_report.py`)
After applying a treatment, render a **self-contained, interactive HTML recap** — useful to show a human what
got hidden and why, and as a durable, reversible record. It's data-driven (reads the project's
`.claude/settings.json` + the skills dir), computes the counts + the bare-name token estimate, and produces an
arcade-styled page whose tiles / before-after bars / panel boxes are **clickable → a searchable, filterable
explorer of every skill by decision** (off / on / — if you pass a decisions file — kept / added / override, each
with the reviewer's reason). All data is inlined, so it opens straight from `file://` (no server, no build).

```bash
python3 ~/.claude/skills/context-police/scripts/render_treatment_report.py \
  --settings .claude/settings.json \
  [--skills-dir ~/.claude/skills] \
  [--decisions panel-decisions.json] \
  [--title "My Project"] [--out skill-treatment.html]
```
- `panel-decisions.json` (optional): `{"pulls":[{"n":"skill","r":"why kept ON"}],"adds":[…],"override":[…]}`.
  Omit it and the report is just the off/on drill-down; pass it and the panel boxes + reason-annotated views appear.
- **Verify the render WITHOUT a screenshot** (the Playwright-MCP screenshot subsystem wedges after "fonts loaded"):
  serve on a fresh port (`python3 -m http.server <port>` in the output dir — `file://` is blocked in the MCP
  browser), navigate, and use `browser_evaluate` to assert the filter buttons + row counts (skill
  `playwright-screenshot-timeout-verify-via-evaluate`). On macOS, `open <file.html>` launches it in the user's browser.
- The numbers are honest-by-construction: token estimate = `Σ(len(name)+3)/4` over the universe (bare names +
  "- " + newline ≈ 4 chars/token); "saved" = same over the OFF set; paid **every turn + per subagent** → the page
  notes the `×N` fan-out multiplier. (First built for a reference project — 866→421 off, ~7.5k→~3.1k tok, panel 22/7/1.)

## The DURABLE root-cause: lessons-as-skills (two strategies — keep them separate)
`skillOverrides` is a per-project SYMPTOM fix. The real growth driver is that a claudeception loop mints ~1 skill
per session and force-loads all of them forever — and most of those are **episodic lesson/traps** (single-incident
gotchas like `flask-flash-silently-dropped-without-base-render`). Those aren't skills; they're **lessons**, and
lessons belong in a searchable archive surfaced on demand — **not** the always-loaded catalog. The bloat is a
knowledge base in the wrong substrate. **Two strategies follow from that — do NOT conflate them:**
1. **CURATION (the real, measured win): `disable-model-invocation` the episodic traps, keep procedures.** Hide them
   from the always-on catalog (reclaim tokens) while they stay `/name`-invocable + `rg`-reachable. This pays
   regardless of any retrieval mechanism. **Triage by intent (below), and decide it on *catalog-cost* grounds.**
2. **RETRIEVAL-HOOK-AS-REPLACEMENT (tested to ground, SHELVED): surfacing the hidden traps via a context-keyed hook
   instead of force-load.** Appealing, but a keyword retriever cannot do it (proof below). It can *assist*, not
   *replace*. Don't sell "the hook makes it safe to hide traps" — that claim is false.

**Fix the trap/procedure classifier FIRST — by DESCRIPTION INTENT, not name shape.** A hyphen-count heuristic
mislabeled **171/886 skills** (S12): 117 name-invoked PROCEDURES called "trap" (would be wrongly hidden — pure
recall loss: `auto-review-loop`, a name-invoked feature-evaluator, a recurring conflict-resolution playbook) and 55
genuine reactive TRAPS called "procedure" (kept force-loaded forever because of name markers like
`worktree`/`handoff`/`sync`: `git-amend-hits-async-post-commit-hook`, `deploy-from-stale-worktree-silent-rollback`).
The discriminator: *"does the agent go LOOKING for it BY NAME (procedure → keep force-loaded) or does it only help
if SURFACED REACTIVELY to warn of a specific mistake (trap → curation candidate)?"* A 36-agent fan-out over the
frontmatter descriptions is the cheap way to curate ~hundreds (intent labels: 434 trap / 452 procedure here).

**Triage by reusability, not topic:** reusable PROCEDURE (multi-step, trigger generalizes — driven-development,
worktrees, handoff harnesses) → stays an auto-surfaced skill; single-incident TRAP → routes to the archive.

**The recall worry:** hiding a trap (whether `disable-model-invocation` or `off`) drops its passive name-recognition
(a trap's trigger situation rarely shares words with its kebab name; the agent can't grep for a trap it doesn't see
coming). The natural idea — and what S11 built — was a **two-trigger retrieval hook** to surface the hidden traps:
`UserPromptSubmit` (keys on the prompt) + `PostToolUse` (keys on the tool command / edited file — most traps surface
mid-session from an action), indexing the `SKILL.md` corpus in place (BM25 v1), injecting top-K as `additionalContext`.
**S12 measured that this hook cannot do the surfacing job (next block) — so the recall worry is real but the hook is
NOT the answer; it is a separate, unmeasured cost/benefit call (see the flip-decision note below).**

**⚠️ The retrieval hook can ASSIST but cannot REPLACE force-load — a keyword precision gate does NOT exist for a
dense trap corpus (S12, proven across FIVE gate families).** A BM25 score floor fires on **~99.6% of ALL turns**
at any floor (`git status` → 19.4, editing any `.py` → 20.9, "thanks continue" → 9.1 all clear it with *irrelevant*
traps). S12 then tested the specificity gates S11 hoped would fix it — distinctive-token count, IDF-sum, score
margin, distinctive-coverage — and **all fail the same way.** The load-bearing reason is a **base-rate wall**, not a
threshold: genuine-trap moments are **~0.11% of all triggers** (105 / 93,176 in a real corpus), so even a *perfect*
gate would fire ≤0.11% of the time; every keyword gate fires far more (6.6%–99.6%), making
**precision-when-firing ≤ 0.31% — ~99.7% noise even at the strictest setting.** (It is NOT that "recall and firing
fall proportionally" — the strict gate trades *favorably* on ratio; it's that the base rate is below any firing
rate.) Mechanism: BM25/distinctiveness measures *token overlap with the nearest trap in a 425-trap pool*, not
*relevance to this context* — only a SEMANTIC signal could, and keyword counting can't represent it. You also can't
just drop the noisy trigger: `PostToolUse` (per bash/edit) is **both** the main noise source (100% firing, 80% of
volume) **and** the plurality recall source (39% vs 23% for prompts; a third of recalled traps surface *only* there).

**So: never run it LIVE, NEVER flip on the "the hook makes it safe" basis.** Going live would cry-wolf and habituate
the model to ignore the banner. **Embeddings — the one untested PRECISION lever — were tested (S13) and FAIL the same
way.** A semantic cosine gate over `user_prompt` (the path where NL semantics is strongest) reproduces ~23% recall at
~99% firing and collapses recall faster than firing as you tighten — no threshold clears precision ≥2% with usable
recall (best realized ≈0.4%). Same base-rate wall, semantic version: it's arithmetic (relevant moments are ~0.1–0.2%
of triggers), not embedder quality. **The shadow hook is REMOVED** (both `scripts/pilot/hook.py` lines
deleted from `~/.claude/settings.json`; it was spawning a subprocess per tool call for a dead path). Retrieval as a
force-load *replacement* for traps is closed; the lever is curation (Strategy 1) + the agent's own
grep-lessons-on-task-start discipline.

**The flip decision the user owns — EXECUTED (S13).** *"hide the traps via `disable-model-invocation` on catalog-COST
grounds"* is a cost/benefit call (benefit measured: ~4.9k bare-name → ~122k full-desc tok/injection × every main turn
+ every subagent + every project; cost unmeasured: passive name-recognition, which force-load wasn't delivering for
no-signal traps anyway). Presented with numbers; user approved → applied `disable-model-invocation: true` to **404**
confirmed traps. Don't claim a recall *gain* from hiding them.

**⚠️ A single-rater hide-list MUST be independently re-rated before a destructive sweep — the gate caught real
mislabels.** The S12 intent labels were single-rater-per-skill. Before flipping, a **blind second-rater (24 agents) +
a 2-of-3-majority tie-break** over all 434 traps found **33 were actually name-invoked PROCEDURES** (would have been
wrongly hidden → pure recall loss; several were skills published from the project itself). 91.7% agreement, but the
42 disagreements skewed 36:6 toward the harmful (trap→procedure) direction — exactly where a mislabel hides a useful
playbook. Corrected hide-list = 404. **Re-rate before you hide; the dangerous direction is procedure-mislabeled-as-trap.**

**⚠️ Don't blow away an existing relevance-curated `skillOverrides` when you add the global flip — they hide DIFFERENT
things.** The global frontmatter flag hides TRAPS everywhere (keeps `/name`); a per-project `skillOverrides` "off" map
is usually a panel-vetted RELEVANCE hide (e.g. bio/research skills irrelevant to *this* repo) that intent labels
CANNOT reconstruct (labels say trap/procedure, not relevant/irrelevant). Surgical fix when adding the flip:
`new_off = old_off − (globally-flipped traps) − (proven-useful rescued procedures)` — keep the relevance hides, let
the global flip own trap-hiding (with `/name`), restore only the spot-check-rescued playbooks.

**Measured (reference project, S10 build → S11 → S12 → S13):** classifier FIXED (intent curation: 434
trap / 452 procedure; hyphen-count wrong on 171). Keyword retrieval: union recall@5 ≈ 54% **only at ~100% firing**;
every gate that cuts firing cuts recall below the base-rate wall (precision-when-firing <0.3%). **Embeddings (S13):
TESTED on `user_prompt`, same wall (best realized precision-when-firing ≈0.4%; reproduces 23% recall at 99% firing).**
Subagent leg dead (S11: trap-firing 0.9% of 2151 subagents). **Flip EXECUTED (S13): 404 traps `disable-model-invocation`d
(blind re-rate + tie-break rescued 33 mislabeled procedures first); shadow hook removed; claudeception mint-default
flipped (new traps mint `disable-model-invocation` by default).** Reference impl + harness: this skill's
`scripts/pilot/` (phase5/6/7 + `phase8_embeddings_probe.py` + the BM25/recall machinery) and the actionable
flip applier `scripts/apply_disable_model_invocation.py` (idempotent `--dry-run`/`--apply`/`--revert`). The
harness reads two corpus-specific inputs (`lesson-index.jsonl`, `intent-labels.json`) it does NOT ship —
`scripts/pilot/README.md` documents how to regenerate them for your own `~/.claude` and reproduce every number.

## Measuring the overhead (if you want the number)
The fixed scaffolding re-read each turn ≈ `min(nonzero cache_read_input_tokens across the session's turns)`
(the stable cached prefix = system prompt + tool/skill catalog + earliest conversation). The naive
"first-turn cache_write+cache_read = catalog" identity is unreliable (resumed/--continue sessions read a
pre-warmed cache on turn 1) — calibrate, don't assume. Subagent transcripts
(`~/.claude/projects/**/subagents/**/agent-*.jsonl`) carry their own per-dispatch floor → that's the N× story.

## Verification
- After adding project `skillOverrides`, restart Claude Code and confirm the injected skills list shrank.
- `git check-ignore` / a dry-run generator can quantify how many skills a denylist would turn off before you
  apply it. Reversible: delete an entry or set `"on"`.

## Notes
- **When `claude-code-guide` overflows, you can't use it to answer Claude Code questions** — verify mechanics
  by `WebFetch`-ing `code.claude.com/docs/...` directly (note `docs.claude.com/en/docs/claude-code/*` 301-
  redirects to `code.claude.com/docs/en/*`), or ask from a session where the catalog is already trimmed.
- Managed-only knobs exist for org control: `strictPluginOnlyCustomization` (block user/project skills),
  `blockedMarketplaces`, `strictKnownMarketplaces` — not needed for a personal per-project trim.
- See also: `concurrent-session-curating-shared-global-dir` (the shared skills dir grows live across sessions),
  `claude-code-subagent-agenttype-overrides-session-model` (a different subagent-context gotcha).
