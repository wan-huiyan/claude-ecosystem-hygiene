#!/usr/bin/env python3
"""Score a SKILL.md description rewrite against this plugin's trigger eval suite.

WHY THIS IS COMMITTED
    A PR that trims trigger text and then quotes four-decimal coverage numbers is asking
    the reviewer to take those numbers on faith unless the harness ships with it. An
    unreproducible table is worse than no table. This is that harness: run it and you get
    the exact figures quoted in CHANGELOG.md, the README version-history entry, and PR #14.

    An earlier round of this work quoted numbers produced by an ad-hoc script that was
    never committed, with an undisclosed stopword list. A reviewer reproduced the
    DIRECTION but not the VALUES, and showed that dropping the stopword filter flipped
    "0 positives worse" to "2 positives worse". Both the method and the stopword list are
    therefore in this file, in the repo, where they can be argued with.

WHAT IT MEASURES
    For each prompt in the eval suite, the fraction of the prompt's content words that
    appear in the description the model can actually see.

    The baseline is the crux: BEFORE is `old_description[:1535]`, NOT the full old text.
    The harness truncates at the cap, so scoring against the full oversized source would
    compare the new description against text the model never read, and would make every
    honest trim look like a regression.

WHAT IT CANNOT MEASURE  (read this before trusting a green result)
    1. This is word overlap. It is structurally BLIND to trigger-condition restructuring:
       rewriting `trigger on X -- separately, watch for Y` into `trigger on X WHOSE Y`
       keeps the identical word set and scores identically, while the trigger now fires
       only for users who have already diagnosed Y. Use
       `check_skill_descriptions.py --compare OLD NEW` for that class and read the
       DROPPED / NARROWED / REWORDED rows yourself. Do not clear them with this number.

    2. It scores ONE description against prompts in isolation, with no competing skill
       present. So deleting a sibling skill's name from the description can only ever
       register as a precision WIN on a negative prompt that mentions that sibling --
       even though, in a real install where the sibling is also present, that name was
       the disambiguator. Treat negative-side gains that come from removing a competitor
       name as an artifact of the setup, not as evidence.

    3. Word overlap is not the harness's real retrieval mechanism. This measures whether
       trigger vocabulary survived a rewrite. It does not predict firing.

USAGE
    python3 plugins/ecosystem-audit/scripts/score_trigger_coverage.py \
        --old  main:plugins/ecosystem-audit/SKILL.md \
        --new  plugins/ecosystem-audit/SKILL.md \
        --eval plugins/ecosystem-audit/evals/trigger_eval.json

    Add --json for machine-readable output. Exit 0 always; this is a measurement, not a
    gate -- the gate is .github/scripts/check_skill_descriptions.py.

EVAL SUITE SHAPE
    Accepts either a bare JSON list or {"triggers": [...]}, and either a "prompt" or a
    "query" key per entry, so it works against this repo's evals/trigger_eval.json and
    against the sibling repos' eval-suite.json without conversion.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

# skillListingMaxDescChars, default 1536 (v2.1.221 binary). The harness keeps
# `full[:cap-1]` and appends an ellipsis when the description EXCEEDS the cap.
CAP = 1536

# Deliberately small and explicit: a large stopword list is a free parameter that can be
# tuned until the numbers look good. Function words only, and kept here in the repo so a
# reviewer can see exactly what was excluded and re-run without it.
STOP = set("""
a an the this that these those i my me you your can could do does did is are was were be
been am on in of to for with and or but if it its as at by from want need get got have has
make please before after so we our us they them then than about just really sure into out
up down over all any some no not
""".split())


def words(s: str, use_stop: bool = True) -> set:
    w = {t for t in re.findall(r"[a-z][a-z-]{2,}", s.lower())}
    return w - STOP if use_stop else w


def read_description(spec: str) -> str:
    """Read a SKILL.md description from a path or a `git-ref:path` spec."""
    if ":" in spec:
        ref, _, path = spec.partition(":")
        r = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True)
        text = r.stdout if r.returncode == 0 else ""
        if not text:
            sys.exit(f"could not `git show {spec}`")
    else:
        text = open(spec, encoding="utf-8").read()
    if not text.startswith("---"):
        sys.exit(f"no frontmatter in {spec}")
    end = re.search(r"^---\s*$", text[4:], re.M)
    if not end:
        sys.exit(f"unterminated frontmatter in {spec}")
    fm = text[4:4 + end.start()]
    m = re.search(r"^description:\s*[|>]\s*\n((?:[ \t]+.*\n?)*)", fm, re.M)
    if not m:
        sys.exit(f"no folded/block description in {spec}")
    body = " ".join(l.strip() for l in m.group(1).splitlines() if l.strip())
    return re.sub(r"\s+", " ", body).strip()


def load_suite(path: str) -> list:
    """Normalise the eval file to [{"prompt": str, "should_trigger": bool}, ...]."""
    raw = json.load(open(path, encoding="utf-8"))
    items = raw.get("triggers", raw) if isinstance(raw, dict) else raw
    out = []
    for t in items:
        prompt = t.get("prompt") or t.get("query")
        if prompt is None:
            sys.exit(f"eval entry has neither 'prompt' nor 'query': {t}")
        out.append({"prompt": prompt, "should_trigger": bool(t.get("should_trigger"))})
    return out


def score(old_full: str, new: str, suite: list, use_stop: bool) -> dict:
    old = old_full if len(old_full) <= CAP else old_full[:CAP - 1]
    pos = [t for t in suite if t["should_trigger"]]
    neg = [t for t in suite if not t["should_trigger"]]
    ow, nw = words(old, use_stop), words(new, use_stop)

    def cov(prompt: str, vocab: set) -> float:
        pw = words(prompt, use_stop)
        return len(pw & vocab) / len(pw) if pw else 0.0

    rows = [(t["prompt"], cov(t["prompt"], ow), cov(t["prompt"], nw)) for t in pos]
    nrows = [(t["prompt"], cov(t["prompt"], ow), cov(t["prompt"], nw)) for t in neg]
    better = sum(1 for _, o, n in rows if n > o + 1e-3)
    worse = sum(1 for _, o, n in rows if n < o - 1e-3)
    same = len(rows) - better - worse

    pm_o = sum(o for _, o, _ in rows) / len(rows) if rows else 0.0
    pm_n = sum(n for _, _, n in rows) / len(rows) if rows else 0.0
    nm_o = sum(o for _, o, _ in nrows) / len(nrows) if nrows else 0.0
    nm_n = sum(n for _, _, n in nrows) / len(nrows) if nrows else 0.0

    return {
        "stopwords_filtered": use_stop,
        "old_chars_authored": len(old_full),
        "old_chars_visible": len(old),
        "new_chars": len(new),
        "positives": len(pos), "negatives": len(neg),
        "better": better, "same": same, "worse": worse,
        "positive_mean": {"before": round(pm_o, 4), "after": round(pm_n, 4)},
        "negative_mean": {"before": round(nm_o, 4), "after": round(nm_n, 4)},
        "separation": {"before": round(pm_o - nm_o, 4), "after": round(pm_n - nm_n, 4)},
        "positive_regressions": [{"prompt": p, "before": round(o, 3), "after": round(n, 3)}
                                 for p, o, n in rows if n < o - 1e-3],
        "negative_movements": sorted(
            [{"prompt": p, "before": round(o, 3), "after": round(n, 3)}
             for p, o, n in nrows if abs(n - o) > 1e-3],
            key=lambda r: r["after"] - r["before"]),
    }


def render(r: dict) -> None:
    tag = "stopword-filtered" if r["stopwords_filtered"] else "NO stopword filter"
    print(f"  [{tag}]")
    print(f"  authored {r['old_chars_authored']:,} chars, but only "
          f"{r['old_chars_visible']:,} were VISIBLE (cap {CAP})  ->  now {r['new_chars']:,}")
    print(f"  positives ({r['positives']}):  {r['better']} better · {r['same']} same · "
          f"{r['worse']} worse")
    print(f"  positive mean coverage   {r['positive_mean']['before']:.4f} -> "
          f"{r['positive_mean']['after']:.4f}")
    print(f"  negative mean coverage   {r['negative_mean']['before']:.4f} -> "
          f"{r['negative_mean']['after']:.4f}   (lower is better)")
    print(f"  separation               {r['separation']['before']:+.4f} -> "
          f"{r['separation']['after']:+.4f}")
    if r["positive_regressions"]:
        print("  positive regressions:")
        for x in r["positive_regressions"]:
            print(f"    {x['before']:.3f} -> {x['after']:.3f}  {x['prompt'][:66]}")
    if r["negative_movements"]:
        print("  negative-side movements (most improved first):")
        for x in r["negative_movements"][:4]:
            print(f"    {x['before']:.3f} -> {x['after']:.3f}  {x['prompt'][:66]}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--old", required=True, help="path or git-ref:path of the pre-trim SKILL.md")
    ap.add_argument("--new", required=True, help="path of the post-trim SKILL.md")
    ap.add_argument("--eval", required=True, help="path to the eval suite JSON")
    ap.add_argument("--no-stopwords", action="store_true",
                    help="also/only report without the stopword filter -- the sensitivity "
                         "check a reviewer asked for; a result that only holds WITH the "
                         "filter is a result about the filter")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    old_full, new = read_description(a.old), read_description(a.new)
    suite = load_suite(a.eval)

    variants = [False] if a.no_stopwords else [True, False]
    results = [score(old_full, new, suite, use_stop) for use_stop in variants]

    if a.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2))
        return 0

    print(f"\ntrigger-coverage · {a.eval} · {len(suite)} prompts\n")
    for r in results:
        render(r)
    print("  NOTE: word overlap cannot see trigger-condition restructuring, and scores one\n"
          "  description in isolation with no competing skill present. Run\n"
          "  .github/scripts/check_skill_descriptions.py --compare OLD NEW and read the\n"
          "  DROPPED / NARROWED / REWORDED rows too.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
