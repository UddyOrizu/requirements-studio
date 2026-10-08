"""Drive the M0 service through samples/client_kyc/intake_session_kyc.json.

SampleProvider plays the LLM: it answers each call from the recorded session, matched by content (the answer text for
an interpretation, the target for a question, the variant for a playback), so the service's own choices decide the
order. Recording with it writes cassettes; tests then replay those cassettes with no provider at all.

Stand-ins for modules not built yet: M11 Improve applies the recorded suggestion patches; M12 story refinement applies
the recorded refinement patch; the M5 semantic detector's gap_match_threshold is seeded from the sample.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from services.gaps.db import GapRow
from services.improve.service import ImproveService
from services.intake.db import IntakeSession
from services.intake.service import STANDARD_OPTIONS, IntakeService
from services.interviewer.db import Question, Sme
from services.ir_store.db import IrPatch
from services.ir_store.service import Actor
from services.llm_gateway import ProviderResponse
from tests.conftest import KYC, SAMPLES, load

SESSION = load(KYC / "intake_session_kyc.json")
TIMELINE = SESSION["timeline"]
V0 = load(KYC / "ir_v0_empty.json")
REQUESTER = Actor("user", "user_sarah_lin")
TURNS = {e["turn"]: e for e in TIMELINE if e.get("turn")}
GAP_TURN = {"sla_without_breach_action": "T18", "undefined_threshold": "T19", "story_priority_missing": "T20"}


def sample_turn_for(target: dict, gap_type: str | None = None) -> dict:
    kind, tid = target["kind"], target["id"]
    if kind == "slot":
        return next(e for e in TURNS.values() if e["target"] == {"kind": "slot", "id": tid})
    if kind == "follow_up":
        return next(e for e in TURNS.values() if e["target"]["kind"] == "follow_up")
    if kind == "playback_confirm":
        return TURNS["T17" if tid == "as_is" else "T22"]
    if kind == "gap":
        return TURNS[GAP_TURN[gap_type]]
    raise KeyError(target)


class Clock:
    """Deterministic: starts at the sample's first timestamp and ticks one second per call."""

    def __init__(self):
        self.now = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)

    def __call__(self):
        current = self.now
        self.now += timedelta(seconds=1)
        return current


def _asked_line(captured: list[str]) -> list[str]:
    return [c for c in captured if not c.startswith("Asked ")]


def _proposal(s: dict) -> dict:
    """A recorded suggestion as improve_suggest returns it (benefit is recomputed by the guardrails)."""
    return {"title": s["title"], "kind": s["kind"], "target_refs": s["target_refs"],
            "change_summary": s["change_summary"], "rationale": s["rationale"], "evidence": s["evidence"],
            "minutes_saved_per_case": s["benefit"].get("minutes_saved_per_case"),
            "qualitative": s["benefit"].get("qualitative"), "controls": s["controls"], "risk": s.get("risk"),
            "confidence": s["confidence"], "ops": s["ops"], "source": "heuristic"}


def _drafted_acs() -> dict:
    """The Deepen system patch, expressed as the intake_draft_acs output that produces it."""
    entry = next(e for e in TIMELINE if e["kind"] == "system_patch")
    criteria, outcomes = [], {}
    for op in entry["ops"]:
        parts = op["path"].split("/")
        if parts[1] == "acceptance_criteria":
            v = op["value"]
            criteria.append({"ac_id": parts[2], "applies_to": v["applies_to"], "title": v["title"],
                             "given": v["given"], "when": v["when"], "then": v["then"], "kind": v["kind"]})
        elif parts[3] in ("outcome", "goal_ids"):
            outcomes.setdefault(parts[2], {"node_id": parts[2], "outcome": "", "goal_ids": []})
            outcomes[parts[2]]["outcome" if parts[3] == "outcome" else "goal_ids"] = op["value"]
    return {"criteria": criteria, "outcomes": list(outcomes.values())}


