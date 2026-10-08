"""Swimlanes, columns and positions (M10 "Swimlanes" and "Layout"). Port of tools/render_flow.py; parity is tested.

Styles in STYLE are normative (M10). Iteration and sort orders matter: they make the output byte-identical.
"""
import html
import re

from ir_core.graph import adjacency, live

AUTO = "lane_automation"
AUTO_LABEL = "Automated (AI agents & systems)"

# One style per control type. Colour is never the only signal: every label also states what the shape is.
STYLE = {
    "lane": "rounded=0;whiteSpace=wrap;html=1;fillColor=#FAFAFA;strokeColor=#C8C8C8;",
    "lane_head": "rounded=0;whiteSpace=wrap;html=1;fillColor=#EDEDED;strokeColor=#C8C8C8;fontStyle=1;fontSize=12;",
    "start": "ellipse;whiteSpace=wrap;html=1;fillColor=#D5E8D4;strokeColor=#82B366;fontSize=10;",
    "end": "ellipse;shape=doubleEllipse;whiteSpace=wrap;html=1;fillColor=#D5E8D4;strokeColor=#82B366;fontSize=10;",
    "automated": "rounded=1;whiteSpace=wrap;html=1;fillColor=#DAE8FC;strokeColor=#6C8EBF;fontSize=11;",
    "hitl_review": "rounded=1;whiteSpace=wrap;html=1;fillColor=#FFE6CC;strokeColor=#D79B00;strokeWidth=3;fontSize=11;",
    "human_task": "rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#4D4D4D;strokeWidth=2;fontSize=11;",
    "approval": "shape=hexagon;perimeter=hexagonPerimeter2;whiteSpace=wrap;html=1;size=0.12;fillColor=#F8CECC;"
                "strokeColor=#B85450;strokeWidth=3;fontSize=11;",
    "unset": "rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#999999;dashed=1;fontSize=11;",
    "decision": "rhombus;whiteSpace=wrap;html=1;fillColor=#FFF2CC;strokeColor=#D6B656;fontSize=10;",
    "wait": "rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F5F5;strokeColor=#999999;dashed=1;fontSize=11;",
    "event": "ellipse;whiteSpace=wrap;html=1;fillColor=#F5F5F5;strokeColor=#999999;fontSize=10;",
    "queue": "rounded=1;whiteSpace=wrap;html=1;fillColor=#FFE6CC;strokeColor=#D79B00;dashed=1;strokeWidth=2;"
             "fontSize=10;",
    "edge": "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;fontSize=10;",
    "edge_reject": "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;strokeColor=#B85450;"
                   "fontColor=#B85450;fontSize=10;",
    "edge_route": "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=open;dashed=1;strokeColor=#7F7F7F;"
                  "fontColor=#7F7F7F;fontSize=10;",
    "edge_queue": "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=open;dashed=1;strokeColor=#D79B00;"
                  "fontColor=#B07800;fontSize=10;",
    "legend": "rounded=0;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#C8C8C8;align=left;verticalAlign=top;"
              "spacingLeft=8;spacingTop=4;fontSize=10;",
    "title": "text;html=1;fontSize=16;fontStyle=1;align=left;verticalAlign=middle;",
}
SIZE = {"start": (60, 60), "end": (64, 64), "decision": (120, 80), "approval": (170, 80), "queue": (160, 56),
        "event": (60, 60), "default": (160, 64)}
COL_W, ROW_H, HEAD_W, PAD_X, PAD_Y, TOP = 200, 110, 140, 30, 25, 70
VARIANT_TITLE = {"as_is": "as-is (today)", "to_be": "to-be (improved)"}
DURATION = re.compile(r"P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?")


def human_duration(d: str | None, calendar: str | None = None) -> str | None:
    """P10D + working_days → '10 working days'; PT4H → '4 hours'. Anything else is returned unchanged."""
    m = DURATION.fullmatch(d or "")
    if not m:
        return d
    w, dd, h, mi = (int(x) if x else 0 for x in m.groups())
    unit = "working day" if calendar == "working_days" else "day"
    parts = []
    if w:
        parts.append(f"{w} week{'s' * (w != 1)}")
    if dd:
        parts.append(f"{dd} {unit}{'s' * (dd != 1)}")
    if h:
        parts.append(f"{h} hour{'s' * (h != 1)}")
    if mi:
        parts.append(f"{mi} minute{'s' * (mi != 1)}")
    return " ".join(parts) or d


def control(ir: dict, nid: str) -> str:
    """A task's hitl mode ('unset' when missing); for other nodes, their type."""
    n = ir["nodes"][nid]
    if n["type"] != "task":
        return n["type"]
    return n.get("hitl", {}).get("mode") or "unset"


