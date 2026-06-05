#!/usr/bin/env python3
"""
phase4_subagent_scan.py  —  "subagent leg" measurement for the lesson-retrieval design.

QUESTION: A SubagentStart hook can only key on the subagent's agent_type (subagent_type),
NOT the subagent's task text. So the only feasible subagent-side retrieval is a FIXED
per-agent_type "trap bundle" preloaded at dispatch. Is that viable, and how well would a
fixed bundle cover real subagent trap-firings?

METHOD (all empirically discovered; see header comments inline):
  - Subagent transcripts: ~/.claude/projects/<slug>/**/subagents/**/agent-*.jsonl
    (rglob over any path containing a 'subagents' dir — catches the nested
     .../subagents/.../workflows/wf_*/agent-*.jsonl workflow fleet too).
  - agent_type: the sibling '<transcript>.meta.json' file, key "agentType".
    (Verified present in 100% of meta files; 1:1 with transcripts.)
    Fallback if a meta is ever missing/unparseable: the "attributionAgent" field
    embedded in assistant lines of the transcript itself.
  - A "Skill firing" = an assistant tool_use block with name=="Skill"; the fired
    skill id is input["skill"] (may carry a plugin prefix like "superpowers:foo" —
    we match both the raw id and the bare id after the last ':').
  - Trap set: rows with kind=="trap" in lesson-index.jsonl (the kind heuristic
    over-labels, so we ALSO report ALL Skill firings regardless of kind).

Dependency-free: stdlib only. Run: python3 phase4_subagent_scan.py
Never fabricates: zero/absent fields are reported as zero/absent.
"""

import json
import os
import re
import collections
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
LESSON_INDEX = HERE / "lesson-index.jsonl"
PROJECTS = Path.home() / ".claude" / "projects"

SKILL_LINE_HINT = '"Skill"'  # cheap pre-filter before JSON-parsing a line


# ---------------------------------------------------------------------------
# 1. Trap set from lesson-index
# ---------------------------------------------------------------------------
def load_index():
    """Return (trap_ids:set, all_ids:set). traps = rows with kind=='trap'."""
    trap_ids, all_ids = set(), set()
    if not LESSON_INDEX.exists():
        return trap_ids, all_ids
    with LESSON_INDEX.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            sid = o.get("id")
            if not sid:
                continue
            all_ids.add(sid)
            if o.get("kind") == "trap":
                trap_ids.add(sid)
    return trap_ids, all_ids


# ---------------------------------------------------------------------------
# 2. Enumerate subagent transcripts (rglob; include nested workflow fleet)
# ---------------------------------------------------------------------------
def enumerate_transcripts():
    """All agent-*.jsonl whose path contains a 'subagents' directory."""
    if not PROJECTS.exists():
        return []
    out = []
    for p in PROJECTS.rglob("agent-*.jsonl"):
        parts = p.parts
        if "subagents" in parts:
            out.append(p)
    return sorted(out)


def meta_path_for(transcript: Path) -> Path:
    # agent-XXXX.jsonl -> agent-XXXX.meta.json (sibling)
    return transcript.with_suffix("").with_suffix(".meta.json") \
        if transcript.suffix == ".jsonl" else Path(str(transcript) + ".meta.json")


def get_agent_type(transcript: Path):
    """agentType from sibling .meta.json; fallback to embedded attributionAgent."""
    mp = Path(str(transcript)[: -len(".jsonl")] + ".meta.json")
    if mp.exists():
        try:
            o = json.loads(mp.read_text())
            at = o.get("agentType")
            if at:
                return at, "meta.agentType"
        except Exception:
            pass
    # fallback: scan transcript for attributionAgent
    try:
        with transcript.open() as fh:
            for line in fh:
                if "attributionAgent" not in line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                aa = o.get("attributionAgent")
                if aa:
                    return aa, "transcript.attributionAgent"
    except Exception:
        pass
    return None, "absent"


