"""Mail transports. SMTP covers Office 365, SendGrid, Mailgun, Mailpit and any relay."""
import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Protocol

from services.common.settings import Settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutgoingEmail:
    to_address: str
    to_name: str | None
    subject: str
    text: str
    html: str
    message_id: str = field(default_factory=make_msgid)


class Mailer(Protocol):
    async def send(self, email: OutgoingEmail) -> None: ...


class SmtpMailer:
    def __init__(self, *, host: str, port: int, sender: str, username: str = "", password: str = "",
                 security: str = "none", timeout: float = 20):
        self.host, self.port, self.sender = host, port, sender
        self.username, self.password, self.security, self.timeout = username, password, security, timeout

    def _message(self, email: OutgoingEmail) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = formataddr((email.to_name or "", email.to_address))
        msg["Subject"] = email.subject
        msg["Message-ID"] = email.message_id
        msg.set_content(email.text)
        msg.add_alternative(email.html, subtype="html")
        return msg

    def _send(self, email: OutgoingEmail) -> None:
        context = ssl.create_default_context()
        if self.security == "tls":
            smtp = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=context)
        else:
            smtp = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
        with smtp:
            if self.security == "starttls":
                smtp.starttls(context=context)
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(self._message(email))

    async def send(self, email: OutgoingEmail) -> None:
        await asyncio.to_thread(self._send, email)


class ConsoleMailer:
    """Logs instead of sending (RS_EMAIL_BACKEND=console)."""

    async def send(self, email: OutgoingEmail) -> None:
        log.info("email to %s: %s\n%s", email.to_address, email.subject, email.text)


class MemoryMailer:
    """Keeps what was sent (tests)."""

    def __init__(self, fail: bool = False):
        self.sent: list[OutgoingEmail] = []
        self.fail = fail

    async def send(self, email: OutgoingEmail) -> None:
        if self.fail:
            raise ConnectionError("smtp unavailable")
        self.sent.append(email)


def build_mailer(settings: Settings) -> Mailer:
    if settings.email_backend == "console":
        return ConsoleMailer()
    return SmtpMailer(host=settings.smtp_host, port=settings.smtp_port, sender=settings.email_from,
                      username=settings.smtp_username, password=settings.smtp_password,
                      security=settings.smtp_security)
