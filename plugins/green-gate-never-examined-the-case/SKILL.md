---
name: green-gate-never-examined-the-case
description: |
  A check reported clean without examining the case it exists for — "green" meant
  "nothing ran". Use when about to trust a gate, test or CI step you have never watched
  fail; when a guard is green but the bug it guards shipped anyway; when a check passes
  on a shallow clone, a disabled object, a malformed input or an empty result; or when a
  gate fires and you are about to satisfy it without asking what the wrong state already
  cost. Five measured mechanisms and a review checklist. The test: make it fail on
  purpose once, and check what the failure already cost before clearing it. NOT for
  measuring an existing suite's catch rate (test-effectiveness-auditor) or flaky tests.
author: Claude Code
version: 1.0.0
date: 2026-08-11
---

# A green gate that never examined the case

**Clean is indistinguishable from safe.** A check that did not run, ran on the wrong
object, or ran on an input that made it succeed trivially reports exactly what a
genuinely passing check reports. The signal you get is the same; the information is not.

> **The test, two clauses:**
> 1. **Make the check fail on purpose once.** If you cannot produce a failing run, you
>    have established that the check *printed something*, not that it can fail.
> 2. **Check what the failure already cost before you clear it.** A guard tells you a
>    state is wrong. It does not tell you what that wrong state already did.

## The five mechanisms

Each of these was measured, not imagined. All five surfaced within one working session,
which is the reason to treat this as a family rather than five unrelated bugs.

### 1. Scope excludes the case

A description-length gate built its worklist as:

```python
live = [s for s in skills if not s.disabled]
```

A **disabled** skill's 1,548-character description therefore reported `over: False`
against a 1,536 cap. Harmless while disabled — and it truncates mid-word the moment
anyone enables it, which is exactly when nobody re-runs the check.

**Generalises to:** any gate scoped to "active", "enabled", "published" or "current"
objects stops guarding the moment something is deactivated. **Deactivation is when
nobody is looking.**

### 2. Malformed input makes the check succeed trivially

A test named for a corrupt base64 payload never reached the decode branch it was named
after. `%` falls outside the base64 alphabet, so the capture group matched **empty**, and
`b64decode("")` returned cleanly. The test passed *because* the input was broken.

**The tell:** a test whose name describes a failure mode, which has never been seen to
go red.

### 3. The error lands on a channel nobody reads

```
git diff --diff-filter=D --name-only a...b     # unrelated histories
  stdout: (empty)
  stderr: fatal: a...b: no merge base
  exit:   128
```

A gate written as `if [ -z "$(git diff --diff-filter=D --name-only origin/main...HEAD)" ]`
reads a clean bill from a comparison that never ran. The same command with **two** dots
reports normally and exits 0 — so the two forms fail in opposite directions, and neither
is universally safe.

**Fix shape:** assert the precondition separately, and check the exit code.

```bash
git merge-base origin/main HEAD >/dev/null || { echo "NO SHARED HISTORY"; exit 1; }
git diff --diff-filter=DR --name-only origin/main...HEAD
```

### 4. A plumbing default silently kills one input

A gate unioned two sources: a `VERSION` file's git history, and a README changelog.
`actions/checkout@v4` **without `fetch-depth: 0`** is a depth-1 clone, so
`git log --follow VERSION` saw one commit and that half contributed nothing.

Measured: **26 claimed versions on the runner against 28 locally — green either way.**
Found on the gate's own introducing CI run, by checking the step's *output* rather than
its tick.

**Generalises to:** any multi-source check where one source can return empty for
environmental reasons. A dead input is not a failure, so it has to announce itself.

```python
if len(source_b) > 3 and len(source_a) < len(source_b) / 2:
    print("::warning::source_a looks truncated — this gate is running on half its inputs")
```

### 5. The guard fires, is acted on correctly, and the damage still stands

The worst one, and the least visible, because **every signal behaved properly.**

A release workflow filtered `paths: ['VERSION']`. A commit shipped `v1.13.0` in the
manifests and the README while leaving `VERSION` at `1.12.0` — so the release job **never
triggered**: no failed run, no skip message, nothing in the Actions list to notice. The
next commit moved `VERSION` `1.12.0 → 1.14.0`, stepping **over** the value, so `1.13.0`
never existed on the default branch and no later push could cut it.

