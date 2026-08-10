---
name: context-police
description: |
  Use when an agent harness's skills/tools catalog has grown large (hundreds+, e.g. an auto-skill-minting
  loop) and is taxing context: the name+description listing is injected every turn AND into every subagent, so
  cost multiplies on fan-out and small-context agents can overflow ("Prompt is too long" at 0 tokens). Also
  use when a description exceeds the per-skill cap — the harness truncates mid-word and every trigger phrase
  past the cut goes silently dead. This skill is the AUDIT + CURATION methodology, measurement/reporting, and
  a publish-time description gate: the trimming levers are now native, so the durable value is deciding WHAT
  to trim (episodic lessons vs real skills), applying it safely, and measuring the result. The PROBLEM +
  METHODOLOGY are harness-agnostic — the Agent Skills standard (agentskills.io) is shared by Claude Code,
  Cursor, Codex, Copilot CLI, Gemini CLI; only levers differ. Covers: classification rigor (curate by INTENT
  not name, conservative asymmetry, blind re-rate); the cross-harness landscape; the Claude Code levers
  (`skillOverrides`, `disable-model-invocation`, the native
  `skillListingBudgetFraction`/`skillListingMaxDescChars` budget read via `/doctor`, and the anti-pattern of
  raising the fraction); the per-skill description cap and the triggers truncation destroys; and the
  `disable-model-invocation` DUAL-ROLE footgun — also the correct setting for a user slash-command, so a
  "name-invoked → restore" audit is a false-positive machine.
