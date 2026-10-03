import logging
import smtplib
import ssl
from collections.abc import Iterator
from email import message_from_bytes, policy
from email.message import EmailMessage as SmtpMessage
from queue import Queue
from socketserver import StreamRequestHandler, TCPServer
from threading import Thread
from types import ModuleType
from typing import cast
from unittest.mock import Mock, create_autospec
from uuid import UUID, uuid4

import pytest
from celery import Celery
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from test_auth_email_delivery import (
    EMAIL,
    TOKEN,
)
from test_auth_email_delivery import (
    email_tasks as email_tasks,
)
from test_auth_email_delivery import (
    fake_settings as fake_settings,
)
from test_auth_email_delivery import (
    settings as settings,
)
from test_auth_http import PASSWORD, csrf_headers
from test_auth_http import browser_settings as browser_settings
from test_auth_http import concurrent_engine as concurrent_engine
from test_auth_http import live_client as live_client

from app.core.config import Settings
from app.modules.auth.application.ports import EmailDeliveryUnavailable, EmailSender
from app.modules.auth.domain.entities import TokenType
from app.modules.auth.infrastructure import email_sender
from app.modules.auth.infrastructure.email_sender import CeleryEmailSender, SmtpEmailSender
from app.modules.auth.infrastructure.orm import OneTimeTokenModel
from app.modules.auth.infrastructure.token_service import hash_token
from app.modules.users.infrastructure.orm import UserModel


@pytest.fixture
def smtp_settings(settings: Settings) -> Settings:
    return Settings.model_validate(
        settings.model_dump()
        | {
            "auth_email_delivery_mode": "smtp",
            "smtp_host": "smtp.example.com",
            "smtp_from_email": "noreply@example.com",
            "smtp_username": "smtp-user",
            "smtp_password": "smtp-secret",
        }
    )


@pytest.mark.parametrize(
    "update",
    [
        {"smtp_host": None},
        {"smtp_host": "smtp.example.com\r\nDATA"},
        {"smtp_from_email": None},
        {"smtp_from_email": "invalid"},
        {"smtp_from_email": "Sender <sender@example.com>"},
        {"smtp_from_email": "sender@example.com\r\nBcc: other@example.com"},
        {"smtp_username": None},
        {"smtp_password": None},
        {"smtp_password": ""},
        {"smtp_security": "none"},
        {"smtp_security": "invalid"},
        {"smtp_port": 0},
        {"smtp_port": 65536},
        {"smtp_timeout_seconds": 0},
        {"smtp_timeout_seconds": 61},
        {"smtp_timeout_seconds": float("inf")},
    ],
)
def test_smtp_configuration_fails_closed_without_exposing_credentials(
    smtp_settings: Settings, update: dict[str, object]
) -> None:
    with pytest.raises(ValidationError) as error:
        Settings.model_validate(smtp_settings.model_dump() | update)
    assert "smtp-secret" not in str(error.value)
    assert "smtp-secret" not in repr(smtp_settings) and "smtp-user" not in repr(smtp_settings)


