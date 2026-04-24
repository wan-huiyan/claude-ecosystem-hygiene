---
name: doc-freshness-reverse-lint
description: |
  Detect stale normative guidance in project docs/ after the user adds a NEW "don't X / avoid Y"
  rule to ~/.claude/lessons.md, ~/.claude/axioms.md, or any
  ~/.claude/projects/<slug>/memory/feedback_*.md. Trigger when: (1) a PostToolUse hook fires on
  Edit|Write to one of those memory files and the diff contains a new negation rule;
  (2) user asks "are my project docs still consistent with my lessons / feedback?",
  "any stale advice in docs/?", "run doc freshness audit"; (3) weekly cron audit is due.
  Produces a list of CANDIDATE stale claims — file:line refs only. NEVER auto-edits. Conservative
  by design: only surfaces when the new rule has an explicit negation (don't / never / avoid / stop)
  AND a multi-token searchable phrase AND ≥1 grep hit in project docs/{research,decisions,findings,runbooks}/
  or project MEMORY.md. If zero hits, the skill exits silent — do not announce "nothing to do".
author: Claude (for Huiyan, 2026-04-24)
version: 1.0.0
date: 2026-04-24
---

# Doc Freshness Reverse-Lint

## Problem

Huiyan's project docs under `docs/{research,decisions,findings,runbooks}/` contain normative
guidance. When she later corrects that guidance in `~/.claude/lessons.md` or a
`feedback_*.md` entry, the original project docs stay stale. Future Claude sessions
read them as authoritative and repeat the retracted advice.

Real example: `schuh_causal_impact/docs/research/pre_period_length_methodology.md:92,98`
referenced "sorting by p-value" after the user had already decided that approach was wrong.

## Mechanisms

### 1. Reverse-lint (primary, event-driven)

Runs when a negation rule is added to a memory file. Extracts the "don't X" phrase,
greps project docs, lists matches. Does NOT edit.

### 2. Weekly cron audit (safety net)

Scans `docs/**/*.md` for normative claims, cross-checks against recent `lessons.md`
entries, flags contradictions.

## Invocation

```bash
# Reverse-lint a specific memory file (project scope inferred from path)
python3 ~/.claude/skills/doc-freshness-reverse-lint/scripts/reverse_lint.py \
    <memory-file-path> [--project-root PATH] [--rescan]

# Weekly audit over a project
python3 ~/.claude/skills/doc-freshness-reverse-lint/scripts/weekly_audit.py \
    --project-root /Users/huiyanwan/Documents
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
    --project-root /Users/huiyanwan/Documents --max-age-days 30
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
  "memory_file": "/Users/huiyanwan/.claude/lessons.md",
  "project_root": "/Users/huiyanwan/Documents",
  "candidates": [
    {
      "rule_id": "#147",
      "rule_title": "When user provides empirical counter-evidence...",
      "negated_phrase": "sort by p-value",
      "matches": [
        {"file": "schuh_causal_impact/docs/research/pre_period_length_methodology.md",
         "line": 92,
         "content": "Sorting by p-value is acceptable provided..."}
      ]
    }
  ]
}
```

## Validation

Validation case already documented in `evals/validation_case.md`. Expected result:
the file `schuh_causal_impact/docs/research/pre_period_length_methodology.md` currently
does NOT contain the literal phrase "sort by p-value" (the user has already rephrased),
so a rule with that negated phrase must produce zero candidates. This confirms the
conservative guardrails (no false positives on qualified or rephrased content).

## What this skill does NOT do

- Does not read or interpret policy docs beyond literal + stem-normalized grep.
- Does not modify any file.
- Does not replace manual review — every candidate needs a human judgment.
- Does not scan code, only `.md` under the specified doc roots + project `MEMORY.md`.