author: Claude Code
version: 2.4.0
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
| **Claude Code** | yes | **YES** — `skillListingBudgetFraction` 1% + `skillListingMaxDescChars` 1536 (shipped v2.1.105, 2026-04-13; defaults as of then — `/doctor` shows your install's live values) | `skillOverrides` (per-project), `disable-model-invocation` (global) | **yes** (whole catalog into every subagent) |
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
   - **`skillListingMaxDescChars`** (default `1536`): per-skill cap on `description`+`whenToUse` (the harness
     joins them with `" - "` and caps the pair); longer is **truncated** (independent of the budget). Keep your
     OWN skills' descriptions ≤1536 — enforce it with `scripts/check_skill_descriptions.py` (below).
     *(The setting is `skillListingMaxDescChars`; earlier revisions of this skill called it
     `maxSkillDescriptionChars`, which no `settings.json` key matches. Verified against the v2.1.221 binary.)*
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

## The publish-time gate: per-skill description cap (`scripts/check_skill_descriptions.py`)
Everything above curates a catalog you INHERITED. This is the upstream half — stop an oversized description
from shipping in the first place. Zero-dependency, exit 1 on violation, drop it in CI.
```bash
python3 scripts/check_skill_descriptions.py .              # gate a skill repo
python3 scripts/check_skill_descriptions.py . --triggers   # what truncation is destroying
python3 scripts/check_skill_descriptions.py . --context 1000000 --json
```

**Why the cap matters more than the token cost.** Going over does not cost tokens — the budget is a hard cap.
It costs *descriptions*, and truncation is **not** intelligent: the harness keeps `full[:1535]` and appends an
ellipsis. A description is trigger text, so every `when the user says "…"` phrase living past that character
position is **already dead** — the skill will not fire on it and nothing reports the loss.

**This inverts the safety question for trimming.** The instinct is "if I cut the description, will the skill
still work?" But an over-cap description is already cut; the only question is whether YOU choose what survives
or the harness chooses by character position. `--triggers` lists the quoted phrases past the cut, so a
deliberate trim is verifiable: re-run until that section is empty.

Measured on a real 18-plugin install (2026-08-04): **12 skills over cap, 30 trigger phrases invisible.** One
skill had lost all 11 triggers for an entire documented feature — `"budget mode"`, `"cheap review"`,
`"token-efficient review"` and the rest — so the feature could not be invoked by any of its own trigger
phrases while still being fully documented in the body.

**Not the same check as SKILL.md body size.** The body lazy-loads only when the skill fires; the description is
resident every turn. A 1,620-char description with a tiny body passes a body-size linter and fails here; the
reverse also holds. The two are independent — run both. Worse, a body-size pass gives false comfort: on
`agent-review-panel` a schliff quality pass (75→86) left the description at **1,501 chars — 35 under the cap**;
the very next feature commit pushed it to 2,004 and schliff never complained, because it does not measure
descriptions.

## Trimming an over-cap description SAFELY (the verified procedure)
Detecting the problem is the easy half. Trimming trigger text is where a careless fix does real damage, so
this is a measured procedure, not a style guide. Validated end-to-end on `agent-review-panel` (2,703 → 1,505
chars, 25 dead triggers recovered).

1. **Run `--triggers` BEFORE touching anything.** You are not deciding whether to cut; the harness already cut.
   You are deciding what survives. Know what is currently dead first.
2. **Compress synonym runs; never delete concepts.** The model generalizes from `"cheap review"` to
   `"frugal review"` — it cannot generalize from a phrase it never sees. Ten literal synonyms for one concept
   is waste; two or three representatives carry it. Every *distinct* concept stays.
3. **Cut prose, not trigger vocabulary.** Implementation detail ("3 sonnet reviewers, one debate round, opus
   judge") belongs in the body. The description's only job is to make the model reach for the skill.
4. **Keep the NOT-for list.** It is precision — it is what stops false firing.
5. **Measure against the right baseline.** Score each known trigger prompt (an `eval-suite.json`, or the
   skill's own trigger list) by word overlap against **`old[:cap-1]`** — what the model *actually saw* — not
   against the full oversized source. Using the full source as baseline includes text the model never read and
   makes every honest trim look like a regression.
6. **Expect the first attempt to regress, and check.** The measured first pass on `agent-review-panel` scored
   **11 better / 18 same / 10 WORSE**. The failure mode is predictable: you optimize the distinctive mode
   triggers and quietly drop natural-language phrases like `"critical look from security and performance
   angles"`. Diagnose mechanically — set-difference the word sets, count how many prompts each dropped word
   serves, restore exactly those, re-cut. The shipped second pass measures **12 better / 27 same / 0 worse**
   against the committed harness. (The first-pass figure is from an intermediate state that was never
   committed and does not reproduce; the second-pass one does.)
7. **Track SEPARATION, not just positive coverage.** Score the negative prompts too. A trim that lifts positive
   coverage by adding generic words also lifts false firing. Report `positive_mean − negative_mean` before and
   after; it must widen or hold (`agent-review-panel`: **+0.2605 → +0.3183**).
8. **Leave headroom (~30–50 chars).** A trim landing at cap−2 is one edit from breaking again.
9. **Preserve the file's YAML scalar style** (`>` folded / `|` block / plain), and **re-wrap with
   `break_on_hyphens=False`.** See the corruption trap below — this one bit the reference fix itself.
10. **Commit the scoring harness, and pin its refs to COMMITS.** A PR that cites coverage numbers
    from an uncommitted scratch script is asking a reviewer to take them on faith. Keep the
    stopword list small and inline: a large one is a free parameter that can be tuned until the
    numbers look good. And write `--old <sha>:path --new <sha>:path`, never `--old main:path` —
    that is correct only while the trim is unmerged. Once it lands, `main` *becomes* the post-trim
    state and the same command prints `0.5198 → 0.5198`, a table of zero deltas that reads as
    though it refutes the table above it. This happened to `claude-ecosystem-hygiene`.

11. **`--compare` only sees DOUBLE-QUOTED spans.** `extract_triggers()` matches `"..."` and
    `“...”` and nothing else, so **backticked literals are invisible to it** — error strings,
    flags, file paths. An empty `DROPPED` table is not proof that no trigger was lost.
    `publish-skill`'s own 2,385 → 1,503 trim silently removed three backticked error literals and
    `--compare` reported 0 dropped. Diff the backticked spans of the **description** by hand too
    (a whole-file diff finds nothing, because the body usually still carries them):
    ```bash
    desclit() { python3 -c '
    import re,sys
    t=open(sys.argv[1]).read() if len(sys.argv)>1 else sys.stdin.read()
    fm=re.match(r"^---\n([\s\S]*?)\n---",t).group(1)
    d=re.search(r"(?m)^description:\s*[|>]-?\s*\n((?:[ \t]+.*\n?)*)",fm).group(1)
    d=" ".join(l.strip() for l in d.split("\n") if l.strip())
    print("\n".join(sorted(set(re.findall(r"`([^`\n]{3,90})`",d)))))
    ' "$@"; }

    diff <(git show main:<path/SKILL.md> | desclit) <(desclit <path/SKILL.md>)
    ```

### If you vendor this gate, pin a DIGEST — not a feature grep
Six repos copy `check_skill_descriptions.py` in. A vendored copy rots silently, so each one wants
a guard. **Do not write that guard as a feature-presence grep.**

`publish-skill` had a test named *"the vendored gate is current with upstream, not a stale fork"*
asserting the file contained `find_wrap_corruption(`, `compare_descriptions(` and
`MAX_DESC_CHARS - 1)`. Its copy **was** a stale fork — a revision whose `find_wrap_corruption()`
reported a bogus `BROKEN BY LINE-WRAP` on every `description: >-` skill. All three substrings were
present, because the drift was *inside* a function whose name never changed. **The test stayed
green through the entire drift.** A feature grep answers "does this version have the feature",
never "is this the version I vendored".

Wrap the local note in strip markers and hash the remainder:

```js
const OPEN  = '--8<-- vendoring note (local addition; stripped before the parity hash) --8<--\n';
const CLOSE = '--8<-- end vendoring note --8<--\n\n';
const s = local.indexOf(OPEN), e = local.indexOf(CLOSE, s);
const stripped = local.slice(0, s) + local.slice(e + CLOSE.length);
assert.equal(createHash('sha256').update(stripped, 'utf8').digest('hex'), UPSTREAM_SHA256);
```

Then **name the test for what it proves** — "matches the upstream revision it was vendored from",
not "is current with upstream" — and say so in the body: this **can** see local edits and drift
from the pin; it **cannot** see upstream moving on, because CI has no access to this repo.
Re-vendoring stays a deliberate act. Prove the guard works by restoring the old copy and watching
it go red.

The note should also record that a version like `2.3.0` here is a `plugin.json`/`marketplace.json`
version, **not a git tag** — this repo's newest tag is `v2.0.0`, and "v2.2.0" in six downstream
repos meant a commit subject.

### The line-wrap corruption trap (silent, and no length check can see it)
A `>` folded or `|` block scalar joins its lines with a **space** — and Python's `textwrap.wrap()`
breaks on hyphens **by default**. Re-wrapping a description therefore splits hyphenated tokens
across lines, and the harness injects them broken:
```
"high- stakes"              was "high-stakes"
"token- efficient review"   was "token-efficient review"
```
Both were *trigger phrases in the very fix that was restoring triggers.* The character count is
identical, so a cap check passes and a coverage score barely moves. `check_skill_descriptions.py`
now flags any folded-scalar line ending in a hyphen followed by an alphanumeric (`BROKEN BY
LINE-WRAP`) and fails the gate on it. Independently observed in two different repos this session —
assume it is present wherever descriptions have been machine-wrapped.

### Word-overlap scoring has a blind spot; `--compare` covers it
Bag-of-words coverage cannot see **trigger-condition restructuring**. Rewriting
`trigger on X — separately, watch for Y` into `trigger on X WHOSE Y` preserves the identical word
set, so any overlap metric scores it **identically** — while the trigger now only fires for users
who have *already diagnosed* Y. That is a narrowed trigger surface passing a green metric.
```bash
python3 scripts/check_skill_descriptions.py --compare main:path/SKILL.md path/SKILL.md
```
Pairs each trigger old→new (fuzzy, so a rephrasing does not read as drop+add) and reports
`DROPPED` / `NARROWED` / `REWORDED` / `REPHRASED`. **`NARROWED` and `REWORDED` need a human read —
do not clear them with a coverage number.**

### The cap is necessary, NOT sufficient — do not overclaim
Two independent limits gate a description. Getting under `skillListingMaxDescChars` only means it
is *no longer truncated*; `skillListingBudgetFraction` can still collapse it to a bare name because
the whole listing is over budget, and that collapse is **usage-ranked**, not length-ranked. On a
real 18-plugin install only ~41% of descriptions survive the budget at 1M context. So "restored N
triggers" is honest only as *"no longer truncated"* — never as *"guaranteed visible"*. State both
limits, or the headline claim is contingent on a fact the PR never checked.

**Regression archaeology — find WHEN the cap broke.** Walk the description length across history; the breach
commit is usually a feature that appended triggers without checking:
```bash
git log --format='%H %s' --reverse   # extract the description at each commit, flag the first over the cap
```
On `agent-review-panel` this exposed the sharpest failure mode of all: the breach was v2.14, and **v3.7.1 — a
release whose entire stated purpose was "broaden budget-mode triggers for discoverability" — added five phrases
that ALL landed past the cut.** It shipped, was documented, changelogged, and delivered exactly nothing.
*Adding triggers to an already-over-cap description is not a no-op; it is a silent no-op that reads as a
feature.* Check the cap before writing a discoverability release.

## Optional: interactive recap report (`scripts/render_treatment_report.py`)
After a treatment, render a self-contained, interactive HTML recap (reads `.claude/settings.json` + the skills dir,
computes counts + the bare-name token estimate; clickable tiles → a searchable explorer of every skill by decision).
Honest-by-construction; opens from `file://`.
```bash
# Resolve across all three install roots. A plugin install creates neither of the first two.
S="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/skills/context-police/scripts/render_treatment_report.py}"
[ -f "$S" ] || S="$HOME/.claude/skills/context-police/scripts/render_treatment_report.py"
[ -f "$S" ] || S="$(find -L "$HOME/.claude/plugins/cache" -mindepth 7 -maxdepth 7 \
    -path '*/context-police/*/skills/context-police/scripts/render_treatment_report.py' 2>/dev/null \
  | awk -F/ '{print $(NF-4)"\t"$0}' | sort -V -k1,1 | tail -1 | cut -f2-)"

if [ -f "$S" ]; then
  python3 "$S" \
    --settings .claude/settings.json [--skills-dir ~/.claude/skills] \
    [--decisions panel-decisions.json] [--title "My Project"] [--out skill-treatment.html]
else
  echo "render_treatment_report.py: not found - tried \$CLAUDE_PLUGIN_ROOT/skills/context-police/scripts/, ~/.claude/skills/context-police/scripts/, and the plugin cache"
fi
```
**Why three roots.** A plugin install lands under `~/.claude/plugins/cache/<marketplace>/context-police/<version>/`,
so `~/.claude/skills/context-police/` does not exist and a single hardcoded root silently misses. `CLAUDE_PLUGIN_ROOT`
does not rescue it on its own — it is often unset in the shell a step runs in, and it points at the *calling* plugin's
root, so it can never reach a sibling. Four details in the snippet are load-bearing: rank on the **version segment
alone** (`$(NF-4)`) because the marketplace segment precedes the version and a plain `sort -V` over whole paths would
let `aaa-mkt/2.5.0` lose to `zzz-mkt/1.0.0`; use `find`, not a glob, because zsh's `nomatch` fails a non-matching glob
*before* `2>/dev/null` can apply; guard **before** any `> "$OUT"` redirect, since the shell creates and truncates the
file before the command runs and leaves a 0-byte file that reads as a real record; and say *"not found - tried
&lt;paths&gt;"* rather than *"not installed"* — a failed lookup is not evidence about install state, and a bare "not
installed" has already been misread by a human as proof a skill was absent.

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
