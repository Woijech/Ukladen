import re
from collections import deque

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
                self.settings.auth_email_delivery_mode != "fake"
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
