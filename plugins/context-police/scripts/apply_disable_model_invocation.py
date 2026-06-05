#!/usr/bin/env python3
"""
Apply (or revert) `disable-model-invocation: true` on a confirmed-trap hide-list.

Stamps the flag into each skill's SKILL.md YAML frontmatter (idempotent: skips if
already present). Removes the skill from the model-invocable catalog GLOBALLY while
keeping `/name` invocation + ripgrep discoverability. Fully reversible with --revert.

USAGE (only after USER approval — this is the catalog-cost flip, ADR 0004 / issue #2):
  python3 apply_disable_model_invocation.py --list confirmed-hide-list.json --dry-run
  python3 apply_disable_model_invocation.py --list confirmed-hide-list.json --apply
  python3 apply_disable_model_invocation.py --list confirmed-hide-list.json --revert

The hide-list JSON is {"hide": ["skill-id", ...]} — the 2-of-3-majority confirmed traps.
"""
import argparse, json, os, pathlib, re, sys

SK = pathlib.Path(os.path.expanduser("~/.claude/skills"))
FLAG = "disable-model-invocation: true"


def stamp(md, on):
    """Insert/remove the flag inside the leading YAML frontmatter.
    Returns (new_text, changed). Raises ValueError if the frontmatter is UNPARSEABLE
    (no closing `---`) — a silent no-op there hides a skill that never got flagged AND a
    SKILL.md whose frontmatter Claude Code itself can't parse (caught cctime-fork S13)."""
    m = re.match(r'^(---\s*\n)(.*?)(\n---\s*\n)', md, re.S)
    if not m:
        if md.lstrip().startswith('---'):
            raise ValueError("frontmatter has no closing '---' — fix the SKILL.md first (CC can't parse it either)")
        return md, False
    head, body, tail = m.group(1), m.group(2), m.group(3)
    has = re.search(r'^\s*disable-model-invocation:\s*true\s*$', body, re.M) is not None
    if on and not has:
        body = body.rstrip("\n") + "\n" + FLAG
        return head + body + tail + md[m.end():], True
    if (not on) and has:
        body = re.sub(r'\n?^\s*disable-model-invocation:\s*true\s*$', '', body, flags=re.M)
        return head + body + tail + md[m.end():], True
    return md, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--apply", action="store_true")
    g.add_argument("--revert", action="store_true")
    g.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    ids = json.load(open(a.list))["hide"]
    on = not a.revert
    changed, already, missing = [], [], []
    for sid in ids:
        p = SK / sid / "SKILL.md"
        if not p.exists():
            missing.append(sid); continue
        md = p.read_text()
        new, ch = stamp(md, on)
        if ch:
            changed.append(sid)
            if a.apply or a.revert:
                p.write_text(new)
        else:
            already.append(sid)
    verb = "revert" if a.revert else ("apply" if a.apply else "dry-run")
    print(f"[{verb}] hide-list={len(ids)}  changed={len(changed)}  no-op(already in target state)={len(already)}  missing={len(missing)}")
    if missing:
        print("  MISSING:", missing)
    if a.dry_run:
        print("  (dry-run: nothing written; re-run with --apply)")
    else:
        print(f"  WROTE {len(changed)} SKILL.md files. Restart Claude Code, then verify with /doctor (catalog token estimate should drop).")


if __name__ == "__main__":
    main()