class SampleProvider:
    """An LLM provider that answers from the recorded KYC session."""

    def __init__(self):
        self.calls: list[str] = []

    async def complete(self, *, model, prompt, temperature, json_schema):
        kind = json_schema["title"]
        self.calls.append(kind)
        if kind == "IntakeInterpretation":
            body = self._interpretation(prompt)
        elif kind == "IntakeQuestion":
            body = self._question(prompt)
        elif kind == "Playback":
            entries = [e for e in TIMELINE if e["kind"] == "playback"]
            body = {"summary": entries[0 if '"variant": "as_is"' in prompt else 1]["playback_text"]}
        elif kind == "DraftedACs":
            body = _drafted_acs()
        elif kind == "SuggestionList":
            body = {"suggestions": [_proposal(s) for s in load(KYC / "suggestions_client_kyc.json")],
                    "not_suggested": []}
        elif kind == "StoryRefinement":
            from tests.m12.refinements import RESPONSES
            instruction = re.search(r"instruction: (.*?)\nstory: ", prompt, re.S).group(1)
            body = RESPONSES[instruction]
        elif kind == "SuggestedChange":  # Edit: the requester asks for review of every auto-approval
            s = next(x for x in load(KYC / "suggestions_client_kyc.json") if f'"suggestion_id": "{x["suggestion_id"]}"'
                     in prompt)
            body = {**_proposal(s), "controls": "An analyst reviews every auto-approved case before it takes effect."}
        else:
            raise AssertionError(f"unexpected prompt for {kind}")
        return ProviderResponse(text=json.dumps(body, ensure_ascii=False), model="sample-replay")

    @staticmethod
    def _interpretation(prompt: str) -> dict:
        answer = re.search(r"\nanswer: (.*)\nmodel view: ", prompt, re.S).group(1)
        turn_id = re.search(r'locator \{kind:"turn", value:"(T\d+)"\}', prompt).group(1)
        entry = next(e for e in TIMELINE if e.get("answer", {}).get("text") == answer and e.get("turn"))
        # The recorded ops cite the sample's turn label; cite the turn being answered (M0 may ask in another order).
        ops = json.loads(json.dumps(entry.get("ops", [])).replace(
            f'"kind": "turn", "value": "{entry["turn"]}"', f'"kind": "turn", "value": "{turn_id}"'))
        return {"ops": ops, "captured": _asked_line(entry.get("captured", [])),
                "assumptions": entry.get("assumptions", []), "follow_up_question": entry.get("follow_up_question")}

    @staticmethod
    def _question(prompt: str) -> dict:
        start = prompt.index("target: ", prompt.index("<data>")) + len("target: ")
        target, _ = json.JSONDecoder().raw_decode(prompt[start:])
        entry = sample_turn_for(target, (target.get("gap") or {}).get("type"))
        q = entry["question"]
        return {"text": q["text"], "why": q["why"], "answer_type": q["answer_type"],
                "suggested_answers": [o for o in q["suggested_answers"] if o not in STANDARD_OPTIONS]}


async def seed_smes(session) -> None:
    for sme in load(SAMPLES / "sme_directory.json"):
        session.add(Sme(id=sme["sme_id"], name=sme["name"], email=sme["email"], role_title=sme["role_title"],
                        actor_ids=sme["actor_ids"], topic_tags=sme["topic_tags"], channels=sme["channels"],
                        process_ids_owned=sme["process_ids_owned"], max_open_questions=sme["max_open_questions"],
                        working_hours=sme["working_hours"]))
    await session.flush()


@dataclass
class Replay:
    service: IntakeService
    results: list = field(default_factory=list)  # every TurnResult, in order
    asked: list[tuple[str, dict]] = field(default_factory=list)  # (sample turn label, our target)

    @property
    def session_id(self) -> str:
        return SESSION["session_id"]


async def start(svc: IntakeService) -> Replay:
    p = V0["process"]
    result = await svc.start(idea_text=SESSION["idea_text"], has_process_today="yes", requester_id=REQUESTER.id,
                             requester_name="Sarah Lin", requester_role="Compliance Manager", title=p["name"],
                             description=p["description"], domain=p["domain"], idea_id=SESSION["idea_id"],
                             session_id=SESSION["session_id"],
                             source_title=V0["sources"]["src_intake_is_client_kyc"]["title"])
    return Replay(svc, [result])


async def answer_next(replay: Replay) -> bool:
    """Answer the open question with the sample's answer; False when there is none (phase change needed)."""
    svc, question = replay.service, replay.results[-1].next_question
    if question is None or question.target["kind"] == "signoff":
        return False
    gap_type = None
    if question.target["kind"] == "gap":
        sess = await svc.s.get(IntakeSession, SESSION["session_id"])
        gap_type = (await svc.s.get(GapRow, (sess.process_id, question.target["id"]))).type
    entry = sample_turn_for(question.target, gap_type)
    if question.target == {"kind": "playback_confirm", "id": "as_is"}:
        await sme_answer_arrives(svc)
    if question.target == {"kind": "playback_confirm", "id": "to_be"}:
        await refine_story(svc)
    answer = entry["answer"]
    replay.asked.append((entry["turn"], question.target))
    replay.results.append(await svc.answer(replay.session_id, text=answer.get("text"),
                                           special=answer.get("special"), ask_sme_id=answer.get("ask_sme_id")))
    return True


