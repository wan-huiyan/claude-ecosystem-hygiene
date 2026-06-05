#!/usr/bin/env python3
"""
Phase 8 — the EMBEDDINGS PRECISION PROBE (issue #1). Tests the ONE lever S12 left
untested: can a SEMANTIC (cosine) gate CUT FIRING while HOLDING RECALL on the
user_prompt path — the separation a keyword (BM25) retriever could not achieve?

Scope: user_prompt path ONLY. The S12 analysis showed post_tool (shell commands /
file paths) is exactly where natural-language semantics is weakest, so embeddings'
only candidate win is signal-bearing NL prompts. Even a positive here is a
LOW-VOLUME assist (user_prompt is ~11% of triggers), never a force-load replacement.

Method mirrors phase6 so the figures are directly comparable to s12-results.json:
  - recall over genuine-trap events, restricted to user_prompt triggers in the window
  - firing over a stride sample of user_prompt triggers (~ false-positive rate)
  - precision_when_firing = (recall@K * n_events) / (firing * T_up)   [s12's definition]

PRE-REGISTERED keep-bar (decided BEFORE running; see ADR 0004 / followup-2 prompt):
  PASS (keep hook live on user_prompt-only as a low-volume assist):
        precision_when_firing >= 2.0%  AND  recall@5 (user_prompt) >= 0.50 * baseline_up_recall
  else FAIL -> the semantic gate does not separate either -> REMOVE the two hook lines.
  (2.0% is ~6x keyword's strictest gate 0.31% and ~40x the floor baseline 0.05%.
   Even a PASS = ~98% noise when it fires; framed as a marginal assist, user decides.)

Embedder: minishlab/potion-base-8M (model2vec static, 256-dim, ~30MB) — genuine
distilled-transformer semantics, not TF-IDF (which would just be keyword again).
"""
import json, os, pathlib, re
import numpy as np
from model2vec import StaticModel

HERE = pathlib.Path(__file__).resolve().parent
PROJECTS = pathlib.Path(os.path.expanduser("~/.claude/projects"))
SK = pathlib.Path(os.path.expanduser("~/.claude/skills"))
LAB = {l["id"]: l["kind"] for l in json.loads((HERE / "intent-labels.json").read_text())["labels"]}
TRAP_IDS = [i for i, k in LAB.items() if k == "trap"]
IDX = {}
for ln in (HERE / "lesson-index.jsonl").read_text().splitlines():
    if ln.strip():
        r = json.loads(ln); IDX[r["id"]] = r


def _text(content):
    if isinstance(content, str): return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def read_desc(tid):
    p = SK / tid / "SKILL.md"
    try: txt = p.read_text(errors="ignore")
    except Exception: return ""
    m = re.match(r'^---\s*\n(.*?)\n---', txt, re.S)
    if not m: return ""
    fm = m.group(1)
    dm = re.search(r'^description:\s*(.+?)(?=\n[a-zA-Z_-]+:\s|\Z)', fm, re.S | re.M)
    return dm.group(1).strip().replace('\n', ' ') if dm else ""


def dekebab(s): return s.replace("-", " ")


print("building trap doc embeddings...")
trap_texts = []
for tid in TRAP_IDS:
    desc = read_desc(tid)
    fix = IDX.get(tid, {}).get("one_line_fix", "")
    trap_texts.append(f"{dekebab(tid)}. {desc} {fix}".strip())

M = StaticModel.from_pretrained('minishlab/potion-base-8M')


def embed(texts):
    v = np.asarray(M.encode(list(texts)), dtype=np.float32)
    n = np.linalg.norm(v, axis=1, keepdims=True); n[n == 0] = 1.0
    return v / n


TRAP_EMB = embed(trap_texts)                      # (n_trap, 256) L2-normalized
tid_pos = {t: i for i, t in enumerate(TRAP_IDS)}
n_trap = len(TRAP_IDS)
print(f"  {n_trap} trap docs embedded, dim={TRAP_EMB.shape[1]}")

# ---- walk corpus: genuine-trap events (user_prompt window) + strided up firing sample + total up count
TRAPSET = set(TRAP_IDS)
events = []         # (trap_id, [user_prompt strings in last-40 window])
up_sample = []      # strided user_prompt strings (firing denominator sample)
T_up_total = 0      # total user_prompt triggers in the corpus (true denominator)
STRIDE = 3
CAP = 6000

for f in PROJECTS.rglob("*.jsonl"):
    ups, seen, last_user = [], set(), ""
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
                last_user = txt; ups.append(txt[:600]); T_up_total += 1
        elif typ == "assistant" and isinstance(content, list):
            for b in content:
                if not isinstance(b, dict) or b.get("type") != "tool_use": continue
                if b.get("name") == "Skill":
                    sid = ((b.get("input", {}) or {}).get("skill") or "").strip()
                    if sid in TRAPSET and sid not in seen:
                        seen.add(sid)
                        if re.match(r"^\s*/" + re.escape(sid) + r"\b", last_user or ""): continue
                        events.append((sid, ups[-40:]))
    for q in ups[::STRIDE]:
        if len(up_sample) < CAP: up_sample.append(q)

