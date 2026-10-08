"""Detailed user stories as Markdown (M7 "Markdown template"). Deterministic templating; polish is off.

Byte-identical to samples/client_kyc/stories_client_kyc.md and samples/stories_client_onboarding.md (tested).
"""
from confidence_dor import band
from flow_renderer import hitl_summary
from flow_renderer.layout import control
from ir_core.graph import closure, live
from ir_core.ids import collection_for

PRIORITY = {"must": "Must have", "should": "Should have", "could": "Could have", "wont": "Won't have",
            None: "Priority not set"}
# Control as a column/header value (story index, story header, "Human in the loop" line).
STORY_CONTROL = {"automated": "Automated (no person)", "hitl_review": "Automated + human review",
                 "human_task": "Human task", "approval": "Approval gate", None: "Not set"}
# Control of a step in the "What changes from today" and HITL tables.
STEP_CONTROL = {"automated": "Automated", "hitl_review": "Automated + human review", "human_task": "Human task",
                "approval": "Approval gate", "human_queue": "Human queue (exception)", "unset": "Not set"}
WHEN = {"always": "always", "on_exception": "on exception", "low_confidence": "low confidence", "sample": "sample"}
CHANGE_WAS = {"human_task": "manual", "approval": "an approval", "hitl_review": "reviewed"}
# NFRs are listed by category in schema order, then id (not by insertion order, which a replay need not keep).
NFR_ORDER = ["volume", "performance", "availability", "security", "privacy", "audit", "compliance", "accessibility",
             "retention", "usability"]
INFERRED_SOURCE_TITLE = "Studio assumption (confirmed by requester)"
FLOW_NOTE = ("_Shown on the process flow diagram (`flow/to_be_process_flow.drawio` for Lucidchart import, `.mmd` for "
             "Mermaid; for a document-led as-is: `flow/as_is_process_flow.drawio`)._")
IMPROVEMENTS_NOTE = "_As-is vs to-be per step. Details and rejected suggestions: `exports/improvements.md`._"


def article(word: str) -> str:
    return "an" if word[:1].upper() in "AEIOU" else "a"


def _num(x) -> str:
    return f"{x:g}"


def _actor(ir: dict, actor_id: str | None) -> str:
    return ir["actors"][actor_id]["name"] if actor_id and actor_id in ir["actors"] else "—"


def _ids(ids: list[str]) -> str:
    return ", ".join(ids) if ids else "—"


# ---------------------------------------------------------------- process context

def _goal_line(ir: dict, gid: str, goal: dict) -> str:
    metrics = []
    for m in goal["metrics"]:
        unit = f" {m['unit']}" if m.get("unit") else ""
        if m.get("baseline") is not None and m.get("target") is not None:
            metrics.append(f"{m['name']}: {_num(m['baseline'])} → {_num(m['target'])}{unit}")
        elif m.get("target") is not None:
            metrics.append(f"{m['name']}: {_num(m['target'])}{unit}")
        else:
            metrics.append(m["name"])
    personas = [ir["personas"][p]["name"] for p in goal.get("persona_ids", []) if p in ir["personas"]]
    return (f"- **{goal['statement']}** (`{gid}`): {'; '.join(metrics) or 'no metric yet'} · "
            f"benefits: {', '.join(personas) or '—'}")


def _scope_lines(scope: dict) -> list[str]:
    return ([f"- In: {x}" for x in scope["in"]] + [f"- Out: {x}" for x in scope["out"]]
            + [f"- Assumption: {x}" for x in scope["assumptions"]]
            + [f"- Constraint: {x}" for x in scope["constraints"]])


def _nfr_line(ir: dict, nid: str, nfr: dict) -> str:
    measure = f" — {nfr['measure']}" if nfr.get("measure") else ""
    where = ", ".join(ir["nodes"][n]["name"] for n in nfr["applies_to"]) if nfr["applies_to"] else "all steps"
    return f"- [{nfr['category']}] {nfr['statement']}{measure} ({where}) `{nid}`"


