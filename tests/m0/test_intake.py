"""M0 intake against Postgres, replaying samples/client_kyc with LLM cassettes (tests/cassettes/intake_*).

Re-record after changing a prompt or the variables M0 sends (every test then records the calls it makes):
    RS_RECORD_CASSETTES=1 RS_DATABASE_URL=… uv run pytest tests/m0
"""
import os
from pathlib import Path

import pytest

from ir_core import canonical_json, validate_integrity, validate_schema
from ir_core.ids import ELEMENT_COLLECTIONS
from services.intake.coverage import next_slot
from services.intake.service import IntakeService, ir_view, provenance_refs
from services.interviewer.db import Question
from services.llm_gateway import CassetteStore, LLMGateway, PromptRegistry
from tests.conftest import KYC, ROOT, load
from tests.m0 import kyc_replay as K

CASSETTES = ROOT / "tests" / "cassettes"
RECORD = os.environ.get("RS_RECORD_CASSETTES") == "1"


def gateway(mode: str, cassettes: Path = CASSETTES) -> LLMGateway:
    return LLMGateway(PromptRegistry(ROOT / "prompts"), mode=mode, provider=K.SampleProvider() if mode == "record"
                      else None, cassettes=CassetteStore(cassettes))


@pytest.fixture
async def db(tx_sessionmaker):
    async with tx_sessionmaker() as session:
        await K.seed_smes(session)
        yield session


@pytest.fixture
def svc(db):
    return IntakeService(db, gateway("record" if RECORD else "replay"), clock=K.Clock(), correlation_id="corr-m0")


# ---------------------------------------------------------------- acceptance tests

async def test_M0_AC_M0_1(svc):
    """From idea.md alone (as-is mode), turn 0 gives a goal, ≥ 2 tasks with pain points; next question is C04."""
    replay = await K.start(svc)
    first = replay.results[0]
    ir = await svc.patches.get_ir("proc_client_kyc_as_is")
    assert ir["goals"] and ir["process"]["variant"] == "as_is"
    tasks = [n for n in ir["nodes"].values() if n["type"] == "task"]
    with_pain = [n for n in tasks if n.get("as_is_effort", {}).get("pain_points")]
    assert len(with_pain) >= 2
    assert first.next_question.target == {"kind": "slot", "id": "C04"}
    assert first.next_question.suggested_answers[-3:] == ["Other…", "Not sure — ask someone", "Skip for now"]
    assert first.coverage["percent"] == 0.08


async def test_M0_AC_M0_2(svc):
    """Every Discover turn targeting a slot targets next_slot() of the pre-turn IR (15 turns in the sample)."""
    replay = await K.start(svc)
    await K.discover(replay)
    session = await svc.export(replay.session_id)
    slot_turns = [e for e in session["timeline"] if e.get("target", {}).get("kind") == "slot"]
    assert len(slot_turns) == 15
    for e in slot_turns:
        patch_before = max((x for x in session["timeline"] if x["seq"] < e["seq"] and x.get("ir_version_after")),
                           key=lambda x: x["seq"])
        ir = await svc.patches.get_ir("proc_client_kyc_as_is", patch_before["ir_version_after"])
        parked = [p for x in session["timeline"] if x["seq"] < e["seq"] for p in x.get("parked", [])]
        assert next_slot(ir, parked) == e["target"]["id"], e["turn"]
    # The same questions in the same order as the recorded session.
    assert [label for label, _ in replay.asked] == [f"T{i}" for i in range(1, 18)]


