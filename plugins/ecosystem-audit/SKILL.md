---
name: ecosystem-audit
version: 1.2.0
updated: 2026-04-25
description: >
  ALWAYS use this skill when the user asks any question about their Claude Code setup, installed
  skills, memory system, handoffs, worktrees, or ~/.claude directory health. This is the
  go-to skill for introspection of the Claude Code environment itself. Specifically trigger on:
  (1) Skill inventory questions — "how many skills do I have", "which skills am I using",
  "what's dormant", "which skills can I uninstall", "are there overlapping skills"; (2) Cleanup
  and hygiene requests — "clean up my ecosystem", "audit my setup", "~/.claude feels bloated",
  "monthly hygiene check", "what needs cleanup", "stale worktrees", "orphaned handoff prompts";
  (3) Diagnostic symptoms — "my memory system isn't working", "lessons aren't being picked up",
  "skill is not triggering", "claude keeps forgetting", "why is the wrong skill firing",
  "duplicate skill confusion"; (4) Health dashboards — "show me a health dashboard", "utilization
  across skills/memory/handoffs", "ecosystem health report"; (5) Any mention of auditing
  persistent artifacts, session logs, JSONL analysis, or cross-project memory files. The skill
  produces an interactive dark-themed HTML report with a radar chart showing health percentages
  across 6 categories (skills, memory, handoffs, ADRs, docs, worktrees) plus prioritized P0/P1/P2
  recommendations and a ready-to-run cleanup script. It complements schliff:doctor (per-skill
  structural quality) and memory-hygiene (persistent knowledge store) by adding runtime usage
  analytics from JSONL session logs and cross-category coverage that neither provides alone.
  Use this proactively whenever the user describes ANY ecosystem-level symptom, even if they
  don't explicitly ask for an "audit".
---

# Ecosystem Audit

A comprehensive audit of the entire `~/.claude/` ecosystem that scans 9 categories of persistent
artifacts, scores each on a health scale, and produces an interactive HTML dashboard with
prioritized cleanup recommendations.

## When to Use

- User wants to know what skills are installed and which are actually used
- User wants to clean up their Claude Code environment
- User asks about ecosystem health, dormant artifacts, or storage bloat
- Monthly hygiene check (recommend running every 30 days)
- Before/after installing a batch of new skills
- When memory-hygiene or schliff:doctor findings suggest broader issues

## Architecture

This skill orchestrates parallel subagents for speed. The audit runs in 3 phases:

```
Phase 1: Scan (parallel subagents)
  ├── Skills: parse JSONL logs for invocations, classify by domain
  ├── Memory: check all project dirs, apply memory-hygiene thresholds
  ├── Handoffs: count, classify lifecycle state, find orphans
  └── ADRs + Docs: read status fields, check links, classify

Phase 2: Score (sequential)
  ├── Calculate health % per category
  ├── Apply lifecycle scoring for worktrees
  ├── Cross-reference with memory-hygiene thresholds
  └── Generate prioritized recommendations (P0/P1/P2)

Phase 3: Report (write files)
  ├── Markdown summary → docs/handoffs/ecosystem_audit_report.md
  └── Interactive HTML → docs/handoffs/ecosystem_audit_report.html
```

## Phase 1: Scan

Launch 4 parallel subagents, each responsible for one scan domain. Each subagent reports
structured findings back to the orchestrator.

### 1A. Skill Usage Scan

Parse JSONL session logs to determine which skills are actually invoked.

**Data source:** `~/.claude/projects/<dir>/<uuid>.jsonl`

**What to extract:**
- Lines where `message.content[].name == "Skill"` — these are invocations
- Extract `input.skill` (skill name), `input.args`, and `timestamp`
- Cross-reference with `toolUseResult.commandName` and `toolUseResult.success`

**Classification rules:**
- **Active**: invoked in the session log window (default: 30 days)
- **Relevant-Dormant**: not invoked but domain-aligned with user's work (check user profile
  in memory files for role/domain context)
- **Niche-Dormant**: specialized domain unlikely to be needed (bio/chem databases, quantum
  computing, wet-lab integrations, astrophysics, game dev, embedded systems)
- **DevOps-Dormant**: IaC/CI/CD tools (terraform, helm, k8s, ansible, dockerfile, jenkins,
  github-actions generators and validators)
