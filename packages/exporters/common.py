"""Shared wording for the tracker and spreadsheet exports (port of tools/render_exports.py helpers).

These differ slightly from the stories file (M7): trackers get plain sentences, e.g. "(on exception)" for a trigger.
"""
import csv
import io

MODE = {"automated": "Automated", "hitl_review": "Automated + human review", "human_task": "Human task",
        "approval": "Approval gate", None: "Not set"}


def actor(ir: dict, actor_id: str | None) -> str:
    return ir["actors"][actor_id]["name"] if actor_id and actor_id in ir["actors"] else "—"


def article(word: str) -> str:
    return "an" if word[:1].upper() in "AEIOU" else "a"


def slug(process_id: str) -> str:
    return process_id.lower().replace("proc_", "").replace("_", "-")


def to_csv(rows: list[list], header: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue()


def gwt_lines(ac: dict) -> list[tuple[str, str]]:
    return [(kw if i == 0 else "And", line)
            for kw, key in (("Given", "given"), ("When", "when"), ("Then", "then")) for i, line in enumerate(ac[key])]


def human_line(ir: dict, s: dict) -> str:
    hc = s["human_control"]
    text = MODE[hc["mode"]]
    if hc.get("actor_id"):
        text += f" — {'approver' if hc['mode'] == 'approval' else 'reviewer'}: {actor(ir, hc['actor_id'])}"
    if hc.get("trigger"):
        text += f" ({hc['trigger'].replace('_', ' ')})"
    if hc.get("criteria"):
        text += f". Checks: {hc['criteria']}"
    for q in hc["queues"]:
        text += f". Exception '{ir['exceptions'][q['exception_id']]['name']}' goes to {actor(ir, q['actor_id'])}"
    return text


def change_line(s: dict) -> str:
    ch = s.get("change")
    if not ch:
        return "Unchanged from today"
    was = {"human_task": "manual", "approval": "an approval", "hitl_review": "reviewed"}.get(ch.get("was"),
                                                                                           ch.get("was") or "")
    text = f"{ch['kind'].replace('_', ' ').capitalize()} by suggestion {ch['suggestion_id']}"
    if was:
        minutes = ch.get("minutes_saved_per_case")
        text += f" (today: {was}" + (f", ~{minutes:g} min per case)" if minutes is not None else ")")
    return text


def story_text(ir: dict, s: dict) -> str:
    a = actor(ir, s["as_a"])
    return f"As {article(a)} {a}, I want to {s['i_want']}, so that {s['so_that']}."


def control_label(s: dict) -> str:
    return f"control-{(s['human_control']['mode'] or 'unset').replace('_', '-')}"