async def test_M0_AC_M0_3(svc):
    """The whole session through M0 (with the M11/M12 stand-ins) yields the stored as-is and to-be; every version
    is schema- and integrity-valid."""
    replay = await K.start(svc)
    await K.to_the_end(replay)
    for pid, stored in (("proc_client_kyc_as_is", "ir_client_kyc_as_is.json"),
                        ("proc_client_kyc_to_be", "ir_client_kyc_to_be.json")):
        got, want = await svc.patches.get_ir(pid), load(KYC / stored)
        if pid.endswith("to_be"):
            # M0 §2 asks Deepen gaps by priority: the match-threshold gap (33.36) before the SLA gap (16), so the SLA
            # answer is turn T19 here. The recorded session asked them the other way round and cites T18.
            [ref] = [p for p in want["slas"]["sla_kyc_checks"]["meta"]["provenance"]
                     if p["locator"] == {"kind": "turn", "value": "T18"}]
            ref["locator"]["value"] = "T19"
            # M11 records its source when it generates suggestions: the time is this replay's clock.
            want["sources"]["src_improve_is_client_kyc"]["ingested_at"] = \
                got["sources"]["src_improve_is_client_kyc"]["ingested_at"]
        for coll in [*ELEMENT_COLLECTIONS, "sources", "scope"]:
            assert got[coll] == want[coll], f"{pid}.{coll}"
        assert got["process"]["version"] == want["process"]["version"]
        for v in range(want["process"]["version"] + 1):
            ir = await svc.patches.get_ir(pid, v)
            assert validate_schema(ir) == [] and validate_integrity(ir) == [], f"{pid}@v{v}"


async def test_M0_AC_M0_4(svc):
    """Every src_intake_* provenance excerpt is a verbatim substring of the cited turn's answer."""
    replay = await K.start(svc)
    await K.discover(replay)
    session = await svc.export(replay.session_id)
    answers = {e["turn"]: e["answer"]["text"] for e in session["timeline"] if e.get("turn") and e.get("answer")}
    ir = await svc.patches.get_ir("proc_client_kyc_as_is")
    refs = [p for c in ELEMENT_COLLECTIONS for x in ir[c].values() for p in x["meta"]["provenance"]
            if p["source_id"] == "src_intake_is_client_kyc"]
    assert refs
    for p in refs:
        assert p["excerpt"] in answers[p["locator"]["value"]]


async def test_M0_AC_M0_4_rejects_a_paraphrased_excerpt(svc, monkeypatch):
    replay = await K.start(svc)
    original = svc._interpret

    async def paraphrase(*args, **kwargs):
        result = await original(*args, **kwargs)
        for op in result.ops:
            for ref in provenance_refs(op.value):
                ref["excerpt"] = "the client record is made in the CRM"  # not in the answer
        return result

    monkeypatch.setattr(svc, "_interpret", paraphrase)
    with pytest.raises(Exception, match="not verbatim"):
        await K.answer_next(replay)


async def test_M0_AC_M0_5(svc, db):
    """T10 "not sure — ask someone" sends a question to sme_james_patel, parks the target, next question is C12."""
    replay = await K.start(svc)
    while replay.results[-1].next_question.target != {"kind": "slot", "id": "C11"}:
        await K.answer_next(replay)
    await K.answer_next(replay)
    t10 = replay.results[-1]
    assert t10.next_question.target == {"kind": "slot", "id": "C12"}
    assert any(c.startswith("Asked James Patel (Head of Onboarding Technology)") for c in t10.captured)
    from sqlalchemy import select
    [question] = (await db.execute(select(Question))).scalars().all()
    assert (question.sme_id, question.origin, question.status) == ("sme_james_patel", "intake_ask_someone", "sent")
    assert question.channel in ("email", "in_app")
    session = await svc.export(replay.session_id)
    assert "C11" in (await svc._session(replay.session_id)).parked
    assert session["timeline"][-2]["question_id"] == question.id


async def test_M0_AC_M0_6(svc):
    """T15 (C16) records today's controls: human_task everywhere except the two approval gates. T16 (C17) records
    minutes per step (110 in total) and coverage reaches 1.0."""
    replay = await K.start(svc)
    await K.discover(replay)
    by_turn = {label: result for (label, _), result in zip(replay.asked, replay.results[1:], strict=True)}
    v16 = await svc.patches.get_ir("proc_client_kyc_as_is", 16)
    modes = {k: n["hitl"]["mode"] for k, n in v16["nodes"].items() if n["type"] == "task"}
    assert sorted(k for k, m in modes.items() if m == "approval") == ["node_analyst_review", "node_mlro_approval"]
    assert all(m == "human_task" for k, m in modes.items() if k not in ("node_analyst_review", "node_mlro_approval"))
    v17 = await svc.patches.get_ir("proc_client_kyc_as_is", 17)
    assert sum(n.get("as_is_effort", {}).get("minutes_per_case", 0) for n in v17["nodes"].values()) == 110
    assert by_turn["T16"].coverage["percent"] == 1.0


