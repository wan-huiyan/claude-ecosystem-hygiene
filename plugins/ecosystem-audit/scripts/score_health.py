#!/usr/bin/env python3
"""Compute health percentages per audit category.

Usage:
    python score_health.py --input audit_data.json

Input format: JSON with counts per category.
Output: health scores 0-100 for radar chart axes.

v1.2.0 additions:
  - layers[]           T1 promotion evidence check (Change A)
  - skill_layers[]     correctness-vs-latency annotation (Change B)
"""

import json
import sys
from pathlib import Path

# Δ vs no-op cell must exceed this many SEs to count as A/B evidence for T1.
# Grounded in v3 layered ablation: single-layer Δ ≤ +27pp is statistical fog at n=15.
AB_EVIDENCE_SE_THRESHOLD = 1.0

def score_skills(active: int, total: int) -> float:
    """Simple utilization rate."""
    return round(100 * active / total, 1) if total else 100.0

def score_memory(memory_lines_max: int, frontmatter_pct: float,
                 axioms_count: int, stale_pct: float, compress_backlog: int) -> float:
    """Weighted composite: MEMORY.md bloat, frontmatter, axioms, staleness, compression."""
    # MEMORY.md bloat (target 40, max 200)
    bloat_score = max(0, min(100, (200 - memory_lines_max) / 160 * 100))
    # Axioms vs Cowan cap of 12
    axiom_score = 100 if axioms_count <= 12 else max(0, 100 - (axioms_count - 12) * 10)
    # Staleness and compression (invert)
    stale_score = max(0, 100 - stale_pct)
    compress_score = max(0, 100 - compress_backlog * 10)
    return round(
        bloat_score * 0.30
        + frontmatter_pct * 0.20
        + axiom_score * 0.15
        + stale_score * 0.20
        + compress_score * 0.15,
        1,
    )

def score_handoffs(current: int, total: int) -> float:
    return round(100 * current / total, 1) if total else 100.0

def score_adrs(active: int, total: int) -> float:
    return round(100 * active / total, 1) if total else 100.0

def score_docs(active: int, total: int) -> float:
    """Plans + reviews + findings + tasks."""
    return round(100 * active / total, 1) if total else 100.0

def score_worktrees(worktrees: list[dict]) -> float:
    """Lifecycle score: weighted average by state.

    Each worktree dict should have keys: age_days (int), merged (bool).
    States:
      - EXPECTED: unmerged, <=7 days -> 100%
      - ACCEPTABLE: unmerged, 7-14 days -> 75%
      - NEEDS_CLEANUP: merged -> 25%
      - ABANDONED: unmerged, >14 days -> 0%
    If no worktrees exist, score is 100%.
    """
    if not worktrees:
        return 100.0
    scores = []
    for wt in worktrees:
        age = wt.get("age_days", 0)
        merged = wt.get("merged", False)
        if merged:
            scores.append(25)
        elif age <= 7:
            scores.append(100)
        elif age <= 14:
            scores.append(75)
        else:
            scores.append(0)
    return round(sum(scores) / len(scores), 1)

def check_t1_promotion(layer: dict) -> dict | None:
    """Return a warning dict if a T1-tier layer lacks A/B evidence, else None.

    T1 means 'evidence-backed load-bearing'. Requires one of:
    - ab_evidence.delta_vs_noop_se >= AB_EVIDENCE_SE_THRESHOLD (signal above noise floor), OR
    - evidence == 'reference-count-only' (explicit disclaimer; surfaces in report)

    See: ab-harness v1.2.0 §'Noise floor: design a no-op cell'
    """
    if layer.get("tier") != "T1":
        return None
    ab = layer.get("ab_evidence") or {}
    delta_se = ab.get("delta_vs_noop_se")
    if delta_se is not None and delta_se >= AB_EVIDENCE_SE_THRESHOLD:
        return None
    if layer.get("evidence") == "reference-count-only":
        return None
    return {
        "layer": layer.get("name", "unknown"),
        "warning": (
            f"T1 tier without A/B evidence. Add ab_evidence.delta_vs_noop_se "
            f">= {AB_EVIDENCE_SE_THRESHOLD} or set evidence='reference-count-only'."
        ),
    }


