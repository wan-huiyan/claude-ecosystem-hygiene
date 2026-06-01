---
name: repo-hygiene
description: |
  Pre-PR checklist and repo cleanup for data science and analytics projects. Use this skill
  BEFORE creating a PR, merging branches, or handing off a repo. Catches common mistakes that
  waste hours later: data files committed to git, hardcoded paths, runtime artifacts tracked,
  branch ownership confusion, internal docs drifting from deliverables, and client data in
  public repos. Also use when the user says "clean up the repo", "is this ready to merge?",
  "prepare for handover", "before we push", "repo hygiene", or when you notice tracked .csv,
  .db, .parquet, or /Users/ paths during any file operation. Especially important for repos
  with multiple contributors working on parallel branches. Also covers reviewing/auditing
  a published plugin/skill repo: probe live CI + run the repo's own tests before eyeballing
  files ("review if this repo needs updating", "is this repo up to date?", "audit my plugin repo").
version: 1.2.0
---

# Repo Hygiene

A pre-PR checklist and repo cleanup guide built from real mistakes that cost hours to fix.
Every item here came from a real incident where something was committed, merged, and then
had to be painfully undone.

## When to Use

- Before running `gh pr create`
- Before merging any branch
- When someone asks "is this repo clean?"
- When preparing a repo for handover to another team member
- When you notice data files, absolute paths, or runtime artifacts during any file operation

## The Pre-PR Checklist

Run through these checks in order. Each one has burned real teams.

### 1. Branch Ownership

**The problem:** You commit deliverable fixes on a feature branch, then need to cherry-pick
them onto the correct branch. Cherry-picking commits that touch files across concerns
(webapp + deliverables + analysis) creates merge conflicts and duplicated work.

**Before your first commit on any branch, answer:** "Which files does this branch own?"

| Branch type | Owns | Does NOT own |
|---|---|---|
| `feature/webapp-*` | `webapp/`, `tests/`, `requirements-web.txt` | `deliverables/`, `analysis/`, `ANALYSIS_FINDINGS.md` |
| `fix/review-*` | `deliverables/`, `analysis/`, `ANALYSIS_FINDINGS.md`, `docs/` | `webapp/` |
| `docs/*` | `docs/`, `README.md`, `.md` files | Code files |

**Rule:** If a commit touches files from two different ownership groups, split it into
two commits on two branches. The 5 minutes you spend now saves the 30-minute cherry-pick
session later.

**This applies to .gitignore too.** If branch A adds `analysis_runs.db` to `.gitignore`
(a webapp concern) and branch B adds `data/features_snapshot.csv` (a data concern),
each `.gitignore` entry belongs on the branch that owns the related files. Otherwise
when branches merge, you get `.gitignore` conflicts or entries that make no sense
without the corresponding code changes.

**Red flag:** If `git diff --stat` shows both `webapp/` and `deliverables/` files, you're
probably on the wrong branch for at least some of those changes.

### 2. Data Files Not in Git

**The problem:** A 531-row CSV seems harmless, but it sets a precedent. Next month it's a
50MB Parquet file. Git stores every version forever — your repo bloats permanently.

**Check:**
```bash
git ls-files | grep -E '\.(csv|parquet|pkl|h5|db|sqlite|feather|arrow|json)$'
```

If any match: remove from tracking, add to `.gitignore`, provide an export script instead.

**The pattern:** Don't store data. Store the script that creates the data.

```
# Bad: data committed
data/features.csv          # 50MB, grows monthly

# Good: script + gitignore
data/.gitkeep              # keeps the directory
data/features.csv          # in .gitignore
analysis/export_data.py    # anyone can regenerate
```

### 3. Runtime Artifacts Not Tracked

**Check:**
```bash
git ls-files | grep -E '(\.db$|\.pyc$|__pycache__|node_modules|\.egg-info|\.env$)'
```