- **Not-a-Skill**: workspace directories, cloned repos, .DS_Store, README files
- **Deprecated**: SKILL.md explicitly says "DEPRECATED" or "merged into"

**Also check:**
- Duplicate/overlap clusters: skills with similar trigger phrases
- Adware: skills that say "ALWAYS run" or inject into every session
- Skills without SKILL.md files

### 1B. Memory & Lessons Scan

**Delegation contract with memory-hygiene (single source of truth).**

memory-hygiene (v3.0+) is the authoritative spec for the Memory tier. To prevent drift, the Memory subagent does NOT re-implement memory-hygiene's detection logic. Instead:

1. **Invoke `memory-hygiene` Phase 1 (Discover) only** — do not execute Phase 4 fixes.
2. **Consume its structured audit report** (the headings under `## Memory Hygiene Audit`) as the input to ecosystem-audit's Memory score.
3. **Version-pin check:** read memory-hygiene's SKILL.md frontmatter. If the major version differs from what this skill was calibrated against (currently v3.0), fail loudly and ask the user to re-sync ecosystem-audit before scoring.

If for any reason memory-hygiene cannot run (missing, errored, version mismatch), render the Memory axis as `N/A` in the radar chart (see Phase 3) and list blockers. Never fabricate a score.

**Scan targets covered by memory-hygiene (full tier map T0→T3):**

| Tier | Path | Key checks |
|------|------|------------|
| T0 | `~/.claude/axioms.md` | Count ≤12 (Cowan cap); classify each as Universal / Role / Phase; flag Phase items for migration to `~/.claude/templates/phase_*.md` |
| T0 | `~/.claude/CLAUDE.md` | Session-start checklist has all 4 items: load axioms, read MEMORY.md, grep archives, grep before "cannot" claims |
| T1 | `~/.claude/projects/*/memory/MEMORY.md` | Line count ≤200 (hard limit 25KB); entries are one-line pointers, no inline content |
| T1.5 | `~/.claude/templates/phase_*.md` | Standard templates exist (onboarding, data sourcing, analysis, deliverables, code review) |
| T1.5 | `<project>/.claude/rules/phase-*.md` | `paths:` frontmatter globs resolve to real files (no dead globs); content consistent with the global template it was copied from |
| T2 | `~/.claude/projects/*/memory/*.md` | Frontmatter has name/description/type; `type` ∈ {user, feedback, project, reference}; indexed in MEMORY.md (no orphans) |
| T3 | `~/.claude/lessons.md`, `sessions_archive.md`, handoffs | Unreferenced sessions >30 days old AND >50 lines → compression candidate; archive >200 lines → split candidate |

**Staleness signals (memory-hygiene §1d — all four, not just dates):**
- Broken references (grep codebase for identifier; not found = stale)
- Relative dates ("last week", "recently") that should be absolute
- Codebase contradictions (memory says lib X; `package.json` says otherwise)
- Contradicted lessons (global vs project rules conflict)

**Agency-aware staleness:** read `user_role.md` before thresholding. Agency / multi-client users measure dormancy in calendar time across portfolio; single-long-project users measure in session count within the project.

**Per-file cross-cutting checks (detection only; resolution belongs to memory-hygiene):**
- Orphan detection (file exists but not in MEMORY.md index)
- Cross-project duplicates (same feedback file in multiple projects) — report clusters; memory-hygiene Phase 4 owns keep/move/merge decisions

### 1C. Handoffs & Session Docs Scan

Count and classify all session handoff documents.

**Scan locations:**
- `<project>/docs/handoffs/` — handoff and prompt files
- `<project>/.claude/worktrees/*/docs/handoffs/` — worktree duplicates

**Classification:**
- **Current**: references in-progress or planned work
- **Historical**: work completed, value is purely archival
- **Orphaned prompt**: `*_prompt.md` whose session already happened or never started
- **Worktree duplicate**: handoff file inside a stale worktree (pure waste)

### 1D. ADRs, Plans, Reviews, Findings, Tasks Scan

Read and classify structured project documentation.

**ADR checks (per memory-hygiene MADR 4.0):**
- Status field validation (Accepted/Proposed/Superseded/Resolved)
- Bidirectional supersession links
- README.md link integrity (do filenames match?)
- Duplicate content detection
- Numbering gaps and sequence issues

