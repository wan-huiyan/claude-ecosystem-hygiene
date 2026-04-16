---
name: skill-trigger-eval-subprocess-blindness
description: |
  Diagnose 0% recall results from skill-creator's trigger evaluation loop
  (`run_loop.py` / `run_eval.py`). Use when: (1) every should-trigger query reports
  `rate=0/3 expected=True [FAIL]` while every should-not-trigger query passes,
  (2) precision is 100% but recall is 0% across 5+ iterations, (3) "ALWAYS use this
  skill" front-loaded descriptions still don't fire, (4) you're tempted to
  conclude the description is broken when it actually isn't. The eval harness
  spawns `claude -p` subprocesses with NO `~/.claude/projects/` history and NO
  project cwd context. Skills that handle ecosystem-introspection or
  questions-Claude-can-answer-directly (e.g., "how many skills do I have")
  systematically fail subprocess eval but trigger fine in real interactive
  sessions. Do NOT rewrite the description in response to 0% recall — verify
  the eval methodology first.
author: Claude Code
version: 1.0.0
date: 2026-04-16
---

# Skill Trigger Eval: Subprocess Blindness

## Problem

Skill-creator's trigger optimization tools (`scripts/run_loop.py`, `scripts/run_eval.py`)
report **0% recall** for skills that handle introspection, ecosystem-audit, or
questions Claude can answer with shell commands directly — even when the description
is well-written, front-loaded with "ALWAYS use this skill", and clearly relevant.

The natural response is to make the description more aggressive, then more aggressive
again. This is wasted effort. The eval harness has a structural blind spot.

## Context / Trigger Conditions

You're hitting this if you see ALL of:

- **Train accuracy stuck at exactly 50%** (all positives fail, all negatives pass)
- **Precision 100%, Recall 0%** every iteration
- Failure pattern reads `[FAIL] rate=0/3 expected=True` for every should-trigger query
- The description already contains the literal phrases from the queries (e.g.,
  description mentions "how many skills do I have", query is "how many skills do
  i have installed")
- Rewriting the description harder doesn't move the numbers

Common skill domains affected:
- Ecosystem audits / introspection (e.g., `ecosystem-audit`, `memory-hygiene`)
- "Show me my X" / "list my Y" / "audit my Z" workflows
- Skills whose value-add is *aggregating* data Claude could fetch piecemeal
- Diagnostic skills triggered by symptom phrases

## Root Cause

`run_eval.py` shells out to `claude -p "<query>"` for each test query, three times
per query. That subprocess starts:

- In an arbitrary working directory (NOT the user's project)
- With **no session history** — `~/.claude/projects/` JSONL files exist but the
  fresh subprocess has no prior context
- With no MEMORY.md, no axioms.md tier-loaded for any specific project

For a query like *"how many skills do I have installed"*, subprocess Claude has two
options:
1. Consult an audit skill (which it sees in `available_skills`)
2. Just run `ls ~/.claude/skills/ | wc -l` and answer

It picks option 2 every time, because that's the cheaper, more direct response.
Skills "consult only for tasks they can't easily handle" — and from the
subprocess's perspective, the question is trivial.

The framework is measuring the wrong thing for these skills. It works fine for
skills that operate on user-supplied files, error messages, or domain-specific
contexts the subprocess can't synthesize.

## Solution

### When you hit 0% recall

1. **Don't reflexively rewrite the description.** First check whether the eval is
   capable of measuring what you care about.

2. **Manually invoke the skill in your real interactive session** to verify it's
   discoverable. Type one of the should-trigger queries verbatim. If Claude triggers
   it, the description is fine — the eval is blind.

3. **If the manual test ALSO fails to trigger**, the description genuinely needs
   work. Common fixes:
   - Front-load with "ALWAYS use this skill when..."
   - List exact symptom phrases in numbered groups
   - Reference complementary skills explicitly so Claude routes correctly

4. **Trust real-session usage data over subprocess eval results** for
   introspection/audit skills. After 30 days of real use, run
   `parse_skill_usage.py` (from the ecosystem-audit skill) on JSONL logs to see
   actual invocation counts. That's the ground truth.

### When the eval is appropriate

The eval framework gives reliable results for skills that:
- Process user-provided files (PDFs, spreadsheets, code)
- Fix specific error messages with verbatim text
- Generate domain-specific artifacts (Terraform, K8s YAML, slides)
- Operate in well-defined languages/frameworks the subprocess can detect

For these, 0% recall really does mean the description is broken — fix it.

## Verification

Two-test protocol when recall is 0%:

```
Test A (subprocess, what the eval does):
  $ cd /tmp && claude -p "how many skills do I have installed"
  → Likely: Claude lists skills via shell, doesn't consult the skill

Test B (interactive, what users actually experience):
  In your normal Claude Code session, ask the same question.
  → If skill triggers: subprocess blindness confirmed, description is fine
  → If skill doesn't trigger: description genuinely needs work
```

If Test A fails but Test B succeeds, **stop optimizing**. The eval is misleading.

## Example

**Scenario** (April 2026): Built `ecosystem-audit` skill with comprehensive description
mentioning "skill inventory", "memory diagnostic", "monthly hygiene check", etc.

**Iteration 1 result:**
```
Train: 18/36 correct, precision=100% recall=0% accuracy=50% (187s)
  [FAIL] rate=0/3 expected=True: how many skills do i have installed...
  [FAIL] rate=0/3 expected=True: my ~/.claude folder feels bloated...
  [FAIL] rate=0/3 expected=True: i keep getting the same bigquery error...
  [PASS] rate=0/3 expected=False: review PR #47...
  [PASS] rate=0/3 expected=False: review k8s deployment.yaml...
```

**Wrong move:** Rewrite description with "ALWAYS USE THIS SKILL" in caps, front-load
all symptom phrases, expand to 4× length.

**Iteration 2 result:** Identical 100% precision / 0% recall.

**Right move:** Recognize the pattern, verify with manual test in real session,
ship the skill, monitor real usage.

## Notes

- This is NOT a bug in `run_eval.py` — it's measuring real subprocess behavior
  faithfully. The mismatch is between subprocess and interactive context.
- The same skill can have wildly different trigger rates in subprocess vs. real
  sessions, especially when the skill's value comes from *aggregating* rather than
  *transforming*.
- Skills with verbatim error messages in the description (e.g.,
  `gcp-cloudrun-job-polling-url`, `bq-time-travel-self-insert-error`) work great
  in the eval because the subprocess CAN'T resolve those errors without the skill.
- If you absolutely need a measurable trigger rate for an introspection skill,
  consider redesigning eval queries to include task complexity the subprocess
  can't shortcut (e.g., "produce an HTML report with a radar chart showing
  utilization across 9 categories" forces consultation because it's not a
  one-shell-command answer).

## References

- `~/.claude/skills/skill-creator/SKILL.md` — section "How skill triggering works"
  acknowledges that simple queries Claude can handle directly may not trigger
  skills regardless of description quality, but doesn't connect this to the eval
  framework's measurement problem.
- `~/.claude/skills/skill-creator/scripts/run_eval.py` — uses `claude -p`
  subprocess invocation, source of the blindness.
