"""Demo and UI-test data built from samples/ (dev and test only; mounted at POST /dev/seed).

Scenarios:
- "samples": both sample ideas as they end — the document-led onboarding idea mid-review, and client KYC ready and
  signed off (as-is v19, to-be v12).
- "kyc_before_refinement": client KYC just before the story refinement (to-be v10, Validate, next turn T21).

Both create the dev users (services/identity_audit/dev.py; password "requirements-studio-dev").

KYC is rebuilt by replaying the recorded session's patches through the Patch Service, so versions, patch history and
audit are real. Nothing here calls an LLM.
"""
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from confidence_dor import closure_hash
from services.gaps.db import GapRow
from services.ideas.db import Idea
from services.identity_audit.dev import seed_dev_users
from services.improve.db import SuggestionRow
from services.intake.db import IntakeSession, IntakeTurn, Signoff
from services.interviewer.db import Question, Sme
from services.ir_store.service import Actor, PatchService
from story_renderer import derive_stories

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
KYC = SAMPLES / "client_kyc"
SCENARIOS = ("samples", "kyc_before_refinement")
KEEP = {"alembic_version", "audit_log"}  # audit_log is append-only (its trigger blocks TRUNCATE)


def _load(path: Path):
    return json.loads(path.read_text())


def _ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


async def reset(s: AsyncSession) -> None:
    """Empty every table except the append-only audit log."""
    tables = [r[0] for r in await s.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))]
    wipe = [t for t in tables if t not in KEEP]
    await s.execute(text(f"TRUNCATE {', '.join(wipe)} CASCADE"))


async def seed(s: AsyncSession, scenario: str) -> None:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario}; one of {SCENARIOS}")
    await reset(s)
    await seed_dev_users(s)
    await _smes(s)
    index = {i["idea_id"]: i for i in _load(SAMPLES / "ideas_index.json")}
    patches = PatchService(s, correlation_id="seed")
    if scenario == "samples":
        await _onboarding(s, patches, index["idea_client_onboarding"])
    await _kyc(s, patches, index["idea_client_kyc"], stop_before_refinement=scenario == "kyc_before_refinement")
    await s.flush()


async def _smes(s: AsyncSession) -> None:
    for sme in _load(SAMPLES / "sme_directory.json"):
        s.add(Sme(id=sme["sme_id"], name=sme["name"], email=sme["email"], role_title=sme["role_title"],
                  actor_ids=sme["actor_ids"], topic_tags=sme["topic_tags"], channels=sme["channels"],
                  process_ids_owned=sme["process_ids_owned"], max_open_questions=sme["max_open_questions"],
                  working_hours=sme["working_hours"]))
    await s.flush()


def _idea(record: dict, **overrides) -> Idea:
    r = {**record, **overrides}
    return Idea(id=r["idea_id"], title=r["title"], summary=r["summary"], owner_user_id=r["owner_user_id"],
                status=r["status"], has_as_is=r["has_as_is"], as_is_process_id=None, to_be_process_id=None,
                session_id=r["session_id"], tags=r["tags"], stats={}, created_at=_ts(r["created_at"]),
                updated_at=_ts(r["updated_at"]))


def _gap_row(g: dict) -> GapRow:
    return GapRow(id=g["gap_id"], process_id=g["process_id"], fingerprint=g["fingerprint"], type=g["type"],
                  severity=g["severity"], detector=g["detector"], target_refs=g["target_refs"], title=g["title"],
                  why_it_matters=g["why_it_matters"], question=g["question"], routing=g["routing"],
                  priority=g["priority"], status=g["status"], ir_version_detected=g["ir_version_detected"])


def _question_row(q: dict) -> Question:
    return Question(id=q["question_id"], process_id=q["process_id"], origin=q.get("origin", "gap_routing"),
                    asked_by=q.get("asked_by"), gap_ids=q["gap_ids"], sme_id=q["sme_id"], batch_id=q.get("batch_id"),
                    channel="in_app" if q["channel"] == "teams" else q["channel"], text=q["text"],
                    context_snippet=q.get("context_snippet"), answer_type=q["answer_type"],
                    suggested_answers=q.get("suggested_answers"), status=q["status"], sent_at=_ts(q.get("sent_at")),
                    due_at=_ts(q.get("due_at")))


async def _onboarding(s: AsyncSession, patches: PatchService, record: dict) -> None:
    idea = _idea(record)
    s.add(idea)
    await s.flush()
    await patches.import_process(_load(SAMPLES / "ir_client_onboarding.json"), actor=Actor("user", idea.owner_user_id))
    idea.as_is_process_id = "proc_client_onboarding"
    for g in _load(SAMPLES / "gaps_client_onboarding.json"):
        s.add(_gap_row(g))
    await s.flush()
    for q in _load(SAMPLES / "questions_outbox.json"):
        s.add(_question_row(q))
    await s.flush()
    idea.updated_at = _ts(record["updated_at"])  # linking the process above touched it