@pytest.mark.parametrize("security", ["starttls", "tls", "none"])
@pytest.mark.parametrize("kind", list(TokenType))
def test_smtp_message_transport_and_tls_validation(
    smtp_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    security: str,
    kind: TokenType,
) -> None:
    configured = Settings.model_validate(
        smtp_settings.model_dump()
        | {
            "smtp_security": security,
            "smtp_port": 465 if security == "tls" else 587,
            "smtp_username": None if security == "none" else "smtp-user",
            "smtp_password": None if security == "none" else "smtp-secret",
        }
    )
    connection = create_autospec(smtplib.SMTP, instance=True)
    connection.__enter__.return_value = connection
    connection.send_message.return_value = {}
    factory = Mock(return_value=connection)
    other_factory = Mock(side_effect=AssertionError("Wrong SMTP transport."))
    monkeypatch.setattr(email_sender.smtplib, "SMTP_SSL" if security == "tls" else "SMTP", factory)
    monkeypatch.setattr(
        email_sender.smtplib, "SMTP" if security == "tls" else "SMTP_SSL", other_factory
    )
    sender: EmailSender = SmtpEmailSender(configured)
    method = (
        sender.send_email_verification
        if kind == TokenType.EMAIL_VERIFICATION
        else sender.send_password_reset
    )
    with caplog.at_level(logging.DEBUG):
        assert method(" Student@Example.COM ", TOKEN) is None
    assert factory.call_args.args == ("smtp.example.com", configured.smtp_port)
    assert factory.call_args.kwargs["timeout"] == 10
    if security != "none":
        context = (
            factory.call_args.kwargs["context"]
            if security == "tls"
            else connection.starttls.call_args.kwargs["context"]
        )
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
        connection.login.assert_called_once_with("smtp-user", "smtp-secret")
    else:
        connection.starttls.assert_not_called()
        connection.login.assert_not_called()
    calls = [call[0] for call in connection.mock_calls]
    if security == "starttls":
        assert calls.index("starttls") < calls.index("login") < calls.index("send_message")
    else:
        connection.starttls.assert_not_called()
    message = connection.send_message.call_args.args[0]
    assert isinstance(message, SmtpMessage)
    assert message["From"] == "noreply@example.com" and message["To"] == EMAIL
    assert connection.send_message.call_args.kwargs == {
        "from_addr": "noreply@example.com",
        "to_addrs": [EMAIL],
    }
    assert TOKEN in message.get_content() and TOKEN not in str(message.items())
    assert ("Verify" if kind == TokenType.EMAIL_VERIFICATION else "Reset") in message["Subject"]
    assert str(86400 if kind == TokenType.EMAIL_VERIFICATION else 3600) in message.get_content()
    assert message["Date"] and message["Message-ID"]
    assert TOKEN not in caplog.text and "smtp-secret" not in caplog.text
    connection.__exit__.assert_called_once()


