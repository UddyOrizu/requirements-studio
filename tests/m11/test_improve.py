"""M11: heuristics and guardrails (pure), and the service on the replayed KYC session (cassettes)."""
import copy
import os

import pytest
from sqlalchemy import select

from flow_renderer import render_drawio
from improve import candidates, cases_per_month, check, complete_ops, protected_approvals
from ir_core.ids import ELEMENT_COLLECTIONS
from services.improve.db import SuggestionRow
from services.improve.service import ImproveService
from services.intake.service import IntakeService
from services.ir_store.db import IrPatch
from tests.conftest import KYC, load
from tests.m0 import kyc_replay as K
from tests.m0.test_intake import gateway
from tests.oracle import replayed_irs

RECORD = os.environ.get("RS_RECORD_CASSETTES") == "1"
AS_IS = load(KYC / "ir_client_kyc_as_is.json")
SUGGESTIONS = load(KYC / "suggestions_client_kyc.json")
REPLAYED = dict(replayed_irs())
TO_BE_V1 = REPLAYED["to_be@v1"]  # fork + improvement source, before any suggestion
TURNS = {e["turn"]: e["answer"]["text"] for e in K.TIMELINE if e.get("turn")}
SME = {"src_answer_q_intake_01": [next(e for e in K.TIMELINE if e["kind"] == "sme_answer")["answer"]["text"]]}


def guard(s, to_be=TO_BE_V1, **kw):
    return check(copy.deepcopy(s), to_be, protected=protected_approvals(AS_IS), cases=cases_per_month(AS_IS),
                 turn_answers=TURNS, source_texts=SME, **kw)


# ---------------------------------------------------------------- pure

def test_M11_AC_M11_2_candidates():
    """Heuristics produce candidates for S01–S06 (and S07 at low confidence); MLRO approval is protected."""
    found = {c.target_ref: c for c in candidates(AS_IS)}
    for s in SUGGESTIONS:
        [ref] = s["target_refs"]
        assert found[ref].kind == s["kind"], s["suggestion_id"]
    assert found["/nodes/node_analyst_review"].confidence_hint == "low"
    assert set(found) - {s["target_refs"][0] for s in SUGGESTIONS} == {"/nodes/node_mlro_approval"}
    assert protected_approvals(AS_IS) == {"node_mlro_approval":
                                          "The final decision on high-risk clients (stays with the MLRO)"}


@pytest.mark.parametrize("s", SUGGESTIONS, ids=lambda s: s["suggestion_id"])
def test_M11_AC_M11_3(s):
    """Every sample suggestion passes the guardrails unchanged: verbatim evidence, hours = minutes × 150 / 60."""
    verdict = guard(s, qualitative=s["benefit"].get("qualitative"))
    assert verdict.suggestion is not None and verdict.notes == []
    assert verdict.suggestion["evidence"] == s["evidence"]
    assert verdict.suggestion["benefit"] == s["benefit"]
    if s["benefit"]["minutes_saved_per_case"] is not None:
        assert s["benefit"]["hours_saved_per_month"] == s["benefit"]["minutes_saved_per_case"] * 150 / 60


def test_m11_guardrail_1_protected_approval():
    s = {**copy.deepcopy(SUGGESTIONS[6]), "target_refs": ["/nodes/node_mlro_approval"],
         "ops": [{"op": "replace", "path": "/nodes/node_mlro_approval/hitl/mode", "value": "automated"}]}
    verdict = guard(s)
    assert verdict.suggestion is None and "stays with the MLRO" in verdict.not_suggested["reason"]


def test_m11_guardrail_2_needs_a_control_and_a_person_for_failures():
    assert guard({**SUGGESTIONS[0], "controls": " "}).suggestion is None
    s3 = copy.deepcopy(SUGGESTIONS[2])  # verify IDs: drop the human queue it adds
    s3["ops"] = [op for op in s3["ops"] if "exc_id_check_failed" not in op["path"]
                 and not op["path"].endswith("/exception_ids")]
    verdict = guard(s3)
    assert verdict.suggestion["kind"] == "automate_with_review"
    mode = next(op for op in verdict.suggestion["ops"] if op["path"].endswith("/hitl/mode"))
    assert mode["value"] == "hitl_review"
    assert any(op["path"] == "/nodes/node_verify_id/hitl/trigger" for op in verdict.suggestion["ops"])


