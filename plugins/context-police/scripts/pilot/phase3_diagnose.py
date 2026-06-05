#!/usr/bin/env python3
"""
Phase 3 — diagnose WHY genuine poorly-recalled traps miss (decides embeddings v2 vs defer).
For each target trap, find its real invocations and print the trigger that scored it best (the
trap's rank+score) + that trigger's text + the index one_line_fix. Classify the miss:
  - PARAPHRASE  : trigger is descriptive but uses different words than the skill name/desc
                  -> embeddings (semantic) would help.
  - NO-SIGNAL   : the immediately-preceding triggers are terse/unrelated (the trap surfaced from
                  reasoning, not from prompt/command text) -> retrieval (any) structurally can't fire.
  - VOCAB-OK    : actually scores fine (was a classifier/other artifact).
"""
import json, os, pathlib, re
import retrieve as R
from recompute_with_overrides import corrected_index, _text

HERE = pathlib.Path(__file__).resolve().parent
PROJECTS = pathlib.Path(os.path.expanduser("~/.claude/projects"))
IDX_PATH = HERE / "_idx_phase3.jsonl"
rows = corrected_index()
IDX_PATH.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
R._CACHE.clear()
TRAPS = {r["id"] for r in rows if r["kind"] == "trap"}
IDX = {r["id"]: r for r in rows}

# ILLUSTRATIVE — replace with the genuine-trap skill IDs from YOUR corpus that recall@K MISSED
# (the ones you want to diagnose: did they miss from no-signal or from paraphrase?). Empty is fine —
# the script then diagnoses every poorly-recalled trap it finds.
TARGETS = set()  # e.g. {"some-trap-that-missed", "another-missed-trap"}

def best_trigger(sid, triggers):
    """Return (best_rank, best_score, trigger_text) for sid over the triggers; rank None if never top-10."""
    best = (None, 0.0, "")
    for t in triggers[-40:]:
        hits = R.retrieve(t["q"], k=10, kinds=("trap",), tool_cmd=t["cmd"], file_path=t["fp"], path=IDX_PATH)
        for rank, h in enumerate(hits, 1):
            if h["id"] == sid:
                if best[0] is None or rank < best[0]:
                    best = (rank, h["score"], t["q"][:160])
                break
    return best

for f in PROJECTS.rglob("*.jsonl"):
    triggers, seen, last_user = [], set(), ""
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
                    if (not TARGETS or sid in TARGETS) and sid in TRAPS and sid not in seen:
                        seen.add(sid)
                        if re.match(r"^\s*/" + re.escape(sid) + r"\b", last_user or ""): continue
                        rank, score, tq = best_trigger(sid, triggers)
                        print(f"\n### {sid}   [best rank={rank} score={score:.2f}]")
                        print(f"    one_line_fix: {(IDX[sid].get('one_line_fix') or '')[:120]}")
                        print(f"    best trigger: {tq!r}")

try: os.remove(IDX_PATH)
except OSError: pass
