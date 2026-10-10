"""Internal user management over HTTP (docs/06 §Identity): admins manage users, invitations and resets by email,
password sign-in with lockout, sessions that end on disable or password change, and optional Entra ID SSO that only
admits people an admin has added."""
import re
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from apps.api.main import create_app
from services.common.settings import Settings
from services.identity_audit.auth import InvalidToken, Principal
from services.identity_audit.db import AuditLog
from services.identity_audit.dev import DEV_PASSWORD, seed_dev_users
from services.notifications import MemoryMailer, deliver_pending
from services.notifications.db import EmailOutbox

PROBLEM = "application/problem+json"


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class FakeEntra:
    """Stands in for EntraVerifier: the bearer token is 'entra|<oid>|<email>|<name>' (or 'entra-app|<role>')."""

    def verify(self, token: str) -> Principal:
        kind, *parts = token.split("|")
        if kind == "entra-app":
            return Principal(user_id="mother-sp", roles=(parts[0],), service=True)
        if kind != "entra":
            raise InvalidToken("not an Entra token")
        oid, email, name = parts
        return Principal(user_id=oid, name=name, email=email, roles=())


def make_app(db_url, tx_sessionmaker, **settings):
    app = create_app(Settings(env="dev", database_url=db_url, email_sender="off",
                              web_base_url="http://web.test", **settings))
    app.state.sessionmaker = tx_sessionmaker
    app.state.clock = Clock()
    return app


@pytest.fixture
async def app(db_url, tx_sessionmaker):
    app = make_app(db_url, tx_sessionmaker)
    async with tx_sessionmaker() as s:
        await seed_dev_users(s)
        await s.commit()
    return app


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def as_user(client, user_id: str) -> dict:
    r = await client.post("/dev/token", data={"username": user_id})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def login(client, email: str, password: str) -> httpx.Response:
    return await client.post("/auth/login", json={"email": email, "password": password})


async def last_email(client, to: str) -> dict:
    emails = (await client.get("/dev/emails", params={"to": to})).json()
    assert emails, f"no email to {to}"
    return emails[0]


def link_token(email: dict) -> str:
    return re.search(r"/set-password\?token=([\w-]+)", email["text"]).group(1)


