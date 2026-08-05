---
name: skill-portfolio-repo-placement-scan
description: >
  Scan a portfolio of authored Claude Code skills and produce, per target repo, a
  precise list of which skills to ADD, which to UPDATE (with direction), and which to
  CROSS-LINK rather than copy. Uses a per-repo function-level inclusion bar, portfolio
  deduplication (never recommend a skill already homed as its own repo or in a sibling
  target), and a version/`last_verified` divergence check for updates. Use this WHENEVER
  the user asks "which of my skills should go in repo X", "scan my skills and tell me what
  to add or update in these repos", "where should this new skill live", "find skills in the
  wrong bundle or duplicated across repos", "which repos have stale copies of skills I've
  improved locally", or wants to reorganize/consolidate a multi-repo skill portfolio. This
  is PLACEMENT/FIT mapping, and it produces a recommendation report — it never mutates repos.
  Don't use for (these are different tools): standardizing READMEs/badges or catching factual
  errors across skills (`skill-portfolio-audit`), finding dormant/unused skills
  (`ecosystem-audit`), searching for a skill by capability (`find-skills`/`search-skill`),
  scoring one skill's structural quality (`schliff`), syncing installed skills with their
  GitHub repos (`skill-sync`), or creating/publishing a brand-new skill (`skill-creator`).
author: wan-huiyan
version: 1.0.0
---

# Skill-Portfolio → Repo Placement Scan

When you maintain dozens of authored skills and several themed repos (bundles,
marketplaces, lesson collections), skills end up in the wrong place or nowhere: a
worktree lesson that belongs in the parallel-agents bundle sits loose in
`~/.claude/skills/`, a repo's published copy of a skill drifts behind the local one, or
the same skill gets copied into two repos and the copies diverge. This skill maps the
portfolio to the repos cleanly.

The output is a **recommendation report** — per repo: ADD / UPDATE / CROSS-LINK / NOTES.
Do not mutate any repo as part of this scan; mutating is a separate, confirmed step.

## Why the naive approach fails (read this first)

The instinct is "grep skill names/descriptions for each repo's theme keywords and
recommend the matches." That produces garbage, for three reasons this skill exists to
prevent:

1. **Repos are not homogeneous — match on FUNCTION, not theme.** A liberal lesson
   collection absorbs any on-theme lesson; a curated workflow bundle has a high bar and
   should reject general lessons that merely share keywords. Each repo needs its own
   *function-level* inclusion test, not a shared keyword filter. Expected yield differs
   wildly per repo (high / moderate / low / near-zero) — and "nothing fits" is a correct,
   valuable answer for a focused repo.

2. **Portfolio duplication.** Many candidates are *already homed* — as their own
   standalone repo, or inside a sibling target repo. Recommending those as ADDs creates
   cross-repo copies that drift. They must be detected and downgraded to CROSS-LINK
   (mention in README, don't bundle).

3. **"Update" needs a real method.** The installed copy at `~/.claude/skills/<name>` is
   often just stale install-lag, not an improvement — so it isn't automatically the
   source of truth. UPDATE detection means comparing `version:` / `last_verified:`
   frontmatter (and body size) between the repo copy and the most-developed local copy,
   and reporting the **direction** of divergence.

## Procedure

### Stage 1 — Gather (build the two indexes)

- **Inventory.** Build a `name<TAB>description` table of every authored skill from
  `~/.claude/skills/*/SKILL.md` (first `description:` line, truncated). Write to a tsv.
  Note: in `zsh`, iterate with `for s in */SKILL.md` (globs expand fine) — but unquoted
  `$VAR` lists do NOT word-split; use a glob, a `while read` over a file, or `bash`.
- **Portfolio map.** `gh repo list <owner> --limit 100 --json name,description` → the set
  of skill names that are *already their own standalone repo*. These are the core of the
  dedup list.
- **Target repos' current contents + manifests.** For each target repo, clone (or
  `gh api .../contents`) and list its current skills and read `version:` / `last_verified`
  from each `SKILL.md` + `plugin.json`. This is both the "already in repo" set (for dedup)
  and the baseline for UPDATE comparison.

### Stage 2 — Define each repo's FUNCTION BAR

Before any matching, write one paragraph per target repo stating the *function-level*
test for inclusion (not a keyword list) and the expected yield. Examples of the right
altitude:
- *Liberal lesson collection:* "absorbs any unhomed bug-pattern lesson on <domain X>;
  a developer doing <X> would hit it. EXCLUDE single-context bugs unrelated to <X>."
  → high yield.
- *Curated workflow bundle:* "a self-contained <workflow> OR a failure mode specific to
  <the workflow's runtime>. NOT general bug lessons." → low/selective yield.
- *Focused single-purpose repo:* "only a <narrow tool-type>." → near-zero; expect "none."

Get the bars right and the rest follows. This is the highest-leverage step.

### Stage 3 — Dispatch one subagent per target repo (parallel)

Fan out: one subagent per repo, each handed the same shared brief (see
`assets/scan_brief_template.md`) plus its repo-specific section. Each subagent must:
- find candidates against its function bar (use the pre-filtered pool, then independently
  grep the inventory for anything missed);
- **read each candidate's `SKILL.md` head** before including it — a description match is
  not confirmation of fit;
- apply DEDUP (drop already-homed → CROSS-LINK), using the full portfolio map and the
  sibling-repos list so it can't recommend a skill that lives elsewhere;
- run the UPDATE comparison for skills already in its repo and report divergences with
  direction;
- return the structured ADD / UPDATE / CROSS-LINK / NOTES block.

Give each subagent the portfolio map and the sibling-target list — a per-repo subagent
without the portfolio view *cannot* catch cross-repo duplication. Parallel subagents also
keep the main context clean and let each repo get full attention.

### Stage 4 — Reconcile and report

Subagents run blind to each other, so reconcile at the end:
- **Cross-repo collisions.** If a skill fits two repos (or one subagent recommends a skill
  another repo already homes), assign a single home by its *core* identity and CROSS-LINK
  the other. Verify against the real clones — a subagent without repo B cloned can't know
  a skill already lives there.
- **Dual-home coordination.** If a skill is bundled in two target repos, diff the copies
  and report which is newer; an update may need to land in both.
- Write a single durable report file: per-repo ADD / UPDATE / CROSS-LINK, plus a
  suggested low-risk execution order (version-sync updates first, then adds). State
  explicitly that nothing was mutated and PRs await confirmation.

## Consult a stronger reviewer before committing

The function bars and the ADD/UPDATE/CROSS-LINK split are exactly where a second
perspective pays off — get review on the *approach* (are the bars right? is the dedup
map complete? is there an UPDATE method at all?) before dispatching the fan-out, not
after. The most common failure caught at this gate: applying a liberal lesson-collection
bar uniformly to curated repos, and forgetting the UPDATE half entirely.

## Output format

Per repo, in the report:
```
REPO: <name>
ADD:        - <skill> — <why it clears the function bar>
UPDATE:     - <skill> — repo v<X> vs local v<Y> (direction); <what diverged>
CROSS-LINK: - <skill> — homed in <repo>
NOTES:      <nothing-fits, dual-home issues, notable rejected near-misses>
```

## Relationship to other skills
- `claude-plugin-repo-ci-release` — once you ADD skills to a repo and bump its version,
  that skill keeps the repo's release in lockstep.
