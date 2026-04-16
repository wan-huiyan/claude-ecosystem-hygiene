---
name: ecosystem-audit
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

Check all persistent memory artifacts across all projects.

**Scan targets:**
- `~/.claude/projects/*/memory/` — all project memory directories
- `~/.claude/axioms.md` — behavioral overrides
- `~/.claude/lessons.md` — global lessons archive
- `~/.claude/CLAUDE.md` — retrieval strategy

**Apply memory-hygiene thresholds:**

| Metric | Threshold | Source |
|--------|-----------|--------|
| MEMORY.md line count | >200 lines = bloated, target ~40 | memory-hygiene |
| Axioms count | >12 items = over Cowan cap | memory-hygiene (Cowan 2001) |
| Session compression | >30 days + >50 lines + unreferenced | memory-hygiene |
| Archive split | sessions_archive > 200 lines | memory-hygiene |
| Frontmatter | All topic files need name/description/type | memory-hygiene |
| CLAUDE.md | Must say "grep" not "read" for lessons | memory-hygiene |

**Per-file checks:**
- Orphan detection (file exists but not in MEMORY.md index)
- Staleness (references completed projects, contains relative dates)
- Cross-project duplicates (same feedback file in multiple projects)
- Frontmatter validation (name, description, type fields)

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

**Memory**: Weighted composite of sub-checks:
- MEMORY.md line count vs threshold (weight: 30%)
- Frontmatter compliance rate (weight: 20%)
- Axioms count vs Cowan cap (weight: 15%)
- Staleness rate of topic files (weight: 20%)
- Session compression backlog (weight: 15%)

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

### Radar Chart Data

The radar chart shows 6 axes: Skills, Memory, Handoffs, ADRs, Docs, Worktrees.
Each axis shows the health percentage from Phase 2 scoring.

Two overlaid polygons:
- **Teal (active/healthy)**: the health score per category
- **Red (dormant/stale)**: the complement (100% - health)

## Complementary Skills

This skill is designed to work alongside, not replace:

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
