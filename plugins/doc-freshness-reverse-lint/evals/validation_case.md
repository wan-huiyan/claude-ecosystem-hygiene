# Validation case

## Case 1 — no false positive (primary)

**Setup:** a synthetic lesson saying "Don't sort by p-value — use effect size instead."

**Target doc:** `/Users/huiyanwan/Documents/schuh_causal_impact/docs/research/pre_period_length_methodology.md`

**Background:** the user already rephrased the doc. The exact phrase "sort by p-value" no longer appears (the doc now says "Sorting by p-value" / "Keep p-value sort" with qualifications — but not the extracted literal "sort by p-value").

**Expected:** `reverse_lint.py` returns `candidates: []`. Hook is silent.

**Why this test matters:** proves the literal-phrase guardrail prevents false positives when docs have been rephrased. Qualified or reworded retracted guidance should not be flagged as stale.

Run:
```bash
python3 scripts/reverse_lint.py evals/fixtures/fake_lesson_pvalue.md \
    --project-root /Users/huiyanwan/Documents --rescan --human
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