def _changes_table(ir: dict, as_is: dict, stories: dict) -> list[str]:
    rows = ["| Step | Today | Minutes today | To-be | Change |", "|---|---|---|---|---|"]
    for s in stories.values():
        nid = s["node_ids"][0]
        node = ir["nodes"][nid]
        before = as_is["nodes"].get(nid)
        today = STEP_CONTROL[control(as_is, nid)] if before else "—"
        minutes = (before or {}).get("as_is_effort", {}).get("minutes_per_case")
        ch = node.get("change")
        change = f"{ch['suggestion_id']}: {ch['kind'].replace('_', ' ')}" if ch else "Unchanged"
        rows.append(f"| {node['name']} | {today} | {_num(minutes) if minutes is not None else '—'} | "
                    f"{STEP_CONTROL[control(ir, nid)]} | {change} |")
    return rows


def _hitl_section(ir: dict) -> list[str]:
    rows = hitl_summary(ir)
    out = ["**Human-in-the-loop and approval gates**", "", FLOW_NOTE, ""]
    if rows:
        out += ["| Step | Control | Who | When | Checks |", "|---|---|---|---|---|"]
        out += [f"| {r['step']} | {STEP_CONTROL[r['control']]} | {r['who'] or '—'} | "
                f"{WHEN.get(r['when'], r['when'])} | {r['criteria'] or '—'} |" for r in rows]
    else:
        out.append("_No human checkpoints captured yet._")
    unset = [n["name"] for n in live(ir, "nodes").values() if n["type"] == "task" and not n.get("hitl", {}).get("mode")]
    if unset:
        out += ["", f"⚠ Control not set for {len(unset)} step(s): {', '.join(unset)}."]
    return out


def _context(ir: dict, stories: dict, as_is: dict | None) -> list[str]:
    out = ["## Process context", "", "**Goals**", ""]
    out += [_goal_line(ir, gid, g) for gid, g in live(ir, "goals").items()] or ["_No goals captured yet._"]
    scope = _scope_lines(ir["scope"])
    if scope:
        out += ["", "**Scope**", ""] + scope
    nfrs = sorted(live(ir, "nfrs").items(), key=lambda kv: (NFR_ORDER.index(kv[1]["category"]), kv[0]))
    if nfrs:
        out += ["", "**Non-functional requirements**", ""] + [_nfr_line(ir, k, v) for k, v in nfrs]
    if as_is is not None:
        out += ["", "**What changes from today**", "", IMPROVEMENTS_NOTE, ""] + _changes_table(ir, as_is, stories)
    out += [""] + _hitl_section(ir)
    out += ["", "**Story index**", "", "| Story | ID | Priority | Control | Confidence | DoR |",
            "|---|---|---|---|---|---|"]
    out += [f"| {s['title']} | `{sid}` | {PRIORITY[s['priority']]} | "
            f"{STORY_CONTROL[s['human_control']['mode']]} | {band(s['confidence'])} {s['confidence']} | "
            f"{s['dor_status']} |" for sid, s in stories.items()]
    return out


# ---------------------------------------------------------------- one story

def human_line(ir: dict, s: dict) -> str:
    hc = s["human_control"]
    text = STORY_CONTROL[hc["mode"]]
    if hc.get("actor_id"):
        role = "approver" if hc["mode"] == "approval" else "reviewer"
        text += f" — {role}: {_actor(ir, hc['actor_id'])}"
        if hc.get("trigger"):
            text += f", {WHEN.get(hc['trigger'], hc['trigger'])}"
    if hc.get("criteria"):
        text += f". Checks: {hc['criteria']}"
    text += "."
    for q in hc["queues"]:
        text += f" Exception '{ir['exceptions'][q['exception_id']]['name']}' goes to {_actor(ir, q['actor_id'])}."
    return text


