---
name: claude-plugin-repo-ci-release
description: >
  Wire up CI validation and automatic release-cutting for a Claude Code plugin or
  marketplace repo (a repo with a `.claude-plugin/marketplace.json` and `plugins/*`).
  Adds two GitHub Actions — a structure validator that runs on every PR/push, and a
  release-on-version-bump job that cuts a GitHub Release whenever a `VERSION` file
  changes — plus the bundled validator script and workflow templates. Use this
  WHENEVER a plugin/marketplace repo has no CI, when GitHub Releases have drifted
  behind the shipped version (e.g. release says v2.0.0 but the skill is v3.3.0), when
  the user says "set up CI for my plugin repo / marketplace", "my releases keep falling
  behind", "tag/release on version bump", "auto-cut releases", "validate my
  marketplace.json / plugin.json", "catch when a plugin folder and its plugin.json name
  disagree", or has just added/bumped plugins and wants releases to keep up. Works for
  both single-plugin repos (nested `skills/<name>/`) and multi-plugin bundles (flat
  `plugins/<name>/`). Don't use for: generic app CI (pytest/lint), Cloud Run or container
  deploy workflows, npm `semantic-release` or cargo/crates.io release tooling, authoring a
  `marketplace.json` from scratch, a one-off manual release, or debugging an unrelated
  failing GitHub Action — those are not Claude-Code-plugin-repo CI/release setup.
author: wan-huiyan
version: 1.0.0
---

# Claude Plugin Repo CI + Release Automation

Claude Code plugin/marketplace repos rot in two predictable ways, and this skill
installs the two small guards that stop both:

1. **No CI.** A typo in `marketplace.json`, a plugin dir whose `plugin.json` `name`
   doesn't match its folder, an orphaned plugin not registered in the marketplace, or
   a `SKILL.md` whose frontmatter `name:` disagrees with its directory — any of these
   silently breaks plugin installation, and nobody notices until a user tries to
   install. A fast structural validator on every PR catches them at review time.

2. **Releases drift behind.** Versions live in `plugin.json` / `marketplace.json` /
   README, but GitHub *Releases* are cut by hand — so they fall behind. (Seen in the
   wild: a skill shipped at v3.3.0 while its GitHub Release sat at v2.0.0 for weeks.)
   A workflow that cuts the release automatically when a `VERSION` file changes keeps
   them in lockstep.

The whole thing is two workflow files, one validator script, and a one-line `VERSION`
file. Bundled and ready to copy — you should rarely need to write any of it from scratch.

## What's bundled

- `scripts/validate_plugins.py` — stdlib-only structural validator (no pip installs).
  Handles both repo layouts. Copy to `.github/scripts/validate_plugins.py`.
- `assets/ci.yml` — runs the validator on every PR + push to main. Copy to
  `.github/workflows/ci.yml`.
- `assets/release.yml` — release-on-version-bump. Copy to `.github/workflows/release.yml`.

## The two repo layouts

The validator and workflows handle both — you don't pick one, the validator
auto-detects:

- **Multi-plugin bundle** (e.g. an ecosystem marketplace): `plugins/<name>/SKILL.md`
  + `plugins/<name>/.claude-plugin/plugin.json`, one marketplace entry per plugin.
- **Single multi-skill plugin** (e.g. a lesson collection): one
  `plugins/<the-plugin>/` whose skills live nested under
  `plugins/<the-plugin>/skills/<skill>/SKILL.md`. The marketplace has a single entry.

## The VERSION file — why a separate file

`release.yml` keys off a repo-root `VERSION` file (one line, e.g. `1.3.0`) rather than
parsing a manifest, for three reasons:

- **Uniform.** Multi-plugin bundles have *no single* version in any JSON (each plugin
  versions independently). A repo-root `VERSION` is the one unambiguous "this is the
  release/bundle version" signal that works identically across every repo.
- **Explicit release intent.** Bumping `VERSION` is the deliberate "cut a release now"
  act, decoupled from incidental per-plugin version churn.
- **Drift-guarded, not drift-prone.** For single-plugin repos the validator *asserts*
  `VERSION` equals the plugin's `plugin.json` version and fails CI if they disagree —
  so the duplication becomes a checked invariant instead of a place to drift.

Convention: **bump `VERSION` in the same PR as the version bump.** On merge,
`release.yml` sees the changed `VERSION` and cuts `v<VERSION>` — unless that release
already exists, in which case it cleanly no-ops (so adding the file the first time,
when the release already exists, does nothing).

## Procedure

Work against a fresh clone and open a PR — never push workflow files straight to the
default branch.

