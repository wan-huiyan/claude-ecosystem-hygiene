#!/usr/bin/env python3
"""Reverse-lint: given a memory file (lessons.md / axioms.md / feedback_*.md),
extract negation rules and grep project docs for literal phrase matches.

Conservative by design: silent on zero hits, skips seen rules, requires
explicit negation + multi-token phrase.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
SEEN_CACHE = HOME / ".claude" / "state" / "reverse-lint-seen.json"

NEGATION_TRIGGER = re.compile(
    r"\b(?:don'?t|do not|never|avoid(?:ing)?|stop|no longer)\b[:\s]+",
    re.IGNORECASE,
)

# Stopwords we trim from the end of an extracted phrase.
TAIL_STOPWORDS = {
    "the", "a", "an", "to", "for", "of", "on", "in", "at", "by", "with",
    "and", "or", "but", "is", "are", "was", "were", "be", "been",
    "this", "that", "these", "those", "it", "its", "anymore", "yet",
    "when", "if", "unless",
}

# Regex to pick up to 5 content words after a negation trigger.
PHRASE_AFTER_TRIGGER = re.compile(
    r"([a-z][a-z\-]*(?:\s+[a-z][a-z\-]*){1,5})",
    re.IGNORECASE,
)

HEADING_RE = re.compile(r"^###\s+(\d+)\.\s+(.*?)\s*$")
# feedback files are single-rule, no ### headings
FRONTMATTER_RE = re.compile(r"^---\s*$")

# --- dead-branch detection (v1.3.0) -----------------------------------------
#
# A SECOND failure mode, and the reverse-lint's original grep cannot see it.
# When a rule is RETIRED rather than contradicted, the docs that carried it
# often keep a SCOPED SURVIVOR: "X is retired — but it still applies if you are
# a Y". That reads as current guidance, and it is dead the moment no Y exists.
#
# Seen 2026-08-04: "no deploys by agents" was retired across four live briefs,
# and each retirement kept "a cloud session still cannot" as a live branch —
# after cloud sessions had stopped existing. The next reader would have stopped
# to work out which kind of session it was instead of just deploying. The
# retirement was correct; the surviving condition was the defect.
#
# THREE explicit signals, ANDed, because a scoped survivor is often perfectly
# legitimate and only a human knows whether the branch can still fire:
#   1. a retirement trigger in the memory file,
#   2. a QUOTED subject next to it (retirement prose nearly always quotes the
#      rule it is retiring), >= 2 tokens,
#   3. a doc line containing that subject AND a surviving-conditional marker.
RETIREMENT_TRIGGER = re.compile(
    r"\b(?:retired|retires|retiring|superseded|supersedes|"
    r"no longer (?:applies|true|holds|stands|the case)|"
    r"is dead|are dead|does not apply(?: anymore)?)\b",
    re.IGNORECASE,
)

# The quoted rule being retired: "...", '...', `...`, **...** or *...*.
QUOTED_SUBJECT = re.compile(
    r"[\"“]([^\"”\n]{4,90})[\"”]"
    r"|'([^'\n]{4,90})'"
    r"|`([^`\n]{4,90})`"
    r"|\*\*([^*\n]{4,90})\*\*"
)

# "...but it STILL applies IF you are a cloud session."
SURVIVING_CONDITIONAL = re.compile(
    r"\b(?:still (?:cannot|can'?t|cannot|applies|apply|applies to|holds|true|stands|"
    r"the case|is|are|do|does|must|should)"
    r"|only (?:applies|apply|if|when|for|on)"
    r"|unless you(?:'re| are)?"
    r"|except (?:for|when|on|if)"
    r"|if you(?:'re| are) (?:a|an|in|on|running)"
    r"|remains? true (?:for|on|of)"
    r"|continues? to (?:apply|hold)"
    r"|does not apply to)\b",
    re.IGNORECASE,
)

# How far after a retirement trigger to look for the quoted subject.
QUOTE_WINDOW = 160

# Project-doc roots inside any project
DOC_SUBDIRS = ("docs/research", "docs/decisions", "docs/findings", "docs/runbooks")


@dataclass
class Rule:
    rule_id: str
    rule_title: str
    negated_phrase: str
    source_file: str


@dataclass
class Match:
    file: str
    line: int
    content: str


def load_seen() -> set[str]:
    if not SEEN_CACHE.exists():
        return set()
    try:
        return set(json.loads(SEEN_CACHE.read_text()))
    except Exception:
        return set()


def save_seen(seen: set[str]) -> None:
    SEEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_CACHE.write_text(json.dumps(sorted(seen)))


def hash_key(source: str, rule_id: str, phrase: str, project_root: str) -> str:
    h = hashlib.sha256()
    h.update(f"{source}|{rule_id}|{phrase}|{project_root}".encode())
    return h.hexdigest()[:16]


def clean_phrase(phrase: str) -> str:
    tokens = phrase.lower().split()
    while tokens and tokens[-1] in TAIL_STOPWORDS:
        tokens.pop()
    while tokens and tokens[0] in TAIL_STOPWORDS:
        tokens.pop(0)
    return " ".join(tokens)


def extract_negations_from_block(block_text: str) -> list[str]:
    """Return a list of cleaned multi-token phrases extracted from negation triggers."""
    phrases: list[str] = []
    for m in NEGATION_TRIGGER.finditer(block_text):
        tail = block_text[m.end(): m.end() + 120]
        # Stop at sentence boundary
        # Stop at a true sentence boundary; don't break on `-` (hyphenated terms like p-value).
        tail = re.split(r"[.\n!?;:\(]|\s-\s|\s—\s", tail, maxsplit=1)[0]
        pm = PHRASE_AFTER_TRIGGER.search(tail)
        if not pm:
            continue
        phrase = clean_phrase(pm.group(1))
        tokens = phrase.split()
        if len(tokens) < 2:
            continue
        # Cap at 4 tokens (tighter match is less false-positive-prone)
        phrase = " ".join(tokens[:4])
        phrases.append(phrase)
    # De-dup preserving order
    seen = set()
    uniq = []
    for p in phrases:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def best_phrase_for_rule(title: str, body: str) -> str | None:
    """Conservative per-rule phrase selection:
    Prefer a negation phrase extracted from the TITLE; fall back to the first
    body negation. Only ONE phrase per rule — multiple body rephrasings
    (e.g. "avoid the X sort" alongside "don't sort by X") inflate false
    positives on qualified docs, so we take just the most specific form.
    """
    title_phrases = extract_negations_from_block(title)
    if title_phrases:
        return title_phrases[0]
    body_phrases = extract_negations_from_block(body)
    return body_phrases[0] if body_phrases else None


def parse_lessons_style(path: Path) -> list[Rule]:
    """Parse a lessons.md / axioms.md file with `### NN. Title` sections."""
    text = path.read_text(errors="replace")
    rules: list[Rule] = []
    blocks = re.split(r"(?m)^### (\d+)\.\s+", text)
    for i in range(1, len(blocks) - 1, 2):
        num = blocks[i]
        body = blocks[i + 1]
        lines = body.splitlines()
        title = lines[0].strip() if lines else ""
        phrase = best_phrase_for_rule(title, body)
        if not phrase:
            continue
        rules.append(Rule(
            rule_id=f"#{num}",
            rule_title=title[:120],
            negated_phrase=phrase,
            source_file=str(path),
        ))
    return rules


def parse_feedback_style(path: Path) -> list[Rule]:
    """Parse a ~/.claude/projects/*/memory/feedback_*.md file."""
    text = path.read_text(errors="replace")
    # Strip YAML frontmatter
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            body = text[end + 4:]
        else:
            body = text
    else:
        body = text
    # Try to extract a name from frontmatter for the rule_id
    name_match = re.search(r"^name:\s*(.+?)\s*$", text, re.MULTILINE)
    rid = name_match.group(1) if name_match else path.stem
    desc_match = re.search(r"^description:\s*(.+?)\s*$", text, re.MULTILINE)
    title = (desc_match.group(1) if desc_match else rid)[:120]
    phrase = best_phrase_for_rule(title, body)
    if not phrase:
        return []
    return [Rule(
        rule_id=rid,
        rule_title=title,
        negated_phrase=phrase,
        source_file=str(path),
    )]


def detect_style(path: Path) -> str:
    name = path.name
    if name == "lessons.md" or name == "axioms.md":
        return "lessons"
    if name.startswith("feedback_") and name.endswith(".md"):
        return "feedback"
    # Fallback: inspect content
    head = path.read_text(errors="replace")[:2000]
    if re.search(r"(?m)^### \d+\.", head):
        return "lessons"
    return "feedback"


def find_doc_files(project_root: Path) -> list[Path]:
    files: list[Path] = []
    for sub in DOC_SUBDIRS:
        root = project_root / sub
        if root.exists():
            files.extend(root.rglob("*.md"))
    # Also pick up per-subproject doc dirs (e.g. the-causal-impact-repo/docs/research/*)
    for candidate in project_root.glob("*/"):
        for sub in DOC_SUBDIRS:
            root = candidate / sub
            if root.exists():
                files.extend(root.rglob("*.md"))
    # MEMORY.md files at project and subproject roots
    for mem in [project_root / "MEMORY.md", *project_root.glob("*/MEMORY.md")]:
        if mem.exists():
            files.append(mem)
    # De-dup
    return sorted(set(files))