def annotate_skill_latency(layer: dict) -> dict:
    """Add latency_cost and trigger_surface_match annotations to a skill layer.

    Latency cost is derived from ab_evidence.latency_turns_generic (turn overhead
    on generic, non-pitfall-prone tasks). Flagged 'unmeasured' if no A/B data.

    Trigger surface mismatch: high ref_count + delta_vs_noop_se below noise floor.
    This is the v3 signature of a skill that's frequently seen but adds latency on
    generic tasks without reducing pitfalls on the user's measured workload.

    See: ab-harness v1.2.0 §'C11 saturation'
    """
    out = dict(layer)
    ab = layer.get("ab_evidence") or {}

    turns = ab.get("latency_turns_generic")
    if turns is None:
        out["latency_cost"] = "unmeasured"
    elif turns < 1.0:
        out["latency_cost"] = "low"
    elif turns < 3.0:
        out["latency_cost"] = "medium"
    else:
        out["latency_cost"] = "high"

    delta_se = ab.get("delta_vs_noop_se")
    ref = layer.get("ref_count", 0)
    if delta_se is None:
        out["trigger_surface_match"] = "unmeasured"
    elif ref > 10 and delta_se < AB_EVIDENCE_SE_THRESHOLD:
        out["trigger_surface_match"] = "mismatched"
        out["mismatch_reason"] = (
            f"ref_count={ref} but delta_vs_noop_se={delta_se:.2f} < "
            f"{AB_EVIDENCE_SE_THRESHOLD}. Adds latency on generic tasks "
            "without reducing pitfalls on the measured workload."
        )
    else:
        out["trigger_surface_match"] = "matched"
    return out


def main():
    inp = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--input" and i < len(sys.argv) - 1:
            inp = sys.argv[i + 1]
    if not inp:
        print("Usage: score_health.py --input audit_data.json", file=sys.stderr)
        sys.exit(1)

    data = json.loads(Path(inp).read_text())

    scores = {
        "skills": score_skills(
            data.get("skills_active", 0), data.get("skills_total", 1)
        ),
        "memory": score_memory(
            data.get("memory_max_lines", 40),
            data.get("frontmatter_pct", 100),
            data.get("axioms_count", 0),
            data.get("stale_memory_pct", 0),
            data.get("compress_backlog", 0),
        ),
        "handoffs": score_handoffs(
            data.get("handoffs_current", 0), data.get("handoffs_total", 1)
        ),
        "adrs": score_adrs(data.get("adrs_active", 0), data.get("adrs_total", 1)),
        "docs": score_docs(data.get("docs_active", 0), data.get("docs_total", 1)),
        "worktrees": score_worktrees(data.get("worktrees", [])),
    }
    scores["overall"] = round(sum(scores.values()) / len(scores), 1)

    # Change A: T1 promotion evidence check
    layers = data.get("layers", [])
    t1_warnings = [w for layer in layers if (w := check_t1_promotion(layer))]

    # Change B: correctness-vs-latency annotation
    skill_layers = data.get("skill_layers", [])
    skill_annotations = [annotate_skill_latency(s) for s in skill_layers]
    trigger_surface_mismatches = [
        s for s in skill_annotations
        if s.get("trigger_surface_match") == "mismatched"
    ]

    result = dict(scores)
    if t1_warnings:
        result["t1_warnings"] = t1_warnings
    if skill_annotations:
        result["skill_annotations"] = skill_annotations
    if trigger_surface_mismatches:
        result["trigger_surface_mismatches"] = trigger_surface_mismatches

    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
