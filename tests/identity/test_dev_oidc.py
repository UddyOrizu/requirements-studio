import jwt
import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from services.common.settings import Settings
from services.identity_audit.auth import JwksVerifier


@pytest.fixture
def client():
    return TestClient(create_app(Settings(env="dev", oidc_issuer="", public_base_url="http://testserver")))


def _token(client, user="user_sarah_lin") -> str:
    r = client.post("/dev/oidc/token", data={"username": user, "password": "x", "grant_type": "password"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_dev_oidc_discovery_and_jwks(client):
    conf = client.get("/dev/oidc/.well-known/openid-configuration").json()
    assert conf["issuer"] == "http://testserver/dev/oidc"
    keys = client.get("/dev/oidc/jwks").json()["keys"]
    assert keys[0]["kty"] == "RSA" and keys[0]["alg"] == "RS256"


def test_dev_oidc_token_verifies_against_published_jwks(client):
    tok = _token(client)
    jwk = client.get("/dev/oidc/jwks").json()["keys"][0]
    assert jwt.get_unverified_header(tok)["kid"] == jwk["kid"]
    key = jwt.PyJWK(jwk).key
    claims = jwt.decode(tok, key, algorithms=["RS256"], audience="requirements-studio",
                        issuer="http://testserver/dev/oidc")
    assert claims["sub"] == "user_sarah_lin" and claims["roles"] == ["requester"]


def test_dev_oidc_me_with_token(client):
    r = client.get("/api/v1/me", headers={"Authorization": f"Bearer {_token(client, 'sme_priya_shah')}"})
    assert r.status_code == 200
    assert r.json() == {"user_id": "sme_priya_shah", "name": "Priya Shah", "email": "priya.shah@example.com",
                        "roles": ["sme"]}


def test_dev_oidc_rejects_missing_and_tampered_tokens(client):
    assert client.get("/api/v1/me").status_code == 401
    tok = _token(client)
    header, payload, sig = tok.split(".")
    forged = jwt.encode({"sub": "user_admin", "roles": ["admin"]}, "s" * 32, algorithm="HS256").split(".")[1]
    for bad in (f"{header}.{forged}.{sig}", tok[:-4] + "AAAA", "not-a-jwt"):
        assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {bad}"}).status_code == 401


def test_dev_oidc_rejects_token_from_another_stub_instance(client):
    other = TestClient(create_app(Settings(env="dev", oidc_issuer="", public_base_url="http://testserver")))
    r = client.get("/api/v1/me", headers={"Authorization": f"Bearer {_token(other)}"})
    assert r.status_code == 401


def test_dev_oidc_unknown_user(client):
    r = client.post("/dev/oidc/token", data={"username": "user_nobody", "password": "x"})
    assert r.status_code == 400


def test_dev_oidc_not_mounted_outside_dev():
    app = create_app(Settings(env="prod", oidc_issuer="https://login.example.com/tenant/v2.0"))
    c = TestClient(app)
    assert c.get("/dev/oidc/.well-known/openid-configuration").status_code == 404
    assert c.post("/dev/oidc/token", data={"username": "user_admin"}).status_code == 404
    assert isinstance(app.state.verifier, JwksVerifier)


def test_dev_oidc_not_mounted_when_real_issuer_configured():
    c = TestClient(create_app(Settings(env="dev", oidc_issuer="https://login.example.com/tenant/v2.0")))
    assert c.get("/dev/oidc/jwks").status_code == 404


def test_settings_require_real_idp_outside_dev():
    with pytest.raises(ValueError, match="RS_OIDC_ISSUER"):
        Settings(env="prod", oidc_issuer="")


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}
