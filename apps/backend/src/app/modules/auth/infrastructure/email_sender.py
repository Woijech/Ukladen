import re
import smtplib
import ssl
from collections import deque
from email.message import EmailMessage as SmtpMessage
from email.utils import formatdate, make_msgid
from html import escape
from urllib.parse import urlencode

from celery import Celery
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.core.config import Settings
from app.modules.auth.application.ports import EmailDeliveryUnavailable
from app.modules.auth.application.registration import normalize_email
from app.modules.auth.domain.entities import TokenType


class EmailMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    kind: TokenType
    email: str = Field(min_length=1, max_length=320)
    token: SecretStr = Field(min_length=43, max_length=43, repr=False)

    @field_validator("email")
    @classmethod
    def normalize_recipient(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: SecretStr) -> SecretStr:
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", value.get_secret_value()) is None:
            raise ValueError("Invalid token format.")
        return value


class FakeEmailSender:
    """Capture development messages in memory; never send email or log their contents."""

    def __init__(self) -> None:
        # ponytail: keep 100 messages per process; a real provider must own durable delivery.
        self.messages: deque[EmailMessage] = deque(maxlen=100)

    def send_email_verification(self, email: str, token: str) -> None:
        self._record(TokenType.EMAIL_VERIFICATION, email, token)

    def send_password_reset(self, email: str, token: str) -> None:
        self._record(TokenType.PASSWORD_RESET, email, token)

    def _record(self, kind: TokenType, email: str, token: str) -> None:
        try:
            message = EmailMessage.model_validate({"kind": kind, "email": email, "token": token})
            if message not in self.messages:
                self.messages.append(message)
        except Exception:
            raise EmailDeliveryUnavailable("Email delivery is unavailable.") from None


class CeleryEmailSender:
    """Enqueue validated token data after commit; queue acceptance is not email delivery."""

    def __init__(self, celery: Celery, settings: Settings) -> None:
        self.celery = celery
        self.settings = settings

    def send_email_verification(self, email: str, token: str) -> None:
        self._enqueue(TokenType.EMAIL_VERIFICATION, email, token)

    def send_password_reset(self, email: str, token: str) -> None:
        self._enqueue(TokenType.PASSWORD_RESET, email, token)

    def _enqueue(self, kind: TokenType, email: str, token: str) -> None:
        try:
            if (
                self.settings.auth_email_delivery_mode not in ("fake", "smtp")
                or self.celery.conf.task_protocol != 2
            ):
                raise EmailDeliveryUnavailable("Email delivery is unavailable.")
            message = EmailMessage.model_validate({"kind": kind, "email": email, "token": token})
            self.celery.send_task(
                "auth.send_email",
                kwargs={
                    "kind": message.kind.value,
                    "email": message.email,
                    "token": message.token.get_secret_value(),
                },
                argsrepr="()",
                kwargsrepr="{<redacted>}",
                ignore_result=True,
                retry=False,
            )
        except Exception:
            raise EmailDeliveryUnavailable("Email delivery is unavailable.") from None


class SmtpEmailSender:
    """Deliver through SMTP in the worker; never log credentials, recipients or message bodies."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send_email_verification(self, email: str, token: str) -> None:
        self._send(TokenType.EMAIL_VERIFICATION, email, token)

    def send_password_reset(self, email: str, token: str) -> None:
        self._send(TokenType.PASSWORD_RESET, email, token)

    def _send(self, kind: TokenType, email: str, token: str) -> None:
        try:
            config = self.settings
            if (
                config.auth_email_delivery_mode != "smtp"
                or config.smtp_host is None
                or config.smtp_from_email is None
            ):
                raise EmailDeliveryUnavailable("Email delivery is unavailable.")
            data = EmailMessage.model_validate({"kind": kind, "email": email, "token": token})
            verification = kind == TokenType.EMAIL_VERIFICATION
            subject = "Verify your Ukladen email" if verification else "Reset your Ukladen password"
            lifetime = (
                config.auth_email_verification_ttl_seconds
                if verification
                else config.auth_password_reset_ttl_seconds
            )
            message = SmtpMessage()
            message["From"] = config.smtp_from_email
            message["To"] = data.email
            message["Subject"] = subject
            message["Date"] = formatdate(localtime=False, usegmt=True)
            message["Message-ID"] = make_msgid(domain=config.smtp_from_email.rsplit("@", 1)[1])
            message.set_content(
                f"{subject}. Your single-use token is:\n\n{data.token.get_secret_value()}\n\n"
                f"It expires {lifetime} seconds after the request. "
                "If you did not request this email, you can ignore it.\n"
            )
            if verification and config.auth_email_verification_url is not None:
                link = f"{config.auth_email_verification_url}#{urlencode({'token': token})}"
                message.set_content(
                    f"Verify your Ukladen email by opening this link:\n\n{link}\n\n"
                    f"The link expires {lifetime} seconds after the request. "
                    "If you did not request this email, you can ignore it.\n"
                )
                message.add_alternative(
                    "<html><body><p>Verify your Ukladen email:</p>"
                    f'<p><a href="{escape(link, quote=True)}">Confirm email address</a></p>'
                    f"<p>The link expires {lifetime} seconds after the request. "
                    "If you did not request this email, you can ignore it.</p></body></html>",
                    subtype="html",
                )
            if config.smtp_security == "tls":
                connection = smtplib.SMTP_SSL(
                    config.smtp_host,
                    config.smtp_port,
                    timeout=config.smtp_timeout_seconds,
                    context=ssl.create_default_context(),
                )
            else:
                connection = smtplib.SMTP(
                    config.smtp_host, config.smtp_port, timeout=config.smtp_timeout_seconds
                )
            with connection as smtp:
                if config.smtp_security == "starttls":
                    smtp.starttls(context=ssl.create_default_context())
                if config.smtp_username is not None and config.smtp_password is not None:
                    smtp.login(
                        config.smtp_username.get_secret_value(),
                        config.smtp_password.get_secret_value(),
                    )
                if smtp.send_message(
                    message, from_addr=config.smtp_from_email, to_addrs=[data.email]
                ):
                    raise EmailDeliveryUnavailable("Email delivery is unavailable.")
        except Exception:
            raise EmailDeliveryUnavailable("Email delivery is unavailable.") from None