async def test_M0_AC_M0_7(svc):
    """After Improve (M11 stand-in), Deepen and Validate on the to-be, all 9 stories are ready and signed off."""
    from confidence_dor import evaluate_dor
    from services.gaps.store import stored_gaps
    from story_renderer import derive_stories
    replay = await K.start(svc)
    await K.to_the_end(replay)
    assert replay.results[-1].phase == "done"
    ir = await svc.patches.get_ir("proc_client_kyc_to_be")
    gaps = [g.as_gap() for g in await stored_gaps(svc.s, "proc_client_kyc_to_be")]
    stories = derive_stories(ir, gaps)
    rows = evaluate_dor(ir, stories, gaps, signoffs=set(stories))
    assert len(rows) == 9 and all(r["status"] == "ready" for r in rows)


@pytest.mark.parametrize("label", ["T1", "T5", "T10", "T16"])
async def test_M0_AC_M0_8(svc, label):
    """Undo of a turn restores the previous IR version byte for byte (canonical JSON, version fields aside)."""
    replay = await K.start(svc)
    while not replay.asked or replay.asked[-1][0] != label:
        await K.answer_next(replay)
    session = await svc.export(replay.session_id)
    entry = next(e for e in session["timeline"] if e.get("turn") == label)
    before = await svc.patches.get_ir("proc_client_kyc_as_is", entry["ir_version_after"] - 1)
    await svc.undo(replay.session_id, entry["seq"])
    after = await svc.patches.get_ir("proc_client_kyc_as_is")
    assert canonical_json(ir_view(after)) == canonical_json(ir_view(before))
    assert after["process"]["version"] == entry["ir_version_after"] + 1


# ---------------------------------------------------------------- more behaviour

async def test_m0_coverage_after_each_turn_matches_the_sample(svc):
    replay = await K.start(svc)
    await K.discover(replay)
    for (label, _), result in zip(replay.asked, replay.results[1:], strict=True):
        assert result.coverage["percent"] == K.TURNS[label]["coverage_after"]["percent"], label
        assert result.coverage["filled"] == K.TURNS[label]["coverage_after"]["filled"], label


async def test_m0_follow_up_is_asked_next(svc):
    replay = await K.start(svc)
    while not replay.asked or replay.asked[-1][0] != "T7":
        await K.answer_next(replay)
    assert replay.results[-1].next_question.target == {"kind": "follow_up", "id": "T7"}


async def test_m0_as_is_is_confirmed_then_forked(svc):
    replay = await K.start(svc)
    await K.discover(replay)
    result = replay.results[-1]
    assert result.phase == "improve" and result.next_question is None  # waiting for M11
    assert result.captured == ["As-is confirmed (60 elements)"]
    as_is = await svc.patches.get_ir("proc_client_kyc_as_is")
    assert as_is["process"]["version"] == 19
    assert all(x["meta"]["status"] == "confirmed" for c in ELEMENT_COLLECTIONS for x in as_is[c].values())
    to_be = await svc.patches.get_ir("proc_client_kyc_to_be")
    assert to_be["process"]["derived_from"] == {"process_id": "proc_client_kyc_as_is", "version": 19}
    timeline = (await svc.export(replay.session_id))["timeline"]
    assert [e["kind"] for e in timeline[-7:]] == ["turn", "playback", "turn", "sme_answer", "phase_change", "fork",
                                                  "suggestions"]
    assert timeline[-5]["target"] == {"kind": "playback_confirm", "id": "as_is"}
    assert timeline[-1]["suggestion_ids"] == [f"S0{i}" for i in range(1, 8)]


