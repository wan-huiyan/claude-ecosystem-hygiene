#!/usr/bin/env python3
"""
Phase 2 — floor-applied recall@K + injection (noise) rate + relative-floor. (efficient: retrieve
ONCE per trigger, evaluate every floor against cached hits.)

The rank-only replay measures whether a trap reaches top-K; the LIVE hook injects only
`if h.score >= FLOOR` (default 6.0). So shipped recall <= rank-only recall. On the CORRECTED
(genuine-trap) pool this reports:
  - floor-applied recall@K (trap in top-K AND score>=FLOOR at some trigger before invocation),
  - injection rate (fraction of trigger points where the hook would fire = the cost side),
  - a RELATIVE floor (keep a hit only if score >= ratio * top-1 score at that trigger).
Per trigger we cache the top-10 (id,score) once so floors are evaluated without re-retrieving.
"""
import json, os, pathlib, re
import retrieve as R
from recompute_with_overrides import corrected_index, _text

HERE = pathlib.Path(__file__).resolve().parent
PROJECTS = pathlib.Path(os.path.expanduser("~/.claude/projects"))
IDX_PATH = HERE / "_idx_phase2.jsonl"
rows = corrected_index()
IDX_PATH.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
R._CACHE.clear()
TRAPS = {r["id"] for r in rows if r["kind"] == "trap"}
INJ_CAP = 4000   # cap the injection sample for runtime

def hits_of(t):
    return R.retrieve(t["q"], k=10, kinds=("trap",), tool_cmd=t["cmd"], file_path=t["fp"], path=IDX_PATH)

def walk():
    for f in PROJECTS.rglob("*.jsonl"):
        triggers, seen, last_user, events = [], set(), "", []
        try: lines = f.read_text(errors="ignore").splitlines()
        except Exception: continue
        for line in lines:
            try: d = json.loads(line)
            except Exception: continue
            typ = d.get("type"); msg = d.get("message", {})
            content = msg.get("content") if isinstance(msg, dict) else None
            if typ == "user":
                txt = _text(content).strip()
                if txt:
                    last_user = txt; triggers.append({"q": txt[:600], "cmd": "", "fp": ""})
            elif typ == "assistant" and isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict) or b.get("type") != "tool_use": continue
                    name, inp = b.get("name"), b.get("input", {}) or {}
                    if name == "Bash" and inp.get("command"):
                        triggers.append({"q": inp["command"][:400], "cmd": inp["command"][:400], "fp": ""})
                    elif name in ("Edit", "Write") and inp.get("file_path"):
                        triggers.append({"q": inp["file_path"], "cmd": "", "fp": inp["file_path"]})
                    elif name == "Skill":
                        sid = (inp.get("skill") or "").strip()
                        if sid in TRAPS and sid not in seen:
                            seen.add(sid)
                            if re.match(r"^\s*/" + re.escape(sid) + r"\b", last_user or ""): continue
                            events.append((sid, list(triggers)))
        yield triggers, events

# Per event: (rank, trap_score, top1_score) over last 40 triggers where trap is in top-10.
# Injection: cache top-10 scores for a stride sample of all triggers (the cost side), retrieve once.
all_events, inj_scores = [], []
for triggers, events in walk():
    for sid, trg in events:
        pairs = []
        for t in trg[-40:]:
            h = hits_of(t); top1 = h[0]["score"] if h else 0.0
            for rank, x in enumerate(h, 1):
                if x["id"] == sid: pairs.append((rank, x["score"], top1)); break
        all_events.append((sid, pairs))
    if len(inj_scores) < INJ_CAP:
        for t in triggers[::3]:
            if len(inj_scores) >= INJ_CAP: break
            inj_scores.append([x["score"] for x in hits_of(t)[:3]])   # top-3 scores cached once

K_LEVELS, FLOORS = (1, 3, 5), (0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0)
N, M = len(all_events), len(inj_scores)
print(f"genuine-trap events: {N}   injection sample (stride-3, cap {INJ_CAP}): {M}\n")

print("FLOOR-APPLIED recall@K  (trap in top-K AND score>=FLOOR at some trigger):")
print(f"{'floor':>6} | " + "  ".join(f"@{K}".rjust(7) for K in K_LEVELS))
for F in FLOORS:
    cells = [f"{sum(1 for _,p in all_events if any(r<=K and s>=F for r,s,_ in p))/N:7.1%}" for K in K_LEVELS]
    print(f"{F:6.1f} | " + "  ".join(cells))

print("\nINJECTION RATE  (fraction of sampled triggers where top-3 has >=1 hit with score>=FLOOR):")
for F in FLOORS:
    fire = sum(1 for scs in inj_scores if any(s >= F for s in scs))
    print(f"  floor {F:5.1f}: fires on {fire/M:5.1%} of triggers")

print("\nRELATIVE floor recall@K  (trap in top-K AND trap_score >= max(2.0, ratio*top1_score)):")
print(f"{'ratio':>6} | " + "  ".join(f"@{K}".rjust(7) for K in K_LEVELS))
for ratio in (0.5, 0.6, 0.7, 0.8, 0.9):
    cells = [f"{sum(1 for _,p in all_events if any(r<=K and s>=max(2.0,ratio*t1) for r,s,t1 in p))/N:7.1%}"
             for K in K_LEVELS]
    print(f"{ratio:6.1f} | " + "  ".join(cells))
print("  [relative injection rate, top-3]")
for ratio in (0.6, 0.7, 0.8):
    fire = sum(1 for scs in inj_scores if scs and any(s >= max(2.0, ratio*scs[0]) for s in scs))
    print(f"    ratio {ratio}: fires on {fire/M:5.1%} of triggers")

try: os.remove(IDX_PATH)
except OSError: pass