**Plans/Reviews/Findings/Tasks:**
- Classify as Active / Historical / Stale
- Check for completed items still marked as in-progress

## Phase 2: Score

### Health Percentage Calculation

Each category gets a health score from 0-100%. The methodology differs by category
because "healthy" means different things for different artifact types.

**Skills**: `active_count / total_installed * 100`
Simple utilization rate. Active = invoked in the log window.

**Memory**: Weighted composite of sub-checks, computed from memory-hygiene's Discover report:
- MEMORY.md line count vs threshold (weight: 25%)
- Frontmatter compliance rate, incl. `type` enum validity (weight: 15%)
- Axiom health — count ≤12 AND zero Phase items in axioms.md (weight: 15%)
- Phase-template hygiene — templates exist, no dead `paths:` globs (weight: 10%)
- Staleness rate of topic files (all 4 signals, agency-aware) (weight: 20%)
- Session compression backlog (weight: 15%)

If any sub-check is un-computable (missing input, memory-hygiene unavailable), set the Memory axis to `N/A` rather than averaging over a partial signal.

**Handoffs**: `current_count / total_count * 100`
Only current handoffs are "healthy" — historical ones should be archived.

**ADRs**: `active_count / total_count * 100`
Active = still governing current behavior (Accepted status, not superseded).

**Docs** (plans + reviews + findings + tasks): `active_count / total_count * 100`

**Worktrees — Lifecycle Score** (not binary active/stale):
Each worktree is scored individually based on its lifecycle state, then averaged:
- EXPECTED (unmerged branch, ≤7 days old): 100%
- ACCEPTABLE (unmerged branch, 7-14 days old): 75%
- NEEDS_CLEANUP (branch already merged): 25%
- ABANDONED (unmerged branch, >14 days old): 0%

If 0 worktrees exist, score is 100% (nothing to manage, nothing mismanaged).

### Priority Classification

Actions are classified by urgency:
- **P0 (Do Now)**: Security risks (exposed keys), broken automation, data integrity issues
- **P1 (This Week)**: Stale artifact cleanup, threshold violations, worktree removal
- **P2 (This Month)**: Archival, consolidation, lessons triage, ongoing monitoring

### T1 Promotion Criteria (v1.2.0)

T1 means **evidence-backed load-bearing**, not merely "frequently referenced." High
reference count alone does not predict A/B contribution — the v3 layered ablation
(240 cells, n=15) found that `lessons.md` (highest-ref layer) had a Δ within noise,
while `skills+plugins` (lower ref count) cleanly separated from the noise floor
(pitfall-avoided rate 80% → 43% when stripped).

To promote a layer to T1, require **one** of:

| Evidence path | Field | Effect in report |
|---|---|---|
| A/B-harness result above noise floor | `ab_evidence.delta_vs_noop_se >= 1.0` | Clean T1 — no disclaimer |
| No harness data yet | `evidence: "reference-count-only"` | T1 with explicit disclaimer shown |

If neither condition is met, `score_health.py` emits a `t1_warnings` entry. The
audit report **must** surface this warning — a silently-promoted T1 erodes trust in
the tier system.

Cross-reference: ab-harness v1.2.0 §"Noise floor: design a no-op cell" and
§"C11 saturation: everything-stripped ties the no-op control."

### Correctness-vs-Latency Annotation (v1.2.0)