@pytest.mark.parametrize(
    "failure", ["connect", "starttls", "login", "send", "refused", "recipient", "token", "disabled"]
)
def test_smtp_errors_are_sanitized_and_never_fall_back_to_plaintext(
    smtp_settings: Settings, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    connection = create_autospec(smtplib.SMTP, instance=True)
    connection.__enter__.return_value = connection
    connection.send_message.return_value = {}
    factory = Mock(return_value=connection)
    monkeypatch.setattr(email_sender.smtplib, "SMTP", factory)
    if failure == "connect":
        factory.side_effect = TimeoutError(TOKEN)
    elif failure in ("starttls", "login", "send"):
        getattr(
            connection, "send_message" if failure == "send" else failure
        ).side_effect = smtplib.SMTPException(TOKEN)
    elif failure == "refused":
        connection.send_message.return_value = {EMAIL: (550, TOKEN.encode())}
    elif failure == "disabled":
        smtp_settings = smtp_settings.model_copy(update={"auth_email_delivery_mode": "disabled"})
    with pytest.raises(EmailDeliveryUnavailable) as error:
        SmtpEmailSender(smtp_settings).send_password_reset(
            f"{EMAIL}\r\nBcc: other@example.com" if failure == "recipient" else EMAIL,
            "!" * 43 if failure == "token" else TOKEN,
        )
    assert str(error.value) == "Email delivery is unavailable." and error.value.__suppress_context__
    if failure in ("connect", "starttls", "login", "recipient", "token", "disabled"):
        connection.send_message.assert_not_called()
    if failure == "starttls":
        connection.login.assert_not_called()
        factory.assert_called_once()


@pytest.mark.parametrize("kind", list(TokenType))
def test_worker_smtp_delivery_and_failure_log_redaction(
    email_tasks: ModuleType,
    smtp_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    kind: TokenType,
) -> None:
    monkeypatch.setattr(email_tasks, "get_settings", lambda: smtp_settings)
    connection = create_autospec(smtplib.SMTP, instance=True)
    connection.__enter__.return_value = connection
    connection.send_message.return_value = {}
    monkeypatch.setattr(email_sender.smtplib, "SMTP", Mock(return_value=connection))
    payload = {"kind": kind.value, "email": EMAIL, "token": TOKEN}
    with caplog.at_level(logging.DEBUG):
        result = email_tasks.send_auth_email.apply(kwargs=payload)
        assert result.successful() and result.get() is None
        connection.send_message.side_effect = smtplib.SMTPDataError(550, TOKEN.encode())
        failed = email_tasks.send_auth_email.apply(kwargs=payload)
    assert failed.failed() and isinstance(failed.result, EmailDeliveryUnavailable)
    assert TOKEN not in str(failed.traceback) and TOKEN not in caplog.text
    assert "smtp-secret" not in caplog.text
    assert all(TOKEN not in repr(record.__dict__) for record in caplog.records)
    assert not email_tasks.fake_sender.messages


@pytest.fixture
def smtp_receiver() -> Iterator[tuple[int, Queue[bytes]]]:
    """Receive SMTP on loopback only, without any external service or delivery."""
    messages: Queue[bytes] = Queue()

    class Receiver(StreamRequestHandler):
        def handle(self) -> None:
            self.connection.settimeout(5)
            self.wfile.write(b"220 localhost test receiver\r\n")
            while line := self.rfile.readline(8192):
                command = line.split(b" ", 1)[0].strip().upper()
                if command in (b"EHLO", b"HELO", b"MAIL", b"RCPT", b"RSET"):
                    self.wfile.write(b"250 OK\r\n")
                elif command == b"DATA":
                    self.wfile.write(b"354 Send message\r\n")
                    body = bytearray()
                    while data := self.rfile.readline(8192):
                        if data == b".\r\n":
                            break
                        body.extend(data[1:] if data.startswith(b"..") else data)
                    messages.put(bytes(body))
                    self.wfile.write(b"250 Accepted\r\n")
                elif command == b"QUIT":
                    self.wfile.write(b"221 Bye\r\n")
                    return
                else:
                    self.wfile.write(b"502 Not implemented\r\n")

    with TCPServer(("127.0.0.1", 0), Receiver) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        try:
            yield server.server_address[1], messages
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_worker_delivers_both_messages_over_real_smtp(
    email_tasks: ModuleType,
    smtp_settings: Settings,
    smtp_receiver: tuple[int, Queue[bytes]],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    port, messages = smtp_receiver
    configured = Settings.model_validate(
        smtp_settings.model_dump()
        | {
            "smtp_host": "127.0.0.1",
            "smtp_port": port,
            "smtp_security": "none",
            "smtp_username": None,
            "smtp_password": None,
        }
    )
    monkeypatch.setattr(email_tasks, "get_settings", lambda: configured)
    with caplog.at_level(logging.DEBUG):
        for kind in TokenType:
            result = email_tasks.send_auth_email.apply(
                kwargs={"kind": kind.value, "email": EMAIL, "token": TOKEN}
            )
            assert result.successful() and result.get() is None
            message = message_from_bytes(messages.get(timeout=5), policy=policy.default)
            assert isinstance(message, SmtpMessage)
            assert message["To"] == EMAIL and TOKEN in message.get_content()
    assert messages.empty() and not email_tasks.fake_sender.messages
    assert TOKEN not in caplog.text


def test_live_auth_flows_commit_then_queue_and_deliver_smtp(
    live_client: TestClient,
    concurrent_engine: Engine,
    email_tasks: ModuleType,
    smtp_settings: Settings,
    smtp_receiver: tuple[int, Queue[bytes]],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    port, messages = smtp_receiver
    configured = Settings.model_validate(
        smtp_settings.model_dump()
        | {
            "smtp_host": "127.0.0.1",
            "smtp_port": port,
            "smtp_security": "none",
            "smtp_username": None,
            "smtp_password": None,
        }
    )
    monkeypatch.setattr(email_tasks, "get_settings", lambda: configured)
    app = cast(FastAPI, live_client.app)
    app.state.settings = app.state.settings.model_copy(update={"auth_email_delivery_mode": "smtp"})
    queue = f"auth-smtp-test-{uuid4().hex}"
    producer = Celery("auth-smtp-test", broker="memory://", set_as_current=False)
    producer.conf.update(task_protocol=2, task_serializer="json", task_default_queue=queue)
    app.state.email_sender = CeleryEmailSender(producer, configured)
    delivered_tokens: list[str] = []

    def receive_after_commit(expected_kind: TokenType, response_text: str) -> str:
        with producer.connection_for_read() as connection:
            inbox = connection.SimpleQueue(queue)
            try:
                queued = inbox.get(block=False)
                try:
                    args, payload, _ = queued.payload
                    token = payload["token"]
                    assert payload["kind"] == expected_kind.value
                    assert token not in response_text and token not in repr(queued.headers)
                    # A separate database connection sees the token before worker delivery.
                    with Session(concurrent_engine) as database:
                        stored = database.scalar(
                            select(OneTimeTokenModel).where(
                                OneTimeTokenModel.token_hash == hash_token(token)
                            )
                        )
                        assert (
                            stored
                            and stored.used_at is None
                            and stored.token_type == expected_kind.value
                        )
                    result = email_tasks.send_auth_email.apply(
                        args=args, kwargs=payload, headers=queued.headers
                    )
                    assert result.successful() and result.get() is None
                    message = message_from_bytes(messages.get(timeout=5), policy=policy.default)
                    assert isinstance(message, SmtpMessage)
                    assert message["To"] == EMAIL and token in message.get_content()
                    delivered_tokens.append(token)
                    return token
                finally:
                    queued.ack()
            finally:
                inbox.close()

    try:
        with caplog.at_level(logging.DEBUG):
            registered = live_client.post(
                "/api/v1/auth/register",
                json={"email": EMAIL, "password": PASSWORD},
                headers=csrf_headers(live_client),
            )
            assert registered.status_code == 201
            receive_after_commit(TokenType.EMAIL_VERIFICATION, registered.text)
            resend = live_client.post(
                "/api/v1/auth/email-verification/request",
                json={},
                headers=csrf_headers(live_client),
            )
            assert resend.status_code == 202
            verification = receive_after_commit(TokenType.EMAIL_VERIFICATION, resend.text)
            assert (
                live_client.post(
                    "/api/v1/auth/email-verification/confirm",
                    json={"token": verification},
                    headers=csrf_headers(live_client),
                ).status_code
                == 204
            )
            with Session(concurrent_engine) as database:
                user = database.get(UserModel, UUID(registered.json()["user_id"]))
                assert user and user.email_verified_at
            reset = live_client.post(
                "/api/v1/auth/password-reset/request",
                json={"email": EMAIL},
                headers=csrf_headers(live_client),
            )
            assert reset.status_code == 202
            reset_token = receive_after_commit(TokenType.PASSWORD_RESET, reset.text)
            new_password = "new SMTP test password"
            assert (
                live_client.post(
                    "/api/v1/auth/password-reset/confirm",
                    json={"token": reset_token, "new_password": new_password},
                    headers=csrf_headers(live_client),
                ).status_code
                == 204
            )
            assert live_client.get("/api/v1/auth/sessions").status_code == 401
            for password, expected in ((PASSWORD, 401), (new_password, 200)):
                assert (
                    live_client.post(
                        "/api/v1/auth/login",
                        json={"email": EMAIL, "password": password},
                        headers=csrf_headers(live_client),
                    ).status_code
                    == expected
                )
            assert (
                live_client.post(
                    "/api/v1/auth/password-reset/confirm",
                    json={"token": reset_token, "new_password": new_password},
                    headers=csrf_headers(live_client),
                ).status_code
                == 400
            )
        assert all(token not in caplog.text for token in delivered_tokens)
        assert not email_tasks.fake_sender.messages and messages.empty()
    finally:
        with producer.connection_for_read() as connection:
            inbox = connection.SimpleQueue(queue)
            inbox.queue.delete()
            inbox.close()
        producer.close()