async def test_m0_skip_parks_the_slot(svc):
    replay = await K.start(svc)
    result = await svc.answer(replay.session_id, special="skip")
    assert result.next_question.target == {"kind": "slot", "id": "C05"}
    assert result.coverage["parked"] == ["C04"]


async def test_m0_jump_to_validate(svc):
    replay = await K.start(svc)
    await svc.jump(replay.session_id, "validate")
    sess = await svc._session(replay.session_id)
    assert sess.phase == "validate"


async def test_m0_export_is_schema_valid(svc):
    replay = await K.start(svc)
    await K.to_the_end(replay)
    exported = await svc.export(replay.session_id)
    assert validate_schema(exported, "intake-session") == []
    assert [e["kind"] for e in exported["timeline"]].count("phase_change") == 4  # improve, deepen, validate, done


# ---------------------------------------------------------------- REST

@pytest.fixture
async def client(db_url, tx_sessionmaker):
    import httpx

    from apps.api.main import create_app
    from services.common.settings import Settings
    from services.identity_audit.dev import seed_dev_users
    app = create_app(Settings(env="dev", database_url=db_url, public_base_url="http://test"))
    app.state.sessionmaker = tx_sessionmaker
    app.state.clock = K.Clock()
    app.state.llm = gateway("record" if RECORD else "replay")
    async with tx_sessionmaker() as s:
        await K.seed_smes(s)
        await seed_dev_users(s)
        await s.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _auth(client, user):
    r = await client.post("/dev/token", data={"username": user})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_m0_api_start_answer_undo(client):
    sarah = await _auth(client, "user_sarah_lin")
    r = await client.post("/api/v1/intake-sessions", headers=sarah, json={
        "idea_text": K.SESSION["idea_text"], "has_process_today": "yes", "title": "Client KYC checks",
        "idea_id": "idea_client_kyc", "description": K.V0["process"]["description"],
        "domain": K.V0["process"]["domain"]})
    assert r.status_code == 201, r.text
    first = r.json()
    assert first["session_id"] == "is_client_kyc" and first["next_question"]["target"] == {"kind": "slot", "id": "C04"}

    r = await client.post("/api/v1/intake-sessions/is_client_kyc/answers", headers=sarah,
                          json={"text": K.TURNS["T1"]["answer"]["text"]})
    assert r.status_code == 200, r.text
    assert r.json()["next_question"]["target"] == {"kind": "slot", "id": "C05"}

    state = (await client.get("/api/v1/intake-sessions/is_client_kyc", headers=sarah)).json()
    t1 = next(e for e in state["timeline"] if e.get("turn") == "T1")
    assert state["next_question"]["turn"] == "T2" and state["coverage"]["percent"] == 0.14
    r = await client.post(f"/api/v1/intake-sessions/is_client_kyc/turns/{t1['seq']}/undo", headers=sarah)
    assert r.status_code == 200 and r.json()["coverage"]["percent"] == 0.08

    viewer = await _auth(client, "user_viewer")
    assert (await client.get("/api/v1/intake-sessions/is_client_kyc", headers=viewer)).status_code == 403
    r = await client.post("/api/v1/intake-sessions/is_client_kyc/answers", headers=sarah, json={})
    assert r.status_code == 422


@pytest.mark.skipif(RECORD, reason="replay-only: the sample provider cannot answer an unrecorded idea")
async def test_m0_api_llm_failure_is_a_503_and_records_nothing(client):
    sarah = await _auth(client, "user_sarah_lin")
    r = await client.post("/api/v1/intake-sessions", headers=sarah, json={
        "idea_text": "Something no cassette has heard of.", "has_process_today": "no", "idea_id": "idea_unheard"})
    assert r.status_code == 503 and r.json()["type"] == "/problems/llm-unavailable"
    assert (await client.get("/api/v1/intake-sessions/is_unheard", headers=sarah)).status_code == 404
