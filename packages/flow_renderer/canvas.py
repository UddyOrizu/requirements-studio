"""The M10 layout as JSON for the browser canvas (M12 Flow tab, M0 live flow): the same lanes, positions and
control styling as the .drawio, so the screen and the Lucidchart import look alike."""
import html
import re

from ir_core.graph import live, story_groups, story_id_for

from .layout import PAD_Y, ROW_H, VARIANT_TITLE, control, edge_list, label, lane_name, layout

TAG = re.compile(r"</?(b|i)>")


def _lines(html_label: str) -> list[str]:
    return [html.unescape(TAG.sub("", part)) for part in html_label.split("<br>")]


def flow_json(ir: dict) -> dict:
    lay = layout(ir)
    nodes = live(ir, "nodes")
    owner = {n: story_id_for(t) for t, group in story_groups(ir).items() if ir["nodes"][t]["type"] == "task"
             for n in group}
    p = ir["process"]
    out_nodes = []
    for k in sorted(nodes):
        x, y, w, h = lay["pos"][k]
        out_nodes.append({"id": k, "type": nodes[k]["type"], "control": control(ir, k), "lane": lay["lanes"][k],
                          "lines": _lines(label(ir, k)), "x": x, "y": y, "w": w, "h": h,
                          "story_id": owner.get(k), "changed_by": (nodes[k].get("change") or {}).get("suggestion_id")})
    for q in lay["queues"]:
        x, y, w, h = lay["pos"][q["id"]]
        exc = ir["exceptions"][q["exception"]]
        out_nodes.append({"id": q["id"], "type": "queue", "control": "queue", "lane": q["lane"],
                          "lines": ["HUMAN QUEUE", exc["name"], lane_name(ir, q["lane"])], "x": x, "y": y, "w": w,
                          "h": h, "story_id": owner.get(q["src"]), "changed_by": None})
    edges = [{"id": eid, "source": s, "target": t, "label": text, "kind": kind}
             for eid, s, t, text, kind in edge_list(ir)]
    edges += [{"id": f"edge_{q['id']}", "source": q["src"], "target": q["id"], "label": "Exception", "kind": "queue"}
              for q in lay["queues"]]
    lanes = [{"id": ln, "name": lane_name(ir, ln), "y": lay["lane_y"][ln],
              "height": lay["rows"][ln] * ROW_H + 2 * PAD_Y} for ln in lay["order"]]
    return {"title": f"{p['name']} — {VARIANT_TITLE.get(p.get('variant'), '')} process flow (IR v{p['version']})",
            "variant": p.get("variant"), "version": p["version"], "width": lay["width"], "height": lay["height"],
            "lanes": lanes, "nodes": out_nodes, "edges": edges}


def thumbnail(ir: dict) -> dict:
    """A compact version for the ideas list: lanes and control-coloured boxes only."""
    full = flow_json(ir)
    return {"width": full["width"], "height": full["height"],
            "lanes": [[ln["y"], ln["height"]] for ln in full["lanes"]],
            "nodes": [[n["x"], n["y"], n["w"], n["h"], n["control"]] for n in full["nodes"]]}