def grep_phrase(files: list[Path], phrase: str) -> list[Match]:
    """Case-insensitive literal substring match. Return all hits."""
    needle = phrase.lower()
    hits: list[Match] = []
    for f in files:
        try:
            for i, line in enumerate(f.read_text(errors="replace").splitlines(), start=1):
                if needle in line.lower():
                    hits.append(Match(
                        file=str(f),
                        line=i,
                        content=line.strip()[:200],
                    ))
        except Exception:
            continue
    return hits


def extract_retired_subjects(text: str) -> list[str]:
    """Quoted rules being retired in `text`, cleaned and de-duplicated.

    Looks BOTH ways around the retirement trigger: prose puts the quote before
    it ("X" is retired) about as often as after (retired: "X").
    """
    subjects: list[str] = []
    for m in RETIREMENT_TRIGGER.finditer(text):
        window = text[max(0, m.start() - QUOTE_WINDOW): m.end() + QUOTE_WINDOW]
        for q in QUOTED_SUBJECT.finditer(window):
            phrase = next(g for g in q.groups() if g is not None)
            phrase = re.sub(r"\s+", " ", phrase).strip().strip(".,;:—-").lower()
            # A quoted PATH or a single word is not a rule.
            if len(phrase.split()) < 2 or "/" in phrase or phrase.endswith(".md"):
                continue
            if phrase not in subjects:
                subjects.append(phrase)
    return subjects


