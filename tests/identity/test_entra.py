"""EntraVerifier against locally minted tokens shaped like Microsoft Entra ID v2.0 access tokens."""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from services.identity_audit.auth import EntraVerifier, InvalidToken

TENANT = "11111111-1111-1111-1111-111111111111"
API = "22222222-2222-2222-2222-222222222222"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJwks:
    """Stands in for the tenant's discovery/v2.0/keys endpoint."""

    def get_signing_key_from_jwt(self, token):
        return type("Key", (), {"key": KEY.public_key()})()


def verifier():
    return EntraVerifier(tenant_id=TENANT, api_client_id=API, api_scope=f"api://{API}/access_as_user",
                         jwks_client=FakeJwks())


def token(key=KEY, **overrides):
    now = int(time.time())
    claims = {"iss": f"https://login.microsoftonline.com/{TENANT}/v2.0", "aud": API, "tid": TENANT,
              "oid": "aaaaaaaa-0000-0000-0000-000000000001", "sub": "pairwise-subject", "iat": now, "nbf": now,
              "exp": now + 3600, "ver": "2.0", "name": "Sarah Lin", "preferred_username": "sarah.lin@example.com",
              "scp": "access_as_user", "roles": ["requester"]}
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


def test_entra_user_token_maps_to_a_principal():
    p = verifier().verify(token())
    assert p.user_id == "aaaaaaaa-0000-0000-0000-000000000001"  # oid, not the pairwise sub
    assert (p.name, p.email, p.roles) == ("Sarah Lin", "sarah.lin@example.com", ("requester",))


def test_entra_accepts_the_app_id_uri_audience():
    assert verifier().verify(token(aud=f"api://{API}")).user_id


def test_entra_app_only_token_uses_app_roles():
    p = verifier().verify(token(scp=None, roles=["system.mother"], name=None, preferred_username=None))
    assert p.roles == ("system:mother",)


@pytest.mark.parametrize("overrides,message", [
    ({"iss": "https://login.microsoftonline.com/99999999-0000-0000-0000-000000000000/v2.0"}, "not from this tenant"),
    ({"iss": f"https://sts.windows.net/{TENANT}/"}, "accessTokenAcceptedVersion"),
    ({"aud": "api://someone-else"}, "(?i)audience"),
    ({"tid": "99999999-0000-0000-0000-000000000000"}, "another tenant"),
    ({"scp": "User.Read"}, "access_as_user"),
    ({"scp": None, "roles": []}, "app role"),
    ({"exp": int(time.time()) - 60}, "expired"),
    ({"oid": None}, "oid"),
])
def test_entra_rejects(overrides, message):
    with pytest.raises(InvalidToken, match=message):
        verifier().verify(token(**overrides))


def test_entra_rejects_a_token_signed_by_another_key():
    with pytest.raises(InvalidToken, match="Signature"):
        verifier().verify(token(key=OTHER_KEY))
