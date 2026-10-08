"""M3 Patch Service against Postgres: apply, rebase, review workflow, events, fork, and a full KYC replay."""
import copy

import pytest
from sqlalchemy import select

from ir_core import PatchRejected, ir_hash
from ir_core.ids import ELEMENT_COLLECTIONS
from services.common.outbox import EventOutbox
from services.ideas.db import Idea
from services.identity_audit.db import AuditLog
from services.ir_store.db import IrPatch, IrVersion, Process
from services.ir_store.service import Actor, Conflict, PatchService
from tests.conftest import KYC, SAMPLES, load

OWNER = Actor("user", "user_daniel_okafor")  # owner of the document-led sample
REQUESTER = Actor("user", "user_sarah_lin")  # owner of the KYC idea


@pytest.fixture
async def s(tx_sessionmaker):
    async with tx_sessionmaker() as session:
        for idea_id, owner in (("idea_client_onboarding", OWNER.id), ("idea_client_kyc", REQUESTER.id)):
            session.add(Idea(id=idea_id, title=idea_id, summary="", owner_user_id=owner, status="discovering",
                             has_as_is=True, session_id=f"is_{idea_id}"))
        await session.flush()
        yield session


@pytest.fixture
def svc(s):
    return PatchService(s, correlation_id="corr-test")


@pytest.fixture
async def onboarding(svc):
    """The document-led sample IR, imported at version 3."""
    return await svc.import_process(load(SAMPLES / "ir_client_onboarding.json"), actor=OWNER)


def user_patch(ops, *, base=3, pid="proc_client_onboarding", patch_id=None, author=OWNER, auto_apply=True, **extra):
    return {"patch_id": patch_id or f"p_{abs(hash(str(ops))) % 10**8}", "process_id": pid, "base_version": base,
            "ops": ops, "author": {"kind": author.kind, "id": author.id}, "reason": "test",
            "auto_apply": auto_apply, "status": "proposed", **extra}


def rename(node: str, name: str) -> list[dict]:
    return [{"op": "replace", "path": f"/nodes/{node}/name", "value": name}]


async def events(s, type_: str) -> list[dict]:
    """This test's events (other test modules commit their own to the shared database)."""
    q = select(EventOutbox).where(EventOutbox.type == type_,
                                  EventOutbox.payload["correlation_id"].astext == "corr-test")
    return [r.payload for r in (await s.execute(q.order_by(EventOutbox.created_at))).scalars()]


async def audit_actions(s, target: str) -> list[str]:
    q = select(AuditLog.action).where(AuditLog.target == target).order_by(AuditLog.at, AuditLog.id)
    return list((await s.execute(q)).scalars())


# ---------------------------------------------------------------- acceptance tests

async def test_M3_AC_M3_1(svc, s, onboarding, patch_example):
    """Applying patch_example.json to ir_client_onboarding.json (v3) produces v4 where node_high_risk_approval.actor_id
    = act_mlro, its meta.status = confirmed, and confidence ≥ 0.95."""
    # An interviewer (agent) patch after the first draft is proposed for review, then accepted by the owner.
    proposed = await svc.submit(patch_example, actor=Actor("agent", "agent:interviewer"))
    assert proposed.status == "proposed" and proposed.to_version is None
    result = await svc.accept(patch_example["patch_id"], reviewer=OWNER)
    assert (result.status, result.to_version) == ("applied", 4)

    v4 = await svc.get_ir("proc_client_onboarding")
    node = v4["nodes"]["node_high_risk_approval"]
    assert node["actor_id"] == "act_mlro"
    assert node["meta"]["status"] == "confirmed"
    assert node["meta"]["confidence"] >= 0.95
    assert v4["process"]["version"] == 4
    assert (await s.get(IrVersion, ("proc_client_onboarding", 4))).ir_hash == ir_hash(v4)
    assert (await s.get(Process, "proc_client_onboarding")).current_version == 4

    [patched] = await events(s, "ir.patched")
    assert patched["process_id"] == "proc_client_onboarding" and patched["ir_version"] == 4
    assert patched["correlation_id"] == "corr-test"
    assert patched["payload"]["from_version"] == 3 and patched["payload"]["to_version"] == 4
    assert "/nodes/node_high_risk_approval/actor_id" in patched["payload"]["changed_paths"]
    [proposal] = await events(s, "patch.proposed")
    assert proposal["payload"]["reviewer_ids"] == [OWNER.id]
    assert await audit_actions(s, patch_example["patch_id"]) == ["patch.proposed", "patch.accepted", "patch.applied"]