def _paragraphs(lines: list[str]) -> list[tuple[int, str]]:
    """(1-based start line, joined text) for each blank-line-delimited block."""
    out, buf, start = [], [], 1
    for i, line in enumerate(lines, start=1):
        if line.strip():
            if not buf:
                start = i
            buf.append(line)
        elif buf:
            out.append((start, " ".join(buf)))
            buf = []
    if buf:
        out.append((start, " ".join(buf)))
    return out


def find_dead_branches(files: list[Path], subjects: list[str],
                       exclude_name: str | None = None) -> list[dict]:
    """Lines that mention a retired rule AND still scope it to a live-looking case.

    Scope is the PARAGRAPH, not the line: markdown prose wraps, so the retirement
    and its surviving condition are routinely on different lines of one block
    ("...is RETIRED. It described what a cloud session can do... A cloud session
    still cannot: no credentials"). Requiring both in one paragraph is the
    tightest unit that still catches the real shape.

    KNOWN LIMIT, stated rather than tuned away: two unrelated sentences sharing a
    paragraph — one mentioning the retired rule, one carrying an unrelated
    conditional — will co-occur and be surfaced. That is why this returns
    CANDIDATES with the question attached and never edits. The script cannot know
    whether a branch can still fire; that is the judgment being asked for.
    """
    out: list[dict] = []
    for subject in subjects:
        needle = subject.lower()
        matches: list[Match] = []
        for f in files:
            if exclude_name and f.name == exclude_name:
                continue
            try:
                lines = f.read_text(errors="replace").splitlines()
            except Exception:
                continue
            for start, para in _paragraphs(lines):
                low = para.lower()
                pos = low.find(needle)
                if pos < 0:
                    continue
                # The condition must come AFTER the retirement it scopes.
                if not SURVIVING_CONDITIONAL.search(para, pos):
                    continue
                # Report the line the subject is actually on.
                hit = start
                for off, line in enumerate(lines[start - 1:], start=start):
                    if needle in line.lower():
                        hit = off
                        break
                matches.append(Match(file=str(f), line=hit,
                                     content=lines[hit - 1].strip()[:200]))
        if matches:
            out.append({
                "retired_subject": subject,
                "question": (f"'{subject}' is retired — does the condition this "
                             "paragraph scopes it to still occur? If not, the "
                             "branch is dead and reads as current guidance."),
                "matches": [asdict(m) for m in matches],
            })
    return out


