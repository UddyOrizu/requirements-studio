"""Approval requests over HTTP: a named user is emailed and decides in the app; the decision runs through the owning
service (M3 patch, M8 sign-off, M11 suggestion, M6 question) and the requester is emailed the outcome."""
import httpx
import pytest
from sqlalchemy import delete, select

from apps.api.main import create_app
from services.common.outbox import EventOutbox
from services.common.settings import Settings
from services.ideas.seed import seed
from services.identity_audit.db import AuditLog
from services.improve.db import SuggestionRow
from services.intake.db import IntakeSession, IntakeTurn, Signoff
from services.interviewer.db import Answer, Question
from services.ir_store.service import Actor, PatchService
from tests.identity.test_users import Clock
from tests.m0.test_intake import gateway

ONBOARDING = "/api/v1/processes/proc_client_onboarding"
RENAME = [{"op": "replace", "path": "/nodes/node_screening/name", "value": "Screen the client"}]


@pytest.fixture
async def app(db_url, tx_sessionmaker):
    app = create_app(Settings(env="dev", database_url=db_url, email_sender="off", web_base_url="http://web.test"))
    app.state.sessionmaker = tx_sessionmaker
    app.state.clock = Clock()
    app.state.llm = gateway("replay")
    async with tx_sessionmaker() as s:
        await seed(s, "samples")
        await s.commit()
    return app


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def as_user(client, user_id: str) -> dict:
    r = await client.post("/dev/token", data={"username": user_id})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def emails_to(client, address: str) -> list[dict]:
    return (await client.get("/dev/emails", params={"to": address})).json()


def proposed(patch_id: str, author: str = "user_admin") -> dict:
    return {"patch_id": patch_id, "process_id": "proc_client_onboarding", "base_version": 3, "ops": RENAME,
            "author": {"kind": "user", "id": author}, "reason": "Name the screening step after what it does",
            "auto_apply": False, "status": "proposed"}


async def test_approvals_proposed_change_is_emailed_to_the_owner_who_approves_it(client, app):
    admin, daniel = await as_user(client, "user_admin"), await as_user(client, "user_daniel_okafor")
    r = await client.post(f"{ONBOARDING}/patches", headers=admin, json=proposed("p_review"))
    assert r.status_code == 202 and r.json()["status"] == "proposed"

    [mail] = await emails_to(client, "daniel.okafor@example.com")
    assert mail["subject"] == "Dev Admin asks you to review a change: Name the screening step after what it does"
    assert 'Dev Admin asks you to review a proposed change for "Client onboarding – KYC & engagement ' \
           'acceptance".' in mail["text"]
    assert "1 change to Client onboarding – KYC & engagement acceptance" in mail["text"]
    [request] = (await client.get("/api/v1/approvals", headers=daniel)).json()
    assert mail["text"].rstrip().endswith(f"http://web.test/approvals/{request['approval_id']}")
    assert (request["kind"], request["requested_by"]["name"], request["assignee"]["name"]) == \
        ("patch_review", "Dev Admin", "Daniel Okafor")
    assert (await client.get("/api/v1/approvals/summary", headers=daniel)).json() == {"pending": 1}

    url = f"/api/v1/approvals/{request['approval_id']}"
    detail = (await client.get(url, headers=daniel)).json()
    assert detail["subject"]["ops"] == RENAME and detail["can_decide"]
    assert (await client.get(url, headers=await as_user(client, "user_viewer"))).status_code == 403
    sarah = await as_user(client, "user_sarah_lin")
    assert (await client.post(f"{url}/decision", headers=sarah, json={"decision": "approve"})).status_code == 403
    r = await client.post(f"{url}/decision", headers=daniel, json={"decision": "reject"})
    assert r.status_code == 422 and r.json()["errors"][0]["path"] == "/note"

    r = await client.post(f"{url}/decision", headers=daniel, json={"decision": "approve", "note": "Clearer, thanks"})
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["response"] == "Clearer, thanks"
    assert r.json()["subject"]["status"] == "applied"
    assert (await client.get(ONBOARDING, headers=daniel)).json()["current_version"] == 4
    assert (await client.post(f"{url}/decision", headers=daniel, json={"decision": "approve"})).status_code == 409

    [outcome] = await emails_to(client, "admin@example.com")
    assert outcome["subject"] == "Daniel Okafor approved: Name the screening step after what it does"
    assert 'Their note: "Clearer, thanks"' in outcome["text"]
    async with app.state.sessionmaker() as s:
        events = [e.type for e in (await s.execute(select(EventOutbox).where(
            EventOutbox.type.like("approval.%")).order_by(EventOutbox.created_at))).scalars()]
        audit = [a.action for a in (await s.execute(select(AuditLog).where(
            AuditLog.target == request["approval_id"]).order_by(AuditLog.at, AuditLog.id))).scalars()]
    assert events == ["approval.requested", "approval.decided"]
    assert audit == ["approval.requested", "approval.decided"]