These should never be tracked. If found:
```bash
git rm --cached <file>     # remove from tracking (keeps local copy)
echo "<pattern>" >> .gitignore
```

**Recommended .gitignore for data science repos:**
```gitignore
# Python
__pycache__/
*.pyc
*.egg-info/
venv*/
.venv/

# Data (use export scripts instead)
*.csv
*.parquet
*.pkl
*.h5
*.feather
data/*
!data/.gitkeep

# Runtime
*.db
*.sqlite
.env
.DS_Store

# Build
node_modules/
dist/
build/

# IDE
.vscode/
.idea/
```

### 4. No Hardcoded Absolute Paths

**Check:**
```bash
grep -rn '/Users/\|/home/\|C:\\' --include='*.py' --include='*.js' --include='*.ts' .
```

Every hit is a reproducibility bug. Replace with:
```python
# Bad
OUT_DIR = "/Users/alice/projects/my-analysis"

# Good
from pathlib import Path
OUT_DIR = Path(__file__).resolve().parent.parent
```

### 5. Test Plan Verification

**Before running `gh pr create`:**

1. Read the test plan items you're about to put in the PR body
2. Actually run each one
3. Record pass/fail
4. Post results as a PR comment after creation

This sounds obvious but the natural flow is: write the PR body with test items,
create the PR, then forget to actually run them. The items become decorative checkboxes.

**Pattern:**
```bash
# Draft PR body with test plan
# Run each test item
# Create PR
gh pr create --title "..." --body "..."
# Post results as comment
gh pr comment <number> --body "## Test Results ..."
```

### 6. Internal Doc Consistency

**The problem:** You reframe claims in client deliverables (e.g., change the headline from
"p=0.039, significant" to "80-90% probability, exploratory") but forget to update the
internal reference document. An auditor or new team member reads the internal doc first
and sees the old framing. Now the reframing looks cosmetic.

**Rule:** When updating deliverables, `git diff` the internal reference doc in the same commit.
If the deliverables say X and the internal doc says Y, fix it now.

**Check:**
```bash
# After editing deliverables, verify internal docs match
git diff --name-only | grep -E '(FINDINGS|ANALYSIS|README)' || echo "WARNING: internal docs not updated"
```

### 7. Client Data Sanitization (for public repos)

**Before pushing to any public repository:**

```bash
# Check for client/company names
grep -rni 'clientname\|CompanyName\|internal-project-id' --include='*.md' --include='*.py' .

# Check for internal infrastructure
grep -rn 'swordfish\|bigquery.*project\|@company.com' .

# Check for specific amounts that could identify an engagement
grep -rn '£297K\|£206K\|\$1.2M' --include='*.md' .
```

**Sanitization rules:**
- Client names → "a retail client", "a university"
- Specific amounts → change currency AND round differently
- Internal project IDs → remove entirely
- Employer email → personal email or remove
- BQ table names → generic placeholders

**Don't forget git history:** Even after sanitizing current files, `git log -p` shows
every previous version. For sensitive data, use an orphan branch:
```bash
git checkout --orphan clean
git add -A && git commit -m "Clean history"
git branch -D main && git branch -m main
git push --force origin main
```

## Quick Reference: The 30-Second Check

Before every PR, run this:

```bash
echo "=== Data files in git ===" && \
git ls-files | grep -E '\.(csv|parquet|pkl|db|sqlite)$' && \
echo "=== Hardcoded paths ===" && \
grep -rn '/Users/\|/home/' --include='*.py' . && \
echo "=== Runtime artifacts ===" && \
git ls-files | grep -E '(__pycache__|\.pyc|node_modules|\.env$|\.db$)' && \
echo "=== Branch file ownership ===" && \
git diff --stat HEAD~1 | head -20
```

If any section has output, fix it before creating the PR.

### 8. Cross-Deliverable Consistency Audit

