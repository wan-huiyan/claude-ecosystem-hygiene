#!/usr/bin/env python3
"""
Shadow-mode recall@K replay — the decisive measurement for the retrieval-hook design.

Ground truth = the user's ACTUAL model-initiated invocations of episodic-trap skills across
all ~/.claude/projects/**/*.jsonl transcripts. For each such invocation we ask: if the
two-trigger hook (UserPromptSubmit per prompt + PostToolUse per tool-call) had been running,
would retrieve() have surfaced that trap in top-K at SOME trigger point BEFORE the agent
invoked it? recall@K = fraction of events where it would have.

Honest limits (read alongside docs/research/2026-06-04-episodic-lesson-recall-substrate-research.md):
- Floor, not point estimate: ground truth = traps that DID fire; can't measure traps that
  SHOULD have fired but were buried (no counterfactual).
- Classifier noise: "trap" vs "procedure" is heuristic (retrieve.classify_kind).
- model-initiated filter: drops invocations whose immediately-preceding user msg is `/<skill>`.
"""
import json, os, pathlib, sys, re
from collections import defaultdict
import retrieve as R

PROJECTS = pathlib.Path(os.path.expanduser("~/.claude/projects"))
IDX = {r["id"]: r for r in R.load_index()}
TRAPS = {k for k, r in IDX.items() if r["kind"] == "trap"}
K_LEVELS = (1, 3, 5, 10)

def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""

def iter_events():
    """Yield (skill_id, triggers) for each first-per-session model-initiated trap invocation.
    triggers = ordered list of {q, cmd, fp} seen before the invocation."""
    for f in PROJECTS.rglob("*.jsonl"):
        triggers, seen, last_user = [], set(), ""
        try:
            lines = f.read_text(errors="ignore").splitlines()
        except Exception:
            continue
        for line in lines:
            try:
                d = json.loads(line)
            except Exception:
                continue
            typ = d.get("type"); msg = d.get("message", {})
            content = msg.get("content") if isinstance(msg, dict) else None
            if typ == "user":
                txt = _text(content).strip()
                if txt:
                    last_user = txt
                    triggers.append({"q": txt[:600], "cmd": "", "fp": ""})
            elif typ == "assistant" and isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict) or b.get("type") != "tool_use":
                        continue
                    name, inp = b.get("name"), b.get("input", {}) or {}
                    if name == "Bash" and inp.get("command"):
                        triggers.append({"q": inp["command"][:400], "cmd": inp["command"][:400], "fp": ""})
                    elif name in ("Edit", "Write", "Read") and inp.get("file_path"):
                        triggers.append({"q": inp["file_path"], "cmd": "", "fp": inp["file_path"]})
                    elif name == "Skill":
                        sid = (inp.get("skill") or "").strip()
                        if sid in TRAPS and sid not in seen:
                            seen.add(sid)
                            # model-initiated filter: skip if the user literally typed /<skill>
                            if re.match(r"^\s*/" + re.escape(sid) + r"\b", last_user or ""):
                                continue
                            yield sid, list(triggers)

def best_rank(skill_id, triggers, kmax=10):
    """Min rank (1-based) skill_id achieves over all triggers; None if never in top-kmax."""
    best = None
    for t in triggers[-40:]:           # bound: last 40 trigger points before invocation
        hits = R.retrieve(t["q"], k=kmax, kinds=("trap",), tool_cmd=t["cmd"], file_path=t["fp"])
        for rank, h in enumerate(hits, 1):
            if h["id"] == skill_id:
                if best is None or rank < best:
                    best = rank
                break
        if best == 1:
            break
    return best

def main():
    events = list(iter_events())
    n = len(events)
    if not n:
        print("no model-initiated trap-invocation events found"); return
    per_event = []                       # (skill, best_rank)
    by_trap = defaultdict(list)          # skill -> [best_rank,...]
    for sid, trg in events:
        r = best_rank(sid, trg)
        per_event.append((sid, r))
        by_trap[sid].append(r)
    def rate(ranks, K): return sum(1 for r in ranks if r is not None and r <= K) / len(ranks)

    print(f"events (first-per-session, model-initiated trap invocations): {n}")
    print(f"distinct traps: {len(by_trap)}")
    print("\n[EVENT-weighted] recall@K — how often, across all real trap moments, the hook would have surfaced it:")
    for K in K_LEVELS:
        ranks = [r for _, r in per_event]
        print(f"  recall@{K:<2} = {rate(ranks,K):5.1%}  ({sum(1 for r in ranks if r and r<=K)}/{n})")
    miss = sum(1 for _, r in per_event if r is None)
    print(f"  miss (never top-10) = {miss/n:5.1%}")

    # TRAP-weighted: average each distinct trap's own recall first, then mean — removes the
    # high-frequency-trap skew (a trap that fired 50× counts once, not 50×).
    print("\n[TRAP-weighted] recall@K — average per distinct trap (de-skews high-frequency traps):")
    for K in K_LEVELS:
        per_trap = [rate(rs, K) for rs in by_trap.values()]
        print(f"  recall@{K:<2} = {sum(per_trap)/len(per_trap):5.1%}")

    print("\ntop traps by event count (the skew):")
    for sid, rs in sorted(by_trap.items(), key=lambda kv: -len(kv[1]))[:8]:
        hit5 = sum(1 for r in rs if r and r <= 5)
        print(f"  {len(rs):>3}×  recall@5 {hit5}/{len(rs)}  {sid}")

    pathlib.Path(pathlib.Path(__file__).parent / "recall-results.json").write_text(json.dumps({
        "events": n, "distinct_traps": len(by_trap),
        "event_weighted": {f"recall@{K}": round(rate([r for _,r in per_event],K),4) for K in K_LEVELS},
        "trap_weighted": {f"recall@{K}": round(sum(rate(rs,K) for rs in by_trap.values())/len(by_trap),4) for K in K_LEVELS},
        "per_trap_event_counts": {s: len(rs) for s, rs in sorted(by_trap.items(), key=lambda kv:-len(kv[1]))},
    }, indent=2))
    print("\nwrote recall-results.json")

if __name__ == "__main__":
    main()
