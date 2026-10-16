import smtplib
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, create_autospec
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, select
from sqlalchemy.orm import Session
from test_auth_google_login import service
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import migration_config
from test_auth_sessions import cache as cache
from test_auth_sessions import concurrent_engine as concurrent_engine
from test_auth_sessions import settings as settings
from test_auth_smtp_delivery import EMAIL, TOKEN
from test_auth_smtp_delivery import smtp_settings as smtp_settings

from alembic import command
from app.core.config import Settings
from app.modules.auth.application.dto import VerifiedGoogleIdentity
from app.modules.auth.infrastructure import email_sender
from app.modules.auth.infrastructure.email_sender import SmtpEmailSender
from app.modules.auth.infrastructure.orm import IdentityModel, OneTimeTokenModel
from app.modules.users.infrastructure.orm import UserModel


def test_google_link_mail_uses_a_private_fragment_and_oauth_expiry(
    smtp_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Settings.model_validate(
        smtp_settings.model_dump()
        | {
            "auth_email_verification_url": "https://ukladen.example/auth/verify-email",
            "auth_allowed_origins": ["https://ukladen.example"],
            "auth_oauth_state_ttl_seconds": 300,
        }
    )
    connection = create_autospec(smtplib.SMTP, instance=True)
    connection.__enter__.return_value = connection
    connection.send_message.return_value = {}
    monkeypatch.setattr(email_sender.smtplib, "SMTP", Mock(return_value=connection))
    SmtpEmailSender(config).send_google_link_confirmation(EMAIL, TOKEN)
    message = connection.send_message.call_args.args[0]
    link = f"https://ukladen.example/auth/confirm-google-link#token={TOKEN}"
    assert message["Subject"] == "Confirm Google sign-in to Ukladen"
    assert link in message.get_body(preferencelist=("plain",)).get_content()
    assert f'href="{link}"' in message.get_body(preferencelist=("html",)).get_content()
    assert "300 seconds" in message.get_body(preferencelist=("plain",)).get_content()
    assert TOKEN not in str(message.items())


@pytest.mark.parametrize("kind", ["gmail", "external", "mail-proof"])
def test_migration_rechecks_only_unproven_legacy_google_only_email(
    database_connection: Connection,
    kind: str,
) -> None:
    config = migration_config(database_connection)
    command.downgrade(config, "0020_basic_search")
    now, user_id = datetime.now(UTC), uuid4()
    with (
        Session(database_connection, join_transaction_mode="create_savepoint") as database,
        database.begin(),
    ):
        email = "student@gmail.com" if kind == "gmail" else "student@example.com"
        database.add(UserModel(id=user_id, email=email, email_verified_at=now))
        database.flush()
        database.add(
            IdentityModel(
                user_id=user_id,
                provider="google",
                provider_subject="legacy",
                provider_email=email,
                created_at=now,
            )
        )
        if kind == "mail-proof":
            database.add(
                OneTimeTokenModel(
                    user_id=user_id,
                    token_type="email_verification",
                    token_hash="a" * 64,
                    created_at=now - timedelta(minutes=1),
                    expires_at=now + timedelta(minutes=1),
                    used_at=now,
                )
            )
    command.upgrade(config, "head")
    with Session(database_connection) as database:
        user = database.get(UserModel, user_id)
        assert user and (user.email_verified_at is None) == (kind == "external")
        assert (
            database.scalar(select(IdentityModel).where(IdentityModel.user_id == user_id))
            is not None
        )


def test_fresh_workspace_proof_can_finish_a_legacy_passwordless_registration(
    concurrent_engine: Engine,
    cache: Mock,
    settings: Settings,
) -> None:
    user_id = uuid4()
    with Session(concurrent_engine) as database, database.begin():
        database.add(UserModel(id=user_id, email="student@example.com"))
        database.flush()
        database.add(
            IdentityModel(
                user_id=user_id,
                provider="google",
                provider_subject="legacy",
                provider_email="student@example.com",
            )
        )
    with Session(concurrent_engine) as database, database.begin():
        issued = service(database, cache, settings).login(
            VerifiedGoogleIdentity("legacy", "student@example.com", True)
        )
        assert issued.session.user_id == user_id
    with Session(concurrent_engine) as database:
        user = database.get(UserModel, user_id)
        assert user and user.email_verified_at is not None
