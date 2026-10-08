"""Gherkin (M7): one Feature per process, one Scenario per acceptance criterion (each AC once, in story order)."""
from .markdown import gwt_lines


def render_gherkin(ir: dict, *, description: str | None = None) -> str:
    """Tags: every story containing the AC, the AC id, the story priority, the AC kind (non-happy-path),
    @exception / @sla when the AC applies to an exception / SLA directly."""
    p = ir["process"]
    stories = ir.get("stories", {})
    description = description or (f"Rendered by M7 from IR version {p['version']}. "
                                  "One scenario per acceptance criterion.")
    owners: dict[str, list[str]] = {}
    for sid, s in stories.items():
        for aid in s["ac_ids"]:
            owners.setdefault(aid, []).append(sid)
    out = [f"@{p['id']}", f"Feature: {p['name']}", f"  {description}"]
    for aid, story_ids in owners.items():
        ac = ir["acceptance_criteria"][aid]
        first = stories[story_ids[0]]
        tags = [f"@{sid}" for sid in story_ids] + [f"@{aid}"]
        if first["priority"]:
            tags.append(f"@{first['priority']}")
        if ac.get("kind", "happy_path") != "happy_path":
            tags.append(f"@{ac['kind']}")
        if any(t.startswith("exc_") for t in ac["applies_to"]):
            tags.append("@exception")
        if any(t.startswith("sla_") for t in ac["applies_to"]):
            tags.append("@sla")
        out += ["", f"  {' '.join(tags)}", f"  Scenario: {ac['title']}"]
        out += [f"    {kw} {line}" for kw, line in gwt_lines(ac)]
    return "\n".join(out) + "\n"