def test_m11_guardrail_3_evidence_must_be_verbatim():
    s = copy.deepcopy(SUGGESTIONS[0])
    s["evidence"][0]["excerpt"] = "we never use the portal"
    verdict = guard(s)
    assert len(verdict.suggestion["evidence"]) == 1 and verdict.notes
    s["evidence"] = [s["evidence"][0]]
    assert guard(s).suggestion is None


def test_m11_guardrail_4_benefit_is_computed():
    s = {**copy.deepcopy(SUGGESTIONS[1]), "benefit": {"minutes_saved_per_case": 999}}
    assert guard(s).suggestion["benefit"] == {"minutes_saved_per_case": 30, "cases_per_month": 150,
                                              "hours_saved_per_month": 75.0}


def test_m11_guardrail_5_ops_stay_in_scope_and_validate():
    out_of_scope = copy.deepcopy(SUGGESTIONS[1])
    out_of_scope["ops"].append({"op": "replace", "path": "/nodes/node_decline/name", "value": "x"})
    assert "outside the step" in guard(out_of_scope).not_suggested["reason"]
    invalid = copy.deepcopy(SUGGESTIONS[1])
    invalid["ops"].append({"op": "replace", "path": "/nodes/node_chase_docs/hitl/mode", "value": "magic"})
    assert "would not validate" in guard(invalid).not_suggested["reason"]


def test_m11_complete_ops_adds_what_accepting_implies():
    s = copy.deepcopy(SUGGESTIONS[2])
    assert complete_ops(s, TO_BE_V1, source_id="src_improve_is_client_kyc", requester_id="user_sarah_lin") == s["ops"]
    bare = {**s, "ops": [op for op in s["ops"]
                         if not op["path"].endswith("/change") and "provenance" not in op["path"]]}
    exc = next(op for op in bare["ops"] if op["path"] == "/exceptions/exc_id_check_failed")
    exc["value"]["meta"] = {"status": "proposed", "confidence": 0, "provenance": []}
    ops = complete_ops(bare, TO_BE_V1, source_id="src_improve_is_client_kyc", requester_id="user_sarah_lin")
    assert ops[0] == {"op": "add", "path": "/nodes/node_verify_id/change",
                      "value": {"kind": "automated", "suggestion_id": "S03", "was": "human_task"}}
    assert ops[-1]["value"]["locator"] == {"kind": "suggestion", "value": "S03"}
    assert next(op for op in ops if op["path"] == "/exceptions/exc_id_check_failed")["value"]["meta"]["status"] \
        == "confirmed"


# ---------------------------------------------------------------- service (replayed session)

@pytest.fixture
async def db(tx_sessionmaker):
    async with tx_sessionmaker() as session:
        await K.seed_smes(session)
        yield session


@pytest.fixture
def intake(db):
    return IntakeService(db, gateway("record" if RECORD else "replay"), clock=K.Clock(), correlation_id="corr-m11")


@pytest.fixture
def improve(intake):
    return ImproveService(intake.s, intake.llm, clock=intake.clock, correlation_id="corr-m11")


async def _to_improve(intake):
    replay = await K.start(intake)
    await K.discover(replay)
    return replay


async def test_M11_AC_M11_1(intake):
    """After the as-is is confirmed (T17), a fork creates proc_client_kyc_to_be with derived_from set."""
    await _to_improve(intake)
    to_be = await intake.patches.get_ir("proc_client_kyc_to_be")
    assert to_be["process"]["derived_from"] == {"process_id": "proc_client_kyc_as_is", "version": 19}
    assert to_be["process"]["variant"] == "to_be"


