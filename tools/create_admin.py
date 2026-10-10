#!/usr/bin/env python3
"""Create the first administrator (or make an existing user an admin) and print their invitation link.

Usage: uv run python tools/create_admin.py --email you@example.com --name "Your Name"

The invitation is also emailed (sent by the API or worker, RS_EMAIL_SENDER). With RS_PASSWORD_SIGN_IN=false (SSO
only) there is no link: the person signs in with Microsoft using that email.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1] / "packages")]

from services.common.db import make_engine, make_sessionmaker  # noqa: E402
from services.common.settings import get_settings  # noqa: E402
from services.identity_audit.audit import write_audit  # noqa: E402
from services.identity_audit.users import UserService  # noqa: E402


async def main(email: str, name: str) -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    try:
        async with make_sessionmaker(engine)() as s:
            users = UserService(s, settings=settings)
            user = await users.by_email(email)
            if user is None:
                user = await users.create(email=email, name=name, role="admin", actor=None, send_invite=False)
                print(f"Created admin {user.id} <{user.email}>")
            elif user.role != "admin" or user.status == "disabled":
                before = {"role": user.role, "status": user.status}
                user.role = "admin"
                if user.status == "disabled":
                    user.status = "active" if user.password_hash or user.entra_oid else "invited"
                await write_audit(s, actor_kind="system", actor_id="tools/create_admin", action="user.updated",
                                  target=user.id, before=before, after={"role": user.role, "status": user.status})
                print(f"{user.email} is now an admin")
            else:
                print(f"{user.email} is already an admin")
            if user.password_hash is None and settings.password_sign_in:
                link = await users.invite(user.id, actor=None)
                print(f"Set a password here (valid until {link.expires_at:%Y-%m-%d %H:%M} UTC):\n{link.url}")
            elif user.password_hash is None:
                print(f"Sign in with Microsoft as {user.email}: {settings.web_base_url.rstrip('/')}/signin")
            await s.commit()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    asyncio.run(main(args.email, args.name))
