#!/usr/bin/env python3
"""
Phase 6 — decompose recall + firing by TRIGGER MODE (user_prompt vs post_tool).

Phase 5 showed the distinctive-token gate can't separate recall from firing. The shadow log is 95%
post_tool (fires on every bash/edit). Hypothesis: genuine-trap recall mostly comes from natural-
language USER PROMPTS; the per-tool-call firing is mostly noise. If so, the fix is to drop the
post_tool trigger (or gate it hard), not to tune a token threshold.

For each genuine-trap event, compute the best rank reachable from (a) user_prompt triggers only,
(b) post_tool triggers only. For firing, split the stride sample by mode. Reports recall@K and
firing per mode, so we can see what restricting the LIVE trigger to user_prompt would cost/save.
"""
import json, os, pathlib, re
import retrieve as R
from recompute_with_overrides import _text
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
PROJECTS = pathlib.Path(os.path.expanduser("~/.claude/projects"))
INJ_CAP = 4000
FLOOR = 6.0

LAB = {l["id"]: l["kind"] for l in json.loads((HERE / "intent-labels.json").read_text())["labels"]}
IDX = R.load_index()
for r in IDX: r["kind"] = LAB.get(r["id"], r["kind"])
BM = R.BM25([r["tokens"] for r in IDX])
TRAPS = {r["id"] for r in IDX if r["kind"] == "trap"}
TRAP_IDX = [i for i, r in enumerate(IDX) if r["kind"] == "trap"]
TRAP_TOKSET = {i: set(IDX[i]["tokens"]) for i in TRAP_IDX}
POST = {}
for i in TRAP_IDX:
    for t in set(IDX[i]["tokens"]): POST.setdefault(t, []).append(i)
PREFIX_DOCS, GLOB_DOCS = {}, {}
for i in TRAP_IDX:
    for tp in IDX[i]["tool_prefixes"]: PREFIX_DOCS.setdefault(tp, []).append(i)
    for g in IDX[i]["file_globs"]: GLOB_DOCS.setdefault(g, []).append(i)

def ranked(query, cmd="", fp="", k=5):
    q = R._tokens(query) + R._tokens(cmd) + R._tokens(fp)
    if not q: return []
    qset = set(q); cmd_tokens = set(R._tokens(cmd)); fpl = (fp or "").lower()
    cand = set()
    for t in qset: cand.update(POST.get(t, ()))
    for tp in cmd_tokens: cand.update(PREFIX_DOCS.get(tp, ()))
    if fpl:
        for tp, docs in PREFIX_DOCS.items():
            if fpl.startswith(tp): cand.update(docs)
        for g, docs in GLOB_DOCS.items():
            if fpl.endswith(g.lstrip("*")): cand.update(docs)
    scored = []
    for i in cand:
        r = IDX[i]; s = BM.score(i, q)
        if cmd and any(tp in cmd_tokens or fpl.startswith(tp) for tp in r["tool_prefixes"]): s += 3.0
        if fp and any(fpl.endswith(g.lstrip("*")) for g in r["file_globs"]): s += 2.0
        if s <= 0: continue
        scored.append((s, r["id"]))
    scored.sort(key=lambda x: -x[0])
    return [(sid, round(s, 3)) for s, sid in scored[:k]]

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
                    last_user = txt; triggers.append({"mode": "user_prompt", "q": txt[:600], "cmd": "", "fp": ""})
            elif typ == "assistant" and isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict) or b.get("type") != "tool_use": continue
                    name, inp = b.get("name"), b.get("input", {}) or {}
                    if name == "Bash" and inp.get("command"):
                        triggers.append({"mode": "post_tool", "q": inp["command"][:400], "cmd": inp["command"][:400], "fp": ""})
                    elif name in ("Edit", "Write") and inp.get("file_path"):
                        triggers.append({"mode": "post_tool", "q": inp["file_path"], "cmd": "", "fp": inp["file_path"]})
                    elif name == "Skill":
                        sid = (inp.get("skill") or "").strip()
                        if sid in TRAPS and sid not in seen:
                            seen.add(sid)
                            if re.match(r"^\s*/" + re.escape(sid) + r"\b", last_user or ""): continue
                            events.append((sid, list(triggers)))
        yield triggers, events