def infer_project_root_from_memory(memory_file: Path) -> Path | None:
    """Map ~/.claude/projects/-Users-<user>-Documents/memory/* → /Users/<user>/Documents."""
    s = str(memory_file)
    m = re.search(r"/\.claude/projects/(-[^/]+)/memory/", s)
    if m:
        slug = m.group(1)
        path = "/" + slug.lstrip("-").replace("-", "/")
        p = Path(path)
        if p.exists():
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("memory_file", type=Path)
    ap.add_argument("--project-root", type=Path, default=None)
    ap.add_argument("--rescan", action="store_true",
                    help="Ignore seen-cache and re-surface all hits.")
    ap.add_argument("--human", action="store_true",
                    help="Human-readable output instead of JSON.")
    args = ap.parse_args()

    mf: Path = args.memory_file
    if not mf.exists():
        print(f"memory file not found: {mf}", file=sys.stderr)
        return 2

    # Infer project root
    project_root = args.project_root
    if project_root is None:
        project_root = infer_project_root_from_memory(mf)
    if project_root is None:
        # Global lessons/axioms with no explicit project: scan the Documents tree
        project_root = HOME / "Documents"
    if not project_root.exists():
        print(f"project root not found: {project_root}", file=sys.stderr)
        return 2

    # Parse rules
    style = detect_style(mf)
    rules = parse_lessons_style(mf) if style == "lessons" else parse_feedback_style(mf)

    if not rules:
        if args.human:
            print("no negation rules extracted")
        else:
            print(json.dumps({
                "memory_file": str(mf),
                "project_root": str(project_root),
                "candidates": [],
            }))
        return 0

    # Gather doc files once
    files = find_doc_files(project_root)

    seen = set() if args.rescan else load_seen()
    new_seen = set(seen)
    candidates = []

    for rule in rules:
        key = hash_key(str(mf), rule.rule_id, rule.negated_phrase, str(project_root))
        if key in seen:
            continue
        new_seen.add(key)
        matches = grep_phrase(files, rule.negated_phrase)
        if not matches:
            continue
        # Don't flag the memory file itself as a match
        matches = [m for m in matches if not m.file.endswith(mf.name)]
        if not matches:
            continue
        candidates.append({
            "rule_id": rule.rule_id,
            "rule_title": rule.rule_title,
            "negated_phrase": rule.negated_phrase,
            "matches": [asdict(m) for m in matches],
        })

    # Only persist cache if there were rules to consider (avoid masking issues)
    save_seen(new_seen)

    # v1.3.0 — the retirement case, which the negation grep above cannot see.
    # Deliberately NOT seen-cached: a dead branch is a property of the DOCS,
    # which change under a rule that was retired once, so re-surfacing it after
    # a doc edit is correct rather than chatty.
    dead_branches = find_dead_branches(
        files, extract_retired_subjects(mf.read_text(errors="replace")),
        exclude_name=mf.name)

    result = {
        "memory_file": str(mf),
        "project_root": str(project_root),
        "candidates": candidates,
        "dead_branch_candidates": dead_branches,
    }

    if not candidates and not dead_branches:
        # Silent on zero hits (user dislikes chatty skills)
        if args.human:
            return 0
        print(json.dumps(result))
        return 0

    if args.human:
        if candidates:
            print(f"Candidate stale claims in {project_root}:")
            for c in candidates:
                print(f"\n  Rule {c['rule_id']}: {c['rule_title']}")
                print(f"    Negated phrase: \"{c['negated_phrase']}\"")
                for m in c["matches"]:
                    rel = os.path.relpath(m["file"], project_root)
                    print(f"    - {rel}:{m['line']}: {m['content']}")
        if dead_branches:
            print(f"\nRetired rules still carrying a live-looking condition "
                  f"in {project_root}:")
            for c in dead_branches:
                print(f"\n  Retired: \"{c['retired_subject']}\"")
                print(f"    Ask: does that condition still occur? If not, the "
                      f"branch is dead and reads as current guidance.")
                for m in c["matches"]:
                    rel = os.path.relpath(m["file"], project_root)
                    print(f"    - {rel}:{m['line']}: {m['content']}")
        print("\n(No auto-edits performed. Review and update manually.)")
    else:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
