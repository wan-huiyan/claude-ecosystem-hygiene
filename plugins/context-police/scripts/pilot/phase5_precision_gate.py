#!/usr/bin/env python3
"""
Phase 5 — design a PRECISION (specificity) gate, on the INTENT-corrected trap set.

S11 blocker: a BM25 score floor fires on ~99.6% of triggers; recall and precision are the same
under-discriminating score. Hypothesis (S11 §Phase 2): real queries share >=2 DISTINCTIVE (high-IDF)
tokens with the right trap; benign ubiquitous triggers share 1 incidental token. So gate on the
COUNT of distinctive matched tokens, not raw BM25 magnitude.

Two changes vs the S11 scripts:
  1. trap set = intent-labels.json (the curated classifier), NOT classify_kind (hyphen-count).
  2. an inverted index for candidate generation, so the full sweep runs in ~1 min, not ~10.

Measures every gate on BOTH axes from ONE retrieval per trigger:
  - RECALL@K over genuine-trap invocation events (must hold ~>= status-quo ~51%): correct trap in
    top-K AND passes the gate at some trigger before the invocation. (@3 and @5 reported.)
  - FIRING over a stride-3 sample of ALL triggers (mostly benign; ~FP rate): >=1 of the top-3 hits
    passes the gate. (the noise/cost side — want it far below 99.6%.)
"""
import json, os, pathlib, re
import retrieve as R
from recompute_with_overrides import _text

HERE = pathlib.Path(__file__).resolve().parent
PROJECTS = pathlib.Path(os.path.expanduser("~/.claude/projects"))
INJ_CAP = 4000
INJECT_K = 3          # the live hook injects top-3

# ---- build the INTENT-corrected index ----
LAB = {l["id"]: l["kind"] for l in json.loads((HERE / "intent-labels.json").read_text())["labels"]}
IDX = R.load_index()
for r in IDX:
    r["kind"] = LAB.get(r["id"], r["kind"])   # fall back to heuristic for any unlabeled
BM = R.BM25([r["tokens"] for r in IDX])
TRAPS = {r["id"] for r in IDX if r["kind"] == "trap"}
TRAP_IDX = [i for i, r in enumerate(IDX) if r["kind"] == "trap"]
TRAP_TOKSET = {i: set(IDX[i]["tokens"]) for i in TRAP_IDX}

# inverted index over TRAP docs only (token -> [doc positions]); + prefix/glob maps for boosts
POST = {}
for i in TRAP_IDX:
    for t in set(IDX[i]["tokens"]):
        POST.setdefault(t, []).append(i)
PREFIX_DOCS = {}     # tool prefix -> [doc i]
GLOB_DOCS = {}       # glob -> [doc i]
for i in TRAP_IDX:
    for tp in IDX[i]["tool_prefixes"]:
        PREFIX_DOCS.setdefault(tp, []).append(i)
    for g in IDX[i]["file_globs"]:
        GLOB_DOCS.setdefault(g, []).append(i)

def ranked(query, cmd="", fp="", k=5):
    """Top-k trap hits, each (id, score, sorted matched-token IDFs desc). Mirrors retrieve scoring
    (BM25 + tool/glob boosts). Candidate set = docs sharing >=1 token OR a matching prefix/glob."""
    q = R._tokens(query) + R._tokens(cmd) + R._tokens(fp)
    if not q:
        return []
    qset = set(q)
    cmd_tokens = set(R._tokens(cmd)); fpl = (fp or "").lower()
    cand = set()
    for t in qset:
        cand.update(POST.get(t, ()))
    for tp in cmd_tokens:
        cand.update(PREFIX_DOCS.get(tp, ()))
    if fpl:
        for tp, docs in PREFIX_DOCS.items():
            if fpl.startswith(tp): cand.update(docs)
        for g, docs in GLOB_DOCS.items():
            if fpl.endswith(g.lstrip("*")): cand.update(docs)
    scored = []
    for i in cand:
        r = IDX[i]
        s = BM.score(i, q)
        if cmd and any(tp in cmd_tokens or fpl.startswith(tp) for tp in r["tool_prefixes"]):
            s += 3.0
        if fp and any(fpl.endswith(g.lstrip("*")) for g in r["file_globs"]):
            s += 2.0
        if s <= 0:
            continue
        matched = qset & TRAP_TOKSET[i]
        idfs = sorted((BM.idf.get(t, 0.0) for t in matched), reverse=True)
        scored.append((s, r["id"], idfs))
    scored.sort(key=lambda x: -x[0])
    return [(sid, round(s, 3), idfs) for s, sid, idfs in scored[:k]]

