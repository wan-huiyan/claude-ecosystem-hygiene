#!/usr/bin/env python3
"""
render_treatment_report.py — emit a self-contained, INTERACTIVE HTML recap of a
per-project skillOverrides treatment (part of the skills-catalog-context-cost skill).

Data-driven and project-neutral: it reads the OFF set from a project's
`.claude/settings.json` (skillOverrides == "off"), enumerates the skills universe from
`~/.claude/skills/`, computes the bare-name token estimate, and renders an arcade-styled
page whose tiles / bars / panel boxes are CLICKABLE → a searchable, filterable explorer
of every skill by decision (off / on / — if you pass a panel-decision file — kept / added /
override, each with the reviewer's reason). No build step, no external fetch; opens from
file:// because all data is inlined.

Usage:
  python3 render_treatment_report.py \
    --settings .claude/settings.json \
    [--skills-dir ~/.claude/skills] \
    [--decisions panel-decisions.json] \
    [--title "My Project"] [--out skill-treatment.html]

panel-decisions.json (all keys optional):
  {
    "pulls":    [{"n":"skill-name","r":"why it was kept ON"}, ...],   # reviewer kept ON
    "adds":     [{"n":"skill-name","r":"why it's clearly off-domain"}, ...],  # extra OFF
    "override": [{"n":"skill-name","r":"why the orchestrator kept it ON"}, ...]
  }

Token math: the injected catalog cost ≈ Σ(len(name)+3)/4 over the universe (bare names +
"- " + newline, ~4 chars/token). "Saved" ≈ the same over the OFF set. Paid every turn AND
per subagent → the page notes the ×N fan-out multiplier.
"""
import argparse, json, pathlib, sys

def load_off(settings_path: pathlib.Path) -> set:
    if not settings_path.is_file():
        sys.exit(f"no settings.json at {settings_path}")
    ov = json.loads(settings_path.read_text()).get("skillOverrides", {})
    return {k for k, v in ov.items() if v == "off"}

def tok(names) -> int:
    return round(sum(len(n) + 3 for n in names) / 4)

