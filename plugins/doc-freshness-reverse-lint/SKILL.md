---
name: doc-freshness-reverse-lint
description: |
  Detect stale normative guidance after the user adds a NEW "don't X / avoid Y"
  rule to ~/.claude/lessons.md, ~/.claude/axioms.md, or any
  ~/.claude/projects/<slug>/memory/feedback_*.md. Also audits ~/.claude/skills/
  for skills whose `last_verified` frontmatter has expired or that opt into a
  freshness contract without declaring one (axiom #21). ALSO detects the
  retirement case (v1.3.0): a rule that was RETIRED but whose CONDITION survives
  in the docs as a live-looking branch ("X is retired — but it still applies if
  you are a Y") after no Y exists. Trigger when: (1) a
  PostToolUse hook fires on Edit|Write to one of those memory files and the diff
  contains a new negation rule OR a retirement; (2) user asks "are my project docs still consistent
  with my lessons / feedback?", "any stale advice in docs/?", "run doc freshness audit",
  "any stale skills?", "did retiring that rule leave anything behind?"; (3) weekly cron audit is due. Produces a list of CANDIDATE
  stale claims — file:line refs only. NEVER auto-edits. Conservative by design:
  for prose lint, surfaces only when the new rule has an explicit negation
  (don't / never / avoid / stop) AND a multi-token searchable phrase AND ≥1 grep hit.
  For skill freshness, the default mode flags only on EXPLICIT frontmatter signals
  (expired `last_verified`, or `scope: project-specific` without `last_verified`);
  the heuristic project-marker scan is opt-in via `--scan-untagged`. If zero hits,
  the skill exits silent.
author: Claude (for Huiyan, 2026-04-24)
version: 1.4.0
date: 2026-08-06
---

# Doc Freshness Reverse-Lint

## Problem

Huiyan's project docs under `docs/{research,decisions,findings,runbooks}/` contain normative
guidance. When she later corrects that guidance in `~/.claude/lessons.md` or a
`feedback_*.md` entry, the original project docs stay stale. Future Claude sessions
read them as authoritative and repeat the retracted advice.

Real example: `the-causal-impact-repo/docs/research/pre_period_length_methodology.md:92,98`
referenced "sorting by p-value" after the user had already decided that approach was wrong.

**And a second shape the grep above cannot see (added v1.3.0).** A rule is not
always *contradicted* — sometimes it is **retired**, and the docs that carried it
keep a **scoped survivor**: *"X is retired — but it still applies if you are a
Y."* That reads as current guidance, and it is dead the moment no Y exists.

Real example (DoodleRun, 2026-08-04): *"no deploys by agents"* was retired across
four live briefs, and every retirement kept *"a cloud session still cannot"* as a
live branch — after cloud sessions had stopped existing. The next reader would
have paused to work out which kind of session it was instead of just deploying.
**The retirement was correct; the surviving condition was the defect.** The
owner caught it by hand, one turn after the retirement shipped.

## Mechanisms

### 1. Reverse-lint (primary, event-driven)

Runs when a negation rule is added to a memory file. Extracts the "don't X" phrase,
greps project docs, lists matches. Does NOT edit.

### 1b. Dead-branch detection (v1.3.0, runs with the reverse-lint)

Same trigger, different question. Where mechanism 1 asks *"does any doc still
assert the thing you just forbade?"*, this asks **"does any doc still carry the
CONDITION of a rule you just retired?"**

THREE explicit signals, ANDed — a scoped survivor is often perfectly legitimate,
and only a human knows whether the branch can still fire:

1. a **retirement trigger** in the memory file (`retired`, `superseded`,
   `no longer applies`, `is dead`, …);
2. a **quoted subject** within 160 chars either side of it — retirement prose
   nearly always quotes the rule it retires (`"..."`, `'...'`, `` `...` ``,
   `**...**`), and the quote must be ≥ 2 tokens and not a path or filename;
3. a doc **paragraph** containing that subject with a **surviving-conditional
   marker after it** (`still cannot`, `only applies`, `unless you`, `except
   when`, `if you are a`, `remains true for`, …).

Scope is the **paragraph**, not the line, because markdown prose wraps and the
retirement and its condition routinely sit on different lines of one block.

**Known limit, stated rather than tuned away:** two unrelated sentences sharing
one paragraph — one mentioning the retired rule, one carrying an unrelated
conditional — will co-occur and be surfaced. That is why the output is a
CANDIDATE with the question attached and never an edit. The script cannot know
whether a branch can still fire; that is precisely the judgment being asked for.

**Not seen-cached**, unlike mechanism 1. A dead branch is a property of the
DOCS, which keep changing under a rule that was retired once, so re-surfacing
after a doc edit is correct rather than chatty.

### 2. Weekly cron audit (safety net)

Scans `docs/**/*.md` for normative claims, cross-checks against recent `lessons.md`
entries, flags contradictions.

### 3. Skill freshness audit (per axiom #21)

**Design only — `skill_freshness_audit.py` is not bundled in this marketplace copy.**
The scripts that ship here are `reverse_lint.py`, `weekly_audit.py`, and
`hook_dispatch.sh`. The rest of this section describes the intended mechanism, not a
script you can run.

Scans `~/.claude/skills/<name>/SKILL.md` for two explicit signals:

- **`last_verified` exceeded `staleness_window_days`** (default 90): the skill
  declared a freshness contract and has aged past it. Re-verify the cited config
  / CLI surface and bump `last_verified`.
- **`scope: project-specific` without `last_verified`**: the skill declared
  itself project-scoped but didn't supply the freshness contract that scope
  requires. Add `last_verified: YYYY-MM-DD` (and optionally `staleness_window_days`).

Default mode is **silent unless explicit signals are present** — zero false
positives on skills that opted out of the freshness contract. An opt-in
`--scan-untagged` mode runs a tighter heuristic scan (3-part BQ refs requiring a
hyphen in the project segment, GCS/GCR URIs, real user paths, `--project=`
flags) over skills that have NO `last_verified` at all, surfacing candidates for
manual tagging. Use the heuristic mode for periodic audit; never wire it into a
hook (its precision is too low for real-time interrupt).

### 4. Invocation by `session-handoff` (v1.2.0+)

`session-handoff` invokes both mechanisms at end-of-session:

- **Phase 4 step 24** runs `reverse_lint.py` against every `lessons.md` /
  `axioms.md` / `feedback_*.md` touched this session. Candidates appear in a
  "Stale docs to review" section of the handoff doc.
- **Phase 4 step 24b** would run `skill_freshness_audit.py` when any SKILL.md was
  edited this session, flagging expired `last_verified` and project-scoped
  skills missing the freshness contract. That script is **not bundled in this
  marketplace copy** (see mechanism 3), so this step is a no-op here.

Both are non-blocking: zero candidates → exit silent. A lookup that misses must be
reported as **"not found - tried <paths>"** with the roots it searched, never as
"not installed" — see Invocation step 0 for the three roots that must all be tried.
`session-handoff` Phase 6 surfaces non-empty candidates back to the user in the
live-dashboard recap when relevant.

### 5. Invocation by `memory-hygiene` (v3.3+)

After a `memory-hygiene` taxonomy migration (§1j moves files between buckets),
run `reverse_lint.py` on the migration commit to catch references in handoff
docs, plans, or skills that hard-code the old path.

## Invocation

### Step 0 — resolve the script path (required, run this first)

**Never invoke these scripts through `~/.claude/skills/…` alone.** A plugin install
unpacks to `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` and creates
neither `~/.claude/skills/<plugin>/` nor a set `$CLAUDE_PLUGIN_ROOT` (that variable
is usually unset in the shell a step actually runs in, and it points at the *calling*
plugin's own root, so it can never reach a sibling plugin). A hardcoded
`~/.claude/skills/` path simply misses, and the usual "log and continue" fallback
makes the step do nothing while the summary still reads clean.

Paste this helper into the same shell before any invocation below:

```bash
# Resolve a bundled script across all three install roots.
# Usage: S="$(dfrl_script reverse_lint.py)"
dfrl_script() {
  local n="$1" s=""
  s="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/scripts/$n}"
  [ -f "$s" ] || s="$HOME/.claude/skills/doc-freshness-reverse-lint/scripts/$n"
  # find, not a shell glob: under zsh a non-matching glob fails at expansion time,
  # BEFORE 2>/dev/null can apply, and prints a raw shell error.
  # Rank on the VERSION segment alone (the awk) — the marketplace name precedes the
  # version in the path, so a plain `sort -V` over whole paths ranks by marketplace
  # name and lets aaa-mkt/2.5.0 lose to zzz-mkt/1.0.0.
  [ -f "$s" ] || s="$(find -L "$HOME/.claude/plugins/cache" -mindepth 5 -maxdepth 5 \
      -path "*/doc-freshness-reverse-lint/*/scripts/$n" 2>/dev/null \
    | awk -F/ '{print $(NF-2)"\t"$0}' | sort -V -k1,1 | tail -1 | cut -f2- || true)"
  [ -f "$s" ] && printf '%s\n' "$s"
}
```

### Invocations

```bash
# Reverse-lint a specific memory file (project scope inferred from path)
S="$(dfrl_script reverse_lint.py)"
if [ -n "$S" ]; then
  python3 "$S" <memory-file-path> [--project-root PATH] [--rescan]
else
  echo "reverse_lint.py: not found - tried \$CLAUDE_PLUGIN_ROOT/scripts/, ~/.claude/skills/doc-freshness-reverse-lint/scripts/, and the plugin cache"
fi

# Weekly audit over a project
S="$(dfrl_script weekly_audit.py)"
if [ -n "$S" ]; then
  python3 "$S" --project-root /Users/<user>/Documents
else
  echo "weekly_audit.py: not found - tried \$CLAUDE_PLUGIN_ROOT/scripts/, ~/.claude/skills/doc-freshness-reverse-lint/scripts/, and the plugin cache"
fi
```

**Always guard BEFORE redirecting.** `python3 "$S" … > "$OUT"` creates and truncates
`$OUT` before the command is exec'd, so an unguarded call on a failed lookup leaves a
0-byte file that a later step reads as a real, empty result. Put the redirect inside
the `if`, never outside it.

Report a failed lookup as **"not found - tried <paths>"**, never as "not installed".
A lookup that missed is not evidence about install state, and a bare "not installed"
has already been misread by a human as proof that a skill was absent.

**`skill_freshness_audit.py` (mechanism 3) is not bundled in this marketplace copy.**
It is described below because the mechanism is part of the skill's design, but
`plugins/doc-freshness-reverse-lint/scripts/` ships only `reverse_lint.py`,
`weekly_audit.py`, and `hook_dispatch.sh` — there is no path, under any install
method, at which the freshness-audit script exists. Do not invoke it and do not
report it as installed-but-unfound; treat mechanism 3 as unimplemented here.

Exit codes: `0` = ran cleanly (zero or more candidates). Candidate JSON goes to stdout;
`--human` flag switches to terminal-friendly output.

## Conservative guardrails (non-negotiable)

1. **Explicit negation only.** Rule must match `\b(don't|do not|never|avoid|stop|no longer)\b`
   followed by a verb + object phrase. Positive rules ("always X") are ignored.
2. **Multi-token phrase.** Extracted search phrase must be ≥ 2 content tokens
   (reverse-lint) or ≥ 3 content tokens (weekly audit, broader scope).
3. **One phrase per rule.** Extract only the TITLE-level negation (or first
   body negation if title has none). Rules often contain multiple rephrasings
   of the same idea ("don't X" in title + "avoid the X" in body) — surfacing
   all of them inflates false positives on qualified docs.
4. **De-dup via seen-cache.** Already-processed `(rule_id, phrase, project_root)` tuples
   are skipped. Cache at `~/.claude/state/reverse-lint-seen.json`. Pass `--rescan` to bypass.
4. **Silent on zero hits.** If no project-doc matches, the script prints nothing and the
   hook emits no systemMessage. Huiyan dislikes chatty skills.
5. **Never auto-edit.** Output is always file:line references. The human decides what to update.
6. **Dead-branch detection needs all THREE signals** (retirement trigger +
   quoted subject + surviving conditional in the same paragraph). A retirement
   with no quoted subject, or a doc mention with no conditional attached, is
   silent — the common case of "this doc simply mentions the old rule as
   history" must not fire.

## Hook wiring (PostToolUse on Edit|Write)

A `settings.json` hook command is a literal string — it cannot resolve anything at
fire time, and a wrong path fails **silently**: the hook simply never produces
output and nothing tells you it did not run. So resolve the path once, then paste
the result.

**Step 1 — print the real path** (uses the `dfrl_script` helper from Invocation step 0):

```bash
dfrl_script hook_dispatch.sh || echo "hook_dispatch.sh: not found - tried \$CLAUDE_PLUGIN_ROOT/scripts/, ~/.claude/skills/doc-freshness-reverse-lint/scripts/, and the plugin cache"
```

**Step 2 — paste that absolute path** into `~/.claude/settings.json` under
`hooks.PostToolUse[matcher="Edit|Write"].hooks`:

```json
{
  "type": "command",
  "command": "<absolute path printed by step 1>",
  "timeout": 10
}
```

Only write the literal `~/.claude/skills/doc-freshness-reverse-lint/scripts/hook_dispatch.sh`
if step 1 actually printed it — that path exists only when the skill was copied in
by hand, not when it was installed as a plugin.

**Re-run step 1 after every plugin upgrade.** A plugin-cache path contains the
version segment (`…/doc-freshness-reverse-lint/1.4.0/scripts/…`), so upgrading
leaves the pinned hook pointing at the old version's directory, or at nothing once
the old version is pruned.

The dispatcher:
- Reads `tool_input.file_path` from stdin.
- Exits silently unless the file matches `lessons.md`, `axioms.md`, or `feedback_*.md` under
  a `~/.claude/projects/*/memory/` path.
- Runs `reverse_lint.py` and, if candidates exist, emits a
  `hookSpecificOutput.additionalContext` block listing them so the current session sees
  them mid-flow.

## Weekly cron

Use `mcp__scheduled-tasks__create_scheduled_task` with cron `0 9 * * 1` (Mon 09:00) to run:

```bash
# dfrl_script is the helper from Invocation step 0 — a cron shell has no
# $CLAUDE_PLUGIN_ROOT and a plugin install has no ~/.claude/skills/ entry, so the
# path must be resolved at run time, inside the scheduled command itself.
S="$(dfrl_script weekly_audit.py)"
if [ -n "$S" ]; then
  python3 "$S" --project-root /Users/<user>/Documents --max-age-days 30
else
  echo "weekly_audit.py: not found - tried \$CLAUDE_PLUGIN_ROOT/scripts/, ~/.claude/skills/doc-freshness-reverse-lint/scripts/, and the plugin cache"
fi
```

If the scheduled command runs in a shell that has not sourced `dfrl_script`, inline
the helper's body into the same command rather than falling back to a fixed path.

The audit:
- Extracts all `### NN.` negation rules added to `lessons.md` in the last 30 days
  (by git blame if available, else by file-position proxy).
- Cross-checks against normative claims in project docs (sentences starting with imperative
  verbs or containing "should", "must", "use X").
- Flags literal phrase matches and near-duplicate phrasings (≥ 70% token overlap).

## Output schema

```json
{
  "memory_file": "/Users/<user>/.claude/lessons.md",
  "project_root": "/Users/<user>/Documents",
  "candidates": [
    {
      "rule_id": "#147",
      "rule_title": "When user provides empirical counter-evidence...",
      "negated_phrase": "sort by p-value",
      "matches": [
        {"file": "the-causal-impact-repo/docs/research/pre_period_length_methodology.md",
         "line": 92,
         "content": "Sorting by p-value is acceptable provided..."}
      ]
    }
  ],
  "dead_branch_candidates": [
    {
      "retired_subject": "no deploys by agents",
      "question": "'no deploys by agents' is retired — does the condition this paragraph scopes it to still occur? If not, the branch is dead and reads as current guidance.",
      "matches": [
        {"file": "docs/runbooks/deploy_thing.md",
         "line": 3,
         "content": "\"No deploys by agents\" is retired. A cloud session still cannot: no"}
      ]
    }
  ]
}
```

`dead_branch_candidates` is always present and is `[]` when nothing fires — the
skill stays silent overall only when BOTH lists are empty.

## Validation

Validation case already documented in `evals/validation_case.md`. Expected result:
the file `the-causal-impact-repo/docs/research/pre_period_length_methodology.md` currently
does NOT contain the literal phrase "sort by p-value" (the user has already rephrased),
so a rule with that negated phrase must produce zero candidates. This confirms the
conservative guardrails (no false positives on qualified or rephrased content).

**Dead-branch validation** (`evals/fixtures/project_with_dead_branch/`): a
runbook retiring *"no deploys by agents"* while keeping *"a cloud session still
cannot"* MUST be flagged; a sibling doc mentioning the same retired rule with no
condition attached MUST NOT be. Both assertions run off one fixture pair.

## What this skill does NOT do

- Does not read or interpret policy docs beyond literal + stem-normalized grep.
- Does not modify any file. Skill freshness audit is read-only too — it never edits frontmatter or bumps `last_verified` for you.
- Does not replace manual review — every candidate needs a human judgment.
- Does not scan code. Reverse-lint and weekly-audit scan `.md` under specified doc roots + project `MEMORY.md`. Skill freshness audit scans `~/.claude/skills/<name>/SKILL.md` only (not `scripts/` or `evals/` inside skill bundles).
- The `--scan-untagged` heuristic is opt-in for audit; do NOT wire it into a PostToolUse hook (precision is too low for real-time interrupt).
