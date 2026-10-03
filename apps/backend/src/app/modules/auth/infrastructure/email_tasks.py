from celery import Task

from app.core.config import get_settings
from app.modules.auth.application.ports import EmailDeliveryUnavailable, EmailSender
from app.modules.auth.domain.entities import TokenType
from app.modules.auth.infrastructure.email_sender import (
    EmailMessage,
    FakeEmailSender,
    SmtpEmailSender,
)
from app.workers.celery_app import celery_app

fake_sender = FakeEmailSender()


@celery_app.task(
    name="auth.send_email", bind=True, ignore_result=True, store_errors_even_if_ignored=False
)
def send_auth_email(task: Task, *args: object, **payload: object) -> None:
    # Also redact direct/eager execution and malformed jobs before Celery handles failures.
    task.request.update(argsrepr="(<redacted>)", kwargsrepr="{<redacted>}")
    try:
        settings = get_settings()
        if args or settings.auth_email_delivery_mode not in ("fake", "smtp"):
            raise EmailDeliveryUnavailable("Email delivery is unavailable.")
        message = EmailMessage.model_validate(payload)
        sender: EmailSender = (
            SmtpEmailSender(settings)
            if settings.auth_email_delivery_mode == "smtp"
            else fake_sender
        )
        token = message.token.get_secret_value()
        if message.kind == TokenType.EMAIL_VERIFICATION:
            sender.send_email_verification(message.email, token)
        else:
            sender.send_password_reset(message.email, token)
    except Exception:
        raise EmailDeliveryUnavailable("Email delivery is unavailable.") from None
