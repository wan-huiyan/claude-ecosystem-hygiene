---
name: doc-freshness-reverse-lint
description: |
  Detect stale normative guidance after the user adds a NEW "don't X / avoid Y"
  rule to ~/.claude/lessons.md, ~/.claude/axioms.md, or any
  ~/.claude/projects/<slug>/memory/feedback_*.md. Also audits ~/.claude/skills/
  for skills whose `last_verified` frontmatter has expired or that opt into a
  freshness contract without declaring one (axiom #21). Trigger when: (1) a
  PostToolUse hook fires on Edit|Write to one of those memory files and the diff
  contains a new negation rule; (2) user asks "are my project docs still consistent
  with my lessons / feedback?", "any stale advice in docs/?", "run doc freshness audit",
  "any stale skills?"; (3) weekly cron audit is due. Produces a list of CANDIDATE
  stale claims — file:line refs only. NEVER auto-edits. Conservative by design:
  for prose lint, surfaces only when the new rule has an explicit negation
  (don't / never / avoid / stop) AND a multi-token searchable phrase AND ≥1 grep hit.
  For skill freshness, the default mode flags only on EXPLICIT frontmatter signals
  (expired `last_verified`, or `scope: project-specific` without `last_verified`);
  the heuristic project-marker scan is opt-in via `--scan-untagged`. If zero hits,
  the skill exits silent.
author: Claude (for Huiyan, 2026-04-24)
version: 1.2.0
date: 2026-05-15
---

# Doc Freshness Reverse-Lint

## Problem

Huiyan's project docs under `docs/{research,decisions,findings,runbooks}/` contain normative
guidance. When she later corrects that guidance in `~/.claude/lessons.md` or a
`feedback_*.md` entry, the original project docs stay stale. Future Claude sessions
read them as authoritative and repeat the retracted advice.

Real example: `the-causal-impact-repo/docs/research/pre_period_length_methodology.md:92,98`
referenced "sorting by p-value" after the user had already decided that approach was wrong.

## Mechanisms

### 1. Reverse-lint (primary, event-driven)

Runs when a negation rule is added to a memory file. Extracts the "don't X" phrase,
greps project docs, lists matches. Does NOT edit.

### 2. Weekly cron audit (safety net)

Scans `docs/**/*.md` for normative claims, cross-checks against recent `lessons.md`
entries, flags contradictions.

### 3. Skill freshness audit (per axiom #21)

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
- **Phase 4 step 24b** runs `skill_freshness_audit.py` when any SKILL.md was
  edited this session, flagging expired `last_verified` and project-scoped
  skills missing the freshness contract.

Both are non-blocking: zero candidates → exit silent; script not installed →
log and continue. `session-handoff` Phase 6 surfaces non-empty candidates back
to the user in the live-dashboard recap when relevant.

### 5. Invocation by `memory-hygiene` (v3.3+)

After a `memory-hygiene` taxonomy migration (§1j moves files between buckets),
run `reverse_lint.py` on the migration commit to catch references in handoff
docs, plans, or skills that hard-code the old path.

## Invocation

```bash
# Reverse-lint a specific memory file (project scope inferred from path)
python3 ~/.claude/skills/doc-freshness-reverse-lint/scripts/reverse_lint.py \
    <memory-file-path> [--project-root PATH] [--rescan]

# Weekly audit over a project
python3 ~/.claude/skills/doc-freshness-reverse-lint/scripts/weekly_audit.py \
    --project-root /Users/<user>/Documents

# Skill freshness audit (default — silent unless explicit signals present)
python3 ~/.claude/skills/doc-freshness-reverse-lint/scripts/skill_freshness_audit.py \
    [--human] [--max-age-days 90] [--skills-root ~/.claude/skills]

# Skill freshness audit with heuristic scan over untagged skills (audit-only)
python3 ~/.claude/skills/doc-freshness-reverse-lint/scripts/skill_freshness_audit.py \
    --scan-untagged --human
```

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

## Hook wiring (PostToolUse on Edit|Write)

Add to `~/.claude/settings.json` under `hooks.PostToolUse[matcher="Edit|Write"].hooks`:

```json
{
  "type": "command",
  "command": "~/.claude/skills/doc-freshness-reverse-lint/scripts/hook_dispatch.sh",
  "timeout": 10
}
```

The dispatcher:
- Reads `tool_input.file_path` from stdin.
- Exits silently unless the file matches `lessons.md`, `axioms.md`, or `feedback_*.md` under
  a `~/.claude/projects/*/memory/` path.
- Runs `reverse_lint.py` and, if candidates exist, emits a
  `hookSpecificOutput.additionalContext` block listing them so the current session sees
  them mid-flow.

## Weekly cron

Use `mcp__scheduled-tasks__create_scheduled_task` with cron `0 9 * * 1` (Mon 09:00) to run:

```
python3 ~/.claude/skills/doc-freshness-reverse-lint/scripts/weekly_audit.py \
    --project-root /Users/<user>/Documents --max-age-days 30
```

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
  ]
}
```

## Validation

Validation case already documented in `evals/validation_case.md`. Expected result:
the file `the-causal-impact-repo/docs/research/pre_period_length_methodology.md` currently
does NOT contain the literal phrase "sort by p-value" (the user has already rephrased),
so a rule with that negated phrase must produce zero candidates. This confirms the
conservative guardrails (no false positives on qualified or rephrased content).

## What this skill does NOT do

- Does not read or interpret policy docs beyond literal + stem-normalized grep.
- Does not modify any file. Skill freshness audit is read-only too — it never edits frontmatter or bumps `last_verified` for you.
- Does not replace manual review — every candidate needs a human judgment.
- Does not scan code. Reverse-lint and weekly-audit scan `.md` under specified doc roots + project `MEMORY.md`. Skill freshness audit scans `~/.claude/skills/<name>/SKILL.md` only (not `scripts/` or `evals/` inside skill bundles).
- The `--scan-untagged` heuristic is opt-in for audit; do NOT wire it into a PostToolUse hook (precision is too low for real-time interrupt).
