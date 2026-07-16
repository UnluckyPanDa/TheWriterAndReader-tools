"""Validate and render story relationship graphs as standalone 3D HTML."""

from __future__ import annotations

import html
import json
from pathlib import Path

from shared.lib.relationship_graph import load_relationship_graph
from shared.lib.safe_write import assert_inside_root, safe_copy_file, safe_write_file
from shared.lib.story_loader import load_story_yaml
from shared.lib.workspace_loader import resolve_story_path


TOOLS_ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = TOOLS_ROOT / "templates" / "story-template" / "canon" / "relationship_graph.yaml"


def init_relation_plot(workspace: str | Path, story_id: str) -> Path:
    """Add an empty relationship graph to an existing story without overwriting canon."""
    story_path = resolve_story_path(workspace, story_id)
    target = story_path / "canon" / "relationship_graph.yaml"
    if target.exists():
        raise FileExistsError(f"relationship graph already exists: {target}")
    return safe_copy_file(TEMPLATE_PATH, target, story_path)


def build_relation_plot(workspace: str | Path, story_id: str) -> Path:
    """Build a standalone local 3D viewer inside the selected story."""
    story_path = resolve_story_path(workspace, story_id)
    graph = load_relationship_graph(story_path)
    story = load_story_yaml(story_path)
    title = str(story.get("title") or story_id)
    output_path = story_path / "build" / "relation-plot" / "index.html"
    assert_inside_root(output_path, story_path)
    return safe_write_file(output_path, _render_html(title, graph), story_path)


def _render_html(title: str, graph: dict) -> str:
    graph_json = json.dumps(graph, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title} — Relationship Plot</title>
