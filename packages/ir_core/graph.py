"""Process-graph helpers shared by M0, M5, M7 and M8. Ported from tools/rs_reference.py; parity is tested.

All functions ignore rejected/superseded elements. Iteration orders follow the oracle, because story order and
tie-breaks depend on them.
"""
from collections import deque

from .ids import DEAD_STATUSES


def live(ir: dict, coll: str) -> dict:
    return {k: v for k, v in ir.get(coll, {}).items() if v.get("meta", {}).get("status") not in DEAD_STATUSES}


def adjacency(ir: dict) -> dict[str, set[str]]:
    """Edges plus exception/SLA routes (route_to_node targets count as reachable)."""
    adj: dict[str, set[str]] = {}
    for e in live(ir, "edges").values():
        adj.setdefault(e["from"], set()).add(e["to"])
    for coll, field in (("exceptions", "handling"), ("slas", "breach_action")):
        for x in live(ir, coll).values():
            target = x[field].get("target_node_id")
            if x[field]["action"] == "route_to_node" and target:
                for n in x["applies_to"]:
                    adj.setdefault(n, set()).add(target)
    return adj


def reach(adj: dict[str, set[str]], starts) -> set[str]:
    """Every node reachable from `starts`, including the starts themselves."""
    seen, queue = set(starts), deque(starts)
    while queue:
        x = queue.popleft()
        for y in adj.get(x, ()):
            if y not in seen:
                seen.add(y)
                queue.append(y)
    return seen


def start_nodes(ir: dict) -> list[str]:
    return [k for k, n in live(ir, "nodes").items() if n["type"] == "start"]


def end_nodes(ir: dict) -> set[str]:
    return {k for k, n in live(ir, "nodes").items() if n["type"] == "end"}


def bfs_distance(ir: dict) -> dict[str, int]:
    """Flow distance from start: main-path edges first; nodes reached only via exception/SLA routes come
    after (+100)."""
    starts = start_nodes(ir)

    def bfs(adj: dict[str, set[str]], seeds: dict[str, int]) -> dict[str, int]:
        dist = dict(seeds)
        queue = deque(sorted(seeds, key=seeds.get))
        while queue:
            x = queue.popleft()
            for y in sorted(adj.get(x, ())):
                if y not in dist:
                    dist[y] = dist[x] + 1
                    queue.append(y)
        return dist

    edge_adj: dict[str, set[str]] = {}
    for e in live(ir, "edges").values():
        edge_adj.setdefault(e["from"], set()).add(e["to"])
    main = bfs(edge_adj, {s: 0 for s in starts})
    full = bfs(adjacency(ir), {s: 0 for s in starts})
    return {k: main.get(k, full[k] + 100) for k in full}


def story_id_for(task_id: str) -> str:
    return "story_" + task_id.removeprefix("node_")


def story_groups(ir: dict) -> dict[str, list[str]]:
    """task → [task, folded decisions/waits]. Each decision/wait folds into its predecessor task nearest the start."""
    nodes = live(ir, "nodes")
    dist = bfs_distance(ir)
    preds: dict[str, set[str]] = {}
    for e in live(ir, "edges").values():
        preds.setdefault(e["to"], set()).add(e["from"])
    groups = {k: [k] for k, n in nodes.items() if n["type"] == "task"}
    for k, n in sorted(nodes.items(), key=lambda kv: (dist.get(kv[0], 10**6), kv[0])):
        if n["type"] not in ("decision", "wait"):
            continue
        cands = [p for p in preds.get(k, ()) if nodes.get(p, {}).get("type") == "task"]
        if cands:
            owner = min(cands, key=lambda p: (dist.get(p, 10**6), p))
            groups[owner].append(k)
        else:
            groups[k] = [k]
    order = sorted(groups, key=lambda t: (dist.get(t, 10**6), t))
    return {t: groups[t] for t in order}


def closure(ir: dict, node_ids) -> set[str]:
    """A story's closure: its nodes plus their actor, rules, SLAs, exceptions, goals, entities and applicable ACs."""
    ids = set(node_ids)
    for nid in node_ids:
        n = ir["nodes"][nid]
        if n.get("actor_id"):
            ids.add(n["actor_id"])
        for k in ("inputs", "outputs", "rule_ids", "sla_ids", "exception_ids", "goal_ids"):
            ids.update(n.get(k, []))
    for aid, a in live(ir, "acceptance_criteria").items():
        if set(a["applies_to"]) & set(node_ids):
            ids.add(aid)
    return ids