def change_line(s: dict) -> str:
    ch = s.get("change")
    if not ch:
        return "Unchanged from today."
    text = f"{ch['kind'].replace('_', ' ').capitalize()} by suggestion {ch['suggestion_id']}"
    was = CHANGE_WAS.get(ch.get("was"), ch.get("was") or "")
    if was:
        minutes = ch.get("minutes_saved_per_case")
        text += f" (today: {was}" + (f", ~{_num(minutes)} min per case)" if minutes is not None else ")")
    return text + "."


def gwt_lines(ac: dict) -> list[tuple[str, str]]:
    """(keyword, text) per line; repeated Given/When/Then lines use And."""
    return [(kw if i == 0 else "And", line)
            for kw, key in (("Given", "given"), ("When", "when"), ("Then", "then")) for i, line in enumerate(ac[key])]


def _rule_lines(rid: str, rule: dict) -> list[str]:
    out = [f"- **{rule['name']}** (`{rid}`) → outcomes: {', '.join(rule['outcomes'])}"]
    logic = rule["logic"]
    if logic["kind"] == "table":
        columns = [c.split(".")[-1] for c in logic["columns"]]  # ent_client.country_risk → country_risk
        out += ["", "  | " + " | ".join(columns) + " | → outcome |", "  |" + "---|" * (len(columns) + 1)]
        out += [f"  | {' | '.join('any' if c == '*' else c for c in row['when'])} | **{row['then']}** |"
                for row in logic["rows"]]
        if logic.get("hit_policy"):
            out.append(f"  _Hit policy: {logic['hit_policy']}_")
    elif logic["kind"] == "expression":
        out.append(f"  `{logic['expression']}`")
    else:
        out.append(f'  ⚠ Natural language: "{logic["text"]}"')
    return out


def _sla_line(ir: dict, sla: dict) -> str:
    calendar = {"working_days": " working days", "calendar_days": " calendar days"}.get(sla.get("calendar"), "")
    parts = [f"{sla['duration']}{calendar}"]
    if sla.get("clock_starts"):
        parts.append(f"starts: {sla['clock_starts']}")
    if sla.get("clock_stops"):
        parts.append(f"stops: {sla['clock_stops']}")
    ba = sla["breach_action"]
    breach = ba["action"].replace("_", " ")
    if ba.get("target_node_id"):
        breach += f" → '{ir['nodes'][ba['target_node_id']]['name']}'"
    if ba.get("notify_actor_id"):
        breach += f" (notify {_actor(ir, ba['notify_actor_id'])})"
    parts.append(f"on breach: {breach}")
    return f"- **{sla['name']}**: " + "; ".join(parts)


def _sources(ir: dict, ids: set[str]) -> str:
    """Titles of every source cited by an element in the closure, in source-id order."""
    cited = {p["source_id"] for i in ids for p in ir[collection_for(i)][i]["meta"]["provenance"]}
    titles = [INFERRED_SOURCE_TITLE if sid == "src_inferred" else ir["sources"][sid]["title"]
              for sid in sorted(cited) if sid == "src_inferred" or sid in ir["sources"]]
    return "; ".join(titles) or "—"


