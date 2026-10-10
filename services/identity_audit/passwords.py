"""Password hashing (Argon2id, argon2-cffi defaults) and the password policy (docs/06 §Identity)."""
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_LENGTH = 12
MAX_LENGTH = 256
_hasher = PasswordHasher()
# Verified against when the email is unknown, so a failed sign-in takes as long either way.
_DUMMY = _hasher.hash("not-a-real-password-just-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def policy_problem(password: str, *, email: str = "") -> str | None:
    """Why the password is not acceptable, or None. Length over composition rules (NIST SP 800-63B)."""
    if len(password) < MIN_LENGTH:
        return f"use at least {MIN_LENGTH} characters"
    if len(password) > MAX_LENGTH:
        return f"use at most {MAX_LENGTH} characters"
    if email and password.strip().lower() in {email.lower(), email.split("@")[0].lower()}:
        return "do not use your email address as your password"
    if len(set(password)) < 4:
        return "use a less repetitive password"
    return None
