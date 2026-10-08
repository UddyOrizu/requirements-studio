"""Dev-only OIDC provider: discovery, JWKS and a password-grant token endpoint for fixed dev users.

Mounted at /dev/oidc only when RS_ENV=dev and RS_OIDC_ISSUER is empty (apps/api/main.py). Any password is accepted.
The signing key is generated at start-up, so tokens do not survive a restart. Swagger UI's "Authorize" button works
against /dev/oidc/token.
"""
import time
import uuid
from typing import Annotated

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, Form, HTTPException

from .auth import StaticKeyVerifier

# Users from the samples, one per role (docs/03).
DEV_USERS: dict[str, dict] = {
    "user_admin": {"name": "Dev Admin", "email": "admin@example.com", "roles": ["admin"]},
    "user_sarah_lin": {"name": "Sarah Lin", "email": "sarah.lin@example.com", "roles": ["requester"]},
    "user_daniel_okafor": {"name": "Daniel Okafor", "email": "daniel.okafor@example.com", "roles": ["owner", "ba"]},
    "sme_priya_shah": {"name": "Priya Shah", "email": "priya.shah@example.com", "roles": ["sme"]},
    "user_viewer": {"name": "Dev Viewer", "email": "viewer@example.com", "roles": ["viewer"]},
    "system_mother": {"name": "MOTHER", "email": "", "roles": ["system:mother"]},
}
TOKEN_TTL_SECONDS = 8 * 3600


class DevOidc:
    def __init__(self, issuer: str, audience: str):
        self.issuer, self.audience = issuer.rstrip("/"), audience
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = uuid.uuid4().hex[:16]

    def verifier(self) -> StaticKeyVerifier:
        return StaticKeyVerifier(self._key.public_key(), self.issuer, self.audience)

    def issue(self, user_id: str) -> str:
        user = DEV_USERS[user_id]
        now = int(time.time())
        claims = {"iss": self.issuer, "aud": self.audience, "sub": user_id, "iat": now,
                  "exp": now + TOKEN_TTL_SECONDS, "name": user["name"], "email": user["email"], "roles": user["roles"]}
        return jwt.encode(claims, self._key, algorithm="RS256", headers={"kid": self.kid})

    def jwks(self) -> dict:
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self._key.public_key(), as_dict=True)
        return {"keys": [{**jwk, "kid": self.kid, "use": "sig", "alg": "RS256"}]}

    def router(self) -> APIRouter:
        r = APIRouter(tags=["dev-oidc"])

        @r.get("/.well-known/openid-configuration")
        def discovery() -> dict:
            return {
                "issuer": self.issuer,
                "jwks_uri": f"{self.issuer}/jwks",
                "token_endpoint": f"{self.issuer}/token",
                "grant_types_supported": ["password"],
                "id_token_signing_alg_values_supported": ["RS256"],
                "subject_types_supported": ["public"],
            }

        @r.get("/jwks")
        def jwks() -> dict:
            return self.jwks()

        @r.get("/users")
        def users() -> dict:
            return DEV_USERS

        @r.post("/token")
        def token(username: Annotated[str, Form()], password: Annotated[str, Form()] = "",
                  grant_type: Annotated[str, Form()] = "password") -> dict:
            if grant_type != "password":
                raise HTTPException(400, {"error": "unsupported_grant_type"})
            if username not in DEV_USERS:
                detail = {"error": "invalid_grant", "error_description": f"unknown dev user {username}"}
                raise HTTPException(400, detail)
            tok = self.issue(username)
            return {"access_token": tok, "id_token": tok, "token_type": "Bearer", "expires_in": TOKEN_TTL_SECONDS}

        return r
