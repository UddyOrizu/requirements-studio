"""M5 priority: severity_weight × (1 + log2(1 + downstream)) × (1 + stories_blocked)."""
import math

from ir_core.graph import adjacency, closure, live, reach, story_groups

from .findings import SEVERITY_WEIGHT, target_ids


def target_nodes(ir: dict, ids: set[str]) -> set[str]:
    """Nodes a gap sits on: node targets, the decisions using a rule target, the nodes an SLA/exception applies to."""
    nodes = live(ir, "nodes")
    out = {i for i in ids if i in nodes}
    for i in ids:
        if i in ir["decision_rules"]:
            out |= {k for k, n in nodes.items() if i in n.get("rule_ids", [])}
        elif i in ir["slas"]:
            out |= set(ir["slas"][i]["applies_to"])
        elif i in ir["exceptions"]:
            out |= set(ir["exceptions"][i]["applies_to"])
    return out


class PriorityModel:
    """Precomputes the graph and story closures once per IR; `priority` is then cheap per gap."""

    def __init__(self, ir: dict):
        self.ir = ir
        self.adj = adjacency(ir)
        self.closures = [closure(ir, group) for task, group in story_groups(ir).items()
                         if ir["nodes"][task]["type"] == "task"]

    def downstream(self, ids: set[str]) -> int:
        """Most nodes reachable from any one target node (excluding itself)."""
        return max((len(reach(self.adj, [n]) - {n}) for n in target_nodes(self.ir, ids)), default=0)

    def stories_blocked(self, ids: set[str]) -> int:
        return sum(1 for c in self.closures if ids & c)

    def priority(self, severity: str, target_refs: list[str]) -> float:
        ids = target_ids(target_refs)
        return round(SEVERITY_WEIGHT[severity] * (1 + math.log2(1 + self.downstream(ids)))
                     * (1 + self.stories_blocked(ids)), 2)