n_events = len(events)
print(f"genuine-trap events: {n_events}   T_up(total user_prompt triggers): {T_up_total}")
print(f"firing sample (strided user_prompt): {len(up_sample)}")

# events with at least one user_prompt query in window (reachable-in-principle)
ev_with_up = sum(1 for _t, ups in events if ups)
print(f"events with >=1 user_prompt in window: {ev_with_up}")

# ---- embed all event-window queries (dedup) + the firing sample
ev_qs = []
ev_query_idx = []   # per event: list of indices into ev_qs
for _t, ups in events:
    idxs = []
    for q in ups:
        idxs.append(len(ev_qs)); ev_qs.append(q)
    ev_query_idx.append(idxs)
EV_EMB = embed(ev_qs) if ev_qs else np.zeros((0, TRAP_EMB.shape[1]), np.float32)
SAMP_EMB = embed(up_sample) if up_sample else np.zeros((0, TRAP_EMB.shape[1]), np.float32)

# cosine matrices
EV_SIM = EV_EMB @ TRAP_EMB.T if len(ev_qs) else np.zeros((0, n_trap))     # (Q, n_trap)
SAMP_TOP1 = (SAMP_EMB @ TRAP_EMB.T).max(axis=1) if len(up_sample) else np.zeros(0)  # (S,)

# baseline (no cosine floor) user_prompt recall@K — for the >=50% bar
def recall_at(K, thr):
    hit = 0
    for ei, (tid, _ups) in enumerate(events):
        pos = tid_pos.get(tid)
        if pos is None: continue
        best = False
        for qi in ev_query_idx[ei]:
            sims = EV_SIM[qi]
            # rank of correct trap
            order = np.argsort(-sims)
            topK = order[:K]
            if pos in topK and sims[pos] >= thr:
                best = True; break
        hit += 1 if best else 0
    return hit / n_events if n_events else 0.0

def firing_at(thr):
    if len(SAMP_TOP1) == 0: return 0.0
    return float((SAMP_TOP1 >= thr).mean())

base_up_recall5 = recall_at(5, -1.0)   # no floor -> pure top-5 reachability on user_prompt
print(f"\nBASELINE user_prompt recall@5 (no cosine floor) = {base_up_recall5:.1%}")
print(f"(cf s12 keyword user_prompt-only recall@5 = 22.9%)")

print(f"\n{'thr':>5} | {'rec@3':>6} {'rec@5':>6} | {'firing':>7} | {'prec@fire':>9} | ceiling")
rows = []
for thr in [0.30, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]:
    r3 = recall_at(3, thr); r5 = recall_at(5, thr); fr = firing_at(thr)
    fires = fr * T_up_total
    prec = (r5 * n_events) / fires if fires > 0 else 0.0
    ceiling = n_events / fires if fires > 0 else float('inf')
    rows.append((thr, r3, r5, fr, prec, ceiling))
    print(f"{thr:5.2f} | {r3:6.1%} {r5:6.1%} | {fr:7.2%} | {prec:9.3%} | {ceiling:.2%}")

# ---- verdict against the pre-registered bar
PASS_PREC = 0.02
PASS_REC = 0.50 * base_up_recall5
best = None
for thr, r3, r5, fr, prec, ceil in rows:
    if prec >= PASS_PREC and r5 >= PASS_REC:
        if best is None or prec > best[4]:
            best = (thr, r3, r5, fr, prec, ceil)
print("\n=== VERDICT vs pre-registered keep-bar ===")
print(f"bar: precision_when_firing >= {PASS_PREC:.1%} AND recall@5 >= {PASS_REC:.1%} (=0.5 x baseline {base_up_recall5:.1%})")
if best:
    print(f"PASS at thr={best[0]:.2f}: recall@5={best[2]:.1%}, firing={best[3]:.2%}, precision_when_firing={best[4]:.3%}")
    print("=> a marginal LOW-VOLUME assist exists on the user_prompt path; user decides if worth a per-tool-call subprocess.")
else:
    print("FAIL: no cosine threshold clears the bar. The semantic gate does not separate recall from firing")
    print("      on the user_prompt path any better than keyword. => REMOVE the two hook lines (issue #1 close).")

out = {
    "embedder": "minishlab/potion-base-8M (model2vec, 256d)",
    "n_trap": n_trap, "n_events": n_events, "ev_with_up": ev_with_up,
    "T_up_total": T_up_total, "firing_sample": len(up_sample),
    "baseline_up_recall5": round(base_up_recall5, 4),
    "keep_bar": {"precision_when_firing_min": PASS_PREC, "recall5_min": round(PASS_REC, 4)},
    "sweep": [{"thr": t, "rec3": round(r3, 4), "rec5": round(r5, 4), "firing": round(fr, 5),
               "precision_when_firing": round(p, 5), "ceiling": (None if ceil == float('inf') else round(ceil, 5))}
              for (t, r3, r5, fr, p, ceil) in rows],
    "verdict": ("PASS" if best else "FAIL"),
    "best": (None if not best else {"thr": best[0], "rec5": round(best[2], 4), "firing": round(best[3], 5),
                                    "precision_when_firing": round(best[4], 5)}),
}
(HERE / "phase8-embeddings-results.json").write_text(json.dumps(out, indent=2))
print(f"\nwrote phase8-embeddings-results.json")