def lane_of(ir: dict, nid: str, cache: dict) -> str | None:
    if nid in cache:
        return cache[nid]
    n = ir["nodes"][nid]
    c = control(ir, nid)
    edges = live(ir, "edges").values()
    if c in ("wait", "decision") and ir["process"].get("variant") == "as_is":
        # Nothing is automated today: waits and rule decisions sit with whoever does the step before them.
        preds = sorted(e["from"] for e in edges if e["to"] == nid and ir["nodes"][e["from"]]["type"] == "task")
        if preds:
            cache[nid] = lane_of(ir, preds[0], cache)
            return cache[nid]
    if c in ("human_task", "approval", "unset"):
        lane = n.get("actor_id") or AUTO
    elif c in ("automated", "hitl_review", "wait", "event"):
        lane = AUTO
    elif c == "decision":
        kinds = {ir["decision_rules"][r]["logic"]["kind"] for r in n.get("rule_ids", []) if r in ir["decision_rules"]}
        if kinds and kinds <= {"table", "expression"}:
            lane = AUTO
        else:  # a judgement call sits with whoever made the preceding step
            preds = sorted(e["from"] for e in edges if e["to"] == nid)
            lane = lane_of(ir, preds[0], cache) if preds else AUTO
    else:
        lane = None  # start/end are resolved from their neighbours
    cache[nid] = lane
    return lane


def annotation(ir: dict, nid: str) -> str:
    """As-is: effort and the first pain point. To-be: which accepted suggestion changed the step."""
    n = ir["nodes"][nid]
    out = []
    if n.get("change"):
        ch = n["change"]
        was = {"human_task": "manual", "automated": "automated", "hitl_review": "reviewed",
               "approval": "approval"}.get(ch.get("was"), ch.get("was") or "")
        out.append(f"<i>Changed by {ch['suggestion_id']}" + (f": was {html.escape(was)}" if was else "") + "</i>")
    elif ir["process"].get("variant") == "as_is":
        effort = n.get("as_is_effort", {})
        if effort.get("minutes_per_case") is not None:
            out.append(f"<i>~{effort['minutes_per_case']:g} min per case</i>")
        if effort.get("pain_points"):
            out.append(f"<i>PAIN: {html.escape(effort['pain_points'][0])}</i>")
    return "".join("<br>" + x for x in out)


def label(ir: dict, nid: str) -> str:
    return label_core(ir, nid) + (annotation(ir, nid) if ir["nodes"][nid]["type"] == "task" else "")


def label_core(ir: dict, nid: str) -> str:
    n, c = ir["nodes"][nid], control(ir, nid)
    name = html.escape(n["name"])
    h = n.get("hitl", {})

    def actor(a):
        return html.escape(ir["actors"][a]["name"]) if a in ir["actors"] else "?"

    if c == "automated":
        return f"<b>[AUTO]</b><br>{name}"
    if c == "hitl_review":
        when = {"always": "every item", "on_exception": "on exceptions", "low_confidence": "low confidence",
                "sample": "sample"}.get(h.get("trigger"), "")
        return f"<b>[AUTO + HUMAN REVIEW]</b><br>{name}<br><i>Reviewed by {actor(h.get('actor_id'))} ({when})</i>"
    if c == "human_task":
        return f"<b>[HUMAN]</b><br>{name}"
    if c == "approval":
        return f"<b>APPROVAL GATE</b><br>{name}<br><i>Approver: {actor(h.get('actor_id'))}</i>"
    if c == "unset":
        return f"<b>[CONTROL NOT SET]</b><br>{name}"
    if c == "wait":
        slas = [ir["slas"][s] for s in n.get("sla_ids", []) if s in ir["slas"]]
        due = (f"<br><i>Due within {html.escape(human_duration(slas[0]['duration'], slas[0].get('calendar')))}</i>"
               if slas else "")
        return f"<b>[WAIT]</b><br>{name}{due}"
    return name


def layout_columns(ir: dict) -> dict[str, int]:
    """Column = shortest distance from start over edges and exception/SLA routes; unreachable nodes go last."""
    nodes = live(ir, "nodes")
    adj = adjacency(ir)
    starts = sorted(k for k, n in nodes.items() if n["type"] == "start")
    col, queue = {s: 0 for s in starts}, list(starts)
    while queue:
        x = queue.pop(0)
        for y in sorted(adj.get(x, ())):
            if y not in col:
                col[y] = col[x] + 1
                queue.append(y)
    for k in sorted(nodes):
        col.setdefault(k, max(col.values(), default=0) + 1)
    return col


def main_path(ir: dict) -> set[str]:
    """Shortest start→end path over sequence edges (ties broken by id): the happy path drawn on the top row."""
    nodes = live(ir, "nodes")
    adj: dict[str, list[str]] = {}
    for e in sorted(live(ir, "edges").values(), key=lambda e: (e["from"], e["to"])):
        adj.setdefault(e["from"], []).append(e["to"])
    starts = sorted(k for k, n in nodes.items() if n["type"] == "start")
    ends = {k for k, n in nodes.items() if n["type"] == "end"}
    parent, queue = {s: None for s in starts}, list(starts)
    while queue:
        x = queue.pop(0)
        if x in ends:
            path = set()
            while x is not None:
                path.add(x)
                x = parent[x]
            return path
        for y in adj.get(x, []):
            if y not in parent:
                parent[y] = x
                queue.append(y)
    return set()