### 1. Preflight

- **Token scope.** Pushing files under `.github/workflows/` needs the `gh` token to
  have `workflow` scope. Check: `gh auth status` should list `workflow` in scopes. If
  it's missing, the push will be rejected — tell the user to re-auth
  (`gh auth refresh -s workflow`); you can't grant it yourself.
- **Existing workflows.** `gh api repos/<owner>/<repo>/contents/.github/workflows
  --jq '.[].name'`. If the repo already has real validation CI (e.g. a `test.yml`
  running a test suite), don't add a redundant `ci.yml` — add only `release.yml`. Never
  clobber existing workflows; the two filenames here (`ci.yml`, `release.yml`) are
  additive.
- **Default branch.** The bundled workflows trigger on `branches: [main, master]`, which
  covers the common cases — but a workflow that lists the wrong branch silently *never
  runs* (no error, just nothing). Confirm the repo's default branch
  (`gh repo view <owner>/<repo> --json defaultBranchRef -q .defaultBranchRef.name`) and,
  if it's neither `main` nor `master`, add it to the `branches:` list in both workflows
  before committing.

### 2. Assemble files

Copy the three bundled files into a fresh clone and write `VERSION`:

```bash
mkdir -p .github/workflows .github/scripts
cp <skill>/scripts/validate_plugins.py .github/scripts/
cp <skill>/assets/ci.yml      .github/workflows/      # skip if repo already has validation CI
cp <skill>/assets/release.yml .github/workflows/
printf '%s\n' "<current-release-version>" > VERSION    # e.g. 1.3.0 — match what's shipped
```

Set `VERSION` to the version that's *already shipped* (read it from the single plugin's
`plugin.json`, or the README version history for a bundle). Matching the current state
is what makes the first merge a safe no-op.

### 3. Validate against current state BEFORE adding — never ship red CI

Run the validator locally against the repo as it is *right now*:

```bash
python3 .github/scripts/validate_plugins.py
```

It must print `OK:` before you proceed. If it reports errors, those are *pre-existing*
problems in the repo — surface them to the user and fix them in this same PR (or a
prior one). Adding a CI workflow that immediately fails red on merge is worse than no
CI. This local pre-check is the single most important step.

### 4. PR, watch it go green, merge

```bash
git checkout -b ci/add-validation-and-release
git add -A && git commit -m "ci: add structure validation + release-on-version-bump"
git push -u origin ci/add-validation-and-release
gh pr create --base main --title "..." --body "..."
```

`ci.yml` runs on the PR itself (same-repo branch). Wait for the check to pass —
`gh pr checks <num> --repo <owner>/<repo>` — before merging. `release.yml` does **not**
run on the PR (it only triggers on push to main with a `VERSION` change), so there's no
risk of a stray release from the branch.

### 5. Merge, then confirm the release job no-opped

After squash-merge, `release.yml` fires on the merge commit (VERSION was added). Confirm
it succeeded *and* was idempotent — it should log `Release v<X> already exists — nothing
to do.` and create no duplicate:

```bash
gh run list --repo <owner>/<repo> --workflow=release.yml --limit 1 --json status,conclusion
gh release list --repo <owner>/<repo>          # exactly one release per version, no dups
```

This closes the loop: from now on, any PR that bumps `VERSION` auto-cuts the matching
release with generated notes.

## Gotchas worth remembering

- **Shipped releases that predate this setup.** The first `VERSION` should match the
  current release so the merge no-ops. If a release for that version doesn't exist yet
  (the repo never cut one), the job will create it on merge — usually what you want.
  Decide deliberately.
- **`--generate-notes`** builds notes from commits/PRs since the previous tag; on a
  repo's first-ever release it summarizes from the start. Fine either way.
- **The release job uses the built-in `GITHUB_TOKEN`** with `permissions: contents:
  write` — no PAT/secret needed. A tag pushed by `GITHUB_TOKEN` deliberately does not
  retrigger other workflows (no loops).
- **Rolling this out across many repos with a shell loop:** in `zsh`, unquoted
  `for x in $LIST` and `set -- $spec` do *not* word-split — they iterate once with the
  whole string. Use a newline-delimited file + `while read -r`, or a `zsh` array, or run
  the loop under `bash`. (This silently bit a multi-repo rollout twice.)

## Extending to a whole portfolio

The same two files drop into any plugin repo unchanged. To fan out across many repos,
loop the §2–§5 procedure per repo (one PR each), and remember the validator must pass
on each repo's current state first. Repos with existing test CI get only `release.yml`.
