# ecosystem-audit

**Version:** 1.2.0 | **License:** MIT | **Author:** wan-huiyan

Full-coverage Claude Code ecosystem audit across 9 artifact categories. Orchestrates 4
parallel scan subagents, scores each category on a 0–100% health scale, and generates
an interactive HTML report with a radar chart and prioritized P0/P1/P2 cleanup actions.

Part of [`claude-ecosystem-hygiene`](https://github.com/wan-huiyan/claude-ecosystem-hygiene)
— the audit → measure → clean → stay-consistent pipeline.

## What It Does

```
Phase 1: Scan (parallel subagents)
  ├── 1A. Skills: parse JSONL session logs, classify by domain
  ├── 1B. Memory: delegate to memory-hygiene Phase 1 (single source of truth)
  ├── 1C. Handoffs: count and classify lifecycle state
  └── 1D. ADRs + Docs: validate status fields, check links

Phase 2: Score (sequential)
  ├── Health % per category (Skills / Memory / Handoffs / ADRs / Docs / Worktrees)
  ├── T1 promotion evidence check (v1.2.0)
  ├── Correctness-vs-latency annotation per skill layer (v1.2.0)
  └── Prioritized recommendations (P0/P1/P2)

Phase 3: Report (write files)
  ├── Markdown → docs/handoffs/ecosystem_audit_report.md
  └── Interactive HTML → docs/handoffs/ecosystem_audit_report.html
       (dark theme, radar chart, action cards, cleanup script)
```

## v1.2.0: What's New

### Change A — A/B-evidence-backed T1 promotion

T1 now means **evidence-backed load-bearing**, not merely "frequently referenced."
Motivated by the v3 layered ablation (240 cells, n=15): `lessons.md` was the highest-ref
layer but its Δ was within noise, while `skills+plugins` cleanly separated from the noise
floor (80% → 43% pitfall-avoided rate when stripped).

**T1 promotion requires one of:**
- `ab_evidence.delta_vs_noop_se >= 1.0` — Δ above the noise floor (≥ 1 SE vs no-op cell), OR
- `evidence: "reference-count-only"` — explicit disclaimer that surfaces in the report

Layers missing both conditions generate a `t1_warning` in the scoring output and report.

Cross-reference: ab-harness v1.2.0 §"Noise floor: design a no-op cell" and
§"C11 saturation: everything-stripped ties the no-op control."

### Change B — Correctness-vs-latency annotation per skill layer

v3 finding: `skills+plugins` (C4) was the fastest cell on generic tasks (7.2 turns /
$0.30 vs C0's 18.8 turns / $0.57) but added latency overhead. Skills help on pitfall-prone
tasks but cost something on routine work. The audit now captures this trade-off per layer.

Each skill-type layer is annotated with:

| Field | Values | Meaning |
|---|---|---|
| `latency_cost` | `low` / `medium` / `high` / `unmeasured` | Turn overhead on generic tasks |
| `trigger_surface_match` | `matched` / `mismatched` / `unmeasured` | Alignment of skill triggers to user's actual task patterns |

**Mismatch pattern:** high `ref_count` + `delta_vs_noop_se < 1.0 SE`. The skill appears
frequently but does not measurably reduce pitfalls — it adds latency without benefit.

A new report section **"Skills with mismatched trigger surface"** lists these skills.
The recommendation engine no longer blanket-recommends installing more skills; it mines
session prompts for dominant task patterns first.

## T1/T1.5/T2 Tier Map

| Tier | Path | Promotion criteria |
|------|------|--------------------|
| T0 | `~/.claude/axioms.md`, `CLAUDE.md` | Session-start essentials; always loaded |
| **T1** | `MEMORY.md`, primary skills | **A/B evidence OR explicit disclaimer (v1.2.0)** |
| T1.5 | Phase templates, project rules | Utilization-backed |
| T2 | Memory topic files | Referenced in MEMORY.md index |
| T3 | Lessons, archives | Compression backlog candidate |

## Scoring Scripts

| Script | Purpose | CLI |
|--------|---------|-----|
| `scripts/parse_skill_usage.py` | Parse JSONL logs for skill invocations | `python parse_skill_usage.py --days 30 --json` |
| `scripts/score_health.py` | Compute 0-100% health per category | `python score_health.py --input audit_data.json` |

### score_health.py — v1.2.0 Input/Output

**Input** (`audit_data.json`) — new optional fields:

```json
{
  "skills_active": 35,
  "skills_total": 394,
  "layers": [
    {
      "name": "lessons.md",
      "tier": "T1",
      "ref_count": 156,
      "ab_evidence": { "delta_vs_noop_se": 0.3 }
    }
  ],
  "skill_layers": [
    {
      "name": "skills+plugins",
      "tier": "T1",
      "ref_count": 42,
      "ab_evidence": { "delta_vs_noop_se": 2.4, "latency_turns_generic": 0.8 }
    }
  ]
}
```

**Output** — new optional fields (only present when applicable):

```json
{
  "skills": 8.9,
  "memory": 74.5,
  "t1_warnings": [
    {
      "layer": "lessons.md",
      "warning": "T1 tier without A/B evidence. Add ab_evidence.delta_vs_noop_se >= 1.0 or set evidence='reference-count-only'."
    }
  ],
  "skill_annotations": [...],
  "trigger_surface_mismatches": [...]
}
```

Backward compatible: if `layers` and `skill_layers` are absent, output is identical to v1.1.0.

## Complementary Skills

- **ab-harness** (v1.2.0+) — Generates the `ab_evidence` fields used for T1 validation and
  latency annotation. Run first to measure which layers actually improve outcomes.
- **memory-hygiene** — Deep audit of the T1 memory stack. Run when audit flags memory health.
- **schliff:doctor** — Per-skill structural quality scoring. Run on dormant skills after audit.
- **schliff:mesh** — Cross-skill trigger overlap detection. Run on overlap clusters.

## Edge Cases

- **No session logs**: Skip skill usage analysis; note "no session data available."
- **No worktrees**: Score 100% (clean state).
- **memory-hygiene unavailable**: Render Memory axis as `N/A` with hatched pattern.
- **No `layers` / `skill_layers` in input**: Skip T1 check and latency annotation; scores unchanged.