async def test_approvals_owner_deciding_directly_closes_the_request(client):
    admin, daniel = await as_user(client, "user_admin"), await as_user(client, "user_daniel_okafor")
    r = await client.post(f"{ONBOARDING}/patches", headers=admin, params={"reviewer": "user_priya_shah"},
                          json=proposed("p_direct"))
    assert r.status_code == 202
    priya = await as_user(client, "user_priya_shah")
    [request] = (await client.get("/api/v1/approvals", headers=priya)).json()
    assert (await client.post("/api/v1/patches/p_direct/accept", headers=daniel)).status_code == 201
    closed = (await client.get(f"/api/v1/approvals/{request['approval_id']}", headers=priya)).json()
    assert (closed["status"], closed["response"], closed["can_decide"]) == \
        ("closed", "Decided directly by Daniel Okafor", False)
    assert (await client.get("/api/v1/approvals", headers=priya)).json() == []


async def _reopen_signoff(app) -> None:
    """The KYC sample as it stood just before Sarah signed off (the seed ends signed off)."""
    async with app.state.sessionmaker() as s:
        await s.execute(delete(Signoff).where(Signoff.process_id == "proc_client_kyc_to_be"))
        await s.execute(delete(IntakeTurn).where(IntakeTurn.session_id == "is_client_kyc",
                                                 IntakeTurn.kind.in_(["signoff", "phase_change"]),
                                                 IntakeTurn.phase == "done"))
        sess = await s.get(IntakeSession, "is_client_kyc")
        sess.phase, sess.status, sess.completed_at = "validate", "active", None
        sess.current_target = {"kind": "signoff", "id": "all"}
        await s.commit()


async def test_approvals_story_signoff_by_the_person_asked(client, app):
    await _reopen_signoff(app)
    sarah, priya = await as_user(client, "user_sarah_lin"), await as_user(client, "user_priya_shah")
    r = await client.post("/api/v1/approvals", headers=sarah, json={
        "kind": "story_signoff", "subject_id": "is_client_kyc", "assignee_user_id": "user_priya_shah",
        "message": "Can you sign these off for Compliance?"})
    assert r.status_code == 201, r.text
    request = r.json()
    stories = request["subject"]["stories"]
    assert request["title"] == f"{len(stories)} user stories for Client KYC checks"
    assert request["summary"] == "to-be version 12" and request["can_cancel"]
    [mail] = await emails_to(client, "priya.shah@example.com")
    assert mail["subject"] == f"Sarah Lin asks you to sign off: {request['title']}"
    assert 'Their note: "Can you sign these off for Compliance?"' in mail["text"]

    r = await client.post(f"/api/v1/approvals/{request['approval_id']}/decision", headers=priya,
                          json={"decision": "approve"})
    assert r.status_code == 200, r.text
    session = (await client.get("/api/v1/intake-sessions/is_client_kyc", headers=sarah)).json()
    assert session["phase"] == "done"
    assert session["timeline"][-2]["captured"] == [f"Priya Shah signed off {len(stories)} stories at to-be version 12"]
    async with app.state.sessionmaker() as s:
        signers = set((await s.execute(select(Signoff.signed_by).where(
            Signoff.process_id == "proc_client_kyc_to_be"))).scalars())
    assert signers == {"user_priya_shah"}
    [outcome] = await emails_to(client, "sarah.lin@example.com")
    assert outcome["subject"] == f"Priya Shah approved: {request['title']}"


