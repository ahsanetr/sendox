"""Transactional email.

Plain SMTP, which Mailpit answers locally and Amazon SES answers in production
(SES speaks SMTP, so the send path does not change when phase 1.10 points this at
SES and adds domain authentication).

Sending happens in a worker, never in a request: a slow mail server must not slow
down a signup.
"""

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

import structlog

from sendox_api.config import Settings

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Outgoing:
    to: str
    subject: str
    text: str


def send(settings: Settings, message: Outgoing) -> None:
    email = EmailMessage()
    email["From"] = settings.mail_from
    email["To"] = message.to
    email["Subject"] = message.subject
    email.set_content(message.text)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        # Mailpit accepts plaintext; SES requires STARTTLS and credentials.
        if settings.smtp_use_tls:
            server.starttls(context=ssl.create_default_context())
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(email)

    log.info("email.sent", to=message.to, subject=message.subject)


def verification_email(settings: Settings, to: str, token: str) -> Outgoing:
    link = f"{settings.web_base_url}/account/verify?token={token}"
    return Outgoing(
        to=to,
        subject="Confirm your Sendox email address",
        text=(
            "Welcome to Sendox.\n\n"
            f"Confirm your email address to activate your account:\n{link}\n\n"
            "The link expires in 24 hours. If you did not sign up, ignore this email.\n"
        ),
    )


def password_reset_email(settings: Settings, to: str, token: str) -> Outgoing:
    link = f"{settings.web_base_url}/account/reset?token={token}"
    return Outgoing(
        to=to,
        subject="Reset your Sendox password",
        text=(
            "Someone asked to reset the password for this Sendox account.\n\n"
            f"Set a new password:\n{link}\n\n"
            "The link expires in one hour. If this was not you, no action is needed "
            "and your password is unchanged.\n"
        ),
    )


def invitation_email(
    settings: Settings, to: str, token: str, workspace: str, role: str, inviter: str
) -> Outgoing:
    link = f"{settings.web_base_url}/account/invite?token={token}"
    return Outgoing(
        to=to,
        subject=f"{inviter} invited you to {workspace} on Sendox",
        text=(
            f"{inviter} has invited you to join the {workspace} workspace on Sendox "
            f"as {role}.\n\n"
            f"Accept the invitation:\n{link}\n\n"
            "The link expires in 7 days.\n"
        ),
    )