# per event: best rank from each mode (apply FLOOR like the live hook)
ev_up, ev_pt = [], []     # (sid, best_rank or None) restricted to that mode
inj_up, inj_pt = [], []   # firing top-3 >= FLOOR per mode
def best_rank(sid, trg, mode):
    best = None
    for t in trg[-40:]:
        if t["mode"] != mode: continue
        for rank, (hid, sc) in enumerate(ranked(t["q"], t["cmd"], t["fp"]), 1):
            if hid == sid and sc >= FLOOR:
                if best is None or rank < best: best = rank
                break
        if best == 1: break
    return best

for triggers, events in walk():
    for sid, trg in events:
        ev_up.append((sid, best_rank(sid, trg, "user_prompt")))
        ev_pt.append((sid, best_rank(sid, trg, "post_tool")))
    if len(inj_up) + len(inj_pt) < INJ_CAP * 2:
        for t in triggers[::3]:
            if len(inj_up) + len(inj_pt) >= INJ_CAP * 2: break
            hits = ranked(t["q"], t["cmd"], t["fp"], k=3)
            fires = any(sc >= FLOOR for _h, sc in hits)
            (inj_up if t["mode"] == "user_prompt" else inj_pt).append(fires)

N = len(ev_up)
def rec(ev, K): return sum(1 for _s, r in ev if r is not None and r <= K) / N
def recU(ev, K):  # union of two modes per event
    pass
# union recall: trap recalled if reachable from EITHER mode
def union_rank(a, b):
    if a is None: return b
    if b is None: return a
    return min(a, b)
ev_union = [(s, union_rank(ru, rp)) for (s, ru), (_s, rp) in zip(ev_up, ev_pt)]

def trapw(ev, K):
    by = defaultdict(list)
    for s, r in ev: by[s].append(1 if (r is not None and r <= K) else 0)
    return sum(sum(v)/len(v) for v in by.values()) / len(by)

print(f"genuine-trap events: {N}   trap pool: {len(TRAPS)}   FLOOR={FLOOR}")
print(f"injection sample: user_prompt={len(inj_up)}  post_tool={len(inj_pt)}\n")
print("RECALL@K (floor-applied) by which trigger mode the trap was reachable from:")
print(f"{'mode':14} | {'rec@1':>6} {'rec@3':>6} {'rec@5':>6} | {'twR@5':>6}")
for label, ev in (("user_prompt", ev_up), ("post_tool", ev_pt), ("UNION(both)", ev_union)):
    print(f"{label:14} | {rec(ev,1):6.1%} {rec(ev,3):6.1%} {rec(ev,5):6.1%} | {trapw(ev,5):6.1%}")
print(f"\nFIRING rate (top-3 >= {FLOOR}) by trigger mode:")
print(f"  user_prompt: {sum(inj_up)/max(1,len(inj_up)):5.1%}  ({sum(inj_up)}/{len(inj_up)})")
print(f"  post_tool:   {sum(inj_pt)/max(1,len(inj_pt)):5.1%}  ({sum(inj_pt)}/{len(inj_pt)})")
print(f"\nTrigger VOLUME (how often each mode occurs in the sampled stream):")
tot = len(inj_up) + len(inj_pt)
print(f"  user_prompt: {len(inj_up)/tot:5.1%} of triggers   post_tool: {len(inj_pt)/tot:5.1%} of triggers")
print("  => per-turn injection VOLUME if LIVE only on user_prompt = firing_up * share_up vs everything")

# how many events are recalled ONLY by post_tool (would be lost if we drop post_tool)?
only_pt = sum(1 for (s,ru),(s2,rp) in zip(ev_up,ev_pt) if (ru is None or ru>5) and (rp is not None and rp<=5))
only_up = sum(1 for (s,ru),(s2,rp) in zip(ev_up,ev_pt) if (rp is None or rp>5) and (ru is not None and ru<=5))
both = sum(1 for (s,ru),(s2,rp) in zip(ev_up,ev_pt) if (ru is not None and ru<=5) and (rp is not None and rp<=5))
print(f"\n@5 recall attribution: only-user_prompt={only_up}  only-post_tool={only_pt}  both={both}  (of {N})")
