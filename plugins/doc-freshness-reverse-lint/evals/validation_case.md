# Validation case

## Case 1 — no false positive (primary)

**Setup:** a synthetic lesson saying "Don't sort by p-value — use effect size instead."

**Target doc:** `/Users/<user>/Documents/the-causal-impact-repo/docs/research/pre_period_length_methodology.md`

**Background:** the user already rephrased the doc. The exact phrase "sort by p-value" no longer appears (the doc now says "Sorting by p-value" / "Keep p-value sort" with qualifications — but not the extracted literal "sort by p-value").

**Expected:** `reverse_lint.py` returns `candidates: []`. Hook is silent.

**Why this test matters:** proves the literal-phrase guardrail prevents false positives when docs have been rephrased. Qualified or reworded retracted guidance should not be flagged as stale.

Run:
```bash
python3 scripts/reverse_lint.py evals/fixtures/fake_lesson_pvalue.md \
    --project-root /Users/<user>/Documents --rescan --human
```

## Case 2 — true positive (counterfactual)

**Setup:** the same lesson, run against a fixture doc containing the literal phrase.

**Expected:** exactly one candidate, pointing to the fixture file line.

This confirms the extractor does fire when a real literal match exists.

Run:
```bash
python3 scripts/reverse_lint.py evals/fixtures/fake_lesson_pvalue.md \
    --project-root evals/fixtures/project_with_stale_doc --rescan --human
```

---

## Dead-branch detection (v1.3.0)

Fixture: `evals/fixtures/project_with_dead_branch/`.

Two assertions off one fixture pair, run with a memory file that retires a
quoted rule (`"no deploys by agents"`):

| doc | expectation | why |
|---|---|---|
| `docs/runbooks/deploy_thing.md` | **flagged** | retires the rule and keeps *"A cloud session still cannot"* — a live-looking branch in the same paragraph |
| `docs/runbooks/unrelated.md` | **not flagged** | mentions the same retired rule as history with no condition attached; the unrelated `only applies on Tuesdays` sits in its own paragraph |

```bash
python3 scripts/reverse_lint.py <memory-file-retiring-the-rule> \
    --project-root evals/fixtures/project_with_dead_branch --human --rescan
```

Expected: exactly one `dead_branch_candidates` entry, matching
`deploy_thing.md` only.

**This is the case the mechanism was built from** — DoodleRun, 2026-08-04.
*"No deploys by agents"* was retired across four live briefs and every
retirement kept the cloud-session condition alive after cloud sessions had
stopped existing. The retirement was right; the survivor was the defect, and it
was caught by the owner rather than by tooling.