**The drift guard did fire.** A `VERSION != plugin version` check went red on that very
commit. A human saw it and fixed it by bumping to the next version — satisfying the guard
and leaving the release permanently unreachable.

> **Fixing forward can satisfy the guard while leaving the damage in place — and the
> guard then goes green, which reads as resolved.**

## Two corollaries worth more than the list

**A working failure path on some *other* input is not evidence the check works.** That
release job *can* fail — an empty `VERSION` exits 1 — which makes a passing run look like
proof. It cannot fail on the case that matters, because that case never reaches it.
*"Never fails"* and *"cannot fail on the case that prompted it"* are different defects,
and the second hides better.

**Status is not consequence.** Both branches of that job's create step exit 0:

```bash
if gh release view "v$V" >/dev/null 2>&1; then
  echo "Release v$V already exists — nothing to do."   # exits 0
else
  gh release create "v$V" ...                          # exits 0
fi
```

`conclusion: success` is byte-identical whether it cut a release or skipped one. The
status field answers a different question than the one being asked of it. After fixing
it, the check that settled the matter was not the green tick — it was
`gh release view v1.23.0` plus reading which line the log printed.

## Checklist for a new or inherited check

- [ ] **Break something on purpose and watch it go red.** A gate nobody has seen fail is
      a decoration. Record the failing output somewhere durable.
- [ ] **Name the case it exists for, then confirm that case reaches it.** Not a case —
      *the* case. Instance 4 was a gate whose two inputs both looked fine and one of which
      was dead.
- [ ] **Read the step's output, not its tick.** In CI, confirm the step ran and printed
      what you expect. `gh run view <id> --log | grep <your gate's own line>`.
- [ ] **Check the exit code, not just the output.** Empty output plus non-zero exit is the
      signature of a check that could not run.
- [ ] **Ask what the wrong state already cost.** If the damage is unreachable, record it
      as accepted **with the verified reason** — never with a plausible one.
- [ ] **Baseline a gate that ships red.** One that cannot go green gets muted inside a
      week, and a muted gate looks like coverage.

## On baselining, because it is where good gates die

A gate introduced against an existing mess reports every historical instance on day one.
Seven findings, none of them today's regression, and it gets muted or deleted.

Record the known state as accepted at the moment of introduction, and fail only on **new**
divergence. Put the reasons in the baseline **file**, not a code comment — a comment does
not survive being skimmed.

And record what was *verified*, not what was plausible. A real baseline from this family:

```
# --- predate both VERSION and the release automation ---
1.0.0  # pre-dates VERSION and release.yml (both introduced in 435ffaa)

# --- workflow existed; cause NOT established ---
# Do not label these "pre-automation" — that is false and was checked. 435ffaa added
# release.yml and set VERSION=1.3.0 in ONE commit, so the workflow was present for all
# three and no release exists for any of them. Why is unknown. Recorded as unknown.
1.3.0  # release.yml present (added in the same commit); cause unestablished
```

**A confident wrong note is what the next person trusts instead of re-checking.** "Cause
unestablished" is more useful than a plausible cause, because it does not stop the
investigation.

## Two instances of the same latent bug, with different costs

Worth doing on every repo that shares a workflow, because the presence of the bug and the
cost of the bug are separate questions:

| repo | `paths: ['VERSION']` filter | releases lost |
|---|---|---|
| `agent-traffic-control` | present | **1** — v1.13.0, for three months |
| `claude-ecosystem-hygiene` | present | **0** — `VERSION` and the workflow arrived in the same commit, and every version since has a release |

The second row is the second clause working in the good direction: the bug was there, the
cost was checked, and it was nil. That is a result, not a reason to skip the check.

## Related

- `test-effectiveness-auditor` — the complementary question: how good is an existing
  suite at catching bugs that already happened. That measures a suite's hit rate over
  history; this one is about a single check that cannot fail on its own case.
- `doc-freshness-reverse-lint` — stale normative guidance, i.e. a *rule* that no longer
  matches reality, rather than a *check* that never examined it.
- `claude-plugin-repo-ci-release` — the release-workflow mechanics behind instance 5.