The v3 finding that `skills+plugins` (cell C4) was the **fastest** cell on generic
tasks (7.2 turns / $0.30 vs C0's 18.8 turns / $0.57) means skills add latency on
routine work even when they help on pitfall-prone tasks. Do **not** blanket-recommend
"install more skills."

For each **skill-type layer**, annotate with:

| Field | Source | Values |
|---|---|---|
| `pitfall_benefit` | Existing T1/T1.5/T2 tier | T1 / T1.5 / T2 |
| `latency_cost` | `ab_evidence.latency_turns_generic` | `low` (<1 turn) / `medium` (1–3) / `high` (>3) / `unmeasured` |
| `trigger_surface_match` | `ref_count` vs `delta_vs_noop_se` | `matched` / `mismatched` / `unmeasured` |

**Mismatch pattern:** `ref_count > 10` AND `delta_vs_noop_se < 1.0`. This is the
v3 signature of a skill that's frequently seen but adds latency on generic tasks
without reducing pitfalls on the user's measured workload.

Skills with `trigger_surface_match == "mismatched"` feed the new **"Skills with
mismatched trigger surface"** report section (see Phase 3).

**Updated recommendation engine logic:**
- Mine recent session prompts for dominant task-type patterns before recommending any skill
- Recommend only skills whose trigger surface matches the user's common pitfall patterns
- Flag high-ref / low-A/B-signal skills as "noise" — they add latency without pitfall benefit
- Do NOT blanket-recommend installing more skills

## Phase 3: Report

Generate two output files:

### Markdown Report
Save to `docs/handoffs/ecosystem_audit_report.md` with:
- Executive summary with key metrics
- Per-category findings table
- Prioritized recommendations
- Cleanup script (ready-to-run shell commands)

### Interactive HTML Report
Save to `docs/handoffs/ecosystem_audit_report.html` with:
- Read `assets/report_template.html` for the base template
- The template uses a dark terminal theme (GitHub-dark background, Inter headings,
  Fira Code / IBM Plex Mono data, teal accent `#2DD4A8`)
- Populate the template by replacing data placeholders with audit results
- Features: sticky sidebar nav, tabbed data views, radar chart (6 axes),
  animated counters, hover tooltips, bar charts, priority-coded action cards

#### Skills with Mismatched Trigger Surface (v1.2.0)

When `trigger_surface_mismatches` is non-empty, add a section to both markdown and
HTML reports listing each mismatched skill with:

- Skill name
- `ref_count` (how often it appeared in session logs)
- `delta_vs_noop_se` (A/B signal strength vs no-op control)
- `latency_cost` (estimated turn overhead on generic tasks)
- Recommendation: review trigger description, narrow scope to pitfall-prone tasks only, or deprecate

If no mismatches, omit the section entirely.

Also emit a T1 warning block when `t1_warnings` is non-empty, listing each affected
layer by name with the remediation options (add `ab_evidence` or set
`evidence: "reference-count-only"`).

### Radar Chart Data

The radar chart shows 6 axes: Skills, Memory, Handoffs, ADRs, Docs, Worktrees.
Each axis shows the health percentage from Phase 2 scoring.

Two overlaid polygons:
- **Teal (active/healthy)**: the health score per category
- **Red (dormant/stale)**: the complement (100% - health)

**Never fabricate a score.** If any sub-check for an axis could not be computed (e.g., memory-hygiene unavailable, `user_role.md` missing, version mismatch), render that axis as `N/A` with a hatched pattern and list blockers in the report's "Coverage" section. A partial average is worse than a missing reading.

## Complementary Skills

This skill is designed to work alongside, not replace:

- **ab-harness** (v1.2.0+): Counterfactual A/B + layered-ablation harness. Run to generate
  the `ab_evidence` fields this skill uses for T1 validation and latency annotation.
  Key sections: §"Noise floor: design a no-op cell" (threshold calibration) and
  §"C11 saturation: everything-stripped ties the no-op control" (why all-stripped ≠ signal).
- **schliff:doctor**: Structural quality scoring of individual SKILL.md files (7-dimension
  scoring). Run after ecosystem-audit identifies dormant skills to assess whether they're
  worth keeping based on quality.
- **schliff:mesh**: Cross-skill trigger overlap detection. Run after ecosystem-audit identifies
  overlap clusters to get detailed conflict analysis.
- **memory-hygiene**: Deep persistent knowledge store audit. Run after ecosystem-audit flags
  memory health issues to get specific fixes (tiered loading, contradiction detection,
  axiom promotion).
- **skill-portfolio-audit**: Portfolio-wide README/badge standardization. Run after
  ecosystem-audit cleanup to polish the remaining skills.

## Edge Cases

- **No session logs**: If `~/.claude/projects/` has no JSONL files, skip skill usage analysis
  and note "no session data available" in the report. Other categories still work.
- **No worktrees**: Score is 100% (clean state). Note "no worktrees found" in report.
- **Single project**: Still audit global files (axioms, lessons, skills).
- **Very large ecosystems** (>500 skills): Use subagent parallelism aggressively. Batch
  skill classification into groups of 50.