**The problem:** After updating analysis results, some deliverables get updated but
others don't. The file updated LAST is most likely to be stale. In one project, the
report was correct but the deck still showed old p-values (0.21 vs 0.190), wrong CIs,
and stale probability (84% vs 95%) — 3 sessions after the numbers changed.

**After any batch of number changes:**

```bash
# Grep every key number across all deliverables
for num in "p=0.047" "p=0.190" "12/12" "£176K" "£120" "£276K" "Four methods"; do
  echo "=== $num ===" && grep -rn "$num" deliverables/ ANALYSIS_FINDINGS.md
done
```

If any file is missing a key number or shows an old one, fix it before creating the PR.

**Update order:** Explorer → Report → Deck → ANALYSIS_FINDINGS.md → Notebook disclaimer

The deck is furthest from the analysis code and gets forgotten most often.

### 9. No Direct Pushes to Main on Shared Repos

**The problem:** Small "housekeeping" commits get pushed directly to main because they
feel too trivial for a branch + PR. But on shared repos, direct pushes bypass review,
can't be squashed after the fact without force-pushing, and create a messy history that
teammates didn't approve.

**Rule:** If the repo has more than one contributor, EVERY change goes through a branch + PR.
Even one-line docs fixes. The overhead is ~30 seconds (`git checkout -b fix/x`, commit,
push, `gh pr create`). The cost of a bad direct push is much higher — you can't squash
already-pushed commits on main without force-push, which is destructive on shared branches.

**Check before pushing:**
```bash
# Am I on main?
git branch --show-current
# If "main" — STOP. Create a branch first.
```

**The exception:** Solo repos where you are the only contributor. Even then, branches
help if you use squash-merge for clean history.

### 10. Reviewing/Auditing a Repo: Probe CI + Run Tests First, Don't Eyeball Files

**The problem:** When asked to "review if this repo needs updating", "check if it's up to
date", or "audit my plugin/skill repo", the instinct is to read the file tree. But a
green-looking tree can hide a repo whose latest push shipped **red CI** and stayed red
unnoticed. Classic signature: a version-bump commit emits a malformed semver with a
leading/trailing dot (`.1.9.1` instead of `1.9.1`) from a `sed` bump — visually almost-right,
invalid semver, fails the repo's own manifest/semver test, breaks plugin-install version parsing.

**Lead with two probes, BEFORE reading content:**
```bash
# 1. Live CI status — if the latest default-branch run is `failure`, that's your headline finding.
gh run list --repo <owner>/<repo> --limit 5

# 2. Clone and run the repo's own test suite — it encodes the invariants eyeballing can't catch.
gh repo clone <owner>/<repo> /tmp/review -- --depth 1
cd /tmp/review && npm test        # or: pytest, node --test tests/*.test.mjs, etc.
```
Only **then** read content for staleness (changelog gaps, cross-file version skew, stale
dependency-version references like "memory-hygiene v3.1" while everything else says v3.3).

**The malformed-semver check specifically:**
```bash
grep -RhoE '"version":\s*"[^"]*"' <repo> | sort -u
# any value not matching ^[0-9]+\.[0-9]+\.[0-9]+ is a bug; also compare SKILL.md frontmatter `version:`
```

**Close the loop:** after pushing a fix, re-run the suite locally (confirm 0 fail) AND poll the
new CI run (`gh run list --limit 1`) until `completed/success` — the step the original push skipped.
Root-cause the *process*, not just the typo: red shipped and stayed red means nobody gates publish
on green CI (see the `claude-plugin-repo-ci-release` plugin, which installs exactly that gate).

## Common Mistakes by Project Type

| Project type | Most common issue | Second most common |
|---|---|---|
| Data science | CSV/Parquet committed | Hardcoded notebook paths |
| Web app | `node_modules/` or `.env` tracked | `analysis_runs.db` committed |
| ML pipeline | Model weights in git | Training data checked in |
| Client deliverable | Internal doc drift | Client names in public repo |
| Multi-contributor | Branch ownership confusion | Merge conflicts from mixed commits |