async def test_M3_AC_M3_3(svc, s, onboarding):
    """Two patches with base_version=3 touching different nodes both apply (second rebases).
    Two touching the same node: second returns 409 with the conflicting path."""
    a = await svc.submit(user_patch(rename("node_screening", "Screen client"), patch_id="p_a"), actor=OWNER)
    b = await svc.submit(user_patch(rename("node_id_verify", "Verify ID"), patch_id="p_b"), actor=OWNER)
    assert (a.status, a.to_version) == ("applied", 4)
    assert (b.status, b.to_version) == ("applied", 5)  # rebased onto v4
    ir = await svc.get_ir("proc_client_onboarding")
    assert ir["nodes"]["node_screening"]["name"] == "Screen client"
    assert ir["nodes"]["node_id_verify"]["name"] == "Verify ID"

    c = await svc.submit(user_patch(rename("node_screening", "Run screening"), patch_id="p_c"), actor=OWNER)
    assert c.status == "conflicted"
    assert c.conflicting_paths == ["/nodes/node_screening/name"]
    assert (c.base_version, c.current_version) == (3, 5)
    assert (await s.get(IrPatch, "p_c")).status == "conflicted"
    assert (await svc.get_ir("proc_client_onboarding"))["nodes"]["node_screening"]["name"] == "Screen client"
    assert await audit_actions(s, "p_c") == ["patch.conflicted"]


async def test_m3_rebase_conflicts_on_ancestor_paths(svc, onboarding):
    """'Overlaps' = one path is a prefix of the other (M3)."""
    await svc.submit(user_patch(rename("node_screening", "X"), patch_id="p1"), actor=OWNER)
    node = copy.deepcopy(onboarding["nodes"]["node_screening"])
    whole = await svc.submit(user_patch([{"op": "replace", "path": "/nodes/node_screening", "value": node}],
                                        patch_id="p2"), actor=OWNER)
    assert whole.status == "conflicted" and whole.conflicting_paths == ["/nodes/node_screening"]
    # Different fields of the same node do not overlap, so they rebase cleanly.
    other_field = await svc.submit(user_patch([{"op": "add", "path": "/nodes/node_screening/outcome",
                                                "value": "Client screened"}], patch_id="p3"), actor=OWNER)
    assert other_field.status == "applied"


# ---------------------------------------------------------------- the KYC session, replayed through M3