# ---- gate predicates over a single hit's (score, idfs) ----
def ndist(idfs, tau, n):  return sum(1 for v in idfs if v >= tau) >= n
def idfsum(idfs, tau, s): return sum(v for v in idfs if v >= tau) >= s

def hit_passes(sc, idfs, kind, p):
    if kind == "FLOOR":  return sc >= p["f"]
    if kind == "NDIST":  return ndist(idfs, p["tau"], p["n"])
    if kind == "IDFSUM": return idfsum(idfs, p["tau"], p["s"])
    if kind == "NDISTF": return ndist(idfs, p["tau"], p["n"]) and sc >= p["f"]
    return False

def gate_fires(hits, kind, p):     # any of top-INJECT_K passes?
    return any(hit_passes(sc, idfs, kind, p) for _id, sc, idfs in hits[:INJECT_K])
def trap_passes(hits, sid, kind, p, K):   # correct trap in top-K AND passes gate?
    for _id, sc, idfs in hits[:K]:
        if _id == sid:
            return hit_passes(sc, idfs, kind, p)
    return False

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

event_hits, inj_hits = [], []
for triggers, events in walk():
    for sid, trg in events:
        event_hits.append((sid, [ranked(t["q"], t["cmd"], t["fp"]) for t in trg[-40:]]))
    if len(inj_hits) < INJ_CAP:
        for t in triggers[::3]:
            if len(inj_hits) >= INJ_CAP: break
            inj_hits.append(ranked(t["q"], t["cmd"], t["fp"]))

N, M = len(event_hits), len(inj_hits)
# trap-weighted recall: average each distinct trap's own recall, then mean (de-skew)
from collections import defaultdict
def recall(kind, p, K):
    per = [any(trap_passes(h, sid, kind, p, K) for h in hh) for sid, hh in event_hits]
    return sum(per) / N
def recall_trapw(kind, p, K):
    by = defaultdict(list)
    for sid, hh in event_hits:
        by[sid].append(any(trap_passes(h, sid, kind, p, K) for h in hh))
    return sum(sum(v)/len(v) for v in by.values()) / len(by)
def firing(kind, p):
    return sum(1 for h in inj_hits if gate_fires(h, kind, p)) / M

print(f"intent-trap pool: {len(TRAPS)}   genuine-trap events: {N}   "
      f"injection sample (stride-3, cap {INJ_CAP}): {M}   inject_K={INJECT_K}\n")

def row(label, kind, p):
    print(f"{label:26} | rec@3 {recall(kind,p,3):5.1%} rec@5 {recall(kind,p,5):5.1%}  "
          f"twR@5 {recall_trapw(kind,p,5):5.1%} | FIRE {firing(kind,p):5.1%}")

print("=== BASELINE: score FLOOR (S11 — does not gate) ===")
for f in (0.0, 6.0, 10.0, 20.0):
    row(f"FLOOR f={f}", "FLOOR", {"f": f})
print("\n=== NDIST: >=n matched tokens with IDF>=tau (the specificity gate) ===")
for tau in (3.0, 4.0, 4.5, 5.0):
    for n in (1, 2, 3):
        row(f"NDIST tau={tau} n={n}", "NDIST", {"tau": tau, "n": n})
print("\n=== IDFSUM: sum of matched-IDF(>=tau) >= s ===")
for tau in (3.0, 4.0):
    for s in (8.0, 10.0, 13.0, 16.0):
        row(f"IDFSUM tau={tau} s={s}", "IDFSUM", {"tau": tau, "s": s})
print("\n=== NDIST + FLOOR combined ===")
for tau in (4.0, 4.5):
    for n in (2, 3):
        for f in (8.0, 12.0):
            row(f"NDISTF tau={tau} n={n} f={f}", "NDISTF", {"tau": tau, "n": n, "f": f})