def _story(ir: dict, sid: str, s: dict, dor_row: dict | None, variant: str | None) -> list[str]:
    cl = closure(ir, s["node_ids"])
    actor = _actor(ir, s["as_a"])
    out = [f"### {s['title']} · `{sid}`",
           f"**{PRIORITY[s['priority']]}** · Confidence **{band(s['confidence'])} ({s['confidence']})** · "
           f"DoR **{s['dor_status']}** · Control **{STORY_CONTROL[s['human_control']['mode']]}** · "
           f"Open questions **{len(s['open_questions'])}**",
           "",
           f"> As {article(actor)} **{actor}**, I want **to {s['i_want']}**, so that **{s['so_that']}**.",
           ""]
    if s["goal_ids"]:
        personas = ", ".join(ir["personas"][p]["name"] for p in s["persona_ids"]) or "—"
        goals = "; ".join(ir["goals"][g]["statement"] for g in s["goal_ids"])
        out += [f"**Who benefits:** {personas} · **Goals served:** {goals}", ""]
    out += [f"**Human in the loop:** {human_line(ir, s)}", ""]
    if variant == "to_be":
        out += [f"**Change from today:** {change_line(s)}", ""]

    out += ["**Acceptance criteria**", ""]
    if s["ac_ids"]:
        for i, aid in enumerate(s["ac_ids"], 1):
            ac = ir["acceptance_criteria"][aid]
            out.append(f"{i}. *{ac['title']}* `{aid}` ({ac.get('kind', 'happy_path').replace('_', ' ')})")
            out += [f"   - {kw} {line}" for kw, line in gwt_lines(ac)]
    else:
        out.append("_None defined yet._")
    out.append("")

    if s["edge_cases"]:
        out += ["**Edge cases & exceptions**", ""]
        out += [f"- {e['title']} (`{e['ref']}`): {e['handling']}" for e in s["edge_cases"]] + [""]
    rules = sorted(i for i in cl if i in live(ir, "decision_rules"))
    if rules:
        out += ["**Business rules**", ""]
        for rid in rules:
            out += _rule_lines(rid, ir["decision_rules"][rid])
        out.append("")
    slas = sorted(i for i in cl if i in live(ir, "slas"))
    if slas:
        out += ["**Time limits (SLAs)**", ""] + [_sla_line(ir, ir["slas"][x]) for x in slas] + [""]
    if s["data_requirements"]:
        out += ["**Data**", "", "| Entity | Access | Attributes |", "|---|---|---|"]
        out += [f"| {ir['entities'][d['entity_id']]['name']} (`{d['entity_id']}`) | "
                f"{d['access'].replace('read_write', 'read/write')} | {', '.join(d['attributes'])} |"
                for d in s["data_requirements"]] + [""]
    if s["nfr_ids"]:
        out += ["**Non-functional**", ""]
        out += [f"- [{ir['nfrs'][n]['category']}] {ir['nfrs'][n]['statement']}" for n in s["nfr_ids"]] + [""]

    deps = s["dependencies"]
    systems = ", ".join(_actor(ir, a) for a in deps["system_actor_ids"]) or "—"
    out += [f"**Dependencies:** upstream {_ids(deps['upstream_story_ids'])} · downstream "
            f"{_ids(deps['downstream_story_ids'])} · systems {systems}", ""]
    if s["open_questions"]:
        out += ["**Open questions**", ""]
        for q in s["open_questions"]:
            waiting = f", waiting on {q['asked_to']}" if q.get("asked_to") else ""
            out.append(f"- {q['text']} ({q['severity']}, {q['status']}{waiting}) `{q['gap_id']}`")
        out.append("")
    if s["dor_status"] == "not_ready" and dor_row:
        out += ["**Not ready because**", ""]
        out += [f"- {c['check_id']}: {c['message']}" for c in dor_row["checks"] if not c["passed"]] + [""]
    out += [f"**Traceability:** nodes {', '.join(s['node_ids'])} · sources: {_sources(ir, cl)}", "", "---", ""]
    return out


def render_markdown(ir: dict, dor_rows: list[dict], *, as_is: dict | None = None, origin: str | None = None) -> str:
    """Stories markdown for an IR whose `stories` are derived and DoR-evaluated.

    `dor_rows`: evaluate_dor output (for "Not ready because"). `as_is`: the as-is IR, when one exists, for the
    "What changes from today" table. `origin`: how the IR came about, for the header line (from M0/M12).
    """
    p = ir["process"]
    origin = origin or f"IR version {p['version']} (polish off)"
    rows = {r["story_id"]: r for r in dor_rows}
    stories = ir.get("stories", {})
    out = [f"# User stories — {p['name']}", "",
           f"_Rendered by M7 from {origin}. Do not edit — change the IR._", ""]
    out += _context(ir, stories, as_is) + ["", "---", ""]
    for sid, s in stories.items():
        out += _story(ir, sid, s, rows.get(sid), p.get("variant"))
    return "\n".join(out[:-1]) + "\n"

