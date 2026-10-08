"""Bearer-token verification against an OIDC issuer (Entra ID in prod, the dev stub locally)."""
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, Protocol

import httpx
import jwt

ROLES = ("admin", "requester", "owner", "ba", "sme", "viewer", "system:mother")  # docs/03


@dataclass(frozen=True)
class Principal:
    user_id: str
    name: str = ""
    email: str = ""
    roles: tuple[str, ...] = field(default_factory=tuple)


class InvalidToken(Exception):
    pass


class TokenVerifier(Protocol):
    def verify(self, token: str) -> Principal: ...


def principal_from_claims(claims: dict[str, Any]) -> Principal:
    return Principal(user_id=claims["sub"], name=claims.get("name", ""), email=claims.get("email", ""),
                     roles=tuple(claims.get("roles", ())))


class StaticKeyVerifier:
    """Verifies RS256 tokens with a known public key (the dev stub, and tests)."""

    def __init__(self, public_key: Any, issuer: str, audience: str):
        self.public_key, self.issuer, self.audience = public_key, issuer, audience

    def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(token, self.public_key, algorithms=["RS256"], audience=self.audience,
                                issuer=self.issuer, options={"require": ["exp", "iat", "sub", "iss", "aud"]})
        except jwt.PyJWTError as e:
            raise InvalidToken(str(e)) from e
        return principal_from_claims(claims)


class JwksVerifier:
    """Verifies tokens from a real IdP: discovery document → jwks_uri → signing key by `kid`.

    Blocking (urllib in PyJWKClient); call it from a threadpool in async code.
    """

    def __init__(self, issuer: str, audience: str):
        self.issuer, self.audience = issuer.rstrip("/"), audience

    @cached_property
    def _jwks(self) -> jwt.PyJWKClient:
        conf = httpx.get(f"{self.issuer}/.well-known/openid-configuration", timeout=10).raise_for_status().json()
        return jwt.PyJWKClient(conf["jwks_uri"], cache_keys=True)

    def verify(self, token: str) -> Principal:
        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.audience, issuer=self.issuer,
                                options={"require": ["exp", "iat", "sub", "iss", "aud"]})
        except jwt.PyJWTError as e:
            raise InvalidToken(str(e)) from e
        return principal_from_claims(claims)
