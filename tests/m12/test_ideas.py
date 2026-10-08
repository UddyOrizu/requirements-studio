"""M12 against Postgres: the seeded sample scenarios, stories, flows, refinement (cassettes), edits and undo."""
import os

import pytest
from sqlalchemy import select

from exporters import compare_rows
from ir_core import canonical_json
from services.ideas.refine import OutOfScope, RefinementService
from services.ideas.seed import seed
from services.ideas.service import IdeasService
from services.ir_store.db import IrPatch
from services.ir_store.service import content_view
from tests.conftest import KYC, SAMPLES, load
from tests.m0.test_intake import gateway
from tests.m12.refinements import MERGE, OUT_OF_SCOPE, QUESTION, SPLIT, T21
from tests.oracle import replayed_irs

RECORD = os.environ.get("RS_RECORD_CASSETTES") == "1"
SARAH = "user_sarah_lin"


@pytest.fixture
async def db(tx_sessionmaker):
    async with tx_sessionmaker() as session:
        yield session


@pytest.fixture
def ideas(db):
    return IdeasService(db, gateway("record" if RECORD else "replay"), correlation_id="m12")


@pytest.fixture
def refiner(db, ideas):
    return RefinementService(db, ideas.llm, correlation_id="m12")


async def test_M12_AC_M12_1(db, ideas):
    """GET /ideas returns both sample ideas with the stats shown in samples/ideas_index.json."""
    await seed(db, "samples")
    got = {i["idea_id"]: i for i in await ideas.list_ideas()}
    for want in load(SAMPLES / "ideas_index.json"):
        assert {k: got[want["idea_id"]][k] for k in want} == want, want["idea_id"]
    assert [i["idea_id"] for i in await ideas.list_ideas()] == ["idea_client_kyc", "idea_client_onboarding"]
    assert [i["idea_id"] for i in await ideas.list_ideas(q="document-led")] == ["idea_client_onboarding"]
    assert [i["idea_id"] for i in await ideas.list_ideas(status="ready")] == ["idea_client_kyc"]
    assert [i["idea_id"] for i in await ideas.list_ideas(tag="aml")] == ["idea_client_kyc"]
    kyc = got["idea_client_kyc"]
    assert kyc["waiting_on"] == ["sme_priya_shah"] and kyc["thumbnail"]["nodes"]


async def test_M12_AC_M12_2(db, ideas):
    """KYC offers as-is and to-be flows; Compare lists the 9 to-be tasks like 'What changes from today'."""
    await seed(db, "samples")
    assert (await ideas.flow("idea_client_kyc", "as_is", "json"))["variant"] == "as_is"
    assert (await ideas.flow("idea_client_kyc", "to_be", "json"))["variant"] == "to_be"
    assert await ideas.flow("idea_client_kyc", "to_be", "drawio") == \
        (KYC / "flow" / "to_be_process_flow.drawio").read_text()
    compare = await ideas.compare("idea_client_kyc")
    want = compare_rows(load(KYC / "ir_client_kyc_as_is.json"), load(KYC / "ir_client_kyc_to_be.json"))
    assert [[r["step"], r["today"], r["minutes_today"] or "", r["to_be"], r["change"]] for r in compare["rows"]] == want
    assert len(compare["rows"]) == 9
    table = [line for line in (KYC / "stories_client_kyc.md").read_text().splitlines()
             if line.startswith("| ") and "S0" in line or "Unchanged |" in line]
    assert len(table) == 9 and all(r["step"] in t for r, t in zip(compare["rows"], table, strict=True))


