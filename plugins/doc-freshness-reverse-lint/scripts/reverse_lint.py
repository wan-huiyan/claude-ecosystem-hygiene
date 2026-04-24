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
    # Also pick up per-subproject doc dirs (e.g. schuh_causal_impact/docs/research/*)
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


def infer_project_root_from_memory(memory_file: Path) -> Path | None:
    """Map ~/.claude/projects/-Users-huiyanwan-Documents/memory/* → /Users/huiyanwan/Documents."""
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

    result = {
        "memory_file": str(mf),
        "project_root": str(project_root),
        "candidates": candidates,
    }

    if not candidates:
        # Silent on zero hits (user dislikes chatty skills)
        if args.human:
            return 0
        print(json.dumps(result))
        return 0

    if args.human:
        print(f"Candidate stale claims in {project_root}:")
        for c in candidates:
            print(f"\n  Rule {c['rule_id']}: {c['rule_title']}")
            print(f"    Negated phrase: \"{c['negated_phrase']}\"")
            for m in c["matches"]:
                rel = os.path.relpath(m["file"], project_root)
                print(f"    - {rel}:{m['line']}: {m['content']}")
        print("\n(No auto-edits performed. Review and update manually.)")
    else:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
