---
name: context-police
description: |
  Use when an agent harness's skills/tools catalog has grown large (hundreds+, e.g. from an auto-skill-minting
  loop) and is taxing context: the listing of skill names+descriptions is injected every turn AND into every
  subagent, so cost multiplies on fan-out and small-context agents can overflow ("Prompt is too long" at 0
  tokens). This skill is the AUDIT + CURATION methodology plus measurement/reporting: the trimming levers are
  now native harness features — the durable value is deciding WHAT to trim (episodic lessons vs real skills),
  applying it safely, and measuring the result. The PROBLEM + METHODOLOGY are harness-agnostic — the Agent
  Skills standard (agentskills.io) is shared by Claude Code, Cursor, Codex, Copilot CLI, Gemini CLI; only the
  levers differ.
  Covers: the portable diagnosis + classification rigor (curate by INTENT not name, conservative asymmetry,
  blind re-rate, deterministic checks over LLM votes); the cross-harness landscape (native budgets vs manual
  curation); the Claude Code levers (`skillOverrides`, `disable-model-invocation`, the native
  `skillListingBudgetFraction`/`maxSkillDescriptionChars` budget read via `/doctor`, and the anti-pattern of
  raising the fraction); the `disable-model-invocation` DUAL-ROLE footgun (also the correct setting for a user
  slash-command — so a "name-invoked → restore" audit is a false-positive machine); plus a history footnote (a
  retrieval-hook replacement was killed by a base-rate wall).
author: Claude Code
version: 2.0.0
date: 2026-06-17
---

# context-police — skills-catalog audit, curation & measurement in agent harnesses

*(formerly `skills-catalog-context-cost-skilloverrides-scoping`. **v2.0.0 reframe:** the problem + method are
harness-agnostic; the Claude Code levers are ONE implementation. Earlier versions were Claude-Code-only, and a
big chunk of that work was superseded when harnesses added native budgets — see "History" at the bottom.)*

## The problem (any harness with an always-on skill catalog)
An agent harness injects the **listing of available skills/tools (names + descriptions) into context every turn,
and into every sub-agent's base context.** An auto-minting loop (claudeception-style: ~1 new skill/session) grows
that catalog unboundedly, and every entry is force-loaded forever. Two real effects: (a) per-turn **and
per-subagent** token cost that multiplies on fan-out (a trivial subagent was observed carrying ~30k tokens of base
context for a one-word reply); (b) small-context agent types overflow on launch ("Prompt is too long", 0 tokens).
Skill *bodies* lazy-load on use on every modern harness — it's the always-on **listing** that's the tax.

## The portable core — this is what travels to ANY harness
The levers further down are platform-specific; **these ideas are not** — they're information architecture + arithmetic.

1. **Catalog cost is real and multiplies per sub-agent.** Measure it (appendix recipe), don't hand-wave.
2. **Most auto-minted "skills" are episodic *lessons*, not skills** — single-incident gotchas
   (`flask-flash-silently-dropped-…`). A lesson belongs in a *searchable archive surfaced on demand*, not the
   always-loaded catalog. The bloat is a knowledge base in the wrong substrate.
3. **Curate by description INTENT, never name shape.** Warning-shaped names are often real traps; command-shaped
   "lessons" exist. A hyphen-count heuristic mislabeled 171/886 skills. The discriminator: *does the agent go
   LOOKING for it BY NAME (procedure → keep) or does it only help if SURFACED REACTIVELY to warn of a specific
   mistake (trap → curation candidate)?*
4. **Conservative, asymmetric bias.** Hiding a real procedure (or restoring a user command) is the *silent, costly*
   error; failing to hide a trap is harmless (a few unrealized tokens). When in doubt, take the harmless side.
5. **A "hide from auto-invocation" flag has TWO roles — don't conflate them** (the reverse-audit footgun, below).
   One is context-saving; the other is the *correct* config for a user slash-command.
6. **Retrieval can't replace force-load for a dense trap corpus** — proven base-rate wall (History, below).
   Curation + the agent's own grep-lessons-on-task-start discipline is the lever; an on-demand hook can *assist*,
   not *replace*.
7. **Once a harness has a native budget, the forward hide-sweep is largely played out** — it then reclaims only
   bare names. The durable value shifts to relevance-scoping + reading the diagnostics right + NOT over-hiding.