async def test_identity_admin_invites_user_who_sets_password_and_signs_in(client):
    admin = await as_user(client, "user_admin")
    r = await client.post("/api/v1/admin/users", headers=admin,
                          json={"email": "Tom.Baker@Example.com ", "name": "Tom Baker"})
    assert r.status_code == 201, r.text
    tom = r.json()
    assert (tom["user_id"], tom["email"], tom["role"], tom["status"], tom["has_password"]) == \
        ("user_tom_baker", "tom.baker@example.com", "user", "invited", False)

    invite = await last_email(client, "tom.baker@example.com")
    assert invite["subject"] == "You have been invited to Requirements Studio"
    assert "Dev Admin has added you to Requirements Studio as a user." in invite["text"]
    token = link_token(invite)
    assert invite["text"].count("http://web.test/set-password?token=") == 1

    assert (await login(client, "tom.baker@example.com", "anything-at-all")).status_code == 401  # invited
    info = (await client.get("/auth/password/link", params={"token": token})).json()
    assert (info["purpose"], info["email"], info["name"]) == ("invite", "tom.baker@example.com", "Tom Baker")

    r = await client.post("/auth/password/set", json={"token": token, "password": "short"})
    assert r.status_code == 422 and r.json()["errors"] == [{"path": "/password",
                                                            "message": "use at least 12 characters"}]
    r = await client.post("/auth/password/set", json={"token": token, "password": "correct horse battery"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "user"
    r = await client.post("/auth/password/set", json={"token": token, "password": "correct horse battery"})
    assert r.status_code == 409 and r.json()["type"] == "/problems/link-expired"  # once only

    r = await login(client, "TOM.BAKER@example.com", "correct horse battery")
    assert r.status_code == 200, r.text
    me = (await client.get("/api/v1/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})).json()
    assert me == {"user_id": "user_tom_baker", "name": "Tom Baker", "email": "tom.baker@example.com", "role": "user",
                  "roles": ["user"]}
    users = {u["user_id"]: u for u in (await client.get("/api/v1/admin/users", headers=admin)).json()}
    assert users["user_tom_baker"]["status"] == "active" and users["user_tom_baker"]["last_sign_in_at"]

    r = await client.post("/api/v1/admin/users", headers=admin, json={"email": "tom.baker@example.com", "name": "T"})
    assert r.status_code == 409 and r.json()["type"] == "/problems/user-exists"


async def test_identity_only_admins_manage_users(client):
    sarah = await as_user(client, "user_sarah_lin")
    for method, path, body in (("get", "/api/v1/admin/users", None),
                               ("post", "/api/v1/admin/users", {"email": "x@example.com", "name": "X"}),
                               ("patch", "/api/v1/admin/users/user_viewer", {"role": "admin"}),
                               ("post", "/api/v1/admin/users/user_viewer/password-reset", None)):
        r = await client.request(method, path, headers=sarah, json=body)
        assert r.status_code == 403, (method, path)
    directory = (await client.get("/api/v1/users", headers=sarah)).json()
    assert {"user_id": "user_priya_shah", "name": "Priya Shah", "email": "priya.shah@example.com",
            "role": "user"} in directory
    assert all(set(u) == {"user_id", "name", "email", "role"} for u in directory)  # no hashes, no status
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_identity_role_change_applies_at_once_and_disable_signs_out(client, app):
    admin = await as_user(client, "user_admin")
    r = await login(client, "viewer@example.com", DEV_PASSWORD)
    viewer = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get("/api/v1/admin/users", headers=viewer)).status_code == 403

    r = await client.patch("/api/v1/admin/users/user_viewer", headers=admin, json={"role": "admin"})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert (await client.get("/api/v1/admin/users", headers=viewer)).status_code == 200  # same token, new role

    r = await client.patch("/api/v1/admin/users/user_viewer", headers=admin, json={"status": "disabled"})
    assert r.json()["status"] == "disabled"
    r = await client.get("/api/v1/me", headers=viewer)
    assert r.status_code == 401 and "sign in again" in r.json()["detail"]
    assert (await login(client, "viewer@example.com", DEV_PASSWORD)).status_code == 401
    r = await client.patch("/api/v1/admin/users/user_viewer", headers=admin, json={"status": "active"})
    assert r.json()["status"] == "active"
    assert (await login(client, "viewer@example.com", DEV_PASSWORD)).status_code == 200

    async with app.state.sessionmaker() as s:
        actions = [a.action for a in (await s.execute(select(AuditLog).where(AuditLog.target == "user_viewer")
                                                      .order_by(AuditLog.at, AuditLog.id))).scalars()]
    assert actions == ["user.updated", "user.disabled", "user.enabled"]


async def test_identity_keeps_an_admin_and_admins_cannot_disable_themselves(client):
    admin = await as_user(client, "user_admin")
    r = await client.patch("/api/v1/admin/users/user_admin", headers=admin, json={"status": "disabled"})
    assert r.status_code == 409 and r.json()["type"] == "/problems/cannot-disable-self"
    r = await client.patch("/api/v1/admin/users/user_daniel_okafor", headers=admin, json={"role": "user"})
    assert r.status_code == 200
    r = await client.patch("/api/v1/admin/users/user_admin", headers=admin, json={"role": "user"})
    assert r.status_code == 409 and r.json()["type"] == "/problems/last-admin"


async def test_identity_failed_sign_ins_lock_the_account_for_a_while(client, app):
    for _ in range(5):
        r = await login(client, "sarah.lin@example.com", "not her password")
        assert r.status_code == 401 and r.headers["content-type"] == PROBLEM
    locked = await login(client, "sarah.lin@example.com", DEV_PASSWORD)
    unknown = await login(client, "nobody@example.com", "whatever-password")
    assert locked.status_code == unknown.status_code == 401
    assert locked.json()["title"] == unknown.json()["title"]  # no account enumeration
    app.state.clock.now += timedelta(minutes=16)
    assert (await login(client, "sarah.lin@example.com", DEV_PASSWORD)).status_code == 200


async def test_identity_forgot_password_resets_once_and_voids_older_links(client):
    r = await client.post("/auth/password/forgot", json={"email": "nobody@example.com"})
    assert r.status_code == 202
    assert (await client.get("/dev/emails", params={"to": "nobody@example.com"})).json() == []

    await client.post("/auth/password/forgot", json={"email": "Priya.Shah@example.com"})
    first = link_token(await last_email(client, "priya.shah@example.com"))
    await client.post("/auth/password/forgot", json={"email": "priya.shah@example.com"})
    reset = await last_email(client, "priya.shah@example.com")
    assert reset["subject"] == "Reset your Requirements Studio password" and "60 minutes" in reset["text"]
    second = link_token(reset)
    r = await client.post("/auth/password/set", json={"token": first, "password": "a brand new password"})
    assert r.status_code == 409  # only the newest link works
    old_session = await as_user(client, "user_priya_shah")
    r = await client.post("/auth/password/set", json={"token": second, "password": "a brand new password"})
    assert r.status_code == 200
    assert (await client.get("/api/v1/me", headers=old_session)).status_code == 401  # signed out everywhere
    assert (await login(client, "priya.shah@example.com", DEV_PASSWORD)).status_code == 401
    assert (await login(client, "priya.shah@example.com", "a brand new password")).status_code == 200


async def test_identity_change_password(client):
    priya = await as_user(client, "user_priya_shah")
    r = await client.post("/api/v1/me/password", headers=priya,
                          json={"current_password": "wrong", "new_password": "another good password"})
    assert r.status_code == 422 and r.json()["errors"][0]["path"] == "/current_password"
    r = await client.post("/api/v1/me/password", headers=priya,
                          json={"current_password": DEV_PASSWORD, "new_password": "another good password"})
    assert r.status_code == 200
    assert (await client.get("/api/v1/me", headers=priya)).status_code == 401
    fresh = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get("/api/v1/me", headers=fresh)).status_code == 200


async def test_identity_admin_reset_and_resend_invite(client):
    admin = await as_user(client, "user_admin")
    r = await client.post("/api/v1/admin/users/user_tom_reed/password-reset", headers=admin)
    assert r.status_code == 200
    email = await last_email(client, "tom.reed@example.com")
    assert "An administrator asked to reset the password" in email["text"]
    await client.post("/api/v1/admin/users", headers=admin, json={"email": "new@example.com", "name": "New Person",
                                                                  "role": "admin", "send_invite": False})
    assert (await client.get("/dev/emails", params={"to": "new@example.com"})).json() == []
    assert (await client.post("/api/v1/admin/users/user_new_person/invite", headers=admin)).status_code == 200
    invite = await last_email(client, "new@example.com")
    assert "as an administrator" in invite["text"]


async def test_identity_sso_admits_only_people_an_admin_added(db_url, tx_sessionmaker):
    app = make_app(db_url, tx_sessionmaker, sso="entra", entra_tenant_id="t", entra_api_client_id="a",
                   entra_spa_client_id="s")
    app.state.entra = FakeEntra()
    async with tx_sessionmaker() as s:
        await seed_dev_users(s)
        await s.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        config = (await client.get("/auth/config")).json()
        assert config["password"] is True and config["sso"]["provider"] == "entra" and config["dev_sign_in"]

        def bearer(token: str) -> dict:
            return {"Authorization": f"Bearer {token}"}

        r = await client.get("/api/v1/me", headers=bearer("entra|oid-stranger|stranger@example.com|Stranger"))
        assert r.status_code == 403 and "ask an administrator to add you" in r.json()["detail"]

        r = await client.get("/api/v1/me", headers=bearer("entra|oid-sarah|Sarah.Lin@example.com|Sarah L"))
        assert r.status_code == 200 and r.json()["user_id"] == "user_sarah_lin" and r.json()["role"] == "user"
        # linked by object id: a later sign-in matches even if the email changed
        r = await client.get("/api/v1/me", headers=bearer("entra|oid-sarah|sarah.l@contoso.com|Sarah L"))
        assert r.json()["user_id"] == "user_sarah_lin"
        # another Entra account cannot take over an account that is already linked
        r = await client.get("/api/v1/me", headers=bearer("entra|oid-impostor|sarah.lin@example.com|S"))
        assert r.status_code == 403

        admin = await as_user(client, "user_admin")
        await client.post("/api/v1/admin/users", headers=admin, json={"email": "kim@example.com", "name": "Kim"})
        r = await client.get("/api/v1/me", headers=bearer("entra|oid-kim|kim@example.com|Kim"))
        assert r.status_code == 200 and r.json()["user_id"] == "user_kim"
        assert (await client.get("/api/v1/admin/users/user_kim", headers=admin)).json()["status"] == "active"

        await client.patch("/api/v1/admin/users/user_kim", headers=admin, json={"status": "disabled"})
        r = await client.get("/api/v1/me", headers=bearer("entra|oid-kim|kim@example.com|Kim"))
        assert r.status_code == 403 and "disabled" in r.json()["detail"]

        r = await client.get("/api/v1/me", headers=bearer("entra-app|system:mother"))
        assert r.json()["roles"] == ["system:mother"] and r.json()["role"] is None


async def test_identity_sso_only_has_no_passwords(db_url, tx_sessionmaker):
    app = make_app(db_url, tx_sessionmaker, sso="entra", entra_tenant_id="t", entra_api_client_id="a",
                   entra_spa_client_id="s", password_sign_in=False)
    async with tx_sessionmaker() as s:
        await seed_dev_users(s)
        await s.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/auth/config")).json()["password"] is False
        assert (await login(client, "sarah.lin@example.com", DEV_PASSWORD)).status_code == 401
        admin = await as_user(client, "user_admin")
        await client.post("/api/v1/admin/users", headers=admin, json={"email": "kim@example.com", "name": "Kim"})
        invite = await last_email(client, "kim@example.com")
        assert "Sign in with your Microsoft work account: http://web.test/signin" in invite["text"]
        assert "set-password" not in invite["text"]


async def test_identity_dev_routes_are_not_in_prod(db_url):
    app = create_app(Settings(env="prod", database_url=db_url, session_secret="x" * 32, email_sender="off",
                              azure_storage_connection_string=""))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/dev/token", data={"username": "user_admin"})).status_code == 404
        assert (await client.get("/dev/emails")).status_code == 404
        assert (await client.get("/auth/config")).json() == {"password": True, "sso": None, "dev_sign_in": False}


@pytest.mark.parametrize("kwargs, message", [
    ({"env": "prod"}, "RS_SESSION_SECRET"),
    ({"env": "prod", "session_secret": "too short"}, "RS_SESSION_SECRET"),
    ({"auth_mode": "dev"}, "RS_AUTH_MODE was replaced"),
    ({"sso": "entra", "entra_tenant_id": "t"}, "RS_ENTRA_API_CLIENT_ID, RS_ENTRA_SPA_CLIENT_ID"),
    ({"password_sign_in": False}, "nobody could sign in"),
])
def test_identity_settings_refuse_unsafe_configs(kwargs, message):
    with pytest.raises(ValueError, match=message):
        Settings(azure_storage_connection_string="", **kwargs)


async def test_identity_email_is_retried_then_sent(app, tx_sessionmaker):
    async with tx_sessionmaker() as s:
        from services.notifications import queue_email
        await queue_email(s, to_address="kim@example.com", to_name="Kim", template="password_reset",
                          context={"link": "http://web.test/set-password?token=t", "email": "kim@example.com",
                                   "by_admin": False, "expires_minutes": 60})
        await s.commit()
    now = datetime.now(UTC) + timedelta(seconds=1)  # queued "now" (wall clock)
    assert await deliver_pending(tx_sessionmaker, MemoryMailer(fail=True), now=now) == 0
    ok = MemoryMailer()
    assert await deliver_pending(tx_sessionmaker, ok, now=now) == 0  # backing off for a minute
    assert await deliver_pending(tx_sessionmaker, ok, now=now + timedelta(minutes=2)) == 1
    async with tx_sessionmaker() as s:
        row = (await s.execute(select(EmailOutbox).where(EmailOutbox.to_address == "kim@example.com"))).scalar_one()
    assert (row.status, row.attempts, row.last_error) == ("sent", 2, None)
    sent = ok.sent[0]
    assert sent.subject == "Reset your Requirements Studio password"
    assert '<a href="http://web.test/set-password?token=t"' in sent.html

