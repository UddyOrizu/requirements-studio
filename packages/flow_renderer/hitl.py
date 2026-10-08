from ir_core.graph import bfs_distance, live


def hitl_summary(ir: dict) -> list[dict]:
    """Every human touchpoint in flow order: reviews, human tasks, approval gates and human queues (M10, M7 header)."""
    rows = []
    for k, n in live(ir, "nodes").items():
        if n["type"] != "task":
            continue
        h = n.get("hitl", {})
        if h.get("mode") in ("hitl_review", "human_task", "approval"):
            rows.append({"node_id": k, "step": n["name"], "control": h["mode"],
                         "who": ir["actors"].get(h.get("actor_id") or n.get("actor_id"), {}).get("name"),
                         "when": h.get("trigger") or "always", "criteria": h.get("criteria")})
    for x in live(ir, "exceptions").values():
        if x["handling"]["action"] in ("manual_review", "escalate"):
            rows.append({"node_id": x["applies_to"][0], "step": f"Exception: {x['name']}", "control": "human_queue",
                         "who": ir["actors"].get(x["handling"].get("notify_actor_id"), {}).get("name"),
                         "when": "on_exception", "criteria": x["handling"].get("notes")})
    dist = bfs_distance(ir)
    return sorted(rows, key=lambda r: (dist.get(r["node_id"], 10**6), r["node_id"], r["step"]))