async def test_approvals_signoff_refused_when_the_stories_changed(client, app):
    await _reopen_signoff(app)
    sarah, priya = await as_user(client, "user_sarah_lin"), await as_user(client, "user_priya_shah")
    request = (await client.post("/api/v1/approvals", headers=sarah, json={
        "kind": "story_signoff", "subject_id": "is_client_kyc", "assignee_user_id": "user_priya_shah"})).json()
    async with app.state.sessionmaker() as s:
        patches = PatchService(s)
        ir = await patches.get_ir("proc_client_kyc_to_be")
        await patches.submit({"patch_id": "p_after_request", "process_id": "proc_client_kyc_to_be",
                              "base_version": ir["process"]["version"], "author": {"kind": "user",
                                                                                   "id": "user_sarah_lin"},
                              "ops": [{"op": "replace", "path": "/process/description", "value": "Changed"}],
                              "reason": "late edit", "auto_apply": True, "status": "proposed"},
                             actor=Actor("user", "user_sarah_lin"))
        await s.commit()
    url = f"/api/v1/approvals/{request['approval_id']}"
    r = await client.post(f"{url}/decision", headers=priya, json={"decision": "approve"})
    assert r.status_code == 409 and r.json()["type"] == "/problems/stories-changed"
    r = await client.post(f"{url}/decision", headers=priya, json={"decision": "reject", "note": "Wait for v13"})
    assert r.json()["status"] == "rejected"
    assert (await client.get("/api/v1/intake-sessions/is_client_kyc", headers=sarah)).json()["phase"] == "validate"


async def test_approvals_suggestion_decided_by_the_person_asked(client, app):
    async with app.state.sessionmaker() as s:
        s07 = await s.get(SuggestionRow, ("S07", "idea_client_kyc"))
        s07.status, s07.decision = "proposed", None
        await s.commit()
    sarah, daniel = await as_user(client, "user_sarah_lin"), await as_user(client, "user_daniel_okafor")
    r = await client.post("/api/v1/approvals", headers=sarah, json={
        "kind": "suggestion", "subject_id": "S01", "idea_id": "idea_client_kyc",
        "assignee_user_id": "user_daniel_okafor"})
    assert r.status_code == 409 and r.json()["type"] == "/problems/suggestion-decided"
    r = await client.post("/api/v1/approvals", headers=sarah, json={
        "kind": "suggestion", "subject_id": "S07", "idea_id": "idea_client_kyc",
        "assignee_user_id": "user_daniel_okafor"})
    assert r.status_code == 201 and r.json()["subject"]["suggestion"]["suggestion_id"] == "S07"
    r = await client.post(f"/api/v1/approvals/{r.json()['approval_id']}/decision", headers=daniel,
                          json={"decision": "reject", "note": "Country flags still need a human"})
    assert r.status_code == 200, r.text
    s07 = next(x for x in (await client.get("/api/v1/ideas/idea_client_kyc/suggestions", headers=sarah)).json()
               if x["suggestion_id"] == "S07")
    assert s07["status"] == "rejected" and s07["decision"]["by"] == "user_daniel_okafor"
    assert s07["decision"]["reason"] == "Country flags still need a human"
    [outcome] = await emails_to(client, "sarah.lin@example.com")
    assert outcome["subject"].startswith("Daniel Okafor rejected: S07: ")