async def test_m3_kyc_session_replays_through_patch_service(svc, s):
    """Every timeline patch of samples/client_kyc goes through submit (and review where an agent wrote it), the as-is
    is forked into the to-be, and the final IRs match the stored samples."""
    session = load(KYC / "intake_session_kyc.json")
    v0 = load(KYC / "ir_v0_empty.json")  # v0 already holds the intake session's source
    p = v0["process"]
    await svc.import_process(v0, actor=REQUESTER)

    pid = {"as_is": p["id"], "to_be": None}
    for e in session["timeline"]:
        variant = e.get("process", "as_is")
        if e["kind"] == "fork":
            f = e["fork"]
            result = await svc.fork(pid["as_is"], actor=REQUESTER, to_process_id=f["to_process_id"],
                                    name=f["process_overrides"]["name"],
                                    description=f["process_overrides"]["description"])
            assert result.fork == f
            pid["to_be"] = result.to_be_process_id
            continue
        if not e.get("ops"):
            continue
        proc = await svc.get_process(pid[variant])
        is_agent = (e.get("author") or "").startswith("agent:")
        patch = user_patch(e["ops"], base=proc.current_version, pid=pid[variant], patch_id=e["patch_id"],
                           author=Actor("agent", e["author"]) if is_agent else REQUESTER)
        if e["kind"] == "sme_answer":
            patch["evidence"] = {"question_id": e["question_id"], "answer_id": f"ans_{e['question_id']}"}
        result = await svc.submit(patch, actor=Actor("agent", e["author"]) if is_agent else REQUESTER)
        if is_agent:  # agent patches after the first draft wait for review
            assert result.status == "proposed", e["seq"]
            result = await svc.accept(e["patch_id"], reviewer=REQUESTER)
        assert (result.status, result.to_version) == ("applied", e["ir_version_after"]), e["seq"]

    for variant, stored_file in (("as_is", "ir_client_kyc_as_is.json"), ("to_be", "ir_client_kyc_to_be.json")):
        got, want = await svc.get_ir(pid[variant]), load(KYC / stored_file)
        for coll in ELEMENT_COLLECTIONS + ["sources", "scope"]:
            assert got[coll] == want[coll], f"{variant}.{coll}"
        # Status moves to 'ready' through DoR sign-off (P3); updated_at is the replay's own clock.
        same = {k: v for k, v in got["process"].items() if k not in ("status", "updated_at")}
        assert same == {k: v for k, v in want["process"].items() if k not in ("status", "updated_at")}
        assert "stories" not in got
        for row in (await s.execute(select(IrVersion).where(IrVersion.process_id == pid[variant]))).scalars():
            assert row.ir_hash == ir_hash(row.snapshot)

    as_is, idea = await s.get(Process, pid["as_is"]), await s.get(Idea, "idea_client_kyc")
    assert as_is.frozen_at is not None and as_is.current_version == 19
    assert (idea.as_is_process_id, idea.to_be_process_id) == (pid["as_is"], pid["to_be"])
    with pytest.raises(Conflict) as exc:  # the as-is is read-only after the fork
        await svc.submit(user_patch(rename("node_screen", "x"), base=19, pid=pid["as_is"], author=REQUESTER),
                         actor=REQUESTER)
    assert exc.value.problem == "/problems/process-frozen"


# ---------------------------------------------------------------- fork rules

async def test_m3_fork_requires_a_confirmed_as_is(svc, onboarding):
    with pytest.raises(Conflict) as exc:
        await svc.fork("proc_client_onboarding", actor=OWNER)
    assert exc.value.problem == "/problems/as-is-not-confirmed"
    assert "node_screening" in exc.value.extra["unconfirmed"]


async def test_m3_fork_once_and_only_from_an_as_is(svc, s):
    as_is = load(KYC / "ir_client_kyc_as_is.json")
    await svc.import_process(as_is, actor=REQUESTER)
    result = await svc.fork("proc_client_kyc_as_is", actor=REQUESTER)
    assert result.to_be_process_id == "proc_client_kyc_to_be"
    to_be = await svc.get_ir("proc_client_kyc_to_be")
    assert to_be["process"]["derived_from"] == {"process_id": "proc_client_kyc_as_is", "version": 19}
    assert (to_be["process"]["variant"], to_be["process"]["version"], to_be["process"]["status"]) == \
        ("to_be", 0, "draft")
    assert to_be["nodes"] == as_is["nodes"]
    assert await audit_actions(s, "proc_client_kyc_as_is") == ["process.imported", "process.forked"]

    for pid, problem in (("proc_client_kyc_as_is", "/problems/already-forked"),
                         ("proc_client_kyc_to_be", "/problems/not-an-as-is")):
        with pytest.raises(Conflict) as exc:
            await svc.fork(pid, actor=REQUESTER)
        assert exc.value.problem == problem


async def test_m3_idea_owns_at_most_one_process_per_variant(svc):
    await svc.create_process(name="KYC today", owner_user_id=REQUESTER.id, idea_id="idea_client_kyc", actor=REQUESTER)
    with pytest.raises(Exception, match="uq_processes_idea_id_variant"):
        await svc.create_process(name="KYC again", owner_user_id=REQUESTER.id, idea_id="idea_client_kyc",
                                 actor=REQUESTER)


