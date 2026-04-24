# Claude Code Ecosystem Hygiene

Four complementary skills for auditing, measuring, and maintaining Claude Code ecosystem health. **Audit → measure → clean → stay consistent:** identify what's HOT vs DORMANT, measure whether the HOT artifacts actually improve outcomes, prune what doesn't pull its weight, and keep project docs in sync with the lessons that supersede them.

[![license](https://img.shields.io/github/license/wan-huiyan/claude-ecosystem-hygiene)](LICENSE)
[![last commit](https://img.shields.io/github/last-commit/wan-huiyan/claude-ecosystem-hygiene)](https://github.com/wan-huiyan/claude-ecosystem-hygiene/commits)
[![Claude Code](https://img.shields.io/badge/Claude_Code-marketplace-orange)](https://claude.com/claude-code)

![Ecosystem Audit Demo](docs/demo-screenshot.png)

## The audit → measure → clean → stay-consistent pipeline

```
┌─────────────────┐   ┌──────────────────┐   ┌────────────────┐   ┌───────────────────┐
│ ecosystem-audit │──▶│ claude-code-ab-  │──▶│ memory-hygiene │──▶│ doc-freshness-    │
│                 │   │ harness          │   │                │   │ reverse-lint      │
│ which artifacts │   │ do the HOT ones  │   │ prune what the │   │ catch project     │
│ are HOT vs      │   │ actually improve │   │ harness showed │   │ docs that still   │
│ DORMANT?        │   │ task outcomes?   │   │ adds no value  │   │ contradict the    │
│                 │   │                  │   │                │   │ new lessons       │
│ minutes, $0     │   │ 30min–3hrs, $10+ │   │ minutes, $0    │   │ event-driven, $0  │
└─────────────────┘   └──────────────────┘   └────────────────┘   └───────────────────┘
```

Reference counts are a starting point, not a verdict. `ecosystem-audit` catches DORMANT artifacts cheaply. But a HOT artifact might still be noise — it gets touched and adds nothing. Only the A/B harness can separate "HOT and useful" from "HOT and ritual." When ≥5 tasks show no outcome change under ablation, `memory-hygiene` has a concrete signal to consolidate or delete. Finally, `doc-freshness-reverse-lint` watches memory-file edits for new "don't X" rules and surfaces project docs that still recommend X — the step that prevents your freshly-corrected lessons from being silently undone by stale research notes.

## What's Inside

| Plugin | Stage | What it does |
|--------|-------|--------------|
| [`ecosystem-audit`](plugins/ecosystem-audit/) | **Audit** | Full-coverage audit across 9 artifact categories (skills, memory, handoffs, ADRs, plans, reviews, worktrees, automation, provenance). Parses JSONL session logs for real skill invocation data. Produces interactive HTML report with radar chart and prioritized P0/P1/P2 cleanup actions. |
| [`claude-code-ab-harness`](plugins/claude-code-ab-harness/) | **Measure** | Counterfactual A/B + layered-ablation harness. Runs each task twice (setup-ON vs setup-OFF) or strips one layer at a time from a full baseline, then reports turns, tool calls, cost, and pitfall-keyword hits. **Heavyweight: $10–$80, 30min–3hrs.** Pair with the audit to turn reference-count signals into actual quality measurements. |
| [`memory-hygiene`](plugins/memory-hygiene/) | **Clean** | Deep audit of the persistent knowledge stack: MEMORY.md bloat (200-line threshold), axioms (Cowan cap of 12), lessons deduplication, ADR integrity (MADR 4.0), tier-placement violations, session compression backlog. Grounded in cognitive science (Cowan 2001) and LLM research (Liu et al. 2024). |
| [`doc-freshness-reverse-lint`](plugins/doc-freshness-reverse-lint/) | **Stay consistent** | Event-driven PostToolUse hook + weekly cron that catches project `docs/` contradicting the lessons that supersede them. When you add "don't sort by p-value" to `lessons.md`, the hook greps `docs/research/**` for literal matches and surfaces them as candidate stale claims — file:line only, never auto-edits. Conservative guardrails (explicit negation, multi-token phrase, one phrase per rule, silent on zero hits) prevent false positives on qualified content. |

> **Moved:** `skill-trigger-eval-subprocess-blindness` lived here in v1.0.0 but has been
> relocated to [`wan-huiyan/claude-skill-authoring`](https://github.com/wan-huiyan/claude-skill-authoring)
> where it sits alongside other skill-authoring tools. Update your install if you had it.

## Quick Start

```
you: i've been using claude code for a couple months and my ~/.claude folder
     feels bloated. can you audit and tell me what to clean up?

claude: *triggers ecosystem-audit*
        → parses 291 session JSONL files → 35 skills invoked out of 394 installed
        → checks memory via memory-hygiene thresholds → MEMORY.md 506 lines (bloated)
        → classifies 313 handoffs → 167 worktree duplicates identified
        → generates interactive HTML report with radar chart
        → writes cleanup script as P0 action

you: *opens docs/handoffs/ecosystem_audit_report.html*
     sees 8.9% skill utilization, 147 niche-dormant skills safe to uninstall.
     wonders: of the 35 invoked skills, which ones actually improve answers?

claude: *triggers claude-code-ab-harness*
        → validates CLAUDE_CONFIG_DIR=/tmp/claude-empty probe
        → runs 3 hand-picked tasks twice each on setup-ON vs setup-OFF
        → mines session JSONLs for turns, cost, pitfall keywords
        → on n=3: setup prevented 1 of 3 pitfalls (33%), no turn savings
        → recommends layered ablation next for per-layer attribution

you: ok, now i know which layers earn their keep. what do i actually delete?

claude: *triggers memory-hygiene*
        → consumes the ranked layer-contribution list from the harness
        → flags the 8 zero-Δ layers as consolidation candidates
        → applies Cowan cap, MEMORY.md 200-line threshold, lesson dedup
```

## Installation

### Install all four (recommended)

```bash
claude plugin marketplace add wan-huiyan/claude-ecosystem-hygiene
claude plugin install ecosystem-audit@wan-huiyan-ecosystem-hygiene
claude plugin install claude-code-ab-harness@wan-huiyan-ecosystem-hygiene
claude plugin install memory-hygiene@wan-huiyan-ecosystem-hygiene
claude plugin install doc-freshness-reverse-lint@wan-huiyan-ecosystem-hygiene
```

### Install individually via git

```bash
git clone https://github.com/wan-huiyan/claude-ecosystem-hygiene.git /tmp/ceh
cp -r /tmp/ceh/plugins/ecosystem-audit ~/.claude/skills/
cp -r /tmp/ceh/plugins/claude-code-ab-harness ~/.claude/skills/
cp -r /tmp/ceh/plugins/memory-hygiene ~/.claude/skills/
cp -r /tmp/ceh/plugins/doc-freshness-reverse-lint ~/.claude/skills/
```

> **`doc-freshness-reverse-lint` needs a hook** to trigger automatically. After
> install, add the one-line `PostToolUse` hook from its
> [README](plugins/doc-freshness-reverse-lint/README.md#hook-wiring-required-for-event-driven-mode)
> to your `~/.claude/settings.json`. Without the hook, it still runs on demand
> via the weekly audit script — you just lose the event-driven surfacing.

> **Note:** `memory-hygiene` is also available as a standalone repo at
> [`wan-huiyan/memory-hygiene`](https://github.com/wan-huiyan/memory-hygiene).
> Installing from either source yields the same skill. Use this bundle if you want
> it alongside the audit and A/B harness; use the standalone repo if you only want memory-hygiene.

## How They Fit Together

```
┌─────────────────────────────────────────────────────────────┐
│  ecosystem-audit               Scope: the WHOLE ecosystem   │
│    ├─ parses JSONL session logs for skill usage             │
│    ├─ calls memory-hygiene thresholds inline                │
│    ├─ scans handoffs, ADRs, worktrees, automation           │
│    └─ produces interactive HTML with radar chart            │
├─────────────────────────────────────────────────────────────┤
│  claude-code-ab-harness        Scope: outcome measurement   │
│    ├─ CLAUDE_CONFIG_DIR clean-env mechanism                 │
│    ├─ binary A/B (setup-ON vs setup-OFF)                    │
│    ├─ 12-cell layered ablation (strip one layer at a time)  │
│    └─ ranked contribution list feeds back into pruning      │
├─────────────────────────────────────────────────────────────┤
│  memory-hygiene                Scope: persistent knowledge  │
│    ├─ MEMORY.md bloat (>200 lines = truncation risk)        │
│    ├─ axioms cap (Cowan 2001 = 12 items max)                │
│    ├─ lessons dedup + tier placement                        │
│    ├─ ADR integrity (MADR 4.0 compliance)                   │
│    └─ codebase contradiction detection                      │
├─────────────────────────────────────────────────────────────┤
│  doc-freshness-reverse-lint    Scope: project docs/ ↔ memory│
│    ├─ PostToolUse hook on lessons.md / axioms.md / feedback │
│    ├─ extracts negated "don't X" phrase                     │
│    ├─ greps docs/{research,decisions,findings,runbooks}/    │
│    ├─ surfaces candidate stale claims via hookOutput        │
│    └─ weekly cron audit as safety net                       │
└─────────────────────────────────────────────────────────────┘
```

Run `ecosystem-audit` to see the big picture. Point `claude-code-ab-harness` at the HOT artifacts it flagged to see which ones actually change outcomes. When the harness or the audit flags memory issues, drop into `memory-hygiene` for concrete fixes. Once a new lesson lands, `doc-freshness-reverse-lint` catches any project docs that still recommend the retracted approach — closing the loop so future sessions don't re-learn the wrong thing. For skill-authoring tooling (including the subprocess-blindness diagnostic), see [`claude-skill-authoring`](https://github.com/wan-huiyan/claude-skill-authoring).

## What to do with A/B harness results

The A/B harness emits a ranked layer-contribution list — e.g., on one real run
(see [`plugins/claude-code-ab-harness/examples/layered_ablation_example.md`](plugins/claude-code-ab-harness/examples/layered_ablation_example.md))
only 2 of 10 ablated layers had measurable pitfall-prevention loss at n=1.
The other 8 were zero-delta strips. That's the signal `memory-hygiene` is
designed to consume:

- **Δ pitfalls = 0 AND Δ cost > 0 when stripped** → layer adds cost without catching anything on the measured task set. Candidate for consolidation.
- **Δ pitfalls < 0** → layer earned its keep. Keep (or invest more in it).
- **Δ pitfalls = 0 AND Δ cost ≤ 0 when stripped** → layer costs nothing to keep but didn't provably help either. Leave alone, re-evaluate next audit.

Remember the limitations: n=1 rankings tie within noise below the top two slots, and the task set upward-biases pitfall-prevention. Use the harness as evidence for pruning decisions, not proof.

## What You Get

When you ask Claude to audit your ecosystem, you get:

- **Markdown report** at `docs/handoffs/ecosystem_audit_report.md` with summary tables and cleanup actions
- **Interactive HTML report** at `docs/handoffs/ecosystem_audit_report.html` featuring:
  - Radar chart showing health % across 6 axes (skills, memory, handoffs, ADRs, docs, worktrees)
  - Sortable tables per category
  - Priority-coded action cards (P0 red, P1 amber, P2 blue)
  - Ready-to-run cleanup script in a code block
- **Cleanup script** ready to paste into your terminal

## Without These Skills vs With

| Question | Without | With |
|----------|---------|------|
| "Which skills am I actually using?" | `ls ~/.claude/skills \| wc -l` — you get the install count, not usage | Parse JSONL logs → "35 invoked out of 394 in last 30 days (8.9%)" |
| "Is my memory bloated?" | Open MEMORY.md, eyeball it | `wc -l` against thresholds: bloated >200, target ~40 |
| "Are my handoffs stale?" | Manually scan `docs/handoffs/` | Classify as Current/Historical/Orphaned with counts per project |
| "Are my worktrees healthy?" | `git worktree list` — see paths, not staleness | Lifecycle score (EXPECTED / ACCEPTABLE / NEEDS_CLEANUP / ABANDONED) |

## Decision Criteria

Thresholds in **bold** are grounded in published sources.
Thresholds in *italic* are practitioner heuristics — adjust for your domain.

| Metric | Threshold | Source |
|--------|-----------|--------|
| MEMORY.md bloat | **>200 lines = truncation risk** | Claude Code platform limit |
| Axioms count | **12 items max** | [Cowan (2001)](https://doi.org/10.1017/S0140525X01003922) — working memory capacity |
| Position decay in long context | **>30% accuracy loss mid-context** | [Liu et al. (2024) TACL](https://arxiv.org/abs/2307.03172) |
| Skill utilization threshold | *<10% = worth pruning* | Practitioner heuristic |
| Worktree "abandoned" | *unmerged + >14 days* | Practitioner heuristic |
| Session compression | *>30 days + >50 lines + unreferenced* | memory-hygiene convention |

## Limitations

- **Session log scope.** Only skills invoked via the `Skill()` tool show up in the usage analysis. Skills invoked through slash commands (`/causal-impact-campaign`) appear the same as interactive triggers, but anything bypassing the Skill tool (e.g., direct file reads of a SKILL.md) won't be counted.
- **No monthly automation.** The audit runs on demand. There's no built-in cron — if you want it scheduled, combine with the `schedule` skill.
- **Worktree lifecycle scoring is age-based.** A "hot" worktree on a 20-day-old branch that's actively being committed to gets scored as ABANDONED. The metric favors conventional workflows.
- **HTML template styling is opinionated.** The dark terminal theme (GitHub-dark background, Fira Code headings, teal accent) is intentional. Rewrite the template if you want a different aesthetic.
- **Not a replacement for `schliff:doctor` or individual skill tooling.** This bundle covers ecosystem-level breadth. For per-skill structural quality, pair with [schliff](https://github.com/Zandereins/schliff).

## Related Skills

- **[schliff](https://github.com/Zandereins/schliff)** — Per-skill structural quality scoring on 7 dimensions. Runs after ecosystem-audit identifies dormant skills to assess if they're worth keeping.
- **[skill-portfolio-audit](https://github.com/wan-huiyan/skill-portfolio-audit)** — Portfolio-wide README/badge standardization. Run after cleanup to polish remaining skills.
- **[session-handoff](https://github.com/wan-huiyan/session-handoff)** — Creates the handoff docs that this bundle audits.
- **[skill-sync](https://github.com/wan-huiyan/skill-sync)** — Keeps published skills in sync with their GitHub repos.

## Quality Checklist

<details>
<summary>What this bundle guarantees</summary>

- [x] **No client data in any published artifact.** All examples use synthetic SaaS/retail domain names.
- [x] **Canonical plugin layout.** `marketplace.json` in `.claude-plugin/`, plugin manifests in `plugins/<name>/.claude-plugin/plugin.json`, source paths start with `./plugins/`.
- [x] **Per-plugin version tracking.** Each plugin has independent `version` in `plugin.json` and marketplace entry.
- [x] **MIT licensed.** Free to fork, modify, and redistribute.
- [x] **Published thresholds are cited.** Cowan, Liu et al., and platform limits link to sources. Heuristics are labeled as such.
- [x] **HTML report is self-contained.** No external CDN dependencies, works offline after initial font load.
- [x] **JSONL parsing tested on 291 real sessions** (~35 skills, ~226 invocations, all projects).

</details>

## Version History

- **v1.3.0** (2026-04-24) — **Added `doc-freshness-reverse-lint` v1.0.0** as the "stay-consistent" step. Event-driven PostToolUse hook on `lessons.md`/`axioms.md`/`feedback_*.md` + weekly cron safety net. Catches project `docs/` that still recommend approaches the user has since retracted in memory. Conservative guardrails (explicit negation, multi-token phrase, one phrase per rule, silent on zero hits) validated against 93 real negation rules × 43 docs → 0 false positives on a live causal-impact project.
- **v1.2.0** (2026-04-24) — **Added `claude-code-ab-harness` v1.1.0** to complete the audit → measure → clean pipeline. The harness is heavyweight ($10–$80, 30min–3hrs) but converts `ecosystem-audit`'s reference-count signals into real outcome measurements, and produces a ranked layer-contribution list that `memory-hygiene` can consume. Includes sanitized example outputs from the 2026-04-21 binary A/B (27 vs 30 turns, 1 of 3 pitfalls prevented) and the 2026-04-23 layered ablation (skills+plugins −2/3 and lessons.md −1/3 were the only non-zero-Δ strips). Marketplace copy is canonical for this plugin — no cross-repo sync job.
- **v1.1.0** (2026-04-17) — **ecosystem-audit bumped to v1.1.0** (memory-hygiene v3.0 alignment): Memory subagent now delegates to memory-hygiene Phase 1 (single source of truth; prevents drift); T1.5 tier coverage added (`~/.claude/templates/phase_*.md` + `.claude/rules/phase-*.md` with `paths:` glob validity); axiom health now checks classification (Universal/Role/Phase), not just raw count vs Cowan cap; staleness expanded from 2 to 4 signals + agency-aware detection via `user_role.md`; radar chart renders `N/A` with hatched pattern when sub-checks can't compute (no fabricated scores); Memory weighting rebalanced to 6 inputs (25/15/15/10/20/15). Also moved `skill-trigger-eval-subprocess-blindness` to [`claude-skill-authoring`](https://github.com/wan-huiyan/claude-skill-authoring); it was out of scope for this marketplace.
- **v1.0.0** (2026-04-16) — Initial bundle release. Contains ecosystem-audit v1.0.0, memory-hygiene v3.0.0, skill-trigger-eval-subprocess-blindness v1.0.0.

## License

MIT. See [LICENSE](LICENSE).
