#!/usr/bin/env python3
"""Compute health percentages per audit category.

Usage:
    python score_health.py --input audit_data.json

Input format: JSON with counts per category.
Output: health scores 0-100 for radar chart axes.
"""

import json
import sys
from pathlib import Path

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

def annotate_layer_tier(harness_layer: dict | None, noise_floor_pp: float | None) -> dict:
    """Annotate a layer with a noise-floor tier (v1.2.0).

    Consumes one entry from claude-code-ab-harness v1.2.0+ output:
        {"name": "skills", "delta_pp": -37.1, "n_covered": 15, "tier": "T1"}

    Returns {"tier": "T1|T1.5|T2|T3|T?", "evidence": "..."} where T? means no
    harness evidence is available (never inferred from reference count).
    """
    if harness_layer is None or noise_floor_pp is None:
        return {"tier": "T?", "evidence": "no_harness_output"}
    n = harness_layer.get("n_covered", 0)
    if n < 10:
        return {"tier": "T?", "evidence": f"n_covered={n} < 10 minimum"}
    # Prefer harness-provided tier (the harness has the full per-cell variance
    # data we don't ship here). Fall back to a simple distance-from-noise rule
    # using a 1σ ≈ √(0.25/n)·100 sampling-error bound.
    if "tier" in harness_layer and harness_layer["tier"] in {"T1", "T1.5", "T2", "T3"}:
        return {"tier": harness_layer["tier"], "evidence": "harness_provided"}
    import math
    sigma_pp = math.sqrt(0.25 / max(n, 1)) * 100  # ~12.9pp at n=15
    delta = abs(harness_layer.get("delta_pp", 0.0))
    distance_from_noise = delta - noise_floor_pp
    if distance_from_noise >= sigma_pp:
        return {"tier": "T1", "evidence": f"|Δ|−noise={distance_from_noise:.1f}pp ≥ 1σ={sigma_pp:.1f}pp (n={n})"}
    if distance_from_noise >= 0:
        return {"tier": "T1.5", "evidence": f"|Δ|−noise={distance_from_noise:.1f}pp (within 1σ above noise, n={n})"}
    if delta > 0.0:
        return {"tier": "T2", "evidence": f"|Δ|={delta:.1f}pp ≤ noise={noise_floor_pp:.1f}pp (n={n})"}
    return {"tier": "T3", "evidence": f"ties no-op floor (n={n})"}


def score_skill_trigger_match(skill: dict, user_pitfall_categories: list[str] | None) -> dict:
    """Decide whether a HOT skill has a mismatched trigger surface (v1.2.0).

    skill: {"name": str, "invocation_count": int, "domain_tags": [str, ...], "p50_rank": int}
    user_pitfall_categories: top-N unaddressed pitfall categories from ab-harness output.

    Returns {"mismatched": bool, "recommendation": str, "reason": str}.
    Never blanket-recommends "install more skills" — only flags HOT-but-mismatched.
    """
    if user_pitfall_categories is None:
        return {"mismatched": False, "recommendation": "skip", "reason": "no_harness_pitfall_tags"}
    if skill.get("p50_rank", 100) > 50:
        return {"mismatched": False, "recommendation": "skip", "reason": "not_in_top_50pct"}
    domain_tags = set(skill.get("domain_tags", []))
    pitfalls = set(user_pitfall_categories[:3])
    if domain_tags & pitfalls:
        return {"mismatched": False, "recommendation": "keep", "reason": "trigger_matches_pitfall"}
    return {
        "mismatched": True,
        "recommendation": "uninstall_or_scope_narrow",
        "reason": f"top_pitfalls={sorted(pitfalls)} disjoint from skill_tags={sorted(domain_tags)}",
    }


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

    # v1.2.0: annotate per-layer tier from optional harness output
    harness = data.get("ab_harness") or {}
    noise = harness.get("noise_floor_pp")
    layers_by_name = {l.get("name"): l for l in harness.get("layers", [])}
    scores["tiers"] = {
        axis: annotate_layer_tier(layers_by_name.get(axis), noise)
        for axis in ("skills", "memory", "handoffs", "adrs", "docs", "worktrees")
    }

    # v1.2.0: skills correctness-vs-latency overlay (signed Δ vs no-op control)
    skills_harness = layers_by_name.get("skills") or {}
    scores["skills_overlay"] = {
        "correctness_delta_pp": skills_harness.get("delta_pp"),
        "latency_delta_turns": skills_harness.get("delta_turns"),
        "latency_delta_dollars": skills_harness.get("delta_dollars"),
        "covered_n": skills_harness.get("n_covered"),
    }

    print(json.dumps(scores, indent=2))

if __name__ == "__main__":
    main()
