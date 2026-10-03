import importlib
import logging
import os
from types import ModuleType
from unittest.mock import Mock, create_autospec
from uuid import uuid4

import pytest
from celery import Celery
from pydantic import ValidationError
from redis import Redis
from test_auth_sessions import settings as settings

from app.core import config
from app.core.config import Settings
from app.modules.auth.application.ports import EmailDeliveryUnavailable, EmailSender
from app.modules.auth.domain.entities import TokenType
from app.modules.auth.infrastructure.email_sender import CeleryEmailSender, FakeEmailSender
from app.modules.auth.infrastructure.token_service import generate_token

EMAIL = "student@example.com"
TOKEN = generate_token()


@pytest.fixture
def fake_settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"auth_email_delivery_mode": "fake"})


@pytest.fixture
def email_tasks(monkeypatch: pytest.MonkeyPatch, fake_settings: Settings) -> ModuleType:
    monkeypatch.setattr(config, "get_settings", lambda: fake_settings)
    module = importlib.import_module("app.modules.auth.infrastructure.email_tasks")
    monkeypatch.setattr(module, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(module, "fake_sender", FakeEmailSender())
    return module


@pytest.fixture
def celery() -> Mock:
    app = create_autospec(Celery, instance=True)
    app.conf.task_protocol = 2
    return app


@pytest.mark.parametrize("kind", list(TokenType))
@pytest.mark.parametrize("mode", ["fake", "smtp"])
def test_queue_payload_and_representations(
    celery: Mock, fake_settings: Settings, kind: TokenType, mode: str
) -> None:
    sender: EmailSender = CeleryEmailSender(
        celery, fake_settings.model_copy(update={"auth_email_delivery_mode": mode})
    )
    method = (
        sender.send_email_verification
        if kind == TokenType.EMAIL_VERIFICATION
        else sender.send_password_reset
    )
    assert method(" Student@Example.COM ", TOKEN) is None
    celery.send_task.assert_called_once_with(
        "auth.send_email",
        kwargs={"kind": kind.value, "email": EMAIL, "token": TOKEN},
        argsrepr="()",
        kwargsrepr="{<redacted>}",
        ignore_result=True,
        retry=False,
    )


@pytest.mark.parametrize("failure", ["disabled", "protocol", "queue", "recipient", "token"])
def test_enqueue_errors_are_sanitized_and_fail_closed(
    celery: Mock, fake_settings: Settings, failure: str
) -> None:
    if failure == "disabled":
        fake_settings = fake_settings.model_copy(update={"auth_email_delivery_mode": "disabled"})
    if failure == "protocol":
        celery.conf.task_protocol = 1
    if failure == "queue":
        celery.send_task.side_effect = RuntimeError(TOKEN)
    sender = CeleryEmailSender(celery, fake_settings)
    with pytest.raises(EmailDeliveryUnavailable) as error:
        sender.send_password_reset(
            TOKEN if failure == "recipient" else EMAIL,
            "!" * 43 if failure == "token" else TOKEN,
        )
    assert str(error.value) == "Email delivery is unavailable." and error.value.__suppress_context__
    if failure != "queue":
        celery.send_task.assert_not_called()


def test_delivery_defaults_disabled_and_rejects_unknown_provider(settings: Settings) -> None:
    assert Settings.model_fields["auth_email_delivery_mode"].default == "disabled"
    with pytest.raises(ValidationError):
        Settings.model_validate(settings.model_dump() | {"auth_email_delivery_mode": "unknown"})


def test_fake_records_both_kinds_without_logging_and_bounds_memory(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = FakeEmailSender()
    sender: EmailSender = fake
    with caplog.at_level(logging.DEBUG):
        sender.send_email_verification(EMAIL, TOKEN)
        sender.send_email_verification(EMAIL, TOKEN)
        sender.send_password_reset(EMAIL, TOKEN)
    assert [message.kind for message in fake.messages] == list(TokenType)
    assert all(message.token.get_secret_value() == TOKEN for message in fake.messages)
    assert TOKEN not in repr(fake.messages) and TOKEN not in caplog.text
    assert all(TOKEN not in message.model_dump_json() for message in fake.messages)
    for number in range(101):
        sender.send_password_reset(EMAIL, f"{number:043}")
    assert len(fake.messages) == 100
    assert fake.messages[0].token.get_secret_value() == f"{1:043}"


def test_fake_invalid_payload_is_sanitized_and_not_recorded() -> None:
    fake = FakeEmailSender()
    with pytest.raises(EmailDeliveryUnavailable) as error:
        fake.send_email_verification(TOKEN, TOKEN)
    assert str(error.value) == "Email delivery is unavailable." and error.value.__suppress_context__
    assert not fake.messages


def test_worker_task_registration(email_tasks: ModuleType) -> None:
    assert "app.modules.auth.infrastructure.email_tasks" in email_tasks.celery_app.conf.include
    email_tasks.celery_app.loader.import_default_modules()
    task = email_tasks.celery_app.tasks["auth.send_email"]
    assert task.name == email_tasks.send_auth_email.name
    assert task.ignore_result and not task.store_errors_even_if_ignored
    assert email_tasks.celery_app.conf.task_protocol == 2


@pytest.mark.parametrize("kind", list(TokenType))
def test_worker_executes_and_deduplicates_fake_delivery(
    email_tasks: ModuleType, caplog: pytest.LogCaptureFixture, kind: TokenType
) -> None:
    with caplog.at_level(logging.DEBUG):
        for _ in range(2):
            result = email_tasks.send_auth_email.apply(
                kwargs={"kind": kind.value, "email": EMAIL, "token": TOKEN}
            )
            assert result.successful() and result.get() is None
    messages = email_tasks.fake_sender.messages
    assert len(messages) == 1 and messages[0].kind == kind
    assert messages[0].email == EMAIL and messages[0].token.get_secret_value() == TOKEN
    assert TOKEN not in caplog.text and TOKEN not in repr(messages)


@pytest.mark.parametrize(
    "failure",
    ["disabled", "settings", "sender", "kind", "recipient", "token", "extra", "positional"],
)
def test_worker_errors_and_task_logs_never_echo_tokens(
    email_tasks: ModuleType,
    fake_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failure: str,
) -> None:
    if failure == "disabled":
        monkeypatch.setattr(
            email_tasks,
            "get_settings",
            lambda: fake_settings.model_copy(update={"auth_email_delivery_mode": "disabled"}),
        )
    elif failure == "settings":
        monkeypatch.setattr(email_tasks, "get_settings", Mock(side_effect=RuntimeError(TOKEN)))
    elif failure == "sender":
        monkeypatch.setattr(
            email_tasks.fake_sender, "send_password_reset", Mock(side_effect=RuntimeError(TOKEN))
        )
    payload = {"kind": TokenType.PASSWORD_RESET.value, "email": EMAIL, "token": TOKEN}
    if failure in ("kind", "recipient"):
        payload["kind" if failure == "kind" else "email"] = TOKEN
    elif failure == "token":
        payload["token"] = "!" * 43
    elif failure == "extra":
        payload["extra"] = TOKEN
    with caplog.at_level(logging.DEBUG):
        result = email_tasks.send_auth_email.apply(
            args=(TOKEN,) if failure == "positional" else (), kwargs=payload
        )
    assert result.failed() and isinstance(result.result, EmailDeliveryUnavailable)
    assert str(result.result) == "Email delivery is unavailable."
    assert TOKEN not in caplog.text and TOKEN not in str(result.traceback)
    assert not email_tasks.fake_sender.messages
    # Celery error records carry a separate context with argument representations.
    assert all(TOKEN not in repr(record.__dict__) for record in caplog.records)


def test_live_redis_queue_to_fake_worker(
    email_tasks: ModuleType, fake_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    url = os.environ.get("AUTH_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set AUTH_TEST_REDIS_URL to run email queue integration checks.")
    queue = f"ukladen-auth-email-test-{uuid4().hex}"
    prefix = f"{queue}:"
    app = Celery("auth-email-test", broker=url)
    app.conf.update(
        task_protocol=2,
        task_serializer="json",
        accept_content=["json"],
        task_ignore_result=True,
        task_default_queue=queue,
        task_default_exchange=queue,
        task_default_routing_key=queue,
        broker_transport_options={
            "global_keyprefix": prefix,
            "socket_connect_timeout": 3,
            "socket_timeout": 3,
        },
    )
    redis = Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
    sender = CeleryEmailSender(app, fake_settings)
    try:
        sender.send_email_verification(EMAIL, TOKEN)
        sender.send_password_reset(EMAIL, TOKEN)
        assert not email_tasks.fake_sender.messages
        with app.connection_for_read() as connection:
            inbox = connection.SimpleQueue(queue)
            try:
                for kind in TokenType:
                    message = inbox.get(block=False)
                    try:
                        assert message.headers["task"] == "auth.send_email"
                        assert TOKEN not in repr(message.headers)
                        args, payload, _ = message.payload
                        assert payload == {"kind": kind.value, "email": EMAIL, "token": TOKEN}
                        with caplog.at_level(logging.DEBUG):
                            result = email_tasks.send_auth_email.apply(
                                args=args, kwargs=payload, headers=message.headers
                            )
                        assert result.successful() and result.get() is None
                    finally:
                        message.ack()
                assert redis.llen(f"{prefix}{queue}") == 0
            finally:
                inbox.queue.delete()
                inbox.close()
        assert [message.kind for message in email_tasks.fake_sender.messages] == list(TokenType)
        assert TOKEN not in caplog.text
    finally:
        app.close()
        keys = list(redis.scan_iter(match=f"{prefix}*"))
        if keys:
            redis.delete(*keys)
        redis.close()
