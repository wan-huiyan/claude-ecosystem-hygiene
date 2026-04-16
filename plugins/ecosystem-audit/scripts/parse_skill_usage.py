#!/usr/bin/env python3
"""Parse Claude Code session JSONL logs to extract skill invocation data.

Usage:
    python parse_skill_usage.py [--days 30] [--json]

Output: skill invocation counts, last invoked dates, and per-project breakdown.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

def find_session_files(base_dir: Path, max_age_days: int = 30) -> list[Path]:
    """Find JSONL session files modified within the time window."""
    cutoff = datetime.now().timestamp() - (max_age_days * 86400)
    files = []
    for project_dir in base_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for f in project_dir.glob("*.jsonl"):
            if f.stat().st_mtime >= cutoff:
                files.append(f)
    return sorted(files)

def extract_skill_invocations(filepath: Path) -> list[dict]:
    """Extract Skill() tool_use calls from a JSONL session file."""
    invocations = []
    project = filepath.parent.name
    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or '"Skill"' not in line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = record.get("message", {})
                content = msg.get("content", [])
                if isinstance(content, str):
                    continue
                for block in content:
                    if isinstance(block, dict) and block.get("name") == "Skill":
                        inp = block.get("input", {})
                        skill_name = inp.get("skill", "unknown")
                        invocations.append({
                            "skill": skill_name,
                            "args": inp.get("args", ""),
                            "timestamp": record.get("timestamp", ""),
                            "session_file": filepath.name,
                            "project": project,
                        })
    except (PermissionError, OSError):
        pass
    return invocations

def main():
    days = 30
    output_json = False
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--days" and i < len(sys.argv) - 1:
            days = int(sys.argv[i + 1])
        elif arg == "--json":
            output_json = True

    base = Path.home() / ".claude" / "projects"
    if not base.exists():
        print(json.dumps({"error": "No projects directory found"}) if output_json else "No projects directory found")
        sys.exit(1)

    files = find_session_files(base, days)
    all_invocations = []
    for f in files:
        all_invocations.extend(extract_skill_invocations(f))

    # Aggregate
    skill_counts = defaultdict(int)
    skill_last_seen = {}
    skill_projects = defaultdict(set)
    for inv in all_invocations:
        name = inv["skill"]
        skill_counts[name] += 1
        ts = inv.get("timestamp", "")
        if ts and (name not in skill_last_seen or ts > skill_last_seen[name]):
            skill_last_seen[name] = ts
        skill_projects[name].add(inv["project"])

    sorted_skills = sorted(skill_counts.items(), key=lambda x: -x[1])

    result = {
        "window_days": days,
        "session_files_scanned": len(files),
        "total_invocations": len(all_invocations),
        "unique_skills_invoked": len(skill_counts),
        "skills": [
            {
                "name": name,
                "count": count,
                "last_invoked": skill_last_seen.get(name, ""),
                "projects": sorted(skill_projects[name]),
            }
            for name, count in sorted_skills
        ],
    }

    if output_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Session files scanned: {len(files)} (last {days} days)")
        print(f"Total invocations: {len(all_invocations)}")
        print(f"Unique skills invoked: {len(skill_counts)}")
        print()
        print(f"{'Skill':<35} {'Count':>6}  {'Last Invoked':<20}  Projects")
        print("-" * 90)
        for name, count in sorted_skills:
            last = skill_last_seen.get(name, "")[:10]
            projs = ", ".join(p[:30] for p in sorted(skill_projects[name]))
            print(f"{name:<35} {count:>6}  {last:<20}  {projs}")

if __name__ == "__main__":
    main()