## Cross-harness landscape (researched 2026-06-17; all adopt the Agent Skills standard, agentskills.io)
| Harness | Always-on listing? | Native budget / truncation? | Per-skill disable (keep manually-invocable) | Per-subagent ×N? |
|---|---|---|---|---|
| **Claude Code** | yes | **YES** — `skillListingBudgetFraction` 1% + `maxSkillDescriptionChars` 1536 (shipped v2.1.105, 2026-04-13; defaults as of then — `/doctor` shows your install's live values) | `skillOverrides` (per-project), `disable-model-invocation` (global) | **yes** (whole catalog into every subagent) |
| **Codex** | yes (name+desc+path at session start) | **YES** — ~2% / 8000-char cap; descriptions shorten then omit-with-warning; desc cap 1024 | `allow_implicit_invocation:false` / `enabled=false` | **yes** (subagents cost more; recommend a mini child model) |
| **Cursor 2.4** | descriptions model-visible; `alwaysApply:true` rules inject full body every turn | **no** documented budget (soft "<500 lines" guidance) | **`disable-model-invocation: true`** (→ slash-only) + `paths` glob | subagents exist; ×N unverified |
| **Copilot CLI** | name+desc index always-on; bodies lazy | **no** | `disable-model-invocation` / `user-invocable:false` + `/skills` toggle | **no** — sub-agents inherit no skills |
| **Gemini CLI** | yes (name+desc in system prompt at session start) | **no** | `/skills disable` + `@`-invoke | subagents isolated; ×N unverified |

**Read-out: the problem is universal; the native fix is not.** Claude Code and Codex bound it automatically.
**Cursor, Copilot CLI, and Gemini CLI have no documented listing budget — there, context-police's manual curation
is still the live answer.** The `disable-model-invocation` flag is part of the open standard, so it works
**verbatim on Cursor and Copilot CLI**, not only Claude Code (Cursor's docs even describe it as "behave like a
traditional slash command" — independent confirmation of the dual-role below). Copilot CLI is the mildest: it also
avoids the ×N fan-out because sub-agents inherit no skills. *(Items marked "unverified" weren't in the harness's
public docs as of the research date — confirm before relying.)*

## Claude Code implementation (the specific levers)
1. **Diagnose precisely.** Catalog injection is a real *cost* that multiplies per subagent, but it does NOT
   universally break launches. If only one agent type overflows ("Prompt is too long", 0 tokens — e.g.
   `claude-code-guide`), the cause is **that agent type's smaller context window**, not a universal overflow.
2. **`skillOverrides`** (settings.json map keyed by skill name; `"on" | "name-only" | "user-invocable-only" |
   "off"`) is the lever for standalone skills. `"off"` removes a skill from the model-invocable catalog without
   editing its SKILL.md. Shipped in CC **v2.1.129** (as of writing — verify against your install; older
   versions silently ignore the key), does **not** apply to plugin skills (manage those via
   `/plugin` / `enabledPlugins`), and the **`/skills` menu writes to `.claude/settings.local.json`** (Local >
   Project) — so menu entries layer OVER hand-authored `.claude/settings.json`; reconcile across both.
3. **Scope per-project, mind precedence.** Precedence is Managed > CLI > Local > **Project > User**, and same-key
   project settings **OVERRIDE (replace)** user settings (only *permissions* merge). So `skillOverrides` in the
   project's `.claude/settings.json` is the right tool for **relevance** trims (bio/infra one-offs irrelevant to
   *this* repo). **`enabledPlugins` per-project is the WRONG tool** — replace-semantics disables every plugin you
   didn't re-list; keep plugin enable/disable global.
4. **`disable-model-invocation: true`** (SKILL.md frontmatter) is the **global** lever for episodic TRAPS: drops
   the skill from the injected catalog while it stays on disk → still `/name`-invocable + `rg`-reachable. Use it
   to bound the catalog at the source (mint niche traps WITH the flag) + a one-time backlog sweep.
5. **The native budget (shipped v2.1.105, 2026-04-13 — version + defaults below are as of that release;
   verify against your install with `/doctor`):**
   - **`skillListingBudgetFraction`** (default `0.01` = 1%): when the listing exceeds 1% of context, the
     **least-used** skills' descriptions collapse to bare names (still `/name`- and model-invocable; the model just
     can't see *why*). Usage-ranked auto-curation, every session.
   - **`maxSkillDescriptionChars`** (default `1536`): per-skill cap on `description`+`when_to_use`; longer is
     **truncated** (independent of the budget). Keep your OWN skills' descriptions ≤1536.
   - `/doctor`'s **Skills ⚠** check prints `N descriptions will be dropped (X%/1% of context)`, the per-entry-cap
     offenders, and the token cost of opting in. It is the canonical readout — re-run it after any change.
   - **THE ANTI-PATTERN: do NOT raise `skillListingBudgetFraction` to silence `/doctor`.** The 1% default *is*
     context-police running natively. Opting in to full descriptions costs ~111k tokens/session (same ballpark as
     the old ~122k whole-catalog estimate) and burns rate limits faster. The aligned move is the opposite — shrink
     the catalog (per-project `"off"` + the curated trap flips). `/doctor`'s drop-count is what REMAINS *after*
     those levers fired; the budget silently absorbs the rest, so the warning is mostly informational.
   - **`"name-only"` reclaims tokens only for a skill the budget still shows WITH a description** (a *most-used*
     one); least-used skills are already bare names, so for them it's a no-op — only `"off"`/`disable-model-invocation`
     reclaims the *name*. (`find-skills`/`search-skill` search EXTERNAL marketplaces only — they do NOT re-surface
     hidden local skills.)

## Porting to another harness (the recipe)
Find the harness's three knobs, then apply the portable core:
1. **Native budget?** Check its own diagnostics (`/doctor`, `/context`, `/skills`). Has one (Claude Code/Codex) →
   mostly relax, just don't defeat it. None (Cursor/Copilot/Gemini) → manual curation is the job.
2. **Per-skill visibility control?** `disable-model-invocation` (Claude Code/Cursor/Copilot), `allow_implicit_invocation:false`/`enabled=false` (Codex), `/skills disable` (Gemini). Use it for episodic traps; **KEEP it on user
   slash-commands.**
3. **Does cost multiply per sub-agent?** Yes (Claude Code/Codex) → the prize is ×N. No (Copilot) → less urgent.
Then run the classification rigor below before any bulk change.

## The `disable-model-invocation` DUAL-ROLE footgun (+ the reverse-audit trap)
The flag does ONE mechanical thing: removes a skill from the **model-invocable** catalog while keeping it
`/name`-invocable by the user. But that serves TWO different intents, and conflating them causes a destructive
false-positive:
1. **Context-saving (the trap sweep):** hide episodic lesson/traps so they don't cost catalog tokens. Reversible.
2. **The CORRECT config for a USER SLASH-COMMAND** (`changelog`, `setup`, `lfg`, `slfg`, `resolve-pr-parallel`,
   the `ce-*`/`todo-*` suites): the flag is exactly what STOPS the model from spontaneously auto-firing the command
   while the user keeps `/name`. For a command the flag is RIGHT — not a "hidden procedure," correct configuration.
   Built-in commands ship WITH it.

**The reverse-audit trap (measured 2026-06-17):** auditing the already-flipped set for "wrongly-hidden procedures"
through a *"name-invoked → restore"* lens produces massive FALSE POSITIVES — it flags every user command as a
mislabeled procedure. Restoring them is actively HARMFUL: it makes the model auto-invoke commands (e.g. the
autonomous-engineering pipelines `lfg`/`slfg`) AND re-bloats the catalog. A full reverse audit (15 agents, body-reads
of all 487 hidden) flagged **17** "restore" candidates; on verification **~16 were correctly-configured user
commands**; genuine restores ≈ **1** (a model-applied design discipline with no command markers). An interim "~7%
mislabeled" sample estimate was inflated by this same framing error.

**The discriminator (DETERMINISTIC beats another LLM pass):** does the frontmatter carry `argument-hint` /
`allowed-tools`, or read as "# … Command"? → USER command; the flag is CORRECT; do **not** restore. Only a
*model-applied* skill (a reusable discipline/procedure the MODEL surfaces, no command markers) is a legit restore
candidate — confirm with PROVENANCE (`git log -L`/`git blame` the flag line; present at mint = intended, added by a
sweep = possible victim). **Narrow the "restoring is low-risk" premise:** it holds ONLY for non-command skills;
restoring a COMMAND is a behavior change (the model can now auto-fire it), not cosmetic.

## Classification rigor for ANY bulk frontmatter sweep (forward OR reverse)
- Classify by description **INTENT**, never name shape (warning-shaped names are usually real traps; command-shaped
  "lessons" exist).
- **Conservative, asymmetric bias:** hiding a procedure (or restoring a command) is the silent, costly error; the
  opposite is harmless. Take the harmless side on doubt.
- A deliberately-lenient first pass **over-flags ~15×** (2026-06-17: 16/343 candidates → blind 3-of-3 re-rate
  confirmed **0**). A BLIND re-rate by independent raters reading the **bodies** (not just descriptions) is mandatory
  before any destructive change; require strong agreement (2-of-3 min, 3-of-3 for a low-reward case).
- Prefer a **deterministic** check where one exists (grep `argument-hint`/`allowed-tools`) over an LLM vote.

## Building a WIDE per-project denylist safely (Claude Code; when conservative isn't enough)
Going past the obvious bio/infra one-offs needs care. It is **allow-by-default**, so the ONLY harm is hiding a skill
relevant to *this* project; a missed cut is just unrealized savings. Method (≈48% cut):
1. **Match ANCHORED (`name.startswith(prefix)`), NEVER substring** (`"ml-"` matches `html-…`, `"react"` matches
   `reactome-database`).
2. **Add an explicit PROTECT allowlist** (anchored) for this project's stack — overrides the denylist; over-protect.
3. **Vet the candidate ADD set with a review panel** (3 diverse lenses); take the **conservative UNION of PULLs**
   (keep ON anything ANY reviewer flags) — false-hide is the only harm, so union-not-intersection is correct.
4. **Final guard:** scan the OFF-set for protect-marker substrings, eyeball the hits. Keep the generator + review
   JSON + a decision record for provenance and easy revert.

## Optional: interactive recap report (`scripts/render_treatment_report.py`)
After a treatment, render a self-contained, interactive HTML recap (reads `.claude/settings.json` + the skills dir,
computes counts + the bare-name token estimate; clickable tiles → a searchable explorer of every skill by decision).
Honest-by-construction; opens from `file://`.
```bash
python3 ~/.claude/skills/context-police/scripts/render_treatment_report.py \
  --settings .claude/settings.json [--skills-dir ~/.claude/skills] \
  [--decisions panel-decisions.json] [--title "My Project"] [--out skill-treatment.html]
```
Verify the render with `browser_evaluate` over a served port (`file://` is blocked in MCP browser; the screenshot
subsystem wedges) or `open` it on macOS.

## Measuring the overhead (Claude Code)
The fixed scaffolding re-read each turn ≈ `min(nonzero cache_read_input_tokens across the session's turns)` (stable
cached prefix = system prompt + tool/skill catalog + earliest conversation). The naive "first-turn
cache_write+cache_read = catalog" identity is unreliable (resumed sessions read a pre-warmed cache) — calibrate.
Subagent transcripts (`~/.claude/projects/**/subagents/**/agent-*.jsonl`) carry their own per-dispatch floor → the
N× story. (`/doctor` is the faster path for the listing specifically.)

## Notes
- **When `claude-code-guide` overflows, you can't use it to answer CC questions** — run `/doctor`, or `WebFetch`
  `code.claude.com/docs/...` (`docs.claude.com/en/docs/claude-code/*` 301-redirects to `code.claude.com/docs/en/*`).
- Managed-only org knobs: `strictPluginOnlyCustomization`, `blockedMarketplaces`, `strictKnownMarketplaces`.
- See also: `concurrent-session-curating-shared-global-dir`, `claude-code-subagent-agenttype-overrides-session-model`.

## History — superseded scaffolding (kept for provenance)
The S6–S13 arc, much of it now overtaken by native budgets:
- **The native budget arrived first.** CC's `skillListingBudgetFraction` shipped **v2.1.105 (2026-04-13)** — ~7
  weeks *before* this skill was first written. The original "docs-derived, not measured ~1% budget" note was about
  this exact mechanism; it is now verified via `/doctor`. This is why the v1.x headline value (measure + trim the
  description cost) is mostly the platform's job today.
- **The retrieval-hook replacement was tested to ground and KILLED.** The idea: surface hidden traps via a
  two-trigger hook (`UserPromptSubmit` + `PostToolUse`) instead of force-loading. It can't: a keyword score floor
  fires on **~99.6% of all turns**; every specificity gate (distinctive-token, IDF-sum, score-margin, coverage)
  fails the same way — a **base-rate wall**: genuine-trap moments are **~0.11% of all triggers** (105/93,176), so
  precision-when-firing is **≤0.31%** even at the strictest setting. **Embeddings fail identically** (~23% recall
  at ~99% firing; best realized precision ≈0.4%) — it's arithmetic, not embedder quality. The shadow hook was
  removed. Retrieval *assists*, it does not *replace* force-load.
- **The curation flip was executed (S13):** 404 traps `disable-model-invocation`d after a blind 2-of-3 re-rate
  rescued 33 mislabeled procedures (the dangerous direction is procedure-mislabeled-as-trap); claudeception's
  mint-default flipped to mint new traps hidden. A **2026-06-17** conservative re-rated extension over ~343 unflagged
  candidates confirmed **0 new safe traps** → the forward sweep is played out (it now reclaims only ~2–3k bare-name
  tokens). Don't claim a recall *gain* from hiding traps; the benefit is catalog-cost, the cost (passive
  name-recognition) was never delivered for no-signal traps anyway.
- **Don't clobber a relevance-curated `skillOverrides` when adding the global flip** — they hide DIFFERENT things
  (relevance per-project vs traps everywhere). Surgical: `new_off = old_off − globally-flipped-traps − rescued-procedures`.
- Reference impl: `scripts/pilot/` (BM25/recall + `phase8_embeddings_probe.py`), `scripts/apply_disable_model_invocation.py`
  (idempotent `--dry-run`/`--apply`/`--revert`), `scripts/render_treatment_report.py`. Corpus inputs
  (`lesson-index.jsonl`, `intent-labels.json`) regenerate per `scripts/pilot/README.md`.