async def _kyc(s: AsyncSession, patches: PatchService, record: dict, *, stop_before_refinement: bool) -> None:
    session = _load(KYC / "intake_session_kyc.json")
    requester = Actor("user", session["requester_user_id"])
    idea = _idea(record, status="refining" if stop_before_refinement else record["status"])
    s.add(idea)
    await s.flush()
    await patches.import_process(_load(KYC / "ir_v0_empty.json"), actor=requester)
    idea.as_is_process_id = session["as_is_process_id"]

    entries = session["timeline"]
    if stop_before_refinement:
        entries = entries[:next(i for i, e in enumerate(entries) if e["kind"] == "story_refinement")]
    process = {"as_is": session["as_is_process_id"], "to_be": session["to_be_process_id"]}
    for e in entries:
        if e["kind"] == "fork":
            overrides = e["fork"]["process_overrides"]
            await patches.fork(process["as_is"], actor=requester, to_process_id=e["fork"]["to_process_id"],
                               name=overrides["name"], description=overrides["description"])
            idea.to_be_process_id = e["fork"]["to_process_id"]
        elif e.get("ops"):
            pid = process[e.get("process", "as_is")]
            proc = await patches.get_process(pid)
            author = Actor("agent", e["author"]) if e.get("author", "").startswith("agent:") else requester
            result = await patches.submit({
                "patch_id": e["patch_id"], "process_id": pid, "base_version": proc.current_version, "ops": e["ops"],
                "author": {"kind": author.kind, "id": author.id},
                "reason": f"{e.get('turn') or e['kind'].replace('_', ' ')}: {(e.get('captured') or [''])[0]}"[:500],
                "auto_apply": True, "status": "proposed"}, actor=author)
            if result.status == "proposed":
                await patches.accept(result.patch_id, reviewer=requester)

    sess = IntakeSession(id=session["session_id"], mode=session["mode"], idea_id=idea.id,
                         process_id=session["to_be_process_id"], requester_user_id=requester.id,
                         phase="validate" if stop_before_refinement else session["phase"],
                         status="active" if stop_before_refinement else session["status"],
                         coverage=next(e["coverage_after"] for e in reversed(entries) if e.get("coverage_after")),
                         parked=[],
                         started_at=_ts(session["started_at"]), source_id=session["source_id"],
                         state={"requester_name": "Sarah Lin", "requester_role": "Compliance Manager",
                                "confirmed_playbacks": ["as_is"] + ([] if stop_before_refinement else ["to_be"]),
                                "turns": max(int(e["turn"][1:]) for e in entries if e.get("turn"))},
                         completed_at=None if stop_before_refinement else _ts(entries[-1]["at"]))
    s.add(sess)
    await s.flush()
    for e in entries:
        payload = {k: e[k] for k in ("playback_text", "from_phase", "to_phase", "question_id", "parked", "fork",
                                     "story_ids", "author", "suggestion_ids", "suggestion_id", "decision")
                   if k in e}
        if e.get("answer", {}).get("by") not in (None, requester.id):
            payload["answer_by"] = e["answer"]["by"]
        s.add(IntakeTurn(session_id=sess.id, n=e["seq"], kind=e["kind"], turn=e.get("turn"),
                         process_variant=e.get("process"), phase=e["phase"], target=e.get("target"),
                         question=e.get("question"), answer_text=e.get("answer", {}).get("text"),
                         special=e.get("answer", {}).get("special"), ask_sme_id=e.get("answer", {}).get("ask_sme_id"),
                         patch_id=e.get("patch_id"), captured=e.get("captured"), assumptions=e.get("assumptions"),
                         follow_up_question=e.get("follow_up_question"), coverage_after=e.get("coverage_after"),
                         at=_ts(e["at"]), payload=payload))

    for x in _load(KYC / "suggestions_client_kyc.json"):
        decided = next((e for e in session["timeline"] if e.get("suggestion_id") == x["suggestion_id"]), None)
        s.add(SuggestionRow(id=x["suggestion_id"], idea_id=idea.id, kind=x["kind"], target_refs=x["target_refs"],
                            title=x["title"], change_summary=x["change_summary"], rationale=x["rationale"],
                            evidence=x["evidence"], benefit=x["benefit"], controls=x["controls"], risk=x.get("risk"),
                            confidence=x["confidence"], status=x["status"], decision=x["decision"], ops=x["ops"],
                            applied_patch_id=(decided or {}).get("patch_id"), source="heuristic"))
    for g in _load(KYC / "gaps_client_kyc.json"):
        s.add(_gap_row(g))
    await s.flush()
    for q in session["parked_questions"]:
        s.add(_question_row(q))

    await s.flush()
    idea.updated_at = _ts(record["updated_at"])  # linking the processes above touched it
    if not stop_before_refinement:  # the requester signed off every story at to-be v12
        to_be = await patches.get_ir(process["to_be"])
        stories = derive_stories(to_be, [])
        signed = next(e for e in session["timeline"] if e["kind"] == "signoff")
        for sid, story in stories.items():
            s.add(Signoff(process_id=process["to_be"], story_id=sid, ir_version=to_be["process"]["version"],
                          closure_hash=closure_hash(to_be, story), signed_by=requester.id,
                          signed_at=_ts(signed["at"])))