async def discover(replay: Replay) -> None:
    while replay.results[-1].phase == "discover" and await answer_next(replay):
        pass


async def sme_answer_arrives(svc: IntakeService) -> None:
    """M6 stand-in: James answers; the interviewer's patch is proposed and the requester accepts the card."""
    entry = next(e for e in TIMELINE if e["kind"] == "sme_answer")
    sess = await svc.s.get(IntakeSession, SESSION["session_id"])
    question = (await svc.s.execute(select(Question).where(Question.process_id == sess.process_id,
                                                           Question.sme_id == "sme_james_patel"))).scalar_one()
    proc = await svc.patches.get_process(sess.process_id)
    agent = Actor("agent", entry["author"])
    patch = {"patch_id": entry["patch_id"], "process_id": proc.id, "base_version": proc.current_version,
             "ops": entry["ops"], "author": {"kind": "agent", "id": entry["author"]},
             "reason": "SME answer", "auto_apply": True, "status": "proposed", "interpretation_confidence": 0.9,
             "evidence": {"question_id": question.id, "answer_id": f"ans_{question.id}"}}
    assert (await svc.patches.submit(patch, actor=agent)).status == "proposed"
    await svc.patches.accept(entry["patch_id"], reviewer=REQUESTER)
    await svc.record_sme_answer(SESSION["session_id"], question_id=question.id, patch_id=entry["patch_id"],
                                answered_by=entry["answer"]["by"], answer_text=entry["answer"]["text"],
                                captured=entry["captured"])


SUGGESTIONS = load(KYC / "suggestions_client_kyc.json")
REJECT_REASON = next(e for e in TIMELINE if e.get("decision") == "rejected")["answer"]["text"]


async def improve(replay: Replay) -> None:
    """M11 on the forked to-be: accept S01–S06, reject S07 with the sample's reason. The last decision moves M0 on."""
    svc = replay.service
    seed = next(g for g in load(KYC / "gaps_client_kyc.json") if g["gap_id"] == "gap_match_threshold")
    svc.s.add(GapRow(id=seed["gap_id"], process_id=seed["process_id"], fingerprint=seed["fingerprint"],
                     type=seed["type"], severity=seed["severity"], detector=seed["detector"],
                     target_refs=seed["target_refs"], title=seed["title"], why_it_matters=seed["why_it_matters"],
                     question=seed["question"], routing=seed["routing"], priority=seed["priority"], status="open",
                     ir_version_detected=seed["ir_version_detected"]))  # stand-in for the M5 semantic detector
    await svc.s.flush()
    improve_svc = ImproveService(svc.s, svc.llm, clock=svc.clock, correlation_id=svc.correlation_id)
    for s in SUGGESTIONS:
        if s["status"] == "accepted":
            await improve_svc.accept(SESSION["idea_id"], s["suggestion_id"], user_id=REQUESTER.id)
        else:
            await improve_svc.reject(SESSION["idea_id"], s["suggestion_id"], user_id=REQUESTER.id,
                                     reason=REJECT_REASON)
    replay.results.append(await svc.current(replay.session_id))


async def refine_story(svc: IntakeService) -> None:
    entry = next(e for e in TIMELINE if e["kind"] == "story_refinement")
    if not await svc.s.get(IrPatch, entry["patch_id"]):
        await _user_patch(svc, "proc_client_kyc_to_be", entry["patch_id"], entry["ops"])


async def _user_patch(svc: IntakeService, process_id: str, patch_id: str, ops: list[dict]) -> None:
    proc = await svc.patches.get_process(process_id)
    result = await svc.patches.submit({"patch_id": patch_id, "process_id": process_id,
                                       "base_version": proc.current_version, "ops": ops,
                                       "author": {"kind": "user", "id": REQUESTER.id}, "reason": "stand-in",
                                       "auto_apply": True, "status": "proposed"}, actor=REQUESTER)
    assert result.status == "applied", result


async def to_the_end(replay: Replay) -> None:
    await discover(replay)
    await improve(replay)
    while await answer_next(replay):
        pass
    replay.results.append(await replay.service.sign_off(replay.session_id, user_id=REQUESTER.id))
