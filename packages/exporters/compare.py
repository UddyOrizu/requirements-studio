"""As-is vs to-be per step (M12 Flow → Compare, the Excel 'As-is vs to-be' sheet). Port of
tools/render_exports.py::compare_rows; parity is tested."""
from ir_core.graph import bfs_distance

MODE = {"automated": "Automated", "hitl_review": "Automated + human review", "human_task": "Human task",
        "approval": "Approval gate", None: "Not set"}


def compare_rows(as_is: dict | None, to_be: dict) -> list[list]:
    """[step, today's control (or 'New step'), minutes today ('' if none), to-be control, change] per to-be task."""
    dist = bfs_distance(to_be)
    rows = []
    for k, n in sorted(to_be["nodes"].items(), key=lambda kv: (dist.get(kv[0], 10**6), kv[0])):
        if n["type"] != "task":
            continue
        before = (as_is or {}).get("nodes", {}).get(k)
        change = n.get("change")
        rows.append([n["name"], MODE[(before or {}).get("hitl", {}).get("mode")] if before else "New step",
                     n.get("as_is_effort", {}).get("minutes_per_case", ""), MODE[n.get("hitl", {}).get("mode")],
                     f"{change['suggestion_id']}: {change['kind'].replace('_', ' ')}" if change else "Unchanged"])
    return rows