# ---------------------------------------------------------------------------
# 3. Extract Skill firings from a transcript
# ---------------------------------------------------------------------------
def skill_firings(transcript: Path):
    """List of fired skill ids (raw, in order) in one transcript."""
    fired = []
    try:
        with transcript.open() as fh:
            for line in fh:
                if SKILL_LINE_HINT not in line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                msg = o.get("message")
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                for b in content:
                    if (isinstance(b, dict) and b.get("type") == "tool_use"
                            and b.get("name") == "Skill"):
                        inp = b.get("input") or {}
                        s = inp.get("skill")
                        if s:
                            fired.append(s)
    except Exception:
        pass
    return fired


def matches_index(skill_id: str, idset: set):
    """A fired skill id matches an index set if its raw OR bare (post-':') form is in it."""
    if skill_id in idset:
        return skill_id
    bare = skill_id.split(":")[-1]
    if bare in idset:
        return bare
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    trap_ids, all_ids = load_index()
    print("=" * 78)
    print("PHASE 4 — SUBAGENT LEG: fixed per-agent_type trap-bundle viability")
    print("=" * 78)
    print(f"lesson-index: {LESSON_INDEX}")
    print(f"  total skills indexed: {len(all_ids)}   trap-kind: {len(trap_ids)}   "
          f"procedure-kind: {len(all_ids) - len(trap_ids)}")
    print()

    # -- METHOD AUDIT (reproducibility) --------------------------------------
    transcripts = enumerate_transcripts()
    print("-" * 78)
    print("METHOD AUDIT (agent_type extraction)")
    print("-" * 78)
    nested = [p for p in transcripts if "workflows" in p.parts]
    print(f"subagent transcripts (agent-*.jsonl under a 'subagents' dir): {len(transcripts)}")
    print(f"  of which nested under a workflows/wf_* fleet: {len(nested)}")
    if transcripts:
        sample = transcripts[0]
        mp = Path(str(sample)[: -len('.jsonl')] + ".meta.json")
        print(f"  sample transcript: .../{sample.parent.name}/{sample.name}")
        print(f"  sample sibling meta exists: {mp.exists()}")
        if mp.exists():
            try:
                print(f"  sample meta.json dump: {mp.read_text().strip()[:200]}")
            except Exception as e:
                print(f"  (meta read err: {e})")
        # sample first transcript line top-keys
        try:
            with sample.open() as fh:
                first = json.loads(fh.readline())
            print(f"  sample transcript first-line top keys: {sorted(first.keys())}")
        except Exception as e:
            print(f"  (first-line err: {e})")
    print()

    # -- Walk every transcript -----------------------------------------------
    n_transcripts = len(transcripts)
    type_count = collections.Counter()          # agent_type -> #transcripts
    type_source = collections.Counter()         # where agent_type came from
    n_with_any_skill = 0
    n_with_trap_skill = 0
    total_skill_firings = 0
    total_trap_firings = 0
    fired_by_id = collections.Counter()         # raw skill id -> count
    # (agent_type, matched_or_raw_id) -> count, for the ALL-skill lens
    pair_all = collections.Counter()
    pair_trap = collections.Counter()           # trap-lens
    type_skill_firings_all = collections.Counter()   # agent_type -> total all-skill firings
    type_skill_firings_trap = collections.Counter()

    for t in transcripts:
        at, src = get_agent_type(t)
        at = at or "<unknown>"
        type_count[at] += 1
        type_source[src] += 1

        fired = skill_firings(t)
        if fired:
            n_with_any_skill += 1
        had_trap = False
        for raw in fired:
            total_skill_firings += 1
            fired_by_id[raw] += 1
            # canonical key for the ALL lens: bare id if it matches the index, else raw
            m_all = matches_index(raw, all_ids)
            key_all = m_all if m_all else raw.split(":")[-1]
            pair_all[(at, key_all)] += 1
            type_skill_firings_all[at] += 1
            # trap lens
            m_trap = matches_index(raw, trap_ids)
            if m_trap:
                had_trap = True
                total_trap_firings += 1
                pair_trap[(at, m_trap)] += 1
                type_skill_firings_trap[at] += 1
        if had_trap:
            n_with_trap_skill += 1

    # -- DELIVERABLE 2: counts ----------------------------------------------
    print("-" * 78)
    print("COUNTS")
    print("-" * 78)
    print(f"subagent transcripts total                 : {n_transcripts}")
    print(f"  that invoke >=1 Skill (any)               : {n_with_any_skill}"
          f"  ({pct(n_with_any_skill, n_transcripts)})")
    print(f"  that invoke >=1 trap-kind Skill           : {n_with_trap_skill}"
          f"  ({pct(n_with_trap_skill, n_transcripts)})")
    print(f"total Skill firings (any)                   : {total_skill_firings}")
    print(f"total trap-kind Skill firings               : {total_trap_firings}")
    print(f"distinct skill ids fired                    : {len(fired_by_id)}")
    print(f"agent_type source breakdown                 : {dict(type_source)}")
    print(f"distinct agent_types                        : {len(type_count)}")
    print()
    print("agent_type distribution (top 15 by transcript count):")
    for at, c in type_count.most_common(15):
        print(f"  {c:5d}  {at}")
    print()

    # -- DELIVERABLE 3: core table (per agent_type, skills fired + freq) -----
    print("-" * 78)
    print("CORE TABLE — per agent_type that fired >=1 Skill (ALL-skill lens)")
    print("-" * 78)
    # group pair_all by agent_type
    by_type = collections.defaultdict(collections.Counter)
    for (at, sk), c in pair_all.items():
        by_type[at][sk] += c
    # order agent_types by total firings desc
    ranked_types = sorted(by_type.items(), key=lambda kv: -sum(kv[1].values()))
    print(f"agent_types that fired >=1 Skill: {len(ranked_types)}")
    for at, skc in ranked_types:
        tot = sum(skc.values())
        ntrap = sum(c for sk, c in skc.items() if sk in trap_ids)
        print(f"\n  [{at}]  total_firings={tot}  trap_firings={ntrap}  "
              f"distinct_skills={len(skc)}")
        for sk, c in skc.most_common():
            tag = "TRAP" if sk in trap_ids else ("proc" if sk in all_ids else "off-idx")
            print(f"       {c:3d}  {sk}   [{tag}]")
    print()
    print("Top agent_types by total Skill-firings:")
    for at, skc in ranked_types[:10]:
        print(f"  {sum(skc.values()):4d}  {at}")
    print()

    # -- DELIVERABLE 4: coverage@N + leave-one-out ---------------------------
    for lens_name, pair, type_fire in (
        ("ALL-skill lens", pair_all, type_skill_firings_all),
        ("TRAP-only lens", pair_trap, type_skill_firings_trap),
    ):
        print("-" * 78)
        print(f"COVERAGE — {lens_name}")
        print("-" * 78)
        total_events = sum(pair.values())
        if total_events == 0:
            print("  no firings in this lens; coverage undefined.")
            print()
            continue
        # build per-agent_type skill->count
        bt = collections.defaultdict(collections.Counter)
        for (at, sk), c in pair.items():
            bt[at][sk] += c

        # deterministic top-N: sort by (-count, skill_id) so ties + re-runs reproduce
        def top_n(counter, N):
            ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
            return {sk for sk, _ in ranked[:N]}

        # in-sample coverage@N: top-N skills per agent_type
        print("  IN-SAMPLE coverage@N (fixed bundle = top-N skills fired per agent_type):")
        for N in (3, 5, 10):
            covered = 0
            for at, skc in bt.items():
                topN = top_n(skc, N)
                covered += sum(c for sk, c in skc.items() if sk in topN)
            print(f"    coverage@{N:<2d} = {covered}/{total_events} = {pct(covered, total_events)}")
        # how many agent_types ever fire >N distinct skills (explains flat sweep)
        maxdistinct = max(len(skc) for skc in bt.values())
        types_over3 = sum(1 for skc in bt.values() if len(skc) > 3)
        print(f"    (max distinct skills any single agent_type fired: {maxdistinct}; "
              f"agent_types firing >3 distinct skills: {types_over3})")
        print()

        # TRUE per-firing LEAVE-ONE-OUT @ N: for each firing instance, remove it,
        # rebuild the agent_type's deterministic top-N bundle from the REMAINING
        # firings, and check whether the held-out skill is in that bundle. This is
        # the honest "does history predict held-out firings" number, and it sits
        # symmetric with in-sample coverage@N (it must be <= in-sample, and for a
        # catch-all type with many distinct skills, LOO@3 < LOO@10).
        print("  LEAVE-ONE-OUT (per-firing; rebuild top-N bundle WITHOUT the held-out firing):")
        for N in (3, 5, 10):
            hits = 0
            for at, skc in bt.items():
                # expand counter into a deterministic firing sequence
                for held_sk in skc.elements():
                    rem = collections.Counter(skc)
                    rem[held_sk] -= 1
                    if rem[held_sk] == 0:
                        del rem[held_sk]
                    bundle = top_n(rem, N) if rem else set()
                    if held_sk in bundle:
                        hits += 1
            print(f"    LOO@{N:<2d} = {hits}/{total_events} = {pct(hits, total_events)}")

        # pair-multiplicity distribution + the N=inf upper bound (predictable iff the
        # pair fired >=2 times so a sibling survives removal). This is the CEILING for
        # any fixed bundle regardless of size; LOO@N above is <= this.
        mult = collections.Counter(pair.values())  # multiplicity -> #pairs at that multiplicity
        singleton_pairs = mult.get(1, 0)
        unpredictable_firings = singleton_pairs  # each singleton pair = 1 unpredictable firing
        ceiling_hits = sum(c for c in pair.values() if c >= 2)
        print(f"    distinct (agent_type, skill) pairs           : {len(pair)}")
        print(f"    pair-multiplicity distribution (mult: #pairs): "
              f"{dict(sorted(mult.items()))}")
        print(f"    singleton pairs (fired exactly once)         : {singleton_pairs}"
              f"  ({pct(singleton_pairs, len(pair))} of pairs)")
        print(f"    firings that are the UNIQUE occ of their pair: {unpredictable_firings}"
              f"  ({pct(unpredictable_firings, total_events)} of firings) -> UNPREDICTABLE by any bundle")
        print(f"    LOO ceiling (N=inf; pair mult>=2)            : {ceiling_hits}"
              f"  ({pct(ceiling_hits, total_events)} of firings) -> upper bound on a fixed bundle")
        print()

        # general-purpose vs specialized split
        gp_keys = [at for at in bt if at == "general-purpose"]
        gp_fire = sum(sum(bt[at].values()) for at in gp_keys)
        spec_fire = total_events - gp_fire
        # specialized pair multiplicity
        spec_pairs = collections.Counter()
        for (at, sk), c in pair.items():
            if at != "general-purpose":
                spec_pairs[(at, sk)] += c
        spec_singletons = sum(1 for c in spec_pairs.values() if c == 1)
        spec_singleton_firings = sum(1 for c in spec_pairs.values() if c == 1)
        spec_predictable = sum(c for c in spec_pairs.values() if c >= 2)
        print("  GENERAL-PURPOSE vs SPECIALIZED split (decision-relevant):")
        print(f"    general-purpose firings : {gp_fire}  ({pct(gp_fire, total_events)})")
        print(f"    specialized firings     : {spec_fire}  ({pct(spec_fire, total_events)})")
        if spec_fire:
            print(f"    within SPECIALIZED types: distinct pairs={len(spec_pairs)}, "
                  f"singleton pairs={spec_singletons}, "
                  f"LOO-predictable firings={spec_predictable} "
                  f"({pct(spec_predictable, spec_fire)} of specialized firings)")
        print()


def pct(a, b):
    return "0.0%" if not b else f"{100.0 * a / b:.1f}%"


if __name__ == "__main__":
    main()
