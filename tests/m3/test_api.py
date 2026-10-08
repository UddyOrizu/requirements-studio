"""M3 REST contract (docs/03): status codes, problem+json bodies and who may do what."""
import httpx
import pytest

from apps.api.main import create_app
from services.common.settings import Settings
from services.ideas.db import Idea
from services.ir_store.service import Actor, PatchService
from tests.conftest import KYC, SAMPLES, load

PROBLEM = "application/problem+json"


@pytest.fixture
async def client(db_url, tx_sessionmaker):
    app = create_app(Settings(env="dev", oidc_issuer="", database_url=db_url, public_base_url="http://test"))
    app.state.sessionmaker = tx_sessionmaker
    async with tx_sessionmaker() as s:
        for idea_id, owner in (("idea_client_kyc", "user_sarah_lin"), ("idea_client_onboarding", "user_daniel_okafor")):
            s.add(Idea(id=idea_id, title=idea_id, summary="", owner_user_id=owner, status="discovering",
                       has_as_is=True, session_id=f"is_{idea_id}"))
        await s.flush()
        svc = PatchService(s)
        await svc.import_process(load(SAMPLES / "ir_client_onboarding.json"), actor=Actor("user", "user_daniel_okafor"))
        await svc.import_process(load(KYC / "ir_client_kyc_as_is.json"), actor=Actor("user", "user_sarah_lin"))
        await s.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def auth(client, user: str) -> dict:
    r = await client.post("/dev/oidc/token", data={"username": user, "password": "x"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def patch(ops, *, base=3, patch_id="p_api", author="user_daniel_okafor", auto_apply=True, **extra):
    return {"patch_id": patch_id, "process_id": "proc_client_onboarding", "base_version": base, "ops": ops,
            "author": {"kind": "user", "id": author}, "reason": "api test", "auto_apply": auto_apply,
            "status": "proposed", **extra}


RENAME = [{"op": "replace", "path": "/nodes/node_screening/name", "value": "Screen the client"}]
URL = "/api/v1/processes/proc_client_onboarding"


async def test_m3_api_submit_applied_proposed_conflict_invalid(client):
    owner = await auth(client, "user_daniel_okafor")
    r = await client.post(f"{URL}/patches", json=patch(RENAME, patch_id="p1"), headers=owner)
    assert r.status_code == 201
    assert r.json() == {"patch_id": "p1", "status": "applied", "to_version": 4,
                        "changed_paths": ["/nodes/node_screening/name"]}

    r = await client.post(f"{URL}/patches", json=patch(RENAME, patch_id="p2"), headers=owner)
    assert r.status_code == 409 and r.headers["content-type"] == PROBLEM
    assert r.json() == {"type": "/problems/patch-conflict", "title": "Patch conflicts with newer changes",
                             "status": 409, "patch_id": "p2", "base_version": 3, "current_version": 4,
                             "conflicting_paths": ["/nodes/node_screening/name"]}

    rename_desc = [{"op": "replace", "path": "/nodes/node_id_verify/name", "value": "Verify"}]
    r = await client.post(f"{URL}/patches", json=patch(rename_desc, base=4, patch_id="p3", auto_apply=False),
                          headers=owner)
    assert r.status_code == 202 and r.json() == {"patch_id": "p3", "status": "proposed"}

    bad = [{"op": "replace", "path": "/stories/story_screening/title", "value": "x"}]
    r = await client.post(f"{URL}/patches", json=patch(bad, base=4, patch_id="p4"), headers=owner)
    assert r.status_code == 422 and r.headers["content-type"] == PROBLEM
    assert r.json()["errors"][0]["kind"] == "forbidden_path"


async def test_m3_api_accept_reject_and_list(client):
    owner = await auth(client, "user_daniel_okafor")
    for pid in ("pa", "pb"):
        r = await client.post(f"{URL}/patches", json=patch(RENAME, patch_id=pid, auto_apply=False), headers=owner)
        assert r.status_code == 202
    r = await client.post("/api/v1/patches/pb/reject", json={}, headers=owner)
    assert r.status_code == 422
    r = await client.post("/api/v1/patches/pb/reject", json={"reason": "Not needed"}, headers=owner)
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    r = await client.post("/api/v1/patches/pa/accept", headers=owner)
    assert r.status_code == 201 and r.json()["to_version"] == 4
    r = await client.post("/api/v1/patches/pa/accept", headers=owner)
    assert r.status_code == 409 and r.json()["type"] == "/problems/patch-not-proposed"

    listed = (await client.get(f"{URL}/patches", headers=owner)).json()
    assert {p["patch_id"]: p["status"] for p in listed} == {"pa": "applied", "pb": "rejected"}
    assert [p["patch_id"] for p in (await client.get(f"{URL}/patches?status=rejected", headers=owner)).json()] == ["pb"]


async def test_m3_api_reads(client):
    viewer = await auth(client, "user_viewer")
    owner = await auth(client, "user_daniel_okafor")
    await client.post(f"{URL}/patches", json=patch(RENAME, patch_id="p1"), headers=owner)
    assert (await client.get(URL, headers=viewer)).json()["current_version"] == 4
    assert (await client.get(f"{URL}/ir", headers=viewer)).json()["nodes"]["node_screening"]["name"] == \
        "Screen the client"
    assert (await client.get(f"{URL}/ir?version=3", headers=viewer)).json()["process"]["version"] == 3
    diff = (await client.get(f"{URL}/ir/diff?from=3&to=4", headers=viewer)).json()
    assert {"op": "replace", "path": "/nodes/node_screening/name", "value": "Screen the client"} in diff
    r = await client.get(f"{URL}/ir?version=99", headers=viewer)
    assert r.status_code == 404 and r.headers["content-type"] == PROBLEM
    ids = [p["id"] for p in (await client.get("/api/v1/processes", headers=viewer)).json()]
    assert ids == ["proc_client_kyc_as_is", "proc_client_onboarding"]
    assert (await client.get(URL)).status_code == 401


async def test_m3_api_permissions(client):
    viewer, requester = await auth(client, "user_viewer"), await auth(client, "user_sarah_lin")
    # Not the owner, not a BA: cannot patch someone else's process.
    r = await client.post(f"{URL}/patches", json=patch(RENAME, author="user_sarah_lin"), headers=requester)
    assert r.status_code == 403
    # Over HTTP the author must be the signed-in user.
    ba = await auth(client, "user_daniel_okafor")
    r = await client.post(f"{URL}/patches", json=patch(RENAME, author="user_sarah_lin"), headers=ba)
    assert r.status_code == 403
    r = await client.post(f"{URL}/patches", json={**patch(RENAME), "author": {"kind": "agent", "id": "agent:x"}},
                          headers=ba)
    assert r.status_code == 403
    r = await client.post("/api/v1/processes", json={"name": "X", "owner_user_id": "u"}, headers=viewer)
    assert r.status_code == 403


async def test_m3_api_create_and_fork(client):
    ba, requester = await auth(client, "user_daniel_okafor"), await auth(client, "user_sarah_lin")
    r = await client.post("/api/v1/processes", json={"name": "Expense claims", "owner_user_id": "user_sarah_lin",
                                                     "domain": "finance"}, headers=ba)
    assert r.status_code == 201 and r.json()["process_id"] == "proc_expense_claims"
    assert r.json()["ir"]["process"]["version"] == 0

    r = await client.post("/api/v1/processes/proc_client_kyc_as_is/fork", headers=requester)
    assert r.status_code == 201
    body = r.json()
    assert body["to_be_process_id"] == "proc_client_kyc_to_be"
    assert body["fork"]["process_overrides"]["derived_from"] == {"process_id": "proc_client_kyc_as_is",
                                                                  "version": 19}
    r = await client.post("/api/v1/processes/proc_client_kyc_as_is/fork", headers=requester)
    assert r.status_code == 409 and r.json()["type"] == "/problems/already-forked"
    r = await client.post("/api/v1/processes/proc_client_onboarding/fork", headers=ba)
    assert r.status_code == 409 and "node_screening" in r.json()["unconfirmed"]
    procs = (await client.get("/api/v1/processes?idea_id=idea_client_kyc", headers=requester)).json()
    assert {(p["id"], p["variant"], p["frozen"]) for p in procs} == {
        ("proc_client_kyc_as_is", "as_is", True), ("proc_client_kyc_to_be", "to_be", False)}
