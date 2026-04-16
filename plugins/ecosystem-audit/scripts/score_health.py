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

    print(json.dumps(scores, indent=2))

if __name__ == "__main__":
    main()