def build(args):
    skills_dir = pathlib.Path(args.skills_dir).expanduser()
    universe = sorted(d.name for d in skills_dir.iterdir() if (d / "SKILL.md").exists())
    off = sorted(n for n in load_off(pathlib.Path(args.settings)) if n in set(universe))
    on = sorted(set(universe) - set(off))

    dec = {"pulls": [], "adds": [], "override": []}
    if args.decisions:
        d = json.loads(pathlib.Path(args.decisions).read_text())
        for k in dec:
            dec[k] = [{"n": x["n"], "r": x.get("r", "")} for x in d.get(k, []) if "n" in x]

    full_tok, off_tok = tok(universe), tok(off)
    pct = round(100 * len(off) / max(len(universe), 1))
    payload = {"total": len(universe), "off": off, "on": on, **dec}

    has_panel = any(dec[k] for k in dec)
    panel_html = f"""
  <section>
    <h2>⚖️ Review-panel decisions <span class=\"hint\">tap a box →</span></h2>
    <p class=\"lead\">Allow-by-default → a wrongly-hidden <i>relevant</i> skill is the only harm. Reviewers hunted
      false-positives; the merge kept ON anything any reviewer flagged (union, not intersection).</p>
    <div class=\"verdict\">
      <div class=\"vbox keep\" data-f=\"pulls\"><div class=\"big\">{len(dec['pulls'])}</div><div class=\"cap\">pulled back ON</div><div class=\"cta\">tap → names + reasons</div></div>
      <div class=\"vbox add\" data-f=\"adds\"><div class=\"big\">{len(dec['adds'])}</div><div class=\"cap\">added OFF</div><div class=\"cta\">tap → names + reasons</div></div>
      <div class=\"vbox over\" data-f=\"override\"><div class=\"big\">{len(dec['override'])}</div><div class=\"cap\">override</div><div class=\"cta\">tap → reason</div></div>
    </div>
  </section>""" if has_panel else ""

    title = args.title or "this project"
    html = TEMPLATE
    html = html.replace("__TITLE__", title)
    html = html.replace("__TOTAL__", str(len(universe)))
    html = html.replace("__OFF__", str(len(off)))
    html = html.replace("__ON__", str(len(on)))
    html = html.replace("__PCT__", str(pct))
    html = html.replace("__FULLTOK__", f"{full_tok/1000:.1f}")
    html = html.replace("__SAVEDTOK__", f"{off_tok/1000:.1f}")
    html = html.replace("__OFFPCTWIDTH__", str(min(pct, 100)))
    html = html.replace("__PANEL__", panel_html)
    html = html.replace("__DATA__", json.dumps(payload, separators=(",", ":")))

    out = pathlib.Path(args.out).expanduser()
    out.write_text(html)
    print(f"wrote {out}  ({len(html)} bytes)")
    print(f"universe {len(universe)} · off {len(off)} ({pct}%) · on {len(on)} · "
          f"~{full_tok/1000:.1f}k tok/injection → ~{off_tok/1000:.1f}k saved"
          + (f" · panel {len(dec['pulls'])}/{len(dec['adds'])}/{len(dec['override'])}" if has_panel else ""))

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Skills-Catalog Treatment · __TITLE__</title>
<style>
  :root{--bg:#0a0612;--panel:#1a0f2e;--panel2:#22143b;--ink:#f3e9ff;--dim:#a991c9;--line:#3a2557;
    --flame:#ff5a3c;--coin:#ffce4a;--neon:#46e8c8;--violet:#b06bff;--moon:#7aa2ff;--good:#46e88a;}
  *{box-sizing:border-box}
  body{margin:0;background:radial-gradient(1200px 600px at 80% -10%,#2a1450 0,transparent 60%),
    radial-gradient(900px 500px at -10% 110%,#2a0f3a 0,transparent 55%),var(--bg);color:var(--ink);
    font:15px/1.55 ui-monospace,"SF Mono",Menlo,Consolas,monospace;letter-spacing:.2px;padding:32px 18px 80px}
  .wrap{max-width:1080px;margin:0 auto}.px{font-weight:800;letter-spacing:1px}code{color:var(--coin)}
  header.hero{border:1px solid var(--line);border-radius:18px;padding:28px 26px;margin-bottom:22px;
    background:linear-gradient(160deg,var(--panel2),var(--panel) 70%);position:relative;overflow:hidden;box-shadow:0 24px 60px -30px rgba(176,107,255,.5)}
  header.hero::after{content:"";position:absolute;inset:0;background:repeating-linear-gradient(0deg,transparent 0 3px,rgba(255,255,255,.018) 3px 4px);pointer-events:none}
  .tag{display:inline-block;font-size:11px;letter-spacing:2px;text-transform:uppercase;color:var(--coin);border:1px solid #4a3a12;background:#231a06;border-radius:999px;padding:4px 11px;margin-bottom:14px}
  h1{margin:.1em 0 .15em;font-size:30px;line-height:1.15}h1 .em{color:var(--neon)}
  .sub{color:var(--dim);font-size:14px;max-width:780px}.sub b{color:var(--ink)}
  .tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0}
  .tile{border:1px solid var(--line);border-radius:14px;padding:16px 14px;background:linear-gradient(165deg,var(--panel),#160c28);cursor:pointer;transition:transform .12s,border-color .12s}
  .tile:hover{transform:translateY(-2px);border-color:var(--violet)}
  .tile .k{font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:var(--dim)}
  .tile .v{font-size:27px;font-weight:800;margin-top:6px}.tile .v small{font-size:13px;color:var(--dim);font-weight:600}
  .t-flame .v{color:var(--flame)}.t-neon .v{color:var(--neon)}.t-coin .v{color:var(--coin)}.t-violet .v{color:var(--violet)}
  .tile .note{font-size:11px;color:var(--dim);margin-top:6px}
  section{border:1px solid var(--line);border-radius:16px;padding:22px;margin:18px 0;background:linear-gradient(180deg,rgba(26,15,46,.7),rgba(16,9,30,.7))}
  section h2{margin:0 0 4px;font-size:18px;display:flex;align-items:center;gap:10px}
  section .lead{color:var(--dim);font-size:13.5px;margin:0 0 16px}
  .bar-row{display:grid;grid-template-columns:140px 1fr 96px;align-items:center;gap:12px;margin:10px 0}
  .bar-row .lab{font-size:12px;color:var(--dim);text-align:right}.bar-row .lab b{color:var(--ink)}
  .track{height:26px;border-radius:7px;background:#120a20;border:1px solid var(--line);overflow:hidden}
  .fill{height:100%;border-radius:6px;transform-origin:left;animation:grow 1.1s cubic-bezier(.2,.8,.2,1) both;cursor:pointer}
  .fill.full{background:linear-gradient(90deg,#7a3bd1,#b06bff)}.fill.s2{background:linear-gradient(90deg,#1f9e84,var(--neon))}
  @keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
  .bar-row .amt{font-size:13px;font-weight:700}
  .verdict{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:6px}
  .vbox{border:1px solid var(--line);border-radius:12px;padding:14px;text-align:center;background:linear-gradient(165deg,var(--panel),#160c28);cursor:pointer;transition:transform .12s}
  .vbox:hover{transform:translateY(-2px)}
  .vbox.keep{border-color:#1f5e3f}.vbox.add{border-color:#5e2a1f}.vbox.over{border-color:#5e4a12}
  .vbox .big{font-size:26px;font-weight:800}.vbox.keep .big{color:var(--good)}.vbox.add .big{color:var(--flame)}.vbox.over .big{color:var(--coin)}
  .vbox .cap{font-size:11px;color:var(--dim);margin-top:3px}.vbox .cta{font-size:10px;color:var(--moon);margin-top:5px}
  #explorer{scroll-margin-top:14px}
  .filters{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
  .fbtn{font-size:12px;border:1px solid var(--line);background:#160c28;color:var(--dim);border-radius:8px;padding:7px 12px;cursor:pointer;transition:.12s}
  .fbtn:hover{color:var(--ink);border-color:var(--violet)}.fbtn.active{background:var(--violet);color:#fff;border-color:var(--violet)}
  .fbtn .c{opacity:.8;font-weight:700}
  .search{width:100%;margin:0 0 12px;padding:11px 13px;border-radius:10px;border:1px solid var(--line);background:#0c0718;color:var(--ink);font:13px ui-monospace,monospace}
  .search::placeholder{color:#6b5689}#count{font-size:12px;color:var(--dim);margin:0 0 10px}
  .list{max-height:440px;overflow:auto;border:1px solid var(--line);border-radius:12px;background:#0c0718;padding:6px}
  .list::-webkit-scrollbar{width:10px}.list::-webkit-scrollbar-thumb{background:#3a2557;border-radius:8px}
  .row{display:grid;grid-template-columns:auto 1fr;gap:10px;align-items:baseline;padding:7px 10px;border-bottom:1px solid #1c1130}
  .row:last-child{border-bottom:0}.row .nm{font-size:12.5px;color:var(--ink);word-break:break-all}
  .row .rs{grid-column:2;font-size:11px;color:var(--dim);margin-top:2px}
  .tagsm{font-size:9px;font-weight:800;letter-spacing:.5px;text-transform:uppercase;border-radius:5px;padding:2px 6px;white-space:nowrap}
  .tag-off,.tag-add{background:#241009;color:#ffb59f;border:1px solid #5e2a1f}
  .tag-on,.tag-kept{background:#0d2419;color:#9ff0c2;border:1px solid #1f5e3f}
  .tag-over{background:#231a06;color:#ffd86b;border:1px solid #5e4a12}
  .hint{font-size:11px;color:var(--moon);margin-left:auto;font-weight:600}
  .note-strip{display:flex;gap:12px;align-items:flex-start;border:1px solid #4a3a12;background:#1e1606;border-radius:12px;padding:14px 16px;margin-top:14px}
  .note-strip .i{font-size:20px}.note-strip .t{font-size:13px;color:#f0dca0}.note-strip .t b{color:#fff}
  footer{color:var(--dim);font-size:12px;text-align:center;margin-top:30px;border-top:1px solid var(--line);padding-top:18px}
  @media(max-width:760px){.tiles,.verdict{grid-template-columns:1fr 1fr}.bar-row{grid-template-columns:92px 1fr 60px}}
</style></head><body><div class="wrap">

  <header class="hero">
    <span class="tag">skillOverrides treatment · __TITLE__</span>
    <h1 class="px">🔥 Skills-Catalog — <span class="em">trimmed for this project</span></h1>
    <p class="sub">The available-skills catalog is injected every turn AND into every subagent. This project hides
      <b>__OFF__ of __TOTAL__</b> clearly-irrelevant skills (~<b>__PCT__%</b>) from the model-invocable catalog —
      hidden skills stay on disk, still <code>/name</code>-invocable. <b>Tap any tile, bar, or panel box to drill
      into the exact list.</b></p>
  </header>

  <div class="tiles">
    <div class="tile t-violet" data-f="all"><div class="k">Catalog size ▸</div><div class="v">__TOTAL__</div><div class="note">tap → every skill</div></div>
    <div class="tile t-flame" data-f="off"><div class="k">Turned OFF ▸</div><div class="v">__OFF__ <small>/__TOTAL__</small></div><div class="note">~__PCT__% cut, this project</div></div>
    <div class="tile t-neon" data-f="on"><div class="k">Kept ON ▸</div><div class="v">__ON__</div><div class="note">tap → what stays loaded</div></div>
    <div class="tile t-coin" data-f="off"><div class="k">Catalog cost</div><div class="v">~__SAVEDTOK__k <small>saved</small></div><div class="note">of ~__FULLTOK__k tok/injection · ×N on fan-out</div></div>
  </div>

  <section>
    <h2>📊 Before vs After <span class="hint">tap a bar →</span></h2>
    <p class="lead">Allow-by-default: a skill is hidden only if clearly irrelevant to this project.</p>
    <div class="bar-row"><div class="lab">Before</div><div class="track"><div class="fill full" style="width:100%" data-f="all"></div></div><div class="amt">__TOTAL__ on</div></div>
    <div class="bar-row"><div class="lab"><b>After</b></div><div class="track"><div class="fill s2" style="width:__OFFPCTWIDTH__%" data-f="off"></div></div><div class="amt">__OFF__ off</div></div>
  </section>
__PANEL__
  <section id="explorer">
    <h2>🔍 Drill down — every skill, by decision</h2>
    <p class="lead">Filter by decision, then search. Each name is a literal <code>~/.claude/skills/</code> dir — the file
      stays intact, just hidden from the model-invocable catalog (reversible: delete its entry or set <code>"on"</code>).</p>
    <div class="filters" id="filters"></div>
    <input class="search" id="q" placeholder="🔎 filter by name…">
    <div id="count"></div>
    <div class="list" id="list"></div>
  </section>

  <div class="note-strip"><span class="i">🕹️</span><span class="t"><b>Takes effect on restart</b> — the catalog is
    injected at session start. Hidden skills remain <code>/name</code>-invocable.</span></div>

  <footer>context-police · interactive treatment recap · self-contained &amp; reversible 🔥🪙🌙⚡🎮</footer>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
  const D=JSON.parse(document.getElementById('data').textContent);
  const ALL=[...D.off.map(n=>({n,tag:'off'})),...D.on.map(n=>({n,tag:'on'}))].sort((a,b)=>a.n<b.n?-1:1);
  const V={all:{l:'All',c:D.total,g:()=>ALL},off:{l:'Off',c:D.off.length,g:()=>D.off.map(n=>({n,tag:'off'}))},
    on:{l:'On',c:D.on.length,g:()=>D.on.map(n=>({n,tag:'on'}))},
    pulls:{l:'Kept ON',c:D.pulls.length,g:()=>D.pulls.map(x=>({n:x.n,r:x.r,tag:'kept'}))},
    adds:{l:'Added OFF',c:D.adds.length,g:()=>D.adds.map(x=>({n:x.n,r:x.r,tag:'add'}))},
    override:{l:'Override',c:D.override.length,g:()=>D.override.map(x=>({n:x.n,r:x.r,tag:'over'}))}};
  const order=['all','off','on'].concat((D.pulls.length||D.adds.length||D.override.length)?['pulls','adds','override']:[]);
  let cur='off';
  const eF=document.getElementById('filters'),eL=document.getElementById('list'),eC=document.getElementById('count'),eQ=document.getElementById('q');
  order.forEach(k=>{const b=document.createElement('button');b.className='fbtn';b.dataset.k=k;
    b.innerHTML=V[k].l+' <span class="c">'+V[k].c+'</span>';b.onclick=()=>{cur=k;render();};eF.appendChild(b);});
  function render(){[...eF.children].forEach(b=>b.classList.toggle('active',b.dataset.k===cur));
    const q=eQ.value.trim().toLowerCase();let r=V[cur].g();
    if(q)r=r.filter(x=>x.n.toLowerCase().includes(q)||(x.r&&x.r.toLowerCase().includes(q)));
    eC.textContent=r.length+' skill'+(r.length===1?'':'s')+(q?' matching "'+q+'"':'')+' · '+V[cur].l;
    eL.innerHTML=r.length?r.map(x=>'<div class="row"><span class="tagsm tag-'+x.tag+'">'+x.tag+'</span><span class="nm">'+x.n+'</span>'+(x.r?'<span class="rs">'+x.r+'</span>':'')+'</div>').join(''):'<div class="row"><span class="nm" style="color:#6b5689">no matches</span></div>';}
  eQ.oninput=render;
  document.body.addEventListener('click',e=>{const t=e.target.closest('[data-f]');if(!t)return;
    if(!V[t.dataset.f])return;cur=t.dataset.f;render();
    document.getElementById('explorer').scrollIntoView({behavior:'smooth',block:'start'});eQ.focus();});
  render();
</script>
</body></html>
"""

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Render an interactive skillOverrides treatment recap.")
    ap.add_argument("--settings", required=True, help="path to the project's .claude/settings.json")
    ap.add_argument("--skills-dir", default="~/.claude/skills", help="skills universe dir")
    ap.add_argument("--decisions", help="optional panel-decisions JSON (pulls/adds/override)")
    ap.add_argument("--title", help="project label shown in the header")
    ap.add_argument("--out", default="skill-treatment.html", help="output HTML path")
    build(ap.parse_args())
