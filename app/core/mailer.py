"""Pluggable mailer.

MAILER_MODE=log  -> messages are printed to backend logs (hackathon demo mode).
MAILER_MODE=smtp -> sent via the SMTP_* environment settings.
"""
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

settings = get_settings()


def send_email(to: str, subject: str, body: str) -> None:
    if settings.mailer_mode != "smtp":
        # Demo mode: surface the message in logs so flows stay demonstrable
        print(f"[MAILER:log] to={to} subject={subject}\n{body}", flush=True)
        return

    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


def send_password_reset_email(to: str, raw_token: str) -> None:
    link = f"{settings.frontend_url}/reset-password?token={raw_token}"
    body = (
        "You requested a password reset for your Brightloop account.\n\n"
        f"Reset link (valid for 60 minutes, single use):\n{link}\n\n"
        "If you did not request this, ignore this email."
    )
    send_email(to, "Reset your Brightloop password", body)
