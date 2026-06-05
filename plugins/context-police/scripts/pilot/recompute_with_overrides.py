#!/usr/bin/env python3
"""
Phase 0 recompute — recall@K over GENUINE traps only (procedures-mislabeled-as-traps removed).

retrieve.classify_kind is hyphen-count + a marker list; the audit (audit_classifier.py) shows the
HIGH-FREQUENCY fired "traps" are overwhelmingly reusable PROCEDURES (recurring playbooks / deploy /
mockup / evaluate / coordinate tasks you seek out by NAME). Those should STAY force-loaded — hiding
them behind a retrieval hook is pure recall loss. This script:
  1. reclassifies the hand-labeled procedures (below) procedure->excluded from the trap pool,
  2. rebuilds a corrected index to a temp path,
  3. re-runs the SAME replay logic (iter_events + best_rank) over GENUINE-trap events only,
  4. reports corrected event- and trap-weighted recall@K vs the polluted baseline.

The labels are hand-judged from each skill's description intent (procedure = deliberate recurring
multi-step task with a generalizing trigger; trap = reactive single-incident gotcha). Borderline
cases are LEFT as trap (conservative: keeps them in the recall denominator + flip set).
"""
import json, os, pathlib, re
from collections import defaultdict
import retrieve as R

HERE = pathlib.Path(__file__).resolve().parent
PROJECTS = pathlib.Path(os.path.expanduser("~/.claude/projects"))
K_LEVELS = (1, 3, 5, 10)

# Skills currently kind=="trap" that are actually reusable PROCEDURES (seek-by-name, recurring).
# Justification = the audit_classifier.py one_line_fix verb (Deploy/Design/Run/Evaluate/Coordinate/
# Set up/Wire/Add/Build/Create/Read-via/Encode/"method"/"playbook"/"framework").
#
# ILLUSTRATIVE ONLY — REPLACE this set with the name-invoked procedures from YOUR OWN catalog that
# the hyphen-count classifier mislabeled as "trap" (typically recurring PR/conflict playbooks,
# overnight-workflow harnesses, deploy how-tos, and triage procedures). See scripts/pilot/README.md
# for how to derive this set for your corpus (it is the "rescued procedures" spot-check described there).
PROCEDURE_OVERRIDES = {
    "doc-freshness-reverse-lint",            # recurring lint (also wired as a PostToolUse hook)
    "overnight-multi-issue-implementation",  # "Run an overnight autonomous workflow"
    "gh-issue-claim-coordination",           # "Coordinate issue pickup across sessions"
    "pr-plan-bucket-triage-before-sizing",   # "Run a Phase 0 bucket triage"
    "css-animated-svg-scenes",               # "Build multi-scene CSS-animated SVGs"
    # "<your-recurring-playbook-here>",      # e.g. a PR-conflict-resolution playbook sought by name
}

def corrected_index():
    rows = R.load_index()
    for r in rows:
        if r["id"] in PROCEDURE_OVERRIDES:
            r["kind"] = "procedure"
    return rows

def _text(content):
    if isinstance(content, str): return content
    if isinstance(content, list):
        return " ".join(b.get("text","") for b in content if isinstance(b, dict) and b.get("type")=="text")
    return ""

def iter_events(traps):
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
                    last_user = txt
                    triggers.append({"q": txt[:600], "cmd": "", "fp": ""})
            elif typ == "assistant" and isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict) or b.get("type") != "tool_use": continue
                    name, inp = b.get("name"), b.get("input", {}) or {}
                    if name == "Bash" and inp.get("command"):
                        triggers.append({"q": inp["command"][:400], "cmd": inp["command"][:400], "fp": ""})
                    elif name in ("Edit", "Write") and inp.get("file_path"):   # SHIPPED matcher: Bash|Edit|Write (no Read)
                        triggers.append({"q": inp["file_path"], "cmd": "", "fp": inp["file_path"]})
                    elif name == "Skill":
                        sid = (inp.get("skill") or "").strip()
                        if sid in traps and sid not in seen:
                            seen.add(sid)
                            if re.match(r"^\s*/" + re.escape(sid) + r"\b", last_user or ""): continue
                            yield sid, list(triggers)

def best_rank(skill_id, triggers, idx_path, kmax=10):
    best = None
    for t in triggers[-40:]:
        hits = R.retrieve(t["q"], k=kmax, kinds=("trap",), tool_cmd=t["cmd"], file_path=t["fp"], path=idx_path)
        for rank, h in enumerate(hits, 1):
            if h["id"] == skill_id:
                if best is None or rank < best: best = rank
                break
        if best == 1: break
    return best

def run(rows, label, idx_path):
    pathlib.Path(idx_path).write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    R._CACHE.clear()
    traps = {r["id"] for r in rows if r["kind"] == "trap"}
    events = list(iter_events(traps))
    by_trap = defaultdict(list)
    per_event = []
    for sid, trg in events:
        r = best_rank(sid, trg, idx_path)
        per_event.append(r); by_trap[sid].append(r)
    def rate(ranks, K): return sum(1 for r in ranks if r is not None and r <= K)/len(ranks) if ranks else 0.0
    print(f"\n=== {label} ===")
    print(f"trap pool: {len(traps)}   events: {len(per_event)}   distinct fired traps: {len(by_trap)}")
    print("  EVENT-weighted: " + "  ".join(f"@{K}={rate(per_event,K):.1%}" for K in K_LEVELS))
    print("  TRAP-weighted:  " + "  ".join(
        f"@{K}={sum(rate(rs,K) for rs in by_trap.values())/len(by_trap):.1%}" for K in K_LEVELS))
    return by_trap

if __name__ == "__main__":
    base = R.load_index()
    tmp_base = HERE / "_idx_base.jsonl"
    tmp_corr = HERE / "_idx_corrected.jsonl"
    run(base, "BASELINE (polluted: procedures counted as traps)", tmp_base)
    by_trap = run(corrected_index(), "CORRECTED (procedures removed from trap pool)", tmp_corr)
    print("\nGenuine fired traps still recalling poorly (recall@5 < 50%), by event count:")
    def rate(rs, K): return sum(1 for r in rs if r is not None and r <= K)/len(rs)
    poor = [(sid, rs) for sid, rs in by_trap.items() if rate(rs, 5) < 0.5]
    for sid, rs in sorted(poor, key=lambda kv: -len(kv[1])):
        print(f"  {len(rs):>2}x  @5={rate(rs,5):.0%}  {sid}")
    for p in (tmp_base, tmp_corr):
        try: os.remove(p)
        except OSError: pass