async def test_m3_create_process_rejects_unknown_idea(svc):
    with pytest.raises(PatchRejected, match="unknown idea"):
        await svc.create_process(name="X", owner_user_id="u", idea_id="idea_nope", actor=OWNER)


async def test_m3_create_process_starts_from_an_empty_ir(svc):
    """POST /processes gives the same v0 as the KYC sample, minus the intake source M0 adds at the start."""
    v0 = load(KYC / "ir_v0_empty.json")
    p = v0["process"]
    created = await svc.create_process(process_id=p["id"], name=p["name"], owner_user_id=p["owner_user_id"],
                                       domain=p["domain"], description=p["description"], idea_id=p["idea_id"],
                                       actor=REQUESTER)
    assert created["process"]["updated_at"] != p["updated_at"]
    assert {**created, "process": {**created["process"], "updated_at": p["updated_at"]}} == {**v0, "sources": {}}


async def test_m3_create_process_generates_free_ids(svc):
    a = await svc.create_process(name="Client KYC (pilot)", owner_user_id="u", actor=OWNER)
    b = await svc.create_process(name="Client KYC (pilot)", owner_user_id="u", actor=OWNER)
    assert (a["process"]["id"], b["process"]["id"]) == ("proc_client_kyc_pilot", "proc_client_kyc_pilot_2")


# ---------------------------------------------------------------- review workflow

async def test_m3_first_draft_agent_patch_auto_applies(svc):
    await svc.create_process(name="Draft", owner_user_id="u", process_id="proc_draft", actor=OWNER)
    extractor = Actor("agent", "agent:extractor")
    ops = [{"op": "add", "path": "/glossary/term_kyc", "value": {
        "term": "KYC", "ambiguous": False, "meta": {"status": "proposed", "confidence": 0, "provenance": []}}}]
    first = await svc.submit(user_patch(ops, base=0, pid="proc_draft", author=extractor), actor=extractor)
    assert first.status == "applied"
    rename_term = [{"op": "replace", "path": "/glossary/term_kyc/term", "value": "Know your client"}]
    later = await svc.submit(user_patch(rename_term, base=1, pid="proc_draft", author=extractor), actor=extractor)
    assert later.status == "proposed"


async def test_m3_reject_requires_reason_and_is_final(svc, s, onboarding):
    await svc.submit(user_patch(rename("node_screening", "X"), patch_id="p_r", auto_apply=False), actor=OWNER)
    with pytest.raises(PatchRejected, match="reason"):
        await svc.reject("p_r", reviewer=OWNER, reason=" ")
    row = await svc.reject("p_r", reviewer=OWNER, reason="Name is fine as it is")
    assert (row.status, row.review_reason, row.reviewed_by) == ("rejected", "Name is fine as it is", OWNER.id)
    with pytest.raises(Conflict):
        await svc.accept("p_r", reviewer=OWNER)
    assert (await svc.get_process("proc_client_onboarding")).current_version == 3


async def test_m3_edit_and_accept_supersedes_the_original(svc, s, onboarding):
    await svc.submit(user_patch(rename("node_screening", "Screening!!"), patch_id="p_orig", auto_apply=False),
                     actor=OWNER)
    result = await svc.accept("p_orig", reviewer=OWNER, ops=rename("node_screening", "Screening"),
                              reason="Tidied the wording")
    assert (result.status, result.to_version) == ("applied", 4)
    edited, original = await s.get(IrPatch, result.patch_id), await s.get(IrPatch, "p_orig")
    assert edited.supersedes_patch_id == "p_orig" and edited.author_id == OWNER.id
    assert original.status == "superseded" and original.review_reason == "Tidied the wording"
    assert (await svc.get_ir("proc_client_onboarding"))["nodes"]["node_screening"]["name"] == "Screening"


