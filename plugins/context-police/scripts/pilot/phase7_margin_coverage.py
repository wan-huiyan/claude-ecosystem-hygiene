#!/usr/bin/env python3
"""
Phase 7 — confirmation sweep of the two remaining keyword gate families (so the negative result is
bulletproof against "did you try a margin / coverage gate?"). Same two axes as phase5.

  MARGIN(delta)   : fire only if top1.score - top2.score >= delta  (a CLEAR single winner). Hypothesis:
                    a relevant query spikes ONE trap; a benign query matches several weakly (flat top).
  COVERAGE(tau,c) : fire only if the top hit's distinctive-token COVERAGE >= c, where coverage =
                    (#query-matched trap tokens with IDF>=tau) / (#trap tokens with IDF>=tau). Hypothesis:
                    a relevant query covers most of the trap's key terms; an incidental match covers few.
"""
import json, os, pathlib, re
import retrieve as R
from recompute_with_overrides import _text
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
PROJECTS = pathlib.Path(os.path.expanduser("~/.claude/projects"))
INJ_CAP = 4000
INJECT_K = 3
LAB = {l["id"]: l["kind"] for l in json.loads((HERE / "intent-labels.json").read_text())["labels"]}
IDX = R.load_index()
for r in IDX: r["kind"] = LAB.get(r["id"], r["kind"])
BM = R.BM25([r["tokens"] for r in IDX])
TRAPS = {r["id"] for r in IDX if r["kind"] == "trap"}
TRAP_IDX = [i for i, r in enumerate(IDX) if r["kind"] == "trap"]
TRAP_TOKSET = {i: set(IDX[i]["tokens"]) for i in TRAP_IDX}
# distinctive token count per trap (idf>=tau) for coverage denominators
def trap_distinct(i, tau): return sum(1 for t in TRAP_TOKSET[i] if BM.idf.get(t, 0.0) >= tau)
DISTINCT_DEN = {tau: {i: max(1, trap_distinct(i, tau)) for i in TRAP_IDX} for tau in (3.0, 4.0)}
POS = {i: i for i in TRAP_IDX}
POST = {}
for i in TRAP_IDX:
    for t in set(IDX[i]["tokens"]): POST.setdefault(t, []).append(i)
PREFIX_DOCS, GLOB_DOCS = {}, {}
for i in TRAP_IDX:
    for tp in IDX[i]["tool_prefixes"]: PREFIX_DOCS.setdefault(tp, []).append(i)
    for g in IDX[i]["file_globs"]: GLOB_DOCS.setdefault(g, []).append(i)

def ranked(query, cmd="", fp="", k=5):
    """top-k (id, score, docpos, matched_idfs)."""
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
        idfs = sorted((BM.idf.get(t, 0.0) for t in (qset & TRAP_TOKSET[i])), reverse=True)
        scored.append((s, r["id"], i, idfs))
    scored.sort(key=lambda x: -x[0])
    return scored[:k]

def margin_pass(hits, i_in_topk, delta):
    # the hit at position p passes if (score[p] is the top1 AND top1-top2>=delta). We gate the WHOLE
    # trigger on the top-1 margin (a clear winner); a hit passes the gate only if it's that top-1.
    if len(hits) == 0: return False
    top1 = hits[0][0]; top2 = hits[1][0] if len(hits) > 1 else 0.0
    return (top1 - top2) >= delta and i_in_topk == 0

def cov_pass(hit, tau, c):
    _s, _id, i, idfs = hit
    nmatch = sum(1 for v in idfs if v >= tau)
    return (nmatch / DISTINCT_DEN[tau][i]) >= c

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
                if txt: last_user = txt; triggers.append({"q": txt[:600], "cmd": "", "fp": ""})
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

event_hits, inj_hits = [], []
for triggers, events in walk():
    for sid, trg in events:
        event_hits.append((sid, [ranked(t["q"], t["cmd"], t["fp"]) for t in trg[-40:]]))
    if len(inj_hits) < INJ_CAP:
        for t in triggers[::3]:
            if len(inj_hits) >= INJ_CAP: break
            inj_hits.append(ranked(t["q"], t["cmd"], t["fp"]))
N, M = len(event_hits), len(inj_hits)

def recall_margin(delta, K):
    def ev_ok(sid, hh):
        for hits in hh:
            for p, (s, hid, i, idfs) in enumerate(hits[:K]):
                if hid == sid and margin_pass(hits, p, delta): return True
        return False
    return sum(ev_ok(sid, hh) for sid, hh in event_hits) / N
def fire_margin(delta):
    return sum(1 for hits in inj_hits if any(margin_pass(hits, p, delta) for p in range(min(INJECT_K, len(hits))))) / M
def recall_cov(tau, c, K):
    def ev_ok(sid, hh):
        for hits in hh:
            for hit in hits[:K]:
                if hit[1] == sid and cov_pass(hit, tau, c): return True
        return False
    return sum(ev_ok(sid, hh) for sid, hh in event_hits) / N
def fire_cov(tau, c):
    return sum(1 for hits in inj_hits if any(cov_pass(h, tau, c) for h in hits[:INJECT_K])) / M

print(f"events: {N}  injection: {M}  trap pool: {len(TRAPS)}\n")
print("=== MARGIN (top1-top2 >= delta; clear single winner) ===")
print(f"{'delta':>6} | {'rec@3':>6} {'rec@5':>6} | {'FIRE':>6}")
for d in (3.0, 6.0, 10.0, 20.0, 40.0):
    print(f"{d:6.1f} | {recall_margin(d,3):6.1%} {recall_margin(d,5):6.1%} | {fire_margin(d):6.1%}")
print("\n=== COVERAGE (matched distinctive / trap distinctive >= c) ===")
print(f"{'tau':>5} {'c':>5} | {'rec@3':>6} {'rec@5':>6} | {'FIRE':>6}")
for tau in (3.0, 4.0):
    for c in (0.3, 0.5, 0.7):
        print(f"{tau:5.1f} {c:5.2f} | {recall_cov(tau,c,3):6.1%} {recall_cov(tau,c,5):6.1%} | {fire_cov(tau,c):6.1%}")
