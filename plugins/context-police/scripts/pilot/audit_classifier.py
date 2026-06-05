#!/usr/bin/env python3
"""
Phase 0 — classifier audit (advisor-elevated keystone).
The trap/procedure split (retrieve.classify_kind) feeds BOTH the recall replay (what counts as
a trap event) AND the eventual disable-model-invocation flip (what gets hidden). If a reusable
PROCEDURE is mislabeled 'trap', the flip would HIDE something that fires by name — pure recall loss.

This prints the FIRED skills (ground truth that they recall by *some* channel today) with their
current kind + description, so the trap/procedure boundary can be judged against reality, and
quantifies: how many fired 'traps' are likely procedures, and at what firing frequency.
"""
import json, pathlib
import retrieve as R

HERE = pathlib.Path(__file__).resolve().parent
idx = {r["id"]: r for r in R.load_index()}
kinds = {}
for r in idx.values():
    kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
print(f"INDEX: {len(idx)} skills  ->  " + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))

recall = json.loads((HERE / "recall-results.json").read_text())
fired = recall["per_trap_event_counts"]   # only 'trap'-kind skills are counted as events
print(f"FIRED (counted as trap events): {len(fired)} distinct, {sum(fired.values())} events\n")

print(f"{'cnt':>4}  {'kind':<9}  {'id':<58}  one_line_fix")
print("-" * 140)
for sid, cnt in sorted(fired.items(), key=lambda kv: -kv[1]):
    r = idx.get(sid, {})
    print(f"{cnt:>4}  {r.get('kind','?'):<9}  {sid:<58}  {(r.get('one_line_fix') or '')[:60]}")
