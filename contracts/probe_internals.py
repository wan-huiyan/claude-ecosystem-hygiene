#!/usr/bin/env python3
"""Probe locally-checkable assumptions from contracts/claude-code-internals.md.

Checks a live ~/.claude installation against the internals contract and prints
an OK / DRIFT / UNKNOWN verdict per assumption:

  OK      — the assumption holds on this machine.
  DRIFT   — the artifact exists but does not match the contract (schema drift).
  UNKNOWN — nothing local to check against (path absent, no sessions yet).

Stdlib only, Python 3.8+. Never crashes on missing paths — missing evidence is
UNKNOWN, not an error. Exit code: 1 if any DRIFT, else 0 (UNKNOWN is not a
failure; it just means this machine has no evidence either way).

Usage:
  python3 contracts/probe_internals.py            # human-readable report
  python3 contracts/probe_internals.py --json     # machine-readable
  python3 contracts/probe_internals.py --claude-dir /path/to/.claude
"""
import argparse
import json
import os
import re
import sys

OK, DRIFT, UNKNOWN = "OK", "DRIFT", "UNKNOWN"

USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


def result(assumption, status, detail):
    return {"assumption": assumption, "status": status, "detail": detail}


def find_session_jsonls(projects_dir):
    """Yield session transcript paths (top-level <uuid>.jsonl per project dir)."""
    try:
        project_dirs = sorted(os.listdir(projects_dir))
    except OSError:
        return
    for d in project_dirs:
        pdir = os.path.join(projects_dir, d)
        if not os.path.isdir(pdir):
            continue
        try:
            names = sorted(os.listdir(pdir))
        except OSError:
            continue
        for name in names:
            path = os.path.join(pdir, name)
            if name.endswith(".jsonl") and os.path.isfile(path):
                yield path


def check_projects_layout(claude_dir):
    projects = os.path.join(claude_dir, "projects")
    if not os.path.isdir(projects):
        return result(
            "session transcripts at ~/.claude/projects/<project>/<uuid>.jsonl",
            UNKNOWN,
            "%s does not exist (no sessions on this machine?)" % projects,
        )
    sessions = list(find_session_jsonls(projects))
    if not sessions:
        return result(
            "session transcripts at ~/.claude/projects/<project>/<uuid>.jsonl",
            UNKNOWN,
            "projects/ exists but contains no *.jsonl session files",
        )
    return result(
        "session transcripts at ~/.claude/projects/<project>/<uuid>.jsonl",
        OK,
        "%d session .jsonl file(s) found (e.g. %s)"
        % (len(sessions), os.path.relpath(sessions[-1], claude_dir)),
    )


def check_usage_schema(claude_dir):
    assumption = "transcript lines parse as JSON; assistant entries carry message.usage token fields"
    projects = os.path.join(claude_dir, "projects")
    sessions = list(find_session_jsonls(projects)) if os.path.isdir(projects) else []
    if not sessions:
        return result(assumption, UNKNOWN, "no session .jsonl files to sample")
    # Prefer the most recently modified session for a fresh sample.
    sessions.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0)
    sampled = 0
    for path in reversed(sessions[-5:]):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        return result(
                            assumption, DRIFT,
                            "non-JSON line in %s" % path,
                        )
                    sampled += 1
                    usage = (obj.get("message") or {}).get("usage") \
                        if isinstance(obj.get("message"), dict) else None
                    if isinstance(usage, dict):
                        missing = [k for k in USAGE_FIELDS if k not in usage]
                        if missing:
                            return result(
                                assumption, DRIFT,
                                "message.usage in %s missing fields: %s"
                                % (os.path.basename(path), ", ".join(missing)),
                            )
                        return result(
                            assumption, OK,
                            "message.usage with all %d token fields found in %s"
                            % (len(USAGE_FIELDS), os.path.basename(path)),
                        )
        except OSError:
            continue
    if sampled:
        return result(
            assumption, UNKNOWN,
            "parsed %d line(s) but found no message.usage object in the 5 newest sessions"
            % sampled,
        )
    return result(assumption, UNKNOWN, "could not read any transcript lines")


def check_subagent_layout(claude_dir):
    assumption = "subagent transcripts at <session>/subagents/agent-*.jsonl (+ workflows/wf_*/)"
    projects = os.path.join(claude_dir, "projects")
    if not os.path.isdir(projects):
        return result(assumption, UNKNOWN, "no projects/ dir")
    hits = []
    for root, dirs, files in os.walk(projects):
        if os.path.basename(root) != "subagents" and "subagents" not in root.split(os.sep):
            continue
        hits.extend(
            os.path.join(root, f) for f in files
            if f.startswith("agent-") and f.endswith(".jsonl")
        )
        if len(hits) >= 3:
            break
    if hits:
        return result(
            assumption, OK,
            "%d agent-*.jsonl file(s) under subagents/ (e.g. %s)"
            % (len(hits), os.path.relpath(hits[0], claude_dir)),
        )
    return result(assumption, UNKNOWN, "no subagents/ transcripts found (no subagent runs on this machine?)")


