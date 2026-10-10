"""Who is calling: the principal, and verification of Microsoft Entra ID access tokens (optional SSO).

Accounts are internal (services/identity_audit/users.py); an Entra ID sign-in is mapped onto one of them.
"""
from dataclasses import dataclass, field
from typing import Any, Protocol

import jwt

ROLES = ("user", "admin")  # docs/03; ownership of ideas and processes is per record, not a role


@dataclass(frozen=True)
class Principal:
    user_id: str
    name: str = ""
    email: str = ""
    roles: tuple[str, ...] = field(default_factory=tuple)
    service: bool = False  # an app-only Entra ID token (e.g. MOTHER): roles are its app roles, no user account

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles


class InvalidToken(Exception):
    pass


class TokenVerifier(Protocol):
    def verify(self, token: str) -> Principal: ...


class EntraVerifier:
    """Access tokens from Microsoft Entra ID (single tenant, v2.0 tokens).

    Accepts a token only if it is signed by the tenant's keys, issued by
    https://login.microsoftonline.com/<tenant>/v2.0, for this API (aud = its client id or api://<client id>), and
    either delegated with the API scope (a person signed in to the web app, mapped onto their internal account by the
    caller) or an app-only token carrying app roles (a service such as MOTHER). The user id is the object id (`oid`),
    which is stable across apps, unlike `sub`.
    App role values map to Requirements Studio roles; "." stands for ":" (Entra role values cannot use colons
    everywhere), so the app role "system.mother" is the role "system:mother".

    Blocking (PyJWKClient fetches and caches the signing keys over HTTP); call it from a threadpool in async code.
    """

    def __init__(self, *, tenant_id: str, api_client_id: str, api_scope: str,
                 authority: str = "https://login.microsoftonline.com", jwks_client: Any = None):
        self.tenant_id = tenant_id
        self.issuer = f"{authority.rstrip('/')}/{tenant_id}/v2.0"
        self.audiences = [api_client_id, f"api://{api_client_id}"]
        self.scope = api_scope.rsplit("/", 1)[-1]  # api://<id>/access_as_user → access_as_user
        self._jwks = jwks_client or jwt.PyJWKClient(f"{authority.rstrip('/')}/{tenant_id}/discovery/v2.0/keys",
                                                     cache_keys=True, lifespan=3600)

    def verify(self, token: str) -> Principal:
        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.audiences, issuer=self.issuer,
                                options={"require": ["exp", "iat", "iss", "aud", "tid", "oid"]})
        except jwt.InvalidIssuerError as e:
            issuer = jwt.decode(token, options={"verify_signature": False}).get("iss", "")
            if issuer.startswith("https://sts.windows.net/"):
                raise InvalidToken("this is a v1.0 access token: set \"accessTokenAcceptedVersion\": 2 in the API "
                                   "app registration's manifest") from e
            raise InvalidToken(f"token is not from this tenant ({issuer})") from e
        except jwt.PyJWTError as e:
            raise InvalidToken(str(e)) from e
        if claims["tid"] != self.tenant_id:
            raise InvalidToken("token is for another tenant")
        roles = tuple(r.replace(".", ":") for r in claims.get("roles", []))
        if "scp" in claims:
            if self.scope not in claims["scp"].split():
                raise InvalidToken(f"token lacks the '{self.scope}' scope")
        elif not roles:
            raise InvalidToken("an app-only token needs an app role")
        return Principal(user_id=claims["oid"], name=claims.get("name") or claims.get("preferred_username", ""),
                         email=claims.get("preferred_username") or claims.get("email", ""), roles=roles,
                         service="scp" not in claims)
