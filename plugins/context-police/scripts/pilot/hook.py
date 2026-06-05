#!/usr/bin/env python3
"""
The two-trigger retrieval hook — SHADOW MODE by default (logs what it WOULD inject, injects
nothing). Flip to live with env LESSON_HOOK_LIVE=1 once the recall@K pilot clears the bar.

Wire BOTH events to this one script (see README):
  - UserPromptSubmit  -> python3 hook.py user_prompt   (keys on the prompt text)
  - PostToolUse       -> python3 hook.py post_tool      (keys on the tool command / edited file)

Contract: NEVER crash the session — always exit 0. In shadow mode it prints nothing (no
injection); it appends a JSONL line to ~/.claude/lesson-retrieval-shadow.log so you can audit
exactly what it would have surfaced, with zero behavior change.
"""
import json, os, sys, pathlib, datetime

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
LOG = pathlib.Path(os.path.expanduser("~/.claude/lesson-retrieval-shadow.log"))
LIVE = os.environ.get("LESSON_HOOK_LIVE") == "1"
K = int(os.environ.get("LESSON_HOOK_K", "3"))
FLOOR = float(os.environ.get("LESSON_HOOK_FLOOR", "6.0"))   # score floor → inject ZERO below it

def _emit_nothing():
    sys.exit(0)

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "user_prompt"
    try:
        payload = json.load(sys.stdin)
    except Exception:
        _emit_nothing()
    try:
        import retrieve as R
        # Deployment guard: the index is gitignored. If a user wires the hook before `--build`,
        # the bare try/except below would make it silently inert ("wired but doing nothing").
        # Log a distinct marker so `tail ~/.claude/lesson-retrieval-shadow.log` shows inert-vs-working.
        if not R.INDEX_PATH.exists():
            try:
                with LOG.open("a") as f:
                    f.write(json.dumps({"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "mode": mode, "warn": "index-missing",
                        "hint": f"build it: python3 {R.INDEX_PATH.parent / 'retrieve.py'} --build"}) + "\n")
            except Exception:
                pass
            _emit_nothing()
        query, cmd, fp = "", "", ""
        if mode == "user_prompt":
            query = (payload.get("prompt") or "")[:1000]
        else:  # post_tool
            ti = payload.get("tool_input", {}) or {}
            cmd = (ti.get("command") or "")[:500]
            fp = ti.get("file_path") or ""
            # also fold in an error snippet from the tool response, if any
            tr = payload.get("tool_response")
            err = ""
            if isinstance(tr, dict):
                err = (tr.get("stderr") or tr.get("error") or "")[:300]
            query = " ".join(x for x in (cmd, fp, err) if x)
        if not query.strip():
            _emit_nothing()
        hits = [h for h in R.retrieve(query, k=K, kinds=("trap",), tool_cmd=cmd, file_path=fp)
                if h["score"] >= FLOOR]
        # audit log (shadow + live both log)
        rec = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(), "mode": mode,
               "live": LIVE, "session": payload.get("session_id"),
               "query": query[:160], "hits": [{"id": h["id"], "score": h["score"]} for h in hits]}
        try:
            with LOG.open("a") as f:
                f.write(json.dumps(rec) + "\n")
        except Exception:
            pass
        if not hits or not LIVE:
            _emit_nothing()                       # SHADOW: inject nothing
        # LIVE: inject the relevant traps as additionalContext
        lines = ["RELEVANT PAST TRAPS (retrieved from your lessons; may not apply — verify):"]
        for h in hits:
            lines.append(f"- {h['id']}: {h['one_line_fix']}  (invoke /{h['id']} for the full lesson)")
        out = {"hookSpecificOutput": {"hookEventName":
               ("UserPromptSubmit" if mode == "user_prompt" else "PostToolUse"),
               "additionalContext": "\n".join(lines)}}
        print(json.dumps(out))
    except Exception:
        pass
    sys.exit(0)

if __name__ == "__main__":
    main()