def parse_frontmatter(text):
    """Return dict of top-level frontmatter keys, or None if no frontmatter."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    block = text[3:end] if end != -1 else text[3:]
    out = {}
    for m in re.finditer(r"^([A-Za-z][\w-]*):\s*(.*?)\s*$", block, re.MULTILINE):
        out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


def check_skills_dir(claude_dir):
    assumption = "skills at ~/.claude/skills/<name>/SKILL.md with parseable frontmatter"
    skills = os.path.join(claude_dir, "skills")
    if not os.path.isdir(skills):
        return result(assumption, UNKNOWN, "%s does not exist" % skills)
    checked = bad = 0
    example_bad = None
    try:
        entries = sorted(os.listdir(skills))
    except OSError as e:
        return result(assumption, UNKNOWN, "cannot list %s: %s" % (skills, e))
    for d in entries:
        sm = os.path.join(skills, d, "SKILL.md")
        if not os.path.isfile(sm):
            continue
        checked += 1
        try:
            with open(sm, encoding="utf-8", errors="replace") as f:
                fm = parse_frontmatter(f.read())
        except OSError:
            fm = None
        if not fm or "name" not in fm:
            bad += 1
            example_bad = example_bad or sm
    if checked == 0:
        return result(assumption, UNKNOWN, "skills/ exists but no <name>/SKILL.md found")
    if bad:
        return result(
            assumption, DRIFT,
            "%d/%d SKILL.md missing frontmatter `name:` (e.g. %s)" % (bad, checked, example_bad),
        )
    return result(assumption, OK, "%d SKILL.md file(s) parsed, all with frontmatter name" % checked)


def check_settings(claude_dir):
    assumption = "~/.claude/settings.json parses; note skillOverrides presence"
    path = os.path.join(claude_dir, "settings.json")
    if not os.path.isfile(path):
        return result(assumption, UNKNOWN, "%s does not exist" % path)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return result(assumption, DRIFT, "settings.json does not parse: %s" % e)
    has = "skillOverrides" in data if isinstance(data, dict) else False
    return result(
        assumption, OK,
        "settings.json parses; skillOverrides %s"
        % ("present" if has else "not present (fine — it is optional)"),
    )


def check_auto_memory(claude_dir):
    assumption = "auto-memory at ~/.claude/projects/<project>/memory/MEMORY.md"
    projects = os.path.join(claude_dir, "projects")
    if not os.path.isdir(projects):
        return result(assumption, UNKNOWN, "no projects/ dir")
    found = []
    try:
        for d in sorted(os.listdir(projects)):
            mm = os.path.join(projects, d, "memory", "MEMORY.md")
            if os.path.isfile(mm):
                found.append(mm)
    except OSError:
        pass
    if found:
        return result(
            assumption, OK,
            "%d MEMORY.md file(s) at the contract path (e.g. %s)"
            % (len(found), os.path.relpath(found[0], claude_dir)),
        )
    return result(assumption, UNKNOWN, "no memory/MEMORY.md found under any project (auto-memory may be unused)")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Probe local Claude Code internals against contracts/claude-code-internals.md"
    )
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument(
        "--claude-dir",
        default=os.path.expanduser("~/.claude"),
        help="Claude config dir to probe (default: ~/.claude)",
    )
    args = ap.parse_args(argv)

    claude_dir = args.claude_dir
    results = [
        check_projects_layout(claude_dir),
        check_usage_schema(claude_dir),
        check_subagent_layout(claude_dir),
        check_skills_dir(claude_dir),
        check_settings(claude_dir),
        check_auto_memory(claude_dir),
    ]
    counts = {s: sum(1 for r in results if r["status"] == s) for s in (OK, DRIFT, UNKNOWN)}

    if args.json:
        print(json.dumps(
            {"claude_dir": claude_dir, "summary": counts, "results": results},
            indent=2,
        ))
    else:
        print("Claude Code internals probe — %s" % claude_dir)
        print("(contract: contracts/claude-code-internals.md)\n")
        for r in results:
            print("  [%-7s] %s" % (r["status"], r["assumption"]))
            print("            %s" % r["detail"])
        print("\n%d OK, %d DRIFT, %d UNKNOWN" % (counts[OK], counts[DRIFT], counts[UNKNOWN]))
        if counts[DRIFT]:
            print("DRIFT found — update contracts/claude-code-internals.md and propagate to consumers.")
    return 1 if counts[DRIFT] else 0


if __name__ == "__main__":
    sys.exit(main())
