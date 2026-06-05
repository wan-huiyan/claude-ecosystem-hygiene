#!/usr/bin/env python3
"""
Lesson-retrieval brain (shadow-mode pilot for the context-police retrieval-hook design).
Dependency-free BM25 over a lesson index built from ~/.claude/skills/*/SKILL.md.
Importable (build_index + retrieve) and runnable (CLI: `python3 retrieve.py "<query>"`).

Design (from docs/research/2026-06-04-episodic-lesson-recall-substrate-research.md):
- index in place from the existing SKILL.md corpus (no content migration);
- BM25/keyword ranking v1 (corpus is exact-token-dominated; <1s, no embedding service);
- a retrieval result = {id, score, kind, one_line_fix, tool_prefixes, file_globs}.
"""
import json, math, os, re, pathlib
from collections import Counter, defaultdict

SKILLS_DIR = pathlib.Path(os.path.expanduser("~/.claude/skills"))
INDEX_PATH = pathlib.Path(__file__).resolve().parent / "lesson-index.jsonl"

STOP = set("a an the of to in on for and or but with without is are be was were this that these those "
           "it its as at by from into not no if then else when where which who whom whose how why what "
           "you your we our they their he she his her i me my mine use used using when uses can may must "
           "do does did done will would should could one two three via per over under above below only also "
           "than more most less least very each any all some such other another same different new old".split())

# tool/domain tokens we treat as high-signal "action prefixes" (match against tool commands).
TOOL_TOKENS = ("bq","gcloud","gcp","gsutil","cloudrun","cloud-run","cloudbuild","dataform","dbt","k8s",
    "kubectl","helm","terraform","terragrunt","ansible","docker","firestore","gh","git","flask","fastapi",
    "django","jinja","pytest","npm","pnpm","yarn","tsc","tsx","vite","node","react","playwright","sql",
    "bash","sed","awk","rg","ripgrep","curl","python","pip","rmarkdown","snowplow","shap","xgboost","pymc")

FILE_EXT_RE = re.compile(r"\b\w*\*?\.(py|ts|tsx|js|jsx|html|sql|sqlx|jsonl|json|md|yml|yaml|sh|css|tf|ipynb)\b", re.I)

def _tokens(text):
    return [t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t and t not in STOP and len(t) > 1]

def _parse_frontmatter(md):
    """Cheap front-matter parse: returns (name, description). Handles `|`/`>` block scalars."""
    m = re.match(r"^---\s*\n(.*?)\n---", md, re.S)
    if not m:
        return None, ""
    fm = m.group(1)
    name = ""
    nm = re.search(r"(?m)^name:\s*(.+)$", fm)
    if nm:
        name = nm.group(1).strip().strip('"').strip("'")
    desc = ""
    dm = re.search(r"(?ms)^description:\s*(\|>?\-?|>\-?)?\s*\n((?:[ \t]+.*\n?)+)", fm)
    if dm:
        desc = re.sub(r"(?m)^[ \t]+", "", dm.group(2)).strip()
    else:
        dm2 = re.search(r"(?m)^description:\s*(.+)$", fm)
        if dm2:
            desc = dm2.group(1).strip().strip('"').strip("'")
    return name, desc

# Procedure vs trap classifier (research §3 test, approximated): trap = a long kebab single-incident name.
def classify_kind(name, desc):
    hyphens = name.count("-")
    proc_markers = ("driven-development","worktree","handoff","brainstorm","review-panel","planning",
        "generator","validator","-creator","research","writing","design","pipeline","orchestrat",
        "audit","skill-","publish","sync","claudeception","deep-research")
    if any(p in name for p in proc_markers):
        return "procedure"
    return "trap" if hyphens >= 2 else "procedure"

def build_index(out_path=INDEX_PATH):
    rows = []
    for d in sorted(SKILLS_DIR.iterdir()):
        sk = d / "SKILL.md"
        if not sk.exists():
            continue
        try:
            md = sk.read_text(errors="ignore")
        except Exception:
            continue
        name, desc = _parse_frontmatter(md)
        name = name or d.name
        name_tokens = name.split("-")
        toks = _tokens(name) + _tokens(desc)
        tool_prefixes = sorted({t for t in TOOL_TOKENS if t in name_tokens or (" "+t+" ") in (" "+name+" ")})
        file_globs = sorted({m.group(0).lower() for m in FILE_EXT_RE.finditer(name + " " + desc)})
        first = re.split(r"(?<=[.!?])\s", desc.strip())[0] if desc else ""
        rows.append({
            "id": d.name,
            "name": name,
            "kind": classify_kind(d.name, desc),
            "tokens": toks,                       # for BM25
            "tool_prefixes": tool_prefixes,
            "file_globs": file_globs,
            "one_line_fix": first[:200],
        })
    out_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return rows

# ---------------- BM25 ----------------
class BM25:
    def __init__(self, docs_tokens, k1=1.5, b=0.75):
        self.docs = docs_tokens
        self.N = len(docs_tokens)
        self.avgdl = (sum(len(d) for d in docs_tokens) / self.N) if self.N else 0.0
        self.df = Counter()
        for d in docs_tokens:
            for t in set(d):
                self.df[t] += 1
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in self.df.items()}
        self.tf = [Counter(d) for d in docs_tokens]
        self.k1, self.b = k1, b

    def score(self, qi, query_tokens):
        dl = len(self.docs[qi]) or 1
        s = 0.0
        tf = self.tf[qi]
        for t in query_tokens:
            if t not in tf:
                continue
            idf = self.idf.get(t, 0.0)
            num = tf[t] * (self.k1 + 1)
            den = tf[t] + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
            s += idf * num / den
        return s

def load_index(path=INDEX_PATH):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

_CACHE = {}
def _engine(path=INDEX_PATH):
    key = str(path)
    if key not in _CACHE:
        idx = load_index(path)
        _CACHE[key] = (idx, BM25([r["tokens"] for r in idx]))
    return _CACHE[key]

def retrieve(query, k=5, kinds=("trap",), tool_cmd="", file_path="", path=INDEX_PATH):
    """Rank lessons against a free-text query (+ optional tool command / edited file path).
    Returns top-k {id, score, kind, one_line_fix}. kinds filters which buckets are eligible."""
    idx, bm = _engine(path)
    q = _tokens(query) + _tokens(tool_cmd) + _tokens(file_path)
    if not q:
        return []
    cmd_tokens = set(_tokens(tool_cmd))
    fp = (file_path or "").lower()
    scored = []
    for i, r in enumerate(idx):
        if kinds and r["kind"] not in kinds:
            continue
        s = bm.score(i, q)
        # action-key boosts (the PostToolUse signal): a tool-prefix or file-glob match is strong.
        if tool_cmd and any(tp in cmd_tokens or fp.startswith(tp) for tp in r["tool_prefixes"]):
            s += 3.0
        if file_path and any(fp.endswith(g.lstrip("*")) for g in r["file_globs"]):
            s += 2.0
        if s > 0:
            scored.append((s, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"id": r["id"], "score": round(s, 3), "kind": r["kind"], "one_line_fix": r["one_line_fix"]}
            for s, r in scored[:k]]

if __name__ == "__main__":
    import sys
    if "--build" in sys.argv:
        rows = build_index()
        traps = sum(1 for r in rows if r["kind"] == "trap")
        print(f"indexed {len(rows)} skills → {INDEX_PATH}  (trap={traps}, procedure={len(rows)-traps})")
    else:
        q = " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
        for hit in retrieve(q, k=8, kinds=("trap","procedure")):
            print(f"{hit['score']:6.2f}  {hit['id']}")
