"""draw.io (mxGraph XML) for Lucidchart import as editable shapes (M10). Byte-identical to tools/render_flow.py."""
import html

from ir_core.graph import live

from .layout import HEAD_W, PAD_Y, ROW_H, STYLE, VARIANT_TITLE, control, edge_list, label, lane_name, layout

LEGEND = ("<b>Legend</b><br>[AUTO] blue: automated, no person<br>[AUTO + HUMAN REVIEW] amber, thick border: AI does "
          "it, a named person checks before it takes effect<br>[HUMAN] white: a person does it<br>APPROVAL GATE red "
          "hexagon: named approver approves or rejects; red arrow = rejected path<br>HUMAN QUEUE amber dashed: "
          "exceptions handed to a person<br>Dashed grey arrow: exception or SLA route<br>To-be: 'Changed by Sxx' = "
          "accepted AI improvement suggestion; as-is: minutes per case and PAIN = where time goes today")
EDGE_STYLE = {"flow": STYLE["edge"], "reject": STYLE["edge_reject"], "route": STYLE["edge_route"]}


def render_drawio(ir: dict) -> str:
    lay = layout(ir)
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']

    def vertex(cid, value, style, x, y, w, h):
        cells.append(f'<mxCell id="{cid}" value="{html.escape(value, quote=True)}" style="{style}" vertex="1" '
                     f'parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')

    def edge(cid, src, tgt, value, style):
        cells.append(f'<mxCell id="{cid}" value="{html.escape(value, quote=True)}" style="{style}" edge="1" '
                     f'parent="1" source="{src}" target="{tgt}"><mxGeometry relative="1" as="geometry"/></mxCell>')

    p = ir["process"]
    title = f"{p['name']} — {VARIANT_TITLE.get(p.get('variant'), '')} process flow (IR v{p['version']})"
    vertex("title", title, STYLE["title"], 0, 10, lay["width"], 40)
    for ln in lay["order"]:
        h = lay["rows"][ln] * ROW_H + 2 * PAD_Y
        vertex(f"lane_{ln}", "", STYLE["lane"], 0, lay["lane_y"][ln], lay["width"], h)
        vertex(f"lanehead_{ln}", html.escape(lane_name(ir, ln)), STYLE["lane_head"], 0, lay["lane_y"][ln], HEAD_W, h)
    for k in sorted(live(ir, "nodes")):
        x, y, w, h = lay["pos"][k]
        vertex(k, label(ir, k), STYLE.get(control(ir, k), STYLE["automated"]), x, y, w, h)
    for q in lay["queues"]:
        x, y, w, h = lay["pos"][q["id"]]
        name = html.escape(ir["exceptions"][q["exception"]]["name"])
        who = html.escape(lane_name(ir, q["lane"]))
        vertex(q["id"], f"<b>HUMAN QUEUE</b><br>{name}<br><i>{who}</i>", STYLE["queue"], x, y, w, h)
    for eid, s, t, text, kind in edge_list(ir):
        edge(eid, s, t, text, EDGE_STYLE[kind])
    for q in lay["queues"]:
        edge(f"edge_{q['id']}", q["src"], q["id"], "Exception", STYLE["edge_queue"])
    vertex("legend", LEGEND, STYLE["legend"], 0, lay["height"] + 20, 620, 140)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<mxfile host="requirements-studio" type="device"><diagram id="{p["id"]}" name="Process flow">'
            f'<mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" page="1" pageScale="1" '
            f'pageWidth="{lay["width"]}" pageHeight="{lay["height"] + 160}" math="0" shadow="0">'
            f'<root>{"".join(cells)}</root></mxGraphModel></diagram></mxfile>\n')