async def test_M11_AC_M11_2_generated(intake, improve):
    """Generated suggestions match the sample in target, kind and benefit; none touches node_mlro_approval."""
    await _to_improve(intake)
    got = await improve.list_suggestions("idea_client_kyc")
    assert [(s["suggestion_id"], s["target_refs"], s["kind"], s["benefit"]) for s in got] == \
        [(s["suggestion_id"], s["target_refs"], s["kind"], s["benefit"]) for s in SUGGESTIONS]
    assert not any("node_mlro_approval" in op["path"] for s in got for op in s["ops"])
    session = await intake.export(K.SESSION["session_id"])
    entry = next(e for e in session["timeline"] if e["kind"] == "suggestions")
    row = await intake._entries(await intake._session(K.SESSION["session_id"]))
    not_suggested = next(r for r in row if r.kind == "suggestions").payload["not_suggested"]
    assert [n["target"] for n in not_suggested] == ["MLRO approval of high-risk client"]
    assert any(c.startswith("Not suggested: MLRO approval") for c in entry["captured"])
    assert entry["captured"][0] == "7 improvement suggestions, about 275 analyst hours a month if all accepted"


async def test_M11_AC_M11_4(intake, improve, db):
    """Accepting S01–S06 and rejecting S07 gives the to-be before Deepen; each patch equals the recorded one."""
    replay = await _to_improve(intake)
    await K.improve(replay)
    v7 = await intake.patches.get_ir("proc_client_kyc_to_be", 7)
    want = REPLAYED["to_be@v7"]
    for coll in [*ELEMENT_COLLECTIONS, "scope"]:
        assert {k: _no_conf(v) for k, v in v7[coll].items()} == {k: _no_conf(v) for k, v in want[coll].items()}, coll
    rows = {r.id: r for r in (await db.execute(select(SuggestionRow))).scalars()}
    for entry in K.TIMELINE:
        if entry["kind"] == "suggestion_decision" and entry["decision"] == "accepted":
            patch = await db.get(IrPatch, rows[entry["suggestion_id"]].applied_patch_id)
            assert patch.ops == entry["ops"], entry["suggestion_id"]
    assert rows["S07"].decision["reason"] == K.REJECT_REASON and rows["S07"].applied_patch_id is None


def _no_conf(x):
    x = copy.deepcopy(x)
    if isinstance(x, dict) and "meta" in x:
        x["meta"].pop("confidence", None)
    return x


async def test_M11_AC_M11_5(intake, improve):
    """change.suggestion_id is set exactly on the accepted set; the flow labels them; the report totals ~275 h."""
    replay = await _to_improve(intake)
    await K.improve(replay)
    to_be = await intake.patches.get_ir("proc_client_kyc_to_be")
    changed = {n["change"]["suggestion_id"] for n in to_be["nodes"].values() if n.get("change")}
    assert changed == {f"S0{i}" for i in range(1, 7)}
    drawio = render_drawio(to_be)
    assert all(f"Changed by {sid}" in drawio for sid in changed) and "Changed by S07" not in drawio
    report = await improve.report("idea_client_kyc")
    assert "**6 accepted, 1 rejected.**" in report and "about **275 analyst hours a month**" in report


async def test_m11_decisions_are_final_and_reject_needs_a_reason(intake, improve):
    await _to_improve(intake)
    with pytest.raises(Exception, match="reason"):
        await improve.reject("idea_client_kyc", "S07", user_id="user_sarah_lin", reason=" ")
    await improve.accept("idea_client_kyc", "S01", user_id="user_sarah_lin")
    with pytest.raises(Exception, match="already accepted"):
        await improve.accept("idea_client_kyc", "S01", user_id="user_sarah_lin")


async def test_m11_edit_then_accept(intake, improve):
    await _to_improve(intake)
    edited = await improve.edit("idea_client_kyc", "S07", user_id="user_sarah_lin",
                                instruction="Do it, but have an analyst review every auto-approval")
    assert edited["status"] == "edited" and edited["controls"].startswith("An analyst reviews every")
    accepted = await improve.accept("idea_client_kyc", "S07", user_id="user_sarah_lin")
    assert accepted["status"] == "accepted"


async def test_m11_accept_remaining_moves_on_to_deepen(intake, improve):
    await _to_improve(intake)
    await improve.reject("idea_client_kyc", "S07", user_id="user_sarah_lin", reason="Needs judgement")
    decided = await improve.accept_remaining("idea_client_kyc", user_id="user_sarah_lin")
    assert [s["suggestion_id"] for s in decided] == [f"S0{i}" for i in range(1, 7)]
    assert (await intake._session(K.SESSION["session_id"])).phase == "deepen"