def lane_name(ir: dict, lane: str) -> str:
    return AUTO_LABEL if lane == AUTO else ir["actors"][lane]["name"]


def edge_list(ir: dict) -> list[tuple[str, str, str, str, str]]:
    """(id, source, target, label, kind) in flow order; kind: flow | reject | route."""
    out = []
    for eid, e in sorted(live(ir, "edges").items()):
        outcome = (e.get("condition") or {}).get("outcome")
        text = e.get("label") or (outcome.replace("_", " ").capitalize() if outcome else "")
        out.append((eid, e["from"], e["to"], text, "reject" if outcome == "rejected" else "flow"))
    for xid, x in sorted(live(ir, "exceptions").items()):
        target = x["handling"].get("target_node_id")
        if x["handling"]["action"] == "route_to_node" and target:
            for n in x["applies_to"]:
                out.append((f"route_{xid}_{n}", n, target, f"Exception: {x['name']}", "route"))
    for sid, s in sorted(live(ir, "slas").items()):
        target = s["breach_action"].get("target_node_id")
        if s["breach_action"]["action"] == "route_to_node" and target:
            for n in s["applies_to"]:
                due = human_duration(s["duration"], s.get("calendar"))
                out.append((f"route_{sid}_{n}", n, target, f"Overdue (SLA {due})", "route"))
    # Flow order (by column of source, then target) gives Lucid/Mermaid auto-layout a left-to-right reading.
    col = layout_columns(ir)
    return sorted(out, key=lambda e: (col.get(e[1], 0), col.get(e[2], 0), e[0]))


def layout(ir: dict) -> dict:
    nodes = live(ir, "nodes")
    adj = adjacency(ir)
    col = layout_columns(ir)
    cache: dict[str, str | None] = {}
    lanes = {k: lane_of(ir, k, cache) for k in nodes}
    preds: dict[str, list[str]] = {}
    for e in live(ir, "edges").values():
        preds.setdefault(e["to"], []).append(e["from"])
    for k, n in nodes.items():  # start/end take a neighbour's lane
        if lanes[k] is None:
            neighbours = sorted(adj.get(k, ())) if n["type"] == "start" else sorted(preds.get(k, []))
            lanes[k] = next((lanes[x] for x in neighbours if lanes.get(x)), AUTO)

    # Human queues: exceptions that hand work to a person, drawn in that person's lane.
    queues = []
    for xid, x in sorted(live(ir, "exceptions").items()):
        if x["handling"]["action"] in ("manual_review", "escalate"):
            src = x["applies_to"][0]
            queues.append({"id": f"queue_{xid}", "exception": xid, "lane": x["handling"].get("notify_actor_id") or AUTO,
                           "src": src, "col": col.get(src, 0)})

    # Lane order: human lanes by the first column they appear in, the automation lane last.
    first: dict[str, int] = {}
    for k in nodes:
        first[lanes[k]] = min(first.get(lanes[k], 10**6), col[k])
    for q in queues:
        first[q["lane"]] = min(first.get(q["lane"], 10**6), q["col"])
    order = sorted((ln for ln in first if ln != AUTO), key=lambda ln: (first[ln], ln))
    order += [AUTO] if AUTO in first else []

    # Items sharing a (lane, column) stack: the main start→end path takes the top row, branches go below.
    main = main_path(ir)
    slots: dict[tuple, list] = {}
    for k in sorted(nodes, key=lambda k: (col[k], k not in main, k)):
        slots.setdefault((lanes[k], col[k]), []).append(k)
    for q in queues:
        slots.setdefault((q["lane"], q["col"]), []).append(q["id"])
    rows = {ln: max([len(v) for (lane, _), v in slots.items() if lane == ln] or [1]) for ln in order}
    lane_y, y = {}, TOP
    for ln in order:
        lane_y[ln] = y
        y += rows[ln] * ROW_H + 2 * PAD_Y
    pos = {}
    for (ln, c), items in slots.items():
        for i, k in enumerate(items):
            kind = "queue" if k.startswith("queue_") else (control(ir, k) if k in nodes else "default")
            w, h = SIZE.get(kind, SIZE["default"])
            if k in nodes and nodes[k]["type"] == "task" and annotation(ir, k):
                h += 16 * annotation(ir, k).count("<br>")
            cx = HEAD_W + PAD_X + c * COL_W + 80
            cy = lane_y[ln] + PAD_Y + i * ROW_H + ROW_H / 2 - 10
            pos[k] = (round(cx - w / 2), round(cy - h / 2), w, h)
    width = HEAD_W + PAD_X * 2 + (max(col.values(), default=0) + 1) * COL_W
    return {"col": col, "lanes": lanes, "order": order, "lane_y": lane_y, "rows": rows, "pos": pos,
            "queues": queues, "width": width, "height": y}
