#!/usr/bin/env python3
"""Reference renderer for the process-flow diagram (M10): Process IR -> draw.io XML (Lucidchart import) + Mermaid.

Deterministic: the same IR always produces byte-identical files.
Usage: python tools/render_flow.py <ir.json> <out_dir>     -> <out_dir>/<variant>_process_flow.drawio and .mmd

Lucidchart: File > Import > draw.io (.drawio/.xml) gives editable shapes. The .mmd file is for Lucid's
diagram-as-code (Mermaid) panel, GitHub and docs; Lucid renders it, but not as draggable shapes.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rs_reference as R  # noqa: E402

AUTO = "lane_automation"
AUTO_LABEL = "Automated (AI agents & systems)"

# ---- styles: one per control type; colour is never the only signal (every label also says what it is)
STYLE = {
    "lane": "rounded=0;whiteSpace=wrap;html=1;fillColor=#FAFAFA;strokeColor=#C8C8C8;",
    "lane_head": "rounded=0;whiteSpace=wrap;html=1;fillColor=#EDEDED;strokeColor=#C8C8C8;fontStyle=1;fontSize=12;",
    "start": "ellipse;whiteSpace=wrap;html=1;fillColor=#D5E8D4;strokeColor=#82B366;fontSize=10;",
    "end": "ellipse;shape=doubleEllipse;whiteSpace=wrap;html=1;fillColor=#D5E8D4;strokeColor=#82B366;fontSize=10;",
    "automated": "rounded=1;whiteSpace=wrap;html=1;fillColor=#DAE8FC;strokeColor=#6C8EBF;fontSize=11;",
    "hitl_review": "rounded=1;whiteSpace=wrap;html=1;fillColor=#FFE6CC;strokeColor=#D79B00;strokeWidth=3;fontSize=11;",
    "human_task": "rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#4D4D4D;strokeWidth=2;fontSize=11;",
    "approval": "shape=hexagon;perimeter=hexagonPerimeter2;whiteSpace=wrap;html=1;size=0.12;fillColor=#F8CECC;strokeColor=#B85450;strokeWidth=3;fontSize=11;",
    "unset": "rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#999999;dashed=1;fontSize=11;",
    "decision": "rhombus;whiteSpace=wrap;html=1;fillColor=#FFF2CC;strokeColor=#D6B656;fontSize=10;",
    "wait": "rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F5F5;strokeColor=#999999;dashed=1;fontSize=11;",
    "event": "ellipse;whiteSpace=wrap;html=1;fillColor=#F5F5F5;strokeColor=#999999;fontSize=10;",
    "queue": "rounded=1;whiteSpace=wrap;html=1;fillColor=#FFE6CC;strokeColor=#D79B00;dashed=1;strokeWidth=2;fontSize=10;",
    "edge": "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;fontSize=10;",
    "edge_reject": "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;strokeColor=#B85450;fontColor=#B85450;fontSize=10;",
    "edge_route": "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=open;dashed=1;strokeColor=#7F7F7F;fontColor=#7F7F7F;fontSize=10;",
    "edge_queue": "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=open;dashed=1;strokeColor=#D79B00;fontColor=#B07800;fontSize=10;",
    "legend": "rounded=0;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#C8C8C8;align=left;verticalAlign=top;spacingLeft=8;spacingTop=4;fontSize=10;",
    "title": "text;html=1;fontSize=16;fontStyle=1;align=left;verticalAlign=middle;",
}
SIZE = {"start": (60, 60), "end": (64, 64), "decision": (120, 80), "approval": (170, 80), "queue": (160, 56),
        "event": (60, 60), "default": (160, 64)}
COL_W, ROW_H, HEAD_W, PAD_X, PAD_Y, TOP = 200, 110, 140, 30, 25, 70


def human_duration(d, calendar=None):
    """P10D + working_days -> '10 working days'; PT4H -> '4 hours'."""
    import re
    m = re.fullmatch(r"P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", d or "")
    if not m:
        return d
    w, dd, h, mi = (int(x) if x else 0 for x in m.groups())
    unit = "working day" if calendar == "working_days" else "day"
    parts = []
    if w: parts.append(f"{w} week{'s' * (w != 1)}")
    if dd: parts.append(f"{dd} {unit}{'s' * (dd != 1)}")
    if h: parts.append(f"{h} hour{'s' * (h != 1)}")
    if mi: parts.append(f"{mi} minute{'s' * (mi != 1)}")
    return " ".join(parts) or d


def control(ir, nid):
    n = ir["nodes"][nid]
    if n["type"] != "task":
        return n["type"]
    return n.get("hitl", {}).get("mode") or "unset"


def lane_of(ir, nid, cache):
    if nid in cache:
        return cache[nid]
    n = ir["nodes"][nid]
    c = control(ir, nid)
    if c in ("wait", "decision") and ir["process"].get("variant") == "as_is":
        # nothing is automated today: waits and rule decisions sit with whoever does the step before them
        preds = sorted(e["from"] for e in R.live(ir, "edges").values() if e["to"] == nid and ir["nodes"][e["from"]]["type"] == "task")
        if preds:
            lane = lane_of(ir, preds[0], cache)
            cache[nid] = lane
            return lane
    if c in ("human_task", "approval", "unset"):
        lane = n.get("actor_id") or AUTO
    elif c in ("automated", "hitl_review", "wait", "event"):
        lane = AUTO
    elif c == "decision":
        kinds = {ir["decision_rules"][r]["logic"]["kind"] for r in n.get("rule_ids", []) if r in ir["decision_rules"]}
        if kinds and kinds <= {"table", "expression"}:
            lane = AUTO
        else:  # a judgement call sits with whoever made the preceding step
            preds = sorted(e["from"] for e in R.live(ir, "edges").values() if e["to"] == nid)
            lane = lane_of(ir, preds[0], cache) if preds else AUTO
    else:
        lane = None  # start/end resolved by neighbours
    cache[nid] = lane
    return lane


def _annotation(ir, nid):
    """As-is: effort + pain point. To-be: which accepted suggestion changed the step."""
    n = ir["nodes"][nid]
    out = []
    if n.get("change"):
        ch = n["change"]
        was = {"human_task": "manual", "automated": "automated", "hitl_review": "reviewed", "approval": "approval"}.get(ch.get("was"), ch.get("was") or "")
        out.append(f"<i>Changed by {ch['suggestion_id']}" + (f": was {html.escape(was)}" if was else "") + "</i>")
    elif ir["process"].get("variant") == "as_is":
        eff = n.get("as_is_effort", {})
        if eff.get("minutes_per_case") is not None:
            out.append(f"<i>~{eff['minutes_per_case']:g} min per case</i>")
        if eff.get("pain_points"):
            out.append(f"<i>PAIN: {html.escape(eff['pain_points'][0])}</i>")
    return "".join("<br>" + x for x in out)


def _label(ir, nid):
    return _label_core(ir, nid) + (_annotation(ir, nid) if ir["nodes"][nid]["type"] == "task" else "")


def _label_core(ir, nid):
    n, c = ir["nodes"][nid], control(ir, nid)
    name = html.escape(n["name"])
    actor = lambda a: html.escape(ir["actors"][a]["name"]) if a in ir["actors"] else "?"
    h = n.get("hitl", {})
    if c == "automated":
        return f"<b>[AUTO]</b><br>{name}"
    if c == "hitl_review":
        trig = {"always": "every item", "on_exception": "on exceptions", "low_confidence": "low confidence", "sample": "sample"}.get(h.get("trigger"), "")
        return f"<b>[AUTO + HUMAN REVIEW]</b><br>{name}<br><i>Reviewed by {actor(h.get('actor_id'))} ({trig})</i>"
    if c == "human_task":
        return f"<b>[HUMAN]</b><br>{name}"
    if c == "approval":
        return f"<b>APPROVAL GATE</b><br>{name}<br><i>Approver: {actor(h.get('actor_id'))}</i>"
    if c == "unset":
        return f"<b>[CONTROL NOT SET]</b><br>{name}"
    if c == "wait":
        sl = [ir["slas"][s] for s in n.get("sla_ids", []) if s in ir["slas"]]
        extra = f"<br><i>Due within {html.escape(human_duration(sl[0]['duration'], sl[0].get('calendar')))}</i>" if sl else ""
        return f"<b>[WAIT]</b><br>{name}{extra}"
    return name


def layout(ir):
    nodes = R.live(ir, "nodes")
    adj = R.adjacency(ir)
    col = layout_columns(ir)  # column = shortest distance from start over edges + exception/SLA routes
    cache: dict[str, str | None] = {}
    lanes = {k: lane_of(ir, k, cache) for k in nodes}
    preds = {}
    for e in R.live(ir, "edges").values():
        preds.setdefault(e["to"], []).append(e["from"])
    for k, n in nodes.items():  # start/end take a neighbour's lane
        if lanes[k] is None:
            nb = sorted(adj.get(k, ())) if n["type"] == "start" else sorted(preds.get(k, []))
            lanes[k] = next((lanes[x] for x in nb if lanes.get(x)), AUTO)
    # HITL queues: exceptions that hand work to a person, drawn in that person's lane
    queues = []
    for xid, x in sorted(R.live(ir, "exceptions").items()):
        if x["handling"]["action"] in ("manual_review", "escalate") and x["handling"].get("action") != "route_to_node":
            owner = x["handling"].get("notify_actor_id") or AUTO
            src = x["applies_to"][0]
            queues.append({"id": f"queue_{xid}", "exception": xid, "lane": owner, "src": src, "col": col.get(src, 0)})
    # lane order: human lanes by first column they appear in, automation lane last
    first: dict[str, int] = {}
    for k in nodes:
        first[lanes[k]] = min(first.get(lanes[k], 10**6), col[k])
    for qd in queues:
        first[qd["lane"]] = min(first.get(qd["lane"], 10**6), qd["col"])
    order = sorted((l for l in first if l != AUTO), key=lambda l: (first[l], l)) + ([AUTO] if AUTO in first else [])
    # stack items sharing a (lane, column): the main start→end path takes the top row, branches go below
    main = main_path(ir)
    slots: dict[tuple, list] = {}
    for k in sorted(nodes, key=lambda k: (col[k], k not in main, k)):
        slots.setdefault((lanes[k], col[k]), []).append(k)
    for qd in queues:
        slots.setdefault((qd["lane"], qd["col"]), []).append(qd["id"])
    rows = {l: max([len(v) for (ln, _), v in slots.items() if ln == l] or [1]) for l in order}
    lane_y, y = {}, TOP
    for l in order:
        lane_y[l] = y; y += rows[l] * ROW_H + 2 * PAD_Y
    pos = {}
    for (l, c), items in slots.items():
        for i, k in enumerate(items):
            kind = "queue" if k.startswith("queue_") else (control(ir, k) if k in nodes else "default")
            w, h = SIZE.get(kind, SIZE["default"])
            if k in nodes and nodes[k]["type"] == "task" and _annotation(ir, k):
                h += 16 * _annotation(ir, k).count("<br>")
            cx = HEAD_W + PAD_X + c * COL_W + 80
            cy = lane_y[l] + PAD_Y + i * ROW_H + ROW_H / 2 - 10
            pos[k] = (round(cx - w / 2), round(cy - h / 2), w, h)
    width = HEAD_W + PAD_X * 2 + (max(col.values(), default=0) + 1) * COL_W
    return {"col": col, "lanes": lanes, "order": order, "lane_y": lane_y, "rows": rows, "pos": pos,
            "queues": queues, "width": width, "height": y}


def main_path(ir) -> set[str]:
    """Shortest start→end path over sequence edges (ties broken by id) — the happy path drawn on the top row."""
    nodes = R.live(ir, "nodes")
    adj: dict[str, list[str]] = {}
    for e in sorted(R.live(ir, "edges").values(), key=lambda e: (e["from"], e["to"])):
        adj.setdefault(e["from"], []).append(e["to"])
    starts = sorted(k for k, n in nodes.items() if n["type"] == "start")
    ends = {k for k, n in nodes.items() if n["type"] == "end"}
    parent, q = {s: None for s in starts}, list(starts)
    while q:
        x = q.pop(0)
        if x in ends:
            path = set()
            while x is not None:
                path.add(x); x = parent[x]
            return path
        for y in adj.get(x, []):
            if y not in parent:
                parent[y] = x; q.append(y)
    return set()


def lane_name(ir, l):
    return AUTO_LABEL if l == AUTO else ir["actors"][l]["name"]


def edge_list(ir):
    """(id, source, target, label, kind) — kind: flow | reject | route | queue."""
    out = []
    for eid, e in sorted(R.live(ir, "edges").items()):
        oc = (e.get("condition") or {}).get("outcome")
        lab = e.get("label") or (oc.replace("_", " ").capitalize() if oc else "")
        out.append((eid, e["from"], e["to"], lab, "reject" if oc == "rejected" else "flow"))
    for xid, x in sorted(R.live(ir, "exceptions").items()):
        t = x["handling"].get("target_node_id")
        if x["handling"]["action"] == "route_to_node" and t:
            for n in x["applies_to"]:
                out.append((f"route_{xid}_{n}", n, t, f"Exception: {x['name']}", "route"))
    for sid, s in sorted(R.live(ir, "slas").items()):
        t = s["breach_action"].get("target_node_id")
        if s["breach_action"]["action"] == "route_to_node" and t:
            for n in s["applies_to"]:
                out.append((f"route_{sid}_{n}", n, t, f"Overdue (SLA {human_duration(s['duration'], s.get('calendar'))})", "route"))
    # flow order (by column of source, then target) gives the auto-layout in Lucid/Mermaid a left-to-right reading
    col = layout_columns(ir)
    return sorted(out, key=lambda e: (col.get(e[1], 0), col.get(e[2], 0), e[0]))


def layout_columns(ir):
    nodes = R.live(ir, "nodes")
    adj = R.adjacency(ir)
    starts = sorted(k for k, n in nodes.items() if n["type"] == "start")
    col, q = {s: 0 for s in starts}, list(starts)
    while q:
        x = q.pop(0)
        for y in sorted(adj.get(x, ())):
            if y not in col:
                col[y] = col[x] + 1; q.append(y)
    for k in sorted(nodes):
        col.setdefault(k, max(col.values(), default=0) + 1)
    return col


def render_drawio(ir) -> str:
    L = layout(ir)
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']

    def vertex(cid, value, style, x, y, w, h):
        cells.append(f'<mxCell id="{cid}" value="{html.escape(value, quote=True)}" style="{style}" vertex="1" parent="1">'
                     f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')

    def edge(cid, src, tgt, value, style):
        cells.append(f'<mxCell id="{cid}" value="{html.escape(value, quote=True)}" style="{style}" edge="1" parent="1" '
                     f'source="{src}" target="{tgt}"><mxGeometry relative="1" as="geometry"/></mxCell>')

    vt = {"as_is": "as-is (today)", "to_be": "to-be (improved)"}.get(ir["process"].get("variant"), "")
    vertex("title", f"{ir['process']['name']} — {vt} process flow (IR v{ir['process']['version']})", STYLE["title"], 0, 10, L["width"], 40)
    for l in L["order"]:
        h = L["rows"][l] * ROW_H + 2 * PAD_Y
        vertex(f"lane_{l}", "", STYLE["lane"], 0, L["lane_y"][l], L["width"], h)
        vertex(f"lanehead_{l}", html.escape(lane_name(ir, l)), STYLE["lane_head"], 0, L["lane_y"][l], HEAD_W, h)
    for k in sorted(R.live(ir, "nodes")):
        x, y, w, h = L["pos"][k]
        c = control(ir, k)
        vertex(k, _label(ir, k), STYLE.get(c, STYLE["automated"]), x, y, w, h)
    for qd in L["queues"]:
        x, y, w, h = L["pos"][qd["id"]]
        ex = ir["exceptions"][qd["exception"]]
        who = html.escape(lane_name(ir, qd["lane"]))
        vertex(qd["id"], f"<b>HUMAN QUEUE</b><br>{html.escape(ex['name'])}<br><i>{who}</i>", STYLE["queue"], x, y, w, h)
    for eid, s, t, lab, kind in edge_list(ir):
        edge(eid, s, t, lab, {"flow": STYLE["edge"], "reject": STYLE["edge_reject"], "route": STYLE["edge_route"]}[kind])
    for qd in L["queues"]:
        edge(f"edge_{qd['id']}", qd["src"], qd["id"], "Exception", STYLE["edge_queue"])
    legend = ("<b>Legend</b><br>[AUTO] blue: automated, no person<br>[AUTO + HUMAN REVIEW] amber, thick border: AI does it, a named "
              "person checks before it takes effect<br>[HUMAN] white: a person does it<br>APPROVAL GATE red hexagon: named approver "
              "approves or rejects; red arrow = rejected path<br>HUMAN QUEUE amber dashed: exceptions handed to a person<br>"
              "Dashed grey arrow: exception or SLA route<br>To-be: 'Changed by Sxx' = accepted AI improvement suggestion; "
              "as-is: minutes per case and PAIN = where time goes today")
    vertex("legend", legend, STYLE["legend"], 0, L["height"] + 20, 620, 140)
    body = "".join(cells)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<mxfile host="requirements-studio" type="device"><diagram id="{ir["process"]["id"]}" name="Process flow">'
            f'<mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" page="1" pageScale="1" '
            f'pageWidth="{L["width"]}" pageHeight="{L["height"] + 160}" math="0" shadow="0"><root>{body}</root></mxGraphModel>'
            '</diagram></mxfile>\n')


def _mq(s):  # Mermaid-safe quoted label
    return s.replace('"', "#quot;")


def render_mermaid(ir) -> str:
    L = layout(ir)
    nodes = R.live(ir, "nodes")
    vt = {"as_is": "as-is (today)", "to_be": "to-be (improved)"}.get(ir["process"].get("variant"), "")
    out = [f"%% {ir['process']['name']} — {vt} process flow (IR v{ir['process']['version']}). Generated by Requirements Studio M10; do not edit.",
           "%% Legend: [AUTO] automated · [AUTO + HUMAN REVIEW] reviewed by a named person · [HUMAN] person does it ·",
           "%% APPROVAL GATE hexagon (rejected path in red) · HUMAN QUEUE exceptions handed to a person · dashed = exception/SLA route",
           "flowchart LR"]
    plain = lambda s: html.unescape(s).replace("<br>", "<br/>").replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("~", "about ")
    for l in L["order"]:
        out.append(f'  subgraph {l.replace("act_", "lane_") if l != AUTO else AUTO}["{_mq(lane_name(ir, l))}"]')
        out.append("    direction LR")
        for k in sorted((k for k in nodes if L["lanes"][k] == l), key=lambda k: (L["col"][k], k)):
            t, lab = nodes[k]["type"], _mq(plain(_label(ir, k)))
            c = control(ir, k)
            shape = {"start": f'(("{lab}"))', "end": f'((("{lab}")))', "decision": f'{{"{lab}"}}',
                     "approval": f'{{{{"{lab}"}}}}', "wait": f'(["{lab}"])', "event": f'(("{lab}"))'}.get(c if c in ("approval",) else t, f'["{lab}"]')
            out.append(f"    {k}{shape}")
        for qd in (q for q in L["queues"] if q["lane"] == l):
            ex = ir["exceptions"][qd["exception"]]
            out.append(f'    {qd["id"]}["HUMAN QUEUE<br/>{_mq(ex["name"])}<br/>{_mq(lane_name(ir, l))}"]')
        out.append("  end")
    rej, route, q_links = [], [], []
    for i, (eid, s, t, lab, kind) in enumerate(edge_list(ir)):
        arrow = "-->" if kind in ("flow", "reject") else "-.->"
        out.append(f'  {s} {arrow}' + (f'|"{_mq(lab)}"|' if lab else "") + f" {t}")
        if kind == "reject":
            rej.append(i)
    n_edges = len(edge_list(ir))
    for j, qd in enumerate(L["queues"]):
        out.append(f'  {qd["src"]} -.->|"Exception"| {qd["id"]}')
        q_links.append(n_edges + j)
    out += ["  classDef auto fill:#DAE8FC,stroke:#6C8EBF,color:#1F2D3D",
            "  classDef review fill:#FFE6CC,stroke:#D79B00,stroke-width:3px,color:#3D2A00",
            "  classDef human fill:#FFFFFF,stroke:#4D4D4D,stroke-width:2px,color:#1A1A1A",
            "  classDef approval fill:#F8CECC,stroke:#B85450,stroke-width:3px,color:#3D0F0E",
            "  classDef unset fill:#FFFFFF,stroke:#999999,stroke-dasharray:4 3,color:#333333",
            "  classDef decision fill:#FFF2CC,stroke:#D6B656,color:#3D3000",
            "  classDef wait fill:#F5F5F5,stroke:#999999,stroke-dasharray:4 3,color:#333333",
            "  classDef queue fill:#FFE6CC,stroke:#D79B00,stroke-dasharray:4 3,color:#3D2A00",
            "  classDef terminal fill:#D5E8D4,stroke:#82B366,color:#1E3D1D"]
    for l in L["order"]:
        out.append(f"  style {l.replace('act_', 'lane_') if l != AUTO else AUTO} fill:#FAFAFA,stroke:#C8C8C8,color:#333333")
    groups: dict[str, list[str]] = {}
    for k in sorted(nodes):
        c = control(ir, k)
        cls = {"automated": "auto", "hitl_review": "review", "human_task": "human", "approval": "approval", "unset": "unset",
               "decision": "decision", "wait": "wait", "event": "wait", "start": "terminal", "end": "terminal"}[c]
        groups.setdefault(cls, []).append(k)
    if L["queues"]:
        groups["queue"] = [q["id"] for q in L["queues"]]
    for cls in sorted(groups):
        out.append(f"  class {','.join(groups[cls])} {cls}")
    if rej:
        out.append(f"  linkStyle {','.join(map(str, rej))} stroke:#B85450,color:#B85450")
    if q_links:
        out.append(f"  linkStyle {','.join(map(str, q_links))} stroke:#D79B00")
    return "\n".join(out) + "\n"


def hitl_summary(ir) -> list[dict]:
    """Every human touchpoint, for the stories header and the M9 package."""
    rows = []
    for k, n in R.live(ir, "nodes").items():
        if n["type"] != "task":
            continue
        h = n.get("hitl", {})
        if h.get("mode") in ("hitl_review", "human_task", "approval"):
            rows.append({"node_id": k, "step": n["name"], "control": h["mode"],
                         "who": ir["actors"].get(h.get("actor_id") or n.get("actor_id"), {}).get("name"),
                         "when": h.get("trigger") or "always", "criteria": h.get("criteria")})
    for xid, x in R.live(ir, "exceptions").items():
        if x["handling"]["action"] in ("manual_review", "escalate"):
            rows.append({"node_id": x["applies_to"][0], "step": f"Exception: {x['name']}", "control": "human_queue",
                         "who": ir["actors"].get(x["handling"].get("notify_actor_id"), {}).get("name"), "when": "on_exception",
                         "criteria": x["handling"].get("notes")})
    order = {k: i for i, k in enumerate(R.bfs_distance(ir))}
    dist = R.bfs_distance(ir)
    return sorted(rows, key=lambda r: (dist.get(r["node_id"], 10**6), r["node_id"], r["step"]))


def main():
    ir = json.loads(Path(sys.argv[1]).read_text())
    out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    v = ir["process"].get("variant", "to_be")
    (out / f"{v}_process_flow.drawio").write_text(render_drawio(ir))
    (out / f"{v}_process_flow.mmd").write_text(render_mermaid(ir))
    print(f"wrote {out}/{v}_process_flow.drawio and .mmd")


if __name__ == "__main__":
    main()