async def test_M12_AC_M12_3(db, ideas, refiner):
    """Refining story_record_kyc with the T21 instruction previews and applies exactly the T21 ops."""
    await seed(db, "kyc_before_refinement")
    preview = await refiner.preview("idea_client_kyc", "story_record_kyc", instruction=T21["answer"]["text"],
                                    user_id=SARAH)
    assert preview["kind"] == "preview" and preview["ops"] == T21["ops"] and preview["turn_id"] == "T21"
    assert "CRM unavailable" in preview["stories_after"]["story_record_kyc"]
    assert "New human queue 'CRM unavailable' in the Onboarding Analyst lane" in preview["flow_changes"]
    applied = await refiner.apply("idea_client_kyc", "story_record_kyc", preview["preview_id"], user_id=SARAH)
    assert (await db.get(IrPatch, applied["patch_id"])).ops == T21["ops"] and applied["to_version"] == 11
    to_be = await ideas.patches.get_ir("proc_client_kyc_to_be")
    assert content_view(to_be) == content_view(dict(replayed_irs())["to_be@v11"])
    story = await ideas.story("idea_client_kyc", "story_record_kyc")
    assert any(e["ref"] == "exc_crm_unavailable" for e in story["story"]["edge_cases"])
    flow = await ideas.flow("idea_client_kyc", "to_be", "json")
    queue = next(n for n in flow["nodes"] if n["id"] == "queue_exc_crm_unavailable")
    assert queue["lane"] == "act_onboarding_analyst"
    session = await db.get(__import__("services.intake.db", fromlist=["IntakeSession"]).IntakeSession,
                           "is_client_kyc")
    assert session.state["turns"] == 21


async def test_M12_AC_M12_4(db, ideas, refiner):
    """A split gives two tasks, rewired edges, both stories rendered and DoR evaluated; undo restores it exactly."""
    await seed(db, "kyc_before_refinement")
    before = await ideas.patches.get_ir("proc_client_kyc_to_be")
    preview = await refiner.preview("idea_client_kyc", "story_request_docs", instruction=SPLIT, user_id=SARAH)
    assert set(preview["stories_after"]) == {"story_request_docs", "story_handle_replies"}
    assert "New connection node_handle_replies → node_verify_id" in preview["flow_changes"]
    applied = await refiner.apply("idea_client_kyc", "story_request_docs", preview["preview_id"], user_id=SARAH)
    after = await ideas.patches.get_ir("proc_client_kyc_to_be")
    assert after["edges"]["edge_await_verify"]["to"] == "node_handle_replies"
    stories = {s["story_id"]: s for s in await ideas.stories("idea_client_kyc")}
    assert {"story_request_docs", "story_handle_replies"} <= set(stories) and len(stories) == 10
    assert all(s["dor_status"] in ("ready", "not_ready") and "failed_checks" in s for s in stories.values())
    history = await ideas.history("idea_client_kyc", "story_request_docs")
    assert history[0]["patch_id"] == applied["patch_id"]
    await ideas.undo("idea_client_kyc", applied["patch_id"], user_id=SARAH)
    restored = await ideas.patches.get_ir("proc_client_kyc_to_be")
    assert canonical_json(content_view(restored)) == canonical_json(content_view(before))
    assert len(await ideas.stories("idea_client_kyc")) == 9


async def test_m12_merge_combines_two_adjacent_tasks(db, ideas, refiner):
    """Merge: the neighbouring task goes, its edge and SLA route are rewired, its AC moves; undo restores it."""
    await seed(db, "kyc_before_refinement")
    before = await ideas.patches.get_ir("proc_client_kyc_to_be")
    preview = await refiner.preview("idea_client_kyc", "story_request_docs", instruction=MERGE, user_id=SARAH)
    assert set(preview["stories_after"]) == {"story_request_docs"}
    assert any(c.startswith("Removed 'Chase missing documents") for c in preview["flow_changes"])
    applied = await refiner.apply("idea_client_kyc", "story_request_docs", preview["preview_id"], user_id=SARAH)
    after = await ideas.patches.get_ir("proc_client_kyc_to_be")
    assert "node_chase_docs" not in after["nodes"] and "edge_chase_await" not in after["edges"]
    assert after["slas"]["sla_docs_due"]["breach_action"]["target_node_id"] == "node_request_docs"
    stories = {s["story_id"]: s for s in await ideas.stories("idea_client_kyc")}
    assert "story_chase_docs" not in stories and len(stories) == 8
    detail = await ideas.story("idea_client_kyc", "story_request_docs")
    assert "ac_chase_docs" in detail["editable"]["acceptance_criteria"]
    await ideas.undo("idea_client_kyc", applied["patch_id"], user_id=SARAH)
    restored = await ideas.patches.get_ir("proc_client_kyc_to_be")
    assert canonical_json(content_view(restored)) == canonical_json(content_view(before))


