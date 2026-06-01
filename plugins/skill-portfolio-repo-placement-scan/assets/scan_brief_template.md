# Shared brief template — per-repo placement scan subagent

Fill the `<...>` placeholders, then hand ONE filled copy to each target-repo subagent
(its repo-specific section already pasted in). Keep one shared copy at a known path and
point every subagent at it.

## Your job
For ONE target repo, scan the local authored-skill inventory and produce:
- **ADD list**: skills that genuinely belong in this repo but are not yet in it.
- **UPDATE list**: skills already in the repo whose most-developed local copy diverges
  (newer version / `last_verified` / materially expanded body) — report DIRECTION
  (local newer vs repo newer).
- **NOTHING-FITS is a valid answer.** Do not pad. Precision over recall.

## Data sources
- Full local skill inventory (name<TAB>description): `<INVENTORY_TSV_PATH>`
- Installed skill bodies to read: `~/.claude/skills/<name>/SKILL.md`
- Source/working copies if present: `<SOURCE_DIRS>` may hold a more-developed copy.
- Target repo clone: `<REPO_CLONE_PATH>` (read its current skills + manifests).

## Method
1. From the inventory, find candidates matching this repo's FUNCTION BAR (below) —
   not just keyword theme.
2. For each candidate, read the actual `SKILL.md` head (~40 lines) to confirm it fits
   the repo's PURPOSE. A description keyword match is not enough.
3. Apply DEDUP: drop any candidate already homed as its own standalone repo or already
   inside a sibling target repo — note it as "cross-link, don't copy" instead of ADD.
4. For UPDATE: for skills already in this repo, compare `version:` / `last_verified:`
   frontmatter and body size between the repo copy and the local copy. Report only real
   divergences, each with a direction.

## THIS REPO
- Name: `<REPO_NAME>`
- Clone: `<REPO_CLONE_PATH>`
- Current contents: `<HOW_TO_LIST_CURRENT_SKILLS>`
- FUNCTION BAR (the precise inclusion test — function-level, not theme):
  `<ONE_PARAGRAPH_FUNCTION_BAR + EXPECTED_YIELD (high/moderate/low/near-zero)>`
- Candidate pool to evaluate (pre-filtered; confirm each by reading): `<CANDIDATES>`
- Also independently grep the inventory for: `<EXTRA_KEYWORDS>`

## DEDUP — skills already homed as their OWN standalone repo (cross-link, never ADD)
`<LIST_FROM_PORTFOLIO_MAP — e.g. `gh repo list <owner>` names that correspond to skills>`

## Sibling target repos (don't recommend a skill for repo A if it lives in repo B)
`<LIST_OTHER_TARGET_REPOS + their current skills>`

## Output format (return as your final message — raw, no preamble)
```
REPO: <name>
ADD:
- <skill-name> — <one line: why it fits the function bar>
UPDATE:
- <skill-name> — repo v<X> vs local v<Y> (direction); <what diverged>
CROSS-LINK (already homed, mention in README not bundle):
- <skill-name> — homed in <repo>
NOTES: <caveats, e.g. "nothing else fits", dual-home issues, rejected near-misses>
```