<style>
:root{{--bg:#07101f;--panel:#0f1c30e8;--text:#eef5ff;--muted:#9eb0c9;--accent:#70d6ff}}
*{{box-sizing:border-box}} body{{margin:0;overflow:hidden;background:radial-gradient(circle at 50% 40%,#142844,#07101f 62%);color:var(--text);font:14px system-ui,-apple-system,sans-serif}}
canvas{{display:block;width:100vw;height:100vh;cursor:grab}} canvas:active{{cursor:grabbing}}
.panel{{position:fixed;z-index:2;top:18px;left:18px;width:min(340px,calc(100vw - 36px));padding:16px;border:1px solid #ffffff1c;border-radius:14px;background:var(--panel);backdrop-filter:blur(16px);box-shadow:0 18px 50px #0008}}
h1{{margin:0 0 4px;font-size:18px}} .meta{{color:var(--muted);font-size:12px;margin-bottom:14px}}
.controls{{display:grid;grid-template-columns:1fr 1fr;gap:9px}} label{{display:grid;gap:5px;color:var(--muted);font-size:11px}} label.wide{{grid-column:1/-1}}
input,select,button{{width:100%;border:1px solid #ffffff20;border-radius:8px;background:#071425;color:var(--text);padding:8px}}
button{{cursor:pointer;background:#173252}} button:hover{{border-color:var(--accent)}}
.detail{{margin-top:12px;padding-top:12px;border-top:1px solid #ffffff18;min-height:42px;color:var(--muted)}} .detail strong{{color:var(--text)}}
.hint{{position:fixed;right:18px;bottom:14px;color:#b9c7da;font-size:12px;text-shadow:0 1px 4px #000}}
@media(max-width:600px){{.panel{{top:10px;left:10px;width:calc(100vw - 20px)}}.hint{{display:none}}}}
</style>
</head>
<body>
<canvas id="plot" aria-label="Interactive 3D character relationship plot"></canvas>
<section class="panel">
  <h1>{safe_title}</h1>
  <div class="meta"><span id="counts"></span> · local 3D relationship plot</div>
  <div class="controls">
    <label class="wide">Search <input id="search" type="search" placeholder="Character or relationship"></label>
    <label>Group <select id="group"><option value="">All groups</option></select></label>
    <label>Relation <select id="relation"><option value="">All types</option></select></label>
    <label class="wide">Chapter <input id="chapter" type="range" min="1" value="1"><span id="chapterValue">1</span></label>
    <button id="reset">Reset view</button><button id="clear">Clear filters</button>
    <button id="focus" disabled>Focus selected</button><button id="export">Export PNG</button>
  </div>
  <div id="detail" class="detail">Select a character or relationship.</div>
</section>
<div class="hint">Drag to rotate · wheel to zoom · click a node or edge</div>
<script id="graph-data" type="application/json">{graph_json}</script>
<script>
const graph=JSON.parse(document.getElementById('graph-data').textContent);
const canvas=document.getElementById('plot'),ctx=canvas.getContext('2d');
const ui={{search:document.getElementById('search'),group:document.getElementById('group'),relation:document.getElementById('relation'),chapter:document.getElementById('chapter'),chapterValue:document.getElementById('chapterValue'),detail:document.getElementById('detail')}};
let rotationX=-0.18,rotationY=0.52,zoom=2.1,drag=null,projected=[],projectedEdges=[],selectedId=null,focusId=null;
const byId=Object.fromEntries(graph.characters.map(node=>[node.id,node]));
const unique=values=>[...new Set(values.filter(Boolean))].sort();
for(const value of unique(graph.characters.map(node=>node.group))) ui.group.add(new Option(value,value));
for(const value of unique(graph.relationships.map(edge=>edge.type))) ui.relation.add(new Option(value,value));
const maxChapter=Math.max(1,...graph.relationships.flatMap(edge=>[edge.visibility?.start_chapter||1,edge.visibility?.end_chapter||1]));
ui.chapter.max=maxChapter; ui.chapter.value=maxChapter; ui.chapterValue.textContent=maxChapter;
document.getElementById('counts').textContent=`${{graph.characters.length}} characters · ${{graph.relationships.length}} relationships`;
function resize(){{const ratio=devicePixelRatio||1;canvas.width=innerWidth*ratio;canvas.height=innerHeight*ratio;ctx.setTransform(ratio,0,0,ratio,0,0);draw()}}
function rotate(point){{let x=point.x,y=point.y,z=point.z;const cy=Math.cos(rotationY),sy=Math.sin(rotationY),cx=Math.cos(rotationX),sx=Math.sin(rotationX);const x1=x*cy-z*sy,z1=x*sy+z*cy;return{{x:x1,y:y*cx-z1*sx,z:y*sx+z1*cx}}}}
function project(node){{const r=rotate(node.position),depth=600+r.z,scale=zoom*600/Math.max(180,depth);return{{node,x:innerWidth/2+r.x*scale,y:innerHeight/2+r.y*scale,scale,depth:r.z}}}}
function visibleEdge(edge){{const chapter=+ui.chapter.value,start=edge.visibility?.start_chapter??1,end=edge.visibility?.end_chapter;return chapter>=start&&(end==null||chapter<=end)}}
function inFocus(id){{return!focusId||id===focusId||graph.relationships.some(edge=>visibleEdge(edge)&&(edge.source===focusId&&edge.target===id||edge.target===focusId&&edge.source===id))}}
function matchesNode(node){{const q=ui.search.value.trim().toLowerCase();return inFocus(node.id)&&(!ui.group.value||node.group===ui.group.value)&&(!q||`${{node.label}} ${{node.id}} ${{node.role}} ${{node.group}}`.toLowerCase().includes(q))}}
function draw(){{ctx.clearRect(0,0,innerWidth,innerHeight);projected=graph.characters.map(project).sort((a,b)=>a.depth-b.depth);const points=Object.fromEntries(projected.map(p=>[p.node.id,p]));projectedEdges=[];ctx.lineCap='round';
 for(const edge of graph.relationships){{if(!visibleEdge(edge)||ui.relation.value&&edge.type!==ui.relation.value)continue;if(focusId&&edge.source!==focusId&&edge.target!==focusId)continue;const a=points[edge.source],b=points[edge.target];if(!a||!b)continue;if(ui.group.value&&a.node.group!==ui.group.value&&b.node.group!==ui.group.value)continue;const q=ui.search.value.trim().toLowerCase();if(q&&!`${{edge.type}} ${{edge.notes}} ${{byId[edge.source]?.label}} ${{byId[edge.target]?.label}}`.toLowerCase().includes(q)&&!matchesNode(a.node)&&!matchesNode(b.node))continue;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.strokeStyle=edge.color+'b8';ctx.lineWidth=1+edge.strength*4;ctx.stroke();projectedEdges.push({{edge,a,b}});}}
 for(const p of projected){{if(!matchesNode(p.node))continue;const radius=Math.max(5,9*p.scale/zoom);ctx.beginPath();ctx.arc(p.x,p.y,radius,0,Math.PI*2);ctx.fillStyle=p.node.color;ctx.shadowColor=p.node.color;ctx.shadowBlur=12;ctx.fill();ctx.shadowBlur=0;ctx.fillStyle='#eef5ff';ctx.font='12px system-ui';ctx.textAlign='center';ctx.fillText(p.node.label,p.x,p.y-radius-7);}}
}}
function pointLineDistance(px,py,a,b){{const dx=b.x-a.x,dy=b.y-a.y,length=dx*dx+dy*dy;if(!length)return Infinity;const t=Math.max(0,Math.min(1,((px-a.x)*dx+(py-a.y)*dy)/length));return Math.hypot(px-(a.x+t*dx),py-(a.y+t*dy))}}
canvas.addEventListener('pointerdown',event=>{{drag={{x:event.clientX,y:event.clientY,rx:rotationX,ry:rotationY,moved:false}};canvas.setPointerCapture(event.pointerId)}});
canvas.addEventListener('pointermove',event=>{{if(!drag)return;const dx=event.clientX-drag.x,dy=event.clientY-drag.y;drag.moved=drag.moved||Math.abs(dx)+Math.abs(dy)>4;rotationY=drag.ry+dx*.006;rotationX=Math.max(-1.45,Math.min(1.45,drag.rx+dy*.006));draw()}});
canvas.addEventListener('pointerup',event=>{{if(drag&&!drag.moved)selectAt(event.clientX,event.clientY);drag=null}});
canvas.addEventListener('wheel',event=>{{event.preventDefault();zoom=Math.max(.55,Math.min(5,zoom*Math.exp(-event.deltaY*.001)));draw()}},{{passive:false}});
function selectAt(x,y){{const node=[...projected].reverse().find(p=>matchesNode(p.node)&&Math.hypot(x-p.x,y-p.y)<16);if(node){{const n=node.node;selectedId=n.id;document.getElementById('focus').disabled=false;ui.detail.innerHTML=`<strong>${{escapeHtml(n.label)}}</strong><br>${{escapeHtml([n.role,n.group,n.status].filter(Boolean).join(' · '))}}`;return}}const hit=projectedEdges.find(item=>pointLineDistance(x,y,item.a,item.b)<7);if(hit){{const e=hit.edge;ui.detail.innerHTML=`<strong>${{escapeHtml(byId[e.source].label)}} → ${{escapeHtml(byId[e.target].label)}}</strong><br>${{escapeHtml(e.type)}} · strength ${{e.strength}}${{e.notes?'<br>'+escapeHtml(e.notes):''}}`;}}}}
function escapeHtml(value){{const span=document.createElement('span');span.textContent=value??'';return span.innerHTML}}
for(const element of [ui.search,ui.group,ui.relation,ui.chapter]) element.addEventListener('input',()=>{{ui.chapterValue.textContent=ui.chapter.value;draw()}});
document.getElementById('reset').onclick=()=>{{rotationX=-.18;rotationY=.52;zoom=2.1;draw()}};
document.getElementById('clear').onclick=()=>{{ui.search.value='';ui.group.value='';ui.relation.value='';ui.chapter.value=maxChapter;ui.chapterValue.textContent=maxChapter;focusId=null;document.getElementById('focus').textContent='Focus selected';draw()}};
document.getElementById('focus').onclick=event=>{{focusId=focusId?null:selectedId;event.currentTarget.textContent=focusId?'Show all':'Focus selected';draw()}};
document.getElementById('export').onclick=()=>{{draw();const link=document.createElement('a');link.download='relationship-plot.png';link.href=canvas.toDataURL('image/png');link.click()}};
addEventListener('resize',resize);resize();
</script>
</body>
</html>
"""