async def test_M12_AC_M12_5(db, refiner):
    """An instruction that would change elements outside the story is rejected with an explanation."""
    await seed(db, "kyc_before_refinement")
    with pytest.raises(OutOfScope) as exc:
        await refiner.preview("idea_client_kyc", "story_record_kyc", instruction=OUT_OF_SCOPE, user_id=SARAH)
    [issue] = exc.value.errors
    assert issue.path == "/nodes/node_decline/name" and "Decline client" in issue.message
    assert "outside the story" in issue.message


async def test_m12_a_question_is_answered_without_changes(db, ideas, refiner):
    await seed(db, "kyc_before_refinement")
    result = await refiner.preview("idea_client_kyc", "story_record_kyc", instruction=QUESTION, user_id=SARAH)
    assert result["kind"] == "answer" and result["answer"].startswith("Nobody approves recording")
    assert (await ideas.patches.get_process("proc_client_kyc_to_be")).current_version == 10


async def test_m12_inline_edits_are_patches(db, ideas):
    await seed(db, "kyc_before_refinement")
    story = await ideas.edit("idea_client_kyc", "story_chase_docs", user_id=SARAH, field="priority", value="could")
    assert story["priority"] == "could"
    story = await ideas.edit("idea_client_kyc", "story_chase_docs", user_id=SARAH, field="acceptance_criterion",
                             ac_id="ac_chase_docs", part="then", value=["a reminder is sent on day 5"])
    assert story["editable"]["acceptance_criteria"]["ac_chase_docs"]["then"] == ["a reminder is sent on day 5"]
    with pytest.raises(Exception, match="criteria"):
        await ideas.edit("idea_client_kyc", "story_chase_docs", user_id=SARAH, field="control_mode",
                         value="approval")
    history = await ideas.history("idea_client_kyc", "story_chase_docs")
    assert [h["reason"] for h in history[:2]] == ["Edited acceptance criterion of Chase missing documents",
                                                  "Edited priority of Chase missing documents"]


async def test_m12_ask_someone_adds_an_open_question(db, ideas):
    await seed(db, "kyc_before_refinement")
    result = await ideas.ask("idea_client_kyc", "story_decline", user_id=SARAH,
                             text="Must the decline letter be reviewed by legal?", sme_id="sme_priya_shah")
    assert result["captured"].startswith("Asked Priya Shah (MLRO)")
    [question] = result["story"]["story"]["open_questions"]
    assert question["asked_to"] == "sme_priya_shah"


async def test_m12_signoff_survives_unrelated_changes(db, ideas):
    """M8: a sign-off holds while the story's closure hash is unchanged."""
    await seed(db, "samples")
    await ideas.edit("idea_client_kyc", "story_chase_docs", user_id=SARAH, field="outcome",
                     value="late documents are chased automatically")
    rows = {s["story_id"]: s for s in await ideas.stories("idea_client_kyc")}
    assert rows["story_chase_docs"]["failed_checks"] == ["DOR-11"]
    assert rows["story_decline"]["dor_status"] == "ready"


async def test_m12_seed_replays_the_session(db, ideas):
    await seed(db, "samples")
    to_be = await ideas.patches.get_ir("proc_client_kyc_to_be")
    stored = load(KYC / "ir_client_kyc_to_be.json")
    stored.pop("stories")
    assert content_view(to_be)["nodes"] == content_view(stored)["nodes"]
    patches = (await db.execute(select(IrPatch.id).where(IrPatch.process_id == "proc_client_kyc_to_be"))).scalars()
    assert "patch_kyc_tobe_v11" in set(patches)
