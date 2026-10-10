"""Session tokens the API issues after a password sign-in (HS256 JWTs, RS_SESSION_SECRET).

The token names the user and their session_version; the role is read from the users table on every request, so a
role change applies at once and disabling a user (or a password change) signs them out everywhere.
"""
import time
from dataclasses import dataclass

import jwt

from .auth import InvalidToken

ISSUER = "requirements-studio"
AUDIENCE = "requirements-studio"


@dataclass(frozen=True)
class SessionClaims:
    user_id: str
    session_version: int


class SessionTokens:
    def __init__(self, secret: str, ttl_minutes: int):
        self.secret, self.ttl = secret, ttl_minutes * 60

    def issue(self, user_id: str, session_version: int) -> str:
        now = int(time.time())
        return jwt.encode({"iss": ISSUER, "aud": AUDIENCE, "sub": user_id, "sv": session_version, "iat": now,
                           "exp": now + self.ttl}, self.secret, algorithm="HS256")

    @staticmethod
    def is_session_token(token: str) -> bool:
        """Ours (iss = requirements-studio) rather than an Entra ID access token; nothing is trusted yet."""
        try:
            return jwt.decode(token, options={"verify_signature": False}).get("iss") == ISSUER
        except jwt.PyJWTError:
            return False

    def verify(self, token: str) -> SessionClaims:
        try:
            claims = jwt.decode(token, self.secret, algorithms=["HS256"], audience=AUDIENCE, issuer=ISSUER,
                                options={"require": ["exp", "iat", "sub", "iss", "aud", "sv"]})
        except jwt.PyJWTError as e:
            raise InvalidToken(str(e)) from e
        return SessionClaims(claims["sub"], int(claims["sv"]))
