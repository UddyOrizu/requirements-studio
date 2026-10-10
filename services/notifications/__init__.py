"""Notifications (S2): email. Messages are queued in email_outbox in the same transaction as the change they announce
and sent by the API process or the worker (RS_EMAIL_SENDER), over SMTP."""
from .mailer import ConsoleMailer, Mailer, MemoryMailer, OutgoingEmail, SmtpMailer, build_mailer
from .service import deliver_pending, queue_email

__all__ = ["ConsoleMailer", "Mailer", "MemoryMailer", "OutgoingEmail", "SmtpMailer", "build_mailer",
           "deliver_pending", "queue_email"]
