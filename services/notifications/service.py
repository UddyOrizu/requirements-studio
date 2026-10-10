"""Queue email in the caller's transaction; deliver what is due."""
import html
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.common.db import utcnow

from .db import EmailOutbox
from .mailer import Mailer, OutgoingEmail

TEMPLATES = Path(__file__).parent / "templates"
BACKOFF = [timedelta(minutes=m) for m in (1, 5, 15, 60, 240)]
MAX_ATTEMPTS = len(BACKOFF) + 1
_env = Environment(loader=FileSystemLoader(TEMPLATES), undefined=StrictUndefined, keep_trailing_newline=True,
                   autoescape=False)
_html = Environment(loader=FileSystemLoader(TEMPLATES), undefined=StrictUndefined, autoescape=True)


def render(template: str, context: dict[str, Any]) -> tuple[str, str, str]:
    """templates/<name>.txt: first line `Subject: …`, a blank line, then the body. Returns (subject, text, html)."""
    rendered = _env.get_template(f"{template}.txt").render(**context)
    head, _, body = rendered.partition("\n\n")
    if not head.startswith("Subject: "):
        raise ValueError(f"{template}.txt must start with 'Subject: '")
    subject = " ".join(head.removeprefix("Subject: ").split())[:200]  # one line: no header injection
    paragraphs = [Markup(_link(html.escape(p.strip())).replace("\n", "<br>")) for p in body.strip().split("\n\n")]
    page = _html.get_template("_layout.html").render(subject=subject, action_url=context.get("link"),
                                                     action_label=context.get("action_label", "Open"),
                                                     paragraphs=paragraphs)
    return subject, body.strip() + "\n", page


def _link(escaped: str) -> str:
    return re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', escaped)


async def queue_email(s: AsyncSession, *, to_address: str, to_name: str | None, template: str,
                      context: dict[str, Any], related_id: str | None = None) -> EmailOutbox:
    subject, text, page = render(template, {"name": to_name or to_address, **context})
    row = EmailOutbox(to_address=to_address, to_name=to_name, subject=subject, text_body=text, html_body=page,
                      template=template, related_id=related_id, status="queued", attempts=0, next_attempt_at=utcnow())
    s.add(row)
    await s.flush()
    return row


async def deliver_pending(sessionmaker: async_sessionmaker[AsyncSession], mailer: Mailer, *, now=None,
                          batch: int = 50) -> int:
    """Send queued email that is due; returns how many were sent. SKIP LOCKED: several senders never double-send."""
    now = now or utcnow()
    sent = 0
    async with sessionmaker() as s:
        rows = (await s.execute(select(EmailOutbox).where(EmailOutbox.status == "queued",
                                                          EmailOutbox.next_attempt_at <= now)
                                .order_by(EmailOutbox.created_at).limit(batch)
                                .with_for_update(skip_locked=True))).scalars().all()
        for row in rows:
            try:
                await mailer.send(OutgoingEmail(row.to_address, row.to_name, row.subject, row.text_body,
                                                row.html_body))
            except Exception as e:  # noqa: BLE001 (any transport failure is retried)
                row.attempts += 1
                row.last_error = f"{type(e).__name__}: {e}"[:1000]
                if row.attempts >= MAX_ATTEMPTS:
                    row.status = "failed"
                else:
                    row.next_attempt_at = now + BACKOFF[row.attempts - 1]
            else:
                row.attempts += 1
                row.status, row.sent_at, row.last_error = "sent", now, None
                sent += 1
        await s.commit()
    return sent