async def test_approvals_ask_someone_emails_the_question_and_shows_the_answer(client, app):
    sarah, priya = await as_user(client, "user_sarah_lin"), await as_user(client, "user_priya_shah")
    story = (await client.get("/api/v1/ideas/idea_client_kyc/stories", headers=sarah)).json()[0]
    r = await client.post(f"/api/v1/ideas/idea_client_kyc/stories/{story['story_id']}/ask", headers=sarah,
                          json={"text": "Who approves a high-risk client?", "user_id": "user_priya_shah"})
    assert r.status_code == 200, r.text
    assert r.json()["captured"] == "Asked Priya Shah (MLRO): Who approves a high-risk client?"
    [mail] = await emails_to(client, "priya.shah@example.com")
    assert mail["subject"] == "Sarah Lin asks you to answer a question: Who approves a high-risk client?"
    [request] = (await client.get("/api/v1/approvals", headers=priya)).json()
    assert request["kind"] == "question"

    url = f"/api/v1/approvals/{request['approval_id']}/decision"
    assert (await client.post(url, headers=priya, json={"decision": "approve"})).status_code == 422
    r = await client.post(url, headers=priya, json={"decision": "answer", "note": "The MLRO, with the partner told."})
    assert r.status_code == 200 and r.json()["status"] == "answered"
    assert r.json()["subject"]["answer"]["text"] == "The MLRO, with the partner told."
    async with app.state.sessionmaker() as s:
        q = await s.get(Question, request["subject_id"])
        answer = (await s.execute(select(Answer).where(Answer.question_id == q.id))).scalar_one()
    assert (q.status, q.assignee_user_id, q.sme_id, answer.answered_by) == \
        ("answered", "user_priya_shah", "sme_priya_shah", "user_priya_shah")
    timeline = (await client.get("/api/v1/intake-sessions/is_client_kyc", headers=sarah)).json()["timeline"]
    assert timeline[-1]["kind"] == "sme_answer"
    assert timeline[-1]["captured"] == ["Priya Shah answered: The MLRO, with the partner told."]
    [outcome] = await emails_to(client, "sarah.lin@example.com")
    assert outcome["subject"] == "Priya Shah answered: Who approves a high-risk client?"
    assert 'Their answer: "The MLRO, with the partner told."' in outcome["text"]


async def test_approvals_guardrails(client):
    sarah, viewer = await as_user(client, "user_sarah_lin"), await as_user(client, "user_viewer")
    admin = await as_user(client, "user_admin")
    body = {"kind": "story_signoff", "subject_id": "is_client_kyc"}
    r = await client.post("/api/v1/approvals", headers=sarah, json={**body, "assignee_user_id": "user_sarah_lin"})
    assert r.status_code == 422 and "someone other than yourself" in r.json()["title"]
    await client.patch("/api/v1/admin/users/user_tom_reed", headers=admin, json={"status": "disabled"})
    r = await client.post("/api/v1/approvals", headers=sarah, json={**body, "assignee_user_id": "user_tom_reed"})
    assert r.status_code == 422 and "disabled" in r.json()["title"]
    r = await client.post("/api/v1/approvals", headers=viewer, json={**body, "assignee_user_id": "user_priya_shah"})
    assert r.status_code == 403
    r = await client.post("/api/v1/approvals", headers=sarah, json={**body, "assignee_user_id": "user_priya_shah"})
    assert r.status_code == 409 and r.json()["type"] == "/problems/not-ready-for-signoff"  # KYC is signed off
    r = await client.post("/api/v1/approvals", headers=sarah, json={**body, "kind": "question",
                                                                    "assignee_user_id": "user_priya_shah"})
    assert r.status_code == 422

    r = await client.post(f"{ONBOARDING}/patches", headers=admin, json=proposed("p_cancel"))
    [request] = (await client.get("/api/v1/approvals", params={"box": "sent"}, headers=admin)).json()
    daniel = await as_user(client, "user_daniel_okafor")
    url = f"/api/v1/approvals/{request['approval_id']}"
    assert (await client.post(f"{url}/cancel", headers=viewer)).status_code == 403
    assert (await client.post(f"{url}/cancel", headers=admin)).json()["status"] == "cancelled"
    r = await client.post(f"{url}/decision", headers=daniel, json={"decision": "approve"})
    assert r.status_code == 409 and r.json()["type"] == "/problems/approval-closed"
