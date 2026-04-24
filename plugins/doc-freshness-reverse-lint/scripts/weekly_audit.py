#!/usr/bin/env python3
"""Weekly cron audit (safety net for reverse-lint).

Scans project docs under docs/{research,decisions,findings,runbooks}/**/*.md
and cross-checks them against recent negation rules in ~/.claude/lessons.md,
~/.claude/axioms.md, and per-project feedback_*.md entries.

Reports:
- Literal phrase hits (same engine as reverse_lint.py)
- Near-duplicate normative claims in docs that contradict newer lesson entries
  (token-overlap ≥ threshold against negation rule titles)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from reverse_lint import (  # noqa: E402
    Rule,
    find_doc_files,
    grep_phrase,
    parse_feedback_style,
    parse_lessons_style,
)


def token_overlap(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z0-9\-]+", a.lower()))
    tb = set(re.findall(r"[a-z0-9\-]+", b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def recent_rules(max_age_days: int) -> list[Rule]:
    """Pull rules from all memory files. max_age_days is informational —
    without git we can't cheaply date individual entries; we report all rules
    and the user can filter by inspection."""
    rules: list[Rule] = []
    for f in [HOME / ".claude" / "lessons.md", HOME / ".claude" / "axioms.md"]:
        if f.exists():
            rules.extend(parse_lessons_style(f))
    for fb in (HOME / ".claude" / "projects").rglob("memory/feedback_*.md"):
        rules.extend(parse_feedback_style(fb))
    return rules


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", type=Path, required=True)
    ap.add_argument("--max-age-days", type=int, default=30)
    ap.add_argument("--overlap-threshold", type=float, default=0.7)
    ap.add_argument("--human", action="store_true")
    args = ap.parse_args()

    rules = recent_rules(args.max_age_days)
    files = find_doc_files(args.project_root)

    report = {
        "project_root": str(args.project_root),
        "rule_count": len(rules),
        "doc_files_scanned": len(files),
        "literal_hits": [],
        "near_duplicate_hits": [],
    }

    for rule in rules:
        # Weekly audit runs broader (no hook trigger), so tighten the phrase
        # threshold from 2 to 3 tokens to keep noise low.
        if len(rule.negated_phrase.split()) < 3:
            continue
        # Literal match (same as reverse-lint)
        matches = grep_phrase(files, rule.negated_phrase)
        matches = [
            m for m in matches
            if not m.file.endswith(Path(rule.source_file).name)
        ]
        if matches:
            report["literal_hits"].append({
                "rule_id": rule.rule_id,
                "rule_title": rule.rule_title,
                "negated_phrase": rule.negated_phrase,
                "source": rule.source_file,
                "matches": [
                    {"file": m.file, "line": m.line, "content": m.content}
                    for m in matches
                ],
            })

        # Near-duplicate check: scan each doc line for high overlap with rule title
        title_lc = rule.rule_title.lower()
        if len(title_lc.split()) < 3:
            continue
        for f in files:
            if f.name == Path(rule.source_file).name:
                continue
            try:
                for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
                    ls = line.strip()
                    if len(ls) < 20 or len(ls) > 300:
                        continue
                    # Only normative claims
                    if not re.search(r"\b(should|must|use|prefer|recommend|always|never)\b",
                                     ls, re.IGNORECASE):
                        continue
                    ov = token_overlap(title_lc, ls)
                    if ov >= args.overlap_threshold:
                        report["near_duplicate_hits"].append({
                            "rule_id": rule.rule_id,
                            "rule_title": rule.rule_title,
                            "source": rule.source_file,
                            "file": str(f),
                            "line": i,
                            "content": ls[:200],
                            "overlap": round(ov, 2),
                        })
            except Exception:
                continue

    if args.human:
        print(f"Weekly doc freshness audit — {args.project_root}")
        print(f"  Rules considered: {report['rule_count']}")
        print(f"  Doc files scanned: {report['doc_files_scanned']}")
        print(f"  Literal hits: {len(report['literal_hits'])}")
        print(f"  Near-duplicate hits: {len(report['near_duplicate_hits'])}")
        for kind, items in (("LITERAL", report["literal_hits"]),
                            ("NEAR-DUPLICATE", report["near_duplicate_hits"])):
            if not items:
                continue
            print(f"\n-- {kind} --")
            for item in items:
                print(f"  {item['rule_id']}: {item['rule_title'][:80]}")
                if kind == "LITERAL":
                    print(f"    Negated phrase: \"{item['negated_phrase']}\"")
                    for m in item["matches"]:
                        rel = os.path.relpath(m["file"], args.project_root)
                        print(f"    {rel}:{m['line']}: {m['content']}")
                else:
                    rel = os.path.relpath(item["file"], args.project_root)
                    print(f"    (overlap {item['overlap']}) {rel}:{item['line']}: {item['content']}")
    else:
        print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