async def test_m3_invalid_edit_leaves_original_proposed(svc, s, onboarding):
    await svc.submit(user_patch(rename("node_screening", "A"), patch_id="p_keep", auto_apply=False), actor=OWNER)
    with pytest.raises(PatchRejected):
        await svc.accept("p_keep", reviewer=OWNER, ops=[{"op": "replace", "path": "/stories/story_screening/title",
                                                         "value": "x"}])
    assert (await s.get(IrPatch, "p_keep")).status == "proposed"


async def test_m3_resubmitting_the_same_patch_is_idempotent(svc, onboarding):
    patch = user_patch(rename("node_screening", "X"), patch_id="p_same")
    first = await svc.submit(patch, actor=OWNER)
    again = await svc.submit(copy.deepcopy(patch), actor=OWNER)
    assert (again.status, again.to_version) == (first.status, first.to_version) == ("applied", 4)
    with pytest.raises(Conflict) as exc:
        await svc.submit({**patch, "ops": rename("node_screening", "Y")}, actor=OWNER)
    assert exc.value.problem == "/problems/patch-id-reused"


@pytest.mark.parametrize("ops,match", [
    ([{"op": "add", "path": "/edges/edge_x", "value": {"from": "node_screening", "to": "node_gone", "meta": {
        "status": "proposed", "confidence": 0, "provenance": []}}}], "node_gone"),
    ([{"op": "replace", "path": "/stories/story_screening/title", "value": "x"}], "read-only"),
    ([{"op": "replace", "path": "/process/version", "value": 9}], "read-only"),
    ([{"op": "remove", "path": "/nodes/node_nowhere"}], "patch_op"),
])
async def test_m3_invalid_patches_are_rejected_and_not_stored(svc, s, onboarding, ops, match):
    with pytest.raises(PatchRejected, match=match):
        await svc.submit(user_patch(ops, patch_id="p_bad"), actor=OWNER)
    assert await s.get(IrPatch, "p_bad") is None


async def test_m3_invalid_proposal_is_rejected_at_submit(svc, s, onboarding):
    ops = [{"op": "replace", "path": "/nodes/node_screening/actor_id", "value": "act_ghost"}]
    with pytest.raises(PatchRejected, match="act_ghost"):
        await svc.submit(user_patch(ops, auto_apply=False), actor=OWNER)


async def test_m3_base_version_ahead_is_invalid(svc, onboarding):
    with pytest.raises(PatchRejected, match="ahead"):
        await svc.submit(user_patch(rename("node_screening", "X"), base=7), actor=OWNER)


async def test_m3_answer_patch_must_confirm_something(svc, onboarding, patch_example):
    patch = {**patch_example, "ops": [op for op in patch_example["ops"]
                                      if "/meta" not in op["path"] and "confirmed_by" not in op["path"]]}
    with pytest.raises(PatchRejected, match="must confirm"):
        await svc.submit(patch, actor=Actor("agent", "agent:interviewer"))


async def test_m3_patch_after_export_reopens_review(svc, s, onboarding):
    await svc.submit(user_patch([{"op": "replace", "path": "/process/status", "value": "exported"}], patch_id="p1"),
                     actor=OWNER)
    await svc.submit(user_patch(rename("node_screening", "X"), base=4, patch_id="p2"), actor=OWNER)
    assert (await svc.get_ir("proc_client_onboarding"))["process"]["status"] == "in_review"
    assert (await s.get(Process, "proc_client_onboarding")).status == "in_review"


async def test_m3_diff_and_versions(svc, onboarding):
    await svc.submit(user_patch(rename("node_screening", "Screen"), patch_id="p1"), actor=OWNER)
    diff = await svc.diff("proc_client_onboarding", 3, 4)
    paths = {d["path"] for d in diff}
    assert "/nodes/node_screening/name" in paths and "/process/version" in paths
    assert (await svc.get_ir("proc_client_onboarding", 3))["nodes"]["node_screening"]["name"] != "Screen"
    with pytest.raises(LookupError):
        await svc.get_ir("proc_client_onboarding", 9)
